"""The request service and the HTTP API on a local chain (phase 2, step 2.6).

Every party signs its own transactions with its own (local test) account; the service holds
only the verifier key and follows the escrow's events. Everything is LOCAL and SIMULATED:
an Anvil chain, the worthless TestUSD token and the committed simulated datasets.
"""

import json
from pathlib import Path

import pytest
from anvil import require_local_chain, test_account
from chain_world import (
    BUDGET,
    PLATFORM,
    REQUESTER,
    REVIEWERS,
    STATION,
    STRANGER,
    VERIFIER,
    ChainWorld,
)
from helpers import catalog, request_bytes
from starlette.testclient import TestClient

from orbit_watch.api import create_app, keys
from orbit_watch.chain import ChainError, request_key, sha256_of_text
from orbit_watch.chain.wallet import Wallet
from orbit_watch.formats import owjson
from orbit_watch.sim.simulator import load_profile, simulate
from orbit_watch.timeutil import parse_utc

ROOT = Path(__file__).resolve().parents[2]
DATASETS = ROOT / "examples" / "simulated" / "datasets"
REQUEST = (ROOT / "examples" / "simulated" / "request.json").read_bytes()
RID = "SIM-REQ-0001"
SPLIT = {"observer": 100_000_000, "reviewer": 10_000_000, "platform_fee": 5_000_000}
DEPOSIT = 135_000_000


class Api:
    """The API through Starlette's TestClient, with keys and idempotency keys."""

    def __init__(self, world):
        self.world = world
        self.http = TestClient(create_app(world.service))
        self.count = 0
        with world.service.storage.db.transaction():
            self.admin = keys.create_key(
                world.service.storage.db, "admin:maintainer", "admin", world.link.now()
            )
        self.keys = {}

    def key(self, party):
        if party not in self.keys:
            role = party.split(":")[0]
            reply = self.post("/v1/admin/keys", self.admin, {"party": party, "role": role})
            self.keys[party] = reply.json()["key"]
        return self.keys[party]

    def get(self, path, party=None, key=None):
        token = key or (self.key(party) if party else self.admin)
        return self.http.get(path, headers={"Authorization": f"Bearer {token}"})

    def post(self, path, key, body=None, content=None, idem=None, headers=None):
        self.count += 1
        all_headers = {
            "Authorization": f"Bearer {key}",
            "Idempotency-Key": idem or f"k{self.count}",
        }
        all_headers.update(headers or {})
        if body is not None:
            content = json.dumps(body).encode()
        return self.http.post(path, content=content, headers=all_headers)

    def act(self, party, path, body=None, content=None, headers=None, expect=200):
        """Do something as ``party``; when the API asks for signatures, sign and send each
        transaction with the party's own wallet and report it, like the command line."""
        reply = self.post(path, self.key(party), body, content, headers=headers)
        if reply.status_code != 202:
            assert reply.status_code == expect, reply.text
            return reply.json()
        prepared = reply.json()
        assert prepared["notice"] == "local Anvil test chain, no real value"
        wallet = self.world.wallet(party)
        result = None
        for item in prepared["sign"]:
            assert item["transaction"]["from"] == wallet.address
            assert set(item["transaction"]) == {"chainId", "from", "to", "data", "value"}
            tx_hash = wallet.send(item["transaction"])
            result = self.report(party, tx_hash)
        return result["request"] or result

    def report(self, party, tx_hash, expect=200):
        reply = self.post("/v1/transactions", self.key(party), {"tx_hash": tx_hash})
        assert reply.status_code == expect, reply.text
        return reply.json()

    def register(self, party):
        view = self.get("/v1/wallet", party).json()
        signature = self.world.wallet(party).sign_message(view["message"])
        reply = self.post(
            "/v1/wallet",
            self.key(party),
            {"address": self.world.address(party), "signature": signature},
        )
        assert reply.status_code == 200, reply.text
        return reply.json()

    def view(self, request_id=RID, party=REQUESTER):
        return self.get(f"/v1/requests/{request_id}", party).json()

    def tick(self):
        reply = self.post("/v1/admin/tick", self.admin)
        assert reply.status_code == 200, reply.text
        return reply.json()

    def balance(self, party):
        return self.get(f"/v1/balances/{party}").json()


@pytest.fixture
def world(tmp_path):
    require_local_chain()
    made = ChainWorld(tmp_path / "service")
    yield made
    made.stop()


@pytest.fixture
def api(world):
    return Api(world)


def open_and_fund(api, request=REQUEST, request_id=RID, split=SPLIT):
    for party in (REQUESTER, STATION, *REVIEWERS):
        if api.world.link.wallet(party) is None:
            api.register(party)
    created = api.post("/v1/requests", api.key(REQUESTER), {"request": json.loads(request)})
    assert created.status_code == 201, created.text
    api.act(REQUESTER, f"/v1/requests/{request_id}/open")
    return api.act(REQUESTER, f"/v1/requests/{request_id}/fund", split)


def deliver(api, dataset, request_id=RID, when="2026-11-02T04:00:00Z"):
    api.act(STATION, f"/v1/requests/{request_id}/reserve")
    api.world.travel(when)
    data = (DATASETS / dataset / "observations.json").read_bytes()
    return api.act(
        STATION,
        f"/v1/requests/{request_id}/deliveries",
        content=data,
        headers={"Content-Type": "application/octet-stream"},
    )


def withdraw(api, party):
    before = api.balance(party)
    api.act(party, "/v1/wallet/withdraw")
    after = api.balance(party)
    assert after["withdrawable"] == 0
    return after["balance"] - before["balance"]


def events(view):
    return [e["event"] for e in view["chain"]["events"]]


# --------------------------------------------------------------------------- the whole chain


def test_an_accepted_request_pays_by_token_transfers(api, world):
    view = open_and_fund(api)
    assert view["summary"]["status"] == "funded"
    assert view["chain"]["on_chain"] and view["chain"]["status"] == "Funded"
    assert view["record"]["split"]["total"] == DEPOSIT
    assert world.chain.token_balance(world.address(REQUESTER)) == BUDGET - DEPOSIT

    view = deliver(api, "acceptable")
    assert view["summary"]["status"] == "challenge_period", view["chain"]["conflicts"]
    assert view["summary"]["automated_verdict"] == "pass"
    assert events(view) == ["Funded", "Reserved", "Delivered", "VerificationRecorded"]
    # The result is an EAS attestation by the verifier key, readable without Orbit Watch.
    on = world.chain.request(RID)
    attestation = world.chain.attestation(on["resultAttestation"])
    assert attestation["attester"] == world.address(VERIFIER)
    assert attestation["recipient"] == world.address(STATION)
    assert attestation["fields"]["verdict"] == "pass"
    assert attestation["fields"]["reportSha256"].hex() == view["record"]["report_sha256"]

    world.travel("2026-11-03T05:00:00Z")  # the challenge period has ended
    tick = api.tick()
    assert len(tick["sent"]) == 1  # the service settled it, with its verifier key
    view = api.view()
    assert view["summary"]["status"] == "settled" and view["summary"]["outcome"] == "accepted"
    assert view["chain"]["status"] == "Settled"
    assert view["summary"]["settlement"]["reference"] == tick["sent"][0]

    # Payouts are credited on chain and move as token transfers when withdrawn.
    assert withdraw(api, STATION) == 100_000_000
    assert withdraw(api, REQUESTER) == 30_000_000  # the unused challenge-round reserve
    assert api.balance(PLATFORM)["withdrawable"] == 5_000_000
    assert world.chain.token_balance(world.chain.escrow.address) == 5_000_000  # the fee, owed

    # Every transaction is shown with its status; a local chain has no explorer.
    listed = api.get("/v1/transactions", STATION).json()
    assert listed["notice"] == "local Anvil test chain, no real value"
    assert [t["action"] for t in listed["transactions"]] == ["reserve", "deliver", "withdraw"]
    assert all(t["status"] == "confirmed" and t["block"] for t in listed["transactions"])
    assert all(t["explorer"] is None for t in listed["transactions"])
    mine = api.get("/v1/transactions").json()["transactions"]  # an admin sees all
    assert {t["party"] for t in mine} == {REQUESTER, STATION, VERIFIER}
    assert {t["action"] for t in mine if t["party"] == VERIFIER} == {"attest_result", "settle"}


def test_a_challenge_takes_its_reviewers_from_the_chain(api, world):
    open_and_fund(api)
    view = deliver(api, "wrong_target")
    assert view["summary"]["automated_verdict"] == "fail"

    # Only the requester or the observer can challenge; the reason stays off chain.
    refused = api.post(f"/v1/requests/{RID}/challenge", api.key(STRANGER), {"reason": "not mine"})
    assert refused.status_code == 403 and refused.json()["error"]["code"] == "not_a_party"
    reason = "I am sure this was SIM-CUBESAT-A"
    view = api.act(STATION, f"/v1/requests/{RID}/challenge", {"reason": reason})
    assert view["summary"]["status"] == "in_review"
    assert view["record"]["challenge_reason"] == reason
    chosen = world.chain.request(RID)["reviewers"]
    assert view["record"]["reviewers"] == [world.link.party_of(a) for a in chosen]
    assert set(view["record"]["reviewers"]) <= set(REVIEWERS)

    voters = view["record"]["reviewers"][:2]
    for reviewer in voters:
        tasks = api.get("/v1/tasks", reviewer).json()["tasks"]
        assert len(tasks) == 2  # the real task and one calibration task
        for task in tasks:
            result = api.act(
                reviewer,
                f"/v1/tasks/{task['task_id']}/review",
                {"approve": False, "reason": "The track belongs to the neighbouring object"},
            )
            assert result is not None
    view = api.view()
    assert view["summary"]["status"] == "settled" and view["summary"]["outcome"] == "rejected"
    assert dict(view["record"]["vote_reasons"])[voters[0]].startswith("The track")
    assert events(view)[-3:] == ["Voted", "Voted", "Settled"]
    for reviewer in voters:
        assert api.balance(reviewer)["withdrawable"] == 10_000_000
    assert api.balance(STATION)["withdrawable"] == 0
    assert api.balance(REQUESTER)["withdrawable"] == DEPOSIT - 20_000_000
    assert api.balance(PLATFORM)["withdrawable"] == 0
    # The votes are EAS attestations by the reviewers' own addresses.
    for event in world.chain.events(0, world.chain.latest_block()):
        if event.name == "Voted":
            fields = world.chain.attestation(event.args["attestation"])
            assert fields["attester"] == event.args["reviewer"]
            assert fields["fields"]["reasonSha256"] == sha256_of_text(
                "The track belongs to the neighbouring object"
            )


def test_an_inconclusive_result_without_a_majority_is_a_dispute(api, world):
    start, end = "2026-11-11T15:00:00Z", "2026-11-12T03:00:00Z"
    request = request_bytes(start=start, end=end)
    world.travel("2026-11-11T12:00:00Z")
    observed = simulate(
        catalog(),
        339001,
        load_profile("sim-cmos-gps"),
        parse_utc(start),
        parse_utc(end),
        seed=7,
        max_passes=2,
    )
    open_and_fund(api, request=request)
    api.act(STATION, f"/v1/requests/{RID}/reserve")
    world.travel("2026-11-12T04:00:00Z")
    view = api.act(
        STATION,
        f"/v1/requests/{RID}/deliveries",
        content=owjson.write_observation_set(observed).encode(),
    )
    assert view["summary"]["automated_verdict"] == "inconclusive"
    assert view["summary"]["status"] == "in_review" and view["record"]["challenger"] is None
    reviewer = view["record"]["reviewers"][0]
    task = next(
        t
        for t in api.get("/v1/tasks", reviewer).json()["tasks"]
        if t["challenge_reason"] == "The automated result was inconclusive."
    )
    api.act(reviewer, f"/v1/tasks/{task['task_id']}/review", {"approve": True, "reason": "ok"})

    world.travel("2026-11-14T05:00:00Z")  # the 48-hour review deadline has passed
    api.tick()
    view = api.view()
    assert view["summary"]["outcome"] == "disputed" and view["summary"]["status"] == "settled"
    assert api.balance(reviewer)["withdrawable"] == 10_000_000
    assert api.balance(STATION)["withdrawable"] == 0
    assert api.balance(REQUESTER)["withdrawable"] == DEPOSIT - 10_000_000


def test_cancelling_and_expiring_refund_the_deposit(api, world):
    open_and_fund(api)
    view = api.act(REQUESTER, f"/v1/requests/{RID}/cancel")
    assert view["summary"]["outcome"] == "cancelled" and view["summary"]["status"] == "settled"
    assert events(view)[-2:] == ["Cancelled", "Settled"]

    other = request_bytes(request_id="SIM-REQ-0002")
    open_and_fund(api, request=other, request_id="SIM-REQ-0002")
    world.travel("2026-11-03T03:00:00Z")  # the delivery deadline
    assert api.tick()["sent"]
    view = api.view("SIM-REQ-0002")
    assert view["summary"]["outcome"] == "expired" and view["summary"]["status"] == "settled"
    assert withdraw(api, REQUESTER) == 2 * DEPOSIT
    assert world.chain.token_balance(world.address(REQUESTER)) == BUDGET


# --------------------------------------------------------------------------- refusals


def test_unauthorised_parties_cannot_approve_work_or_take_money(api, world):
    open_and_fund(api)
    deliver(api, "wrong_target")
    api.act(STATION, f"/v1/requests/{RID}/challenge", {"reason": "it was the right object"})
    reviewers = api.view()["record"]["reviewers"]
    outsider = next(r for r in REVIEWERS if r not in reviewers)

    # Roles: a station key cannot fund.
    refused = api.post(f"/v1/requests/{RID}/fund", api.key(STATION), SPLIT)
    assert refused.status_code == 403 and refused.json()["error"]["code"] == "forbidden_role"
    # A registered reviewer outside the round, and a stranger, voting straight on chain:
    # the escrow refuses both, so no attestation is ever created.
    on = world.chain.request(RID)
    for party in (outsider, STRANGER):
        call = world.chain.vote_call(
            RID,
            delivery_sha256=on["deliverySha256"],
            approve=True,
            reason_sha256=sha256_of_text("let me in"),
            observer=on["station"],
            result_attestation=on["resultAttestation"],
        )
        with pytest.raises(ChainError) as error:
            world.wallet(party).send(world.chain.unsigned(world.address(party), call))
        assert error.value.code in ("not_assigned", "not_a_reviewer")
    # The same vote forced onto the chain fails there, and shows as failed.
    account = world.account(STRANGER)
    api.register(STRANGER)
    transaction = world.chain.unsigned(account.address, call) | {
        "gas": 500_000,
        "nonce": world.w3.eth.get_transaction_count(account.address),
        "maxFeePerGas": 10**10,
        "maxPriorityFeePerGas": 10**9,
    }
    signed = account.sign_transaction(transaction)
    tx_hash = world.w3.eth.send_raw_transaction(signed.raw_transaction).to_0x_hex()
    shown = api.report(STRANGER, tx_hash)["transaction"]
    assert shown["status"] == "failed" and shown["error"] == "not_a_reviewer"
    assert shown["action"] == "attest_vote" and shown["request_id"] == RID
    assert api.view()["record"]["votes"] == []
    # Nobody can report a transaction that is not theirs.
    assert api.report(REQUESTER, tx_hash, expect=403)["error"]["code"] == "not_your_transaction"

    # Nobody can take money they are not owed, through the API or straight on chain.
    refused = api.post("/v1/wallet/withdraw", api.key(STRANGER))
    assert refused.status_code == 409 and refused.json()["error"]["code"] == "nothing_to_withdraw"
    with pytest.raises(ChainError) as error:
        world.wallet(STRANGER).send(
            world.chain.unsigned(world.address(STRANGER), world.chain.withdraw_call())
        )
    assert error.value.code == "nothing_to_withdraw"
    # The escrow has no function that hands a deposit to anyone but by the rules.
    assert world.chain.deposit(RID) == DEPOSIT


def test_a_party_without_a_wallet_or_with_someone_elses_is_refused(api, world):
    key = api.key(REQUESTER)
    assert api.post("/v1/requests", key, {"request": json.loads(REQUEST)}).status_code == 201
    api.act(REQUESTER, f"/v1/requests/{RID}/open")
    refused = api.post(f"/v1/requests/{RID}/fund", key, SPLIT)
    assert refused.status_code == 409 and refused.json()["error"]["code"] == "no_wallet"

    message = api.get("/v1/wallet", REQUESTER).json()["message"]
    assert REQUESTER in message and str(world.chain.chain_id) in message
    # A signature by another key, or of another message, proves nothing.
    for signer, text in ((STATION, message), (REQUESTER, message + " ")):
        bad = api.post(
            "/v1/wallet",
            key,
            {
                "address": world.address(REQUESTER),
                "signature": world.wallet(signer).sign_message(text),
            },
        )
        assert bad.status_code == 422 and bad.json()["error"]["code"] == "bad_signature"
    api.register(REQUESTER)
    assert api.register(REQUESTER)["address"] == world.address(REQUESTER)  # idempotent
    # One wallet per party, and one party per address.
    other = Wallet(world.w3, test_account("another wallet"))
    changed = api.post(
        "/v1/wallet", key, {"address": other.address, "signature": other.sign_message(message)}
    )
    assert changed.status_code == 409
    assert changed.json()["error"]["code"] == "wallet_already_set"
    taken = api.post(
        "/v1/wallet",
        api.key(STATION),
        {
            "address": world.address(REQUESTER),
            "signature": world.wallet(REQUESTER).sign_message(
                api.get("/v1/wallet", STATION).json()["message"]
            ),
        },
    )
    assert taken.status_code == 409 and taken.json()["error"]["code"] == "address_taken"
    # Points are not used on chain.
    grant = api.post("/v1/admin/grants", api.admin, {"party": REQUESTER, "points": 5})
    assert grant.status_code == 409 and grant.json()["error"]["code"] == "points_not_used"


def test_someone_else_funding_the_same_request_id_is_shown_not_applied(api, world):
    for party in (REQUESTER, STRANGER):
        api.register(party)
    key = api.key(REQUESTER)
    assert api.post("/v1/requests", key, {"request": json.loads(REQUEST)}).status_code == 201
    api.act(REQUESTER, f"/v1/requests/{RID}/open")
    # A stranger funds the request's ID first, with terms of their own.
    stranger = world.account(STRANGER)
    world.local.send(
        world.deployment.deployer, world.deployment.usd.functions.mint(stranger.address, 10)
    )
    world.local.send(
        stranger, world.deployment.usd.functions.approve(world.chain.escrow.address, 10)
    )
    terms = world.link.chain_terms(world.service.records[RID]) | {"termsHash": b"\x01" * 32}
    world.local.send(
        stranger,
        world.chain.escrow.functions.fund(
            request_key(RID),
            terms,
            {"observerReward": 10, "reviewerReward": 0, "platformFee": 0},
        ),
    )
    refused = api.post(f"/v1/requests/{RID}/fund", key, SPLIT)
    assert refused.status_code == 409 and refused.json()["error"]["code"] == "already_on_chain"
    view = api.view()
    assert view["summary"]["status"] == "open" and not view["chain"]["on_chain"]
    assert [c["code"] for c in view["chain"]["conflicts"]] == ["foreign_funding"]
    # Its other events are never applied to the request.
    world.local.send(world.account(STATION), world.chain.escrow.functions.reserve(request_key(RID)))
    assert api.view()["summary"]["status"] == "open"


# --------------------------------------------------------------------------- retries


def test_a_retry_never_pays_twice(api, world):
    open_and_fund(api)
    deliver(api, "acceptable")
    world.travel("2026-11-03T05:00:00Z")
    first = api.tick()
    assert len(first["sent"]) == 1
    assert api.tick()["sent"] == []  # settled once; a second tick sends nothing

    # Reporting a transaction again changes nothing.
    tx = api.get("/v1/transactions", STATION).json()["transactions"][-1]["tx_hash"]
    before = api.view()
    assert api.report(STATION, tx)["transaction"]["status"] == "confirmed"
    assert api.view()["record"] == before["record"]
    # Settling again on chain, by anyone, is refused.
    with pytest.raises(ChainError) as error:
        world.wallet(STRANGER).send(
            world.chain.unsigned(world.address(STRANGER), world.chain.settle_call(RID))
        )
    assert error.value.code == "already_settled"
    # A replayed API call returns its first answer and prepares nothing new.
    reply = api.post("/v1/wallet/withdraw", api.key(STATION), idem="withdraw-once")
    assert reply.status_code == 202, reply.text
    tx_hash = world.wallet(STATION).send(reply.json()["sign"][0]["transaction"])
    api.report(STATION, tx_hash)
    replay = api.post("/v1/wallet/withdraw", api.key(STATION), idem="withdraw-once")
    assert replay.headers["Idempotent-Replayed"] == "true"
    with pytest.raises(ChainError) as error:  # its transaction cannot pay twice either
        world.wallet(STATION).send(replay.json()["sign"][0]["transaction"])
    assert error.value.code == "nothing_to_withdraw"
    assert world.chain.token_balance(world.address(STATION)) == 100_000_000


# --------------------------------------------------------------------------- restarts


def test_the_service_keeps_following_the_chain_after_a_restart(api, world, tmp_path):
    open_and_fund(api)
    api.act(STATION, f"/v1/requests/{RID}/reserve")
    world.service.storage.close()
    # While the service is down, the station delivers on chain with its own wallet.
    world.travel("2026-11-02T04:00:00Z")
    data = (DATASETS / "acceptable" / "observations.json").read_bytes()
    from orbit_watch.canonical import sha256_bytes

    world.wallet(STATION).send(
        world.chain.unsigned(
            world.address(STATION),
            world.chain.deliver_call(RID, bytes.fromhex(sha256_bytes(data))),
        )
    )
    world.service = world.open()
    restarted = Api(world)
    restarted.keys = api.keys
    view = restarted.view()
    assert view["summary"]["status"] == "delivered"  # the chain decided while it was down
    # The station uploads the file it delivered; verification runs at once.
    view = restarted.act(
        STATION,
        f"/v1/requests/{RID}/deliveries",
        content=data,
        headers={"Content-Type": "application/octet-stream"},
    )
    assert view["summary"]["status"] == "challenge_period", view["chain"]["conflicts"]
    world.service.storage.close()
    other = world.local.deploy(
        world.deployment.deployer,
        "OrbitWatchEscrow.sol",
        "OrbitWatchEscrow",
        world.deployment.usd.address,
        world.address(PLATFORM),
        world.chain.eas.address,
        world.deployment.registry.address,
        world.address(VERIFIER),
    )
    with pytest.raises(ChainError) as error:
        world.open(escrow=other.address)
    assert error.value.code == "other_chain"
    world.service = world.open()


# --------------------------------------------------------------------------- wallets and set-up


def test_the_users_wallet_checks_before_it_signs(api, world, tmp_path, monkeypatch):
    from eth_account import Account

    from orbit_watch.chain import wallet as wallet_module

    unsigned = world.chain.unsigned(world.address(STATION), world.chain.reserve_call(RID))
    for changed, code in (({"chainId": 84532}, "wrong_chain"), ({}, "wrong_wallet")):
        with pytest.raises(ChainError) as error:
            world.wallet(REQUESTER).send(unsigned | changed)
        assert error.value.code == code
    # A party without testnet ETH for gas is told so, before anything is sent.
    broke = Wallet(world.w3, test_account("no gas money"), timeout=5)
    with pytest.raises(ChainError) as error:
        broke.send(world.chain.unsigned(broke.address, world.chain.approve_call(1)))
    assert error.value.code == "rpc_error"
    # Keystores open with their password only, which comes from a file or the environment.
    keystore = tmp_path / "keystore"
    keystore.write_text(
        json.dumps(Account.encrypt(world.account(STATION).key, "pw", kdf="pbkdf2", iterations=10))
    )
    password = tmp_path / "password"
    password.write_text("pw\n")
    assert wallet_module.read_password(str(password)) == "pw"
    monkeypatch.setenv("ORBIT_WATCH_PASSWORD_FILE", str(password))
    assert wallet_module.read_password(None) == "pw"
    opened = wallet_module.load_keystore(keystore, "pw")
    assert opened.address == world.address(STATION)
    with pytest.raises(ChainError) as error:
        wallet_module.load_keystore(keystore, "wrong")
    assert error.value.code == "bad_keystore"
    # Funding needs the deposit in the wallet: the faucet comes first.
    api.register(STATION)
    poor = api.post("/v1/requests", api.key(REQUESTER), {"request": json.loads(REQUEST)})
    assert poor.status_code == 201
    api.register(REQUESTER)
    api.act(REQUESTER, f"/v1/requests/{RID}/open")
    too_much = dict(SPLIT, observer=BUDGET)
    refused = api.post(f"/v1/requests/{RID}/fund", api.key(REQUESTER), too_much)
    assert refused.status_code == 409
    assert refused.json()["error"]["code"] == "insufficient_balance"


def test_a_reason_given_only_on_chain_is_shown_by_its_hash(api, world):
    open_and_fund(api)
    deliver(api, "wrong_target")
    digest = sha256_of_text("a reason Orbit Watch never saw")
    world.wallet(REQUESTER).send(
        world.chain.unsigned(world.address(REQUESTER), world.chain.challenge_call(RID, digest))
    )
    record = api.view()["record"]
    assert record["status"] == "in_review" and record["challenger"] == REQUESTER
    assert record["challenge_reason"] == (
        f"(reason not given to Orbit Watch; SHA-256 {digest.hex()})"
    )


def test_the_server_starts_on_a_chain_only_with_the_escrows_verifier(world, tmp_path, capsys):
    import argparse

    from eth_account import Account

    from orbit_watch.cli import _chain_link, main

    rpc = world.w3.provider.endpoint_uri
    # The chain options come together.
    assert main(["serve", "--dir", str(tmp_path / "x"), "--chain-rpc", rpc]) == 2
    assert "together" in capsys.readouterr().err
    password = tmp_path / "password"
    password.write_text("pw\n")

    def link_with(party):
        keystore = tmp_path / party.replace(":", "_")
        keystore.write_text(
            json.dumps(Account.encrypt(world.account(party).key, "pw", kdf="pbkdf2", iterations=10))
        )
        keystore.chmod(0o644)
        args = argparse.Namespace(
            chain_rpc=rpc,
            escrow=world.chain.escrow.address,
            verifier_keystore=str(keystore),
            verifier_password_file=str(password),
            from_block=0,
        )
        return _chain_link(args)

    link = link_with(VERIFIER)
    assert link.verifier.address == world.address(VERIFIER)
    assert "can be read by other users" in capsys.readouterr().err
    with pytest.raises(ChainError) as error:
        link_with(STATION)
    assert error.value.code == "not_the_verifier"
    # A service directory started without a chain cannot move onto one.
    from helpers import catalog_bytes, policy_bytes

    from orbit_watch.service import VerificationContext, open_service

    context = VerificationContext(catalog=catalog_bytes(), policy=policy_bytes())
    plain = open_service(tmp_path / "plain", world.service.reviewers, context)
    plain.create(REQUEST, REQUESTER, parse_utc("2026-11-01T12:00:00Z"))
    plain.storage.close()
    with pytest.raises(ChainError) as error:
        open_service(tmp_path / "plain", world.service.reviewers, context, chain=link)
    assert error.value.code == "not_a_chain_service"


def test_a_refused_log_range_is_halved_and_retried(api, world, monkeypatch):
    """Endpoints limit eth_getLogs ranges (Base's public one to 200 blocks)."""
    import requests

    from orbit_watch.chain.client import MIN_LOG_CHUNK, _smaller_range

    real = world.chain._query_logs
    spans = []

    def limited(start, end):
        spans.append(end - start + 1)
        if end - start + 1 > 100:
            error = requests.HTTPError("413 Client Error: Payload Too Large")
            error.response = requests.Response()
            error.response.status_code = 413
            raise error
        return real(start, end)

    monkeypatch.setattr(world.chain, "_query_logs", limited)
    world.local.rpc("anvil_mine", [hex(450)])
    open_and_fund(api)
    assert world.chain.log_chunk <= 100 and max(spans) > 100
    assert api.view()["record"]["status"] == "funded"
    assert _smaller_range(ValueError("query exceeds max block range 1000"), 2000) == 1000
    assert _smaller_range(ValueError("connection refused"), 2000) is None
    assert _smaller_range(ValueError("block range too large"), MIN_LOG_CHUNK) is None
    # Base's public endpoint names its limit in the body of a 413 answer: take it at once.
    base = requests.HTTPError("413 Client Error: Payload Too Large for url")
    base.response = requests.Response()
    base.response.status_code = 413
    base.response._content = (
        b'{"jsonrpc":"2.0","id":0,"error":{"code":-32614,'
        b'"message":"eth_getLogs is limited to a 200 range"}}'
    )
    assert _smaller_range(base, 2000) == 200
    assert _smaller_range(base, 200) == 100  # refused although within the named limit


def test_a_new_directory_follows_the_chain_from_the_current_block(world, tmp_path):
    """A new service directory has no requests yet, so no earlier event is its own; it does
    not read the escrow's whole history (on Base Sepolia, 200 blocks per call)."""
    from helpers import catalog_bytes, policy_bytes

    from orbit_watch.chain.client import OrbitWatchChain
    from orbit_watch.chain.link import ChainLink
    from orbit_watch.service import VerificationContext, open_service

    context = VerificationContext(catalog=catalog_bytes(), policy=policy_bytes())
    world.local.rpc("anvil_mine", [hex(50)])

    def opened(name, **options):
        chain = OrbitWatchChain(world.w3, world.chain.escrow.address)
        link = ChainLink(chain, world.account(VERIFIER), **options)
        return open_service(tmp_path / name, world.service.reviewers, context, chain=link)

    latest = world.chain.latest_block()
    fresh = opened("fresh")
    assert fresh.chain.synced_block() == latest
    fresh.storage.close()
    given = opened("given", from_block=7)
    assert given.chain.synced_block() == 6
    given.storage.close()
    world.local.rpc("anvil_mine", [hex(5)])
    again = opened("fresh")  # a known directory goes on from where it stopped
    assert again.chain.synced_block() == latest
    again.chain.sync()
    assert again.chain.synced_block() == world.chain.latest_block() > latest
    again.storage.close()

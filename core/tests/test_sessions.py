"""Signing in with a wallet (phase 3, step 3.2; decisions P3-04, P3-05, D-27).

Against a request service on a local Anvil chain, because wallets belong to the chain.
Everything is LOCAL and SIMULATED; the accounts are public test accounts.
"""

import json
import subprocess
import sys
from datetime import UTC, datetime, timedelta

import pytest
from anvil import require_local_chain, test_account
from chain_world import REQUESTER, STATION, ChainWorld
from starlette.testclient import TestClient

from orbit_watch.api import create_app
from orbit_watch.api import sessions as sess
from orbit_watch.chain import wallet_message

ORIGIN = "http://127.0.0.1:8787"
OTHER = "http://localhost:8787"
EVIL = "https://evil.example"
NOW = datetime(2026, 11, 13, 9, 0, tzinfo=UTC)


class WallClock:
    def __init__(self):
        self.now = NOW

    def __call__(self):
        return self.now


@pytest.fixture
def world(tmp_path):
    require_local_chain()
    made = ChainWorld(tmp_path / "service")
    yield made
    made.stop()


@pytest.fixture
def clock():
    return WallClock()


def client(world, clock):
    app = create_app(world.service, origins=[ORIGIN, OTHER], wall_clock=clock)
    return TestClient(app, base_url=ORIGIN)


def register(world, party):
    """A party registers its wallet the command line's way (step 2.6)."""
    from eth_account import Account
    from eth_account.messages import encode_defunct

    account = world.account(party)
    message = wallet_message(party, world.chain.chain_id, world.chain.escrow.address)
    signature = Account.sign_message(encode_defunct(text=message), account.key).signature
    with world.service.storage.db.transaction():
        world.link.register_wallet(party, account.address, "0x" + signature.hex(), world.link.now())
    return account


def sign(account, message):
    from eth_account import Account
    from eth_account.messages import encode_defunct

    return "0x" + Account.sign_message(encode_defunct(text=message), account.key).signature.hex()


def challenge(http, address, origin=ORIGIN, **extra):
    return http.post(
        "/v1/session/challenge", json={"address": address, **extra}, headers={"Origin": origin}
    )


def sign_in(http, account, origin=ORIGIN, **extra):
    asked = challenge(http, account.address, origin, **extra)
    assert asked.status_code == 200, asked.text
    message = asked.json()["message"]
    return message, http.post(
        "/v1/session",
        json={"message": message, "signature": sign(account, message)},
        headers={"Origin": origin},
    )


def test_the_message_is_erc_4361_for_this_origin(world, clock):
    http = client(world, clock)
    account = register(world, STATION)
    asked = challenge(http, account.address.lower())
    assert asked.status_code == 200, asked.text
    message = asked.json()["message"]
    lines = message.split("\n")
    assert lines[0] == f"{ORIGIN} wants you to sign in with your Ethereum account:"
    assert lines[1] == account.address  # EIP-55 checksummed
    assert lines[2] == "" and lines[4] == ""
    assert lines[3].startswith(f"Sign in to Orbit Watch as {STATION}. Testnet only")
    fields = dict(line.split(": ", 1) for line in lines[5:])
    assert fields["URI"] == ORIGIN + "/"
    assert fields["Version"] == "1"
    assert fields["Chain ID"] == "31337"
    assert len(fields["Nonce"]) >= 8 and fields["Nonce"].isalnum()
    assert fields["Issued At"] == "2026-11-13T09:00:00.000Z"
    assert fields["Expiration Time"] == "2026-11-13T09:05:00.000Z"
    assert asked.json()["party"] == STATION and asked.json()["sign_up"] is False


def test_signing_in_sets_a_cookie_scripts_cannot_read(world, clock):
    http = client(world, clock)
    account = register(world, STATION)
    _, signed = sign_in(http, account)
    assert signed.status_code == 200, signed.text
    assert signed.json()["session"] == {
        "party": STATION,
        "role": "station",
        "address": account.address,
        "expires_at": "2026-11-13T21:00:00.000Z",
    }
    cookie = signed.headers["set-cookie"]
    assert cookie.startswith(f"{sess.COOKIE}=")
    for part in ("HttpOnly", "SameSite=strict", "Path=/", "Max-Age=43200"):
        assert part in cookie
    assert "Secure" not in cookie  # plain http on 127.0.0.1; https origins get Secure
    token = cookie.split(";")[0].split("=", 1)[1]
    assert token not in signed.text  # never in the body
    rows = world.service.storage.db.query("SELECT token_hash FROM sessions")
    assert [r["token_hash"] for r in rows] == [sess.token_hash(token)]  # only the hash is kept

    assert http.get("/v1/session").json()["session"]["party"] == STATION
    # The session works for the rest of the API, like the party's own key.
    assert http.get("/v1/wallet").json()["address"] == account.address


def test_a_sign_in_message_works_once_for_its_own_origin_and_address(world, clock):
    http = client(world, clock)
    station = register(world, STATION)
    requester = register(world, REQUESTER)

    message, signed = sign_in(http, station)
    assert signed.status_code == 200
    again = http.post(
        "/v1/session",
        json={"message": message, "signature": sign(station, message)},
        headers={"Origin": ORIGIN},
    )
    assert again.json()["error"]["code"] == "message_used"

    # Another page of ours cannot use it, and a foreign page gets no message at all.
    message = challenge(http, station.address).json()["message"]
    elsewhere = http.post(
        "/v1/session",
        json={"message": message, "signature": sign(station, message)},
        headers={"Origin": OTHER},
    )
    assert elsewhere.status_code == 403 and elsewhere.json()["error"]["code"] == "wrong_origin"
    foreign = challenge(http, station.address, origin=EVIL)
    assert foreign.status_code == 403 and foreign.json()["error"]["code"] == "forbidden_origin"
    assert http.post("/v1/session/challenge", json={"address": station.address}).status_code == 403

    # A message changed to name another site is not one the service wrote.
    changed = message.replace(ORIGIN, EVIL)
    refused = http.post(
        "/v1/session",
        json={"message": changed, "signature": sign(station, changed)},
        headers={"Origin": ORIGIN},
    )
    assert refused.json()["error"]["code"] == "unknown_message"

    # Signed by someone else: refused, and the message stays unused for its owner.
    wrong = http.post(
        "/v1/session",
        json={"message": message, "signature": sign(requester, message)},
        headers={"Origin": ORIGIN},
    )
    assert wrong.json()["error"]["code"] == "bad_signature"
    right = http.post(
        "/v1/session",
        json={"message": message, "signature": sign(station, message)},
        headers={"Origin": ORIGIN},
    )
    assert right.status_code == 200


def test_messages_and_sessions_expire(world, clock):
    http = client(world, clock)
    station = register(world, STATION)
    message = challenge(http, station.address).json()["message"]
    clock.now = NOW + timedelta(minutes=5)
    late = http.post(
        "/v1/session",
        json={"message": message, "signature": sign(station, message)},
        headers={"Origin": ORIGIN},
    )
    assert late.json()["error"]["code"] == "message_expired"

    _, signed = sign_in(http, station)
    assert signed.status_code == 200
    clock.now += timedelta(hours=12)
    assert http.get("/v1/session").json() == {"session": None}
    assert http.get("/v1/wallet").json()["error"]["code"] == "unauthorized"


def test_changes_with_a_session_need_its_page(world, clock):
    """Cross-site request forgery: the cookie is SameSite=Strict, and a change made with a
    session must also carry the Origin it was signed in on."""
    http = client(world, clock)
    station = register(world, STATION)
    _, signed = sign_in(http, station)
    assert signed.status_code == 200
    headers = {"Idempotency-Key": "w1"}
    missing = http.post("/v1/wallet/withdraw", headers=headers)
    assert missing.json()["error"]["code"] == "forbidden_origin"
    other = http.post("/v1/wallet/withdraw", headers={**headers, "Origin": OTHER})
    assert other.json()["error"]["code"] == "wrong_origin"
    own = http.post("/v1/wallet/withdraw", headers={**headers, "Origin": ORIGIN})
    assert own.json()["error"]["code"] == "nothing_to_withdraw"  # past authentication


def test_unknown_wallets_sign_up_as_requesters_or_stations(world, clock):
    from eth_account import Account
    from eth_account.messages import encode_defunct

    http = client(world, clock)
    newcomer = test_account("a new station's wallet")
    unknown = challenge(http, newcomer.address)
    assert unknown.status_code == 404 and unknown.json()["error"]["code"] == "unknown_wallet"

    for party in ("reviewer:sim-zed", "admin:me", "station:x", "station:bad name", "nobody"):
        refused = challenge(http, newcomer.address, sign_up={"party": party})
        assert refused.json()["error"]["code"] == "invalid_party", party
    register(world, STATION)
    taken = challenge(http, newcomer.address, sign_up={"party": STATION})
    assert taken.json()["error"]["code"] == "party_taken"

    message, signed = sign_in(http, newcomer, sign_up={"party": "station:SIM-NEW"})
    assert "Sign up to Orbit Watch as station:SIM-NEW." in message
    assert signed.status_code == 200, signed.text
    assert signed.json()["session"]["party"] == "station:SIM-NEW"
    assert world.link.wallet("station:SIM-NEW") == newcomer.address
    # The registration stays verifiable: the stored message and signature.
    row = world.service.storage.db.query(
        "SELECT signature, signed_message FROM wallets WHERE party = 'station:SIM-NEW'"
    )[0]
    assert row["signed_message"] == message
    signer = Account.recover_message(encode_defunct(text=message), signature=row["signature"])
    assert signer == newcomer.address

    # The wallet now signs in, and cannot sign up again.
    again = challenge(http, newcomer.address, sign_up={"party": "requester:sim-other"})
    assert again.json()["error"]["code"] == "address_taken"
    assert challenge(http, newcomer.address).json()["party"] == "station:SIM-NEW"


def test_signing_out_ends_the_session(world, clock):
    http = client(world, clock)
    station = register(world, STATION)
    _, signed = sign_in(http, station)
    token = signed.headers["set-cookie"].split(";")[0].split("=", 1)[1]
    assert http.delete("/v1/session").json()["error"]["code"] == "forbidden_origin"
    out = http.delete("/v1/session", headers={"Origin": ORIGIN})
    assert out.status_code == 200 and out.json() == {"signed_out": True}
    assert "Max-Age=0" in out.headers["set-cookie"] or "expires=" in out.headers["set-cookie"]
    assert http.get("/v1/session").json() == {"session": None}
    # The old cookie is dead even if a browser kept it.
    stale = TestClient(
        create_app(world.service, origins=[ORIGIN], wall_clock=clock), base_url=ORIGIN
    )
    stale.cookies.set(sess.COOKIE, token)
    assert stale.get("/v1/session").json() == {"session": None}


def test_sign_in_needs_a_chain(tmp_path):
    from helpers import catalog_bytes, packaged, policy_bytes

    from orbit_watch.reviewers import ReviewerRegistry
    from orbit_watch.service import VerificationContext, open_service

    context = VerificationContext(catalog=catalog_bytes(), policy=policy_bytes())
    service = open_service(
        tmp_path / "ledger", ReviewerRegistry.parse(packaged("reviewers.json")), context
    )
    http = TestClient(create_app(service, origins=[ORIGIN]), base_url=ORIGIN)
    asked = challenge(http, "0x" + "11" * 20)
    assert asked.json()["error"]["code"] == "not_on_chain"
    service.storage.close()


def test_the_api_starts_without_the_evm_extra():
    """The ledger service needs no wallet libraries: they load only to sign in."""
    code = (
        "import sys\n"
        "for m in ('eth_account', 'eth_utils', 'web3', 'eth_abi'): sys.modules[m] = None\n"
        "import orbit_watch.api, orbit_watch.cli\n"
        "print('ok')\n"
    )
    done = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True)
    assert done.stdout.strip() == "ok", done.stderr


def test_serve_takes_the_web_origins(tmp_path, capsys, monkeypatch):
    import uvicorn

    from orbit_watch.cli import EXIT_USAGE, _default_origins, main

    assert _default_origins("127.0.0.1", 8787) == [
        "http://127.0.0.1:8787",
        "http://localhost:8787",
    ]
    assert _default_origins("0.0.0.0", 80) == ["http://0.0.0.0:80"]
    bad = main(["serve", "--dir", str(tmp_path / "x"), "--origin", "orbit.example/app"])
    assert bad == EXIT_USAGE and "web origin" in capsys.readouterr().err
    seen = {}
    monkeypatch.setattr(uvicorn, "run", lambda app, host, port: seen.update(app=app))
    assert main(["serve", "--dir", str(tmp_path / "y"), "--origin", "https://orbit.example"]) == 0
    assert json.loads(TestClient(seen["app"]).get("/v1/health").text)["status"] == "ok"

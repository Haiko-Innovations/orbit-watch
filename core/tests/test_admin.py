"""The administrator view and the public pages' API (phase 3, step 3.7).

The governance tests run on a local Anvil chain where, as on Base Sepolia, a timelock owns
the reviewer registry and a 2-of-3 Safe proposes to it; the Safe's signers, like every
party, are LOCAL TEST accounts. Everything is SIMULATED and has no value.
"""

import json
from pathlib import Path

import pytest
from anvil import LOCAL_TIMELOCK_DELAY, require_local_chain
from chain_world import REQUESTER, REVIEWERS, STATION, STRANGER, ChainWorld
from eth_utils import keccak
from helpers import catalog_bytes, packaged, policy_bytes
from starlette.testclient import TestClient
from test_chain_service import Api, deliver, open_and_fund

from orbit_watch.api import create_app, keys
from orbit_watch.canonical import sha256_bytes
from orbit_watch.chain import request_key
from orbit_watch.chain.governance import _serialize, batch_checksum, batch_file, safe_app_links
from orbit_watch.reviewers import ReviewerRegistry
from orbit_watch.service import VerificationContext, open_service
from orbit_watch.timeutil import format_utc, parse_utc

ROOT = Path(__file__).resolve().parents[2]
ACCEPTABLE = (ROOT / "examples/simulated/datasets/acceptable/observations.json").read_bytes()
NEWCOMER = "reviewer:sim-newcomer"
ADMIN_GETS = ["/v1/admin/overview", "/v1/admin/governance", "/v1/admin/demo-datasets"]
ADMIN_POSTS = [
    ("/v1/admin/governance/proposals", {"action": "add", "reviewer": "0x" + "11" * 20}),
    ("/v1/admin/demo-datasets/acceptable", {}),
    ("/v1/admin/simulate", {"profile": "sim-cmos-gps", "norad_id": 339001}),
]

# safe-react-apps apps/tx-builder/src/lib/checksum.test.js: its batch and the checksum the
# Transaction Builder computes for it (with its empty "checksum" field included).
BUILDER_FIXTURE = {
    "version": "1.0",
    "chainId": "4",
    "createdAt": 1646321521061,
    "meta": {
        "name": "test batch file",
        "txBuilderVersion": "1.4.0",
        "checksum": "",
        "createdFromSafeAddress": "0xDF8a1Ce35c9a6ACE153B4e0767942f1E2291a1Aa",
        "createdFromOwnerAddress": "0x49d4450977E2c95362C13D3a31a09311E0Ea26A6",
    },
    "transactions": [
        {
            "to": "0x49d4450977E2c95362C13D3a31a09311E0Ea26A6",
            "value": "0",
            "contractMethod": {
                "inputs": [{"internalType": "address", "name": "paramAddress", "type": "address"}],
                "name": "testAddress",
                "payable": False,
            },
            "contractInputsValues": {"paramAddress": "0x49d4450977E2c95362C13D3a31a09311E0Ea26A6"},
        },
        {
            "to": "0x49d4450977E2c95362C13D3a31a09311E0Ea26A6",
            "value": "0",
            "contractMethod": {
                "inputs": [{"internalType": "bool", "name": "paramBool", "type": "bool"}],
                "name": "testBool",
                "payable": False,
            },
            "contractInputsValues": {"paramAddress": "", "paramBool": "false"},
        },
        {
            "to": "0x49d4450977E2c95362C13D3a31a09311E0Ea26A6",
            "value": "2000000000000000000",
            "data": "0x42f4579000000000000000000000000049d4450977e2c95362c13d3a31a09311e0ea26a6",
        },
    ],
}
BUILDER_CHECKSUM = "0x4ecbfd364aa6759983915644e73f8bd411e85a2dc306f252a387c2728c4db64c"


# --------------------------------------------------------------------------- Safe files


def test_the_batch_file_checksum_is_the_transaction_builders():
    hashed = {**BUILDER_FIXTURE, "meta": {**BUILDER_FIXTURE["meta"], "name": None}}
    assert "0x" + keccak(text=_serialize(hashed)).hex() == BUILDER_CHECKSUM
    # The builder checks a loaded file without its checksum field, and not by its name.
    batch = batch_file(84532, None, "a", "b", [{"to": "0x1", "value": "0", "data": "0x"}], 1)
    renamed = {**batch, "meta": {**batch["meta"], "name": "renamed"}}
    assert batch_checksum(renamed) == batch["meta"]["checksum"]
    assert batch["chainId"] == "84532" and batch["version"] == "1.0"
    changed = {**batch, "transactions": [{"to": "0x2", "value": "0", "data": "0x"}]}
    assert batch_checksum(changed) != batch["meta"]["checksum"]


def test_safe_app_links_exist_only_for_base_sepolia():
    safe = "0xcfB913356bd7D99707CCE6CC08f628B38652E458"
    assert safe_app_links(84532, safe) == {
        "home": f"https://app.safe.global/home?safe=basesep:{safe}",
        "queue": f"https://app.safe.global/transactions/queue?safe=basesep:{safe}",
        "history": f"https://app.safe.global/transactions/history?safe=basesep:{safe}",
    }
    assert safe_app_links(31337, safe) is None
    assert safe_app_links(84532, None) is None


# --------------------------------------------------------------------------- without a chain


@pytest.fixture
def plain(tmp_path):
    """A phase 1 service (points, no chain) with an admin key and a requester key."""
    registry = ReviewerRegistry.parse(packaged("reviewers.json"))
    context = VerificationContext(catalog=catalog_bytes(), policy=policy_bytes())
    service = open_service(tmp_path / "service", registry, context)
    now = parse_utc("2026-11-01T12:00:00Z")
    with service.storage.db.transaction():
        admin = keys.create_key(service.storage.db, "admin:maintainer", "admin", now)
        requester = keys.create_key(service.storage.db, REQUESTER, "requester", now)
    http = TestClient(create_app(service, clock=lambda: now))
    yield {"service": service, "http": http, "admin": admin, "requester": requester}
    service.storage.close()


def bearer(key):
    return {"Authorization": f"Bearer {key}"}


def test_only_administrators_reach_the_administrator_api(plain):
    http = plain["http"]
    for path in ADMIN_GETS:
        assert http.get(path).status_code == 401, path
        refused = http.get(path, headers=bearer(plain["requester"]))
        assert refused.status_code == 403, path
        assert refused.json()["error"]["code"] == "forbidden_role"
    for path, body in ADMIN_POSTS:
        assert http.post(path, json=body).status_code == 401, path
        refused = http.post(path, json=body, headers=bearer(plain["requester"]))
        assert refused.status_code == 403, path


def test_the_overview_works_without_a_chain(plain):
    view = plain["http"].get("/v1/admin/overview", headers=bearer(plain["admin"])).json()
    assert view["requests"] == [] and view["counts"] == {}
    assert view["chain"] is None and view["transactions"] == []
    governance = plain["http"].get("/v1/admin/governance", headers=bearer(plain["admin"]))
    assert governance.status_code == 404
    assert governance.json()["error"]["code"] == "not_on_chain"


def test_demo_datasets_and_the_simulator_make_simulated_files_and_keep_nothing(plain):
    http, admin = plain["http"], bearer(plain["admin"])
    listed = http.get("/v1/admin/demo-datasets", headers=admin).json()
    assert [d["name"] for d in listed["datasets"]] == [
        "acceptable",
        "invalid",
        "late",
        "duplicate",
        "wrong_target",
        "too_imprecise",
    ]
    assert listed["simulated"] is True and listed["request"]["simulated"] is True
    files_before = len(plain["service"].files)

    made = http.post("/v1/admin/demo-datasets/wrong_target", headers=admin).json()
    assert made["simulated"] is True and made["expected_verdict"] == "fail"
    assert made["expected_failures"] == ["orbit_residuals"]
    assert sha256_bytes(made["observations"].encode()) == made["sha256"]
    assert "SIM-CUBESAT-B" in json.loads(made["observations"])["source"]["notes"]
    # Made afresh each time, the same way: the scenarios are seeded.
    again = http.post("/v1/admin/demo-datasets/wrong_target", headers=admin).json()
    assert again["sha256"] == made["sha256"]
    assert http.post("/v1/admin/demo-datasets/nothing", headers=admin).status_code == 404

    window = {"start": "2026-11-01T15:00:00Z", "end": "2026-11-02T03:00:00Z"}
    simulated = http.post(
        "/v1/admin/simulate",
        headers=admin,
        json={"profile": "sim-cmos-gps", "norad_id": 339001, "max_passes": 1, **window},
    )
    assert simulated.status_code == 200, simulated.text
    result = simulated.json()
    assert result["simulated"] is True and result["count"] > 0
    assert "SIMULATED" in json.loads(result["observations"])["source"]["notes"]
    for body, code in [
        ({"profile": "../../etc/passwd", "norad_id": 339001, **window}, "unknown_profile"),
        ({"profile": "sim-cmos-gps", "norad_id": 25544, **window}, "unknown_target"),
        (
            {"profile": "sim-cmos-gps", "norad_id": 339001, **window, "max_passes": 99},
            "invalid_body",
        ),
        (
            {
                "profile": "sim-cmos-gps",
                "norad_id": 339001,
                "start": window["end"],
                "end": window["start"],
            },
            "invalid_window",
        ),
    ]:
        refused = http.post("/v1/admin/simulate", headers=admin, json=body)
        assert refused.json()["error"]["code"] == code, body
    assert len(plain["service"].files) == files_before


def test_the_quality_meter_scores_a_file_without_a_key_and_keeps_nothing(plain):
    http = plain["http"]
    files_before = len(plain["service"].files)
    scored = http.post("/v1/public/quality", content=ACCEPTABLE)
    assert scored.status_code == 200, scored.text
    report = scored.json()["report"]
    assert report["report_format"] == "orbit-watch/station-quality-report"
    assert report["simulated_input"] is True and report["overall"]["observations"] > 0
    assert report["station"]["id"] == "SIM-ESPOO"
    assert "SIMULATED" in scored.json()["text"]
    assert len(plain["service"].files) == files_before

    broken = http.post("/v1/public/quality", content=b"{not json")
    assert broken.status_code == 422
    assert broken.json()["error"]["code"] == "invalid_file"
    bad_format = http.post("/v1/public/quality?format=xls", content=ACCEPTABLE)
    assert bad_format.json()["error"]["code"] == "invalid_format"
    huge = http.post("/v1/public/quality", content=b" " * (2 * 1024 * 1024 + 1))
    assert huge.status_code == 413


# --------------------------------------------------------------------------- on a chain


@pytest.fixture
def world(tmp_path):
    require_local_chain()
    made = ChainWorld(tmp_path / "service")
    yield made
    made.stop()


@pytest.fixture
def governed(tmp_path):
    require_local_chain()
    made = ChainWorld(tmp_path / "governed", governance=True, parties=(NEWCOMER,))
    yield made
    made.stop()


def test_the_overview_shows_requests_transactions_events_and_payments(world):
    api = Api(world)
    open_and_fund(api)
    deliver(api, "acceptable")
    view = api.get("/v1/admin/overview").json()
    assert view["notice"] == "local Anvil test chain, no real value"
    (only,) = view["requests"]
    assert only["request_id"] == "SIM-REQ-0001" and only["on_chain"] is True
    assert only["status"] == "challenge_period" and only["automated_verdict"] == "pass"
    assert only["observer"] == STATION and only["requester"] == REQUESTER
    assert view["counts"] == {"challenge_period": 1}
    assert [e["event"] for e in view["events"]][-1] == "Funded"  # newest first
    assert "VerificationRecorded" in [e["event"] for e in view["events"]]
    actions = {t["action"] for t in view["transactions"]}
    assert {"approve", "fund", "reserve", "deliver", "attest_result"} <= actions
    assert view["chain"]["synced_block"] >= max(e["block"] for e in view["events"])

    # After the challenge period the service settles, and the payments show.
    world.travel("2026-11-05T04:00:00Z")
    api.tick()
    view = api.get("/v1/admin/overview").json()
    (only,) = view["requests"]
    assert only["status"] == "settled" and only["outcome"] == "accepted"
    reasons = {p["reason"] for p in only["settlement"]["plan"]["payouts"]}
    assert "observer_reward" in reasons


def test_public_attestations_list_the_chains_attestations_without_a_key(world):
    api = Api(world)
    open_and_fund(api)
    deliver(api, "acceptable")
    listed = api.http.get("/v1/public/attestations")
    assert listed.status_code == 200, listed.text
    body = listed.json()
    (result,) = body["attestations"]
    on_chain = world.chain.request("SIM-REQ-0001")
    assert result["uid"] == "0x" + on_chain["resultAttestation"].hex()
    assert result["kind"] == "result" and result["by_service"] is True
    assert result["attester"] == world.chain.verifier
    assert result["fields"]["verdict"] == "pass"
    assert result["fields"]["requestId"] == "SIM-REQ-0001"
    assert result["eas_scan"] is None and result["explorer"] is None  # a local chain
    assert result["published"] is False
    assert body["result_schema"] == "0x" + world.chain.result_schema.hex()
    # Kept once read: the second listing does not ask the chain again.
    rows = world.service.storage.db.query("SELECT COUNT(*) AS n FROM chain_attestations")
    assert rows[0]["n"] == 1
    assert api.http.get("/v1/public/attestations").json() == body
    assert request_key("SIM-REQ-0001")  # the request this attestation names


def test_without_a_timelock_the_registry_cannot_be_changed_through_the_view(world):
    api = Api(world)
    view = api.get("/v1/admin/governance").json()
    assert view["registry"]["owner_kind"] == "other"
    assert view["registry"]["timelock"] is None and view["safe"] is None
    assert view["operations"] == []
    refused = api.http.post(
        "/v1/admin/governance/proposals",
        json={"action": "add", "reviewer": world.address(STRANGER)},
        headers=bearer(api.admin),
    )
    assert refused.status_code == 409 and refused.json()["error"]["code"] == "no_timelock"


def test_a_reviewer_is_added_by_the_safe_through_the_timelock(governed):
    world = governed
    api = Api(world)
    api.register(NEWCOMER)
    deployment = world.deployment
    view = api.get("/v1/admin/governance").json()
    registry = view["registry"]
    assert registry["owner"] == deployment.timelock.address
    assert registry["owner_kind"] == "timelock"
    assert registry["timelock"]["min_delay_seconds"] == LOCAL_TIMELOCK_DELAY
    assert [r["address"] for r in registry["reviewers"]] == [world.address(r) for r in REVIEWERS]
    safe = view["safe"]
    assert safe["address"] == deployment.safe.address and safe["proposer"] is True
    assert safe["threshold"] == 2 and len(safe["owners"]) == 3
    assert safe["app"] is None  # no Safe app for a local chain
    assert view["operations"] == []

    # The administrator prepares; nothing is sent and nothing is kept.
    newcomer = world.address(NEWCOMER)
    asked = api.http.post(
        "/v1/admin/governance/proposals",
        json={"action": "add", "reviewer": NEWCOMER},
        headers=bearer(api.admin),
    )
    assert asked.status_code == 200, asked.text
    proposal = asked.json()["proposal"]
    assert proposal["reviewer"] == newcomer
    assert proposal["call"]["to"] == deployment.registry.address
    assert proposal["schedule"]["to"] == deployment.timelock.address
    batch = proposal["batch_file"]
    assert batch["meta"]["checksum"] == batch_checksum(batch)
    assert batch["transactions"] == [proposal["schedule"]]
    assert batch["chainId"] == "31337"
    assert batch["meta"]["createdFromSafeAddress"] == deployment.safe.address

    # The Safe's owners schedule it (in the Safe app; here with two LOCAL TEST signers).
    deployment.safe_execute(proposal["schedule"]["to"], proposal["schedule"]["data"])
    (operation,) = api.get("/v1/admin/governance").json()["operations"]
    assert operation["operation_id"] == proposal["operation_id"]
    assert operation["state"] == "waiting" and operation["salt"] == proposal["salt"]
    assert operation["calls"][0]["description"] == f"registry.addReviewer({newcomer})"
    assert operation["execute"] == proposal["execute"]
    assert operation["execute_batch"]["meta"]["checksum"] == batch_checksum(
        operation["execute_batch"]
    )
    ready_at = parse_utc(operation["ready_at"])
    assert (ready_at - parse_utc(operation["scheduled_at"])).total_seconds() == 60

    # After the delay anyone may execute it: here a stranger's wallet.
    world.travel(format_utc(ready_at))
    assert api.get("/v1/admin/governance").json()["operations"][0]["state"] == "ready"
    stranger = world.wallet(STRANGER)
    stranger.send(
        {
            "chainId": 31337,
            "from": stranger.address,
            "to": operation["execute"]["to"],
            "data": operation["execute"]["data"],
            "value": 0,
        }
    )
    view = api.get("/v1/admin/governance").json()
    (done,) = view["operations"]
    assert done["state"] == "done" and done["executed_tx"] and "execute" not in done
    assert {"address": newcomer, "party": NEWCOMER} in view["registry"]["reviewers"]
    assert world.chain.is_reviewer(newcomer)

    for body, code in [
        ({"action": "add", "reviewer": newcomer}, "already_reviewer"),
        ({"action": "remove", "reviewer": world.address(STRANGER)}, "not_a_reviewer"),
        ({"action": "promote", "reviewer": newcomer}, "invalid_action"),
        ({"action": "add", "reviewer": "0x1234"}, "invalid_address"),
        ({"action": "add", "reviewer": "station:nobody"}, "no_wallet"),
    ]:
        refused = api.http.post(
            "/v1/admin/governance/proposals", json=body, headers=bearer(api.admin)
        )
        assert refused.json()["error"]["code"] == code, body
    removal = api.http.post(
        "/v1/admin/governance/proposals",
        json={"action": "remove", "reviewer": NEWCOMER},
        headers=bearer(api.admin),
    ).json()["proposal"]
    assert removal["call"]["function"] == f"removeReviewer({newcomer})"
    assert removal["salt"] != proposal["salt"]

"""The phase 1 HTTP API (step 1.6), exercised through Starlette's TestClient."""

import json
from datetime import timedelta
from pathlib import Path

import pytest
from helpers import catalog_bytes, packaged, policy_bytes
from starlette.testclient import TestClient

from orbit_watch import api as api_module
from orbit_watch.api import create_app, keys
from orbit_watch.canonical import sha256_bytes
from orbit_watch.reviewers import ReviewerRegistry
from orbit_watch.service import VerificationContext, open_service
from orbit_watch.sim.scenarios import REQUEST
from orbit_watch.timeutil import parse_utc

ROOT = Path(__file__).resolve().parents[2]
ACCEPTABLE = (ROOT / "examples/simulated/datasets/acceptable/observations.json").read_bytes()
REQUESTER = "requester:sim-cubesat-team"
STATION = "station:SIM-ESPOO"


class Clock:
    def __init__(self):
        self.now = parse_utc("2026-11-01T12:00:00Z")

    def __call__(self):
        return self.now

    def at(self, text):
        self.now = parse_utc(text)


class Client:
    """A TestClient with keys and automatic idempotency keys."""

    def __init__(self, test_client):
        self.http = test_client
        self.counter = 0

    def call(self, method, path, key=None, body=None, content=None, idem=None, headers=None):
        headers = dict(headers or {})
        if key:
            headers["Authorization"] = f"Bearer {key}"
        if method == "POST" and idem is not False:
            self.counter += 1
            headers["Idempotency-Key"] = idem or f"k{self.counter}"
        if body is not None:
            content = json.dumps(body).encode()
        return self.http.request(method, path, content=content, headers=headers)


@pytest.fixture
def world(tmp_path):
    directory = tmp_path / "service"
    registry = ReviewerRegistry.parse(packaged("reviewers.json"))
    context = VerificationContext(catalog=catalog_bytes(), policy=policy_bytes())
    service = open_service(directory, registry, context)
    clock = Clock()
    with service.storage.db.transaction():
        admin = keys.create_key(service.storage.db, "admin:maintainer", "admin", clock())
    client = Client(TestClient(create_app(service, clock=clock)))
    state = {
        "service": service,
        "clock": clock,
        "client": client,
        "admin": admin,
        "directory": directory,
        "registry": registry,
        "context": context,
    }
    yield state
    state["service"].storage.close()


def new_key(world, party, role):
    response = world["client"].call(
        "POST", "/v1/admin/keys", world["admin"], {"party": party, "role": role}
    )
    assert response.status_code == 201, response.text
    return response.json()["key"]


def funded_request(world, request_id="SIM-REQ-0001"):
    client, admin = world["client"], world["admin"]
    requester = new_key(world, REQUESTER, "requester")
    station = new_key(world, STATION, "station")
    assert (
        client.call(
            "POST", "/v1/admin/grants", admin, {"party": REQUESTER, "points": 1000}
        ).status_code
        == 200
    )
    document = dict(REQUEST, request_id=request_id)
    response = client.call("POST", "/v1/requests", requester, {"request": document})
    assert response.status_code == 201, response.text
    world["clock"].at("2026-11-01T12:01:00Z")
    assert client.call("POST", f"/v1/requests/{request_id}/open", requester).status_code == 200
    response = client.call(
        "POST",
        f"/v1/requests/{request_id}/fund",
        requester,
        {"observer": 100, "reviewer": 10, "platform_fee": 5},
    )
    assert response.status_code == 200, response.text
    assert client.call("POST", f"/v1/requests/{request_id}/reserve", station).status_code == 200
    return requester, station


def test_health_needs_no_key_but_everything_else_does(world):
    client = world["client"]
    assert client.call("GET", "/v1/health").json()["status"] == "ok"
    response = client.call("GET", "/v1/requests")
    assert response.status_code == 401 and response.json()["error"]["code"] == "unauthorized"
    assert client.call("GET", "/v1/requests", "ow_wrong").status_code == 401


def test_roles_are_enforced_and_a_station_cannot_move_points(world):
    requester, station = funded_request(world)
    client = world["client"]
    for path, body in [
        ("/v1/admin/grants", {"party": STATION, "points": 5}),
        ("/v1/requests/SIM-REQ-0001/fund", {"observer": 1, "reviewer": 0}),
        ("/v1/admin/keys", {"party": "station:x", "role": "station"}),
    ]:
        response = client.call("POST", path, station, body)
        assert response.status_code == 403, path
        assert response.json()["error"]["code"] == "forbidden_role"
    response = client.call("POST", "/v1/requests/SIM-REQ-0001/reserve", requester)
    assert response.status_code == 403
    assert client.call("GET", f"/v1/balances/{STATION}", requester).status_code == 403


def test_the_whole_chain_over_http(world):
    requester, station = funded_request(world)
    client, clock = world["client"], world["clock"]
    clock.at("2026-11-02T04:00:00Z")
    response = client.call(
        "POST",
        "/v1/requests/SIM-REQ-0001/deliveries",
        station,
        content=ACCEPTABLE,
        headers={"Content-SHA256": sha256_bytes(ACCEPTABLE)},
    )
    assert response.status_code == 200, response.text
    view = response.json()
    assert view["summary"]["automated_verdict"] == "pass"
    assert view["record"]["status"] == "challenge_period"
    report = client.call("GET", "/v1/requests/SIM-REQ-0001/report", requester)
    assert json.loads(report.content)["verdict"] == "pass"
    stored = client.call("GET", f"/v1/files/{sha256_bytes(ACCEPTABLE)}", requester)
    assert stored.content == ACCEPTABLE
    clock.at("2026-11-03T04:00:01Z")
    response = client.call("POST", "/v1/admin/tick", world["admin"])
    assert response.json() == {"changed": ["SIM-REQ-0001"]}
    view = client.call("GET", "/v1/requests/SIM-REQ-0001", requester).json()
    assert view["summary"]["status"] == "settled" and view["summary"]["outcome"] == "accepted"
    assert client.call("GET", f"/v1/balances/{STATION}", station).json()["points"] == 100
    assert client.call("GET", f"/v1/balances/{REQUESTER}", requester).json()["points"] == 895


def test_double_delivery_and_double_settlement_have_no_double_effect(world):
    _requester, station = funded_request(world)
    client, clock, service = world["client"], world["clock"], world["service"]
    clock.at("2026-11-02T04:00:00Z")
    path = "/v1/requests/SIM-REQ-0001/deliveries"
    first = client.call("POST", path, station, content=ACCEPTABLE, idem="delivery-1")
    journal = len(service.adapter.journal)
    replay = client.call("POST", path, station, content=ACCEPTABLE, idem="delivery-1")
    assert replay.status_code == 200 and replay.json() == first.json()
    assert replay.headers["Idempotent-Replayed"] == "true"
    assert len(service.adapter.journal) == journal
    again = client.call("POST", path, station, content=ACCEPTABLE, idem="delivery-2")
    assert again.status_code == 409 and again.json()["error"]["code"] == "forbidden_in_status"
    reused = client.call("POST", path, station, content=b"{}", idem="delivery-1")
    assert reused.status_code == 409 and reused.json()["error"]["code"] == "key_reused"
    clock.at("2026-11-03T05:00:00Z")
    client.call("POST", "/v1/admin/tick", world["admin"], idem="tick-1")
    balances = service.adapter.account_balances()
    second = client.call("POST", "/v1/admin/tick", world["admin"], idem="tick-2")
    assert second.json() == {"changed": []}
    assert service.adapter.account_balances() == balances
    settles = [e for e in service.adapter.journal if e.operation == "settle"]
    assert len(settles) == 1


def test_changes_need_an_idempotency_key_and_bodies_are_checked(world, monkeypatch):
    requester, station = funded_request(world)
    client = world["client"]
    response = client.call("POST", "/v1/requests/SIM-REQ-0001/cancel", requester, idem=False)
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "idempotency_key_required"
    response = client.call(
        "POST",
        "/v1/requests/SIM-REQ-0001/deliveries",
        station,
        content=ACCEPTABLE,
        headers={"Content-SHA256": "0" * 64},
    )
    assert response.json()["error"]["code"] == "hash_mismatch"
    response = client.call("POST", "/v1/requests", requester, content=b"[1, 2]")
    assert response.json()["error"]["code"] == "invalid_body"
    response = client.call(
        "POST",
        "/v1/requests",
        requester,
        {"request": dict(REQUEST, request_id="SIM-REQ-0009"), "terms": {"price": 5}},
    )
    assert response.status_code == 422
    monkeypatch.setattr(api_module, "MAX_BODY_BYTES", 10)
    response = client.call(
        "POST", "/v1/requests/SIM-REQ-0001/deliveries", station, content=ACCEPTABLE
    )
    assert response.status_code == 413
    assert client.call("GET", "/v1/requests/SIM-NOPE", requester).status_code == 404


def test_a_refused_call_changes_nothing(world):
    requester, _station = funded_request(world)
    client, service = world["client"], world["service"]
    before = (service.records["SIM-REQ-0001"], service.adapter.account_balances())
    response = client.call(
        "POST", "/v1/requests/SIM-REQ-0001/challenge", requester, {"reason": "too early"}
    )
    assert response.status_code == 409
    assert (service.records["SIM-REQ-0001"], service.adapter.account_balances()) == before
    # The refused call was not stored: the same key works for a valid call later.
    response = client.call("POST", "/v1/requests/SIM-REQ-0001/cancel", requester, idem="k1x")
    assert response.status_code == 409  # reserved requests cannot be cancelled


def test_reviewers_work_through_their_task_queue(world):
    requester, station = funded_request(world)
    client, clock, service = world["client"], world["clock"], world["service"]
    clock.at("2026-11-02T04:00:00Z")
    client.call("POST", "/v1/requests/SIM-REQ-0001/deliveries", station, content=ACCEPTABLE)
    clock.at("2026-11-02T05:00:00Z")
    response = client.call(
        "POST",
        "/v1/requests/SIM-REQ-0001/challenge",
        requester,
        {"reason": "Please check the timing"},
    )
    assert response.status_code == 200, response.text
    reviewers = response.json()["record"]["reviewers"]
    reviewer_keys = {r: new_key(world, r, "reviewer") for r in reviewers}
    clock.at("2026-11-02T06:00:00Z")
    for reviewer in reviewers[:2]:
        tasks = client.call("GET", "/v1/tasks", reviewer_keys[reviewer]).json()["tasks"]
        assert len(tasks) == 2
        for task in tasks:
            response = client.call(
                "POST",
                f"/v1/tasks/{task['task_id']}/review",
                reviewer_keys[reviewer],
                {"approve": True, "reason": "Residuals are fine"},
            )
            assert response.status_code == 200 and response.json()["recorded"] is True
    record = service.records["SIM-REQ-0001"]
    assert record.outcome is not None and str(record.outcome) == "accepted"
    profile = client.call(
        "GET", f"/v1/reviewers/{reviewers[0]}/profile", reviewer_keys[reviewers[0]]
    )
    assert profile.json()["calibration"]["answered"] == 1
    other = client.call("GET", f"/v1/reviewers/{reviewers[0]}/profile", reviewer_keys[reviewers[1]])
    assert other.status_code == 403
    assert client.call("GET", "/v1/tasks", requester).status_code == 403


def test_new_keys_are_shown_once(world):
    client, admin = world["client"], world["admin"]
    first = client.call(
        "POST",
        "/v1/admin/keys",
        admin,
        {"party": "station:SIM-OULU", "role": "station"},
        idem="key-1",
    )
    assert first.json()["key"].startswith("ow_")
    replay = client.call(
        "POST",
        "/v1/admin/keys",
        admin,
        {"party": "station:SIM-OULU", "role": "station"},
        idem="key-1",
    )
    assert replay.json()["key"] is None
    bad = client.call("POST", "/v1/admin/keys", admin, {"party": "oulu", "role": "station"})
    assert bad.status_code == 422 and bad.json()["error"]["code"] == "invalid_party"
    stored = world["service"].storage.db.query("SELECT key_hash FROM api_keys")
    assert all(first.json()["key"] not in row["key_hash"] for row in stored)


def test_state_and_keys_survive_a_restart(world):
    requester, station = funded_request(world)
    world["service"].storage.close()
    service = open_service(world["directory"], world["registry"], world["context"])
    world["service"] = service
    client = Client(TestClient(create_app(service, clock=world["clock"])))
    view = client.call("GET", "/v1/requests/SIM-REQ-0001", requester).json()
    assert view["record"]["status"] == "reserved"
    world["clock"].now += timedelta(hours=1)
    response = client.call(
        "POST", "/v1/requests/SIM-REQ-0001/deliveries", station, content=ACCEPTABLE
    )
    assert response.status_code == 200


def test_keys_command_and_serve_wiring(tmp_path, capsys, monkeypatch):
    from orbit_watch.cli import main

    directory = tmp_path / "svc"
    assert (
        main(["keys", "create", "--dir", str(directory), "--role", "admin", "--party", "admin:me"])
        == 0
    )
    printed = capsys.readouterr()
    key = printed.out.strip()
    assert key.startswith("ow_") and "shown only this once" in printed.err
    assert (
        main(
            [
                "keys",
                "create",
                "--dir",
                str(directory),
                "--role",
                "station",
                "--party",
                "requester:x",
            ]
        )
        == 2
    )

    calls = {}

    def fake_run(app, host, port):
        calls.update(host=host, port=port)
        client = TestClient(app)
        response = client.get("/v1/requests", headers={"Authorization": f"Bearer {key}"})
        calls["status"] = response.status_code

    import uvicorn

    monkeypatch.setattr(uvicorn, "run", fake_run)
    assert main(["serve", "--dir", str(directory), "--port", "8123"]) == 0
    assert calls == {"host": "127.0.0.1", "port": 8123, "status": 200}
    assert "SIMULATED" in capsys.readouterr().out

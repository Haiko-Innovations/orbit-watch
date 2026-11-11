"""Data publication (phase 1, step 1.8): licence, embargo, access and permanent URLs."""

from datetime import timedelta
from pathlib import Path

from helpers import request_bytes
from test_api import STATION, funded_request, new_key, world  # noqa: F401 - fixture
from test_service import (
    DELIVERY,
    REQUESTER,
    SPLIT,
    T0,
    make_service,
)

from orbit_watch.canonical import sha256_bytes
from orbit_watch.lifecycle import Status

ACCEPTABLE_PATH = "examples/simulated/datasets/acceptable/observations.json"


def delivered(service, data, embargo=0, request_id="SIM-REQ-0001"):
    record = service.create(
        request_bytes(request_id=request_id), REQUESTER, T0, embargo_days=embargo
    )
    rid = record.request_id
    service.open(rid, REQUESTER, T0 + timedelta(minutes=1))
    service.fund(rid, REQUESTER, SPLIT, T0 + timedelta(minutes=2))
    service.reserve(rid, STATION, T0 + timedelta(minutes=3))
    service.deliver(rid, STATION, data, DELIVERY)
    return rid


def test_files_are_private_until_settled_then_public(repo_root):
    data = (repo_root / ACCEPTABLE_PATH).read_bytes()
    service, _ = make_service()
    rid = delivered(service, data)
    now = DELIVERY + timedelta(hours=1)
    publication = service.publication(rid, now)
    assert publication["state"] == "pending" and publication["public_from"] is None
    assert [f["role"] for f in publication["files"]] == ["request", "observations", "report"]
    observations = sha256_bytes(data)
    assert not service.can_read_file(observations, None, None, now)  # the public
    assert not service.can_read_file(observations, "station:SIM-OTHER", "station", now)
    assert service.can_read_file(observations, STATION, "station", now)  # the observer
    assert service.can_read_file(observations, REQUESTER, "requester", now)
    assert service.can_read_file(observations, "admin:x", "admin", now)
    service.tick(DELIVERY + timedelta(hours=24))
    later = DELIVERY + timedelta(hours=25)
    publication = service.publication(rid, later)
    assert publication["state"] == "published"
    assert publication["licence"] == "CC-BY-4.0"
    assert publication["licence_url"] == "https://creativecommons.org/licenses/by/4.0/"
    assert STATION in publication["attribution"] and publication["simulated"] is True
    assert publication["files"][1]["url"] == f"/v1/public/files/{observations}"
    assert service.can_read_file(observations, None, None, later)
    assert [p["request_id"] for p in service.published(later)] == [rid]


def test_embargo_delays_publication(repo_root):
    data = (repo_root / ACCEPTABLE_PATH).read_bytes()
    service, _ = make_service()
    rid = delivered(service, data, embargo=7)
    service.tick(DELIVERY + timedelta(hours=24))
    settled = service.records[rid].updated_at
    assert service.records[rid].status is Status.SETTLED
    assert service.publication(rid, settled + timedelta(days=6))["state"] == "embargoed"
    assert service.published(settled + timedelta(days=6)) == []
    assert service.publication(rid, settled + timedelta(days=7))["state"] == "published"


def test_an_expired_request_publishes_only_its_request():
    service, _ = make_service()
    record = service.create(request_bytes(), REQUESTER, T0)
    service.open(record.request_id, REQUESTER, T0 + timedelta(minutes=1))
    service.tick(T0 + timedelta(days=3))
    publication = service.publication(record.request_id, T0 + timedelta(days=3))
    assert publication["state"] == "published"
    assert [f["role"] for f in publication["files"]] == ["request"]


def test_calibration_files_are_never_public(repo_root):
    data = (repo_root / ACCEPTABLE_PATH).read_bytes()
    service, _ = make_service()
    rid = delivered(service, data)
    service.challenge(rid, REQUESTER, "Second opinion", DELIVERY + timedelta(hours=1))
    task = next(iter(service.calibration_tasks.values()))
    far = DELIVERY + timedelta(days=60)
    service.tick(far)
    assert service.publication(rid, far)["state"] == "published"
    for digest in (task.observations_sha256, task.report_sha256, task.request_sha256):
        assert not service.can_read_file(digest, None, None, far)
        assert not service.can_read_file(digest, REQUESTER, "requester", far)
        assert service.can_read_file(digest, task.reviewer, "reviewer", far)


def test_public_endpoints_over_http(world):  # noqa: F811 - pytest fixture
    requester, station = funded_request(world)
    client, clock = world["client"], world["clock"]
    outsider = new_key(world, "station:SIM-OTHER", "station")
    clock.at("2026-11-02T04:00:00Z")
    acceptable = (Path(__file__).resolve().parents[2] / ACCEPTABLE_PATH).read_bytes()
    client.call("POST", "/v1/requests/SIM-REQ-0001/deliveries", station, content=acceptable)
    digest = sha256_bytes(acceptable)
    assert client.call("GET", "/v1/public/requests").json() == {"requests": []}
    assert client.call("GET", f"/v1/public/files/{digest}").status_code == 404
    assert client.call("GET", f"/v1/files/{digest}", outsider).status_code == 404
    assert client.call("GET", "/v1/requests/SIM-REQ-0001/report", outsider).status_code == 404
    assert client.call("GET", "/v1/requests/SIM-REQ-0001/report", requester).status_code == 200
    clock.at("2026-11-03T04:00:01Z")
    client.call("POST", "/v1/admin/tick", world["admin"])
    listed = client.call("GET", "/v1/public/requests").json()["requests"]
    assert [p["request_id"] for p in listed] == ["SIM-REQ-0001"]
    response = client.call("GET", f"/v1/public/files/{digest}")
    assert response.status_code == 200 and response.content == acceptable
    assert (
        response.headers["Link"] == '<https://creativecommons.org/licenses/by/4.0/>; rel="license"'
    )
    view = client.call("GET", "/v1/public/requests/SIM-REQ-0001").json()
    assert view["publication"]["state"] == "published"
    assert client.call("GET", "/v1/public/requests/SIM-NOPE").status_code == 404
    assert client.call("GET", "/v1/requests/SIM-REQ-0001/report", outsider).status_code == 200

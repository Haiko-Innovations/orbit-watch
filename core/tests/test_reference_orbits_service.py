"""Reference orbits in the service (phase 5, step 5.4; decision D-47).

The element sets here are made up for the tests: the elements of a SIMULATED object,
given to object 99001, a test object that names no real satellite. No real element set is
committed (decision D-06).
"""

import json
from datetime import timedelta

import pytest
from helpers import catalog_bytes, packaged, policy_bytes, request_bytes
from starlette.testclient import TestClient

from orbit_watch import lifecycle as lc
from orbit_watch.api import create_app, keys
from orbit_watch.canonical import dumps_pretty
from orbit_watch.catalog import parse_catalog, record_sha256
from orbit_watch.formats import owjson
from orbit_watch.reviewers import ReviewerRegistry
from orbit_watch.service import RequestService, ServiceError, VerificationContext, open_service
from orbit_watch.settlement.ledger import LedgerAdapter
from orbit_watch.sim.simulator import load_profile, simulate
from orbit_watch.timeutil import parse_utc

TEST_OBJECT = 99001
REQUESTER = "requester:sim-cubesat-team"
STATION = "station:SIM-ESPOO"
SPLIT = lc.RewardSplit(observer=100, reviewer=10, platform_fee=5)
T0 = parse_utc("2026-11-01T12:00:00Z")
DELIVERY = parse_utc("2026-11-02T04:00:00Z")


def made_up_record(epoch_shift_days=0.0):
    """SIM-CUBESAT-A's elements given to the test object; with a shift, the same elements
    at a later epoch, which is another orbit."""
    record = dict(json.loads(catalog_bytes())["records"][0])
    record.update(NORAD_CAT_ID=TEST_OBJECT, OBJECT_NAME="TEST OBJECT", OBJECT_ID="2026-999A")
    if epoch_shift_days:
        epoch = parse_utc(record["EPOCH"] + "Z") + timedelta(days=epoch_shift_days)
        record["EPOCH"] = epoch.strftime("%Y-%m-%dT%H:%M:%S.%f")
    return record


def upload(*records, simulated=False):
    document = {
        "format": "orbit-watch/gp-catalog",
        "format_version": "1.0",
        "simulated": simulated,
        "description": "Made-up element sets for a test.",
        "records": list(records),
    }
    return dumps_pretty(document, sort_keys=False).encode()


def policy():
    document = json.loads(policy_bytes())
    document["allow"].append({"norad_id": TEST_OBJECT, "name": "TEST OBJECT"})
    return json.dumps(document).encode()


def observations():
    """SIMULATED observations of the test object, computed from the true elements."""
    catalog = parse_catalog(upload(made_up_record()))
    observed = simulate(
        catalog,
        TEST_OBJECT,
        load_profile("sim-cmos-gps"),
        parse_utc("2026-11-01T15:00:00Z"),
        parse_utc("2026-11-02T03:00:00Z"),
        seed=7,
    )
    return owjson.write_observation_set(observed).encode()


def make_service():
    ledger = LedgerAdapter()
    ledger.grant(REQUESTER, 1000, key="budget")
    registry = ReviewerRegistry.parse(packaged("reviewers.json"))
    context = VerificationContext(catalog=catalog_bytes(), policy=policy())
    return RequestService(ledger, registry, context)


def deliver(service, data):
    record = service.create(request_bytes(norad_id=TEST_OBJECT), REQUESTER, T0)
    rid = record.request_id
    service.open(rid, REQUESTER, T0 + timedelta(minutes=1))
    service.fund(rid, REQUESTER, SPLIT, T0 + timedelta(minutes=2))
    service.reserve(rid, STATION, T0 + timedelta(minutes=5))
    service.deliver(rid, STATION, data, DELIVERY)
    report = json.loads(service.files[service.deliveries[rid].report_sha256])
    return {check["id"]: check for check in report["checks"]}, report


def test_a_delivery_is_verified_against_the_nearest_stored_set():
    service = make_service()
    right, wrong = made_up_record(), made_up_record(epoch_shift_days=10)
    kept, already = service.keep_element_sets([wrong, right], "uploaded", T0, "admin:a")
    assert len(kept) == 2 and already == 0
    checks, report = deliver(service, observations())
    assert checks["orbit_residuals"]["result"] == "pass"
    reference = report["reference_orbit"]
    assert reference["element_set_sha256"] == record_sha256(right)
    assert reference["selection"] == "nearest the middle of the observations"
    assert reference["element_sets_in_catalogue"] == 2
    assert reference["source"]["kept_from"] == "uploaded"
    assert reference["source"]["service"] == "uploaded by an administrator"


def test_without_a_stored_set_the_object_has_no_orbit():
    checks, _ = deliver(make_service(), observations())
    assert checks["orbit_residuals"]["result"] == "inconclusive"
    assert "no orbit for object 99001" in checks["orbit_residuals"]["reason"]


def test_a_set_kept_twice_is_kept_once_and_simulated_objects_have_none():
    service = make_service()
    service.keep_element_sets([made_up_record()], "uploaded", T0)
    assert service.keep_element_sets([made_up_record()], "celestrak", T0) == ([], 1)
    assert len(service.reference_orbits(TEST_OBJECT)) == 1
    simulated = dict(json.loads(catalog_bytes())["records"][0])
    with pytest.raises(ServiceError) as refused:
        service.keep_element_sets([simulated], "uploaded", T0)
    assert refused.value.code == "simulated_object"


def test_the_simulated_objects_keep_their_own_catalogue():
    service = make_service()
    service.keep_element_sets([made_up_record()], "uploaded", T0)
    assert service.catalog_for([339001]) == catalog_bytes()
    real = json.loads(service.catalog_for([TEST_OBJECT]))
    assert real["simulated"] is False and len(real["records"]) == 1


# Through the API, with the database ----------------------------------------------------


class Clock:
    def __init__(self):
        self.now = T0

    def __call__(self):
        return self.now


@pytest.fixture
def api(database):
    registry = ReviewerRegistry.parse(packaged("reviewers.json"))
    context = VerificationContext(catalog=catalog_bytes(), policy=policy())
    service = open_service(database, registry, context)
    clock = Clock()
    with service.storage.db.transaction():
        admin = keys.create_key(service.storage.db, "admin:maintainer", "admin", clock())
        station = keys.create_key(service.storage.db, STATION, "station", clock())
    client = TestClient(create_app(service, clock=clock, wall_clock=clock))
    yield {
        "service": service,
        "client": client,
        "admin": admin,
        "station": station,
        "database": database,
        "registry": registry,
        "context": context,
    }
    service.storage.close()


def post(world, path, body, key, idem):
    return world["client"].post(
        path,
        content=body,
        headers={"Authorization": f"Bearer {key}", "Idempotency-Key": idem},
    )


def test_an_administrator_uploads_sets_that_are_named_but_not_served(api):
    response = post(api, "/v1/admin/element-sets", upload(made_up_record()), api["admin"], "u1")
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["already_kept"] == 0 and len(body["kept"]) == 1
    named = body["kept"][0]
    assert named["norad_id"] == TEST_OBJECT and named["source"] == "uploaded"
    assert named["element_set_sha256"] == record_sha256(made_up_record())
    assert named["fetched_at"] == "2026-11-01T12:00:00.000Z"
    again = post(api, "/v1/admin/element-sets", upload(made_up_record()), api["admin"], "u2")
    assert again.json() == {"kept": [], "already_kept": 1}
    listed = api["client"].get(f"/v1/public/reference-orbits?norad_id={TEST_OBJECT}")
    assert listed.status_code == 200
    assert listed.json()["element_sets"] == [named]
    assert "MEAN_MOTION" not in listed.text and "INCLINATION" not in listed.text
    # Kept in the database: another process sees it.
    other = open_service(api["database"], api["registry"], api["context"])
    try:
        assert other.reference_orbits(TEST_OBJECT) == [named]
    finally:
        other.storage.close()


def test_uploads_that_are_refused(api):
    simulated = post(
        api, "/v1/admin/element-sets", upload(made_up_record(), simulated=True), api["admin"], "s"
    )
    assert simulated.status_code == 422
    assert simulated.json()["error"]["code"] == "simulated_element_sets"
    sim_object = dict(json.loads(catalog_bytes())["records"][0])
    refused = post(api, "/v1/admin/element-sets", upload(sim_object), api["admin"], "o")
    assert refused.json()["error"]["code"] == "simulated_object"
    garbage = post(api, "/v1/admin/element-sets", b"not a catalogue", api["admin"], "g")
    assert garbage.json()["error"]["code"] == "invalid_element_sets"
    station = post(api, "/v1/admin/element-sets", upload(made_up_record()), api["station"], "x")
    assert station.status_code == 403
    assert api["service"].reference_orbits() == []
    bad = api["client"].get("/v1/public/reference-orbits?norad_id=ISS")
    assert bad.json()["error"]["code"] == "invalid_query"


def test_the_client_command_uploads(api, tmp_path, monkeypatch, capsys):
    from orbit_watch import cli_client
    from orbit_watch.client import ApiClient

    path = tmp_path / "sets.json"
    path.write_bytes(upload(made_up_record()))
    http = api["client"]

    class Reply:
        def __init__(self, response):
            self.response = response
            self.replayed = False

        def json(self):
            return self.response.json()

    def request(self, method, url, body=None, content_type=None, idempotency_key=None, **kw):
        headers = {"Authorization": f"Bearer {api['admin']}", "Content-Type": content_type}
        headers["Idempotency-Key"] = idempotency_key
        return Reply(http.request(method, url, content=body, headers=headers))

    monkeypatch.setattr(ApiClient, "request", request)
    args = type(
        "Args",
        (),
        {
            "file": str(path),
            "api": "http://test",
            "key": api["admin"],
            "json": False,
            "idempotency_key": "c1",
        },
    )()
    assert cli_client.cmd_admin_upload_orbits(args) == 0
    out = capsys.readouterr().out
    assert "1 element set(s) kept, labelled as uploaded; 0 already kept" in out
    assert record_sha256(made_up_record()) in out

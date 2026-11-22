"""The local stack's stand-ins (decision D-53), seeded as the stack seeds them, without a
chain: a real object's stand-in on the allow-list with an uploaded element set, a SIMULATED
request for it that a simulated station fulfils, a real request for it, and a replay of
made-up published observations that settles. Its labels say what each part is (D-52).
"""

import hashlib
import json
from datetime import timedelta

import pytest
from helpers import catalog_bytes, packaged, policy_bytes, request_bytes
from stand_ins import (
    EXAMPLE_ORCID,
    STAND_IN,
    STAND_IN_NAME,
    STAND_IN_REASON,
    published_observations,
    stand_in_catalogue,
    stand_in_observations,
)
from starlette.testclient import TestClient
from test_orbit_follower import REQUESTER, SPLIT, STATION, T0, Clock

from orbit_watch.api import create_app, keys
from orbit_watch.replay import replay_request
from orbit_watch.reviewers import ReviewerRegistry
from orbit_watch.service import VerificationContext, open_service
from orbit_watch.sim.simulator import load_profile
from orbit_watch.timeutil import format_utc, parse_utc

REPLAY_STATION = "station:LOCAL-REPLAY"
ADMIN = "admin:local"
WINDOW = ("2026-11-01T15:00:00Z", "2026-11-02T03:00:00Z")  # the stack's requests' window


@pytest.fixture
def world(database):
    registry = ReviewerRegistry.parse(packaged("reviewers.json"))
    context = VerificationContext(catalog=catalog_bytes(), policy=policy_bytes())
    service = open_service(database, registry, context)
    service.adapter.grant(REQUESTER, 10_000, key="budget")
    clock = Clock()
    with service.storage.db.transaction():
        made = {
            party: keys.create_key(service.storage.db, party, party.split(":")[0], clock())
            for party in (ADMIN, STATION, REPLAY_STATION, REQUESTER)
        }
    app = create_app(service, clock=clock, wall_clock=clock)
    yield {"service": service, "client": TestClient(app), "clock": clock, "keys": made}
    service.storage.close()


def call(world, path, party, body=None, content=None, content_type="application/json"):
    payload = content if content is not None else json.dumps(body or {}).encode()
    return world["client"].post(
        path,
        content=payload,
        headers={
            "Authorization": f"Bearer {world['keys'][party]}",
            "Content-Type": content_type,
            "Idempotency-Key": hashlib.sha256(path.encode() + payload + party.encode()).hexdigest(),
        },
    )


def stand_in_on_the_list(world):
    allowed = call(
        world,
        "/v1/admin/allowlist",
        ADMIN,
        {"norad_id": STAND_IN, "name": STAND_IN_NAME, "reason": STAND_IN_REASON},
    )
    assert allowed.status_code == 200, allowed.text
    uploaded = call(world, "/v1/admin/element-sets", ADMIN, content=stand_in_catalogue())
    assert uploaded.status_code == 200, uploaded.text


def test_the_stand_in_comes_onto_the_list_with_its_uploaded_orbit(world):
    stand_in_on_the_list(world)
    target = world["service"].targets()[STAND_IN]
    assert target.source == "administrator" and target.simulated is False
    assert "made up" in (target.reason or "")
    (stored,) = world["service"].element_sets[STAND_IN]
    assert stored.source == "uploaded"


def test_simulated_stations_observe_the_stand_in(world):
    stand_in_on_the_list(world)
    service, now = world["service"], world["clock"]
    rid = "SIM-REQ-3010"
    document = request_bytes(
        request_id=rid, norad_id=STAND_IN, simulated=True, start=WINDOW[0], end=WINDOW[1]
    )
    service.create(document, REQUESTER, now())
    service.open(rid, REQUESTER, now())
    service.fund(rid, REQUESTER, SPLIT, now())
    service.reserve(rid, STATION, now())
    start, end = (parse_utc(t) for t in WINDOW)
    observations = stand_in_observations(load_profile("sim-cmos-gps"), start, end, seed=210)
    service.deliver(rid, STATION, observations, T0 + timedelta(hours=16))
    assert service.deliveries[rid].verdict == "pass"
    labels = service.labels(rid)
    assert labels["object"]["source"] == "administrator"
    assert labels["reference_orbit"]["source"] == "uploaded"
    assert labels["observations"]["kind"] == "simulated"

    # A real request for it asks for real observations, beside the SIMULATED one.
    real = request_bytes(
        request_id="REQ-3011", norad_id=STAND_IN, simulated=False, start=WINDOW[0], end=WINDOW[1]
    )
    service.create(real, REQUESTER, now())
    assert service.labels("REQ-3011")["request_simulated"] is False


def test_the_replay_of_made_up_published_observations_settles(world):
    stand_in_on_the_list(world)
    service, clock = world["service"], world["clock"]
    data = published_observations()
    document = json.loads(replay_request(data, "REPLAY-3020", REPLAY_STATION))
    assert document["replay"]["observers"] == [EXAMPLE_ORCID]
    terms = {
        "delivery_deadline": format_utc(T0 + timedelta(days=2)),
        "challenge_period_hours": 1,
    }
    body = {"requester": REQUESTER, "request": document, "terms": terms}
    assert call(world, "/v1/admin/replays", ADMIN, body).status_code == 201
    service.open("REPLAY-3020", REQUESTER, clock())
    service.fund("REPLAY-3020", REQUESTER, SPLIT, clock())
    assert call(world, "/v1/requests/REPLAY-3020/reserve", REPLAY_STATION).status_code == 200
    delivered = call(
        world, "/v1/requests/REPLAY-3020/deliveries?format=json", REPLAY_STATION, content=data
    )
    assert delivered.status_code == 200, delivered.text
    assert delivered.json()["summary"]["automated_verdict"] == "pass"

    clock.now = T0 + timedelta(hours=2)
    assert call(world, "/v1/admin/tick", ADMIN).json()["changed"] == ["REPLAY-3020"]
    record = service.records["REPLAY-3020"]
    assert str(record.status) == "settled" and str(record.outcome) == "accepted"
    assert service.adapter.balance(REPLAY_STATION) == SPLIT.observer
    labels = service.labels("REPLAY-3020")
    assert labels["request_simulated"] is False
    assert labels["observations"]["kind"] == "replayed"
    assert labels["replay"]["station"] == REPLAY_STATION

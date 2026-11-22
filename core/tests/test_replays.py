"""Replays (phase 5, step 5.5, second part; decisions P5-10, D-51).

An administrator creates a replay request for observations that someone else published,
with a window in the past; its replay station delivers exactly that file, once the service
keeps SatChecker's set nearest the window, and the testnet reward goes to the replay
station. No test here calls an outside service: CelesTrak and SatChecker are local stand-ins
whose objects name no real satellite. The "published" file is made up too: SIMULATED
observations relabelled as published by a made-up source, credited to ORCID's documented
example iD of a fictitious researcher.
"""

import hashlib
import json
from datetime import timedelta
from pathlib import Path

import pytest
from helpers import catalog_bytes, packaged, policy_bytes
from starlette.testclient import TestClient
from test_allowlist_service import GroupStandIn
from test_orbit_follower import REQUESTER, SPLIT, STATION, T0, Clock, csv_of, made_up_record

from orbit_watch import orbit_follower
from orbit_watch.api import create_app, keys
from orbit_watch.catalog import parse_catalog
from orbit_watch.cli import build_parser
from orbit_watch.documents import Request
from orbit_watch.formats import owjson
from orbit_watch.formats.owjson import FormatError
from orbit_watch.replay import replay_request
from orbit_watch.reviewers import ReviewerRegistry
from orbit_watch.service import ServiceError, VerificationContext, open_service
from orbit_watch.sim.simulator import load_profile, simulate
from orbit_watch.timeutil import format_utc, parse_utc

EXAMPLE_ORCID = "0000-0002-1825-0097"  # ORCID's example iD of a fictitious researcher
REAL = "../examples/real/observations/58296-20240508T2142-SCORE-a25cc06b7fd1.json"
OTHER_STATION = "station:SIM-OULU"
DEADLINE = format_utc(T0 + timedelta(days=7))


def published(seed=7):
    """A made-up published file: observations of 99015 in a window that has ended, with a
    source.origin like SCORE's. Its station's place has three decimals."""
    observed = simulate(
        parse_catalog(csv_of(made_up_record(99015))),
        99015,
        load_profile("sim-cmos-gps"),
        parse_utc("2026-10-31T15:00:00Z"),
        parse_utc("2026-11-01T03:00:00Z"),
        seed=seed,
    )
    document = json.loads(owjson.write_observation_set(observed))
    document["simulated"] = False
    document["format_version"] = "1.1"
    document["source"] = {
        "software": "a test",
        "notes": "Made up for a test: not real observations.",
        "origin": {
            "name": "A MADE-UP SOURCE, for tests",
            "url": "https://example.org",
            "licence": "CC-BY-4.0",
            "observers": [EXAMPLE_ORCID],
            "observation_ids": [str(i) for i in range(len(document["observations"]))],
        },
    }
    return json.dumps(document, indent=2).encode()


@pytest.fixture
def world(database):
    """The allow-list tests' world, with the public service's rounding of station places."""
    registry = ReviewerRegistry.parse(packaged("reviewers.json"))
    context = VerificationContext(catalog=catalog_bytes(), policy=policy_bytes())
    service = open_service(database, registry, context)
    service.adapter.grant(REQUESTER, 10_000, key="budget")
    clock = Clock()
    with service.storage.db.transaction():
        made = {
            party: keys.create_key(service.storage.db, party, party.split(":")[0], clock())
            for party in ("admin:maintainer", STATION, OTHER_STATION, REQUESTER)
        }
    stand_in = GroupStandIn()
    fetcher = orbit_follower.Fetcher(opener=stand_in, sleep=lambda s: None)
    app = create_app(
        service, clock=clock, wall_clock=clock, orbit_fetcher=fetcher, station_decimals=2
    )
    world = {
        "service": service,
        "api": app.state.api,
        "client": TestClient(app),
        "clock": clock,
        "stand_in": stand_in,
        "keys": made,
    }
    world["api"].follow_once()  # CelesTrak's groups, then 99015 is on the list
    clock.now = T0 + timedelta(minutes=15)
    world["api"].follow_once()
    assert 99015 in service.targets()
    yield world
    service.storage.close()


def call(world, method, path, party, body=None, content=None):
    payload = content if content is not None else json.dumps(body or {}).encode()
    return world["client"].request(
        method,
        path,
        content=payload,
        headers={
            "Authorization": f"Bearer {world['keys'][party]}",
            "Idempotency-Key": hashlib.sha256(path.encode() + payload + party.encode()).hexdigest(),
        },
    )


def create_replay(world, rid="REPLAY-0001", data=None, station=STATION, party="admin:maintainer"):
    document = json.loads(replay_request(data or published(), rid, station))
    body = {"requester": REQUESTER, "request": document, "terms": {"delivery_deadline": DEADLINE}}
    return call(world, "POST", "/v1/admin/replays", party, body)


def open_and_fund(world, rid="REPLAY-0001"):
    service, now = world["service"], world["clock"]
    service.open(rid, REQUESTER, now())
    service.fund(rid, REQUESTER, SPLIT, now())


def deliver(world, rid, data, party=STATION):
    return call(world, "POST", f"/v1/requests/{rid}/deliveries?format=json", party, content=data)


# The request ----------------------------------------------------------------------------------


def test_a_replay_request_names_the_published_file():
    data = Path(REAL).read_bytes()
    request = Request.parse(replay_request(data, "REPLAY-0001", "station:replay"))
    assert request.replay is not None
    assert request.replay.observations_sha256 == hashlib.sha256(data).hexdigest()
    assert request.replay.station == "station:replay"
    assert request.replay.source.startswith("SCORE")
    assert request.replay.licence == "CC-BY-4.0"
    assert request.replay.observers == ("0000-0001-6659-9253",)
    assert request.simulated is False and request.norad_id == 58296
    observed = owjson.read_observation_set(data).observations
    assert request.window_start < min(o.time for o in observed)
    assert request.window_end > max(o.time for o in observed)
    assert request.min_observations == len(observed)
    assert "SCORE" in (request.title or "")


def test_only_published_observations_can_be_replayed():
    observed = simulate(
        parse_catalog(catalog_bytes()),
        339001,
        load_profile("sim-cmos-gps"),
        parse_utc("2026-11-01T15:00:00Z"),
        parse_utc("2026-11-02T03:00:00Z"),
        seed=1,
    )
    simulated = owjson.write_observation_set(observed).encode()
    with pytest.raises(FormatError, match="someone else published"):
        replay_request(simulated, "REPLAY-0001", "station:replay")
    document = json.loads(published())
    del document["source"]["origin"]
    document["format_version"] = "1.0"
    with pytest.raises(FormatError, match="someone else published"):
        replay_request(json.dumps(document).encode(), "REPLAY-0001", "station:replay")


def test_only_an_administrator_creates_a_replay(world):
    document = json.loads(replay_request(published(), "REPLAY-0001", STATION))
    body = {"request": document, "terms": {"delivery_deadline": DEADLINE}}
    by_requester = call(world, "POST", "/v1/requests", REQUESTER, body)
    assert by_requester.status_code == 403
    assert by_requester.json()["error"]["code"] == "replay_admin_only"
    assert create_replay(world, party=REQUESTER).json()["error"]["code"] == "forbidden_role"
    made = create_replay(world)
    assert made.status_code == 201, made.text
    assert made.json()["record"]["requester"] == REQUESTER
    assert made.json()["record"]["status"] == "draft"
    assert world["service"].replay_of("REPLAY-0001").station == STATION
    # Not a replay: the administrator's endpoint is for replays only.
    normal = json.loads(published())
    plain = {
        "format": "orbit-watch/request",
        "format_version": "1.0",
        "simulated": False,
        "request_id": "REQ-0002",
        "target": {"norad_id": normal["target"]["norad_id"]},
        "window": document["window"],
        "requirements": document["requirements"],
    }
    body = {"requester": REQUESTER, "request": plain, "terms": {"delivery_deadline": DEADLINE}}
    refused = call(world, "POST", "/v1/admin/replays", "admin:maintainer", body)
    assert refused.json()["error"]["code"] == "not_a_replay"
    body = {"requester": "station:x", "request": document}
    refused = call(world, "POST", "/v1/admin/replays", "admin:maintainer", body)
    assert refused.json()["error"]["code"] == "invalid_body"


def test_a_replays_window_lies_in_the_past(world):
    service = world["service"]
    request = replay_request(published(), "REPLAY-0001", STATION)
    early = T0 - timedelta(days=2)
    with pytest.raises(ServiceError) as refused:
        service.create(request, REQUESTER, early, replay_by="admin:maintainer")
    assert refused.value.code == "replay_window_not_past"
    # Without a deadline it is a day after the window, long past by now.
    late = T0 + timedelta(days=2)
    with pytest.raises(ServiceError, match="deadline must be in the future"):
        service.create(request, REQUESTER, late, replay_by="admin:maintainer")


def test_only_the_replay_station_reserves_and_delivers_it(world):
    # Asked about before it exists, it is still a replay once it does.
    assert deliver(world, "REPLAY-0001", published()).status_code != 200
    assert create_replay(world).status_code == 201
    open_and_fund(world)
    refused = call(world, "POST", "/v1/requests/REPLAY-0001/reserve", OTHER_STATION)
    assert refused.status_code == 403
    assert refused.json()["error"]["code"] == "replay_station_only"
    reserved = call(world, "POST", "/v1/requests/REPLAY-0001/reserve", STATION)
    assert reserved.status_code == 200, reserved.text


# Delivery and settlement ----------------------------------------------------------------------


def test_a_replay_settles_and_pays_its_replay_station(world):
    """The whole chain with published observations: the replay waits for SatChecker's set,
    delivers exactly the named file, passes, and pays the replay station."""
    service, clock = world["service"], world["clock"]
    data = published()
    assert create_replay(world, data=data).status_code == 201
    open_and_fund(world)
    assert call(world, "POST", "/v1/requests/REPLAY-0001/reserve", STATION).status_code == 200

    pending = deliver(world, "REPLAY-0001", data)
    assert pending.status_code == 409
    assert pending.json()["error"]["code"] == "reference_orbit_pending"

    (fetched,) = world["api"].follow_once()["reference_orbits"]
    assert fetched["source"] == "satchecker" and fetched["norad_id"] == 99015
    assert "get-nearest" in world["stand_in"].urls()[-1]

    before = service.labels("REPLAY-0001")["reference_orbit"]
    assert before["source"] == "satchecker" and before["final"] is False

    other = deliver(world, "REPLAY-0001", published(seed=8))
    assert other.json()["error"]["code"] == "not_the_replayed_file"
    delivered = deliver(world, "REPLAY-0001", data)
    assert delivered.status_code == 200, delivered.text
    assert delivered.json()["summary"]["automated_verdict"] == "pass"

    report = json.loads(service.files[service.deliveries["REPLAY-0001"].report_sha256])
    assert report["simulated_input"] is False and "notice" not in report
    assert report["reference_orbit"]["source"]["kept_from"] == "satchecker"

    # Nothing here is SIMULATED, and the observations are a replay with their credits.
    labels = delivered.json()["summary"]["labels"]
    assert labels["request_simulated"] is False and labels["object"]["simulated"] is False
    assert labels["reference_orbit"]["source"] == "satchecker"
    assert labels["reference_orbit"]["final"] is True
    assert labels["observations"]["kind"] == "replayed"
    assert labels["observations"]["station"] == STATION
    assert labels["replay"]["observers"] == [EXAMPLE_ORCID]
    assert labels["replay"]["licence"] == "CC-BY-4.0"

    clock.now = T0 + timedelta(days=2)
    world["api"].follow_once()
    record = service.records["REPLAY-0001"]
    assert str(record.status) == "settled" and str(record.outcome) == "accepted"
    assert record.observer == STATION  # the replay station, paid on the testnet
    assert service.adapter.balance(STATION) == SPLIT.observer


def test_a_normal_request_needs_the_stations_profile_and_place(world):
    """The exemption is for replays only: the same file for a normal request needs its
    station's profile, which is its place (D-55)."""
    data = published()
    document = json.loads(replay_request(data, "REQ-0003", STATION))
    del document["replay"]
    document["format_version"] = "1.0"
    service, now = world["service"], world["clock"]
    service.create(
        json.dumps(document).encode(), REQUESTER, now(), delivery_deadline=T0 + timedelta(days=7)
    )
    open_and_fund(world, "REQ-0003")
    assert call(world, "POST", "/v1/requests/REQ-0003/reserve", STATION).status_code == 200
    refused = deliver(world, "REQ-0003", data)
    assert refused.json()["error"]["code"] == "profile_required"


def test_the_command_line_creates_a_replay(world, monkeypatch, capsys, tmp_path):
    path = tmp_path / "published.json"
    path.write_bytes(published())
    sent = []

    class Client:
        warnings = ()

        def __init__(self, api, key):
            pass

        def request(self, method, url, body=None, content_type=None, idempotency_key=None, **kw):
            sent.append(json.loads(body))
            response = call(world, method, url, "admin:maintainer", content=body)

            class Reply:
                replayed = False

                def json(self):
                    return response.json()

            return Reply()

    monkeypatch.setattr("orbit_watch.cli_client.ApiClient", Client)
    args = build_parser().parse_args(
        [
            "admin",
            "replay",
            str(path),
            "--request-id",
            "REPLAY-0009",
            "--requester",
            REQUESTER,
            "--station",
            STATION,
            "--api",
            "http://test",
            "--key",
            "k",
        ]
    )
    assert args.handler(args) == 0
    (body,) = sent
    assert body["requester"] == REQUESTER
    assert body["request"]["replay"]["observers"] == [EXAMPLE_ORCID]
    assert parse_utc(body["terms"]["delivery_deadline"]) > T0
    out = capsys.readouterr().out
    assert "REPLAY-0009" in out and EXAMPLE_ORCID in out and STATION in out

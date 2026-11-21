"""The follower fetches reference orbits (phase 5, step 5.4; decisions P5-02, P5-03, D-48).

No test here calls an outside service: CelesTrak and SatChecker are local stand-ins whose
answers are built from a SIMULATED object's elements, given to made-up objects 99001 to
99004 and 100001, which name no real satellite. No real element set is committed (D-06).
"""

import gzip
import io
import json
import urllib.error
import urllib.parse
from datetime import timedelta

import pytest
from helpers import catalog_bytes, packaged, policy_bytes, request_bytes
from sgp4 import exporter, omm
from sgp4.api import Satrec
from starlette.testclient import TestClient

from orbit_watch import lifecycle as lc
from orbit_watch import orbit_follower
from orbit_watch.api import create_app, keys
from orbit_watch.catalog import parse_catalog
from orbit_watch.cli import ServeError, build_parser, serve_app
from orbit_watch.formats import owjson
from orbit_watch.reviewers import ReviewerRegistry
from orbit_watch.satchecker import julian_date
from orbit_watch.service import ServiceError, VerificationContext, open_service
from orbit_watch.sim.simulator import load_profile, simulate
from orbit_watch.timeutil import parse_utc

REQUESTER = "requester:sim-cubesat-team"
STATION = "station:SIM-ESPOO"
SPLIT = lc.RewardSplit(observer=100, reviewer=10, platform_fee=5)
T0 = parse_utc("2026-11-01T12:00:00Z")
OBJECTS = (99001, 99002, 99003, 99004, 100001)
SIM = json.loads(catalog_bytes())["records"][0]  # SIM-CUBESAT-A


def made_up_record(norad):
    record = dict(SIM)
    record.update(NORAD_CAT_ID=norad, OBJECT_NAME=f"TEST OBJECT {norad}", OBJECT_ID="2026-999A")
    return record


def csv_of(*records) -> bytes:
    names = list(records[0])
    lines = [",".join(names)] + [",".join(str(r[k]) for k in names) for r in records]
    return ("\n".join(lines) + "\n").encode()


def tle_of(norad) -> tuple[str, str]:
    satrec = Satrec()
    omm.initialize(satrec, {k: str(v) for k, v in made_up_record(norad).items()})
    return exporter.export_tle(satrec)


class Answer(io.BytesIO):
    def __init__(self, body: bytes, status: int = 200, headers: dict | None = None):
        super().__init__(body)
        self.status = status
        self.headers = headers or {}

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


def http_error(status, text=b"No GP data found"):
    """An answer that is not 200."""

    def answer(request):
        raise urllib.error.HTTPError(request.full_url, status, "", {}, io.BytesIO(text))

    return answer


def no_answer(error):
    def answer(request):
        raise error

    return answer


class StandIn:
    """CelesTrak and SatChecker on this machine. Each call takes the next of ``answers``,
    a function of the request; without one, the source answers 200 with the object's
    sets: CelesTrak with compressed CSV, SatChecker with a TLE or an OMM."""

    def __init__(self, *answers):
        self.answers = list(answers)
        self.calls = []

    def __call__(self, request, timeout):
        self.calls.append(request)
        if self.answers:
            return self.answers.pop(0)(request)
        query = dict(urllib.parse.parse_qsl(urllib.parse.urlsplit(request.full_url).query))
        if "celestrak.org" in request.full_url:
            body = csv_of(made_up_record(int(query["CATNR"])))
            return Answer(gzip.compress(body), headers={"Content-Encoding": "gzip"})
        norad = int(query["id"])
        item = {"data_source": "a stand-in", "date_collected": "2026-11-01 01:00:00 UTC"}
        if "get-nearest-tle" in request.full_url:
            line1, line2 = tle_of(norad)
            item.update(satellite_name=f"TEST OBJECT {norad}", tle_line1=line1, tle_line2=line2)
        else:
            item.update(satellite_id=norad, orbital_elements=made_up_record(norad))
        return Answer(json.dumps([{"orbital_data": [item], "version": "1.9.0"}]).encode())

    def urls(self):
        return [call.full_url for call in self.calls]


def policy():
    document = json.loads(policy_bytes())
    document["allow"] += [{"norad_id": n, "name": f"TEST OBJECT {n}"} for n in OBJECTS]
    return json.dumps(document).encode()


class Clock:
    def __init__(self):
        self.now = T0

    def __call__(self):
        return self.now


@pytest.fixture
def world(database):
    registry = ReviewerRegistry.parse(packaged("reviewers.json"))
    context = VerificationContext(catalog=catalog_bytes(), policy=policy())
    service = open_service(database, registry, context)
    service.adapter.grant(REQUESTER, 10_000, key="budget")
    clock = Clock()
    with service.storage.db.transaction():
        admin = keys.create_key(service.storage.db, "admin:maintainer", "admin", clock())
        station = keys.create_key(service.storage.db, STATION, "station", clock())
    stand_in, pauses = StandIn(), []
    # The groups of the allow-list are tested in test_allowlist_service.py.
    fetcher = orbit_follower.Fetcher(opener=stand_in, sleep=pauses.append, groups=())
    app = create_app(service, clock=clock, wall_clock=clock, orbit_fetcher=fetcher)
    yield {
        "service": service,
        "api": app.state.api,
        "client": TestClient(app),
        "clock": clock,
        "stand_in": stand_in,
        "pauses": pauses,
        "admin": admin,
        "station": station,
        "database": database,
        "registry": registry,
        "context": context,
    }
    service.storage.close()


def open_request(world, number, norad, start="2026-11-01T15:00:00Z", end="2026-11-02T03:00:00Z"):
    service, now = world["service"], world["clock"]()
    rid = f"SIM-REQ-{number:04d}"
    document = request_bytes(request_id=rid, norad_id=norad, start=start, end=end)
    # A window in the past, as a replay's (step 5.5), still has a deadline to come.
    deadline = max(parse_utc(end), now) + timedelta(days=2)
    service.create(document, REQUESTER, now, delivery_deadline=deadline)
    service.open(rid, REQUESTER, now)
    return rid


def at(world, **delta):
    world["clock"].now = T0 + timedelta(**delta)


def follow(world):
    return world["api"].follow_once()["reference_orbits"]


def health(world):
    response = world["client"].get("/v1/health/reference-orbits")
    return response.status_code, response.json()


def resume(world, source="celestrak", key="admin", **body):
    return world["client"].post(
        "/v1/admin/reference-orbits/resume",
        content=json.dumps({"source": source, **body}),
        headers={"Authorization": f"Bearer {world[key]}", "Idempotency-Key": str(body) + source},
    )


# CelesTrak -------------------------------------------------------------------------------


def test_the_follower_fetches_an_open_requests_object_from_celestrak(world):
    rid = open_request(world, 2, 99001)
    assert follow(world) == [
        {"source": "celestrak", "norad_id": 99001, "kept": 1, "already_kept": 0}
    ]
    (call,) = world["stand_in"].calls
    assert call.full_url == ("https://celestrak.org/NORAD/elements/gp.php?CATNR=99001&FORMAT=csv")
    assert call.get_header("Accept-encoding") == "gzip"
    assert call.get_header("User-agent").startswith("orbit-watch/")
    (named,) = world["service"].reference_orbits(99001)
    assert named["source"] == "celestrak" and named["source_name"] == "CelesTrak"
    assert named["fetched_at"] == "2026-11-01T12:00:00.000Z"
    assert health(world) == (
        200,
        {
            "status": "ok",
            "sources": {
                "celestrak": {
                    "status": "ok",
                    "stopped_at": None,
                    "http_status": None,
                    "norad_id": None,
                    "reason": None,
                    "not_before": None,
                    "last_answer_at": "2026-11-01T12:00:00.000Z",
                    "resumed_at": None,
                },
                "satchecker": {
                    "status": "ok",
                    "stopped_at": None,
                    "http_status": None,
                    "norad_id": None,
                    "reason": None,
                    "not_before": None,
                    "last_answer_at": None,
                    "resumed_at": None,
                },
            },
            "objects_without_public_data": [],
        },
    )
    # A delivery is verified against it, and the report names it with its source.
    service = world["service"]
    service.fund(rid, REQUESTER, SPLIT, T0 + timedelta(minutes=2))
    service.reserve(rid, STATION, T0 + timedelta(minutes=5))
    observed = simulate(
        parse_catalog(csv_of(made_up_record(99001))),
        99001,
        load_profile("sim-cmos-gps"),
        parse_utc("2026-11-01T15:00:00Z"),
        parse_utc("2026-11-02T03:00:00Z"),
        seed=7,
    )
    service.deliver(
        rid, STATION, owjson.write_observation_set(observed).encode(), T0 + timedelta(hours=16)
    )
    report = json.loads(service.files[service.deliveries[rid].report_sha256])
    checks = {check["id"]: check for check in report["checks"]}
    assert checks["orbit_residuals"]["result"] == "pass"
    reference = report["reference_orbit"]
    assert reference["element_set_sha256"] == named["element_set_sha256"]
    assert reference["source"]["kept_from"] == "celestrak"
    assert reference["source"]["url"] == call.full_url


def test_once_per_update(world):
    open_request(world, 2, 99001)
    follow(world)
    at(world, hours=1, minutes=59)
    assert follow(world) == [] and len(world["stand_in"].calls) == 1
    at(world, hours=2)
    assert follow(world) == [
        {"source": "celestrak", "norad_id": 99001, "kept": 0, "already_kept": 1}
    ]
    assert len(world["stand_in"].calls) == 2


def test_only_open_requests_for_real_objects_on_the_allow_list(world):
    service = world["service"]
    service.create(request_bytes(), REQUESTER, T0)  # a SIMULATED object
    service.open("SIM-REQ-0001", REQUESTER, T0)
    with pytest.raises(ServiceError, match="not on the allow-list"):
        open_request(world, 2, 99999)  # refused when it is made (D-49)
    service.create(request_bytes(request_id="SIM-REQ-0003", norad_id=99002), REQUESTER, T0)
    open_request(world, 4, 99003, start="2026-11-04T00:00:00Z", end="2026-11-04T06:00:00Z")
    assert follow(world) == [] and world["stand_in"].calls == []
    # A day before its window starts, the object is fetched.
    at(world, days=1, hours=12)
    assert [entry["norad_id"] for entry in follow(world)] == [99003]


def test_a_few_objects_per_run_the_least_recently_asked_first(world):
    for number, norad in enumerate((99001, 99002, 99003, 99004), start=2):
        open_request(world, number, norad)
    assert [entry["norad_id"] for entry in follow(world)] == [99001, 99002, 99003]
    assert world["pauses"] == [orbit_follower.PAUSE_S] * 2
    at(world, minutes=15)
    assert [entry["norad_id"] for entry in follow(world)] == [99004]
    at(world, hours=2, minutes=15)
    assert [entry["norad_id"] for entry in follow(world)] == [99001, 99002, 99003]


def test_one_object_is_asked_for_once_whatever_its_requests(world):
    open_request(world, 2, 99001)
    open_request(world, 3, 99001)
    assert len(follow(world)) == 1 and len(world["stand_in"].calls) == 1


def test_another_process_does_not_ask_again(world):
    """A request is recorded as asked for just before it is made."""
    open_request(world, 2, 99001)
    db = world["service"].storage.db
    with db.transaction():
        (want,) = orbit_follower.plan(db, world["service"], T0, 3, groups=())
        assert orbit_follower.claim(db, want, T0)
    other = open_service(world["database"], world["registry"], world["context"])
    try:
        fetcher = orbit_follower.Fetcher(opener=world["stand_in"], sleep=lambda s: None, groups=())
        app = create_app(other, clock=world["clock"], wall_clock=world["clock"])
        app.state.api.orbit_fetcher = fetcher
        assert app.state.api.follow_once()["reference_orbits"] == []
    finally:
        other.storage.close()
    assert world["stand_in"].calls == []


# Stopping --------------------------------------------------------------------------------


@pytest.mark.parametrize(("status", "waits"), [(503, True), (500, True), (403, False)])
def test_an_answer_that_is_not_200_stops_until_a_person_resumes(world, status, waits):
    open_request(world, 2, 99001)
    open_request(world, 3, 99002)
    world["stand_in"].answers.append(http_error(status, b"Busy"))
    (entry,) = follow(world)
    assert entry["norad_id"] == 99001 and f"HTTP {status}" in entry["stopped"]
    assert len(world["stand_in"].calls) == 1  # 99002 was not asked for
    code, document = health(world)
    stopped = document["sources"]["celestrak"]
    assert code == 503 and document["status"] == "stopped"
    assert stopped["status"] == "stopped" and stopped["http_status"] == status
    assert stopped["norad_id"] == 99001 and "Busy" in stopped["reason"]
    assert stopped["stopped_at"] == "2026-11-01T12:00:00.000Z"
    assert stopped["not_before"] == ("2026-11-01T12:15:00.000Z" if waits else None)
    assert document["sources"]["satchecker"]["status"] == "ok"
    # Nothing more until a person resumes it.
    at(world, minutes=20)
    assert follow(world) == [] and len(world["stand_in"].calls) == 1
    at(world, minutes=5)
    response = resume(world)
    assert response.status_code == 200, response.text
    resumed = response.json()["sources"]["celestrak"]
    assert resumed["status"] == ("waiting" if waits else "ok")
    assert resumed["resumed_at"] == "2026-11-01T12:05:00.000Z" and resumed["reason"] is None
    assert health(world)[0] == 200
    if waits:  # at least 15 minutes after a 500 or a 503, even once resumed
        at(world, minutes=14)
        assert follow(world) == []
        at(world, minutes=15)
    assert [entry["norad_id"] for entry in follow(world)] == [99002]
    # The object that answered is asked for again at the next update.
    at(world, hours=2)
    assert [entry["norad_id"] for entry in follow(world)] == [99001]


def test_an_object_without_public_data_is_not_asked_for_again(world):
    open_request(world, 2, 99001)
    world["stand_in"].answers.append(http_error(404))
    (entry,) = follow(world)
    assert "do not ask for it again" in entry["stopped"]
    code, document = health(world)
    assert code == 503 and document["objects_without_public_data"] == [99001]
    assert document["sources"]["celestrak"]["not_before"] is None
    resume(world)
    at(world, hours=3)
    assert follow(world) == [] and len(world["stand_in"].calls) == 1
    response = resume(world, ask_again=[99001])
    assert response.json()["objects_without_public_data"] == []
    assert [entry["kept"] for entry in follow(world)] == [1]


@pytest.mark.parametrize(
    "failure",
    [urllib.error.URLError("connection refused"), TimeoutError("timed out")],
    ids=["unreachable", "timeout"],
)
def test_no_answer_stops_and_waits(world, failure):
    """No answer may mean that CelesTrak's firewall blocks the service's address."""
    open_request(world, 2, 99001)
    world["stand_in"].answers.append(no_answer(failure))
    (entry,) = follow(world)
    assert "CelesTrak" in entry["stopped"]
    stopped = health(world)[1]["sources"]["celestrak"]
    assert stopped["http_status"] is None and stopped["not_before"] == "2026-11-01T12:15:00.000Z"


@pytest.mark.parametrize(
    ("body", "reason"),
    [
        (csv_of(made_up_record(99002)), "holds the element sets of 99002"),
        (b"No GP data found", "did not return GP data"),
    ],
)
def test_an_answer_without_the_objects_sets_stops(world, body, reason):
    open_request(world, 2, 99001)
    world["stand_in"].answers.append(lambda request: Answer(body))
    (entry,) = follow(world)
    assert reason in entry["stopped"]
    stopped = health(world)[1]["sources"]["celestrak"]
    assert stopped["http_status"] == 200 and stopped["not_before"] is None
    assert world["service"].reference_orbits() == []


def test_resuming_is_for_administrators(world):
    assert resume(world, key="station").status_code == 403
    bad = resume(world, source="space-track")
    assert bad.status_code == 422 and bad.json()["error"]["code"] == "invalid_body"
    assert resume(world, ask_again=["99001"]).status_code == 422
    assert resume(world, source="satchecker").json()["sources"]["satchecker"]["resumed_at"]
    # Who resumed it is kept, not shown.
    assert "admin:maintainer" not in world["client"].get("/v1/health/reference-orbits").text


# SatChecker ------------------------------------------------------------------------------


def test_a_past_window_is_fetched_from_satchecker_once(world):
    open_request(world, 2, 99001, start="2026-10-01T00:00:00Z", end="2026-10-01T12:00:00Z")
    assert follow(world) == [
        {
            "source": "satchecker",
            "norad_id": 99001,
            "nearest": "2026-10-01T06:00:00.000Z",
            "kept": 1,
            "already_kept": 0,
        }
    ]
    middle = julian_date(parse_utc("2026-10-01T06:00:00Z"))
    assert world["stand_in"].urls() == [
        "https://satchecker.cps.iau.org/tools/get-nearest-tle/"
        f"?id=99001&id_type=catalog&epoch={middle:.8f}"
    ]
    (named,) = world["service"].reference_orbits(99001)
    assert named["source"] == "satchecker" and named["source_name"] == "IAU CPS SatChecker"
    listed = world["client"].get("/v1/public/reference-orbits").text
    assert tle_of(99001)[0] not in listed
    # The past does not change: asked for once.
    at(world, days=2)
    assert follow(world) == [] and len(world["stand_in"].calls) == 1
    assert health(world)[1]["sources"]["satchecker"]["last_answer_at"] == (
        "2026-11-01T12:00:00.000Z"
    )


def test_a_catalogue_number_too_large_for_a_tle_is_asked_for_as_omm(world):
    open_request(world, 2, 100001, start="2026-10-01T00:00:00Z", end="2026-10-01T12:00:00Z")
    assert [entry["kept"] for entry in follow(world)] == [1]
    assert "/get-nearest-omm/?id=100001&" in world["stand_in"].urls()[0]


def test_a_stored_set_near_the_window_is_enough(world):
    epoch = parse_utc(SIM["EPOCH"] + "Z")
    world["service"].keep_element_sets([made_up_record(99001)], "uploaded", T0)
    start, end = epoch - timedelta(hours=10), epoch - timedelta(hours=2)
    open_request(
        world, 2, 99001, start=f"{start:%Y-%m-%dT%H:%M:%SZ}", end=f"{end:%Y-%m-%dT%H:%M:%SZ}"
    )
    assert follow(world) == [] and world["stand_in"].calls == []


def test_satchecker_stops_on_its_own(world):
    open_request(world, 2, 99001, start="2026-10-01T00:00:00Z", end="2026-10-01T12:00:00Z")
    open_request(world, 3, 99002)
    world["stand_in"].answers.append(http_error(429, b"Too many requests"))
    entries = follow(world)
    assert [(e["source"], "stopped" in e) for e in entries] == [
        ("satchecker", True),
        ("celestrak", False),
    ]
    document = health(world)[1]
    assert document["sources"]["satchecker"]["status"] == "stopped"
    assert document["sources"]["celestrak"]["status"] == "ok"


# Switching it on -------------------------------------------------------------------------


def test_fetching_is_off_unless_switched_on(world):
    plain = create_app(world["service"], clock=world["clock"], wall_clock=world["clock"])
    open_request(world, 2, 99001)
    assert "reference_orbits" not in plain.state.api.follow_once()
    response = TestClient(plain).get("/v1/health/reference-orbits")
    assert response.status_code == 200 and response.json()["status"] == "off"
    assert world["stand_in"].calls == []

    def start(environ, argv=()):
        options = build_parser().parse_args(["serve", "--database", world["database"], *argv])
        app, service, lines = serve_app(options, environ=environ)
        service.storage.close()
        return app.state.api, lines

    api, lines = start({"ORBIT_WATCH_FETCH_ORBITS": "1"})
    assert api.orbit_fetcher is not None
    assert any("fetches the reference orbits" in line for line in lines)
    assert start({})[0].orbit_fetcher is None
    assert start({}, ["--fetch-orbits"])[0].orbit_fetcher is not None
    with pytest.raises(ServeError, match="FETCH_ORBITS"):
        start({"ORBIT_WATCH_FETCH_ORBITS": "maybe"})


def test_the_client_command_resumes(world, monkeypatch, capsys):
    from orbit_watch import cli_client
    from orbit_watch.client import ApiClient

    http = world["client"]

    class Reply:
        def __init__(self, response):
            self.response = response
            self.replayed = False

        def json(self):
            return self.response.json()

    def request(self, method, url, body=None, content_type=None, idempotency_key=None, **kw):
        headers = {"Authorization": f"Bearer {world['admin']}", "Content-Type": content_type}
        headers["Idempotency-Key"] = idempotency_key
        return Reply(http.request(method, url, content=body, headers=headers))

    monkeypatch.setattr(ApiClient, "request", request)
    args = build_parser().parse_args(
        ["admin", "resume-orbits", "--source", "celestrak", "--ask-again", "99001"]
    )
    args.api, args.key = "http://test", world["admin"]
    assert cli_client.cmd_admin_resume_orbits(args) == 0
    out = capsys.readouterr().out
    assert "celestrak: ok" in out and "asked for again: 99001" in out

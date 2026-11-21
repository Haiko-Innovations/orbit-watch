"""Real objects on the service's allow-list (phase 5, step 5.4; decisions P5-08, D-49).

No test here calls an outside service: CelesTrak is a local stand-in whose groups hold
made-up objects 99011 to 99017, which name no real satellite, with a SIMULATED object's
elements. No real element set is committed (D-06).
"""

import gzip
import hashlib
import json
from datetime import timedelta

import pytest
from helpers import catalog_bytes, packaged, policy_bytes, request_bytes
from starlette.testclient import TestClient
from test_orbit_follower import (
    REQUESTER,
    SPLIT,
    STATION,
    T0,
    Answer,
    Clock,
    StandIn,
    csv_of,
    http_error,
    made_up_record,
)

from orbit_watch import allowlist, orbit_follower
from orbit_watch.api import create_app, keys
from orbit_watch.catalog import parse_catalog
from orbit_watch.cli import build_parser
from orbit_watch.documents import TargetPolicy
from orbit_watch.formats import owjson
from orbit_watch.reviewers import ReviewerRegistry
from orbit_watch.service import ServiceError, VerificationContext, open_service
from orbit_watch.sim.simulator import load_profile, simulate
from orbit_watch.timeutil import parse_utc


def named(norad, name):
    record = made_up_record(norad)
    record["OBJECT_NAME"] = name
    return record


GROUPS = {
    "military": [named(99013, "TEST CUBESAT 3")],
    "radar": [named(99017, "TEST SPHERE")],
    "science": [named(99015, "TEST SCIENCE")],
    "education": [named(99016, "TEST SCHOOL")],
    "amateur": [named(99011, "TEST CUBESAT 1"), named(99014, "TEST AMATEUR")],
    "cubesat": [
        named(99011, "TEST CUBESAT 1"),
        named(99012, "USA 999"),
        named(99013, "TEST CUBESAT 3"),
    ],
}


def members(group):
    return {r["NORAD_CAT_ID"]: r["OBJECT_NAME"] for r in GROUPS[group]}


class GroupStandIn(StandIn):
    """CelesTrak with the groups above too."""

    def __call__(self, request, timeout):
        if "GROUP=" in request.full_url and not self.answers:
            self.calls.append(request)
            group = request.full_url.split("GROUP=")[1].split("&")[0]
            body = csv_of(*GROUPS[group])
            return Answer(gzip.compress(body), headers={"Content-Encoding": "gzip"})
        return super().__call__(request, timeout)


@pytest.fixture
def world(database):
    registry = ReviewerRegistry.parse(packaged("reviewers.json"))
    context = VerificationContext(catalog=catalog_bytes(), policy=policy_bytes())
    service = open_service(database, registry, context)
    service.adapter.grant(REQUESTER, 10_000, key="budget")
    clock = Clock()
    with service.storage.db.transaction():
        admin = keys.create_key(service.storage.db, "admin:maintainer", "admin", clock())
        station = keys.create_key(service.storage.db, STATION, "station", clock())
        requester = keys.create_key(service.storage.db, REQUESTER, "requester", clock())
    stand_in, pauses = GroupStandIn(), []
    fetcher = orbit_follower.Fetcher(opener=stand_in, sleep=pauses.append)
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
        "requester": requester,
        "database": database,
        "registry": registry,
        "context": context,
    }
    service.storage.close()


def at(world, **delta):
    world["clock"].now = T0 + timedelta(**delta)


def follow(world):
    return world["api"].follow_once()["reference_orbits"]


def fetch_all_groups(world):
    follow(world)
    at(world, minutes=15)
    follow(world)


def post(world, path, body, key="admin"):
    return world["client"].post(
        path,
        content=json.dumps(body),
        headers={
            "Authorization": f"Bearer {world[key]}",
            "Idempotency-Key": hashlib.sha256(
                (path + json.dumps(body, sort_keys=True) + key).encode()
            ).hexdigest(),
        },
    )


def allow(world, norad, name="TEST LARGE GROUP", reason="Its operator is a university."):
    return post(world, "/v1/admin/allowlist", {"norad_id": norad, "name": name, "reason": reason})


# How the list is built ---------------------------------------------------------------------


def test_the_list_is_built_from_celestraks_groups():
    groups = {group: members(group) for group in GROUPS}
    additions = {
        99020: {"name": "TEST LARGE GROUP", "reason": "A university's.", "added_at": "x"},
        99021: {"name": "STARSHIELD 1", "reason": "A wrong one.", "added_at": "x"},
        99013: {"name": "TEST CUBESAT 3", "reason": "In the military group.", "added_at": "x"},
        99011: {"name": "TEST CUBESAT 1", "reason": "Held by groups too.", "added_at": "x"},
    }
    targets = allowlist.combine(policy_bytes(), groups, additions)
    assert sorted(targets) == [99011, 99014, 99015, 99016, 99020, 339001, 339002, 339003]
    assert targets[339001].simulated and targets[339001].source == "service"
    assert targets[99014].public() == {
        "norad_id": 99014,
        "name": "TEST AMATEUR",
        "simulated": False,
        "source": "celestrak",
        "groups": ["amateur"],
    }
    assert targets[99011].groups == ("amateur", "cubesat")
    assert targets[99011].source == "administrator"
    assert targets[99020].public() == {
        "norad_id": 99020,
        "name": "TEST LARGE GROUP",
        "simulated": False,
        "source": "administrator",
        "reason": "A university's.",
        "added_at": "x",
    }
    # USA 999 matches a name pattern; 99013 is in the military group; 99017 is only in
    # the radar group.
    assert not {99012, 99013, 99017, 99021} & set(targets)


def test_the_groups_count_only_once_the_excluded_ones_are_fetched():
    included = {group: members(group) for group in allowlist.INCLUDED_GROUPS}
    assert sorted(allowlist.combine(policy_bytes(), included, {})) == [339001, 339002, 339003]
    included["military"] = members("military")
    assert 99014 not in allowlist.combine(policy_bytes(), included, {})  # radar is missing
    included["radar"] = members("radar")
    targets = allowlist.combine(policy_bytes(), included, {})
    assert 99014 in targets and 99013 not in targets


def test_the_patterns_apply_to_the_names_of_the_stored_sets():
    additions = {99020: {"name": "TEST LARGE GROUP", "reason": "Said so.", "added_at": "x"}}
    assert 99020 in allowlist.combine(policy_bytes(), {}, additions)
    names = {99020: ["NROL-999 DEB"]}
    assert 99020 not in allowlist.combine(policy_bytes(), {}, additions, names)


# The follower fetches the groups -------------------------------------------------------


def test_the_follower_fetches_the_groups_once_a_day(world):
    assert follow(world) == [
        {"source": "celestrak", "group": "military", "objects": 1},
        {"source": "celestrak", "group": "radar", "objects": 1},
        {"source": "celestrak", "group": "science", "objects": 1},
    ]
    assert world["stand_in"].urls() == [
        f"https://celestrak.org/NORAD/elements/gp.php?GROUP={group}&FORMAT=csv"
        for group in ("military", "radar", "science")
    ]
    assert world["pauses"] == [orbit_follower.PAUSE_S] * 2
    at(world, minutes=15)
    assert [entry["group"] for entry in follow(world)] == ["education", "amateur", "cubesat"]
    assert sorted(world["service"].targets()) == [
        99011,
        99014,
        99015,
        99016,
        339001,
        339002,
        339003,
    ]
    at(world, hours=23, minutes=59)
    assert follow(world) == []
    at(world, days=1)
    assert [entry["group"] for entry in follow(world)] == ["military", "radar", "science"]
    # Its element sets are not kept: only a request's object is fetched for those.
    assert world["service"].element_sets == {}


def test_requests_objects_come_before_the_groups(world):
    fetch_all_groups(world)
    at(world, days=1)
    service = world["service"]
    service.create(
        request_bytes(request_id="SIM-REQ-0002", norad_id=99011, simulated=False),
        REQUESTER,
        world["clock"](),
    )
    service.open("SIM-REQ-0002", REQUESTER, world["clock"]())
    assert [entry.get("norad_id", entry.get("group")) for entry in follow(world)] == [
        99011,
        "military",
        "radar",
    ]


def test_a_group_that_does_not_answer_200_stops_celestrak(world):
    world["stand_in"].answers = [http_error(503, b"busy")]
    (entry,) = follow(world)
    assert entry["group"] == "military" and "HTTP 503" in entry["stopped"]
    response = world["client"].get("/v1/health/reference-orbits")
    assert response.status_code == 503
    celestrak = response.json()["sources"]["celestrak"]
    assert celestrak["http_status"] == 503 and celestrak["norad_id"] is None
    assert "GROUP=military" in celestrak["reason"]
    assert len(world["stand_in"].calls) == 1
    at(world, hours=3)
    assert follow(world) == []  # stopped until a person resumes it
    assert post(
        world, "/v1/admin/reference-orbits/resume", {"source": "celestrak"}
    ).status_code == (200)
    # The excluded groups first, the one never asked for before the other.
    assert [entry["group"] for entry in follow(world)] == ["radar", "military", "science"]


def test_a_group_without_gp_data_stops_celestrak(world):
    world["stand_in"].answers = [lambda request: Answer(b"No GP data found")]
    (entry,) = follow(world)
    assert entry["group"] == "military" and "did not return GP data" in entry["stopped"]
    assert world["client"].get("/v1/health/reference-orbits").status_code == 503


def test_another_process_sees_the_groups(world):
    fetch_all_groups(world)
    other = open_service(world["database"], world["registry"], world["context"])
    try:
        assert 99014 in other.targets()
    finally:
        other.storage.close()


# The public list -------------------------------------------------------------------------


def test_the_list_says_why_each_object_is_on_it(world):
    fetch_all_groups(world)
    assert allow(world, 99020).status_code == 200
    listed = world["client"].get("/v1/public/targets").json()
    assert listed["simulated"] is False
    by_id = {target["norad_id"]: target for target in listed["targets"]}
    assert by_id[339001]["simulated"] is True and by_id[339001]["source"] == "service"
    assert by_id[99015] == {
        "norad_id": 99015,
        "name": "TEST SCIENCE",
        "simulated": False,
        "source": "celestrak",
        "groups": ["science"],
    }
    assert by_id[99020] == {
        "norad_id": 99020,
        "name": "TEST LARGE GROUP",
        "simulated": False,
        "source": "administrator",
        "reason": "Its operator is a university.",
        "added_at": "2026-11-01T12:15:00.000Z",
    }
    assert "admin:maintainer" not in json.dumps(listed)  # who added it is not shown
    assert [g["group"] for g in listed["groups"]] == list(allowlist.GROUPS)
    assert listed["groups"][0] == {
        "group": "military",
        "role": "exclude",
        "fetched_at": "2026-11-01T12:00:00.000Z",
        "objects": 1,
    }


# An administrator's additions ------------------------------------------------------------


def test_an_administrator_adds_an_object_with_a_public_reason(world):
    response = allow(world, 99020)
    assert response.status_code == 200
    assert response.json()["source"] == "administrator"
    assert 99020 in world["service"].targets()
    removed = post(world, "/v1/admin/allowlist/remove", {"norad_id": 99020})
    assert removed.json() == {"norad_id": 99020, "allowed": False}
    assert 99020 not in world["service"].targets()
    again = post(world, "/v1/admin/allowlist/remove", {"norad_id": 99020, "n": 2})
    assert again.status_code == 404 and again.json()["error"]["code"] == "unknown_target"


def test_an_addition_of_an_object_of_the_groups_keeps_it_there(world):
    fetch_all_groups(world)
    allow(world, 99015, name="TEST SCIENCE")
    removed = post(world, "/v1/admin/allowlist/remove", {"norad_id": 99015})
    assert removed.json() == {"norad_id": 99015, "allowed": True}


@pytest.mark.parametrize(
    ("norad", "name", "reason", "code", "status"),
    [
        (99021, "USA 345", "Said so.", "excluded_name", 422),
        (99013, "TEST CUBESAT 3", "Said so.", "excluded_group", 422),
        (339009, "SIM-RESTRICTED-PAYLOAD", "Said so.", "simulated_object", 422),
        (339001, "SIM-CUBESAT-A", "Said so.", "already_allowed", 409),
        (99020, " ", "Said so.", "invalid_name", 422),
        (99020, "TEST", "", "invalid_reason", 422),
        (99020, "TEST", "x" * 501, "invalid_reason", 422),
        (0, "TEST", "Said so.", "invalid_body", 422),
    ],
)
def test_an_addition_is_refused(world, norad, name, reason, code, status):
    fetch_all_groups(world)
    response = allow(world, norad, name=name, reason=reason)
    assert (response.status_code, response.json()["error"]["code"]) == (status, code)


def test_only_an_administrator_adds_objects(world):
    response = post(
        world,
        "/v1/admin/allowlist",
        {"norad_id": 99020, "name": "TEST", "reason": "Mine."},
        key="station",
    )
    assert response.status_code == 403
    assert 99020 not in world["service"].targets()


def test_the_client_commands_add_and_remove(world, monkeypatch, capsys):
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
    argv = ["admin", "allow", "--norad-id", "99020", "--name", "TEST", "--reason", "A school's."]
    args = build_parser().parse_args(argv)
    args.api, args.key = "http://test", world["admin"]
    assert cli_client.cmd_admin_allow(args) == 0
    assert "99020 TEST is on the allow-list: A school's." in capsys.readouterr().out
    args = build_parser().parse_args(["admin", "disallow", "--norad-id", "99020"])
    args.api, args.key = "http://test", world["admin"]
    assert cli_client.cmd_admin_disallow(args) == 0
    assert "99020: removed" in capsys.readouterr().out


# Requests and verification ---------------------------------------------------------------


def test_a_request_for_an_object_not_on_the_list_is_refused(world):
    service = world["service"]
    with pytest.raises(ServiceError, match="not on the allow-list") as refused:
        service.create(request_bytes(norad_id=99015), REQUESTER, T0)
    assert refused.value.code == "target_not_allowed"
    fetch_all_groups(world)
    service.create(request_bytes(norad_id=99015, simulated=False), REQUESTER, T0)
    with pytest.raises(ServiceError, match="not on the allow-list"):
        service.create(request_bytes(request_id="SIM-REQ-0002", norad_id=99012), REQUESTER, T0)


def test_a_real_object_is_verified_against_the_real_list(world):
    fetch_all_groups(world)
    service = world["service"]
    assert service.policy_for(339001) == policy_bytes()
    assert service.policy_for(None) == policy_bytes()
    real = TargetPolicy.parse(service.policy_for(99015))
    assert real.simulated is False
    assert sorted(real.allowed) == [99011, 99014, 99015, 99016]
    document = json.loads(service.policy_for(99015))
    assert {entry["group"] for entry in document["built_from"]} == set(allowlist.GROUPS)


def test_a_delivery_for_a_real_object_does_not_say_simulated(world):
    """A real request, real reference orbits and observations marked as real: nothing in
    its report is SIMULATED (P5-09)."""
    fetch_all_groups(world)
    service, now = world["service"], world["clock"]
    rid = "REQ-0002"
    document = request_bytes(
        request_id=rid,
        norad_id=99015,
        simulated=False,
        start="2026-11-01T15:00:00Z",
        end="2026-11-02T03:00:00Z",
    )
    service.create(document, REQUESTER, now())
    service.open(rid, REQUESTER, now())
    (entry,) = follow(world)
    assert entry == {"source": "celestrak", "norad_id": 99015, "kept": 1, "already_kept": 0}
    service.fund(rid, REQUESTER, SPLIT, now())
    service.reserve(rid, STATION, now())
    observed = simulate(
        parse_catalog(csv_of(made_up_record(99015))),
        99015,
        load_profile("sim-cmos-gps"),
        parse_utc("2026-11-01T15:00:00Z"),
        parse_utc("2026-11-02T03:00:00Z"),
        seed=7,
    )
    text = json.loads(owjson.write_observation_set(observed))
    text["simulated"] = False  # as a station's own observations would be
    service.deliver(rid, STATION, json.dumps(text).encode(), T0 + timedelta(hours=16))
    report = json.loads(service.files[service.deliveries[rid].report_sha256])
    checks = {check["id"]: check for check in report["checks"]}
    assert checks["target_allowed"]["result"] == "pass"
    assert report["simulated_input"] is False


def test_simulated_stations_observe_only_the_services_own_objects(world):
    fetch_all_groups(world)
    response = post(
        world,
        "/v1/admin/simulate",
        {
            "profile": "sim-cmos-gps",
            "norad_id": 99015,
            "start": "2026-11-01T15:00:00Z",
            "end": "2026-11-02T03:00:00Z",
        },
    )
    assert response.status_code == 404
    assert "own catalogue" in response.json()["error"]["message"]

"""The follower fetches operators' orbits from CelesTrak's SupGP (phase 6, step 6.2, third
part; decisions P6-03 and D-63).

The world is the allow-list tests': CelesTrak is a local stand-in whose groups and SupGP
sources hold made-up objects with a SIMULATED object's elements. No test calls an outside
service, and no real element set is committed (D-06).
"""

import gzip
import json
from datetime import timedelta

from helpers import request_bytes
from test_allowlist_service import (  # noqa: F401 - the world fixture
    REQUESTER,
    SOURCES,
    at,
    csv_of,
    fetch_all_groups,
    follow,
    post,
    sup,
    world,
)
from test_orbit_follower import Answer, http_error, made_up_record

ONEWEB = 99036  # in the source OneWeb-E only
SCHOOL = 99016  # in the group education and the source CPF
SCIENCE = 99015  # in the group science only
SUPGP_URL = "https://celestrak.org/NORAD/elements/supplemental/sup-gp.php"


def open_for(world, norad, number=2):  # noqa: F811
    service, now = world["service"], world["clock"]()
    rid = f"SIM-REQ-{number:04d}"
    service.create(request_bytes(request_id=rid, norad_id=norad, simulated=False), REQUESTER, now)
    service.open(rid, REQUESTER, now)
    return rid


def gp_answer(norad):
    def answer(request):
        body = gzip.compress(csv_of(made_up_record(norad)))
        return Answer(body, headers={"Content-Encoding": "gzip"})

    return answer


def health(world):  # noqa: F811
    response = world["client"].get("/v1/health/reference-orbits")
    return response.status_code, response.json()


def test_an_operator_tracked_objects_orbit_is_fetched_after_its_gp_data(world):  # noqa: F811
    fetch_all_groups(world)
    open_for(world, ONEWEB)
    calls = len(world["stand_in"].calls)
    assert follow(world) == [
        {"source": "celestrak", "norad_id": ONEWEB, "kept": 1, "already_kept": 0},
        {"source": "celestrak", "norad_id": ONEWEB, "data": "supgp", "kept": 1, "already_kept": 0},
    ]
    assert world["stand_in"].urls()[calls:] == [
        f"https://celestrak.org/NORAD/elements/gp.php?CATNR={ONEWEB}&FORMAT=csv",
        f"{SUPGP_URL}?CATNR={ONEWEB}&FORMAT=csv",
    ]
    service = world["service"]
    listed = world["client"].get(f"/v1/public/reference-orbits?norad_id={ONEWEB}").json()
    names = sorted((s["source_name"], s.get("data_source")) for s in listed["element_sets"])
    assert names == [("CelesTrak", None), ("the operator's orbit via CelesTrak", "OneWeb-E")]
    kept = [s for s in service.element_sets[ONEWEB] if s.operator_orbit]
    assert kept[0].record["source"]["service"] == "CelesTrak SupGP"
    assert kept[0].record["source"]["data_source"] == "OneWeb-E"
    assert kept[0].record["source"]["rms_km"] == 0.2
    assert "TLE_LINE1" not in json.dumps(listed)  # names, never elements


def test_verification_still_uses_the_gp_set(world):  # noqa: F811
    fetch_all_groups(world)
    rid = open_for(world, ONEWEB)
    follow(world)
    service = world["service"]
    assert len(service.element_sets[ONEWEB]) == 2
    assert [s.operator_orbit for s in service.verifying_sets(ONEWEB)] == [False]
    catalog = json.loads(service.catalog_for([ONEWEB]))
    assert [r["source"]["service"] for r in catalog["records"]] == ["CelesTrak"]
    label = service.labels(rid)["reference_orbit"]
    assert label["source_name"] == "CelesTrak" and label["final"] is False


def test_both_are_asked_for_again_two_hours_later(world):  # noqa: F811
    fetch_all_groups(world)
    open_for(world, SCHOOL)
    follow(world)
    at(world, hours=1, minutes=45)
    assert follow(world) == []
    at(world, hours=2, minutes=45)
    entries = follow(world)
    assert [e.get("data") for e in entries] == [None, "supgp"]
    assert entries[1]["already_kept"] == 1


def test_not_for_an_object_without_an_operators_orbit(world):  # noqa: F811
    fetch_all_groups(world)
    open_for(world, SCIENCE)
    assert [e.get("data") for e in follow(world)] == [None]


def test_not_for_a_window_that_has_ended(world):  # noqa: F811
    fetch_all_groups(world)
    at(world, days=2)
    for minutes in (0, 15, 30, 45):  # the groups and sources again
        at(world, days=2, minutes=minutes)
        follow(world)
    service, now = world["service"], world["clock"]()
    document = request_bytes(request_id="SIM-REQ-0003", norad_id=ONEWEB, simulated=False)
    service.create(document, REQUESTER, now, delivery_deadline=now + timedelta(days=2))
    service.open("SIM-REQ-0003", REQUESTER, now)
    (entry,) = follow(world)
    assert entry["source"] == "satchecker"  # a past window keeps SatChecker's GP (P6-03)


def test_only_the_sets_of_an_operators_orbit_are_kept(world):  # noqa: F811
    fetch_all_groups(world)
    open_for(world, ONEWEB)
    rows = [sup(ONEWEB, "TEST ONEWEB 1", "OneWeb-E"), sup(ONEWEB, "TEST ONEWEB 1", "OneWeb-TLE")]
    rows[1]["MEAN_ANOMALY"] = float(rows[1]["MEAN_ANOMALY"]) + 1

    def supgp_answer(request):
        return Answer(gzip.compress(csv_of(*rows)), headers={"Content-Encoding": "gzip"})

    world["stand_in"].answers = [gp_answer(ONEWEB), supgp_answer]
    assert follow(world)[1]["kept"] == 1
    kept = [s.data_source for s in world["service"].element_sets[ONEWEB]]
    assert kept == [None, "OneWeb-E"]


def test_an_answer_that_is_not_200_stops_celestrak(world):  # noqa: F811
    fetch_all_groups(world)
    open_for(world, ONEWEB)
    world["stand_in"].answers = [gp_answer(ONEWEB), http_error(503, b"Busy")]
    entries = follow(world)
    assert entries[1]["data"] == "supgp" and "HTTP 503" in entries[1]["stopped"]
    status, document = health(world)
    celestrak = document["sources"]["celestrak"]
    assert status == 503 and celestrak["norad_id"] == ONEWEB
    assert f"sup-gp.php?CATNR={ONEWEB}" in celestrak["reason"]


def test_an_object_without_supgp_data_is_listed_and_not_asked_for_again(world):  # noqa: F811
    fetch_all_groups(world)
    open_for(world, ONEWEB)
    world["stand_in"].answers = [gp_answer(ONEWEB), http_error(404, b"No SupGP data found")]
    follow(world)
    status, document = health(world)
    assert status == 503
    assert document["objects_without_supgp_data"] == [ONEWEB]
    assert document["objects_without_public_data"] == []
    resumed = post(world, "/v1/admin/reference-orbits/resume", {"source": "celestrak"})
    assert resumed.status_code == 200
    at(world, hours=3)
    assert [e.get("data") for e in follow(world)] == [None]  # GP only
    # Asked again once a person says so, as for GP data.
    again = {"source": "celestrak", "ask_again": [ONEWEB]}
    assert post(world, "/v1/admin/reference-orbits/resume", again).status_code == 200
    at(world, hours=5)
    assert [e.get("data") for e in follow(world)] == [None, "supgp"]


def test_an_answer_with_another_objects_sets_stops_celestrak(world):  # noqa: F811
    fetch_all_groups(world)
    open_for(world, ONEWEB)
    other = csv_of(*SOURCES["Kuiper-E"])

    def wrong(request):
        return Answer(gzip.compress(other), headers={"Content-Encoding": "gzip"})

    world["stand_in"].answers = [gp_answer(ONEWEB), wrong]
    entries = follow(world)
    assert "holds the element sets of 99035" in entries[1]["stopped"]
    assert health(world)[0] == 503

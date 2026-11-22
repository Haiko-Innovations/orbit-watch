"""Simulated stations on real objects (phase 5, step 5.5, first part; decisions P5-09, D-50).

A request for a real object may be SIMULATED: simulated stations then observe the real
object along its stored element set, and their observations are verified against the same
set. A request for a SIMULATED object must be SIMULATED, and a real request takes no
SIMULATED observations. No test here calls an outside service: CelesTrak is the local
stand-in of the allow-list tests, whose objects name no real satellite.
"""

import json
from datetime import timedelta

import pytest
from helpers import packaged, request_bytes
from test_allowlist_service import at, fetch_all_groups, follow, post, world  # noqa: F401
from test_orbit_follower import REQUESTER, SPLIT, STATION, T0, made_up_record

from orbit_watch.catalog import parse_catalog
from orbit_watch.service import ServiceError
from orbit_watch.timeutil import parse_utc

START, END = "2026-11-01T15:00:00Z", "2026-11-02T03:00:00Z"
PROFILE = f"/v1/stations/{STATION}/profile"


def station_profile(world):  # noqa: F811
    """The station's own profile: the SIMULATED template whose station is SIM-ESPOO."""
    response = world["client"].put(
        PROFILE,
        content=json.dumps(
            {"profile": json.loads(packaged("stations/sim-cmos-gps.json")), "place": "exact"}
        ),
        headers={"Authorization": f"Bearer {world['station']}", "Idempotency-Key": "profile"},
    )
    assert response.status_code == 200, response.text


def reserved(world, rid, *, simulated, fetch=True):  # noqa: F811
    """A request for the real object 99015, reserved by the station; its element set
    fetched by the follower unless ``fetch`` is false."""
    service, now = world["service"], world["clock"]
    document = request_bytes(
        request_id=rid, norad_id=99015, simulated=simulated, start=START, end=END
    )
    service.create(document, REQUESTER, now())
    service.open(rid, REQUESTER, now())
    if fetch:
        assert [entry["norad_id"] for entry in follow(world)] == [99015]
    service.fund(rid, REQUESTER, SPLIT, now())
    service.reserve(rid, STATION, now())


def simulate(world, rid):  # noqa: F811
    return post(world, f"/v1/requests/{rid}/simulate", {}, key="station")


def admin_simulate(world, norad, start=START, end=END):  # noqa: F811
    body = {"profile": "sim-cmos-gps", "norad_id": norad, "start": start, "end": end}
    return post(world, "/v1/admin/simulate", body)


def test_a_request_for_a_simulated_object_must_be_simulated(world):  # noqa: F811
    service = world["service"]
    with pytest.raises(ServiceError, match="must be marked as SIMULATED") as refused:
        service.create(request_bytes(norad_id=339001, simulated=False), REQUESTER, T0)
    assert refused.value.code == "simulated_target"
    service.create(request_bytes(norad_id=339001), REQUESTER, T0)  # SIMULATED: as before


def test_a_simulated_station_observes_a_real_object(world):  # noqa: F811
    """The whole chain with a real orbit and no real observer: the observations and the
    report say SIMULATED, and the report names the real set it used."""
    fetch_all_groups(world)
    station_profile(world)
    rid = "SIM-REQ-0050"
    reserved(world, rid, simulated=True)

    made = simulate(world, rid)
    assert made.status_code == 200, made.text
    document = json.loads(made.json()["observations"])
    assert document["simulated"] is True and document["target"]["norad_id"] == 99015
    assert len(document["observations"]) >= 6

    service = world["service"]
    record = service.deliver(
        rid, STATION, made.json()["observations"].encode(), T0 + timedelta(hours=16)
    )
    report = json.loads(service.files[service.deliveries[rid].report_sha256])
    checks = {check["id"]: check for check in report["checks"]}
    assert report["verdict"] == "pass", report["summary"]
    assert record.status.value == "challenge_period"
    assert report["simulated_input"] is True and "SIMULATED" in report["notice"]
    assert checks["simulation_label"]["result"] == "pass"
    assert checks["target_allowed"]["result"] == "pass"
    reference = report["reference_orbit"]
    assert reference["source"]["kept_from"] == "celestrak"
    assert reference["epoch"].startswith("2026-11-01T00:00:00")

    # Each part says what it is (P5-09, D-52): a real object and orbit, SIMULATED
    # observations, and so a SIMULATED request.
    labels = service.labels(rid)
    assert labels["request_simulated"] is True
    assert labels["object"]["simulated"] is False and labels["object"]["source"] == "celestrak"
    assert labels["object"]["groups"] == ["science"]
    assert labels["reference_orbit"]["source"] == "celestrak"
    assert labels["reference_orbit"]["simulated"] is False and labels["reference_orbit"]["final"]
    assert labels["observations"] == {
        "kind": "simulated",
        "station": STATION,
        "sha256": service.deliveries[rid].observations_sha256,
    }


def test_a_real_request_takes_no_simulated_observations(world):  # noqa: F811
    fetch_all_groups(world)
    station_profile(world)
    reserved(world, "REQ-0051", simulated=False)
    refused = simulate(world, "REQ-0051")
    assert refused.status_code == 409
    assert refused.json()["error"]["code"] == "real_request"


def test_a_real_object_without_an_element_set_cannot_be_simulated(world):  # noqa: F811
    fetch_all_groups(world)
    station_profile(world)
    reserved(world, "SIM-REQ-0052", simulated=True, fetch=False)
    refused = simulate(world, "SIM-REQ-0052")
    assert refused.status_code == 409
    assert refused.json()["error"]["code"] == "no_reference_orbit"
    assert "follower fetches it" in refused.json()["error"]["message"]
    assert admin_simulate(world, 99015).json()["error"]["code"] == "no_reference_orbit"

    assert [entry["norad_id"] for entry in follow(world)] == [99015]
    assert simulate(world, "SIM-REQ-0052").status_code == 200


def test_an_administrator_simulates_a_real_object(world):  # noqa: F811
    fetch_all_groups(world)
    reserved(world, "SIM-REQ-0053", simulated=True)
    made = admin_simulate(world, 99015)
    assert made.status_code == 200, made.text
    assert made.json()["simulated"] is True and made.json()["count"] > 0
    assert json.loads(made.json()["observations"])["target"]["norad_id"] == 99015
    # Far from every stored set, the age limit would make verification inconclusive.
    far = admin_simulate(world, 99015, "2026-11-20T00:00:00Z", "2026-11-20T12:00:00Z")
    assert far.status_code == 409
    assert "within 7 days" in far.json()["error"]["message"]
    # Not on the list: refused as before.
    assert admin_simulate(world, 99012).status_code == 404
    # The service's own objects: from its own catalogue, as before.
    assert admin_simulate(world, 339001).status_code == 200


def test_the_simulation_uses_the_set_nearest_the_window(world):  # noqa: F811
    """With several stored sets, the simulator follows the one verification will pick."""
    fetch_all_groups(world)
    service = world["service"]
    sets = []
    for epoch in ("2026-10-29T00:00:00.000000", "2026-11-01T18:00:00.000000"):
        record = made_up_record(99015)
        record["EPOCH"] = epoch
        sets.append(record)
    service.keep_element_sets(sets, "uploaded", T0, uploaded_by="admin:maintainer")
    catalogue = parse_catalog(service.simulation_catalog(99015, parse_utc(START), parse_utc(END)))
    assert catalogue.simulated is False
    (only,) = catalogue.element_sets(99015)
    assert only.epoch == parse_utc("2026-11-01T18:00:00Z")
    # The service's own objects keep its own catalogue.
    assert service.simulation_catalog(339001, parse_utc(START), parse_utc(END)) == (
        world["context"].catalog
    )
    at(world, hours=1)  # the clock is not used: nothing is fetched

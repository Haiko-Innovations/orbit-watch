"""Method 3.0.0 (phase 6, step 6.3, part 2; decisions D-67 and D-68): the orbit term by the
set's kind, orbit class and age, the ellipse along and across the apparent motion, and
method 2.1.0 still run for the requests whose terms name it. Every element set here is
SIMULATED.
"""

import json
from dataclasses import replace

import pytest
from test_reference_accuracy import truth_pair
from test_service import DELIVERY, STATION, datasets, funded_and_reserved, make_service  # noqa: F401

from orbit_watch import cli
from orbit_watch import reference_accuracy as ra
from orbit_watch.canonical import dumps_pretty
from orbit_watch.geometry import orbit_projection, residuals
from orbit_watch.verify import orbit_terms
from orbit_watch.verify.engine import (
    METHOD_VERSION,
    METHOD_VERSIONS,
    UsageError,
    VerificationInput,
    verify,
)

LEO = {"MEAN_MOTION": "15.2", "ECCENTRICITY": "0.001"}
MEO = {"MEAN_MOTION": "2.0", "ECCENTRICITY": "0.01"}
GEO = {"MEAN_MOTION": "1.0027", "ECCENTRICITY": "0.0002"}
HEO = {"MEAN_MOTION": "2.0", "ECCENTRICITY": "0.7"}


def ages(low, high):
    return f"{low}{orbit_terms.DASH}{high}"


def term(record, age, simulated=False):
    found = orbit_terms.term_for(record, age, simulated=simulated)
    return None if found is None else (found.kind, found.age_days, found.in_track_km)


# The orbit term ---------------------------------------------------------------------------


def test_a_gp_set_in_low_orbits_grows_along_the_track_and_stops_at_three_days():
    assert term(LEO, 0.2) == ("gp", ages(0, 1), 4.0)
    assert term(LEO, 1.5) == ("gp", ages(1, 2), 9.0)
    assert term(LEO, 3.0) == ("gp", ages(2, 3), 16.0)
    assert term(LEO, 3.01) is None
    found = orbit_terms.term_for(LEO, 2.5)
    assert (found.radial_km, found.cross_track_km) == (0.5, 0.5)


def test_an_operators_orbit_for_a_day_then_as_gp():
    record = {**LEO, "DATA_SOURCE": "OneWeb-E"}
    assert term(record, 0.9) == ("operator", ages(0, 1), 2.0)
    assert term(record, 1.5) == ("gp", ages(1, 2), 9.0)  # past its day it ages like GP
    assert term({**LEO, "DATA_SOURCE": "SpaceX-SV"}, 0.5) == ("operator", ages(0, 1), 2.0)
    assert term({**LEO, "DATA_SOURCE": "GPS-A"}, 0.5) == ("gp", ages(0, 1), 4.0)  # not one


def test_a_laser_ranging_prediction_for_three_days():
    assert term({**MEO, "DATA_SOURCE": "CPF"}, 2.5) == ("laser-ranging", ages(0, 3), 1.0)
    assert term({**GEO, "DATA_SOURCE": "CPF"}, 2.9) == ("laser-ranging", ages(0, 3), 3.0)
    assert term({**GEO, "DATA_SOURCE": "CPF"}, 3.5) == ("gp", ages(3, 5), 12.0)


def test_medium_and_geosynchronous_orbits_have_their_own_ages():
    assert term(MEO, 6.0) == ("gp", ages(3, 7), 7.0)
    assert term(MEO, 7.5) is None
    assert term(GEO, 4.0) == ("gp", ages(3, 5), 12.0)
    assert term(GEO, 5.5) is None
    assert orbit_terms.oldest_age(GEO) == 5.0


def test_orbits_not_measured_keep_method_2_1_0s_values():
    found = orbit_terms.term_for(HEO, 6.0)
    assert found.kind == "not-measured"
    assert (found.radial_km, found.in_track_km, found.cross_track_km) == (5.0, 5.0, 5.0)
    assert orbit_terms.term_for(HEO, 7.5) is None


def test_a_simulated_set_keeps_its_last_row_past_its_ages():
    assert term(LEO, 17.0) is None
    assert term(LEO, 17.0, simulated=True) == ("gp", ages(2, 3), 16.0)


def test_the_table_names_every_row():
    rows = orbit_terms.table()
    assert len(rows) == sum(len(v) for v in orbit_terms.TERMS.values())
    assert {r["kind"] for r in rows} == set(orbit_terms.KINDS)


# The ellipse ------------------------------------------------------------------------------


def test_a_kilometre_shows_on_the_sky_as_the_station_sees_it():
    pair = truth_pair()
    element_set = pair.truth.sup.element_set
    track = ra.synthetic_track(element_set, "SIM", seed=1)
    res = residuals(element_set.satellite, track.station, track.observations)
    projection = orbit_projection(element_set.satellite, track.station, track.observations, res)
    middle = ra.TRACK_POINTS // 2
    expected = 206264.8 / res.range_km[middle]  # arcseconds per kilometre, overhead
    along, cross = projection[middle]
    assert along[1] == pytest.approx(expected, rel=0.01)  # in track: along the motion
    assert cross[2] == pytest.approx(expected, rel=0.01)  # cross track: across it
    assert abs(along[0]) < 0.01 * expected and abs(cross[0]) < 0.01 * expected  # radial
    assert abs(along[2]) < 0.1 * expected and abs(cross[1]) < 0.1 * expected


def test_half_a_second_fails_against_an_operators_orbit_and_passes_against_gp():
    # A track a quarter second late is 2 km along the track: within an operator's orbit's
    # 2 km only just, and within a GP set's 4 km. Half a second is 3.8 km.
    row = ra.time_shifts([truth_pair()])
    by_method = {(r["method"], r["reference"]): r["results"] for r in row}
    shifts = list(ra.SHIFTS_S)
    operator = dict(zip(shifts, by_method[("3.0.0", "operator")], strict=True))
    assert operator[0.0] == operator[0.25] == "pass" and operator[0.5] == "fail"
    old = dict(zip(shifts, by_method[("2.1.0", "operator")], strict=True))
    assert old[0.5] == "pass" and old[1.0] == "fail"  # D-46


# Both methods -----------------------------------------------------------------------------


def demo_input(examples_dir, name, previous=()):
    base = examples_dir / "simulated"
    return VerificationInput(
        request=(base / "request.json").read_bytes(),
        observations=(base / "datasets" / name / "observations.json").read_bytes(),
        observations_format="json",
        catalog=(base / "catalog.json").read_bytes(),
        policy=(base / "target-policy.json").read_bytes(),
        previous=[(base / "datasets" / p / "observations.json").read_bytes() for p in previous],
        declared_sha256=json.loads((base / "datasets" / name / "delivery.json").read_bytes())[
            "observations"
        ]["sha256"],
    )


@pytest.mark.parametrize(
    ("name", "previous"), [("acceptable", ()), ("wrong_target", ("acceptable",))]
)
def test_a_method_2_1_0_report_is_made_again_byte_for_byte(examples_dir, repo_root, name, previous):
    committed = (repo_root / "core/tests/data/method-2.1.0" / f"{name}-report.json").read_bytes()
    inputs = replace(demo_input(examples_dir, name, previous), method_version="2.1.0")
    report = verify(inputs)
    expected = json.loads(committed)
    report["software"] = expected["software"]  # the versions of the day it was made
    assert dumps_pretty(report, sort_keys=False).encode("utf-8") == committed


def test_method_3_0_0_is_the_default_and_names_its_orbit_term(examples_dir):
    report = verify(demo_input(examples_dir, "acceptable"))
    assert report["method"]["version"] == METHOD_VERSION == "3.0.0"
    assert report["report_format_version"] == "1.2"
    assert report["method"]["orbit_terms"] == orbit_terms.table()
    assert "reference_position_error_km" not in report["method"]["parameters"]
    check = next(c for c in report["checks"] if c["id"] == "orbit_residuals")
    assert check["details"]["orbit_term"]["kind"] == "gp"
    first = check["details"]["per_observation"][0]
    assert first["cross_track_limit_arcsec"] < first["along_track_limit_arcsec"]
    assert 0 <= first["normalised_residual"] <= 1 and first["within_limit"]


def test_an_unknown_method_is_a_usage_error(examples_dir):
    with pytest.raises(UsageError, match=r"unknown method version '9\.9\.9'"):
        verify(replace(demo_input(examples_dir, "acceptable"), method_version="9.9.9"))


def test_the_command_line_offers_the_engines_methods():
    assert cli.VERIFICATION_METHODS == METHOD_VERSIONS
    assert cli.VERIFICATION_METHODS[-1] == METHOD_VERSION


def delivered_method(service, rid):
    report = json.loads(service.files[service.deliveries[rid].report_sha256])
    return report["method"]["version"]


def test_the_service_verifies_with_the_method_the_terms_name(datasets):  # noqa: F811
    service, _ = make_service()
    rid = funded_and_reserved(service)
    service.deliver(rid, STATION, datasets["acceptable"], DELIVERY)
    assert delivered_method(service, rid) == "2.1.0"  # the terms' default, for now

    service, _ = make_service()
    rid = funded_and_reserved(service)
    record = service.records[rid]
    terms = replace(record.terms, verification_method="orbit-watch-automated-verification 3.0.0")
    service.records[rid] = replace(record, terms=terms)
    service.deliver(rid, STATION, datasets["acceptable"], DELIVERY)
    assert delivered_method(service, rid) == "3.0.0"

"""Orbit determination in the core (phase 6, step 6.4, part 1; decision D-70): the fit's
elements, its recovery of a known orbit, B* over long arcs only, outliers, its inputs'
names, and the committed example repeated byte for byte. Every orbit and observation here
is SIMULATED.
"""

import json
import math
from dataclasses import replace
from datetime import timedelta

import numpy as np
import pytest
from helpers import catalog_bytes, real_catalog_bytes

from orbit_watch import cli, orbit_fit
from orbit_watch.catalog import parse_catalog
from orbit_watch.formats import owjson
from orbit_watch.sim import fit_example
from orbit_watch.sim.simulator import load_profile, simulate

NORAD = fit_example.NORAD_ID


def truth():
    return parse_catalog(catalog_bytes()).element_sets(NORAD)[0]


def start():
    return parse_catalog(fit_example.start_catalog()).element_sets(NORAD)[0]


def observed(stations=fit_example.STATIONS, days=1.0, seed=1):
    catalog = parse_catalog(catalog_bytes())
    profile = load_profile("sim-cmos-gps")
    epoch = truth().epoch
    sets = []
    for k, station in enumerate(stations):
        found = simulate(
            catalog,
            NORAD,
            replace(profile, station=station),
            epoch,
            epoch + timedelta(days=days),
            seed=seed + k,
        )
        if found.observations:
            sets.append(found)
    return sets


def off_truth_km(document, when):
    """The fitted position minus the true one, radially, along the track and across it."""
    true = truth().satellite
    p, v = orbit_fit._positions(true, [when])
    q, _ = orbit_fit._positions(orbit_fit.satellite_of(document["result"]["omm"]), [when])
    return orbit_fit._rtn(p[0], v[0]) @ (q[0] - p[0])


def last_time(sets):
    return max(o.time for s in sets for o in s.observations)


# The elements -----------------------------------------------------------------------------


def test_the_equinoctial_elements_give_back_the_set():
    record = truth().record
    back = orbit_fit.to_record(record, orbit_fit.to_equinoctial(record))
    for key in ("MEAN_MOTION", "ECCENTRICITY", "INCLINATION", "BSTAR"):
        assert back[key] == pytest.approx(float(record[key]), abs=1e-12)
    for key in ("RA_OF_ASC_NODE", "ARG_OF_PERICENTER", "MEAN_ANOMALY"):
        difference = (back[key] - float(record[key]) + 180) % 360 - 180
        assert abs(difference) < 1e-9


def test_a_circular_orbit_has_well_defined_elements():
    record = {**truth().record, "ECCENTRICITY": 0.0, "ARG_OF_PERICENTER": 0.0}
    x = orbit_fit.to_equinoctial(record)
    assert x[1] == 0.0 and x[2] == 0.0
    back = orbit_fit.to_record(record, x)
    assert back["ECCENTRICITY"] == 0.0
    # Without a perigee, only the mean longitude is defined: it is kept.
    longitude = back["RA_OF_ASC_NODE"] + back["ARG_OF_PERICENTER"] + back["MEAN_ANOMALY"]
    expected = float(record["RA_OF_ASC_NODE"]) + float(record["MEAN_ANOMALY"])
    assert abs((longitude - expected + 180) % 360 - 180) < 1e-9


# The fit ----------------------------------------------------------------------------------


def test_the_fit_finds_the_true_orbit_from_a_set_4_km_off():
    sets = observed()
    document = orbit_fit.fit(start(), sets, simulated_catalog=True)
    result = document["result"]
    assert result["converged"] and result["used"] == result["observations"]
    when = last_time(sets)
    moved = result["difference_from_start_set_km_at_last_observation"]
    assert abs(moved["in_track"]) > 4.0  # the start set was this far off
    assert np.all(np.abs(off_truth_km(document, when)) < 0.1)
    # A day later the fit is still within a few hundred metres of the truth.
    assert np.all(np.abs(off_truth_km(document, when + timedelta(days=1))) < 0.3)
    sigma = result["position_sigma_km_at_last_observation"]
    assert 0 < sigma["in_track"] < 0.2
    assert 0.5 < result["rms_normalised_residual"] < 1.5  # residuals as declared


def test_b_star_is_fitted_over_two_days_and_kept_over_less():
    short = orbit_fit.fit(start(), observed(days=1.0), simulated_catalog=True)
    assert "bstar" not in short["method"]["fitted"]
    assert short["result"]["omm"]["BSTAR"] == pytest.approx(float(start().record["BSTAR"]))
    long = orbit_fit.fit(start(), observed(days=3.0), simulated_catalog=True)
    assert long["result"]["span_days"] >= 2.0
    assert long["method"]["fitted"][-1] == "bstar"
    covariance = long["result"]["covariance"]
    assert len(covariance["standard_deviations"]) == len(covariance["correlations"]) == 7
    assert all(row[k] == 1.0 for k, row in enumerate(covariance["correlations"]))


def test_the_start_set_is_a_measurement_at_its_epoch_and_each_track():
    sets = observed()
    document = orbit_fit.fit(start(), sets, simulated_catalog=True)
    terms = document["result"]["start_set_terms"]
    times = [o.time for s in sets for o in s.observations]
    middles = orbit_fit.track_middles(times, orbit_fit.PARAMETERS["track_gap_s"])
    assert terms[0]["time"] == "2026-11-01T00:00:00.000Z"  # the epoch
    assert len(terms) == 1 + len(middles)
    assert {t["kind"] for t in terms} == {"gp"} and terms[0]["in_track_km"] == 4.0


def test_one_station_alone_still_fits():
    sets = observed(stations=fit_example.STATIONS[:1])
    document = orbit_fit.fit(start(), sets, simulated_catalog=True)
    assert document["result"]["converged"]
    assert np.all(np.abs(off_truth_km(document, last_time(sets))) < 0.1)


def test_an_observation_far_off_is_dropped_and_the_fit_made_again():
    sets = observed()
    first = sets[0].observations[3]
    moved = replace(first, dec_deg=first.dec_deg + 300 / 3600)  # 5 arcminutes off
    sets[0] = replace(
        sets[0], observations=[*sets[0].observations[:3], moved, *sets[0].observations[4:]]
    )
    document = orbit_fit.fit(start(), sets, simulated_catalog=True)
    result = document["result"]
    assert result["dropped_as_outliers"] == 1
    dropped = [p for p in document["per_observation"] if not p["used"]]
    assert [(p["set"], p["index"]) for p in dropped] == [(0, 3)]
    assert dropped[0]["normalised_residual"] > 3
    assert np.all(np.abs(off_truth_km(document, last_time(sets))) < 0.1)


def test_at_most_a_tenth_is_dropped():
    sets = observed(stations=fit_example.STATIONS[:1])
    noisy = [
        replace(o, ra_deg=o.ra_deg + (k % 2) * 0.5) for k, o in enumerate(sets[0].observations)
    ]
    sets[0] = replace(sets[0], observations=noisy)
    result = orbit_fit.fit(start(), sets, simulated_catalog=True)["result"]
    assert result["dropped_as_outliers"] == math.floor(0.1 * result["observations"])


# Its document -----------------------------------------------------------------------------


def test_the_fit_is_named_by_its_inputs():
    sets = observed()
    one = orbit_fit.fit(start(), sets, simulated_catalog=True)
    again = orbit_fit.fit(start(), observed(), simulated_catalog=True)
    assert one == again
    changed = observed(seed=7)
    other = orbit_fit.fit(start(), changed, simulated_catalog=True)
    assert other["fit_id"] != one["fit_id"]
    shas = [i["sha256"] for i in one["inputs"]["observation_sets"]]
    assert shas == [orbit_fit.set_sha256(s) for s in sets]
    assert one["inputs"]["start_set"]["sha256"] == start().sha256


@pytest.mark.parametrize(("count", "days"), [(3, 1.0), (1, 1.0), (1, 3.0)])
def test_rounding_in_the_inputs_does_not_move_the_fit(count, days):
    # Another machine rounds differently: changes of 1e-10 degrees, far below any
    # observation's precision, give the same document (D-70).
    sets = observed(stations=fit_example.STATIONS[:count], days=days)
    found = []
    for eps in (-1e-10, 0.0, 1e-10):
        moved = [
            replace(s, observations=[replace(o, ra_deg=o.ra_deg + eps) for o in s.observations])
            for s in sets
        ]
        document = orbit_fit.fit(start(), moved, simulated_catalog=True)
        found.append((document["result"], document["per_observation"]))
    assert found[0] == found[1] == found[2]


def test_a_real_objects_fit_is_marked_not_for_publication():
    catalog = parse_catalog(real_catalog_bytes())
    sets = [replace(s, simulated=False) for s in observed()]
    document = orbit_fit.fit(catalog.element_sets(NORAD)[0], sets)
    assert document["simulated"] is False
    assert document["notice"] == orbit_fit.NOT_FOR_PUBLICATION
    assert "P6-07" in document["notice"]


def test_refusals():
    with pytest.raises(orbit_fit.FitError, match="no observation sets"):
        orbit_fit.fit(start(), [])
    few = observed()[:1]
    few[0] = replace(few[0], observations=few[0].observations[:3])
    with pytest.raises(orbit_fit.FitError, match="at least 4"):
        orbit_fit.fit(start(), few)
    other = observed()[:1]
    other[0] = replace(other[0], target=replace(other[0].target, norad_id=339002))
    with pytest.raises(orbit_fit.FitError, match="of object 339002"):
        orbit_fit.fit(start(), other)


# The committed example --------------------------------------------------------------------


def test_the_committed_example_is_made_again_byte_for_byte(tmp_path, examples_dir):
    fit_example.run_fit_example(tmp_path)
    committed = examples_dir / "orbit-fit"
    made = sorted(p.relative_to(tmp_path) for p in tmp_path.rglob("*") if p.is_file())
    assert made == sorted(p.relative_to(committed) for p in committed.rglob("*") if p.is_file())
    for name in made:
        assert (tmp_path / name).read_bytes() == (committed / name).read_bytes(), name


def test_fit_orbit_on_the_command_line(tmp_path, examples_dir, capsys):
    example = examples_dir / "orbit-fit"
    out = tmp_path / "fit.json"
    inputs = sorted(str(p) for p in (example / "observations").glob("*.json"))
    code = cli.main(
        ["fit-orbit", *inputs, "--catalog", str(example / "catalog.json"), "--out", str(out)]
    )
    assert code == cli.EXIT_OK
    assert out.read_bytes() == (example / "fit.json").read_bytes()
    printed = capsys.readouterr().out
    assert "converged" in printed and "SIMULATED" in printed
    document = json.loads(out.read_text())
    assert document["format"] == orbit_fit.FORMAT
    assert document["method"]["version"] == orbit_fit.METHOD_VERSION == "1.0.0"
    # The fitted set reads as any catalogue's.
    catalogue = {
        "format": "orbit-watch/gp-catalog",
        "format_version": "1.0",
        "simulated": True,
        "records": [document["result"]["omm"]],
    }
    assert NORAD in parse_catalog(json.dumps(catalogue).encode())


def test_fit_orbit_refuses_too_few_observations(tmp_path, examples_dir, capsys):
    example = examples_dir / "orbit-fit"
    observation_set = owjson.read_observation_set(
        (example / "observations" / "SIM-ESPOO.json").read_bytes()
    )
    few = replace(observation_set, observations=observation_set.observations[:2])
    path = tmp_path / "few.json"
    path.write_text(owjson.write_observation_set(few))
    code = cli.main(["fit-orbit", str(path), "--catalog", str(example / "catalog.json")])
    assert code == cli.EXIT_USAGE
    assert "at least 4" in capsys.readouterr().err

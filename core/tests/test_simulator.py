import math

import numpy as np
import pytest
from helpers import catalog

from orbit_watch.formats.owjson import FormatError
from orbit_watch.geometry import residuals
from orbit_watch.sim.simulator import (
    DeterministicRandom,
    StationProfile,
    builtin_profiles,
    load_profile,
    simulate,
)
from orbit_watch.timeutil import parse_utc

START = parse_utc("2026-11-01T00:00:00Z")
END = parse_utc("2026-11-02T00:00:00Z")


def test_builtin_profiles_are_valid_and_simulated():
    names = builtin_profiles()
    assert {"sim-cmos-gps", "sim-clock-offset", "sim-visual-binoculars", "sim-azel-mount"} <= set(
        names
    )
    for name in names:
        profile = load_profile(name)
        assert profile.description.startswith("SIMULATED")
        assert profile.station.id.startswith("SIM-")


def test_profile_must_be_marked_simulated():
    import json
    from importlib import resources

    doc = json.loads(
        resources.files("orbit_watch.data").joinpath("stations", "sim-cmos-gps.json").read_text()
    )
    doc["simulated"] = False
    with pytest.raises(FormatError):
        StationProfile.from_document(doc)


def test_deterministic_random_is_stable():
    # random.random() is guaranteed stable across Python versions for a given seed.
    rng = DeterministicRandom(42)
    values = [rng.uniform() for _ in range(3)]
    assert values == pytest.approx([0.6394267984578837, 0.025010755222666936, 0.27502931836911926])
    normals = [DeterministicRandom(7).normal() for _ in range(2)]
    assert normals[0] == normals[1]


def test_same_seed_same_output_different_seed_different_output():
    profile = load_profile("sim-cmos-gps")
    a = simulate(catalog(), 339001, profile, START, END, seed=5)
    b = simulate(catalog(), 339001, profile, START, END, seed=5)
    c = simulate(catalog(), 339001, profile, START, END, seed=6)
    assert a.to_document() == b.to_document()
    assert a.to_document() != c.to_document()
    assert a.simulated and "SIMULATED" in a.source["notes"]


def test_observations_respect_profile():
    profile = load_profile("sim-azel-mount")
    result = simulate(catalog(), 339003, profile, START, END, seed=9)
    assert result.observations
    for obs in result.observations:
        assert obs.angle_type == "azel"
        assert obs.el_deg >= profile.min_elevation_deg - 0.1
        assert obs.angle_uncertainty_arcsec == profile.declared_angle_uncertainty_arcsec
        assert obs.time.microsecond % 1000 == 0


def test_noise_matches_profile_and_clock_offset_shows_as_along_track_lag():
    cat = catalog()
    good = load_profile("sim-cmos-gps")
    result = simulate(cat, 339003, good, START, END, seed=11)
    res = residuals(cat.satellite(339003), good.station, result.observations)
    # Two axes of 5" angle noise plus 0.005 s timing noise along the track.
    expected = math.sqrt(2 * 5.0**2 + float(np.mean((0.005 * res.rate_arcsec_per_s) ** 2)))
    rms = math.sqrt(float(np.mean(res.separation_arcsec**2)))
    assert 0.6 * expected < rms < 1.4 * expected
    assert abs(float(np.mean(res.along_s))) < 0.01

    late_clock = load_profile("sim-clock-offset")  # clock 0.25 s ahead of UTC
    result = simulate(cat, 339003, late_clock, START, END, seed=11)
    res = residuals(cat.satellite(339003), late_clock.station, result.observations)
    assert float(np.mean(res.along_s)) == pytest.approx(-0.25, abs=0.01)


def test_wrong_object_is_far_from_the_claimed_orbit():
    cat = catalog()
    profile = load_profile("sim-cmos-gps")
    result = simulate(cat, 339001, profile, START, END, seed=3, observed_id=339002)
    res = residuals(cat.satellite(339001), profile.station, result.observations)
    # SIM-CUBESAT-B trails SIM-CUBESAT-A by about 8 seconds.
    assert float(np.mean(res.along_s)) == pytest.approx(-7.9, abs=0.3)


def test_no_passes_gives_no_observations():
    profile = load_profile("sim-cmos-gps")
    result = simulate(catalog(), 339001, profile, START, parse_utc("2026-11-01T00:10:00Z"), seed=1)
    assert result.observations == []

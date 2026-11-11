import dataclasses
from datetime import timedelta

import pytest
from helpers import catalog

from orbit_watch.quality import render_text, score_station
from orbit_watch.sim.scenarios import build_quality_example
from orbit_watch.sim.simulator import load_profile, simulate
from orbit_watch.timeutil import parse_utc


def sets_for(profile, nights=("2026-11-01", "2026-11-02"), objects=(339001, 339003), seed=1):
    cat = catalog()
    result = []
    for n, night in enumerate(nights):
        start = parse_utc(f"{night}T15:00:00Z")
        for k, norad in enumerate(objects):
            result.append(
                simulate(
                    cat,
                    norad,
                    profile,
                    start,
                    start + timedelta(hours=12),
                    seed=seed + 10 * n + k,
                    max_passes=2,
                )
            )
    return result


def test_recovers_simulated_precision_and_finds_no_clock_error():
    profile = load_profile("sim-cmos-gps")  # 5" angle noise, 0.005 s timing noise
    report = score_station(sets_for(profile), catalog())
    overall = report["overall"]
    assert overall["angle_scatter_arcsec"] == pytest.approx(5.0, rel=0.35)
    # Timing scatter also holds the along-track part of the angle noise (5" / rate).
    assert 0.004 < overall["timing_scatter_s"] < 0.009
    assert abs(overall["mean_along_track_s"]) < 0.01
    assert any("No systematic timing offset" in f for f in report["findings"])


def test_finds_clock_offset_shared_by_objects():
    profile = load_profile("sim-clock-offset")  # clock 0.25 s ahead of UTC
    report = score_station(sets_for(profile), catalog())
    assert report["nights"][-1]["mean_along_track_s"] == pytest.approx(-0.25, abs=0.01)
    finding = next(f for f in report["findings"] if "clock" in f)
    assert "0.25 s ahead of UTC" in finding


def test_single_object_offset_is_not_blamed_on_the_clock():
    profile = load_profile("sim-clock-offset")
    report = score_station(sets_for(profile, nights=("2026-11-01",), objects=(339001,)), catalog())
    assert any("cannot be told apart" in f for f in report["findings"])


def test_declared_uncertainty_too_small_is_flagged():
    profile = dataclasses.replace(load_profile("sim-cmos-gps"), angle_noise_arcsec=30.0)
    report = score_station(sets_for(profile), catalog())
    assert any("Consider declaring a larger uncertainty" in f for f in report["findings"])


def test_stale_and_unknown_objects_are_reported():
    profile = load_profile("sim-cmos-gps")
    sets = sets_for(profile, nights=("2026-11-01", "2026-11-12"))
    sets[0].target = dataclasses.replace(sets[0].target, norad_id=25544)
    report = score_station(sets, catalog())
    assert any("more than 7 days" in n for n in report["notices"])
    assert any("Object 25544 was left out" in n for n in report["notices"])
    assert "Inputs include SIMULATED data." in render_text(report)


def test_one_station_at_a_time():
    a = sets_for(load_profile("sim-cmos-gps"), nights=("2026-11-01",), objects=(339001,))
    b = sets_for(load_profile("sim-azel-mount"), nights=("2026-11-01",), objects=(339003,))
    with pytest.raises(ValueError):
        score_station(a + b, catalog())


def test_quality_example_story(tmp_path):
    report = build_quality_example(tmp_path, catalog())
    offsets = [n["mean_along_track_s"] for n in report["nights"]]
    assert offsets[0] == pytest.approx(0, abs=0.01) and offsets[-1] == pytest.approx(
        -0.25, abs=0.01
    )
    assert (tmp_path / "observations.iod").read_text().startswith("# orbit-watch: simulated=true")

"""A station's passes and their visible parts, and the simulator that observes only there
(phase 5, step 5.7; decisions P5-12, D-57; issue #7). Everything is SIMULATED."""

from datetime import timedelta

import pytest
from helpers import catalog

from orbit_watch import sun
from orbit_watch.catalog import timescale
from orbit_watch.cli import main
from orbit_watch.passes import passes
from orbit_watch.sim.simulator import load_profile, simulate
from orbit_watch.timeutil import parse_utc

PROFILE = load_profile("sim-cmos-gps")  # SIM-ESPOO, elevation limit 15°
NIGHT = (parse_utc("2026-11-01T15:00:00Z"), parse_utc("2026-11-02T03:00:00Z"))
DAY = (parse_utc("2026-11-01T00:00:00Z"), parse_utc("2026-11-02T00:00:00Z"))


def found(window=NIGHT, profile=PROFILE, **options):
    return passes(catalog(), 339001, profile.station, *window, profile.min_elevation_deg, **options)


def test_the_evening_passes_are_visible_and_the_later_ones_are_not():
    night = found()
    visible = [p for p in night if p.visible]
    assert [f"{p.visible_peak:%H:%M}" for p in visible] == ["15:44", "17:18"]
    for p in night:
        assert p.rise <= p.culmination <= p.set
        assert p.max_elevation_deg >= PROFILE.min_elevation_deg
        if p.visible:
            assert p.rise <= p.visible_start <= p.visible_peak <= p.visible_end <= p.set
            assert p.visible_max_elevation_deg <= p.max_elevation_deg + 1e-9
    assert any(not p.visible for p in found(DAY))  # daylight and shadow


def test_a_pass_under_way_is_cut_at_the_windows_edges():
    first = found()[0]
    middle = first.culmination
    cut = found((middle, middle + timedelta(minutes=30)))[0]
    assert cut.rise == middle
    tail = found((first.rise - timedelta(minutes=5), middle))[-1]
    assert tail.set == middle


def test_the_dark_sky_is_a_setting():
    lighter = [p for p in found(dark_sky_deg=0.0) if p.visible]
    darker = [p for p in found(dark_sky_deg=-18.0) if p.visible]
    assert len(darker) <= len([p for p in found() if p.visible]) <= len(lighter)


def test_the_public_view_of_a_pass():
    view = next(p for p in found() if p.visible).public()
    assert view["visible"] is True
    assert view["visible_peak"].startswith("2026-11-01T15:4")
    assert set(view) == {
        "rise",
        "culmination",
        "set",
        "max_elevation_deg",
        "visible",
        "visible_start",
        "visible_peak",
        "visible_end",
        "visible_max_elevation_deg",
    }


def test_the_simulator_observes_only_what_the_station_can_see():
    seen = simulate(catalog(), 339001, PROFILE, *DAY, seed=3)
    everything = simulate(catalog(), 339001, PROFILE, *DAY, seed=3, dark_sky_deg=None)
    assert 0 < len(seen.observations) < len(everything.observations)
    visible = [p for p in found(DAY) if p.visible]
    for observation in seen.observations:
        assert any(
            p.visible_start - timedelta(seconds=11)
            <= observation.time
            <= p.visible_end + timedelta(seconds=11)
            for p in visible
        ), observation.time
    ts = timescale()
    times = ts.from_datetimes([o.time for o in seen.observations])
    position = catalog().satellite(339001).at(times).position.km
    assert sun.sunlit(position, times).mean() > 0.9  # labels are within a second of truth
    assert sun.dark(PROFILE.station, times).all()


def test_the_command_line_says_why_there_is_nothing_to_see(tmp_path, capsys):
    out = tmp_path / "sim.json"
    common = ["simulate", "--target", "339001", "--start", "2026-11-01T06:00:00Z"]
    daytime = [*common, "--end", "2026-11-01T12:00:00Z", "-o", str(out)]
    assert main(daytime) != 0
    assert "sunlit under a dark sky" in capsys.readouterr().err
    assert main([*daytime, "--any-light"]) == 0
    assert out.read_text().count('"time"') > 0


@pytest.mark.parametrize("name", ["sim-azel-mount", "sim-clock-offset", "sim-visual-binoculars"])
def test_every_simulated_station_sees_two_evening_passes(name):
    profile = load_profile(name)
    assert len([p for p in found(profile=profile) if p.visible]) == 2

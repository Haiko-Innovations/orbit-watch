"""The Sun's place from the USNO formula (phase 5, step 5.7; decisions P5-12, D-56).

No test here needs an ephemeris: the reference directions were computed once from JPL's
DE421 through Skyfield, as ``orbit-watch measure-sun`` does. With DE421 in the cache, the
last test repeats the whole measurement and compares it with validation/sun/results.json.
"""

import json
from pathlib import Path

import numpy as np
import pytest

from orbit_watch import orbit_cache, sun, sun_check
from orbit_watch.catalog import timescale
from orbit_watch.cli import main
from orbit_watch.model import Station

ROOT = Path(__file__).resolve().parents[2]
NORTH = Station("NORTH", 60.0, 25.0, 0.0)

# DE421's apparent Sun from the Earth's centre, unit vectors in the ICRS axes.
DE421 = [
    ((2000, 1, 1, 12), (0.180052, -0.9024894, -0.3912725)),
    ((2026, 3, 20, 12), (0.9999645, -0.0077251, -0.0033528)),
    ((2026, 6, 21, 0), (0.0123273, 0.9174365, 0.3976911)),
    ((2026, 11, 1, 12), (-0.7804326, -0.573664, -0.2486656)),
    ((2049, 12, 1, 6), (-0.3620676, -0.8552772, -0.3706857)),
]


@pytest.mark.parametrize(("when", "reference"), DE421)
def test_the_suns_direction_is_within_an_arcminute_of_de421(when, reference):
    direction = sun.sun_direction(timescale().utc(*when))
    assert np.linalg.norm(direction) == pytest.approx(1.0)
    reference = np.array(reference) / np.linalg.norm(reference)  # rounded to 7 decimals
    error = (
        np.degrees(
            np.arctan2(np.linalg.norm(np.cross(direction, reference)), direction @ reference)
        )
        * 3600
    )
    assert error < 60  # the USNO formula's "about 1 arcminute"


def test_the_suns_elevation_at_the_solstices():
    ts = timescale()
    hours = np.arange(0, 24, 1 / 60)
    summer = sun.sun_elevation_deg(NORTH, ts.utc(2026, 6, 21, hours))
    winter = sun.sun_elevation_deg(NORTH, ts.utc(2026, 12, 21, hours))
    # Noon at 60° north: 90 - 60 ± 23.44 degrees.
    assert summer.max() == pytest.approx(53.44, abs=0.03)
    assert winter.max() == pytest.approx(6.56, abs=0.03)
    assert summer.min() > -7 and winter.min() < -53


def test_a_dark_sky():
    ts = timescale()
    midnight, noon = ts.utc(2026, 12, 21, 22), ts.utc(2026, 6, 21, 10)
    assert bool(sun.dark(NORTH, midnight)) and not bool(sun.dark(NORTH, noon))
    # The limit is a setting: on a midsummer midnight at 60° north the Sun is only about
    # 6.5 degrees down, dark at -6 but not at -12.
    late = ts.utc(2026, 6, 21, 22, 20)
    assert bool(sun.dark(NORTH, late)) and not bool(sun.dark(NORTH, late, limit_deg=-12))


def test_sunlight_is_outside_the_earths_shadow():
    t = timescale().utc(2026, 11, 1, 12)
    towards = sun.sun_direction(t)
    across = np.cross(towards, [0.0, 0.0, 1.0])
    across /= np.linalg.norm(across)
    positions = np.array(
        [
            7000 * towards,  # on the Sun's side
            -7000 * towards,  # straight behind the Earth: in its shadow
            -7000 * towards + 6000 * across,  # behind, within the Earth's radius
            -7000 * towards + 6500 * across,  # behind, but beyond it
        ]
    ).T
    assert sun.sunlit(positions, t).tolist() == [True, False, False, True]
    assert bool(sun.sunlit(7000 * towards, t))


def test_measuring_needs_the_ephemeris(tmp_path, capsys):
    code = main(["measure-sun", "--root", str(tmp_path), "--cache", str(tmp_path / "cache")])
    assert code == 2
    assert "fetch it once with orbit-watch measure-sun --fetch" in capsys.readouterr().err
    assert not (tmp_path / "validation").exists()


@pytest.mark.skipif(
    not (orbit_cache.default_cache_dir() / "ephemeris" / sun_check.EPHEMERIS).is_file(),
    reason="DE421 is not in the cache: fetch it with orbit-watch measure-sun --fetch",
)
def test_the_recorded_measurement_is_what_the_measurement_gives():
    eph = sun_check.load_ephemeris(orbit_cache.default_cache_dir(), fetch=False)
    catalog = (ROOT / "core/src/orbit_watch/data/catalog.json").read_bytes()
    recorded = json.loads((ROOT / "validation/sun/results.json").read_text())
    measured = sun_check.measure(eph, catalog)
    for part in ("direction", "elevation", "sunlight"):
        assert measured[part] == recorded[part], part

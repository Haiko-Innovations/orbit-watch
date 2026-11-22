"""The USNO Sun formula measured against JPL's DE421 (phase 5, step 5.7; P5-12, D-56).

``orbit-watch measure-sun`` runs it once and writes ``validation/sun/results.json``. It needs
DE421 (``de421.bsp``, 1900 to 2050, 17 MB), which Skyfield's loader fetches into the cache
directory only when asked (``--fetch``): no test and no CI job fetches it. Three things
are measured:

* **the Sun's direction**, once a day over DE421's whole span, against Skyfield's apparent
  place of the Sun seen from the Earth's centre;
* **the Sun's elevation** at SIM-ESPOO, every 10 minutes through 2026, against Skyfield's
  topocentric apparent place without refraction, and how often the two disagree on a dark
  sky at -6°;
* **sunlight**, every 10 seconds over a week of SIM-CUBESAT-A's orbit, against Skyfield's
  ``is_sunlit`` with DE421: how often the two disagree, and for how long at a time.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import numpy as np

from orbit_watch import __version__, sun
from orbit_watch.catalog import parse_catalog, timescale
from orbit_watch.model import Station

EPHEMERIS = "de421.bsp"
ARCSEC_PER_RAD = 180 / np.pi * 3600
ESPOO = Station("SIM-ESPOO", 60.205, 24.655, 40.0)  # the SIMULATED station's place


def load_ephemeris(cache_dir: Path, fetch: bool):
    """DE421 from the cache directory; fetched there only when ``fetch`` is true."""
    from skyfield.api import Loader

    folder = cache_dir / "ephemeris"
    if not (folder / EPHEMERIS).is_file() and not fetch:
        raise FileNotFoundError(
            f"{EPHEMERIS} is not in {folder}: fetch it once with orbit-watch measure-sun "
            "--fetch (17 MB from JPL, through Skyfield's loader)"
        )
    folder.mkdir(parents=True, exist_ok=True)
    return Loader(str(folder), verbose=False)(EPHEMERIS)


def _stats(values: np.ndarray, digits: int = 2) -> dict[str, float]:
    return {
        "median": round(float(np.median(values)), digits),
        "p95": round(float(np.percentile(values, 95)), digits),
        "max": round(float(np.max(values)), digits),
    }


def _angle_arcsec(a: np.ndarray, b: np.ndarray) -> np.ndarray:
    a = a / np.linalg.norm(a, axis=0)
    b = b / np.linalg.norm(b, axis=0)
    across = np.linalg.norm(np.cross(a, b, axis=0), axis=0)
    return np.arctan2(across, np.sum(a * b, axis=0)) * ARCSEC_PER_RAD  # exact near 0


def direction(eph) -> dict[str, Any]:
    """The Sun's direction from the Earth's centre, once a day from 1900 to 2049."""
    ts = timescale()
    earth, star = eph["earth"], eph["sun"]
    result: dict[str, Any] = {}
    for label, first, last in (("1900-2049", 1900, 2049), ("2000-2049", 2000, 2049)):
        days = np.arange(0, (last - first + 1) * 365.25, 1.0)
        t = ts.utc(first, 1, 1 + days)
        reference = earth.at(t).observe(star).apparent().position.au
        result[label] = {
            "samples": int(days.size),
            "error_arcsec": _stats(_angle_arcsec(sun.sun_direction(t), reference), 1),
        }
    return result


def elevation(eph) -> dict[str, Any]:
    """The Sun's elevation at SIM-ESPOO through 2026, every 10 minutes."""
    from skyfield.api import wgs84

    ts = timescale()
    minutes = np.arange(0, 365 * 24 * 60, 10)
    t = ts.utc(2026, 1, 1, 0, minutes)
    place = eph["earth"] + wgs84.latlon(ESPOO.latitude_deg, ESPOO.longitude_deg, ESPOO.altitude_m)
    reference = place.at(t).observe(eph["sun"]).apparent().altaz()[0].degrees
    ours = sun.sun_elevation_deg(ESPOO, t)
    limit = sun.DARK_SKY_SUN_ELEVATION_DEG
    disagree = (ours <= limit) != (reference <= limit)
    return {
        "station": {"id": ESPOO.id, "latitude_deg": ESPOO.latitude_deg},
        "samples": int(minutes.size),
        "error_arcsec": _stats(np.abs(ours - reference) * 3600, 1),
        "dark_sky_limit_deg": limit,
        "dark_sky_disagreements": int(disagree.sum()),
    }


def sunlight(eph, catalog: bytes) -> dict[str, Any]:
    """SIM-CUBESAT-A's sunlight every 10 seconds for a week from 2026-11-01."""
    ts = timescale()
    satellite = parse_catalog(catalog).satellite(339001)
    seconds = np.arange(0, 7 * 86400, 10)
    t = ts.utc(2026, 11, 1, 0, 0, seconds)
    at = satellite.at(t)
    reference = at.is_sunlit(eph)
    ours = sun.sunlit(at.position.km, t)
    disagree = ours != reference
    runs, length = [], 0
    for flag in disagree:
        if flag:
            length += 1
        elif length:
            runs.append(length)
            length = 0
    if length:
        runs.append(length)
    return {
        "object": "339001 SIM-CUBESAT-A (SIMULATED)",
        "samples": int(seconds.size),
        "step_s": 10,
        "sunlit_fraction": round(float(reference.mean()), 4),
        "disagreements": int(disagree.sum()),
        "longest_disagreement_s": 10 * max(runs, default=0),
        "transitions": int(np.count_nonzero(np.diff(reference.astype(int)))),
    }


def measure(eph, catalog: bytes) -> dict[str, Any]:
    from skyfield import __version__ as skyfield_version

    return {
        "format": "orbit-watch/sun-measurement",
        "format_version": "1.0",
        "description": (
            "The US Naval Observatory's approximate solar coordinates, as orbit_watch.sun "
            "computes them, against JPL's DE421 through Skyfield (decision D-56)."
        ),
        "formula": "https://aa.usno.navy.mil/faq/sun_approx",
        "ephemeris": EPHEMERIS,
        "software": {"orbit-watch": __version__, "skyfield": skyfield_version},
        "direction": direction(eph),
        "elevation": elevation(eph),
        "sunlight": sunlight(eph, catalog),
    }

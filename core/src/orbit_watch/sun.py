"""The Sun's place, for visibility (phase 5, step 5.7; decisions P5-12 and D-56).

An optical observer sees a satellite only when the Sun lights it and the observer's sky is
dark. This needs the Sun's place to a fraction of a degree, not an ephemeris file: the US
Naval Observatory's short formula gives it "to an accuracy of about 1 arcminute within two
centuries of 2000" (https://aa.usno.navy.mil/faq/sun_approx, read on 2026-11-22). Skyfield
rotates it into the ICRS axes that its geocentric positions use, and gives the Earth's
rotation, without any file. ``orbit-watch measure-sun`` measures it against JPL's DE421 once,
and ``validation/sun/results.json`` records the result.

* ``sun_direction``: the unit vector from the Earth's centre towards the Sun;
* ``sun_elevation_deg``: the Sun's elevation above a station's horizon;
* ``sunlit``: whether a satellite is outside the Earth's shadow, a cylinder of the Earth's
  equatorial radius behind the Earth;
* ``dark``: whether a station's sky is dark, by default with the Sun at least 6° below the
  horizon, the end of civil twilight (``DARK_SKY_SUN_ELEVATION_DEG``, a setting).
"""

from __future__ import annotations

import numpy as np
from skyfield.framelib import itrs

from orbit_watch.model import Station

J2000_JD = 2451545.0
EARTH_RADIUS_KM = 6378.137  # WGS 84 equatorial radius
DARK_SKY_SUN_ELEVATION_DEG = -6.0  # the end of civil twilight (P5-12)


def sun_of_date(t) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """The Sun's right ascension and declination (radians) referred to the equator and
    equinox of date, and its distance (au), from the USNO formula, for a Skyfield time or
    array of times. The formula takes the Julian date in Universal Time."""
    d = np.asarray(t.ut1) - J2000_JD
    g = np.radians((357.529 + 0.98560028 * d) % 360.0)  # mean anomaly
    q = (280.459 + 0.98564736 * d) % 360.0  # mean longitude
    longitude = np.radians(q + 1.915 * np.sin(g) + 0.020 * np.sin(2 * g))  # apparent
    distance = 1.00014 - 0.01671 * np.cos(g) - 0.00014 * np.cos(2 * g)
    obliquity = np.radians(23.439 - 0.00000036 * d)  # mean
    ra = np.arctan2(np.cos(obliquity) * np.sin(longitude), np.cos(longitude))
    dec = np.arcsin(np.sin(obliquity) * np.sin(longitude))
    return ra, dec, distance


def sun_direction(t) -> np.ndarray:
    """The unit vector from the Earth's centre towards the Sun, in the ICRS axes of
    Skyfield's geocentric positions: shape (3,), or (3, n) for n times."""
    ra, dec, _ = sun_of_date(t)
    of_date = np.array([np.cos(dec) * np.cos(ra), np.cos(dec) * np.sin(ra), np.sin(dec)])
    return np.einsum("ij...,j...->i...", t.MT, of_date)  # equinox of date -> ICRS


def _up(station: Station, t) -> np.ndarray:
    """The station's geodetic zenith, in the ICRS axes."""
    lat, lon = np.radians(station.latitude_deg), np.radians(station.longitude_deg)
    zenith = np.array([np.cos(lat) * np.cos(lon), np.cos(lat) * np.sin(lon), np.sin(lat)])
    return np.einsum("ji...,j->i...", itrs.rotation_at(t), zenith)  # ITRS -> ICRS


def sun_elevation_deg(station: Station, t) -> np.ndarray:
    """The Sun's elevation above the station's horizon, in degrees, without refraction. The
    Sun's parallax, under 9 arcseconds, is left out."""
    cosine = np.sum(_up(station, t) * sun_direction(t), axis=0)
    return np.degrees(np.arcsin(np.clip(cosine, -1.0, 1.0)))


def dark(station: Station, t, limit_deg: float = DARK_SKY_SUN_ELEVATION_DEG) -> np.ndarray:
    """Whether the station's sky is dark: the Sun at or below ``limit_deg``."""
    return sun_elevation_deg(station, t) <= limit_deg


def sunlit(position_km: np.ndarray, t) -> np.ndarray:
    """Whether a satellite at a geocentric position (km, ICRS axes; shape (3,) or (3, n))
    is in sunlight: on the Sun's side of the Earth, or outside the cylinder of the Earth's
    shadow."""
    towards_sun = sun_direction(t)
    position = np.asarray(position_km, dtype=float)
    if position.ndim > towards_sun.ndim:  # one time, several positions
        towards_sun = towards_sun[:, np.newaxis]
    along = np.sum(position * towards_sun, axis=0)
    across = np.linalg.norm(position - along * towards_sun, axis=0)
    return (along > 0) | (across > EARTH_RADIUS_KM)

"""Predicted topocentric directions and residual decomposition.

Predictions use Skyfield's geometric topocentric vector
``(satellite - station).at(t)`` as recommended in the Skyfield documentation for
Earth satellites. Light travel time and annual aberration are not modelled
(together up to about 20 arcseconds); see docs/verification.md.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

import numpy as np
from skyfield.api import wgs84

from orbit_watch.catalog import timescale
from orbit_watch.model import Observation, Station
from orbit_watch.timeutil import add_seconds

ARCSEC_PER_RAD = 206264.80624709636
DERIVATIVE_STEP_S = 1.0


def topos(station: Station):
    return wgs84.latlon(station.latitude_deg, station.longitude_deg, elevation_m=station.altitude_m)


def _unit_from_angles(lon_deg: np.ndarray, lat_deg: np.ndarray) -> np.ndarray:
    lon = np.radians(lon_deg)
    lat = np.radians(lat_deg)
    return np.stack([np.cos(lat) * np.cos(lon), np.cos(lat) * np.sin(lon), np.sin(lat)])


def _azel_unit(az_deg: np.ndarray, el_deg: np.ndarray) -> np.ndarray:
    # East-north-up components; azimuth from north through east.
    az = np.radians(az_deg)
    el = np.radians(el_deg)
    return np.stack([np.cos(el) * np.sin(az), np.cos(el) * np.cos(az), np.sin(el)])


@dataclass
class Prediction:
    angle_1_deg: np.ndarray  # RA or azimuth
    angle_2_deg: np.ndarray  # Dec or elevation
    range_km: np.ndarray
    elevation_deg: np.ndarray


def predict(
    satellite, station: Station, times: list[datetime], angle_type: str, frame: str | None = None
) -> Prediction:
    """Predicted angles of a satellite seen from a station at the given UTC times."""
    ts = timescale()
    t = ts.from_datetimes(times)
    topocentric = (satellite - topos(station)).at(t)
    alt, az, distance = topocentric.altaz()
    if angle_type == "radec":
        if frame == "of-date":
            ra, dec, _ = topocentric.radec(epoch="date")
        else:
            ra, dec, _ = topocentric.radec()
        return Prediction(
            (np.asarray(ra.hours) * 15.0) % 360.0,
            np.asarray(dec.degrees),
            np.asarray(distance.km),
            np.asarray(alt.degrees),
        )
    return Prediction(
        np.asarray(az.degrees) % 360.0,
        np.asarray(alt.degrees),
        np.asarray(distance.km),
        np.asarray(alt.degrees),
    )


def unit_vectors(angle_type: str, a1: np.ndarray, a2: np.ndarray) -> np.ndarray:
    if angle_type == "radec":
        return _unit_from_angles(a1, a2)
    return _azel_unit(a1, a2)


@dataclass
class Residuals:
    separation_arcsec: np.ndarray
    along_arcsec: np.ndarray  # positive: the object is ahead of the prediction
    cross_arcsec: np.ndarray
    along_s: np.ndarray  # along-track residual converted to seconds of time
    rate_arcsec_per_s: np.ndarray
    range_km: np.ndarray
    elevation_deg: np.ndarray


def residuals(satellite, station: Station, observations: list[Observation]) -> Residuals:
    """Observed minus predicted, split into along-track and cross-track components.

    All observations must share one angle type and frame.
    """
    kinds = {(o.angle_type, o.frame) for o in observations}
    if len(kinds) != 1:
        raise ValueError("residuals() needs observations of a single angle type and frame")
    angle_type, frame = kinds.pop()
    times = [o.time for o in observations]
    before = [add_seconds(t, -DERIVATIVE_STEP_S) for t in times]
    after = [add_seconds(t, DERIVATIVE_STEP_S) for t in times]
    now = predict(satellite, station, times, angle_type, frame)
    p0 = predict(satellite, station, before, angle_type, frame)
    p1 = predict(satellite, station, after, angle_type, frame)
    obs_a1 = np.array([o.angle_1_deg for o in observations])
    obs_a2 = np.array([o.angle_2_deg for o in observations])
    o = unit_vectors(angle_type, obs_a1, obs_a2)
    p = unit_vectors(angle_type, now.angle_1_deg, now.angle_2_deg)
    motion = unit_vectors(angle_type, p1.angle_1_deg, p1.angle_2_deg) - unit_vectors(
        angle_type, p0.angle_1_deg, p0.angle_2_deg
    )
    # Remove the radial component so that the motion direction lies in the tangent plane at p.
    motion = motion - p * np.sum(motion * p, axis=0)
    rate = np.linalg.norm(motion, axis=0) / (2 * DERIVATIVE_STEP_S)  # rad/s
    u = motion / np.linalg.norm(motion, axis=0)
    c = np.cross(p.T, u.T).T
    diff = o - p
    along = np.sum(diff * u, axis=0)
    cross = np.sum(diff * c, axis=0)
    separation = np.arctan2(np.linalg.norm(np.cross(o.T, p.T).T, axis=0), np.sum(o * p, axis=0))
    return Residuals(
        separation_arcsec=separation * ARCSEC_PER_RAD,
        along_arcsec=along * ARCSEC_PER_RAD,
        cross_arcsec=cross * ARCSEC_PER_RAD,
        along_s=along / rate,
        rate_arcsec_per_s=rate * ARCSEC_PER_RAD,
        range_km=now.range_km,
        elevation_deg=now.elevation_deg,
    )

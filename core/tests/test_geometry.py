import numpy as np
import pytest
from helpers import catalog

from orbit_watch.geometry import predict, residuals
from orbit_watch.model import Observation, Station
from orbit_watch.timeutil import add_seconds, parse_utc

STATION = Station("SIM-X", 60.205, 24.655, 40.0)
T0 = parse_utc("2026-11-01T18:55:04Z")  # SIM-CUBESAT-A culminates for this station


def observations_from_prediction(satellite, shift_s=0.0, angle_type="radec", frame="ICRF"):
    times = [add_seconds(T0, k * 10.0) for k in range(-2, 3)]
    truth = predict(satellite, STATION, [add_seconds(t, shift_s) for t in times], angle_type, frame)
    result = []
    for i, t in enumerate(times):
        if angle_type == "radec":
            result.append(
                Observation(
                    t,
                    0.01,
                    "radec",
                    5.0,
                    frame=frame,
                    ra_deg=float(truth.angle_1_deg[i]),
                    dec_deg=float(truth.angle_2_deg[i]),
                )
            )
        else:
            result.append(
                Observation(
                    t,
                    0.01,
                    "azel",
                    5.0,
                    az_deg=float(truth.angle_1_deg[i]),
                    el_deg=float(truth.angle_2_deg[i]),
                )
            )
    return result


@pytest.mark.parametrize(
    ("angle_type", "frame"), [("radec", "ICRF"), ("radec", "of-date"), ("azel", None)]
)
def test_perfect_observations_have_zero_residuals(angle_type, frame):
    sat = catalog().satellite(339001)
    res = residuals(sat, STATION, observations_from_prediction(sat, 0.0, angle_type, frame))
    assert np.max(res.separation_arcsec) < 0.01


@pytest.mark.parametrize("shift", [0.5, -0.5])
def test_time_shift_appears_along_track_with_sign(shift):
    sat = catalog().satellite(339001)
    res = residuals(sat, STATION, observations_from_prediction(sat, shift))
    # Positions from later in the pass mean the object is ahead of the prediction.
    assert np.mean(res.along_s) == pytest.approx(shift, abs=0.01)
    assert np.max(np.abs(res.cross_arcsec)) < 0.05 * np.max(np.abs(res.along_arcsec))


def test_of_date_differs_from_icrf():
    sat = catalog().satellite(339001)
    icrf = predict(sat, STATION, [T0], "radec", "ICRF")
    of_date = predict(sat, STATION, [T0], "radec", "of-date")
    # Precession since J2000 moves RA by roughly 0.37 degrees by 2026.
    assert abs(icrf.angle_1_deg[0] - of_date.angle_1_deg[0]) > 0.1


def test_mixed_kinds_rejected():
    sat = catalog().satellite(339001)
    mixed = (
        observations_from_prediction(sat)[:2]
        + observations_from_prediction(sat, angle_type="azel", frame=None)[:2]
    )
    with pytest.raises(ValueError):
        residuals(sat, STATION, mixed)

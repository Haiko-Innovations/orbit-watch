"""Orbit determination in the core (phase 6, step 6.4, decisions P6-06 and D-70).

A batch least squares fit of SGP4's mean elements, and B* over a long enough arc, to the
angles of one or more observation sets. It starts from a reference orbit, the start set,
and keeps that set's epoch. Every candidate orbit is built as the catalogue builds one
(Skyfield's ``EarthSatellite.from_omm``), so a fitted set reads back as it was fitted.

- **Elements.** The fit moves equinoctial elements: the mean motion, ``af`` and ``ag``
  (the eccentricity vector), ``chi`` and ``psi`` (the inclination's) and the mean
  longitude. Near-circular low orbits leave the argument of perigee and the mean
  anomaly nearly undefined apart; their sum is well defined (D-70, choice a).
- **B\\*** is fitted only when the observations span at least two days; over a shorter
  arc the start set's value is kept (choice b).
- **The start set as a measurement** (choice c). At its epoch and at the middle of each
  track, the fit's position is held to the start set's, radially, along the track and
  across it, with the error step 6.1 measured for sets like it at that age (method
  3.0.0's orbit term, its 90th percentile taken as 1.645 standard deviations). So a
  short arc from one station does not leave the orbit free where the angles do not
  measure it. Those times are treated as independent: this weighs the start set a little
  more than its errors' correlation over time would.
- **Outliers** (choice d). After the fit, the observation furthest off, if it is more
  than three standard deviations off, is dropped and the fit made again; one at a time,
  and at most a tenth of the observations. Dropping all of them at once would also drop
  good ones that a far observation pulled the first fit away from.
- **Deterministic.** Fixed steps, iterations and stopping rules, and rounded output, so
  a fit is repeated byte for byte. The method has a version of its own.

Its limit: a short arc seen from one place measures the range poorly, and a fit to one
station's tracks takes that station's constant clock error into the orbit along the
track. Only another station, or an operator's orbit, shows such an error.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import datetime
from typing import Any

import numpy as np
from skyfield.api import EarthSatellite

from orbit_watch import SIMULATION_NOTICE
from orbit_watch.canonical import dumps_compact, sha256_bytes
from orbit_watch.catalog import ElementSet, omm_fields, timescale
from orbit_watch.geometry import ARCSEC_PER_RAD, predict, residuals, unit_vectors
from orbit_watch.model import Observation, ObservationSet, Station
from orbit_watch.timeutil import format_utc
from orbit_watch.verify import orbit_terms

FORMAT = "orbit-watch/orbit-fit"
FORMAT_VERSION = "1.0"
METHOD_NAME = "orbit-watch-orbit-fit"
METHOD_VERSION = "1.0.0"

NAMES = ("mean_motion_rev_per_day", "af", "ag", "chi", "psi", "mean_longitude_rad", "bstar")
# Central differences: a step for each element, small against what the fit resolves and
# large against SGP4's rounding.
STEPS = (1e-7, 1e-7, 1e-7, 1e-7, 1e-7, 1e-6, 1e-6)

PARAMETERS: dict[str, Any] = {
    "elements": "equinoctial: mean motion, af, ag, chi, psi, mean longitude; and B*",
    "bstar_min_span_days": 2.0,
    "start_set_sigma_from_p90": 1.645,
    "track_gap_s": 900.0,
    "max_iterations": 30,
    "min_relative_cost_decrease": 1e-9,
    "min_step_in_sigma": 1e-4,
    "damping_start": 1e-3,
    "damping_tries": 8,
    "outlier_threshold_sigma": 3.0,
    "max_outlier_fraction": 0.1,
}

NOT_FOR_PUBLICATION = (
    "Elements fitted to a real object. Orbit Watch publishes no fitted elements until "
    "Space-Track's user agreement is read (P6-07)."
)


class FitError(ValueError):
    pass


# --------------------------------------------------------------------------- elements


def to_equinoctial(record: dict[str, Any]) -> np.ndarray:
    """The fit's elements of an OMM record."""
    e = float(record["ECCENTRICITY"])
    i = math.radians(float(record["INCLINATION"]))
    node = math.radians(float(record["RA_OF_ASC_NODE"]))
    perigee = math.radians(float(record["ARG_OF_PERICENTER"]))
    anomaly = math.radians(float(record["MEAN_ANOMALY"]))
    if not i < math.pi:
        raise FitError("an equatorial retrograde orbit cannot be fitted in these elements")
    longitude_of_perigee = perigee + node
    t = math.tan(i / 2)
    return np.array(
        [
            float(record["MEAN_MOTION"]),
            e * math.cos(longitude_of_perigee),
            e * math.sin(longitude_of_perigee),
            t * math.sin(node),
            t * math.cos(node),
            anomaly + longitude_of_perigee,
            float(record["BSTAR"]),
        ]
    )


def to_record(start: dict[str, Any], x: np.ndarray, rounded: bool = False) -> dict[str, Any]:
    """An OMM record with the fit's elements, the rest as the start set's."""
    n, af, ag, chi, psi, longitude, bstar = (float(v) for v in x)
    e = math.hypot(af, ag)
    longitude_of_perigee = math.atan2(ag, af) if e > 0 else 0.0
    node = math.atan2(chi, psi) if (chi or psi) else 0.0
    i = 2 * math.atan(math.hypot(chi, psi))

    def degrees(angle: float) -> float:
        value = math.degrees(angle) % 360.0
        return round(value, 7) % 360.0 if rounded else value

    record = dict(omm_fields(start))
    record.update(
        {
            "MEAN_MOTION": round(n, 9) if rounded else n,
            "ECCENTRICITY": round(e, 9) if rounded else e,
            "INCLINATION": round(math.degrees(i), 7) if rounded else math.degrees(i),
            "RA_OF_ASC_NODE": degrees(node),
            "ARG_OF_PERICENTER": degrees(longitude_of_perigee - node),
            "MEAN_ANOMALY": degrees(longitude - longitude_of_perigee),
            "BSTAR": float(f"{bstar:.6e}") if rounded else bstar,
        }
    )
    return record


def satellite_of(record: dict[str, Any]) -> EarthSatellite:
    return EarthSatellite.from_omm(
        timescale(), {key: repr(v) if isinstance(v, float) else str(v) for key, v in record.items()}
    )


# --------------------------------------------------------------------------- the model


@dataclass
class _Group:
    """Observations of one station in one angle type and frame."""

    station: Station
    observations: list[Observation]
    set_index: int
    indices: list[int]  # each observation's place in the set

    @property
    def angle_type(self) -> str:
        return self.observations[0].angle_type

    @property
    def frame(self) -> str | None:
        return self.observations[0].frame

    def observed_units(self) -> np.ndarray:
        a1 = np.array([o.angle_1_deg for o in self.observations])
        a2 = np.array([o.angle_2_deg for o in self.observations])
        return unit_vectors(self.angle_type, a1, a2)

    def predicted_units(self, satellite) -> np.ndarray:
        found = predict(
            satellite,
            self.station,
            [o.time for o in self.observations],
            self.angle_type,
            self.frame,
        )
        return unit_vectors(self.angle_type, found.angle_1_deg, found.angle_2_deg)


def _groups(observation_sets: list[ObservationSet]) -> list[_Group]:
    groups: list[_Group] = []
    for set_index, observation_set in enumerate(observation_sets):
        by_kind: dict[tuple, list[int]] = {}
        for index, o in enumerate(observation_set.observations):
            by_kind.setdefault((o.angle_type, o.frame or ""), []).append(index)
        for key in sorted(by_kind):
            indices = by_kind[key]
            groups.append(
                _Group(
                    observation_set.station,
                    [observation_set.observations[i] for i in indices],
                    set_index,
                    indices,
                )
            )
    return groups


def track_middles(times: list[datetime], gap_s: float) -> list[datetime]:
    """The middle of each track: observations closer than ``gap_s`` in time are one."""
    ordered = sorted(times)
    tracks: list[list[datetime]] = []
    for t in ordered:
        if tracks and (t - tracks[-1][-1]).total_seconds() <= gap_s:
            tracks[-1].append(t)
        else:
            tracks.append([t])
    return [track[0] + (track[-1] - track[0]) / 2 for track in tracks]


@dataclass
class _Prior:
    """The start set's positions, with its measured errors, at fixed times."""

    times: list[datetime]
    positions: np.ndarray  # (k, 3) km
    axes: np.ndarray  # (k, 3, 3): radial, along-track and cross-track unit vectors
    sigma_km: np.ndarray  # (k, 3)
    terms: list[orbit_terms.OrbitTerm]


def _rtn(position: np.ndarray, velocity: np.ndarray) -> np.ndarray:
    radial = position / np.linalg.norm(position)
    normal = np.cross(position, velocity)
    normal = normal / np.linalg.norm(normal)
    return np.stack([radial, np.cross(normal, radial), normal])


def _positions(satellite, times: list[datetime]) -> tuple[np.ndarray, np.ndarray]:
    at = satellite.at(timescale().from_datetimes(times))
    return np.asarray(at.position.km).T, np.asarray(at.velocity.km_per_s).T


def _prior(start: ElementSet, middles: list[datetime]) -> _Prior | None:
    times: list[datetime] = []
    terms: list[orbit_terms.OrbitTerm] = []
    for t in [start.epoch, *middles]:
        if any(abs((t - u).total_seconds()) < PARAMETERS["track_gap_s"] for u in times):
            continue
        age = abs((t - start.epoch).total_seconds()) / 86400
        term = orbit_terms.term_for(start.record, age)
        if term is not None:
            times.append(t)
            terms.append(term)
    if not times:
        return None
    positions, velocities = _positions(start.satellite, times)
    axes = np.stack([_rtn(p, v) for p, v in zip(positions, velocities, strict=True)])
    scale = PARAMETERS["start_set_sigma_from_p90"]
    sigma = np.array([[t.radial_km, t.in_track_km, t.cross_track_km] for t in terms]) / scale
    return _Prior(times, positions, axes, sigma, terms)


class _Model:
    """Normalised residuals of a candidate orbit: the observations' along and across the
    apparent motion at the current orbit, then the start set's positions."""

    def __init__(self, start: ElementSet, groups: list[_Group], prior: _Prior | None):
        self.start = start
        self.groups = groups
        self.prior = prior
        self.observed = [g.observed_units() for g in groups]
        self.active = [np.ones(len(g.observations), dtype=bool) for g in groups]
        self.axes: list[tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]] = []

    def set_axes(self, satellite) -> None:
        """The motion's directions, rates and sigmas at the current orbit; held fixed while
        the Jacobian is taken."""
        self.axes = []
        for g in self.groups:
            res = residuals(satellite, g.station, g.observations)
            sigma_angle = np.array([o.angle_uncertainty_arcsec for o in g.observations])
            sigma_time = np.array([o.time_uncertainty_s for o in g.observations])
            sigma_along = np.sqrt(sigma_angle**2 + (sigma_time * res.rate_arcsec_per_s) ** 2)
            self.axes.append((res.along_unit, res.cross_unit, sigma_along, sigma_angle))

    def observation_residuals(self, satellite) -> list[tuple[np.ndarray, np.ndarray]]:
        """Along and across, in arcseconds, observed minus predicted, for each group."""
        found = []
        for g, observed, (u, c, _, _) in zip(self.groups, self.observed, self.axes, strict=True):
            diff = observed - g.predicted_units(satellite)
            found.append(
                (
                    np.sum(diff * u, axis=0) * ARCSEC_PER_RAD,
                    np.sum(diff * c, axis=0) * ARCSEC_PER_RAD,
                )
            )
        return found

    def prior_residuals(self, satellite) -> np.ndarray:
        if self.prior is None:
            return np.zeros(0)
        positions, _ = _positions(satellite, self.prior.times)
        diff = self.prior.positions - positions
        return (np.einsum("kij,kj->ki", self.prior.axes, diff) / self.prior.sigma_km).ravel()

    def vector(self, record: dict[str, Any]) -> np.ndarray:
        satellite = satellite_of(record)
        parts = []
        for (along, cross), (_, _, s_along, s_cross), active in zip(
            self.observation_residuals(satellite), self.axes, self.active, strict=True
        ):
            parts.append((along / s_along)[active])
            parts.append((cross / s_cross)[active])
        parts.append(self.prior_residuals(satellite))
        return np.concatenate(parts)


# --------------------------------------------------------------------------- the fit


@dataclass
class _State:
    x: np.ndarray
    cost: float
    iterations: int
    converged: bool
    jacobian: np.ndarray
    free: list[int]


def _jacobian(model: _Model, x: np.ndarray, free: list[int]) -> np.ndarray:
    columns = []
    for j in free:
        step = np.zeros_like(x)
        step[j] = STEPS[j]
        plus = model.vector(to_record(model.start.record, x + step))
        minus = model.vector(to_record(model.start.record, x - step))
        columns.append((plus - minus) / (2 * STEPS[j]))
    return np.stack(columns, axis=1)


def _solve(model: _Model, x0: np.ndarray, free: list[int]) -> _State:
    x = x0.copy()
    model.set_axes(satellite_of(to_record(model.start.record, x)))
    r = model.vector(to_record(model.start.record, x))
    cost = float(r @ r)
    damping = PARAMETERS["damping_start"]
    converged = False
    iterations = 0
    jacobian = _jacobian(model, x, free)
    while iterations < PARAMETERS["max_iterations"]:
        iterations += 1
        normal = jacobian.T @ jacobian
        gradient = jacobian.T @ r
        diagonal = np.diag(np.diag(normal))
        accepted = False
        for _ in range(PARAMETERS["damping_tries"]):
            delta = np.linalg.solve(normal + damping * diagonal, -gradient)
            trial = x.copy()
            trial[free] += delta
            r_trial = model.vector(to_record(model.start.record, trial))
            cost_trial = float(r_trial @ r_trial)
            if cost_trial < cost:
                accepted = True
                break
            damping *= 10.0
        if not accepted:
            converged = True  # no step lowers the cost: a minimum
            break
        sigma = np.sqrt(np.diag(np.linalg.inv(normal)))
        small_step = bool(np.all(np.abs(delta) < PARAMETERS["min_step_in_sigma"] * sigma))
        small_gain = (cost - cost_trial) < PARAMETERS["min_relative_cost_decrease"] * cost
        x, cost = trial, cost_trial
        damping = max(damping / 10.0, 1e-12)
        model.set_axes(satellite_of(to_record(model.start.record, x)))
        r = model.vector(to_record(model.start.record, x))
        cost = float(r @ r)
        jacobian = _jacobian(model, x, free)
        if small_step or small_gain:
            converged = True
            break
    return _State(x, cost, iterations, converged, jacobian, free)


def _normalised(model: _Model, satellite) -> list[np.ndarray]:
    return [
        np.hypot(along / s_along, cross / s_cross)
        for (along, cross), (_, _, s_along, s_cross) in zip(
            model.observation_residuals(satellite), model.axes, strict=True
        )
    ]


def _worst_outlier(model: _Model, satellite) -> tuple[int, int] | None:
    """The used observation furthest off, if it is more than the threshold off."""
    worst = None
    for gi, values in enumerate(_normalised(model, satellite)):
        for k, value in enumerate(values):
            if model.active[gi][k] and value > PARAMETERS["outlier_threshold_sigma"]:
                key = (-float(value), gi, k)
                if worst is None or key < worst:
                    worst = key
    return None if worst is None else (worst[1], worst[2])


def _r(value: float, digits: int) -> float:
    return round(float(value), digits)


def _sig(value: float) -> float:
    return float(f"{float(value):.6e}")


def set_sha256(observation_set: ObservationSet) -> str:
    """SHA-256 of an observation set as compact canonical JSON, whatever its file format."""
    return sha256_bytes(dumps_compact(observation_set.to_document()).encode("utf-8"))


def fit(
    start: ElementSet,
    observation_sets: list[ObservationSet],
    *,
    simulated_catalog: bool = False,
) -> dict[str, Any]:
    """Fit the start set's object to the observation sets: the fit's document."""
    norad = start.norad_id
    if not observation_sets:
        raise FitError("no observation sets to fit")
    for s in observation_sets:
        if s.target.norad_id != norad:
            raise FitError(
                f"an observation set is of object {s.target.norad_id}, the start set of {norad}"
            )
    groups = _groups(observation_sets)
    times = [o.time for g in groups for o in g.observations]
    if len(times) < 4:
        raise FitError(f"{len(times)} observation(s): a fit needs at least 4")
    span_days = (max(times) - min(times)).total_seconds() / 86400
    free = list(range(7 if span_days >= PARAMETERS["bstar_min_span_days"] else 6))
    middles = track_middles(times, PARAMETERS["track_gap_s"])
    prior = _prior(start, middles)
    model = _Model(start, groups, prior)

    x0 = to_equinoctial(start.record)
    state = _solve(model, x0, free)
    iterations = state.iterations
    # The worst observation more than the threshold off is left out and the fit made
    # again, one at a time: a far one pulls the first fit towards it, and others with it.
    allowed = math.floor(PARAMETERS["max_outlier_fraction"] * len(times))
    for _ in range(allowed):
        found = _worst_outlier(model, satellite_of(to_record(start.record, state.x)))
        if found is None:
            break
        model.active[found[0]][found[1]] = False
        state = _solve(model, state.x, free)
        iterations += state.iterations

    record = to_record(start.record, state.x, rounded=True)
    satellite = satellite_of(record)
    model.set_axes(satellite)
    observation_residuals = model.observation_residuals(satellite)
    normal = state.jacobian.T @ state.jacobian
    covariance = np.linalg.inv(normal)

    per_observation = []
    used_along, used_cross, used_norm = [], [], []
    for g, (along, cross), (_, _, s_along, s_cross), active in zip(
        groups, observation_residuals, model.axes, model.active, strict=True
    ):
        for k, o in enumerate(g.observations):
            norm = math.hypot(along[k] / s_along[k], cross[k] / s_cross[k])
            per_observation.append(
                {
                    "set": g.set_index,
                    "index": g.indices[k],
                    "time": format_utc(o.time),
                    "along_track_arcsec": _r(along[k], 2),
                    "cross_track_arcsec": _r(cross[k], 2),
                    "normalised_residual": _r(norm, 3),
                    "used": bool(active[k]),
                }
            )
            if active[k]:
                used_along.append(along[k])
                used_cross.append(cross[k])
                used_norm.append(norm)
    per_observation.sort(key=lambda p: (p["set"], p["index"]))

    def rms(values: list[float]) -> float:
        return _r(math.sqrt(sum(v * v for v in values) / len(values)), 2) if values else 0.0

    last = max(times)
    sigma_last = _position_sigma(start.record, state.x, free, covariance, last)
    difference = _start_difference(start, satellite, last)
    simulated = simulated_catalog or any(s.simulated for s in observation_sets)
    inputs = {
        "start_set": {
            "norad_id": norad,
            "epoch": format_utc(start.epoch),
            "sha256": start.sha256,
            "kind": orbit_terms.kinds_for(start.record)[0],
        },
        "observation_sets": [
            {
                "sha256": set_sha256(s),
                "station": s.station.id,
                "observations": len(s.observations),
                "first": format_utc(min(o.time for o in s.observations)),
                "last": format_utc(max(o.time for o in s.observations)),
            }
            for s in observation_sets
        ],
    }
    identity = {
        "method": f"{METHOD_NAME} {METHOD_VERSION}",
        "start_set": start.sha256,
        "observation_sets": [i["sha256"] for i in inputs["observation_sets"]],
    }
    document: dict[str, Any] = {
        "format": FORMAT,
        "format_version": FORMAT_VERSION,
        "simulated": simulated,
        "notice": SIMULATION_NOTICE if simulated else NOT_FOR_PUBLICATION,
        "fit_id": sha256_bytes(dumps_compact(identity).encode("utf-8")),
        "method": {
            "name": METHOD_NAME,
            "version": METHOD_VERSION,
            "parameters": PARAMETERS,
            "fitted": [NAMES[j] for j in free],
        },
        "inputs": inputs,
        "result": {
            "converged": state.converged,
            "iterations": iterations,
            "observations": len(times),
            "used": len(used_norm),
            "dropped_as_outliers": len(times) - len(used_norm),
            "span_days": _r(span_days, 4),
            "rms_along_track_arcsec": rms(used_along),
            "rms_cross_track_arcsec": rms(used_cross),
            "rms_normalised_residual": _r(
                math.sqrt(sum(v * v for v in used_norm) / len(used_norm)), 3
            )
            if used_norm
            else 0.0,
            "start_set_terms": [
                {"time": format_utc(t), **term.public()}
                for t, term in zip(prior.times, prior.terms, strict=True)
            ]
            if prior
            else [],
            "position_sigma_km_at_last_observation": sigma_last,
            "difference_from_start_set_km_at_last_observation": difference,
            "covariance": {
                "parameters": [NAMES[j] for j in free],
                "matrix": [[_sig(v) for v in row] for row in covariance],
            },
            "omm": record,
        },
        "per_observation": per_observation,
    }
    return document


def _position_sigma(
    start: dict[str, Any], x: np.ndarray, free: list[int], covariance: np.ndarray, when: datetime
) -> dict[str, float]:
    """One standard deviation of the fitted position at a time: radially, along the track
    and across it."""
    position, velocity = _positions(satellite_of(to_record(start, x)), [when])
    axes = _rtn(position[0], velocity[0])
    columns = []
    for j in free:
        step = np.zeros_like(x)
        step[j] = STEPS[j]
        plus, _ = _positions(satellite_of(to_record(start, x + step)), [when])
        minus, _ = _positions(satellite_of(to_record(start, x - step)), [when])
        columns.append(axes @ (plus[0] - minus[0]) / (2 * STEPS[j]))
    g = np.stack(columns, axis=1)
    sigma = np.sqrt(np.diag(g @ covariance @ g.T))
    return {
        "time": format_utc(when),
        "radial": _r(sigma[0], 3),
        "in_track": _r(sigma[1], 3),
        "cross_track": _r(sigma[2], 3),
    }


def _start_difference(start: ElementSet, fitted, when: datetime) -> dict[str, float]:
    """The fitted orbit's position minus the start set's at a time, in the start set's
    radial, along-track and cross-track directions."""
    p_start, v_start = _positions(start.satellite, [when])
    p_fit, _ = _positions(fitted, [when])
    d = _rtn(p_start[0], v_start[0]) @ (p_fit[0] - p_start[0])
    return {
        "time": format_utc(when),
        "radial": _r(d[0], 3),
        "in_track": _r(d[1], 3),
        "cross_track": _r(d[2], 3),
    }


def start_set_for(element_sets: list[ElementSet], observation_sets: list[ObservationSet]):
    """The set to start from: the one whose epoch is nearest the middle of the
    observations, as verification picks one (P5-04)."""
    times = [o.time for s in observation_sets for o in s.observations]
    middle = min(times) + (max(times) - min(times)) / 2
    return min(
        element_sets,
        key=lambda s: (abs((s.epoch - middle).total_seconds()), s.epoch, s.sha256),
    )


def render_text(document: dict[str, Any]) -> str:
    """A fit's summary for the terminal."""
    result = document["result"]
    start = document["inputs"]["start_set"]
    sigma = result["position_sigma_km_at_last_observation"]
    moved = result["difference_from_start_set_km_at_last_observation"]
    lines = [
        f"Orbit fit {document['fit_id']}",
        f"  method {document['method']['name']} {document['method']['version']}; "
        f"fitted: {', '.join(document['method']['fitted'])}",
        f"  object {start['norad_id']}, from the {start['kind']} set of {start['epoch']} "
        f"({start['sha256'][:12]}...)",
        f"  {result['used']} of {result['observations']} observations used "
        f"({result['dropped_as_outliers']} dropped as outliers), "
        f"{len(document['inputs']['observation_sets'])} set(s) over "
        f"{result['span_days']:g} days",
        f"  {'converged' if result['converged'] else 'NOT converged'} in "
        f"{result['iterations']} iterations",
        f'  RMS {result["rms_along_track_arcsec"]:g}" along the motion, '
        f'{result["rms_cross_track_arcsec"]:g}" across it; normalised '
        f"{result['rms_normalised_residual']:g}",
        f"  at the last observation ({sigma['time']}): 1 sigma {sigma['radial']:g} km "
        f"radially, {sigma['in_track']:g} km along the track, {sigma['cross_track']:g} km "
        "across it",
        f"  moved from the start set by {moved['radial']:g}, {moved['in_track']:g} and "
        f"{moved['cross_track']:g} km",
        f"  {document['notice']}",
    ]
    return "\n".join(lines) + "\n"

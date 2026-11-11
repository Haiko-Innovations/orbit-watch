"""Station quality meter: how accurate are my observations?

An observer runs their own observations (JSON, IOD or TDM) through the meter.
It compares every observation with the public reference orbit of the object
and reports:

* **angle precision**: the scatter of the cross-track residuals around a
  straight-line trend within each pass. Errors of the reference orbit are
  smooth over a pass, so the scatter mostly measures the station itself;
* **timing precision**: the same for the along-track residuals in seconds;
* **timing offset**: the mean along-track offset in seconds per object. An
  offset shared by several objects points to the station clock; offsets that
  differ between objects are more likely errors of the reference orbits;
* **development over time**: the same numbers per observing night.

The reference orbit is only good to about a kilometre, so absolute residuals
are not a measure of station quality on their own. The meter says so in its
output.
"""

from __future__ import annotations

import itertools
import math
from collections import defaultdict
from dataclasses import dataclass
from datetime import timedelta
from typing import Any

import numpy as np

from orbit_watch import SIMULATION_NOTICE, __version__
from orbit_watch.catalog import Catalog, CatalogError
from orbit_watch.geometry import residuals
from orbit_watch.model import Observation, ObservationSet, Station
from orbit_watch.timeutil import format_utc

REPORT_FORMAT = "orbit-watch/station-quality-report"
REPORT_FORMAT_VERSION = "1.0"
METHOD_VERSION = "1.0.0"
MAX_REFERENCE_AGE_DAYS = 7.0
PASS_GAP_S = 900.0  # a gap longer than this starts a new pass
MIN_POINTS_FOR_SCATTER = 4
CLOCK_OFFSET_MIN_S = 0.05  # smaller timing offsets are not reported as clock errors
ORBIT_NOTE = (
    "Residuals include the error of the public reference orbit (about a kilometre at epoch, "
    "growing with age). Offsets shared by several objects point to the station; offsets of "
    "single objects are more likely orbit errors."
)


def _r(value: float | None, digits: int) -> float | None:
    return None if value is None else round(float(value), digits)


@dataclass
class _Point:
    norad_id: int
    observation: Observation
    pass_index: int
    along_s: float
    cross_arcsec: float
    separation_arcsec: float


def _night(observation: Observation, station: Station) -> str:
    """Observing night, as the local solar date at the start of the night."""
    local = observation.time + timedelta(hours=station.longitude_deg / 15.0) - timedelta(hours=12)
    return local.date().isoformat()


def _scatter(points: list[_Point], attribute: str) -> float | None:
    """One-sigma scatter of a residual component around a linear trend per pass."""
    by_pass: dict[tuple[int, int], list[_Point]] = defaultdict(list)
    for p in points:
        by_pass[(p.norad_id, p.pass_index)].append(p)
    squares, dof = 0.0, 0
    for group in by_pass.values():
        if len(group) < MIN_POINTS_FOR_SCATTER:
            continue
        t = np.array([g.observation.time.timestamp() for g in group])
        t = t - t.mean()
        values = np.array([getattr(g, attribute) for g in group])
        fitted = np.polyval(np.polyfit(t, values, 1), t)
        squares += float(np.sum((values - fitted) ** 2))
        dof += len(group) - 2
    if dof == 0:
        return None
    return math.sqrt(squares / dof)


def _mean_along(points: list[_Point]) -> float:
    return float(np.mean([p.along_s for p in points]))


def _collect(
    observation_sets: list[ObservationSet], catalog: Catalog, station: Station
) -> tuple[list[_Point], list[str]]:
    notices: list[str] = []
    points: list[_Point] = []
    stale = 0
    for observation_set in observation_sets:
        norad = observation_set.target.norad_id
        if norad not in catalog:
            notices.append(f"Object {norad} was left out: no reference orbit in the catalogue.")
            continue
        try:
            satellite = catalog.satellite(norad)
        except CatalogError as exc:
            notices.append(f"Object {norad} was left out: {exc}.")
            continue
        epoch = satellite.epoch.utc_datetime()
        usable = [
            o
            for o in observation_set.observations
            if abs((o.time - epoch).total_seconds()) <= MAX_REFERENCE_AGE_DAYS * 86400
        ]
        stale += len(observation_set.observations) - len(usable)
        groups: dict[tuple, list[Observation]] = defaultdict(list)
        for o in usable:
            groups[(o.angle_type, o.frame)].append(o)
        for group in groups.values():
            group.sort(key=lambda o: o.time)
            res = residuals(satellite, station, group)
            pass_index, previous = 0, None
            for i, o in enumerate(group):
                if previous is not None and (o.time - previous).total_seconds() > PASS_GAP_S:
                    pass_index += 1
                previous = o.time
                points.append(
                    _Point(
                        norad,
                        o,
                        pass_index,
                        float(res.along_s[i]),
                        float(res.cross_arcsec[i]),
                        float(res.separation_arcsec[i]),
                    )
                )
    if stale:
        notices.insert(
            0,
            f"{stale} observation(s) are more than {MAX_REFERENCE_AGE_DAYS:g} days "
            "from the epoch of their reference orbit and were left out.",
        )
    return points, notices


def score_station(observation_sets: list[ObservationSet], catalog: Catalog) -> dict[str, Any]:
    """Quality report for the observations of one station."""
    stations = {s.station.id for s in observation_sets}
    if len(stations) != 1:
        raise ValueError(f"score one station at a time (found {', '.join(sorted(stations))})")
    station = observation_sets[0].station
    points, notices = _collect(observation_sets, catalog, station)
    simulated = any(s.simulated for s in observation_sets) or catalog.simulated

    report: dict[str, Any] = {
        "report_format": REPORT_FORMAT,
        "report_format_version": REPORT_FORMAT_VERSION,
        "method_version": METHOD_VERSION,
        "software": {"orbit-watch": __version__},
        "simulated_input": simulated,
        "station": station.to_document(),
    }
    if simulated:
        report["notice"] = "Inputs include SIMULATED data. " + SIMULATION_NOTICE
    if not points:
        report["summary"] = "No observations could be compared with a reference orbit."
        report["notices"] = notices
        return report

    by_object: dict[int, list[_Point]] = defaultdict(list)
    by_night: dict[str, list[_Point]] = defaultdict(list)
    for p in points:
        by_object[p.norad_id].append(p)
        by_night[_night(p.observation, station)].append(p)

    def summary_row(group: list[_Point]) -> dict[str, Any]:
        return {
            "observations": len(group),
            "angle_scatter_arcsec": _r(_scatter(group, "cross_arcsec"), 3),
            "timing_scatter_s": _r(_scatter(group, "along_s"), 4),
            "mean_along_track_s": _r(_mean_along(group), 4),
        }

    objects = []
    for norad in sorted(by_object):
        group = by_object[norad]
        objects.append(
            {
                "norad_id": norad,
                "name": catalog.name(norad),
                "passes": len({p.pass_index for p in group}),
                "median_residual_arcsec": _r(np.median([p.separation_arcsec for p in group]), 3),
                **summary_row(group),
            }
        )
    nights = []
    for night in sorted(by_night):
        group = by_night[night]
        nights.append(
            {"night": night, "objects": len({p.norad_id for p in group}), **summary_row(group)}
        )

    declared_angle = sorted({p.observation.angle_uncertainty_arcsec for p in points})
    declared_time = sorted({p.observation.time_uncertainty_s for p in points})
    overall = {
        "objects": len(by_object),
        "nights": len(nights),
        **summary_row(points),
        "declared_angle_uncertainty_arcsec": declared_angle,
        "declared_time_uncertainty_s": declared_time,
    }
    times = [p.observation.time for p in points]
    report["summary"] = (
        f"{len(points)} observations of {len(by_object)} object(s) on {len(nights)} night(s), "
        f"{format_utc(min(times))} to {format_utc(max(times))}."
    )
    report["overall"] = overall
    report["findings"] = _findings(overall, objects, nights)
    report["objects"] = objects
    report["nights"] = nights
    report["notices"] = [*notices, ORBIT_NOTE]
    return report


def _compare(measured: float | None, declared: list[float], unit: str, what: str) -> str:
    if measured is None:
        return (
            f"Not enough observations per pass (at least {MIN_POINTS_FOR_SCATTER}) to "
            f"estimate your {what}."
        )
    declared_text = "/".join(f"{d:g}" for d in declared) + unit
    shown = f"{measured:.1f}{unit}" if unit == "″" else f"{measured:.3f}{unit}"
    if measured > 1.5 * max(declared):
        verdict = (
            f"larger than the uncertainty you declare ({declared_text}). Consider "
            "declaring a larger uncertainty"
        )
    elif measured < 0.5 * min(declared):
        verdict = (
            f"well below the uncertainty you declare ({declared_text}). You could "
            "declare a smaller uncertainty"
        )
    else:
        verdict = f"consistent with the uncertainty you declare ({declared_text})"
    return f"Your {what} is {shown}, {verdict}."


def _findings(overall: dict, objects: list[dict], nights: list[dict]) -> list[str]:
    findings = [
        _compare(
            overall["angle_scatter_arcsec"],
            overall["declared_angle_uncertainty_arcsec"],
            "″",
            "angle precision (cross-track scatter within passes)",
        ),
        _compare(
            overall["timing_scatter_s"],
            overall["declared_time_uncertainty_s"],
            " s",
            "timing precision (along-track scatter within passes)",
        ),
    ]
    latest = nights[-1]
    latest_objects = latest["objects"]
    offset = latest["mean_along_track_s"]
    scope = "on the latest night" if len(nights) > 1 else "in these observations"
    if latest_objects >= 2 and abs(offset) >= CLOCK_OFFSET_MIN_S:
        clock = "ahead of" if offset < 0 else "behind"
        findings.append(
            f"{latest_objects} objects appear on average {abs(offset):.2f} s "
            f"{'behind' if offset < 0 else 'ahead of'} their predictions {scope}. A shared "
            f"offset points to your clock: your timestamps seem to run about {abs(offset):.2f} s "
            f"{clock} UTC. Check the time synchronisation (GPS/PPS or NTP) and the exposure timing."
        )
    elif latest_objects == 1 and abs(offset) >= CLOCK_OFFSET_MIN_S:
        findings.append(
            f"The object appears {abs(offset):.2f} s {'behind' if offset < 0 else 'ahead of'} its "
            f"prediction {scope}. With one object this cannot be told apart from an error of its "
            "reference orbit; observe more objects to check your clock."
        )
    else:
        findings.append(f"No systematic timing offset was found {scope}.")
    for earlier, later in itertools.pairwise(nights):
        change = later["mean_along_track_s"] - earlier["mean_along_track_s"]
        if abs(change) >= CLOCK_OFFSET_MIN_S:
            findings.append(
                f"The mean timing offset changed from {earlier['mean_along_track_s']:+.2f} s "
                f"(night of {earlier['night']}) to {later['mean_along_track_s']:+.2f} s "
                f"(night of {later['night']})."
            )
    return findings


def _cell(value: float | None, fmt: str) -> str:
    return "-" if value is None else format(value, fmt)


def render_text(report: dict[str, Any]) -> str:
    station = report["station"]
    lines = [f"Orbit Watch station quality meter {report['method_version']}"]
    if report.get("simulated_input"):
        lines.append("Inputs include SIMULATED data.")
    lines.append(
        f"Station {station['id']} ({station['latitude_deg']:.4f}, "
        f"{station['longitude_deg']:.4f}, {station['altitude_m']:g} m)"
    )
    lines.append(report["summary"])
    if "overall" not in report:
        lines.extend(f"Note: {n}" for n in report.get("notices", []))
        return "\n".join(lines) + "\n"
    lines += ["", "Findings"]
    lines.extend(f"  - {f}" for f in report["findings"])
    header = f"{'obs':>5}{'angle':>9}{'timing':>9}{'offset':>9}"
    lines += ["", "Per object", f"  {'object':<9}{'name':<30}{'passes':>7}{header}"]
    for o in report["objects"]:
        lines.append(
            f"  {o['norad_id']:<9}{o['name'][:29]:<30}{o['passes']:>7}{o['observations']:>5}"
            f"{_cell(o['angle_scatter_arcsec'], '.1f'):>8}″"
            f"{_cell(o['timing_scatter_s'], '.3f'):>8}s{o['mean_along_track_s']:>+8.3f}s"
        )
    lines += ["", "Per night (development over time)", f"  {'night of':<12}{'objects':>8}{header}"]
    for n in report["nights"]:
        lines.append(
            f"  {n['night']:<12}{n['objects']:>8}{n['observations']:>5}"
            f"{_cell(n['angle_scatter_arcsec'], '.1f'):>8}″"
            f"{_cell(n['timing_scatter_s'], '.3f'):>8}s{n['mean_along_track_s']:>+8.3f}s"
        )
    lines += [
        "",
        "angle = cross-track scatter within passes, timing = along-track scatter within passes,",
        "offset = mean along-track offset (positive: the object is ahead of its prediction).",
    ]
    lines.extend(f"Note: {n}" for n in report["notices"])
    return "\n".join(lines) + "\n"

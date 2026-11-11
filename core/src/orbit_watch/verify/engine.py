"""Deterministic, versioned automated verification of observation deliveries.

The report names the method and its version, the SHA-256 of every input and
the result of every check with its reasoning. Anyone with the same inputs and
the same software versions gets a byte-identical report.

This is a prototype. It is not production-ready scientific validation.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from importlib import metadata
from typing import Any

import numpy as np

from orbit_watch import SIMULATION_NOTICE, __version__
from orbit_watch.canonical import sha256_bytes
from orbit_watch.catalog import Catalog, CatalogError, parse_catalog
from orbit_watch.documents import Request, TargetPolicy
from orbit_watch.formats import FormatError, Sites, detect_format, load_observation_sets
from orbit_watch.geometry import residuals
from orbit_watch.model import Observation, ObservationSet
from orbit_watch.timeutil import format_utc

REPORT_FORMAT = "orbit-watch/verification-report"
REPORT_FORMAT_VERSION = "1.0"
METHOD_NAME = "orbit-watch-automated-verification"
METHOD_VERSION = "1.0.0"
ACCEPTED_OBSERVATION_FORMATS = [
    "orbit-watch/observation-set 1.0",
    "iod",
    "ccsds-tdm 1.0/2.0 subset",
]

PARAMETERS: dict[str, float] = {
    # Assumed error of the public reference orbit (GP elements are good to about
    # a kilometre at epoch and degrade quickly; 5 km tolerates a few days).
    "reference_position_error_km": 5.0,
    # Each observation may deviate by this many declared sigmas (angle and timing).
    "residual_sigma_multiplier": 3.0,
    # Share of observations that must lie within their limit.
    "min_fraction_within_limit": 0.8,
    # Beyond this distance from the reference epoch the residual check is inconclusive.
    "max_reference_age_days": 7.0,
    # Two observations are the same if they agree to these resolutions.
    "duplicate_time_resolution_s": 0.001,
    "duplicate_angle_resolution_arcsec": 1.0,
}

DISCLAIMER = (
    "Automated verification by a prototype method. It compares the observations with a "
    "public reference orbit and the request terms; it is not production-ready scientific "
    "validation and does not prove that the measurements are physically correct."
)

CHECK_TITLES = {
    "format": "Required fields and format",
    "simulation_label": "Simulation labels are consistent",
    "target_allowed": "Target is on the allow-list",
    "target_match": "Target matches the request",
    "time_window": "Observations are inside the time window",
    "min_observations": "Minimum number of observations",
    "declared_uncertainty": "Declared uncertainty meets the requirements",
    "hash_match": "File matches the declared hash",
    "duplicates": "No duplicates or resubmissions",
    "orbit_residuals": "Residuals against the public reference orbit",
}
CHECK_ORDER = list(CHECK_TITLES)


class UsageError(ValueError):
    """The verifier itself was given invalid inputs (not a property of the delivery)."""


@dataclass
class VerificationInput:
    request: bytes
    observations: bytes
    catalog: bytes
    policy: bytes
    observations_format: str | None = None
    previous: list[bytes] = field(default_factory=list)
    declared_sha256: str | None = None
    sites: Sites | None = None


def _r(value: float, digits: int) -> float:
    return round(float(value), digits)


def _software() -> dict[str, str]:
    versions = {"orbit-watch": __version__}
    for package in ("skyfield", "sgp4", "numpy"):
        versions[package] = metadata.version(package)
    return versions


def _check(check_id: str, result: str, reason: str, details: dict | None = None) -> dict[str, Any]:
    entry: dict[str, Any] = {
        "id": check_id,
        "title": CHECK_TITLES[check_id],
        "result": result,
        "reason": reason,
    }
    if details:
        entry["details"] = details
    return entry


def _skip_all(checks: dict[str, dict], reason: str) -> None:
    for check_id in CHECK_ORDER:
        if check_id not in checks:
            checks[check_id] = _check(check_id, "skip", reason)


def _fingerprint(norad_id: int, obs: Observation) -> tuple:
    millis = round(obs.time.timestamp() / PARAMETERS["duplicate_time_resolution_s"])
    res = PARAMETERS["duplicate_angle_resolution_arcsec"]
    return (
        norad_id,
        millis,
        obs.angle_type,
        round(obs.angle_1_deg * 3600 / res),
        round(obs.angle_2_deg * 3600 / res),
    )


def _load_single_set(
    data: bytes, fmt: str | None, sites: Sites | None
) -> tuple[str, ObservationSet]:
    detected = fmt or detect_format("", data)
    loaded = load_observation_sets("delivery", data=data, input_format=detected, sites=sites)
    if len(loaded.sets) != 1:
        raise FormatError(
            f"the file holds {len(loaded.sets)} station/object groups; "
            "a delivery must hold exactly one"
        )
    return loaded.format, loaded.sets[0]


def verify(inp: VerificationInput) -> dict[str, Any]:
    try:
        request = Request.parse(inp.request)
        policy = TargetPolicy.parse(inp.policy)
    except FormatError as exc:
        raise UsageError(f"{exc}: {'; '.join(exc.problems[:5])}") from None
    try:
        catalog = parse_catalog(inp.catalog)
    except (CatalogError, ValueError) as exc:
        raise UsageError(f"invalid reference catalogue: {exc}") from None

    checks: dict[str, dict[str, Any]] = {}
    observation_set: ObservationSet | None = None
    fmt_label = inp.observations_format or detect_format("", inp.observations)
    fmt_names = {"json": "Orbit Watch JSON", "iod": "IOD", "tdm": "CCSDS TDM"}
    try:
        fmt_label, observation_set = _load_single_set(
            inp.observations, inp.observations_format, inp.sites
        )
    except FormatError as exc:
        problems = exc.problems[:20]
        first = problems[0] if problems else str(exc)
        reason = f"The file is not a valid {fmt_names.get(fmt_label, fmt_label)} file: {first}"
        if len(exc.problems) > 1:
            reason += f" (and {len(exc.problems) - 1} more problem(s))"
        reason += "."
        details = {"problems": problems} if problems else {"error": str(exc)}
        checks["format"] = _check("format", "fail", reason, details)
        _skip_all(checks, "Not evaluated because the file could not be read.")

    if observation_set is not None:
        obs = observation_set.observations
        checks["format"] = _check(
            "format",
            "pass",
            f"Valid {fmt_names.get(fmt_label, fmt_label)} with {len(obs)} observation(s) "
            f"from station {observation_set.station.id}.",
        )
        checks["simulation_label"] = _simulation_label(request, observation_set)
        checks["target_allowed"] = _target_allowed(request, policy)
        checks["target_match"] = _target_match(request, observation_set)
        checks["time_window"] = _time_window(request, obs)
        checks["min_observations"] = _min_observations(request, obs)
        checks["declared_uncertainty"] = _declared_uncertainty(request, obs)
        checks["hash_match"] = _hash_match(inp)
        checks["duplicates"] = _duplicates(inp, observation_set)
        checks["orbit_residuals"] = _orbit_residuals(request, catalog, observation_set)

    ordered = [checks[c] for c in CHECK_ORDER]
    failed = [c for c in ordered if c["result"] == "fail"]
    inconclusive = [c for c in ordered if c["result"] == "inconclusive"]
    if failed:
        verdict = "fail"
        names = ", ".join(c["title"].lower() for c in failed)
        summary = f"FAIL: {len(failed)} check(s) failed: {names}."
    elif inconclusive:
        verdict = "inconclusive"
        names = ", ".join(c["title"].lower() for c in inconclusive)
        summary = f"INCONCLUSIVE: no check failed, but these could not be decided: {names}."
    else:
        verdict = "pass"
        passed = sum(1 for c in ordered if c["result"] == "pass")
        summary = f"PASS: all {passed} applicable checks passed."

    simulated = bool(
        request.simulated
        or catalog.simulated
        or policy.simulated
        or (observation_set is not None and observation_set.simulated)
    )
    report: dict[str, Any] = {
        "report_format": REPORT_FORMAT,
        "report_format_version": REPORT_FORMAT_VERSION,
        "verdict": verdict,
        "summary": summary,
        "simulated_input": simulated,
    }
    if simulated:
        report["notice"] = "Inputs include SIMULATED data. " + SIMULATION_NOTICE
    report["disclaimer"] = DISCLAIMER
    report["method"] = {
        "name": METHOD_NAME,
        "version": METHOD_VERSION,
        "parameters": dict(PARAMETERS),
        "accepted_observation_formats": ACCEPTED_OBSERVATION_FORMATS,
    }
    report["software"] = _software()
    report["inputs"] = {
        "request_sha256": sha256_bytes(inp.request),
        "observations_sha256": sha256_bytes(inp.observations),
        "observations_format": fmt_label,
        "declared_sha256": inp.declared_sha256,
        "reference_catalog_sha256": sha256_bytes(inp.catalog),
        "target_policy_sha256": sha256_bytes(inp.policy),
        "previous_deliveries_sha256": sorted(sha256_bytes(p) for p in inp.previous),
    }
    report["request"] = {
        "request_id": request.request_id,
        "target_norad_id": request.norad_id,
        "window_start": format_utc(request.window_start),
        "window_end": format_utc(request.window_end),
        "min_observations": request.min_observations,
        "max_angle_uncertainty_arcsec": request.max_angle_uncertainty_arcsec,
        "max_time_uncertainty_s": request.max_time_uncertainty_s,
    }
    if request.norad_id in catalog:
        record = catalog.record(request.norad_id)
        report["reference_orbit"] = {
            "norad_id": request.norad_id,
            "object_name": str(record.get("OBJECT_NAME")),
            "epoch": str(record.get("EPOCH")),
            "element_set_no": str(record.get("ELEMENT_SET_NO")),
            "propagator": "SGP4 (sgp4 library via Skyfield)",
        }
    report["checks"] = ordered
    return report


def _simulation_label(request: Request, observation_set: ObservationSet) -> dict[str, Any]:
    if observation_set.simulated and not request.simulated:
        return _check(
            "simulation_label",
            "fail",
            "The observations are marked as SIMULATED, so they cannot fulfil a real request.",
        )
    if observation_set.simulated:
        return _check(
            "simulation_label",
            "pass",
            "Both the request and the observations are marked as simulated.",
        )
    if request.simulated:
        return _check(
            "simulation_label",
            "pass",
            "The request is simulated; the observations are marked as real.",
        )
    return _check(
        "simulation_label",
        "pass",
        "Neither the request nor the observations are marked as simulated.",
    )


def _target_allowed(request: Request, policy: TargetPolicy) -> dict[str, Any]:
    name = request.target_name or policy.allowed.get(request.norad_id) or ""
    label = f"{request.norad_id}" + (f", {name}," if name else "")
    if policy.allows(request.norad_id):
        return _check("target_allowed", "pass", f"Target {label} is on the allow-list.")
    return _check(
        "target_allowed",
        "fail",
        f"Target {label} is not on the allow-list. Orbit Watch only accepts requests for "
        "civilian objects on the configured list.",
    )


def _target_match(request: Request, observation_set: ObservationSet) -> dict[str, Any]:
    delivered = observation_set.target.norad_id
    if delivered == request.norad_id:
        return _check(
            "target_match", "pass", f"The delivery is for object {delivered}, as requested."
        )
    return _check(
        "target_match",
        "fail",
        f"The delivery is for object {delivered}, but the request is for object "
        f"{request.norad_id}.",
    )


def _time_window(request: Request, obs: list[Observation]) -> dict[str, Any]:
    start, end = request.window_start, request.window_end
    before = [o for o in obs if o.time < start]
    after = [o for o in obs if o.time > end]
    window = f"{format_utc(start)} to {format_utc(end)}"
    if not before and not after:
        return _check(
            "time_window",
            "pass",
            f"All {len(obs)} observations are inside the requested window {window}.",
        )
    parts = []
    if after:
        latest = max(o.time for o in after)
        hours = (latest - end).total_seconds() / 3600
        parts.append(
            f"{len(after)} after the window closed (latest {format_utc(latest)}, "
            f"{hours:.1f} h late)"
        )
    if before:
        parts.append(f"{len(before)} before the window opened")
    return _check(
        "time_window",
        "fail",
        f"{len(before) + len(after)} of {len(obs)} observations are outside the requested window "
        f"{window}: " + "; ".join(parts) + ".",
        {"outside": len(before) + len(after), "before": len(before), "after": len(after)},
    )


def _min_observations(request: Request, obs: list[Observation]) -> dict[str, Any]:
    inside = sum(1 for o in obs if request.window_start <= o.time <= request.window_end)
    if inside >= request.min_observations:
        return _check(
            "min_observations",
            "pass",
            f"{inside} observations inside the window; the request needs at least "
            f"{request.min_observations}.",
        )
    return _check(
        "min_observations",
        "fail",
        f"Only {inside} observation(s) inside the window; the request needs at least "
        f"{request.min_observations}.",
    )


def _declared_uncertainty(request: Request, obs: list[Observation]) -> dict[str, Any]:
    max_angle = max(o.angle_uncertainty_arcsec for o in obs)
    max_time = max(o.time_uncertainty_s for o in obs)
    bad_angle = sum(
        1 for o in obs if o.angle_uncertainty_arcsec > request.max_angle_uncertainty_arcsec
    )
    bad_time = sum(1 for o in obs if o.time_uncertainty_s > request.max_time_uncertainty_s)
    bad_type = sorted({o.angle_type for o in obs} - set(request.angle_types))
    details = {
        "largest_angle_uncertainty_arcsec": max_angle,
        "largest_time_uncertainty_s": max_time,
    }
    if not bad_angle and not bad_time and not bad_type:
        return _check(
            "declared_uncertainty",
            "pass",
            f"Declared uncertainties meet the requirements: largest angle uncertainty "
            f"{max_angle:g}″ (limit {request.max_angle_uncertainty_arcsec:g}″), "
            f"largest time uncertainty {max_time:g} s "
            f"(limit {request.max_time_uncertainty_s:g} s).",
            details,
        )
    parts = []
    if bad_angle:
        parts.append(
            f"{bad_angle} observation(s) declare an angle uncertainty above "
            f"{request.max_angle_uncertainty_arcsec:g}″ (largest {max_angle:g}″)"
        )
    if bad_time:
        parts.append(
            f"{bad_time} observation(s) declare a time uncertainty above "
            f"{request.max_time_uncertainty_s:g} s (largest {max_time:g} s)"
        )
    if bad_type:
        parts.append(f"angle type(s) {', '.join(bad_type)} not accepted by the request")
    return _check(
        "declared_uncertainty",
        "fail",
        "The data is too imprecise for this request: " + "; ".join(parts) + ".",
        details,
    )


def _hash_match(inp: VerificationInput) -> dict[str, Any]:
    if inp.declared_sha256 is None:
        return _check(
            "hash_match", "skip", "No delivery manifest, so there is no declared hash to compare."
        )
    actual = sha256_bytes(inp.observations)
    if actual == inp.declared_sha256:
        return _check(
            "hash_match", "pass", "The SHA-256 of the observation file matches the declared hash."
        )
    return _check(
        "hash_match",
        "fail",
        f"The SHA-256 of the observation file ({actual[:16]}...) does not match the declared hash "
        f"({inp.declared_sha256[:16]}...): the file is not the one that was declared.",
    )


def _duplicates(inp: VerificationInput, observation_set: ObservationSet) -> dict[str, Any]:
    norad = observation_set.target.norad_id
    prints = [_fingerprint(norad, o) for o in observation_set.observations]
    seen_times: dict[tuple, int] = {}
    internal = 0
    for fp in prints:
        key = fp[:2]
        seen_times[key] = seen_times.get(key, 0) + 1
        if seen_times[key] > 1:
            internal += 1
    own_hash = sha256_bytes(inp.observations)
    identical, overlap_by_delivery = [], {}
    for data in inp.previous:
        digest = sha256_bytes(data)
        if digest == own_hash:
            identical.append(digest)
            continue
        try:
            _fmt, earlier = _load_single_set(data, None, inp.sites)
        except FormatError as exc:
            raise UsageError(f"cannot read an earlier delivery ({digest[:16]}...): {exc}") from None
        earlier_prints = {_fingerprint(earlier.target.norad_id, o) for o in earlier.observations}
        overlap = sum(1 for fp in prints if fp in earlier_prints)
        if overlap:
            overlap_by_delivery[digest] = overlap
    problems = []
    if internal:
        problems.append(f"{internal} observation(s) repeat a timestamp already used in this file")
    if identical:
        problems.append("the identical file was already delivered earlier")
    for digest, overlap in sorted(overlap_by_delivery.items()):
        problems.append(
            f"{overlap} of {len(prints)} observations already appear in an earlier "
            f"delivery (sha256 {digest[:16]}...)"
        )
    if problems:
        return _check(
            "duplicates",
            "fail",
            "Duplicate or resubmitted data: " + "; ".join(problems) + ".",
            {
                "internal_duplicates": internal,
                "overlap_with_earlier": dict(sorted(overlap_by_delivery.items())),
                "identical_earlier_files": len(identical),
            },
        )
    compared = len(inp.previous)
    return _check(
        "duplicates",
        "pass",
        f"No repeated observations in the file and no overlap with {compared} earlier "
        f"deliver{'y' if compared == 1 else 'ies'}.",
    )


def _orbit_residuals(
    request: Request, catalog: Catalog, observation_set: ObservationSet
) -> dict[str, Any]:
    norad = request.norad_id
    if norad not in catalog:
        return _check(
            "orbit_residuals",
            "inconclusive",
            f"The reference catalogue has no orbit for object {norad}.",
        )
    obs = observation_set.observations
    try:
        satellite = catalog.satellite(norad)
    except CatalogError as exc:
        return _check("orbit_residuals", "inconclusive", str(exc))
    epoch = satellite.epoch.utc_datetime()
    ages = [abs((o.time - epoch).total_seconds()) / 86400 for o in obs]
    max_age = max(ages)
    if max_age > PARAMETERS["max_reference_age_days"]:
        return _check(
            "orbit_residuals",
            "inconclusive",
            f"The reference orbit epoch ({epoch.strftime('%Y-%m-%d %H:%M')} UTC) is up to "
            f"{max_age:.1f} days from the observations. GP elements are only reliable close to "
            f"their epoch, so the residuals would mostly measure the age of the orbit. Use an "
            f"element set within {PARAMETERS['max_reference_age_days']:g} days.",
        )

    groups: dict[tuple, list[int]] = {}
    for index, o in enumerate(obs):
        groups.setdefault((o.angle_type, o.frame), []).append(index)
    n = len(obs)
    sep = np.zeros(n)
    along = np.zeros(n)
    cross = np.zeros(n)
    along_s = np.zeros(n)
    rate = np.zeros(n)
    rng = np.zeros(n)
    for indices in groups.values():
        res = residuals(satellite, observation_set.station, [obs[i] for i in indices])
        sep[indices], along[indices], cross[indices] = (
            res.separation_arcsec,
            res.along_arcsec,
            res.cross_arcsec,
        )
        along_s[indices], rate[indices], rng[indices] = (
            res.along_s,
            res.rate_arcsec_per_s,
            res.range_km,
        )

    k = PARAMETERS["residual_sigma_multiplier"]
    ref_km = PARAMETERS["reference_position_error_km"]
    sigma = np.array([o.angle_uncertainty_arcsec for o in obs])
    tau = np.array([o.time_uncertainty_s for o in obs])
    ref_arcsec = np.degrees(np.arctan2(ref_km, rng)) * 3600
    limit = np.sqrt((k * sigma) ** 2 + (k * tau * rate) ** 2 + ref_arcsec**2)
    within = sep <= limit
    fraction = float(np.mean(within))
    median_sep = float(np.median(sep))
    median_limit = float(np.median(limit))
    mean_along_s = float(np.mean(along_s))
    std_along_s = float(np.std(along_s, ddof=1)) if n > 1 else 0.0
    rms_cross = float(np.sqrt(np.mean(cross**2)))
    statistics = {
        "observations": n,
        "within_limit": int(np.sum(within)),
        "fraction_within_limit": _r(fraction, 4),
        "median_residual_arcsec": _r(median_sep, 3),
        "max_residual_arcsec": _r(float(np.max(sep)), 3),
        "rms_cross_track_arcsec": _r(rms_cross, 3),
        "mean_along_track_s": _r(mean_along_s, 4),
        "std_along_track_s": _r(std_along_s, 4),
        "median_limit_arcsec": _r(median_limit, 3),
        "reference_epoch_max_age_days": _r(max_age, 4),
    }
    per_observation = [
        {
            "time": format_utc(o.time),
            "residual_arcsec": _r(sep[i], 3),
            "along_track_arcsec": _r(along[i], 3),
            "cross_track_arcsec": _r(cross[i], 3),
            "along_track_s": _r(along_s[i], 4),
            "limit_arcsec": _r(limit[i], 3),
            "range_km": _r(rng[i], 3),
            "within_limit": bool(within[i]),
        }
        for i, o in enumerate(obs)
    ]
    details = {"statistics": statistics, "per_observation": per_observation}
    share = f"{int(np.sum(within))} of {n} observations ({fraction:.0%})"
    needed = PARAMETERS["min_fraction_within_limit"]
    if fraction >= needed:
        return _check(
            "orbit_residuals",
            "pass",
            f"{share} lie within their limits (needed {needed:.0%}). Median residual "
            f"{_fmt_angle(median_sep)} against a typical limit of {_fmt_angle(median_limit)}.",
            details,
        )
    reason = (
        f"Only {share} lie within their limits (needed {needed:.0%}). Median residual "
        f"{_fmt_angle(median_sep)} against a typical limit of {_fmt_angle(median_limit)}."
    )
    if abs(mean_along_s) > 3 * max(std_along_s, 1e-3) / math.sqrt(n) and rms_cross < median_sep:
        direction = "ahead of" if mean_along_s > 0 else "behind"
        reason += (
            f" The residuals lie mostly along the track: the object is on average "
            f"{abs(mean_along_s):.2f} s {direction} the prediction. That points to a different "
            "object in a similar orbit or to a timing error."
        )
    else:
        reason += (
            " The positions do not follow the reference orbit of the requested object: it may "
            "be a different object, wrong times or wrong station coordinates."
        )
    return _check("orbit_residuals", "fail", reason, details)


def _fmt_angle(arcsec: float) -> str:
    if arcsec >= 3600:
        return f"{arcsec / 3600:.2f}°"
    if arcsec >= 60:
        return f"{arcsec / 60:.2f}′"
    return f"{arcsec:.1f}″"


def render_text(report: dict[str, Any]) -> str:
    """A short human-readable explanation of a report."""
    lines = [
        f"Orbit Watch verification ({report['method']['name']} {report['method']['version']})",
    ]
    if report.get("simulated_input"):
        lines.append("Inputs include SIMULATED data.")
    req = report["request"]
    lines.append(
        f"Request {req['request_id']}: object {req['target_norad_id']}, window "
        f"{req['window_start']} to {req['window_end']}"
    )
    lines.append(report["summary"])
    lines.append("")
    marks = {"pass": "PASS", "fail": "FAIL", "skip": "SKIP", "inconclusive": "????"}
    for check in report["checks"]:
        lines.append(f"  {marks[check['result']]}  {check['title']}")
        lines.append(f"        {check['reason']}")
        problems = check.get("details", {}).get("problems", [])
        if check["result"] == "fail" and len(problems) > 1:
            for problem in problems[:10]:
                lines.append(f"          - {problem}")
    lines.append("")
    lines.append(report["disclaimer"])
    return "\n".join(lines) + "\n"

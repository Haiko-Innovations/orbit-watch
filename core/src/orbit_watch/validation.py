"""The verification method measured on real observations (phase 5, step 5.3).

Decision P5-07: the method's behaviour on real data is measured and published before the
method changes. Every verdict here is ``verify()``'s, with the method's checks and
parameters as they are. Only the inputs vary: the real tracks as published, and copies
of them changed in memory to stand for faults. The changed copies are never written to
a file, since they are no longer what the observers published.

The request of each track asks for the track's own object over the track's time, and
its requirements let every track through, so that only the residual check against the
reference orbit decides. That is the check being measured.

A measurement names the method's version, orbit-watch's version, whose lock file pins
every library, and the SHA-256 of every observation file and element set. Anyone with
the same files gets the same numbers: ``orbit-watch measure-method`` regenerates them,
and the tables of ``docs/real-data-validation.md`` from them.
"""

from __future__ import annotations

import hashlib
import re
from collections.abc import Callable, Iterable
from dataclasses import dataclass, replace
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

import numpy as np

from orbit_watch import __version__, orbit_cache
from orbit_watch.canonical import dumps_pretty, sha256_bytes
from orbit_watch.catalog import Catalog, ElementSet, parse_catalog, record_sha256
from orbit_watch.formats import owjson
from orbit_watch.geometry import predict
from orbit_watch.model import ObservationSet
from orbit_watch.timeutil import format_utc
from orbit_watch.verify import orbit_terms
from orbit_watch.verify.engine import (
    METHOD_NAME,
    METHOD_VERSION,
    PARAMETERS,
    VerificationInput,
    ellipse,
    verify,
)
from orbit_watch.verify.orbit_terms import orbit_class

RESULTS_FORMAT = "orbit-watch/real-data-validation"
RESULTS_FORMAT_VERSION = "1.0"

TIME_SHIFTS_S = (0.25, 0.5, 1.0, 2.0, 5.0, 10.0, 30.0)
STATION_MOVES_KM = (1.0, 10.0, 100.0)
ASSUMED_ANGLES_ARCSEC = (10.0, 30.0, 60.0, 120.0)
REFERENCE_AGES_DAYS = (1.0, 3.0, 7.0, 14.0)
ROUNDING_DECIMALS = 2  # about a kilometre, as the service keeps a station's place (P5-11)
FABRICATED_NOISE_ARCSEC = 10.0  # per axis, about what the video camera achieves
KM_PER_DEGREE_LATITUDE = 111.32
# A track that passes once its mean time offset is taken out joins the fault study when
# the offset is no larger than this: a clock's, not minutes of an exposure.
CLOCK_OFFSET_MAX_S = 5.0

REQUIREMENTS = {
    # Loose enough that only the residual check decides.
    "min_observations": 1,
    "max_angle_uncertainty_arcsec": 3600.0,
    "max_time_uncertainty_s": 3600.0,
    "angle_types": ["radec"],
}


# Inputs -----------------------------------------------------------------------------------


@dataclass(frozen=True)
class Track:
    group: str  # the directory it came from, e.g. "examples/real"
    file: str
    sha256: str
    observation_set: ObservationSet

    @property
    def norad_id(self) -> int:
        return self.observation_set.target.norad_id

    @property
    def instrument(self) -> str:
        name = self.observation_set.station.name or ""
        return name.removeprefix("SCORE observer, ") or "unknown"

    @property
    def times(self) -> list[datetime]:
        return [o.time for o in self.observation_set.observations]

    @property
    def middle(self) -> datetime:
        times = self.times
        return min(times) + (max(times) - min(times)) / 2

    @property
    def assumed_angle(self) -> bool:
        origin = self.observation_set.source.get("origin") or {}
        return "assumed_angle_uncertainty_arcsec" in origin


def load_tracks(directories: Iterable[tuple[str, Path]]) -> list[Track]:
    """Every observation set in each directory's ``observations/``, labelled by group."""
    tracks = []
    for group, directory in directories:
        for path in sorted((directory / "observations").glob("*.json")):
            data = path.read_bytes()
            tracks.append(
                Track(group, path.name, sha256_bytes(data), owjson.read_observation_set(data))
            )
    return tracks


def instrument_kind(instrument: str) -> str:
    """A short name for an instrument as SCORE's observers write it."""
    text = instrument.lower()
    if "watec" in text:
        return "Video camera (WATEC 902H2)"
    if "decam" in text:
        return "DECam (Blanco 4 m)"
    if "evscope" in text:
        return "eVscope"
    match = re.search(r"iphone\s*(\d+\s*\w*\s*\w*)", text)
    if match:
        model = re.sub(r"\s+", " ", match.group(1)).strip().title()
        return f"Phone (iPhone {model})"
    return instrument


# One run of the method --------------------------------------------------------------------


def request_for(
    norad_id: int,
    name: str | None,
    times: list[datetime],
    *,
    request_id: str | None = None,
    title: str = "Measurement of the verification method on real data",
) -> bytes:
    """A request for one object over a track's time, whose requirements let every track
    through to the residual check."""
    request = {
        "format": "orbit-watch/request",
        "format_version": "1.0",
        "simulated": False,
        "request_id": request_id or f"VALIDATION-{norad_id}",
        "title": title,
        "target": {"norad_id": norad_id, **({"name": name[:200]} if name else {})},
        "window": {
            "start": format_utc(min(times) - timedelta(hours=1)),
            "end": format_utc(max(times) + timedelta(hours=1)),
        },
        "requirements": REQUIREMENTS,
    }
    return dumps_pretty(request, sort_keys=False).encode("utf-8")


def policy_for(norad_id: int) -> bytes:
    policy = {
        "format": "orbit-watch/target-policy",
        "format_version": "1.0",
        "simulated": False,
        "allow": [{"norad_id": norad_id}],
    }
    return dumps_pretty(policy, sort_keys=False).encode("utf-8")


def catalog_bytes(records: list[dict[str, Any]]) -> bytes:
    document = {
        "format": "orbit-watch/gp-catalog",
        "format_version": "1.0",
        "simulated": False,
        "description": "Real element sets, for the measurement only. Not for redistribution.",
        "records": records,
    }
    return dumps_pretty(document, sort_keys=False).encode("utf-8")


@dataclass(frozen=True)
class Outcome:
    verdict: str
    result: str  # of the residual check: pass, fail or inconclusive
    statistics: dict[str, Any]


def run(
    observation_set: ObservationSet, catalog: bytes, method_version: str = METHOD_VERSION
) -> Outcome:
    """``verify()`` on one track, as the service would run it for a request of the track's
    own object over the track's time."""
    norad = observation_set.target.norad_id
    # The bytes write_observation_set() gives, without its own schema check: verify()
    # checks the file when it reads it, as it checks every delivery.
    document = observation_set.to_document()
    observations = dumps_pretty(document, sort_keys=False).encode("utf-8")
    report = verify(
        VerificationInput(
            request=request_for(norad, observation_set.target.name, _times(observation_set)),
            observations=observations,
            observations_format="json",
            catalog=catalog,
            policy=policy_for(norad),
            declared_sha256=sha256_bytes(observations),
            method_version=method_version,
        )
    )
    check = next(c for c in report["checks"] if c["id"] == "orbit_residuals")
    statistics = (check.get("details") or {}).get("statistics", {})
    return Outcome(report["verdict"], check["result"], statistics)


def _times(observation_set: ObservationSet) -> list[datetime]:
    return [o.time for o in observation_set.observations]


# Changes that stand for faults ------------------------------------------------------------


def shifted(observation_set: ObservationSet, seconds: float) -> ObservationSet:
    """The same angles at times ``seconds`` later: a clock that is wrong, or an object
    that many seconds ahead in the same orbit."""
    step = timedelta(seconds=seconds)
    observations = [replace(o, time=o.time + step) for o in observation_set.observations]
    return replace(observation_set, observations=observations)


def moved(observation_set: ObservationSet, km_north: float) -> ObservationSet:
    station = observation_set.station
    latitude = station.latitude_deg + km_north / KM_PER_DEGREE_LATITUDE
    return replace(observation_set, station=replace(station, latitude_deg=latitude))


def rounded(observation_set: ObservationSet, decimals: int) -> ObservationSet:
    station = observation_set.station
    return replace(
        observation_set,
        station=replace(
            station,
            latitude_deg=round(station.latitude_deg, decimals),
            longitude_deg=round(station.longitude_deg, decimals),
        ),
    )


def _all_angles(observation_set: ObservationSet, arcsec: float) -> bool:
    return all(o.angle_uncertainty_arcsec == arcsec for o in observation_set.observations)


def with_angle_uncertainty(observation_set: ObservationSet, arcsec: float) -> ObservationSet:
    observations = [
        replace(o, angle_uncertainty_arcsec=arcsec) for o in observation_set.observations
    ]
    return replace(observation_set, observations=observations)


def relabelled(observation_set: ObservationSet, norad_id: int, name: str) -> ObservationSet:
    """The same observations delivered for another object."""
    target = replace(observation_set.target, norad_id=norad_id, name=name)
    return replace(observation_set, target=target)


def fabricated(observation_set: ObservationSet, reference: ElementSet, seed: int) -> ObservationSet:
    """Positions computed from the reference orbit itself at the track's times, with
    noise: what someone who never observed could deliver."""
    rng = np.random.default_rng(seed)
    times = _times(observation_set)
    prediction = predict(reference.satellite, observation_set.station, times, "radec", "ICRF")
    sigma_deg = FABRICATED_NOISE_ARCSEC / 3600
    dec = prediction.angle_2_deg + rng.normal(0, sigma_deg, len(times))
    cos_dec = np.cos(np.radians(prediction.angle_2_deg))
    ra = prediction.angle_1_deg + rng.normal(0, sigma_deg, len(times)) / np.maximum(cos_dec, 1e-6)
    observations = [
        replace(o, ra_deg=round(float(ra[i]) % 360.0, 8), dec_deg=round(float(dec[i]), 8))
        for i, o in enumerate(observation_set.observations)
    ]
    return replace(observation_set, observations=observations)


def _seed(text: str) -> int:
    return int(hashlib.sha256(text.encode("utf-8")).hexdigest()[:8], 16)


# The limit's terms ------------------------------------------------------------------------


def _term(reference: ElementSet, observation_set: ObservationSet) -> orbit_terms.OrbitTerm:
    """The orbit term the check gives the set for the track; past the method's ages, its
    last row's, to show what lies beyond."""
    times = [o.time for o in observation_set.observations]
    age = max(abs((t - reference.epoch).total_seconds()) / 86400 for t in times)
    term = orbit_terms.term_for(reference.record, age, simulated=True)
    assert term is not None
    return term


def limit_terms(observation_set: ObservationSet, reference: ElementSet) -> dict[str, Any]:
    """Medians of the terms of each observation's limit, computed as the residual check
    computes them, and the median share of the limit's square along the track that the
    reference orbit's term makes."""
    term = _term(reference, observation_set)
    e = ellipse(reference.satellite, observation_set.station, observation_set.observations, term)
    return {
        "orbit_term": term.public(),
        "angle_term_arcsec": _r(np.median(e.angle_term), 2),
        "timing_term_arcsec": _r(np.median(e.timing_term), 2),
        "orbit_term_along_arcsec": _r(np.median(e.orbit_along), 2),
        "orbit_term_across_arcsec": _r(np.median(e.orbit_cross), 2),
        "orbit_share_of_limit": _r(np.median(e.orbit_along**2 / e.along_limit**2), 4),
        "median_range_km": _r(np.median(e.range_km), 1),
        "median_rate_arcsec_per_s": _r(np.median(e.rate), 2),
    }


def age_residuals(observation_set: ObservationSet, reference: ElementSet) -> dict[str, Any]:
    """The residual check's statistics against an element set of any age, computed as the
    check computes them. The check itself stops at the oldest age its orbit term has; this
    shows what lies beyond, with the term's last row."""
    obs = observation_set.observations
    term = _term(reference, observation_set)
    e = ellipse(reference.satellite, observation_set.station, obs, term)
    ages = [abs((o.time - reference.epoch).total_seconds()) / 86400 for o in obs]
    return {
        "reference_epoch": format_utc(reference.epoch),
        "age_days": _r(max(ages), 3),
        "median_residual_arcsec": _r(np.median(e.sep), 2),
        "mean_along_track_s": _r(np.mean(e.along_s), 4),
        "rms_cross_track_arcsec": _r(np.sqrt(np.mean(e.cross**2)), 2),
        "fraction_within_limit": _r(np.mean(e.normalised <= 1.0), 4),
    }


def _r(value: Any, digits: int) -> float:
    return round(float(value), digits)


# The measurement --------------------------------------------------------------------------


@dataclass
class Inputs:
    tracks: list[Track]
    records: dict[int, list[dict[str, Any]]]  # element sets by object
    element_sets: list[dict[str, Any]]  # what the manifests name, for the record

    def catalog(self, norad_id: int) -> bytes:
        return catalog_bytes(self.records.get(norad_id, []))

    def parsed(self, norad_id: int) -> Catalog:
        return parse_catalog(self.catalog(norad_id))


def measure(inputs: Inputs, log: Callable[[str], None] = lambda message: None) -> dict[str, Any]:
    """The whole measurement, as one deterministic document."""
    rows = []
    for index, track in enumerate(inputs.tracks, 1):
        log(f"[{index}/{len(inputs.tracks)}] {track.file}")
        rows.append(_measure_track(track, inputs))
    return {
        "format": RESULTS_FORMAT,
        "format_version": RESULTS_FORMAT_VERSION,
        "simulated": False,
        "method": {
            "name": METHOD_NAME,
            "version": METHOD_VERSION,
            "parameters": PARAMETERS,
            "orbit_terms": orbit_terms.table(),
        },
        "software": {"orbit-watch": __version__},
        "settings": {
            "requirements": REQUIREMENTS,
            "time_shifts_s": list(TIME_SHIFTS_S),
            "station_moves_km": list(STATION_MOVES_KM),
            "assumed_angles_arcsec": list(ASSUMED_ANGLES_ARCSEC),
            "reference_ages_days": list(REFERENCE_AGES_DAYS),
            "rounding_decimals": ROUNDING_DECIMALS,
            "fabricated_noise_arcsec": FABRICATED_NOISE_ARCSEC,
        },
        "inputs": {
            "observation_files": [
                {"group": t.group, "file": t.file, "sha256": t.sha256} for t in inputs.tracks
            ],
            "element_sets": inputs.element_sets,
        },
        "tracks": rows,
    }


def _measure_track(track: Track, inputs: Inputs) -> dict[str, Any]:
    observation_set = track.observation_set
    catalog = inputs.catalog(track.norad_id)
    parsed = parse_catalog(catalog)
    reference = parsed.nearest(track.norad_id, track.middle)
    base = run(observation_set, catalog)
    row: dict[str, Any] = {
        "group": track.group,
        "file": track.file,
        "norad_id": track.norad_id,
        "object": observation_set.target.name,
        "instrument": instrument_kind(track.instrument),
        "station": observation_set.station.id,
        "start": format_utc(min(track.times)),
        "observations": len(observation_set.observations),
        "angle_uncertainty": "assumed" if track.assumed_angle else "declared",
        "orbit": orbit_class(reference.record),
        "verdict": base.verdict,
        "result": base.result,
        "statistics": base.statistics,
        "limit_terms": limit_terms(observation_set, reference),
    }
    passed = base.result == "pass"
    # The cost of rounding the station's place to about a kilometre.
    rounding = run(rounded(observation_set, ROUNDING_DECIMALS), catalog)
    row["rounded"] = {
        "result": rounding.result,
        "median_residual_arcsec": rounding.statistics.get("median_residual_arcsec"),
        "fraction_within_limit": rounding.statistics.get("fraction_within_limit"),
    }
    # What the assumed angle uncertainty changes.
    row["assumed_angle"] = {
        f"{value:g}": (
            base.result
            if _all_angles(observation_set, value)
            else run(with_angle_uncertainty(observation_set, value), catalog).result
        )
        for value in ASSUMED_ANGLES_ARCSEC
    }
    sound = observation_set if passed else None
    if not passed:
        along = base.statistics.get("mean_along_track_s")
        if base.result == "fail" and along is not None:
            # Does the track pass once its mean time offset is taken out? Then its angles
            # are sound and only its times are off.
            corrected = shifted(observation_set, along)
            result = run(corrected, catalog).result
            row["offset_removed"] = {"shift_s": along, "result": result}
            if result == "pass" and abs(along) <= CLOCK_OFFSET_MAX_S:
                sound = corrected
    if sound is None:
        return row
    # Faults put into a track that passes, as published or with its offset taken out: is
    # it still accepted?
    row["faults_on"] = "as published" if passed else "offset removed"
    row["faults"] = {
        "time_shift_s": {f"{s:g}": run(shifted(sound, s), catalog).result for s in TIME_SHIFTS_S},
        "station_moved_km": {
            f"{d:g}": run(moved(sound, d), catalog).result for d in STATION_MOVES_KM
        },
        "wrong_object": _wrong_objects(sound, track.middle, inputs),
        "fabricated": run(fabricated(sound, reference, _seed(track.file)), catalog).result,
        # The station at about a kilometre, as a profile may publish it (P5-11).
        "rounded": run(rounded(sound, ROUNDING_DECIMALS), catalog).result,
    }
    if passed:
        # The reference orbit's age.
        row["reference_age"] = _ages(track, parsed)
    return row


def _wrong_objects(
    observation_set: ObservationSet, middle: datetime, inputs: Inputs
) -> dict[str, str]:
    """The track delivered for every other object whose element sets reach the track's
    time, so that the method can judge it: the observer mixed up two objects."""
    results = {}
    own = observation_set.target.norad_id
    for other in sorted(inputs.records):
        if other == own:
            continue
        parsed = inputs.parsed(other)
        nearest = parsed.nearest(other, middle)
        age = abs((nearest.epoch - middle).total_seconds()) / 86400
        if age > orbit_terms.oldest_age(nearest.record):
            continue
        changed = relabelled(observation_set, other, parsed.name(other))
        results[str(other)] = run(changed, inputs.catalog(other)).result
    return results


def _ages(track: Track, parsed: Catalog) -> list[dict[str, Any]]:
    """Residuals against older element sets of the same object, where the manifests name
    one near the time asked for."""
    rows = []
    seen = set()
    for days in REFERENCE_AGES_DAYS:
        wanted = track.middle - timedelta(days=days)
        older = parsed.nearest(track.norad_id, wanted)
        if abs((older.epoch - wanted).total_seconds()) > 0.5 * 86400:
            continue
        key = format_utc(older.epoch)
        if key in seen:
            continue
        seen.add(key)
        entry = {"asked_days": days, **age_residuals(track.observation_set, older)}
        single = catalog_bytes([older.record])
        entry["result"] = run(track.observation_set, single).result
        rows.append(entry)
    return rows


def write_results(path: Path, results: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(dumps_pretty(results, sort_keys=False), encoding="utf-8")


GROUPS = (("examples/real", "examples/real"), ("validation/real", "validation/real"))


def load_inputs(root: Path, cache_dir: Path) -> Inputs:
    """The committed tracks of both sets, and the element sets their manifests name, from
    the cache. Raises ``orbit_cache.CacheError`` when the cache lacks any."""
    tracks = load_tracks((group, root / path) for group, path in GROUPS)
    records: dict[int, list[dict[str, Any]]] = {}
    named: list[dict[str, Any]] = []
    seen: set[str] = set()
    for _, path in GROUPS:
        manifest = orbit_cache.parse_manifest((root / path / "reference-orbits.json").read_bytes())
        for record in orbit_cache.catalog_document(manifest, cache_dir)["records"]:
            digest = record_sha256(record)
            if digest not in seen:
                seen.add(digest)
                records.setdefault(int(record["NORAD_CAT_ID"]), []).append(record)
        for entry in manifest.entries:
            document = entry.to_document()
            if document not in named:
                named.append(document)
    named.sort(key=lambda e: (e["norad_id"], e["epoch"], e["sha256"]))
    return Inputs(tracks, records, named)


def missing_sets(root: Path, cache_dir: Path) -> list[orbit_cache.Entry]:
    absent = []
    for _, path in GROUPS:
        manifest = orbit_cache.parse_manifest((root / path / "reference-orbits.json").read_bytes())
        absent += orbit_cache.missing(manifest, cache_dir)
    return absent


# Known answers for reviewer calibration ---------------------------------------------------

KNOWN_ANSWERS_FORMAT = "orbit-watch/known-answers"
SOUND_INSTRUMENTS = ("Video camera (WATEC 902H2)", "eVscope")
OFFSET_SETTLED_S = 1.0  # a constant offset larger than this, found again and again


def known_answers(results: dict[str, Any]) -> dict[str, Any]:
    """Real tracks whose correct answer is settled, for reviewer calibration (step 1.4):
    - approve: a track whose delivery passes, from an instrument whose tracks all pass the
      residual check and whose quality report finds no clock offset;
    - reject: a phone's track whose delivery fails because its times are off by a
      constant second or more, as on the phone's other tracks of low orbits; or one whose
      positions lie a degree or more from the requested object's orbit.
    DECam's tracks have no settled answer: why most of them fail is not known."""
    hashes = {f["file"]: f["sha256"] for f in results["inputs"]["observation_files"]}
    entries = []
    for row in results["tracks"]:
        stats = row.get("statistics") or {}
        offset = row.get("offset_removed") or {}
        phone = row["instrument"].startswith("Phone")
        answer = reason = None
        if row["instrument"] in SOUND_INSTRUMENTS and row["verdict"] == "pass":
            answer = "approve"
            reason = "The delivery passes, from an instrument whose tracks all pass."
        elif phone and row["verdict"] == "fail" and row["result"] == "fail":
            if offset.get("result") == "pass" and abs(offset["shift_s"]) > OFFSET_SETTLED_S:
                answer = "reject"
                reason = (
                    f"The times are {abs(offset['shift_s']):.1f} s off, like this phone's "
                    "other tracks of low orbits; the angles fit once the offset is taken out."
                )
            elif (stats.get("median_residual_arcsec") or 0) >= 3600 and (
                stats.get("rms_cross_track_arcsec") or 0
            ) >= 1800:
                answer = "reject"
                reason = "The positions lie a degree or more from the requested object's orbit."
        if answer:
            entries.append(
                {
                    "group": row["group"],
                    "file": row["file"],
                    "sha256": hashes[row["file"]],
                    "norad_id": row["norad_id"],
                    "expected": answer,
                    "automated_verdict": row["verdict"],
                    "reason": reason,
                }
            )
    return {
        "format": KNOWN_ANSWERS_FORMAT,
        "format_version": "1.0",
        "simulated": False,
        "description": (
            "Real tracks from SCORE with a settled answer, for reviewer calibration. Made by "
            "orbit-watch measure-method from results.json; see docs/real-data-validation.md."
        ),
        "method": results["method"]["version"],
        "entries": entries,
    }


# The tables of docs/real-data-validation.md -----------------------------------------------


NONE = "\u2013"  # an en dash, for a value that does not exist


def _arcsec(value: float | None) -> str:
    if value is None:
        return NONE
    if value >= 3600:
        return f"{value / 3600:.2f}°"
    return f"{value:,.0f}″"


def _median(values: list[float]) -> float | None:
    values = [v for v in values if v is not None]
    return float(np.median(values)) if values else None


def _table(header: list[str], rows: list[list[str]]) -> str:
    lines = ["| " + " | ".join(header) + " |", "|" + "|".join("---" for _ in header) + "|"]
    lines += ["| " + " | ".join(row) + " |" for row in rows]
    return "\n".join(lines)


def _by(rows: list[dict[str, Any]], key: Callable[[dict[str, Any]], str]) -> dict[str, list]:
    groups: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        groups.setdefault(key(row), []).append(row)
    return dict(sorted(groups.items()))


def _count(rows: list[dict[str, Any]], result: str) -> int:
    return sum(1 for row in rows if row["result"] == result)


def tables(results: dict[str, Any]) -> dict[str, str]:
    rows = results["tracks"]
    out: dict[str, str] = {}

    out["data"] = _table(
        ["Set", "Tracks", "Observations", "Stations", "Objects"],
        [
            [
                f"`{group}/`",
                str(len(members)),
                f"{sum(r['observations'] for r in members):,}",
                str(len({r["station"] for r in members})),
                str(len({r["norad_id"] for r in members})),
            ]
            for group, members in _by(rows, lambda r: r["group"]).items()
        ]
        + [
            [
                "Both",
                str(len(rows)),
                f"{sum(r['observations'] for r in rows):,}",
                str(len({r["station"] for r in rows})),
                str(len({r["norad_id"] for r in rows})),
            ]
        ],
    )

    def results_table(key: Callable[[dict[str, Any]], str], label: str) -> str:
        body = []
        for name, members in _by(rows, key).items():
            stats = [r["statistics"] for r in members]
            body.append(
                [
                    name,
                    str(len(members)),
                    f"{sum(r['observations'] for r in members):,}",
                    str(_count(members, "pass")),
                    str(_count(members, "fail")),
                    str(_count(members, "inconclusive")),
                    _arcsec(_median([s.get("median_residual_arcsec") for s in stats])),
                    _arcsec(_median([s.get("median_along_track_limit_arcsec") for s in stats])),
                    _arcsec(_median([s.get("median_cross_track_limit_arcsec") for s in stats])),
                ]
            )
        return _table(
            [
                label,
                "Tracks",
                "Observations",
                "Pass",
                "Fail",
                "Inconclusive",
                "Median residual",
                "Median limit along",
                "Median limit across",
            ],
            body,
        )

    out["by_instrument"] = results_table(lambda r: r["instrument"], "Instrument")
    out["by_orbit"] = results_table(lambda r: r["orbit"], "Orbit")

    body = []
    for name, members in _by(rows, lambda r: r["instrument"]).items():
        terms = [r["limit_terms"] for r in members]
        body.append(
            [
                name,
                _arcsec(_median([t["angle_term_arcsec"] for t in terms])),
                _arcsec(_median([t["timing_term_arcsec"] for t in terms])),
                _arcsec(_median([t["orbit_term_along_arcsec"] for t in terms])),
                _arcsec(_median([t["orbit_term_across_arcsec"] for t in terms])),
                f"{_median([t['median_range_km'] for t in terms]):,.0f} km",
                f"{_median([t['orbit_share_of_limit'] for t in terms]):.0%}",
            ]
        )
    out["limit_terms"] = _table(
        [
            "Instrument",
            "Angle term 3\u03c3",
            "Timing term 3\u03c4 \u00d7 rate",
            "Orbit term along",
            "Orbit term across",
            "Range",
            "Orbit term's share of the limit² along",
        ],
        body,
    )

    body = []
    failing = [r for r in rows if r["result"] == "fail"]
    for name, members in _by(failing, lambda r: r["instrument"]).items():
        fixed = [r for r in members if (r.get("offset_removed") or {}).get("result") == "pass"]
        shifts = [r["offset_removed"]["shift_s"] for r in fixed]
        body.append(
            [
                name,
                str(len(members)),
                str(len(fixed)),
                f"{min(shifts):+.2f} to {max(shifts):+.2f} s" if shifts else NONE,
            ]
        )
    out["offsets"] = _table(
        [
            "Instrument",
            "Tracks that fail",
            "Pass with their mean offset taken out",
            "Those offsets",
        ],
        body,
    )

    body = []
    for row in rows:
        if "reference_age" not in row:
            continue
        cells = {f"{a['asked_days']:g}": a for a in row["reference_age"]}
        nearest = row["statistics"].get("reference_epoch_max_age_days")
        line = [
            f"{row['object']} ({row['start'][:10]})",
            row["instrument"],
            f"{nearest:.2f} d: {row['result']}, "
            f"{_arcsec(row['statistics'].get('median_residual_arcsec'))}",
        ]
        for days in REFERENCE_AGES_DAYS:
            a = cells.get(f"{days:g}")
            line.append(
                f"{a['age_days']:.1f} d: {a['result']}, {_arcsec(a['median_residual_arcsec'])}"
                if a
                else NONE
            )
        body.append(line)
    out["ages"] = _table(
        ["Track", "Instrument", "Nearest set"]
        + [f"About {d:g} d older" for d in REFERENCE_AGES_DAYS],
        body,
    )

    studied = [r for r in rows if "faults" in r]

    def fault_group(r: dict[str, Any]) -> str:
        suffix = ", offset taken out" if r["faults_on"] == "offset removed" else ""
        return f"{r['instrument']}, {r['orbit']}{suffix}"

    def accepted(members: list[dict[str, Any]], pick: Callable[[dict[str, Any]], str]) -> str:
        values = [pick(m) for m in members]
        return f"{sum(1 for v in values if v == 'pass')} of {len(values)}"

    groups = _by(studied, fault_group)
    out["time_shift"] = _table(
        ["Tracks", "n"] + [f"{s:g} s" for s in TIME_SHIFTS_S],
        [
            [name, str(len(members))]
            + [
                accepted(members, lambda m, s=s: m["faults"]["time_shift_s"][f"{s:g}"])
                for s in TIME_SHIFTS_S
            ]
            for name, members in groups.items()
        ],
    )
    out["station_moved"] = _table(
        ["Tracks", "n"] + [f"{d:g} km north" for d in STATION_MOVES_KM] + ["Rounded to 0.01°"],
        [
            [name, str(len(members))]
            + [
                accepted(members, lambda m, d=d: m["faults"]["station_moved_km"][f"{d:g}"])
                for d in STATION_MOVES_KM
            ]
            + [accepted(members, lambda m: m["faults"]["rounded"])]
            for name, members in groups.items()
        ],
    )
    body = []
    for name, members in groups.items():
        pairs = [v for m in members for v in m["faults"]["wrong_object"].values()]
        body.append(
            [
                name,
                str(len(members)),
                str(len(pairs)),
                str(sum(1 for v in pairs if v == "pass")),
                str(sum(1 for v in pairs if v == "inconclusive")),
                accepted(members, lambda m: m["faults"]["fabricated"]),
            ]
        )
    out["wrong_object"] = _table(
        [
            "Tracks",
            "n",
            "Delivered for another object",
            "Accepted",
            "Inconclusive",
            "Made from the reference orbit: accepted",
        ],
        body,
    )

    body = []
    for name, members in _by(rows, lambda r: r["instrument"]).items():
        changes = []
        flips = 0
        for r in members:
            before = r["statistics"].get("median_residual_arcsec")
            after = r["rounded"]["median_residual_arcsec"]
            if before is not None and after is not None:
                changes.append(after - before)
            flips += r["rounded"]["result"] != r["result"]
        magnitudes = [abs(c) for c in changes]
        body.append(
            [
                name,
                str(len(members)),
                str(flips),
                _arcsec(_median(magnitudes)),
                _arcsec(max(magnitudes)) if magnitudes else NONE,
            ]
        )
    out["rounding"] = _table(
        [
            "Instrument",
            "Tracks",
            "Results changed",
            "Median change of the median residual",
            "Largest change",
        ],
        body,
    )

    body = []
    for (name, kind), members in _by(
        rows, lambda r: (r["instrument"], r["angle_uncertainty"])
    ).items():
        line = [name, kind, str(len(members))]
        for value in ASSUMED_ANGLES_ARCSEC:
            key = f"{value:g}"
            line.append(str(sum(1 for r in members if r["assumed_angle"][key] == "pass")))
        body.append(line)
    out["assumed_angle"] = _table(
        ["Instrument", "Angle uncertainty in the files", "Tracks"]
        + [f"Pass with {v:g}″" for v in ASSUMED_ANGLES_ARCSEC],
        body,
    )

    body = []
    for r in sorted(rows, key=lambda r: (r["instrument"], r["start"], r["norad_id"])):
        stats = r["statistics"]
        along = stats.get("mean_along_track_s")
        age = stats.get("reference_epoch_max_age_days")
        body.append(
            [
                f"[{r['file'][:-5]}](../{r['group']}/observations/{r['file']})",
                r["instrument"],
                str(r["object"]),
                r["orbit"],
                str(r["observations"]),
                r["result"],
                _arcsec(stats.get("median_residual_arcsec")),
                _arcsec(stats.get("median_along_track_limit_arcsec")),
                _arcsec(stats.get("median_cross_track_limit_arcsec")),
                NONE if along is None else f"{along:+.2f} s",
                _arcsec(stats.get("rms_cross_track_arcsec")),
                NONE if age is None else f"{age:.2f} d",
            ]
        )
    out["tracks"] = _table(
        [
            "Track",
            "Instrument",
            "Object",
            "Orbit",
            "Obs.",
            "Result",
            "Median residual",
            "Limit along",
            "Limit across",
            "Mean along-track",
            "RMS cross-track",
            "Set's age",
        ],
        body,
    )
    return out


MARKER = re.compile(
    r"(<!-- measured:(?P<name>[a-z_]+) -->\n)(?P<body>.*?)(<!-- /measured:(?P=name) -->)",
    re.DOTALL,
)


def update_document(text: str, generated: dict[str, str]) -> str:
    """Replace every generated table between its markers; every table must have a place."""
    found = set()

    def fill(match: re.Match) -> str:
        name = match.group("name")
        if name not in generated:
            raise ValueError(f"the document has a place for an unknown table: {name}")
        found.add(name)
        return match.group(1) + generated[name] + "\n" + match.group(4)

    updated = MARKER.sub(fill, text)
    absent = sorted(set(generated) - found)
    if absent:
        raise ValueError(f"the document has no place for the tables {', '.join(absent)}")
    return updated

"""How far GP sets are from operators' own orbits (phase 6, step 6.1; P6-02, D-60).

``orbit-watch measure-reference-orbits --fetch`` makes one run:

* **the truth**: CelesTrak's SupGP sets fitted to operators' orbits (``orbit_watch.supgp``),
  one download per source (``SOURCES``). From each source and orbit class up to
  ``PER_GROUP`` objects are taken, evenly by catalogue number. An object's truth is its
  operator-derived set with the latest epoch at or before the run, and for the ISS the last
  ``ISS_SEGMENTS`` 6-hour segments that have begun;
* **the GP sets**: every OMM that SatChecker keeps of each object from ``HISTORY_DAYS`` days
  before its truth's epoch up to it (``orbit_watch.satchecker.fetch_history``), one request
  per object, two seconds apart;
* **the comparison**: SGP4 positions of the GP set and of the truth every ``STEP_S`` seconds
  over the ``SPAN_S`` after the truth's epoch, since "SupGP data is fitted from the current
  epoch forward". The difference is split into radial, in-track and cross-track parts in the
  truth's frame, and the set's age is taken at the middle of the span;
* **how operators' orbits age** (step 6.2): with more than one run in the cache, each truth
  of a later run is compared in the same way with the set that the object's operator had
  published by an earlier run with the latest epoch at or before the truth's, beside the
  newest GP set that SatChecker had collected by the earlier run. These are what the
  follower would have had to choose between for that time (P6-03). The ISS's ephemeris
  gives segments ahead, so its set may be one that had not begun at the earlier run.

Every answer is kept, as received, in a run directory of the cache outside the repository.
A run is used only when it is complete. Without ``--fetch`` the measurement is recomputed from
the newest run and the runs before it, byte for byte. SupGP keeps no history, so nobody else
can fetch the same sets later; a new run measures again with current ones. No element set
leaves the cache: the results name sets by epoch and SHA-256 only (D-06, P5-05).
"""

from __future__ import annotations

import json
import time
import urllib.request
from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import numpy as np

from orbit_watch import __version__
from orbit_watch.canonical import dumps_pretty
from orbit_watch.catalog import Catalog, ElementSet, parse_catalog
from orbit_watch.satchecker import PAUSE_S, download, history_url, parse_history
from orbit_watch.supgp import SupSet, download_supgp, sup_sets
from orbit_watch.validation import orbit_class

RESULTS_FORMAT = "orbit-watch/reference-orbit-accuracy"
RESULTS_FORMAT_VERSION = "1.1"
SOURCES = ("AST-E", "CPF", "ISS-E", "Kuiper-E", "OneWeb-E", "Planet-E")
PER_GROUP = 6  # objects per source and orbit class
ISS_SEGMENTS = 8
HISTORY_DAYS = 10
SPAN_S = 6 * 3600
STEP_S = 60
SAME_KM = 0.001  # a GP set this close at the truth's own epoch is the truth itself
MIN_RUN_GAP_S = 2 * 3600  # CelesTrak asks for at least two hours between SupGP downloads
DASH = "\u2013"  # an en dash, in ranges and for a value that does not exist
AGE_BINS = ((0.0, 0.5), (0.5, 1.0), (1.0, 2.0), (2.0, 3.0), (3.0, 5.0), (5.0, 7.0), (7.0, 10.0))
RUN_FILE = "run.json"
RUN_FORMAT = "orbit-watch/reference-accuracy-run"


def _utc(text: str) -> datetime:
    return datetime.fromisoformat(text.replace("Z", "+00:00")).astimezone(UTC)


def _stamp(moment: datetime) -> str:
    return moment.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


@dataclass(frozen=True)
class Truth:
    norad_id: int
    name: str
    source: str
    orbit: str
    sup: SupSet

    @property
    def epoch(self) -> datetime:
        return self.sup.element_set.epoch


def _latest_before(sets: list[SupSet], moment: datetime) -> SupSet | None:
    usable = [s for s in sets if s.operator_orbit and s.element_set.epoch <= moment]
    if not usable:
        return None
    latest = max(s.element_set.epoch for s in usable)
    tied = [s for s in usable if s.element_set.epoch == latest]
    return min(tied, key=lambda s: (_rms_or_large(s), s.element_set.sha256))


def _rms_or_large(sup: SupSet) -> float:
    return sup.rms_km if sup.rms_km is not None else float("inf")


def _evenly(items: list, count: int) -> list:
    if len(items) <= count:
        return items
    picks = np.linspace(0, len(items) - 1, count)
    return [items[round(float(i))] for i in picks]


def choose_truths(sources: dict[str, Catalog], moment: datetime) -> list[Truth]:
    """The truth sets of one run, oldest catalogue number first within each source."""
    truths: list[Truth] = []
    for source in sorted(sources):
        catalog = sources[source]
        if source == "ISS-E":
            for norad_id in sorted(catalog.sets):
                begun = [
                    s
                    for s in sup_sets(catalog, norad_id)
                    if s.operator_orbit and s.element_set.epoch <= moment
                ]
                for sup in begun[-ISS_SEGMENTS:]:
                    truths.append(_truth(catalog, norad_id, source, sup))
            continue
        groups: dict[str, list[tuple[int, SupSet]]] = {}
        for norad_id in sorted(catalog.sets):
            sup = _latest_before(sup_sets(catalog, norad_id), moment)
            if sup is None:
                continue
            groups.setdefault(orbit_class(sup.element_set.record), []).append((norad_id, sup))
        for orbit in sorted(groups):
            for norad_id, sup in _evenly(groups[orbit], PER_GROUP):
                truths.append(_truth(catalog, norad_id, source, sup))
    return truths


def _truth(catalog: Catalog, norad_id: int, source: str, sup: SupSet) -> Truth:
    record = sup.element_set.record
    name = str(record.get("OBJECT_NAME", norad_id))
    return Truth(norad_id, name, source, orbit_class(record), sup)


def _states(element_set: ElementSet, start: datetime) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    model = element_set.satellite.model
    seconds = np.arange(0, SPAN_S + 1, STEP_S, dtype=float)
    jd0 = start.timestamp() / 86400 + 2440587.5
    jd = np.full(seconds.shape, np.floor(jd0 - 0.5) + 0.5)
    fr = (jd0 - jd) + seconds / 86400
    errors, positions, velocities = model.sgp4_array(jd, fr)
    return errors, positions, velocities


def compare(gp: ElementSet, truth: ElementSet) -> dict[str, Any] | None:
    """The GP set against the truth over the span after the truth's epoch, in km; None when
    SGP4 cannot propagate either over the span."""
    start = truth.epoch
    gp_errors, gp_r, _ = _states(gp, start)
    errors, r, v = _states(truth, start)
    if np.any(gp_errors) or np.any(errors):
        return None
    radial = r / np.linalg.norm(r, axis=1)[:, None]
    normal = np.cross(r, v)
    cross = normal / np.linalg.norm(normal, axis=1)[:, None]
    along = np.cross(cross, radial)
    difference = gp_r - r
    parts = {
        "radial": np.sum(difference * radial, axis=1),
        "in_track": np.sum(difference * along, axis=1),
        "cross_track": np.sum(difference * cross, axis=1),
    }
    total = np.linalg.norm(difference, axis=1)

    def rms(values: np.ndarray) -> float:
        return round(float(np.sqrt(np.mean(values**2))), 3)

    middle = start + timedelta(seconds=SPAN_S / 2)
    return {
        "age_days": round((middle - gp.epoch).total_seconds() / 86400, 3),
        "rms_km": rms(total),
        "max_km": round(float(np.max(total)), 3),
        "radial_rms_km": rms(parts["radial"]),
        "in_track_rms_km": rms(parts["in_track"]),
        "cross_track_rms_km": rms(parts["cross_track"]),
        "in_track_mean_km": round(float(np.mean(parts["in_track"])), 3),
    }


# A run in the cache -----------------------------------------------------------------------


@dataclass(frozen=True)
class Run:
    path: Path
    fetched_at: datetime
    supgp: dict[str, bytes]  # source -> CelesTrak's CSV as received
    history: dict[int, bytes]  # catalogue number -> SatChecker's answer as received


def run_dirs(cache_dir: Path) -> list[Path]:
    root = cache_dir / "reference-accuracy"
    if not root.is_dir():
        return []
    return sorted(p for p in root.iterdir() if (p / RUN_FILE).is_file())


def load_run(path: Path) -> Run:
    document = json.loads((path / RUN_FILE).read_text(encoding="utf-8"))
    if document.get("format") != RUN_FORMAT or not document.get("complete"):
        raise ValueError(f"{path} is not a complete run")
    supgp = {source: (path / f"supgp-{source}.csv").read_bytes() for source in document["sources"]}
    history = {int(n): (path / f"satchecker-{n}.json").read_bytes() for n in document["objects"]}
    return Run(path, _utc(document["fetched_at"]), supgp, history)


def earlier_runs(path: Path) -> list[Run]:
    """The complete runs beside ``path`` that were fetched before it, oldest first."""
    found = []
    for other in sorted(path.parent.iterdir()):
        if other.name >= path.name or not (other / RUN_FILE).is_file():
            continue
        try:
            found.append(load_run(other))
        except ValueError:
            continue  # an incomplete run is not used
    return found


def fetch_run(
    cache_dir: Path,
    *,
    now: Callable[[], datetime] = lambda: datetime.now(UTC),
    opener: Callable = urllib.request.urlopen,
    sleep: Callable[[float], None] = time.sleep,
    log: Callable[[str], None] = lambda message: None,
) -> Path:
    """Fetch one run into the cache: one SupGP download per source, then one SatChecker
    request per chosen object, ``PAUSE_S`` apart. Stops at the first answer that is not 200
    (the run then stays incomplete and unused). Refuses to start within two hours of the
    last run, since CelesTrak asks for that much between SupGP downloads."""
    moment = now().astimezone(UTC).replace(microsecond=0)
    previous = run_dirs(cache_dir)
    if previous:
        last = load_run(previous[-1]).fetched_at
        if (moment - last).total_seconds() < MIN_RUN_GAP_S:
            raise ValueError(
                f"the last run was fetched at {_stamp(last)}; CelesTrak asks for at least two "
                "hours between downloads of SupGP data, so measure that run again without "
                "--fetch, or wait"
            )
    path = cache_dir / "reference-accuracy" / moment.strftime("%Y%m%dT%H%M%SZ")
    path.mkdir(parents=True, exist_ok=False)
    catalogs: dict[str, Catalog] = {}
    for index, source in enumerate(SOURCES):
        if index:
            sleep(PAUSE_S)
        body = download_supgp("SOURCE", source, opener=opener)
        (path / f"supgp-{source}.csv").write_bytes(body)
        catalogs[source] = parse_catalog(body)
        log(f"SupGP {source}: {sum(len(s) for s in catalogs[source].sets.values())} set(s)")
    truths = choose_truths(catalogs, moment)
    objects = sorted({t.norad_id for t in truths})
    for norad_id in objects:
        sleep(PAUSE_S)
        epochs = [t.epoch for t in truths if t.norad_id == norad_id]
        start = min(epochs) - timedelta(days=HISTORY_DAYS)
        body = download(history_url(norad_id, start, max(epochs)), opener=opener)
        (path / f"satchecker-{norad_id}.json").write_bytes(body)
        log(f"SatChecker {norad_id}: {len(body)} bytes")
    document = {
        "format": RUN_FORMAT,
        "fetched_at": _stamp(moment),
        "sources": list(SOURCES),
        "objects": objects,
        "complete": True,
    }
    (path / RUN_FILE).write_text(json.dumps(document, indent=2) + "\n", encoding="utf-8")
    return path


# The measurement --------------------------------------------------------------------------


def measure(run: Run, earlier: Sequence[Run] = ()) -> dict[str, Any]:
    """Every comparison of one run, and the inputs by epoch and SHA-256. With ``earlier``
    runs, also how operators' orbits age between the runs."""
    catalogs = {source: parse_catalog(body) for source, body in sorted(run.supgp.items())}
    truths = choose_truths(catalogs, run.fetched_at)
    histories = {n: parse_history(body, n) for n, body in sorted(run.history.items())}
    runs = sorted([*earlier, run], key=lambda r: r.fetched_at)
    ageing, unchanged = operator_ageing(runs)
    comparisons: list[dict[str, Any]] = []
    truth_rows: list[dict[str, Any]] = []
    skipped = same = 0
    truth_index: dict[str, int] = {}
    for truth in truths:
        truth_set = truth.sup.element_set
        truth_index.setdefault(truth_set.sha256, len(truth_index))
        truth_rows.append(
            {
                "norad_id": truth.norad_id,
                "object": truth.name,
                "source": truth.source,
                "data_source": truth.sup.data_source,
                "orbit": truth.orbit,
                "epoch": truth_set.record["EPOCH"],
                "sha256": truth_set.sha256,
                "supgp_rms_km": truth.sup.rms_km,
            }
        )
        earliest = truth.epoch - timedelta(days=HISTORY_DAYS)
        gp_catalog = _history_catalog(histories.get(truth.norad_id, []))
        if gp_catalog is None:
            continue
        for gp in gp_catalog.element_sets(truth.norad_id):
            if not earliest <= gp.epoch <= truth.epoch:
                continue
            result = compare(gp, truth_set)
            if result is None:
                skipped += 1
                continue
            if gp.epoch == truth.epoch and result["max_km"] < SAME_KM:
                same += 1  # SatChecker keeps the truth itself among CelesTrak's sets
                continue
            source = gp.source or {}
            comparisons.append(
                {
                    "norad_id": truth.norad_id,
                    "source": truth.source,
                    "orbit": truth.orbit,
                    "truth_sha256": truth_set.sha256,
                    "gp_epoch": gp.record["EPOCH"],
                    "gp_sha256": gp.sha256,
                    "gp_data_source": source.get("data_source", ""),
                    "gp_collected": source.get("date_collected", ""),
                    **result,
                }
            )
    return {
        "format": RESULTS_FORMAT,
        "format_version": RESULTS_FORMAT_VERSION,
        "simulated": False,
        "software": f"orbit-watch {__version__}",
        "settings": {
            "sources": list(SOURCES),
            "per_group": PER_GROUP,
            "iss_segments": ISS_SEGMENTS,
            "history_days": HISTORY_DAYS,
            "span_s": SPAN_S,
            "step_s": STEP_S,
        },
        "run": {"fetched_at": _stamp(run.fetched_at), "directory": run.path.name},
        "runs": [{"fetched_at": _stamp(r.fetched_at), "directory": r.path.name} for r in runs],
        "truths": truth_rows,
        "comparisons": {
            "columns": list(COLUMNS),
            "rows": [_row(c, truth_index) for c in comparisons],
        },
        "not_propagated": skipped,
        "same_as_truth": same,
        "operator_ageing": {
            "columns": list(AGEING_COLUMNS),
            "rows": [[row[column] for column in AGEING_COLUMNS] for row in ageing],
            "unchanged": unchanged,
        },
        "summary": {**summary(comparisons, truth_rows), **ageing_summary(ageing)},
    }


# One comparison per row: the truth by its place in ``truths``, the GP set by epoch, source,
# collection time and SHA-256, then the differences in km and the set's age in days.
COLUMNS = (
    "truth",
    "gp_epoch",
    "gp_data_source",
    "gp_collected",
    "gp_sha256",
    "age_days",
    "rms_km",
    "max_km",
    "radial_rms_km",
    "in_track_rms_km",
    "cross_track_rms_km",
    "in_track_mean_km",
)


def _row(comparison: dict[str, Any], truth_index: dict[str, int]) -> list[Any]:
    values = {**comparison, "truth": truth_index[comparison["truth_sha256"]]}
    return [values[column] for column in COLUMNS]


def comparison_rows(results: dict[str, Any]) -> list[dict[str, Any]]:
    """The comparisons of written results as dictionaries, with their truth's fields."""
    truths = results["truths"]
    rows = []
    for row in results["comparisons"]["rows"]:
        values = dict(zip(results["comparisons"]["columns"], row, strict=True))
        truth = truths[values["truth"]]
        rows.append({**values, "norad_id": truth["norad_id"], "source": truth["source"]})
    return rows


def dumps_results(results: dict[str, Any]) -> str:
    """The results as JSON, readable, with each comparison on one line."""
    marked = dict(results)
    rows: list[list[Any]] = []
    for key in ("comparisons", "operator_ageing"):
        if key not in results:
            continue
        table = results[key]
        marks = [f"@@row{len(rows) + i}@@" for i in range(len(table["rows"]))]
        rows += table["rows"]
        marked[key] = {**table, "rows": marks}
    text = dumps_pretty(marked, sort_keys=False)
    for i, row in enumerate(rows):
        text = text.replace(f'"@@row{i}@@"', json.dumps(row, ensure_ascii=False), 1)
    return text


def _history_catalog(sets: list) -> Catalog | None:
    if not sets:
        return None
    wrapper = {"format": "orbit-watch/gp-catalog", "records": [s.record for s in sets]}
    return parse_catalog(json.dumps(wrapper).encode())


def _bin(age: float) -> str | None:
    for low, high in AGE_BINS:
        if low <= age < high:
            return f"{low:g}{DASH}{high:g}"
    return None


def _stats(values: Iterable[float]) -> dict[str, float | int | None]:
    data = np.array(list(values), dtype=float)
    if data.size == 0:
        return {"n": 0, "median": None, "p90": None, "max": None}
    return {
        "n": int(data.size),
        "median": round(float(np.median(data)), 3),
        "p90": round(float(np.percentile(data, 90)), 3),
        "max": round(float(np.max(data)), 3),
    }


def summary(comparisons: list[dict[str, Any]], truths: list[dict[str, Any]]) -> dict[str, Any]:
    by_age: dict[str, dict[str, Any]] = {}
    for orbit in sorted({c["orbit"] for c in comparisons}):
        for low, high in AGE_BINS:
            label = f"{low:g}{DASH}{high:g}"
            rows = [c for c in comparisons if c["orbit"] == orbit and _bin(c["age_days"]) == label]
            if not rows:
                continue
            by_age[f"{orbit} {label}"] = {
                "orbit": orbit,
                "age_days": label,
                "objects": len({r["norad_id"] for r in rows}),
                "rms_km": _stats(r["rms_km"] for r in rows),
                "in_track_rms_km": _stats(r["in_track_rms_km"] for r in rows),
                "cross_track_rms_km": _stats(r["cross_track_rms_km"] for r in rows),
                "radial_rms_km": _stats(r["radial_rms_km"] for r in rows),
            }
    newest: dict[str, dict[str, Any]] = {}
    for key in sorted({(c["source"], c["orbit"]) for c in comparisons}):
        rows = []
        for truth in {c["truth_sha256"] for c in comparisons if (c["source"], c["orbit"]) == key}:
            candidates = [c for c in comparisons if c["truth_sha256"] == truth]
            rows.append(min(candidates, key=lambda c: (c["age_days"], c["gp_sha256"])))
        newest[f"{key[0]} {key[1]}"] = {
            "source": key[0],
            "orbit": key[1],
            "truths": len(rows),
            "age_days": _stats(r["age_days"] for r in rows),
            "rms_km": _stats(r["rms_km"] for r in rows),
        }
    sources = {}
    for source in sorted({t["source"] for t in truths}):
        rows = [t for t in truths if t["source"] == source]
        sources[source] = {
            "truths": len(rows),
            "objects": len({t["norad_id"] for t in rows}),
            "supgp_rms_km": _stats(
                t["supgp_rms_km"] for t in rows if t["supgp_rms_km"] is not None
            ),
            "comparisons": sum(1 for c in comparisons if c["source"] == source),
        }
    leo_by_source: dict[str, dict[str, Any]] = {}
    for source in sorted({c["source"] for c in comparisons if c["orbit"] == "LEO"}):
        cells = {}
        for low, high in AGE_BINS:
            label = f"{low:g}{DASH}{high:g}"
            cells[label] = _stats(
                c["rms_km"]
                for c in comparisons
                if c["source"] == source and c["orbit"] == "LEO" and _bin(c["age_days"]) == label
            )
        leo_by_source[source] = cells
    return {
        "by_age": by_age,
        "newest_set": newest,
        "sources": sources,
        "leo_by_source": leo_by_source,
    }


# How operators' orbits age --------------------------------------------------------------

# One pair per row: the truth of a later run, against the object's operator set as an earlier
# run had it, beside the newest GP set collected by the earlier run.
AGEING_COLUMNS = (
    "earlier_run",
    "later_run",
    "norad_id",
    "source",
    "orbit",
    "truth_epoch",
    "truth_sha256",
    "set_epoch",
    "set_data_source",
    "set_sha256",
    "age_days",
    "rms_km",
    "radial_rms_km",
    "in_track_rms_km",
    "cross_track_rms_km",
    "gp_epoch",
    "gp_sha256",
    "gp_age_days",
    "gp_rms_km",
)


def _collected_at(element_set: ElementSet) -> datetime | None:
    """When SatChecker collected a set, from its ``date_collected``."""
    text = str((element_set.source or {}).get("date_collected", ""))
    try:
        return datetime.strptime(text[:19], "%Y-%m-%d %H:%M:%S").replace(tzinfo=UTC)
    except ValueError:
        return None


def _newest_gp(history: list, norad_id: int, moment: datetime) -> ElementSet | None:
    """The GP set with the latest epoch among those SatChecker had collected by ``moment``."""
    catalog = _history_catalog(history)
    if catalog is None:
        return None
    collected = [
        s
        for s in catalog.element_sets(norad_id)
        if (at := _collected_at(s)) is not None and at <= moment
    ]
    if not collected:
        return None
    return max(collected, key=lambda s: (s.epoch, s.sha256))


def operator_ageing(runs: Sequence[Run]) -> tuple[list[dict[str, Any]], int]:
    """Every pair of an earlier and a later run: each truth of the later run against the set
    its operator had published by the earlier run with the latest epoch at or before the
    truth's, and beside the newest GP set SatChecker had collected by then, from the later
    run's answer. Returns the pairs and how many sets were unchanged between the runs."""
    ordered = sorted(runs, key=lambda r: r.fetched_at)
    catalogs = [
        {source: parse_catalog(body) for source, body in sorted(r.supgp.items())} for r in ordered
    ]
    rows: list[dict[str, Any]] = []
    unchanged = 0
    for j, later in enumerate(ordered):
        if not j:
            continue
        truths = choose_truths(catalogs[j], later.fetched_at)
        histories = {
            norad: parse_history(later.history[norad], norad)
            for norad in sorted({t.norad_id for t in truths})
            if norad in later.history
        }
        for i, before in enumerate(ordered[:j]):
            for truth in truths:
                catalog = catalogs[i].get(truth.source)
                if catalog is None or truth.norad_id not in catalog.sets:
                    continue
                older = _latest_before(sup_sets(catalog, truth.norad_id), truth.epoch)
                if older is None:
                    continue
                truth_set = truth.sup.element_set
                if older.element_set.sha256 == truth_set.sha256:
                    unchanged += 1
                    continue
                result = compare(older.element_set, truth_set)
                if result is None:
                    continue
                history = histories.get(truth.norad_id, [])
                gp = _newest_gp(history, truth.norad_id, before.fetched_at)
                gp_result = None if gp is None else compare(gp, truth_set)
                rows.append(
                    {
                        "earlier_run": before.path.name,
                        "later_run": later.path.name,
                        "norad_id": truth.norad_id,
                        "source": truth.source,
                        "orbit": truth.orbit,
                        "truth_epoch": truth_set.record["EPOCH"],
                        "truth_sha256": truth_set.sha256,
                        "set_epoch": older.element_set.record["EPOCH"],
                        "set_data_source": older.data_source,
                        "set_sha256": older.element_set.sha256,
                        **{k: result[k] for k in AGEING_COLUMNS if k in result},
                        "gp_epoch": None if gp is None else gp.record["EPOCH"],
                        "gp_sha256": None if gp is None else gp.sha256,
                        "gp_age_days": None if gp_result is None else gp_result["age_days"],
                        "gp_rms_km": None if gp_result is None else gp_result["rms_km"],
                    }
                )
    return rows, unchanged


def ageing_rows(results: dict[str, Any]) -> list[dict[str, Any]]:
    """The pairs of written results as dictionaries."""
    table = results["operator_ageing"]
    return [dict(zip(table["columns"], row, strict=True)) for row in table["rows"]]


def ageing_summary(rows: list[dict[str, Any]]) -> dict[str, Any]:
    by_age: dict[str, dict[str, Any]] = {}
    for key in sorted({(r["source"], r["orbit"]) for r in rows}):
        for low, high in AGE_BINS:
            label = f"{low:g}{DASH}{high:g}"
            chosen = [
                r for r in rows if (r["source"], r["orbit"]) == key and _bin(r["age_days"]) == label
            ]
            if not chosen:
                continue
            by_age[f"{key[0]} {key[1]} {label}"] = {
                "source": key[0],
                "orbit": key[1],
                "age_days": label,
                "objects": len({r["norad_id"] for r in chosen}),
                "rms_km": _stats(r["rms_km"] for r in chosen),
                "in_track_rms_km": _stats(r["in_track_rms_km"] for r in chosen),
                "cross_track_rms_km": _stats(r["cross_track_rms_km"] for r in chosen),
            }
    against_gp: dict[str, dict[str, Any]] = {}
    for key in sorted({(r["source"], r["orbit"]) for r in rows}):
        pairs = [r for r in rows if (r["source"], r["orbit"]) == key and r["gp_rms_km"] is not None]
        if not pairs:
            continue
        against_gp[f"{key[0]} {key[1]}"] = {
            "source": key[0],
            "orbit": key[1],
            "pairs": len(pairs),
            "operator_closer": sum(1 for r in pairs if r["rms_km"] < r["gp_rms_km"] - SAME_KM),
            "gp_closer": sum(1 for r in pairs if r["gp_rms_km"] < r["rms_km"] - SAME_KM),
            "operator_age_days": _stats(r["age_days"] for r in pairs),
            "operator_rms_km": _stats(r["rms_km"] for r in pairs),
            "gp_age_days": _stats(r["gp_age_days"] for r in pairs),
            "gp_rms_km": _stats(r["gp_rms_km"] for r in pairs),
        }
    return {"operator_by_age": by_age, "operator_against_gp": against_gp}


# The document -----------------------------------------------------------------------------


def _km(value: float | None) -> str:
    if value is None:
        return DASH
    return f"{value:,.2f}" if value < 10 else f"{value:,.1f}"


def _table(header: list[str], rows: list[list[str]]) -> str:
    lines = ["| " + " | ".join(header) + " |", "|" + "|".join("---" for _ in header) + "|"]
    lines += ["| " + " | ".join(row) + " |" for row in rows]
    return "\n".join(lines)


def tables(results: dict[str, Any]) -> dict[str, str]:
    s = results["summary"]
    sources = _table(
        ["Source", "Objects", "Truth sets", "SupGP's own fit, median (km)", "GP sets compared"],
        [
            [
                f"`{name}`",
                str(row["objects"]),
                str(row["truths"]),
                _km(row["supgp_rms_km"]["median"]),
                str(row["comparisons"]),
            ]
            for name, row in s["sources"].items()
        ],
    )
    newest = _table(
        [
            "Source",
            "Orbit",
            "Truth sets",
            "Newest set's age, median (days)",
            "Median (km)",
            "90 % (km)",
            "Largest (km)",
        ],
        [
            [
                f"`{row['source']}`",
                row["orbit"],
                str(row["truths"]),
                f"{row['age_days']['median']:.2f}",
                _km(row["rms_km"]["median"]),
                _km(row["rms_km"]["p90"]),
                _km(row["rms_km"]["max"]),
            ]
            for row in s["newest_set"].values()
        ],
    )
    by_age = _table(
        [
            "Orbit",
            "Set's age (days)",
            "Comparisons",
            "Objects",
            "Median (km)",
            "90 % (km)",
            "In track, median (km)",
            "Cross track, median (km)",
            "Radial, median (km)",
        ],
        [
            [
                row["orbit"],
                row["age_days"],
                str(row["rms_km"]["n"]),
                str(row["objects"]),
                _km(row["rms_km"]["median"]),
                _km(row["rms_km"]["p90"]),
                _km(row["in_track_rms_km"]["median"]),
                _km(row["cross_track_rms_km"]["median"]),
                _km(row["radial_rms_km"]["median"]),
            ]
            for row in s["by_age"].values()
        ],
    )
    run = (
        f"Run fetched {results['run']['fetched_at']}: {len(results['truths'])} truth sets of "
        f"{len({t['norad_id'] for t in results['truths']})} objects, "
        f"{len(results['comparisons']['rows'])} comparisons with GP sets, "
        f"{results['not_propagated']} not propagated, {results['same_as_truth']} left out as "
        "the truth itself."
    )
    labels = [f"{low:g}{DASH}{high:g}" for low, high in AGE_BINS]
    leo = _table(
        ["Source", *(f"{label} days" for label in labels)],
        [
            [f"`{source}`", *(_cell(cells[label]) for label in labels)]
            for source, cells in s["leo_by_source"].items()
        ],
    )
    operator_by_age = _table(
        [
            "Source",
            "Orbit",
            "Set's age (days)",
            "Pairs",
            "Objects",
            "Median (km)",
            "90 % (km)",
            "Largest (km)",
            "In track, median (km)",
            "Cross track, median (km)",
        ],
        [
            [
                f"`{row['source']}`",
                row["orbit"],
                row["age_days"],
                str(row["rms_km"]["n"]),
                str(row["objects"]),
                _km(row["rms_km"]["median"]),
                _km(row["rms_km"]["p90"]),
                _km(row["rms_km"]["max"]),
                _km(row["in_track_rms_km"]["median"]),
                _km(row["cross_track_rms_km"]["median"]),
            ]
            for row in s["operator_by_age"].values()
        ],
    )
    against_gp = _table(
        [
            "Source",
            "Orbit",
            "Pairs",
            "Operator's set closer",
            "GP set closer",
            "Operator's set: age, median (days)",
            "Median (km)",
            "Newest GP set: age, median (days)",
            "Median (km)",
        ],
        [
            [
                f"`{row['source']}`",
                row["orbit"],
                str(row["pairs"]),
                str(row["operator_closer"]),
                str(row["gp_closer"]),
                f"{row['operator_age_days']['median']:.2f}",
                _km(row["operator_rms_km"]["median"]),
                f"{row['gp_age_days']['median']:.2f}",
                _km(row["gp_rms_km"]["median"]),
            ]
            for row in s["operator_against_gp"].values()
        ],
    )
    ageing = results["operator_ageing"]
    runs = ", ".join(r["fetched_at"] for r in results["runs"])
    ageing_run = (
        f"Runs fetched {runs}: {len(ageing['rows'])} pairs of an operator's set and a later "
        f"one, {ageing['unchanged']} sets unchanged between the runs."
    )
    return {
        "run": run,
        "sources": sources,
        "newest_set": newest,
        "by_age": by_age,
        "leo_by_source": leo,
        "ageing_run": ageing_run,
        "operator_by_age": operator_by_age,
        "operator_against_gp": against_gp,
    }


def _cell(stats: dict[str, Any]) -> str:
    """A median and a 90th percentile in km, as "0.26 (1.10)"."""
    if not stats["n"]:
        return DASH
    return f"{_km(stats['median'])} ({_km(stats['p90'])})"

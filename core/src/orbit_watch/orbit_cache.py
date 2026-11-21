"""Real reference orbits named in a manifest and kept in a cache outside the repository.

Decision P5-05 (confirming D-06): the repository commits no real element sets. Examples
with real observations name their reference orbits in a manifest instead
(``orbit-watch/reference-orbits``): the object, the source, the epoch and the SHA-256 of
the original element set. ``fill`` fetches what the cache lacks, politely and by the exact
epoch, and checks every SHA-256; ``catalog_from_cache`` builds the catalogue that
verification and the quality meter read. Tests that need the cache are skipped without
it; CI keeps it in GitHub Actions' cache only.

The cache is ``$ORBIT_WATCH_CACHE``, or ``orbit-watch`` under ``$XDG_CACHE_HOME`` (by
default ``~/.cache``). It holds SatChecker's answers as received, one file per element set
named by its SHA-256.
"""

from __future__ import annotations

import json
import os
import time
import urllib.request
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from orbit_watch.canonical import dumps_pretty
from orbit_watch.satchecker import KINDS, PAUSE_S, NearestSet, fetch_nearest, parse_answer

MANIFEST_FORMAT = "orbit-watch/reference-orbits"
MANIFEST_FORMAT_VERSION = "1.0"
SOURCES = ("satchecker",)


class CacheError(ValueError):
    """The manifest or the cache is not as expected."""


@dataclass(frozen=True)
class Entry:
    norad_id: int
    kind: str
    source: str
    epoch: str
    sha256: str

    @property
    def time(self) -> datetime:
        parsed = datetime.fromisoformat(self.epoch.replace("Z", "+00:00"))
        return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)

    def to_document(self) -> dict[str, Any]:
        return {
            "norad_id": self.norad_id,
            "kind": self.kind,
            "source": self.source,
            "epoch": self.epoch,
            "sha256": self.sha256,
        }


@dataclass
class Manifest:
    entries: list[Entry]
    description: str = ""

    def to_document(self) -> dict[str, Any]:
        entries = sorted(self.entries, key=lambda e: (e.norad_id, e.epoch, e.sha256))
        return {
            "format": MANIFEST_FORMAT,
            "format_version": MANIFEST_FORMAT_VERSION,
            "description": self.description,
            "element_sets": [e.to_document() for e in entries],
        }

    def add(self, nearest: NearestSet) -> bool:
        """Name an element set; False if the manifest already names it."""
        if any(e.sha256 == nearest.sha256 for e in self.entries):
            return False
        self.entries.append(
            Entry(nearest.norad_id, nearest.kind, "satchecker", nearest.epoch, nearest.sha256)
        )
        return True


def parse_manifest(data: bytes) -> Manifest:
    try:
        document = json.loads(data.decode("utf-8"))
    except (ValueError, UnicodeDecodeError) as exc:
        raise CacheError(f"the manifest is not JSON: {exc}") from None
    if not isinstance(document, dict) or document.get("format") != MANIFEST_FORMAT:
        raise CacheError(f"not an {MANIFEST_FORMAT} document")
    if document.get("format_version") != MANIFEST_FORMAT_VERSION:
        raise CacheError(f"unsupported format_version {document.get('format_version')!r}")
    entries = []
    for index, item in enumerate(document.get("element_sets", [])):
        try:
            entry = Entry(
                int(item["norad_id"]),
                str(item["kind"]),
                str(item["source"]),
                str(item["epoch"]),
                str(item["sha256"]).lower(),
            )
            entry.time  # noqa: B018 - the epoch must be a time
        except (KeyError, TypeError, ValueError) as exc:
            raise CacheError(f"element set {index} is not valid: {exc}") from None
        if entry.kind not in KINDS or entry.source not in SOURCES:
            raise CacheError(f"element set {index}: unknown kind or source")
        if len(entry.sha256) != 64:
            raise CacheError(f"element set {index}: sha256 is not a SHA-256")
        entries.append(entry)
    return Manifest(entries, str(document.get("description", "")))


def write_manifest(path: Path, manifest: Manifest) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(dumps_pretty(manifest.to_document(), sort_keys=False), encoding="utf-8")


def default_cache_dir() -> Path:
    explicit = os.environ.get("ORBIT_WATCH_CACHE")
    if explicit:
        return Path(explicit)
    base = os.environ.get("XDG_CACHE_HOME") or str(Path.home() / ".cache")
    return Path(base) / "orbit-watch"


def cache_file(cache_dir: Path, entry: Entry) -> Path:
    return cache_dir / entry.source / f"{entry.sha256}.json"


def store(cache_dir: Path, nearest: NearestSet) -> Path:
    """Keep SatChecker's answer as received, named by the element set's SHA-256."""
    path = cache_dir / "satchecker" / f"{nearest.sha256}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".part")
    temporary.write_bytes(nearest.answer)
    temporary.replace(path)
    return path


def cached(cache_dir: Path, entry: Entry) -> NearestSet | None:
    """The cached element set, checked against the manifest; None if it is not cached."""
    path = cache_file(cache_dir, entry)
    if not path.is_file():
        return None
    nearest = parse_answer(
        path.read_bytes(), entry.norad_id, entry.kind, endpoint=f"get-nearest-{entry.kind}"
    )
    if nearest.sha256 != entry.sha256:
        raise CacheError(f"{path} does not hold the element set the manifest names")
    return nearest


def missing(manifest: Manifest, cache_dir: Path) -> list[Entry]:
    return [e for e in manifest.entries if not cache_file(cache_dir, e).is_file()]


def fill(
    entries: Iterable[Entry],
    cache_dir: Path,
    *,
    opener: Callable = urllib.request.urlopen,
    sleep: Callable[[float], None] = time.sleep,
    log: Callable[[str], None] = lambda message: None,
) -> tuple[int, int]:
    """Fetch every element set the cache lacks, one request at a time and ``PAUSE_S``
    apart. Stops at the first answer that is not 200, and at the first set that is not the
    one the manifest names. Returns (fetched, already cached)."""
    fetched = present = 0
    for entry in entries:
        if cached(cache_dir, entry) is not None:
            present += 1
            continue
        if fetched:
            sleep(PAUSE_S)
        nearest = fetch_nearest(entry.norad_id, entry.time, kind=entry.kind, opener=opener)
        if nearest.sha256 != entry.sha256:
            raise CacheError(
                f"SatChecker's set of {entry.norad_id} nearest {entry.epoch} is not the one the "
                f"manifest names (got epoch {nearest.epoch}, SHA-256 {nearest.sha256})"
            )
        store(cache_dir, nearest)
        fetched += 1
        log(f"fetched {entry.norad_id} at {entry.epoch}")
    return fetched, present


def catalog_document(manifest: Manifest, cache_dir: Path) -> dict[str, Any]:
    """The ``orbit-watch/gp-catalog`` of the manifest's element sets, from the cache."""
    absent = missing(manifest, cache_dir)
    if absent:
        raise CacheError(
            f"{len(absent)} element set(s) of the manifest are not in the cache {cache_dir}; "
            "run orbit-watch fetch-orbits"
        )
    records = []
    for entry in sorted(manifest.entries, key=lambda e: (e.norad_id, e.epoch, e.sha256)):
        nearest = cached(cache_dir, entry)
        assert nearest is not None
        records.append(nearest.record)
    return {
        "format": "orbit-watch/gp-catalog",
        "format_version": "1.0",
        "simulated": False,
        "description": (
            "Real element sets from the IAU CPS's SatChecker, named in a manifest and fetched "
            "into a local cache. Not for redistribution (decision D-06)."
        ),
        "records": records,
    }


def catalog_from_cache(manifest: Manifest, cache_dir: Path) -> bytes:
    return dumps_pretty(catalog_document(manifest, cache_dir), sort_keys=False).encode("utf-8")

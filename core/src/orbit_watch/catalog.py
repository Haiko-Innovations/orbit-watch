"""Reference orbits from General Perturbations (GP) element sets in OMM form.

Accepted inputs:

* CelesTrak GP data in JSON or CSV form (``FORMAT=JSON`` / ``FORMAT=CSV``),
  which use OMM keywords (https://celestrak.org/NORAD/documentation/gp-data-formats.php);
* an Orbit Watch catalogue wrapper with metadata, used for simulated objects
  and for element sets fetched from SatChecker:
  ``{"format": "orbit-watch/gp-catalog", "simulated": true, "records": [...]}``.
  A wrapper's record may carry a ``source`` object (where the set came from),
  which is not an OMM field and is not passed to SGP4.

A catalogue may hold several element sets of one object (decision P5-04).
``Catalog.nearest`` gives the set whose epoch is nearest a time; ``records`` and
``satellite`` give the newest set, as before.

Satellites are built with Skyfield's ``EarthSatellite.from_omm`` (SGP4).
TLE input is not read here because TLEs cannot hold catalogue numbers above
99999 (Alpha-5 aside); ``orbit_watch.satchecker`` converts past TLEs to OMM form.
"""

from __future__ import annotations

import csv
import io
import json
from dataclasses import dataclass, field
from datetime import datetime
from functools import cache
from typing import Any

from skyfield.api import EarthSatellite, load

from orbit_watch.canonical import dumps_compact, sha256_bytes

REQUIRED_OMM_FIELDS = (
    "OBJECT_NAME",
    "OBJECT_ID",
    "EPOCH",
    "MEAN_MOTION",
    "ECCENTRICITY",
    "INCLINATION",
    "RA_OF_ASC_NODE",
    "ARG_OF_PERICENTER",
    "MEAN_ANOMALY",
    "EPHEMERIS_TYPE",
    "CLASSIFICATION_TYPE",
    "NORAD_CAT_ID",
    "ELEMENT_SET_NO",
    "REV_AT_EPOCH",
    "BSTAR",
    "MEAN_MOTION_DOT",
    "MEAN_MOTION_DDOT",
)


class CatalogError(ValueError):
    pass


@cache
def timescale():
    """Skyfield timescale with the leap-second table built into Skyfield (no download)."""
    return load.timescale(builtin=True)


# A wrapper record's key for where the element set came from: not an OMM field.
SOURCE_KEY = "source"


@dataclass(frozen=True)
class ElementSet:
    """One element set of one object, with the orbit SGP4 builds from it."""

    norad_id: int
    record: dict[str, Any]
    satellite: EarthSatellite
    epoch: datetime
    sha256: str  # of the record's OMM fields as compact canonical JSON, without its source

    @property
    def source(self) -> dict[str, Any] | None:
        source = self.record.get(SOURCE_KEY)
        return source if isinstance(source, dict) else None


@dataclass
class Catalog:
    records: dict[int, dict[str, Any]]
    simulated: bool = False
    description: str | None = None
    # Every element set per object, in the order read; ``records`` holds the newest.
    sets: dict[int, list[dict[str, Any]]] = field(default_factory=dict)
    _satellites: dict[int, EarthSatellite] = field(default_factory=dict, repr=False)
    _element_sets: dict[int, list[ElementSet]] = field(default_factory=dict, repr=False)

    def __post_init__(self) -> None:
        for norad_id, record in self.records.items():
            self.sets.setdefault(norad_id, [record])

    def __contains__(self, norad_id: int) -> bool:
        return norad_id in self.records

    def record(self, norad_id: int) -> dict[str, Any]:
        return self.records[norad_id]

    def satellite(self, norad_id: int) -> EarthSatellite:
        """The orbit of the object's newest element set."""
        if norad_id not in self._satellites:
            self._satellites[norad_id] = _build(norad_id, self.records[norad_id])
        return self._satellites[norad_id]

    def name(self, norad_id: int) -> str:
        return str(self.records[norad_id].get("OBJECT_NAME", norad_id))

    def element_sets(self, norad_id: int) -> list[ElementSet]:
        """Every element set of the object, oldest epoch first."""
        if norad_id not in self._element_sets:
            built = []
            for record in self.sets[norad_id]:
                satellite = _build(norad_id, record)
                built.append(
                    ElementSet(
                        norad_id,
                        record,
                        satellite,
                        satellite.epoch.utc_datetime(),
                        record_sha256(record),
                    )
                )
            built.sort(key=lambda s: (s.epoch, s.sha256))
            self._element_sets[norad_id] = built
        return self._element_sets[norad_id]

    def nearest(self, norad_id: int, when: datetime) -> ElementSet:
        """The element set whose epoch is nearest ``when``; on a tie, the earlier one."""
        return min(
            self.element_sets(norad_id),
            key=lambda s: (abs((s.epoch - when).total_seconds()), s.epoch, s.sha256),
        )


def _build(norad_id: int, record: dict[str, Any]) -> EarthSatellite:
    try:
        return EarthSatellite.from_omm(timescale(), _as_strings(record))
    except (KeyError, ValueError) as exc:
        raise CatalogError(f"cannot build an orbit for {norad_id}: {exc}") from None


def omm_fields(record: dict[str, Any]) -> dict[str, Any]:
    """A record without the wrapper's ``source``: the OMM fields only."""
    return {key: value for key, value in record.items() if key != SOURCE_KEY}


def record_sha256(record: dict[str, Any]) -> str:
    """SHA-256 of a record's OMM fields as compact canonical JSON."""
    return sha256_bytes(dumps_compact(omm_fields(record)).encode("utf-8"))


def _as_strings(record: dict[str, Any]) -> dict[str, str]:
    return {key: str(value) for key, value in omm_fields(record).items()}


def _check_record(record: Any, index: int) -> tuple[int, dict[str, Any]]:
    if not isinstance(record, dict):
        raise CatalogError(f"record {index} is not an object")
    missing = [f for f in REQUIRED_OMM_FIELDS if f not in record]
    if missing:
        raise CatalogError(f"record {index} lacks OMM field(s): {', '.join(missing)}")
    try:
        norad_id = int(record["NORAD_CAT_ID"])
    except (TypeError, ValueError):
        raise CatalogError(f"record {index}: NORAD_CAT_ID is not an integer") from None
    return norad_id, dict(record)


def parse_catalog(data: bytes) -> Catalog:
    """Parse GP data (CelesTrak JSON or CSV, or the Orbit Watch wrapper)."""
    text = data.decode("utf-8-sig")
    stripped = text.lstrip()
    simulated, description = False, None
    if stripped.startswith("[") or stripped.startswith("{"):
        document = json.loads(text)
        if isinstance(document, dict):
            if document.get("format") != "orbit-watch/gp-catalog":
                raise CatalogError("JSON object is not an orbit-watch/gp-catalog document")
            simulated = bool(document.get("simulated", False))
            description = document.get("description")
            rows = document.get("records", [])
        else:
            rows = document
    else:
        rows = list(csv.DictReader(io.StringIO(text)))
    records: dict[int, dict[str, Any]] = {}
    sets: dict[int, list[dict[str, Any]]] = {}
    seen: set[str] = set()
    for index, row in enumerate(rows):
        norad_id, record = _check_record(row, index)
        if SOURCE_KEY in record and not isinstance(record[SOURCE_KEY], dict):
            raise CatalogError(f"record {index}: {SOURCE_KEY} is not an object")
        digest = record_sha256(record)
        if digest in seen:  # the same element set twice
            continue
        seen.add(digest)
        sets.setdefault(norad_id, []).append(record)
        # The newest element set of an object, as before P5-04.
        if norad_id in records and str(record["EPOCH"]) <= str(records[norad_id]["EPOCH"]):
            continue
        records[norad_id] = record
    if not records:
        raise CatalogError("no GP records found")
    return Catalog(records=records, simulated=simulated, description=description, sets=sets)

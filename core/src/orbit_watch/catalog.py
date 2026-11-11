"""Reference orbits from General Perturbations (GP) element sets in OMM form.

Accepted inputs:

* CelesTrak GP data in JSON or CSV form (``FORMAT=JSON`` / ``FORMAT=CSV``),
  which use OMM keywords (https://celestrak.org/NORAD/documentation/gp-data-formats.php);
* an Orbit Watch catalogue wrapper with metadata, used for simulated objects:
  ``{"format": "orbit-watch/gp-catalog", "simulated": true, "records": [...]}``.

Satellites are built with Skyfield's ``EarthSatellite.from_omm`` (SGP4).
TLE input is not supported because TLEs cannot hold catalogue numbers above
99999 (Alpha-5 aside).
"""

from __future__ import annotations

import csv
import io
import json
from dataclasses import dataclass, field
from functools import cache
from typing import Any

from skyfield.api import EarthSatellite, load

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


@dataclass
class Catalog:
    records: dict[int, dict[str, Any]]
    simulated: bool = False
    description: str | None = None
    _satellites: dict[int, EarthSatellite] = field(default_factory=dict, repr=False)

    def __contains__(self, norad_id: int) -> bool:
        return norad_id in self.records

    def record(self, norad_id: int) -> dict[str, Any]:
        return self.records[norad_id]

    def satellite(self, norad_id: int) -> EarthSatellite:
        if norad_id not in self._satellites:
            try:
                self._satellites[norad_id] = EarthSatellite.from_omm(
                    timescale(), _as_strings(self.records[norad_id])
                )
            except (KeyError, ValueError) as exc:
                raise CatalogError(f"cannot build an orbit for {norad_id}: {exc}") from None
        return self._satellites[norad_id]

    def name(self, norad_id: int) -> str:
        return str(self.records[norad_id].get("OBJECT_NAME", norad_id))


def _as_strings(record: dict[str, Any]) -> dict[str, str]:
    return {key: str(value) for key, value in record.items()}


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
    for index, row in enumerate(rows):
        norad_id, record = _check_record(row, index)
        # Keep the newest element set for an object.
        if norad_id in records and str(record["EPOCH"]) <= str(records[norad_id]["EPOCH"]):
            continue
        records[norad_id] = record
    if not records:
        raise CatalogError("no GP records found")
    return Catalog(records=records, simulated=simulated, description=description)

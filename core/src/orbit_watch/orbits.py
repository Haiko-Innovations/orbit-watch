"""Reference orbits in the service (phase 5, step 5.4; decisions P5-02, P5-05 and D-47).

The service keeps the real element sets it verifies deliveries against in its database:
those it fetched from CelesTrak or SatChecker, and those an administrator uploaded. Each
is kept with its source, the time it was fetched or uploaded, its epoch and the SHA-256 of
its OMM fields, which is how a verification report names it.

The sets are kept, not served (P5-05). What anyone may see of a set is its name: the
object, the epoch, the source and the SHA-256, with which anyone can fetch the same set
from the same source and repeat a verification.

A set from CelesTrak's SupGP (step 6.2, D-63) is kept as CelesTrak's, with its
``DATA_SOURCE``. Those of an operator's orbit (``StoredSet.operator_orbit``) are named so,
and verification uses one when it is fresh enough for the window (D-66).
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from orbit_watch.catalog import SOURCE_KEY, CatalogError, parse_catalog, record_sha256
from orbit_watch.supgp import is_operator_orbit
from orbit_watch.timeutil import parse_utc

SOURCES = ("celestrak", "satchecker", "uploaded")
SOURCE_NAMES = {
    "celestrak": "CelesTrak",
    "satchecker": "IAU CPS SatChecker",
    "uploaded": "uploaded by an administrator",
}
OPERATOR_ORBIT_NAME = "the operator's orbit via CelesTrak"  # P6-03


class OrbitError(ValueError):
    """An element set the service will not keep. ``code`` maps to an API error."""

    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


@dataclass(frozen=True)
class StoredSet:
    sha256: str
    norad_id: int
    epoch: str
    source: str
    fetched_at: str
    uploaded_by: str | None
    record: dict[str, Any]

    @property
    def data_source(self) -> str | None:
        """CelesTrak's ``DATA_SOURCE`` of a SupGP set, such as ``OneWeb-E``; None for GP."""
        value = str(self.record.get("DATA_SOURCE") or "").strip()
        return value or None

    @property
    def rms_km(self) -> float | None:
        """CelesTrak's fit of a SupGP set to the operator's data, in km; None for GP."""
        try:
            return float(self.record["RMS"]) if str(self.record.get("RMS", "")).strip() else None
        except ValueError:
            return None

    @property
    def operator_orbit(self) -> bool:
        """Whether the set is fitted to its operator's orbit (D-59's rule)."""
        return self.data_source is not None and is_operator_orbit(self.data_source)

    @property
    def epoch_time(self) -> datetime | None:
        """The epoch as a time in UTC, or None if it cannot be read."""
        try:
            return parse_utc(self.epoch if self.epoch.endswith("Z") else self.epoch + "Z")
        except ValueError:
            return None

    def public(self) -> dict[str, Any]:
        """What anyone may see of the set: its name, never its elements."""
        view = {
            "norad_id": self.norad_id,
            "object_name": str(self.record.get("OBJECT_NAME") or ""),
            "epoch": self.epoch,
            "element_set_sha256": self.sha256,
            "source": self.source,
            "source_name": OPERATOR_ORBIT_NAME
            if self.operator_orbit and self.source == "celestrak"
            else SOURCE_NAMES[self.source],
            "fetched_at": self.fetched_at,
        }
        if self.data_source is not None:
            view["data_source"] = self.data_source
        return view

    def row(self) -> tuple[Any, ...]:
        return (
            self.sha256,
            self.norad_id,
            self.epoch,
            self.source,
            self.fetched_at,
            self.uploaded_by,
            json.dumps(self.record, sort_keys=True),
        )

    @classmethod
    def from_row(cls, row: dict[str, Any]) -> StoredSet:
        return cls(
            sha256=row["sha256"],
            norad_id=int(row["norad_id"]),
            epoch=row["epoch"],
            source=row["source"],
            fetched_at=row["fetched_at"],
            uploaded_by=row["uploaded_by"],
            record=json.loads(row["record_json"]),
        )


def keep(
    record: dict[str, Any], source: str, fetched_at: str, uploaded_by: str | None = None
) -> StoredSet:
    """An element set as the service keeps it. Its ``source`` field says where it came
    from, beside what its fetcher recorded; the SHA-256 is of the OMM fields only, so it is
    the same as the source's."""
    if source not in SOURCES:
        raise ValueError(f"source must be one of {', '.join(SOURCES)}")
    found = record.get(SOURCE_KEY)
    provenance = dict(found) if isinstance(found, dict) else {}
    provenance.setdefault("service", SOURCE_NAMES[source])
    provenance["kept_from"] = source
    provenance["fetched_at"] = fetched_at
    kept = {**record, SOURCE_KEY: provenance}
    return StoredSet(
        sha256=record_sha256(kept),
        norad_id=int(kept["NORAD_CAT_ID"]),
        epoch=str(kept["EPOCH"]),
        source=source,
        fetched_at=fetched_at,
        uploaded_by=uploaded_by,
        record=kept,
    )


def read_upload(data: bytes) -> list[dict[str, Any]]:
    """The element sets of an uploaded file: an ``orbit-watch/gp-catalog`` document, or
    CelesTrak's OMM JSON or CSV. A SIMULATED catalogue is refused: an upload is real."""
    try:
        catalog = parse_catalog(data)
    except (CatalogError, ValueError, UnicodeDecodeError) as error:
        raise OrbitError("invalid_element_sets", f"cannot read the element sets: {error}") from None
    if catalog.simulated:
        raise OrbitError(
            "simulated_element_sets",
            "this catalogue is SIMULATED; only real element sets are uploaded",
        )
    return [record for norad in sorted(catalog.sets) for record in catalog.sets[norad]]

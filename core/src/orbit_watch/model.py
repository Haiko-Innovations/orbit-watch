"""In-memory model of observation sets.

The JSON document (schemas/observation-set-1.0.schema.json) is the source of
truth; these classes are a convenience for converters, the simulator and the
verification engine.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from orbit_watch.timeutil import format_utc, parse_utc

FORMAT_ID = "orbit-watch/observation-set"
FORMAT_VERSION = "1.0"

ANGLE_DECIMALS = 8  # 1e-8 degrees is about 0.04 milliarcseconds


@dataclass(frozen=True)
class Station:
    id: str
    latitude_deg: float
    longitude_deg: float
    altitude_m: float
    name: str | None = None
    iod_station_number: int | None = None

    def to_document(self) -> dict[str, Any]:
        doc: dict[str, Any] = {
            "id": self.id,
            "latitude_deg": self.latitude_deg,
            "longitude_deg": self.longitude_deg,
            "altitude_m": self.altitude_m,
        }
        if self.name is not None:
            doc["name"] = self.name
        if self.iod_station_number is not None:
            doc["iod_station_number"] = self.iod_station_number
        return doc

    @classmethod
    def from_document(cls, doc: dict[str, Any]) -> Station:
        return cls(
            id=doc["id"],
            latitude_deg=float(doc["latitude_deg"]),
            longitude_deg=float(doc["longitude_deg"]),
            altitude_m=float(doc["altitude_m"]),
            name=doc.get("name"),
            iod_station_number=doc.get("iod_station_number"),
        )


@dataclass(frozen=True)
class Target:
    norad_id: int
    cospar_id: str | None = None
    name: str | None = None

    def to_document(self) -> dict[str, Any]:
        doc: dict[str, Any] = {"norad_id": self.norad_id}
        if self.cospar_id is not None:
            doc["cospar_id"] = self.cospar_id
        if self.name is not None:
            doc["name"] = self.name
        return doc

    @classmethod
    def from_document(cls, doc: dict[str, Any]) -> Target:
        return cls(
            norad_id=int(doc["norad_id"]), cospar_id=doc.get("cospar_id"), name=doc.get("name")
        )


@dataclass(frozen=True)
class Observation:
    time: datetime
    time_uncertainty_s: float
    angle_type: str  # "radec" or "azel"
    angle_uncertainty_arcsec: float
    frame: str | None = None  # "ICRF" or "of-date" for radec
    ra_deg: float | None = None
    dec_deg: float | None = None
    az_deg: float | None = None
    el_deg: float | None = None
    magnitude: float | None = None

    @property
    def angle_1_deg(self) -> float:
        value = self.ra_deg if self.angle_type == "radec" else self.az_deg
        assert value is not None
        return value

    @property
    def angle_2_deg(self) -> float:
        value = self.dec_deg if self.angle_type == "radec" else self.el_deg
        assert value is not None
        return value

    def to_document(self) -> dict[str, Any]:
        doc: dict[str, Any] = {
            "time": format_utc(self.time),
            "time_uncertainty_s": self.time_uncertainty_s,
            "angle_type": self.angle_type,
        }
        if self.angle_type == "radec":
            doc["frame"] = self.frame
            doc["ra_deg"] = round(self.ra_deg % 360.0, ANGLE_DECIMALS) % 360.0
            doc["dec_deg"] = round(self.dec_deg, ANGLE_DECIMALS)
        else:
            doc["az_deg"] = round(self.az_deg % 360.0, ANGLE_DECIMALS) % 360.0
            doc["el_deg"] = round(self.el_deg, ANGLE_DECIMALS)
        doc["angle_uncertainty_arcsec"] = self.angle_uncertainty_arcsec
        if self.magnitude is not None:
            doc["magnitude"] = self.magnitude
        return doc

    @classmethod
    def from_document(cls, doc: dict[str, Any]) -> Observation:
        return cls(
            time=parse_utc(doc["time"]),
            time_uncertainty_s=float(doc["time_uncertainty_s"]),
            angle_type=doc["angle_type"],
            angle_uncertainty_arcsec=float(doc["angle_uncertainty_arcsec"]),
            frame=doc.get("frame"),
            ra_deg=_opt_float(doc.get("ra_deg")),
            dec_deg=_opt_float(doc.get("dec_deg")),
            az_deg=_opt_float(doc.get("az_deg")),
            el_deg=_opt_float(doc.get("el_deg")),
            magnitude=_opt_float(doc.get("magnitude")),
        )


@dataclass
class ObservationSet:
    station: Station
    target: Target
    observations: list[Observation]
    simulated: bool
    source: dict[str, Any] = field(default_factory=dict)

    def to_document(self) -> dict[str, Any]:
        doc: dict[str, Any] = {
            "format": FORMAT_ID,
            "format_version": FORMAT_VERSION,
            "simulated": self.simulated,
            "station": self.station.to_document(),
            "target": self.target.to_document(),
            "observations": [o.to_document() for o in self.observations],
        }
        if self.source:
            doc["source"] = dict(self.source)
        return doc

    @classmethod
    def from_document(cls, doc: dict[str, Any]) -> ObservationSet:
        """Build from an already validated document."""
        return cls(
            station=Station.from_document(doc["station"]),
            target=Target.from_document(doc["target"]),
            observations=[Observation.from_document(o) for o in doc["observations"]],
            simulated=bool(doc["simulated"]),
            source=dict(doc.get("source", {})),
        )


def _opt_float(value: Any) -> float | None:
    return None if value is None else float(value)

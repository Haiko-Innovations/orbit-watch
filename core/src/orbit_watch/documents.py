"""Requests, delivery manifests and target policies (allow-lists)."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from orbit_watch.formats.owjson import FormatError
from orbit_watch.schema import validate
from orbit_watch.timeutil import parse_utc


def _load(data: bytes, kind: str) -> dict[str, Any]:
    try:
        document = json.loads(data.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise FormatError(f"{kind}: not valid UTF-8 JSON ({exc})") from None
    problems = validate(document, kind)
    if problems:
        raise FormatError(f"invalid {kind} document", problems)
    return document


@dataclass(frozen=True)
class Request:
    request_id: str
    norad_id: int
    target_name: str | None
    window_start: datetime
    window_end: datetime
    min_observations: int
    max_angle_uncertainty_arcsec: float
    max_time_uncertainty_s: float
    angle_types: tuple[str, ...]
    simulated: bool
    title: str | None

    @classmethod
    def parse(cls, data: bytes) -> Request:
        doc = _load(data, "request")
        start, end = parse_utc(doc["window"]["start"]), parse_utc(doc["window"]["end"])
        if end <= start:
            raise FormatError("invalid request: the window ends before it starts")
        req = doc["requirements"]
        return cls(
            request_id=doc["request_id"],
            norad_id=int(doc["target"]["norad_id"]),
            target_name=doc["target"].get("name"),
            window_start=start,
            window_end=end,
            min_observations=int(req["min_observations"]),
            max_angle_uncertainty_arcsec=float(req["max_angle_uncertainty_arcsec"]),
            max_time_uncertainty_s=float(req["max_time_uncertainty_s"]),
            angle_types=tuple(req.get("angle_types", ["radec", "azel"])),
            simulated=bool(doc["simulated"]),
            title=doc.get("title"),
        )


@dataclass(frozen=True)
class Delivery:
    delivery_id: str
    request_id: str
    file: str
    format: str | None
    sha256: str
    simulated: bool

    @classmethod
    def parse(cls, data: bytes) -> Delivery:
        doc = _load(data, "delivery")
        observations = doc["observations"]
        return cls(
            delivery_id=doc["delivery_id"],
            request_id=doc["request_id"],
            file=observations["file"],
            format=observations.get("format"),
            sha256=observations["sha256"],
            simulated=bool(doc["simulated"]),
        )


@dataclass(frozen=True)
class TargetPolicy:
    allowed: dict[int, str | None]
    simulated: bool
    description: str | None

    @classmethod
    def parse(cls, data: bytes) -> TargetPolicy:
        doc = _load(data, "target-policy")
        return cls(
            allowed={int(a["norad_id"]): a.get("name") for a in doc["allow"]},
            simulated=bool(doc.get("simulated", False)),
            description=doc.get("description"),
        )

    def allows(self, norad_id: int) -> bool:
        return norad_id in self.allowed


def is_delivery_manifest(data: bytes) -> bool:
    try:
        document = json.loads(data.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return False
    return isinstance(document, dict) and document.get("format") == "orbit-watch/delivery"

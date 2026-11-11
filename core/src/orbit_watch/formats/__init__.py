"""Observation formats: Orbit Watch JSON, IOD and a CCSDS TDM subset."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from orbit_watch.formats import iod, owjson, tdm
from orbit_watch.formats.owjson import FormatError
from orbit_watch.formats.sites import Sites
from orbit_watch.model import ObservationSet

FORMATS = ("json", "iod", "tdm")

__all__ = [
    "FORMATS",
    "FormatError",
    "LoadResult",
    "Sites",
    "detect_format",
    "load_observation_sets",
]


@dataclass
class LoadResult:
    format: str
    sets: list[ObservationSet]
    warnings: list[str] = field(default_factory=list)
    skipped: list[str] = field(default_factory=list)


def detect_format(path: str | Path, data: bytes) -> str:
    suffix = Path(path).suffix.lower()
    if suffix == ".json":
        return "json"
    if suffix in (".tdm", ".kvn"):
        return "tdm"
    if suffix == ".iod":
        return "iod"
    head = data[:4096].decode("utf-8", errors="replace").lstrip()
    if head.startswith("{"):
        return "json"
    if "CCSDS_TDM_VERS" in head:
        return "tdm"
    return "iod"


def load_observation_sets(
    path: str | Path,
    *,
    data: bytes | None = None,
    input_format: str | None = None,
    sites: Sites | None = None,
    default_angle_uncertainty_arcsec: float | None = None,
    default_time_uncertainty_s: float | None = None,
) -> LoadResult:
    """Load one file in any supported format as Orbit Watch observation sets."""
    if data is None:
        data = Path(path).read_bytes()
    fmt = input_format or detect_format(path, data)
    sites = sites or Sites.empty()
    if fmt == "json":
        return LoadResult("json", [owjson.read_observation_set(data)])
    text = data.decode("utf-8", errors="strict")
    if fmt == "iod":
        result = iod.read_iod(
            text,
            default_angle_uncertainty_arcsec=default_angle_uncertainty_arcsec,
            default_time_uncertainty_s=default_time_uncertainty_s,
        )
        if not result.records:
            raise FormatError("no IOD observations found", result.skipped)
        stations = {}
        missing = []
        for number in sorted({r.station_number for r in result.records}):
            station = sites.by_iod_number(number)
            if station is None:
                missing.append(f"{number:04d}")
            else:
                stations[number] = station
        if missing:
            raise FormatError(
                "station coordinates missing for IOD station(s) "
                + ", ".join(missing)
                + "; give a sites file with --sites",
            )
        sets = iod.group_records(result, stations)
        return LoadResult("iod", sets, result.warnings, result.skipped)
    if fmt == "tdm":
        try:
            result = tdm.read_tdm(
                text,
                default_angle_uncertainty_arcsec=default_angle_uncertainty_arcsec,
                default_time_uncertainty_s=default_time_uncertainty_s,
            )
        except tdm.TdmError as exc:
            raise FormatError(f"invalid TDM: {exc}") from None
        stations = {}
        for segment in result.segments:
            station = sites.by_id(segment.station_id)
            if station is None:
                raise FormatError(
                    f"station coordinates missing for PARTICIPANT_1 {segment.station_id!r}; "
                    "give a sites file with --sites"
                )
            stations[segment.station_id] = station
        try:
            sets = tdm.segments_to_sets(result, stations)
        except tdm.TdmError as exc:
            raise FormatError(f"invalid TDM: {exc}") from None
        return LoadResult("tdm", sets, result.warnings)
    raise FormatError(f"unknown input format {fmt!r}")

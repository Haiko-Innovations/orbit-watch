"""A limited subset of the CCSDS Tracking Data Message (TDM), KVN syntax.

Reference: CCSDS 503.0-B-2, "Tracking Data Message", Blue Book, June 2020,
including Technical Corrigendum 1 (October 2021).

Orbit Watch TDM profile (what this module reads and writes):

* Header: CCSDS_TDM_VERS (1.0 or 2.0), CREATION_DATE, ORIGINATOR; COMMENT and
  MESSAGE_ID are allowed.
* Each segment: META_START ... META_STOP, then DATA_START ... DATA_STOP.
* Metadata: TIME_SYSTEM must be UTC. PARTICIPANT_1 is the observing station
  (looked up in a sites file). PARTICIPANT_2 is the observed object, written as
  its catalogue number (digits or Alpha-5). ANGLE_TYPE is RADEC or AZEL. For
  RADEC, REFERENCE_FRAME must be EME2000 or ICRF (both treated as ICRF).
  Other metadata keywords are ignored with a warning.
* Data: ANGLE_1 and ANGLE_2 records with identical timetags form one
  observation (degrees). MAG records with the same timetag are kept. Other
  data keywords are ignored with a warning.
* Uncertainties are not part of the TDM data section. This profile carries them
  in metadata comments, which the standard allows for information not covered
  by keywords:

      COMMENT orbit-watch angle_uncertainty_arcsec=5
      COMMENT orbit-watch time_uncertainty_s=0.01
      COMMENT orbit-watch simulated=true

  Command-line defaults can supply missing uncertainties.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta

from orbit_watch.ids import format_alpha5, parse_catalog_number
from orbit_watch.model import Observation, ObservationSet, Station, Target
from orbit_watch.timeutil import format_utc

_TIME_RE = re.compile(
    r"^(\d{4})-(?:(\d{2})-(\d{2})|(\d{3}))T(\d{2}):(\d{2}):(\d{2})(?:\.(\d+))?Z?$"
)
_COMMENT_KV_RE = re.compile(r"^orbit-watch\s+([a-z_]+)\s*=\s*(\S+)\s*$")
_IGNORED_DATA = {"COMMENT"}


class TdmError(ValueError):
    pass


@dataclass
class TdmSegment:
    station_id: str
    target_id: str
    angle_type: str
    frame: str | None
    comments: dict[str, str]
    observations: list[Observation]


@dataclass
class TdmReadResult:
    segments: list[TdmSegment] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    header: dict[str, str] = field(default_factory=dict)


def parse_time(text: str) -> datetime:
    match = _TIME_RE.match(text.strip())
    if not match:
        raise TdmError(f"unsupported time format {text!r}")
    year, month, day, doy, hour, minute, second, frac = match.groups()
    frac = (frac or "0")[:6].ljust(6, "0")
    if doy is not None:
        base = datetime(int(year), 1, 1, tzinfo=UTC) + timedelta(days=int(doy) - 1)
        month, day = base.month, base.day
    return datetime(
        int(year), int(month), int(day), int(hour), int(minute), int(second), int(frac), tzinfo=UTC
    )


def _split_kv(line: str, number: int) -> tuple[str, str]:
    if "=" not in line:
        raise TdmError(f"line {number}: expected 'KEYWORD = value'")
    key, value = line.split("=", 1)
    key, value = key.strip(), value.strip()
    if not key or key != key.upper() or " " in key:
        raise TdmError(f"line {number}: keyword {key!r} must be uppercase without blanks")
    if not value:
        raise TdmError(f"line {number}: keyword {key} has an empty value")
    return key, value


def read_tdm(
    text: str,
    *,
    default_angle_uncertainty_arcsec: float | None = None,
    default_time_uncertainty_s: float | None = None,
) -> TdmReadResult:
    result = TdmReadResult()
    state = "header"
    meta: dict[str, str] = {}
    meta_comments: dict[str, str] = {}
    data: dict[datetime, dict[str, float]] = {}
    data_order: list[datetime] = []
    header_comments: dict[str, str] = {}

    def finish_segment() -> None:
        comments = {**header_comments, **meta_comments}
        result.segments.append(
            _build_segment(
                meta,
                comments,
                data,
                data_order,
                result.warnings,
                default_angle_uncertainty_arcsec,
                default_time_uncertainty_s,
            )
        )

    for number, raw in enumerate(text.splitlines(), start=1):
        line = raw.replace("\u00a0", " ").strip()
        if not line:
            continue
        if line.startswith("COMMENT"):
            body = line[len("COMMENT") :].strip()
            match = _COMMENT_KV_RE.match(body)
            if match:
                target = header_comments if state == "header" else meta_comments
                target[match.group(1)] = match.group(2)
            continue
        if line == "META_START":
            if state not in ("header", "between"):
                raise TdmError(f"line {number}: META_START in the wrong place")
            state, meta, meta_comments, data, data_order = "meta", {}, {}, {}, []
            continue
        if line == "META_STOP":
            if state != "meta":
                raise TdmError(f"line {number}: META_STOP without META_START")
            state = "after_meta"
            continue
        if line == "DATA_START":
            if state != "after_meta":
                raise TdmError(f"line {number}: DATA_START must follow META_STOP")
            state = "data"
            continue
        if line == "DATA_STOP":
            if state != "data":
                raise TdmError(f"line {number}: DATA_STOP without DATA_START")
            finish_segment()
            state = "between"
            continue
        key, value = _split_kv(line, number)
        if state == "header":
            result.header[key] = value
        elif state == "meta":
            meta[key] = value
        elif state == "data":
            parts = value.split()
            if len(parts) != 2:
                raise TdmError(f"line {number}: expected 'timetag measurement'")
            moment = parse_time(parts[0])
            if key not in ("ANGLE_1", "ANGLE_2", "MAG"):
                if key not in _IGNORED_DATA:
                    result.warnings.append(f"line {number}: data keyword {key} ignored")
                continue
            if moment not in data:
                data[moment] = {}
                data_order.append(moment)
            if key in data[moment]:
                raise TdmError(f"line {number}: duplicate {key} at {parts[0]}")
            data[moment][key] = float(parts[1])
        else:
            raise TdmError(f"line {number}: unexpected keyword {key} outside a section")

    if state not in ("between",):
        raise TdmError("message ends inside a segment or has no segments")
    version = result.header.get("CCSDS_TDM_VERS")
    if version not in ("1.0", "2.0"):
        raise TdmError(f"CCSDS_TDM_VERS {version!r} is not 1.0 or 2.0")
    for required in ("CREATION_DATE", "ORIGINATOR"):
        if required not in result.header:
            raise TdmError(f"header keyword {required} is missing")
    return result


def _build_segment(meta, comments, data, data_order, warnings, default_angle_unc, default_time_unc):
    known = {
        "TIME_SYSTEM",
        "PARTICIPANT_1",
        "PARTICIPANT_2",
        "ANGLE_TYPE",
        "REFERENCE_FRAME",
        "START_TIME",
        "STOP_TIME",
        "MODE",
        "PATH",
        "TRACK_ID",
        "DATA_TYPES",
        "DATA_QUALITY",
    }
    for key in sorted(meta):
        if key.startswith("CORRECTION_"):
            raise TdmError(f"metadata keyword {key} is not supported (corrections must be applied)")
        if key not in known:
            warnings.append(f"metadata keyword {key} ignored")
    if meta.get("TIME_SYSTEM") != "UTC":
        raise TdmError(f"TIME_SYSTEM must be UTC, got {meta.get('TIME_SYSTEM')!r}")
    for required in ("PARTICIPANT_1", "PARTICIPANT_2", "ANGLE_TYPE"):
        if required not in meta:
            raise TdmError(f"metadata keyword {required} is missing")
    angle_type = meta["ANGLE_TYPE"]
    if angle_type == "RADEC":
        frame_keyword = meta.get("REFERENCE_FRAME")
        if frame_keyword not in ("EME2000", "ICRF"):
            raise TdmError(f"REFERENCE_FRAME {frame_keyword!r} is not supported (EME2000 or ICRF)")
        kind, frame = "radec", "ICRF"
    elif angle_type == "AZEL":
        kind, frame = "azel", None
    else:
        raise TdmError(f"ANGLE_TYPE {angle_type!r} is not supported (RADEC or AZEL)")

    angle_unc = _float_option(
        comments.get("angle_uncertainty_arcsec"), default_angle_unc, "angle_uncertainty_arcsec"
    )
    time_unc = _float_option(
        comments.get("time_uncertainty_s"), default_time_unc, "time_uncertainty_s"
    )
    observations = []
    for moment in data_order:
        values = data[moment]
        if "ANGLE_1" not in values or "ANGLE_2" not in values:
            raise TdmError(f"ANGLE_1 and ANGLE_2 must share the timetag {format_utc(moment)}")
        a1 = values["ANGLE_1"] % 360.0
        a2 = values["ANGLE_2"]
        if not -90.0 <= a2 <= 90.0:
            raise TdmError(f"ANGLE_2 {a2} out of range at {format_utc(moment)}")
        common = dict(
            time=moment,
            time_uncertainty_s=time_unc,
            angle_uncertainty_arcsec=angle_unc,
            magnitude=values.get("MAG"),
        )
        if kind == "radec":
            observations.append(
                Observation(angle_type="radec", frame=frame, ra_deg=a1, dec_deg=a2, **common)
            )
        else:
            observations.append(Observation(angle_type="azel", az_deg=a1, el_deg=a2, **common))
    return TdmSegment(
        station_id=meta["PARTICIPANT_1"],
        target_id=meta["PARTICIPANT_2"],
        angle_type=kind,
        frame=frame,
        comments=comments,
        observations=observations,
    )


def _float_option(comment_value, default, name):
    if comment_value is not None:
        try:
            value = float(comment_value)
        except ValueError:
            raise TdmError(f"COMMENT orbit-watch {name}={comment_value} is not a number") from None
    elif default is not None:
        value = float(default)
    else:
        raise TdmError(
            f"{name} is not given: add 'COMMENT orbit-watch {name}=...' to the metadata "
            "or pass a default on the command line"
        )
    if not value > 0:
        raise TdmError(f"{name} must be positive")
    return value


def segments_to_sets(result: TdmReadResult, stations: dict[str, Station]) -> list[ObservationSet]:
    """One observation set per (station, object); segments of the same pair are merged."""
    groups: dict[tuple[str, int], ObservationSet] = {}
    for segment in result.segments:
        station = stations.get(segment.station_id)
        if station is None:
            raise KeyError(segment.station_id)
        try:
            norad_id = parse_catalog_number(segment.target_id)
        except ValueError:
            raise TdmError(
                f"PARTICIPANT_2 {segment.target_id!r} is not a catalogue number (digits or Alpha-5)"
            ) from None
        simulated = segment.comments.get("simulated", "false").lower() == "true"
        key = (segment.station_id, norad_id)
        if key not in groups:
            groups[key] = ObservationSet(
                station=station,
                target=Target(norad_id=norad_id),
                observations=[],
                simulated=simulated,
                source={"software": "orbit-watch convert", "converted_from": "ccsds-tdm"},
            )
        group = groups[key]
        group.simulated = group.simulated or simulated
        group.observations.extend(segment.observations)
    for group in groups.values():
        group.observations.sort(key=lambda o: o.time)
    return list(groups.values())


def _uniform(values: list[float], name: str) -> float:
    unique = sorted(set(values))
    if len(unique) != 1:
        # The profile carries one value per segment; keep the most conservative one.
        return unique[-1]
    return unique[0]


def write_tdm(
    observation_sets: list[ObservationSet],
    *,
    creation_date: datetime,
    originator: str = "ORBIT-WATCH",
) -> str:
    """Write observation sets as a TDM 2.0 message, one segment per set and angle type."""
    lines = ["CCSDS_TDM_VERS = 2.0"]
    if any(s.simulated for s in observation_sets):
        lines.append("COMMENT SIMULATED DATA generated by the Orbit Watch simulator")
    lines += [f"CREATION_DATE = {format_utc(creation_date)}", f"ORIGINATOR = {originator}", ""]
    for observation_set in observation_sets:
        by_kind: dict[tuple[str, str | None], list[Observation]] = {}
        for observation in observation_set.observations:
            by_kind.setdefault((observation.angle_type, observation.frame), []).append(observation)
        for (kind, frame), observations in by_kind.items():
            if kind == "radec" and frame != "ICRF":
                raise ValueError("TDM output supports RA/Dec only in ICRF (EME2000)")
            angle_unc = _uniform([o.angle_uncertainty_arcsec for o in observations], "angle")
            time_unc = _uniform([o.time_uncertainty_s for o in observations], "time")
            lines += [
                "META_START",
                f"COMMENT orbit-watch angle_uncertainty_arcsec={angle_unc:g}",
                f"COMMENT orbit-watch time_uncertainty_s={time_unc:g}",
                f"COMMENT orbit-watch simulated={'true' if observation_set.simulated else 'false'}",
                "TIME_SYSTEM = UTC",
                f"START_TIME = {format_utc(min(o.time for o in observations))}",
                f"STOP_TIME = {format_utc(max(o.time for o in observations))}",
                f"PARTICIPANT_1 = {observation_set.station.id}",
                f"PARTICIPANT_2 = {_target_label(observation_set.target.norad_id)}",
                "MODE = SEQUENTIAL",
                "PATH = 2,1",
                f"ANGLE_TYPE = {'RADEC' if kind == 'radec' else 'AZEL'}",
            ]
            if kind == "radec":
                lines.append("REFERENCE_FRAME = EME2000")
            lines += ["META_STOP", "DATA_START"]
            for observation in observations:
                stamp = format_utc(observation.time)
                lines.append(f"ANGLE_1 = {stamp} {observation.angle_1_deg:.8f}")
                lines.append(f"ANGLE_2 = {stamp} {observation.angle_2_deg:.8f}")
                if observation.magnitude is not None:
                    lines.append(f"MAG = {stamp} {observation.magnitude:.2f}")
            lines += ["DATA_STOP", ""]
    return "\n".join(lines)


def _target_label(norad_id: int) -> str:
    return format_alpha5(norad_id) if norad_id <= 339_999 else str(norad_id)

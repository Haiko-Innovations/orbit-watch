"""The IOD (Interactive Orbit Determination) 80-column observation format.

Reference: "Interactive Orbit Determination (IOD) Version 0" by George D. Lewis,
as reproduced at http://www.satobs.org/position/IODformat.html (read 2026-11-11).

Column layout (1-based, inclusive):

  1-15  object number (5 chars, digits or Alpha-5) and international designator
 17-20  station number
    22  station status: sky E/G/F/P/B/T, or C (clouded out) / O (observer unavailable)
 24-31  UTC date YYYYMMDD
 32-40  UTC time HHMMSSsss (trailing digits may be blank)
 42-43  time uncertainty MX: M * 10**(X - 8) seconds
    45  angle format code 1-7
    46  epoch code: 0 or blank = of date, 1=1855, 2=1875, 3=1900, 4=1950, 5=2000, 6=2050
 48-54  RA or azimuth
    55  sign of declination or elevation
 56-61  declination or elevation
 63-64  position uncertainty MX: M * 10**(X - 8) in arcseconds (formats 1, 4),
        arcminutes (2, 5) or degrees (3, 6, 7)
    66  optical behaviour code
 67-70  visual magnitude (sign, then three digits with an implied decimal point)

Angle formats (columns 48-61):
  1: RA/Dec HHMMSSs+DDMMSS   2: RA/Dec HHMMmmm+DDMMmm   3: RA/Dec HHMMmmm+DDdddd
  4: Az/El DDDMMSS+DDMMSS    5: Az/El DDDMMmm+DDMMmm    6: Az/El DDDdddd+DDdddd
  7: RA/Dec HHMMSSs+DDdddd

Phase 0 supports epoch codes 0 (of date) and 5 (2000, treated as ICRF). Other
equinoxes are rejected with an explanation; adding them is a good first issue.
Uncertainties are interpreted as one-sigma values.

Real-world files are messy, so the reader is lenient where it is safe:
non-breaking spaces become spaces, short lines are padded, lines whose
columns are shifted are re-aligned on the "station status date" anchor (with
a warning), and lines that are not observations are skipped with a reason.
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass, field
from datetime import UTC, datetime

from orbit_watch.ids import format_alpha5, parse_catalog_number
from orbit_watch.model import Observation, ObservationSet, Station, Target

SIMULATED_MARKER = "# orbit-watch: simulated=true"

SKY_CODES = set("EGFPBT")
UNAVAILABLE_CODES = set("CO")
SUPPORTED_EPOCHS = {"0": "of-date", " ": "of-date", "5": "ICRF"}
EPOCH_NAMES = {"1": "1855", "2": "1875", "3": "1900", "4": "1950", "6": "2050"}
RADEC_FORMATS = {1, 2, 3, 7}
AZEL_FORMATS = {4, 5, 6}
# Unit of the position uncertainty, in arcseconds, per angle format.
UNCERTAINTY_UNIT_ARCSEC = {1: 1.0, 4: 1.0, 2: 60.0, 5: 60.0, 3: 3600.0, 6: 3600.0, 7: 3600.0}

_ANCHOR_RE = re.compile(r"(\d{4}) ([A-Z]) (\d{8})")


@dataclass(frozen=True)
class IodRecord:
    line_number: int
    norad_id: int
    designator: str
    station_number: int
    status: str
    observation: Observation


@dataclass
class IodReadResult:
    records: list[IodRecord] = field(default_factory=list)
    skipped: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    simulated: bool = False


class IodLineError(ValueError):
    pass


def decode_mx(field_text: str) -> float | None:
    """Decode an MX uncertainty field: M * 10**(X - 8). Blank means not given."""
    text = field_text.strip()
    if not text:
        return None
    if len(text) != 2 or not text.isdigit():
        raise IodLineError(f"uncertainty field {field_text!r} is not two digits (MX)")
    mantissa, exponent = int(text[0]), int(text[1])
    return mantissa * 10.0 ** (exponent - 8)


def encode_mx(value: float) -> str:
    """Encode a positive value as MX, rounding up so the uncertainty is never understated."""
    if not value > 0:
        raise ValueError("uncertainty must be positive")
    exponent = math.floor(math.log10(value)) + 8
    scale = 10.0 ** (exponent - 8)
    mantissa = math.ceil(round(value / scale, 9))
    if mantissa >= 10:
        mantissa, exponent = 1, exponent + 1
    if exponent < 0:
        mantissa, exponent = 1, 0
    if exponent > 9:
        raise ValueError(f"uncertainty {value} is too large for the IOD MX field (max 90)")
    return f"{mantissa}{exponent}"


def _digits(text: str, what: str) -> str:
    """Treat blanks as non-significant zeros and require digits otherwise."""
    filled = text.replace(" ", "0")
    if not filled.isdigit():
        raise IodLineError(f"{what} {text!r} contains non-digits")
    return filled


def _parse_time(date_text: str, time_text: str) -> datetime:
    date_digits = _digits(date_text, "date")
    time_digits = _digits(time_text.ljust(9), "time")
    year, month, day = int(date_digits[0:4]), int(date_digits[4:6]), int(date_digits[6:8])
    hour, minute, second = int(time_digits[0:2]), int(time_digits[2:4]), int(time_digits[4:6])
    millis = int(time_digits[6:9])
    try:
        return datetime(year, month, day, hour, minute, second, millis * 1000, tzinfo=UTC)
    except ValueError as exc:
        raise IodLineError(f"invalid date/time {date_text}{time_text}: {exc}") from None


def _parse_angles(fmt: int, a1: str, sign: str, a2: str) -> tuple[float, float]:
    """Return (angle_1_deg, angle_2_deg) for the given IOD angle format."""
    d1 = _digits(a1, "angle 1")
    d2 = _digits(a2, "angle 2")
    if sign not in "+- ":
        raise IodLineError(f"sign {sign!r} is not + or -")
    negative = sign == "-"
    if fmt in (1, 7):  # HHMMSSs
        angle_1 = 15.0 * (
            int(d1[0:2]) + int(d1[2:4]) / 60 + (int(d1[4:6]) + int(d1[6]) / 10) / 3600
        )
    elif fmt in (2, 3):  # HHMMmmm
        angle_1 = 15.0 * (int(d1[0:2]) + (int(d1[2:4]) + int(d1[4:7]) / 1000) / 60)
    elif fmt == 4:  # DDDMMSS
        angle_1 = int(d1[0:3]) + int(d1[3:5]) / 60 + int(d1[5:7]) / 3600
    elif fmt == 5:  # DDDMMmm
        angle_1 = int(d1[0:3]) + (int(d1[3:5]) + int(d1[5:7]) / 100) / 60
    elif fmt == 6:  # DDDdddd
        angle_1 = int(d1[0:3]) + int(d1[3:7]) / 10000
    else:
        raise IodLineError(f"unknown angle format {fmt}")
    if fmt in (1, 4):  # DDMMSS
        angle_2 = int(d2[0:2]) + int(d2[2:4]) / 60 + int(d2[4:6]) / 3600
    elif fmt in (2, 5):  # DDMMmm
        angle_2 = int(d2[0:2]) + (int(d2[2:4]) + int(d2[4:6]) / 100) / 60
    else:  # 3, 6, 7: DDdddd
        angle_2 = int(d2[0:2]) + int(d2[2:6]) / 10000
    if negative:
        angle_2 = -angle_2
    return angle_1, angle_2


def _normalise(raw: str) -> str:
    return raw.replace("\u00a0", " ").replace("\t", " ").rstrip("\r\n").rstrip()


def _align(line: str) -> tuple[str, int]:
    """Re-align a line whose station field is not at columns 17-20."""
    if len(line) >= 31 and _ANCHOR_RE.match(line, 16):
        return line, 0
    match = _ANCHOR_RE.search(line)
    if not match or match.start() < 6:
        raise IodLineError("cannot find the 'station status date' fields")
    start = match.start()
    shift = 16 - start
    if shift > 0:
        # The designator field is too short; pad it before the station number.
        line = line[:start].ljust(16) + line[start:]
    else:
        if line[16:start].strip():
            raise IodLineError("object/designator field is longer than columns 1-15")
        line = line[:16] + line[start:]
    return line, shift


def parse_line(
    raw: str,
    line_number: int = 0,
    *,
    default_angle_uncertainty_arcsec: float | None = None,
    default_time_uncertainty_s: float | None = None,
) -> tuple[IodRecord | None, str | None, int]:
    """Parse one line.

    Returns (record, skip_reason, column_shift). A record is None when the
    line is not a positional observation; skip_reason then says why.
    """
    text = _normalise(raw)
    if not text.strip() or text.lstrip().startswith("#"):
        return None, None, 0
    status_only = _ANCHOR_RE.search(text) or re.search(r"(\d{4}) ([CO])\b", text)
    if status_only and status_only.group(2) in UNAVAILABLE_CODES:
        return (
            None,
            f"line {line_number}: station status {status_only.group(2)!r} (no observation)",
            0,
        )
    line, shift = _align(text)
    line = line.ljust(80)

    status = line[21]
    station_number = int(line[16:20])
    object_field = line[0:5]
    designator = line[6:15].strip()
    if status in UNAVAILABLE_CODES:
        return None, f"line {line_number}: station status {status!r} (no observation)", shift
    if status not in SKY_CODES:
        raise IodLineError(f"station status {status!r} is not one of E G F P B T C O")
    format_code = line[44]
    if format_code == " ":
        return None, f"line {line_number}: no position reported (angle format blank)", shift
    if not format_code.isdigit() or int(format_code) not in RADEC_FORMATS | AZEL_FORMATS:
        raise IodLineError(f"angle format {format_code!r} is not 1-7")
    fmt = int(format_code)
    epoch_code = line[45]
    norad_id = parse_catalog_number(object_field)
    moment = _parse_time(line[23:31], line[31:40])

    time_uncertainty = decode_mx(line[41:43])
    position_uncertainty = decode_mx(line[62:64])
    angle_1, angle_2 = _parse_angles(fmt, line[47:54], line[54], line[55:61])
    if position_uncertainty is not None:
        angle_uncertainty_arcsec = position_uncertainty * UNCERTAINTY_UNIT_ARCSEC[fmt]
    elif default_angle_uncertainty_arcsec is not None:
        angle_uncertainty_arcsec = default_angle_uncertainty_arcsec
    else:
        raise IodLineError("position uncertainty (columns 63-64) is blank; give a default")
    if time_uncertainty is None:
        if default_time_uncertainty_s is None:
            raise IodLineError("time uncertainty (columns 42-43) is blank; give a default")
        time_uncertainty = default_time_uncertainty_s

    magnitude = None
    mag_text = line[66:70]
    if mag_text.strip():
        mag_sign, mag_digits = mag_text[0], _digits(mag_text[1:4], "magnitude")
        magnitude = int(mag_digits) / 10.0
        if mag_sign == "-":
            magnitude = -magnitude

    if fmt in RADEC_FORMATS:
        if epoch_code not in SUPPORTED_EPOCHS:
            name = EPOCH_NAMES.get(epoch_code, repr(epoch_code))
            raise IodLineError(
                f"equinox code {epoch_code!r} ({name}) is not supported yet; "
                "phase 0 supports 0 (of date) and 5 (2000)"
            )
        if not 0 <= angle_1 < 360 or not -90 <= angle_2 <= 90:
            raise IodLineError("right ascension or declination out of range")
        observation = Observation(
            time=moment,
            time_uncertainty_s=_round_unc(time_uncertainty),
            angle_type="radec",
            frame=SUPPORTED_EPOCHS[epoch_code],
            ra_deg=angle_1,
            dec_deg=angle_2,
            angle_uncertainty_arcsec=_round_unc(angle_uncertainty_arcsec),
            magnitude=magnitude,
        )
    else:
        if not 0 <= angle_1 < 360 or not -90 <= angle_2 <= 90:
            raise IodLineError("azimuth or elevation out of range")
        observation = Observation(
            time=moment,
            time_uncertainty_s=_round_unc(time_uncertainty),
            angle_type="azel",
            az_deg=angle_1,
            el_deg=angle_2,
            angle_uncertainty_arcsec=_round_unc(angle_uncertainty_arcsec),
            magnitude=magnitude,
        )
    record = IodRecord(
        line_number=line_number,
        norad_id=norad_id,
        designator=designator,
        station_number=station_number,
        status=status,
        observation=observation,
    )
    return record, None, shift


def _round_unc(value: float) -> float:
    return float(f"{value:.10g}")


def read_iod(
    text: str,
    *,
    strict: bool = False,
    default_angle_uncertainty_arcsec: float | None = None,
    default_time_uncertainty_s: float | None = None,
) -> IodReadResult:
    """Read IOD text. Invalid lines raise in strict mode and are reported otherwise."""
    result = IodReadResult()
    for number, raw in enumerate(text.splitlines(), start=1):
        if raw.strip().lower() == SIMULATED_MARKER:
            result.simulated = True
            continue
        try:
            record, reason, shift = parse_line(
                raw,
                number,
                default_angle_uncertainty_arcsec=default_angle_uncertainty_arcsec,
                default_time_uncertainty_s=default_time_uncertainty_s,
            )
        except (IodLineError, ValueError) as exc:
            if strict:
                raise IodLineError(f"line {number}: {exc}") from None
            result.skipped.append(f"line {number}: {exc}")
            continue
        if reason:
            result.skipped.append(reason)
        if shift:
            result.warnings.append(
                f"line {number}: columns re-aligned by {shift:+d} "
                "(station number not in columns 17-20)"
            )
        if record:
            result.records.append(record)
    return result


def group_records(result: IodReadResult, stations: dict[int, Station]) -> list[ObservationSet]:
    """Group IOD records into one observation set per (station, object), in file order."""
    groups: dict[tuple[int, int], list[IodRecord]] = {}
    for record in result.records:
        groups.setdefault((record.station_number, record.norad_id), []).append(record)
    sets = []
    for (station_number, norad_id), records in groups.items():
        station = stations.get(station_number)
        if station is None:
            raise KeyError(station_number)
        designators = sorted({r.designator for r in records if r.designator})
        source = {"software": "orbit-watch convert", "converted_from": "iod"}
        if designators:
            source["original_designator"] = designators[0][:20]
        sets.append(
            ObservationSet(
                station=station,
                target=Target(norad_id=norad_id),
                observations=sorted((r.observation for r in records), key=lambda o: o.time),
                simulated=result.simulated,
                source=source,
            )
        )
    return sets


def _format_angles(observation: Observation, fmt: int) -> tuple[str, str, str]:
    a1, a2 = observation.angle_1_deg, observation.angle_2_deg
    sign = "-" if a2 < 0 else "+"
    a2 = abs(a2)
    if fmt == 2:
        total = round(a1 / 15.0 * 60_000)  # thousandths of a minute of time
        total %= 24 * 60_000
        hours, rest = divmod(total, 60_000)
        f1 = f"{hours:02d}{rest // 1000:02d}{rest % 1000:03d}"
        total2 = round(a2 * 6000)  # hundredths of an arcminute
        degrees, rest2 = divmod(total2, 6000)
        f2 = f"{degrees:02d}{rest2 // 100:02d}{rest2 % 100:02d}"
    elif fmt == 5:
        total = round(a1 * 6000) % (360 * 6000)
        degrees, rest = divmod(total, 6000)
        f1 = f"{degrees:03d}{rest // 100:02d}{rest % 100:02d}"
        total2 = round(a2 * 6000)
        degrees2, rest2 = divmod(total2, 6000)
        f2 = f"{degrees2:02d}{rest2 // 100:02d}{rest2 % 100:02d}"
    else:
        raise ValueError(f"writing angle format {fmt} is not supported (use 2 or 5)")
    return f1, sign, f2


def format_line(observation_set: ObservationSet, observation: Observation) -> str:
    """Write one observation as an IOD line (angle format 2 for RA/Dec, 5 for Az/El)."""
    station = observation_set.station
    if station.iod_station_number is None:
        raise ValueError(f"station {station.id} has no iod_station_number")
    if observation.angle_type == "radec":
        if observation.frame != "ICRF":
            raise ValueError("writing IOD supports only ICRF (epoch code 5) right ascension")
        fmt, epoch = 2, "5"
    else:
        fmt, epoch = 5, " "
    unit = UNCERTAINTY_UNIT_ARCSEC[fmt]
    f1, sign, f2 = _format_angles(observation, fmt)
    moment = observation.time.astimezone(UTC)
    millis = round(moment.microsecond / 1000)
    if millis == 1000:
        raise ValueError("time rounds to a full second; write times with millisecond precision")
    designator = (observation_set.source.get("original_designator") or "").ljust(9)[:9]
    columns = [
        format_alpha5(observation_set.target.norad_id),
        " ",
        designator,
        " ",
        f"{station.iod_station_number:04d}",
        " ",
        "G",
        " ",
        moment.strftime("%Y%m%d%H%M%S") + f"{millis:03d}",
        " ",
        encode_mx(observation.time_uncertainty_s),
        " ",
        f"{fmt}{epoch}",
        " ",
        f1,
        sign,
        f2,
        " ",
        encode_mx(observation.angle_uncertainty_arcsec / unit),
    ]
    return "".join(columns)


def write_iod(observation_sets: list[ObservationSet]) -> str:
    lines = []
    if any(s.simulated for s in observation_sets):
        lines.append(SIMULATED_MARKER)
        lines.append("# SIMULATED DATA: these lines were generated by the Orbit Watch simulator.")
    for observation_set in observation_sets:
        for observation in observation_set.observations:
            lines.append(format_line(observation_set, observation))
    return "\n".join(lines) + "\n"

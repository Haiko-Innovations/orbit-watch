"""UTC time parsing and canonical formatting.

All times in Orbit Watch documents are UTC, written as ISO 8601 with a "Z"
suffix and at most microsecond precision. Leap seconds (23:59:60) are not
supported in phase 0.
"""

from __future__ import annotations

import re
from datetime import UTC, datetime, timedelta

_ISO_RE = re.compile(r"^(\d{4})-(\d{2})-(\d{2})T(\d{2}):(\d{2}):(\d{2})(?:\.(\d{1,6}))?Z$")


def parse_utc(text: str) -> datetime:
    """Parse "YYYY-MM-DDThh:mm:ss[.ffffff]Z" into an aware UTC datetime."""
    match = _ISO_RE.match(text)
    if not match:
        raise ValueError(f"not a UTC timestamp of the form YYYY-MM-DDThh:mm:ss[.ffffff]Z: {text!r}")
    year, month, day, hour, minute, second, frac = match.groups()
    micro = int((frac or "0").ljust(6, "0"))
    return make_utc(int(year), int(month), int(day), int(hour), int(minute), int(second), micro)


def make_utc(
    year: int,
    month: int,
    day: int,
    hour: int = 0,
    minute: int = 0,
    second: int = 0,
    microsecond: int = 0,
) -> datetime:
    """Build a UTC datetime with an error message that does not depend on the Python version.

    Error texts end up in verification reports, which must be byte-identical
    across supported Python versions.
    """
    try:
        return datetime(year, month, day, hour, minute, second, microsecond, tzinfo=UTC)
    except ValueError:
        raise ValueError(
            f"not a valid calendar date and time: {year:04d}-{month:02d}-{day:02d} "
            f"{hour:02d}:{minute:02d}:{second:02d}"
        ) from None


def format_utc(moment: datetime) -> str:
    """Format an aware datetime canonically: milliseconds, or microseconds when needed."""
    if moment.tzinfo is None:
        raise ValueError("naive datetime; Orbit Watch times must be UTC-aware")
    moment = moment.astimezone(UTC)
    base = moment.strftime("%Y-%m-%dT%H:%M:%S")
    micro = moment.microsecond
    if micro % 1000 == 0:
        return f"{base}.{micro // 1000:03d}Z"
    return f"{base}.{micro:06d}Z"


def add_seconds(moment: datetime, seconds: float) -> datetime:
    """Add a float number of seconds, rounded to the nearest microsecond."""
    return moment + timedelta(microseconds=round(seconds * 1_000_000))

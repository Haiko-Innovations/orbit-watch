"""The station profile is the station's place for every format (phase 5, step 5.6; decisions
P5-11 and D-55).

A station is verified with the place it publishes, so that anyone can repeat the
verification, and that place is its profile's, as precisely as its observer chose (D-54):

* an Orbit Watch JSON delivery names its station's place, which must be the profile's:
  latitude, longitude and height;
* an IOD or CCSDS TDM delivery names only a station number or name. It is verified at the
  profile's place, written as a sites document that is kept and published with the
  delivery, without the station's name.

A delivery names one station, its own. A replay delivers someone else's published file as
it is, and does not come here (D-51).
"""

from __future__ import annotations

import json
import re
from typing import Any

from orbit_watch.canonical import dumps_pretty
from orbit_watch.formats import detect_format, iod, tdm
from orbit_watch.formats.owjson import FormatError
from orbit_watch.schema import validate

PLACE_FIELDS = ("latitude_deg", "longitude_deg", "altitude_m")
SITE_ID = re.compile(r"^[A-Za-z0-9._-]{1,64}$")


class PlaceError(ValueError):
    """A delivery from another place than its station's profile. ``code`` maps to an API
    error."""

    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


def _place_text(station: dict[str, Any]) -> str:
    return (
        f"latitude {station.get('latitude_deg')}, longitude {station.get('longitude_deg')}, "
        f"{station.get('altitude_m')} m"
    )


def sites_for(profile: dict[str, Any], data: bytes, fmt: str | None) -> bytes | None:
    """Check a delivery's place against its station's profile. Returns, for an IOD or TDM
    delivery, the sites document that places the file's station at the profile's place;
    for a JSON delivery, None. Raises ``PlaceError`` for a file from another place. A file
    that cannot be read is left to verification, which says what is wrong with it."""
    station = profile["station"]
    try:
        detected = fmt or detect_format("", data)
        text = data.decode("utf-8")
    except (UnicodeDecodeError, FormatError, ValueError):
        return None
    if detected == "json":
        try:
            named = json.loads(text).get("station")
        except (ValueError, AttributeError):
            return None
        if not isinstance(named, dict):
            return None
        if any(named.get(name) != station.get(name) for name in PLACE_FIELDS):
            raise PlaceError(
                "wrong_place",
                f"the file places its station at {_place_text(named)}, and your station's "
                f"profile at {_place_text(station)}. The profile is your station's place for "
                "every delivery: deliver files with its place, or change the profile",
            )
        return None
    if detected == "iod":
        records = iod.read_iod(text).records
        numbers = sorted({record.station_number for record in records})
        if not numbers:
            return None
        if len(numbers) > 1:
            raise PlaceError(
                "wrong_place",
                "a delivery names one station, its own; this file names IOD stations "
                + ", ".join(f"{n:04d}" for n in numbers),
            )
        own = station.get("iod_station_number")
        if own is not None and own != numbers[0]:
            raise PlaceError(
                "wrong_place",
                f"the file names IOD station {numbers[0]:04d}, and your station's profile "
                f"{own:04d}",
            )
        site = {"id": station["id"], "iod_station_number": numbers[0]}
    elif detected == "tdm":
        try:
            segments = tdm.read_tdm(text).segments
        except tdm.TdmError:
            return None
        names = sorted({segment.station_id for segment in segments})
        if not names:
            return None
        if len(names) > 1:
            raise PlaceError(
                "wrong_place",
                "a delivery names one station, its own; this file names stations "
                + ", ".join(names),
            )
        if not SITE_ID.match(names[0]):
            raise PlaceError(
                "wrong_place",
                f"PARTICIPANT_1 {names[0]!r} is not a station name the service can place: "
                "use letters, digits, dots, dashes and underscores",
            )
        site = {"id": names[0]}
    else:
        return None
    for name in PLACE_FIELDS:
        site[name] = station[name]
    document = {"format": "orbit-watch/sites", "format_version": "1.0", "sites": [site]}
    problems = validate(document, "sites")
    if problems:  # pragma: no cover - a saved profile's place is valid
        raise PlaceError("wrong_place", "; ".join(problems))
    return dumps_pretty(document, sort_keys=False).encode("utf-8")

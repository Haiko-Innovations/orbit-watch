"""Personal data in the service (phase 4, step 4.4; decisions P4-09 and D-37).

The data inventory is ``docs/personal-data.md``; the privacy notice tells people what this
module does. Two things live here:

* **Station coordinates exactly or to about a kilometre, as the observer chooses** (P5-11,
  D-54). A station may be someone's home, and what a station delivers is published
  (decision D-17). The observer chooses "exact" or "kilometre" when saving the profile,
  with nothing chosen in advance; "kilometre" keeps the coordinates to two decimals of a
  degree, 1.1 km of latitude. With ``station_decimals`` set, as ``orbit-watch serve`` sets
  it by default, the service refuses a delivered file whose station coordinates are more
  precise than that, unless its station chose "exact": a file is kept as it was delivered,
  since its SHA-256 is what the chain and the attestations name.
* **Retention.** ``sweep`` deletes what the service no longer needs: ended and expired
  sign-in sessions, used-up sign-in messages, the limits' counts once their window has
  passed and idempotency records after a day. The follower runs it, and so does every
  sign-in, so it runs even where no follower is scheduled.
"""

from __future__ import annotations

import copy
import json
from datetime import datetime, timedelta
from typing import Any

from orbit_watch.storage import Database
from orbit_watch.timeutil import format_utc

STATION_DECIMALS = 2  # the public service's precision: about a kilometre
# How precisely a station's place is published, as its observer chooses (P5-11, D-54).
PLACES = ("exact", "kilometre")
# How long an Idempotency-Key is remembered: a retry within it is answered from the record.
IDEMPOTENCY_LIFETIME = timedelta(hours=24)
# How long a sign-in message is kept after it expires (5 minutes after it was written), so
# that a late answer is told "expired" rather than "unknown".
CHALLENGE_GRACE = timedelta(hours=1)


def rounded_station(profile: dict[str, Any], decimals: int) -> dict[str, Any]:
    """A copy of a station profile (or an observation set) whose station coordinates are
    rounded to ``decimals`` decimals of a degree."""
    rounded = copy.deepcopy(profile)
    station = rounded.get("station")
    if isinstance(station, dict):
        for name in ("latitude_deg", "longitude_deg"):
            value = station.get(name)
            if isinstance(value, int | float) and not isinstance(value, bool):
                station[name] = round(float(value), decimals)
    return rounded


def _more_precise(value: Any, decimals: int) -> bool:
    if not isinstance(value, int | float) or isinstance(value, bool):
        return False
    return round(float(value), decimals) != float(value)


def too_precise(body: bytes, decimals: int) -> str | None:
    """Why a delivered file may not be kept, or None. Only an Orbit Watch JSON observation
    set names its station's coordinates; IOD and CCSDS TDM files name a station that the
    service's own sites file places."""
    try:
        document = json.loads(body.decode("utf-8"))
    except (UnicodeDecodeError, ValueError):
        return None  # not JSON: verification says what is wrong with it
    station = document.get("station") if isinstance(document, dict) else None
    if not isinstance(station, dict):
        return None
    if not any(
        _more_precise(station.get(name), decimals) for name in ("latitude_deg", "longitude_deg")
    ):
        return None
    return (
        f"this service keeps station coordinates to {decimals} decimals of a degree (about a "
        f"kilometre), and the file's are more precise: round the station's latitude_deg and "
        f"longitude_deg to {decimals} decimals before you deliver it"
    )


def sweep(db: Database, now: datetime) -> dict[str, int]:
    """Delete what the service no longer needs (``now`` is wall-clock time). In the
    caller's transaction; none of it is state that other processes keep in memory."""
    stamp = format_utc(now)
    seconds = int(now.timestamp())
    removed = {
        "sessions": db.execute(
            "DELETE FROM sessions WHERE ended_at IS NOT NULL OR expires_at <= ?",
            (stamp,),
            state=False,
        ).rowcount,
        "sign_in_messages": db.execute(
            "DELETE FROM signin_challenges WHERE expires_at <= ?",
            (format_utc(now - CHALLENGE_GRACE),),
            state=False,
        ).rowcount,
        "limit_counts": db.execute(
            "DELETE FROM rate_limits WHERE expires_at <= ?", (seconds,), state=False
        ).rowcount,
        "idempotency_records": db.execute(
            "DELETE FROM idempotency WHERE expires_at IS NULL OR expires_at <= ?",
            (seconds,),
            state=False,
        ).rowcount,
    }
    return removed

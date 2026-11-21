"""Real observations from the IAU CPS's SCORE (decision P5-06).

The Satellite Constellation Observation Repository (https://score.cps.iau.org) publishes
observers' positional and brightness observations of satellites under CC BY 4.0. A positional
observation holds its time and the time's uncertainty, right ascension and declination in the
ICRF measured against Gaia DR3 stars with their variances, the observer's place and
instrument, and the observers' ORCID iDs.

Fetching is polite (SCORE's API allows 10 requests a second, read 2026-11-20): one satellite
and one time window at a time, through ``/api/observations/search``, in pages of at most 100,
at least a second apart, stopping at the first answer that is not 200. The full download,
which is behind a CAPTCHA, is never used.

Converting groups the observations into tracks, one station (place, instrument and
observers) and one object each, and writes each track as an Orbit Watch observation set whose
``source.origin`` names SCORE, the observers, SCORE's observation IDs and the licence.

SCORE's use policy (last updated 2024-12-02) asks users to credit the observers, and to show
this statement on any website or web service that uses SCORE data: "Any opinions, findings,
and conclusions or recommendations expressed in this material are those of the author(s) and
do not necessarily reflect the views of the NSF NOIRLab, the SKAO, the IAU, or any host or
member institution of the IAU CPS."
"""

from __future__ import annotations

import hashlib
import json
import math
import time
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

from orbit_watch import __version__
from orbit_watch.fetch import USER_AGENT, FetchError, read_body
from orbit_watch.model import Observation, ObservationSet, Station, Target
from orbit_watch.timeutil import format_utc, parse_utc

API_URL = "https://score.cps.iau.org/api/observations/search"
SITE_URL = "https://score.cps.iau.org"
NAME = "SCORE, the IAU CPS Satellite Constellation Observation Repository"
LICENCE = "CC-BY-4.0"
PAGE_SIZE = 100  # observations per request
PAUSE_S = 1.0  # between two requests: a tenth of what SCORE's API allows
MAX_PAGES = 200  # 20,000 observations per query at most
MAX_BYTES = 20 * 1024 * 1024
TRACK_GAP_S = 900.0  # a longer gap starts a new track, as a new pass in the quality meter
# A phone's place jitters by metres. Observations within this distance of a track's first
# place share it; farther ones start a new track, since a set has one station place.
PLACE_TOLERANCE_M = 100.0
FETCH_FORMAT = "orbit-watch/score-fetch"

NSF_STATEMENT = (
    "Any opinions, findings, and conclusions or recommendations expressed in this material are "
    "those of the author(s) and do not necessarily reflect the views of the NSF NOIRLab, the "
    "SKAO, the IAU, or any host or member institution of the IAU CPS."
)
ACKNOWLEDGEMENT = (
    "This research made use of data and/or services provided by the International Astronomical "
    "Union Centre for the Protection of the Dark and Quiet Sky (IAU CPS) SatHub. The "
    "development of SCORE has been supported by the National Science Foundation (NSF) under "
    "grant number: AST 2332736. SCORE is hosted at the NSF NOIRLab."
)


class ScoreError(FetchError):
    """SCORE answered with something unexpected; stop asking."""

    def __init__(self, message: str, status: int | None = None):
        super().__init__(message)
        self.status = status


def _advice(status: int) -> str:
    if status in (429, 500, 502, 503, 504):
        return "the server is busy: stop and wait at least 15 minutes before asking again"
    return "not retrying"


def _time(moment: datetime) -> str:
    return moment.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%S.000Z")


def search_url(norad_id: int, start: datetime, end: datetime, offset: int) -> str:
    query = urllib.parse.urlencode(
        {
            "satellite_number": str(norad_id),
            "start_date": _time(start),
            "end_date": _time(end),
            "limit": str(PAGE_SIZE),
            "offset": str(offset),
        }
    )
    return f"{API_URL}?{query}"


def fetch_window(
    norad_id: int,
    start: datetime,
    end: datetime,
    *,
    opener: Callable = urllib.request.urlopen,
    sleep: Callable[[float], None] = time.sleep,
    now: Callable[[], datetime] = lambda: datetime.now(UTC),
) -> dict[str, Any]:
    """Every SCORE observation of one object in a window, page by page."""
    if end <= start:
        raise ValueError("the window must end after it starts")
    items: list[dict[str, Any]] = []
    total: int | None = None
    for page in range(MAX_PAGES):
        if page:
            sleep(PAUSE_S)
        url = search_url(norad_id, start, end, page * PAGE_SIZE)
        request = urllib.request.Request(
            url,
            headers={
                "User-Agent": USER_AGENT,
                "Accept": "application/json",
                "Accept-Encoding": "gzip",
            },
        )
        try:
            with opener(request, timeout=60) as response:
                status = getattr(response, "status", 200)
                body = read_body(response, MAX_BYTES) if status == 200 else b""
        except urllib.error.HTTPError as exc:
            raise ScoreError(
                f"SCORE answered HTTP {exc.code} for {url} ({_advice(exc.code)})", exc.code
            ) from None
        except urllib.error.URLError as exc:
            raise ScoreError(f"could not reach SCORE: {exc.reason}") from None
        if status != 200:
            raise ScoreError(f"SCORE answered HTTP {status} for {url} ({_advice(status)})", status)
        try:
            document = json.loads(body.decode("utf-8"))
            page_items, count = document["items"], int(document["count"])
        except (ValueError, UnicodeDecodeError, LookupError, TypeError):
            raise ScoreError(f"SCORE's answer is not the expected JSON: {body[:200]!r}") from None
        if not isinstance(page_items, list):
            raise ScoreError("SCORE's answer has no list of items")
        total = count if total is None else total
        items.extend(page_items)
        if not page_items or len(items) >= total:
            break
    else:
        limit = MAX_PAGES * PAGE_SIZE
        raise ScoreError(f"more than {limit} observations: ask for a shorter window")
    unique = {int(item["id"]): item for item in items}
    return {
        "format": FETCH_FORMAT,
        "source": NAME,
        "url": search_url(norad_id, start, end, 0).replace("&offset=0", ""),
        "satellite_number": norad_id,
        "start": format_utc(start),
        "end": format_utc(end),
        "retrieved": format_utc(now().replace(microsecond=0)),
        "licence": LICENCE,
        "count": len(unique),
        "items": [unique[key] for key in sorted(unique)],
    }


@dataclass(frozen=True)
class Assumed:
    """What the converter assumes when SCORE gives no uncertainty."""

    angle_uncertainty_arcsec: float | None = None
    time_uncertainty_s: float | None = None


@dataclass
class Converted:
    observation_set: ObservationSet
    skipped: dict[str, int]


def _positive(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) and number > 0 else None


def angle_uncertainty(item: dict[str, Any]) -> float | None:
    """One-sigma angle uncertainty from SCORE's variances (arcsec²): the larger of the two,
    which is conservative whichever way SCORE measures the right ascension's."""
    ra, dec = _positive(item.get("sigma_2_ra")), _positive(item.get("sigma_2_dec"))
    if ra is None or dec is None:
        return None
    return round(math.sqrt(max(ra, dec)), 3)


def station_id(place: tuple[float, float, float], instrument: str, observers: tuple) -> str:
    """The ID of one observer's instrument at one site, from the station's place."""
    digest = hashlib.sha256(json.dumps([place, instrument, list(observers)]).encode()).hexdigest()
    return f"SCORE-{digest[:12]}"


def _place(item: dict[str, Any]) -> tuple[float, float, float]:
    return (float(item["obs_lat_deg"]), float(item["obs_long_deg"]), float(item["obs_alt_m"]))


def distance_m(a: tuple[float, float, float], b: tuple[float, float, float]) -> float:
    """Approximate distance between two nearby places, enough to compare with metres."""
    north = math.radians(b[0] - a[0]) * 6371000.0
    east = math.radians(b[1] - a[1]) * 6371000.0 * math.cos(math.radians(a[0]))
    return math.sqrt(north**2 + east**2 + (b[2] - a[2]) ** 2)


def _key(item: dict[str, Any]) -> tuple:
    return (
        int(item["satellite_number"]),
        str(item.get("instrument") or ""),
        tuple(sorted(item.get("obs_orc_id") or [])),
    )


NOTHING_ASSUMED = Assumed()


def place_jumps(points: list[tuple[datetime, tuple[float, float, float]]]) -> dict[int, float]:
    """The observations whose place jumps away from the rest of their track, by index, with
    the distance in metres to the nearest other place. ``points`` are one object's
    observations by one instrument, as (time, place) in time order, and a track is a run
    without a gap longer than ``TRACK_GAP_S``. An observation jumps when no other
    observation of its track lies within ``PLACE_TOLERANCE_M`` of it, while most of them
    share a place with another: a phone's position fix that failed for one exposure. A
    phone that truly moves has no such majority, and nothing is left out."""
    jumps: dict[int, float] = {}
    start = 0
    for end in range(1, len(points) + 1):
        if end < len(points) and points[end][0] - points[end - 1][0] <= timedelta(
            seconds=TRACK_GAP_S
        ):
            continue
        track = range(start, end)
        start = end
        if len(track) < 3:
            continue
        places: dict[tuple[float, float, float], list[int]] = {}
        for index in track:
            places.setdefault(points[index][1], []).append(index)
        alone: dict[tuple[float, float, float], float] = {}
        for place, members in places.items():
            if len(members) > 1:
                continue
            others = [distance_m(place, other) for other in places if other != place]
            if others and min(others) > PLACE_TOLERANCE_M:
                alone[place] = min(others)
        if alone and 2 * sum(len(places[place]) for place in alone) < len(track):
            for place, away in alone.items():
                jumps[places[place][0]] = away
    return jumps


def convert(
    documents: list[dict[str, Any]], assumed: Assumed = NOTHING_ASSUMED
) -> tuple[list[ObservationSet], dict[str, int]]:
    """Tracks of positional observations as observation sets, and the counts left out by
    reason. Observations without a position, place or time are left out; an uncertainty
    SCORE does not give is taken from ``assumed``, or the observation is left out.

    A station is one observer's instrument at one site. Tracks of the same instrument and
    observers whose places lie within ``PLACE_TOLERANCE_M`` of each other share a station,
    whose place is the first one seen; so convert everything of one example together."""
    retrieved: dict[int, str] = {}
    unique: dict[int, dict[str, Any]] = {}
    for fetched in documents:
        if fetched.get("format") != FETCH_FORMAT:
            raise ValueError(f"not an {FETCH_FORMAT} document")
        for item in fetched["items"]:
            unique[int(item["id"])] = item
            retrieved[int(item["id"])] = str(fetched["retrieved"])[:10]
    skipped: dict[str, int] = {}

    def skip(reason: str) -> None:
        skipped[reason] = skipped.get(reason, 0) + 1

    groups: dict[tuple, list[tuple[dict[str, Any], Observation, bool, bool]]] = {}
    for key_id in sorted(unique):
        item = unique[key_id]
        if item.get("sat_ra_deg") is None or item.get("sat_dec_deg") is None:
            skip("no position (brightness only)")
            continue
        if None in (item.get("obs_lat_deg"), item.get("obs_long_deg"), item.get("obs_alt_m")):
            skip("no observer's place")
            continue
        try:
            moment = parse_utc(str(item["obs_time_utc"]))
        except (KeyError, ValueError):
            skip("no valid time")
            continue
        angle = angle_uncertainty(item)
        angle_assumed = angle is None
        if angle_assumed:
            angle = assumed.angle_uncertainty_arcsec
        tau = _positive(item.get("obs_time_uncert_sec"))
        time_assumed = tau is None
        if time_assumed:
            tau = assumed.time_uncertainty_s
        if angle is None:
            skip("no angle uncertainty, and none assumed")
            continue
        if tau is None:
            skip("no time uncertainty, and none assumed")
            continue
        magnitude = item.get("apparent_mag")
        observation = Observation(
            time=moment,
            time_uncertainty_s=float(tau),
            angle_type="radec",
            angle_uncertainty_arcsec=float(angle),
            frame="ICRF",
            ra_deg=round(float(item["sat_ra_deg"]) % 360.0, 8),
            dec_deg=round(float(item["sat_dec_deg"]), 8),
            magnitude=None if magnitude is None else round(float(magnitude), 3),
        )
        groups.setdefault(_key(item), []).append((item, observation, angle_assumed, time_assumed))

    tracks: list[tuple[tuple, list[tuple]]] = []
    jumped: dict[tuple, list[tuple[datetime, float]]] = {}
    for key in sorted(groups):
        rows = sorted(groups[key], key=lambda row: (row[1].time, int(row[0]["id"])))
        jumps = place_jumps([(row[1].time, _place(row[0])) for row in rows])
        for index in sorted(jumps):
            skip("its place lies far from every other observation of its track")
            jumped.setdefault(key, []).append((rows[index][1].time, jumps[index]))
        rows = [row for index, row in enumerate(rows) if index not in jumps]
        current: list[tuple] = []
        for row in rows:
            if (
                current
                and (row[1].time - current[-1][1].time) <= timedelta(seconds=TRACK_GAP_S)
                and distance_m(_place(current[0][0]), _place(row[0])) <= PLACE_TOLERANCE_M
            ):
                current.append(row)
            else:
                if current:
                    tracks.append((key, current))
                current = [row]
        if current:
            tracks.append((key, current))
    tracks.sort(key=lambda t: (t[1][0][1].time, t[0][0], int(t[1][0][0]["id"])))

    stations: dict[tuple, list[tuple[float, float, float]]] = {}
    sets: list[ObservationSet] = []
    for (norad_id, instrument, observers), track in tracks:
        first = _place(track[0][0])
        sites = stations.setdefault((instrument, observers), [])
        place = next((s for s in sites if distance_m(s, first) <= PLACE_TOLERANCE_M), None)
        if place is None:
            place = first
            sites.append(place)
        day = retrieved[int(track[0][0]["id"])]
        start, end = track[0][1].time, track[-1][1].time
        jumps = jumped.get((norad_id, instrument, observers), [])
        left_out = [distance for moment, distance in jumps if start < moment < end]
        sets.append(
            _observation_set(track, norad_id, place, instrument, observers, assumed, day, left_out)
        )
    sets.sort(key=lambda s: (s.observations[0].time, s.target.norad_id, s.station.id))
    return sets, skipped


def _observation_set(
    track: list[tuple],
    norad_id: int,
    place: tuple[float, float, float],
    instrument: str,
    observers: tuple,
    assumed: Assumed,
    retrieved: str,
    jumps: list[float],
) -> ObservationSet:
    items = [row[0] for row in track]
    angles_assumed = sum(1 for row in track if row[2])
    times_assumed = sum(1 for row in track if row[3])
    discrepant = sum(1 for item in items if item.get("potentially_discrepant"))
    origin: dict[str, Any] = {
        "name": NAME,
        "url": SITE_URL,
        "licence": LICENCE,
        "observers": list(observers),
        "observation_ids": [str(item["id"]) for item in items],
        "retrieved": retrieved,
    }
    notes = [f"Real observations published in SCORE under {LICENCE}, converted by Orbit Watch."]
    if angles_assumed:
        origin["assumed_angle_uncertainty_arcsec"] = assumed.angle_uncertainty_arcsec
        notes.append(
            f"SCORE gives no angle uncertainty for {angles_assumed} of {len(track)} observations: "
            f"{assumed.angle_uncertainty_arcsec:g} arcsec is assumed by the converter, not "
            "declared by the observer."
        )
    if times_assumed:
        origin["assumed_time_uncertainty_s"] = assumed.time_uncertainty_s
        notes.append(
            f"SCORE gives no time uncertainty for {times_assumed} of {len(track)} observations: "
            f"{assumed.time_uncertainty_s:g} s is assumed by the converter."
        )
    if discrepant:
        notes.append(f"SCORE marks {discrepant} of these observations as potentially discrepant.")
    spread = max(distance_m(place, _place(item)) for item in items)
    if spread > 0:
        notes.append(
            f"SCORE gives the observer's place for each observation; they differ by up to "
            f"{spread:.0f} m from the station's place, the first seen at this site."
        )
    if jumps:
        notes.append(
            f"{len(jumps)} observation(s) of this track are left out: SCORE gives each a place "
            f"{min(jumps) / 1000:.1f} to {max(jumps) / 1000:.1f} km from every other "
            "observation of the track, while the others share one place."
        )
    name = str(items[0].get("satellite_name") or "") or None
    return ObservationSet(
        station=Station(
            id=station_id(place, instrument, observers),
            latitude_deg=place[0],
            longitude_deg=place[1],
            altitude_m=place[2],
            name=(f"SCORE observer, {instrument}" if instrument else "SCORE observer")[:200],
        ),
        target=Target(norad_id=norad_id, name=name[:200] if name else None),
        observations=[row[1] for row in track],
        simulated=False,
        source={
            "software": f"orbit-watch {__version__}",
            "converted_from": "score",
            "notes": " ".join(notes)[:2000],
            "origin": origin,
        },
    )


def file_name(observation_set: ObservationSet) -> str:
    first = observation_set.observations[0].time.strftime("%Y%m%dT%H%M")
    return f"{observation_set.target.norad_id}-{first}-{observation_set.station.id}.json"


def credits_markdown(sets: list[ObservationSet], title: str = "Credits") -> str:
    """The credits CC BY 4.0 asks for: who made each file's observations, and the statements
    that SCORE and SatChecker ask users to show."""
    lines = [
        f"# {title}",
        "",
        "The observations here were made and published by the observers below in",
        f"[SCORE]({SITE_URL}), the IAU CPS's Satellite Constellation Observation Repository,",
        "under the [Creative Commons Attribution 4.0](https://creativecommons.org/licenses/by/4.0/)",
        "licence. Orbit Watch converted them to its own format and changed nothing else: the",
        "files name SCORE's observation IDs, any uncertainty the converter assumed and any",
        "observation it left out.",
        "",
        "| File | Object | Instrument | Observations | Observers (ORCID iD) |",
        "|---|---|---|---|---|",
    ]
    for observation_set in sorted(sets, key=file_name):
        origin = observation_set.source["origin"]
        observers = ", ".join(
            f"[{orcid}](https://orcid.org/{orcid})" for orcid in origin["observers"]
        )
        instrument = (observation_set.station.name or "").removeprefix("SCORE observer, ")
        name = observation_set.target.name or ""
        lines.append(
            f"| `{file_name(observation_set)}` | {observation_set.target.norad_id} {name} | "
            f"{instrument} | {len(observation_set.observations)} | {observers} |"
        )
    lines += [
        "",
        "SCORE asks for this acknowledgement:",
        "",
        f"> {ACKNOWLEDGEMENT}",
        "",
        "and for this statement on any publication, presentation, website or web service that",
        "uses SCORE data:",
        "",
        f"> {NSF_STATEMENT}",
        "",
        "The reference orbits come from the IAU CPS's SatChecker, which asks for this",
        "acknowledgement:",
        "",
        "> This research made use of data and/or services provided by the International",
        "> Astronomical Union Centre for the Protection of the Dark and Quiet Sky (IAU CPS)",
        "> SatHub. The development of SatChecker has been supported by the National Science",
        "> Foundation (NSF) under grant numbers: AST 2332735 and AST 2332736. SatChecker is",
        "> hosted at the NSF NOIRLab. Any opinions, findings, and conclusions or recommendations",
        "> expressed in this material are those of the author(s) and do not necessarily reflect",
        "> the views of the NSF, IAU, NSF NOIRLab, SKAO, ESO, or any host or member institution",
        "> of the IAU CPS.",
        "",
        "If you are one of these observers and want your observations removed, write to",
        'info@haikoinnovations.com with "Orbit Watch privacy" in the subject line: they are',
        "removed from the next version of the repository.",
        "",
    ]
    return "\n".join(lines)

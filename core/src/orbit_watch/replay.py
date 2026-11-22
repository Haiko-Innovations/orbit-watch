"""Replay requests (phase 5, step 5.5, second part; decisions P5-10 and D-51).

A replay delivers observations that someone else published, through the service, to show
and test the whole chain with real data. Only an administrator creates a replay request.
Its window lies in the past, and its document (request format 1.1) names:

* the observation file it replays, by its SHA-256: nothing else can be delivered for it;
* the replay station that delivers the file, which is never its observer;
* the file's source, licence and observers' ORCID iDs, so that every file of the replay
  names them.

``replay_request`` builds such a document from a published observation file whose
``source.origin`` names where it comes from, such as one in ``examples/real/``.
"""

from __future__ import annotations

from datetime import datetime, timedelta

from orbit_watch.canonical import dumps_pretty, sha256_bytes
from orbit_watch.formats.owjson import FormatError, read_observation_set
from orbit_watch.timeutil import format_utc

MARGIN = timedelta(minutes=5)  # the window reaches this far beyond the first and last
TITLE_LIMIT = 200


def replay_request(
    observations: bytes, request_id: str, station: str, *, margin: timedelta = MARGIN
) -> bytes:
    """A replay request (format 1.1) for a published observation file. The window runs
    from ``margin`` before its first observation to ``margin`` after its last; the
    requirements are those the file meets, so that the replay asks for the file as it is."""
    observation_set = read_observation_set(observations)
    origin = observation_set.source.get("origin")
    if observation_set.simulated or not isinstance(origin, dict):
        raise FormatError(
            "a replay needs observations that someone else published: a file that is not "
            "SIMULATED and whose source.origin names the source, licence and observers"
        )
    if not origin.get("observers"):
        raise FormatError("a replay names its observers, and source.origin names none")
    observed = observation_set.observations
    first = min(o.time for o in observed)
    last = max(o.time for o in observed)
    target = observation_set.target
    name = target.name or str(target.norad_id)
    replay = {
        "station": station,
        "observations_sha256": sha256_bytes(observations),
        "source": origin["name"],
        **({"url": origin["url"]} if origin.get("url") else {}),
        "licence": origin["licence"],
        "observers": list(origin["observers"]),
    }
    title = (
        f"Replay of {len(observed)} observations of {name} published in "
        f"{origin['name'].split(',')[0]} under {origin['licence']}"
    )
    document = {
        "format": "orbit-watch/request",
        "format_version": "1.1",
        "simulated": False,
        "request_id": request_id,
        "title": title[:TITLE_LIMIT],
        "target": {"norad_id": target.norad_id, **({"name": target.name} if target.name else {})},
        "window": {"start": _whole(first - margin), "end": _whole(last + margin, up=True)},
        "requirements": {
            "min_observations": len(observed),
            "max_angle_uncertainty_arcsec": max(o.angle_uncertainty_arcsec for o in observed),
            "max_time_uncertainty_s": max(o.time_uncertainty_s for o in observed),
            "angle_types": sorted({o.angle_type for o in observed}),
        },
        "replay": replay,
    }
    return dumps_pretty(document, sort_keys=False).encode("utf-8")


def _whole(when: datetime, *, up: bool = False) -> str:
    """The time to the whole second, rounded outwards so the window keeps every
    observation."""
    whole = when.replace(microsecond=0)
    if up and whole < when:
        whole += timedelta(seconds=1)
    return format_utc(whole)

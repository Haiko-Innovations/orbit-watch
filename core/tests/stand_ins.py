"""Stand-ins for a real object and for published observations, for the local stack and its
tests (phase 5, step 5.5; decision D-53). Everything here is made up and LOCAL:

* the object 339990, "LOCAL STAND-IN 339990", which an administrator adds to the allow-list
  with a reason that says so, and whose element set is SIM-CUBESAT-A's elements under its
  number, uploaded by hand: no real element set is committed (D-06), and nothing is fetched.
  No catalogue will reach that number for decades; it comes after the SIMULATED objects', so
  that they stay first on the list, and SGP4 reads numbers up to 339999;
* observations "published" by a made-up observer at a made-up source, credited to ORCID's
  documented example iD of a fictitious researcher, for a replay to deliver;
* SIMULATED observations of the stand-in, for a SIMULATED request for it.

The stack labels the stand-in as a real object, which is what it stands in for, and the
reason on the allow-list says that it is made up.
"""

from __future__ import annotations

import json
from dataclasses import replace
from datetime import datetime

from helpers import catalog_bytes

from orbit_watch.canonical import dumps_pretty
from orbit_watch.catalog import parse_catalog
from orbit_watch.formats import owjson
from orbit_watch.sim.simulator import StationProfile, load_profile, simulate
from orbit_watch.timeutil import parse_utc

STAND_IN = 339990
STAND_IN_NAME = "LOCAL STAND-IN 339990"
STAND_IN_REASON = (
    "LOCAL TEST: stands in for a real object in the local stack; its orbit is made up."
)
EXAMPLE_ORCID = "0000-0002-1825-0097"  # ORCID's example iD of a fictitious researcher
MADE_UP_SOURCE = "A MADE-UP SOURCE, for the local stack"
PUBLISHED_WINDOW = ("2026-10-31T15:00:00Z", "2026-11-01T03:00:00Z")  # before the stack starts
PUBLISHED_SEED = 301


def stand_in_record() -> dict:
    """SIM-CUBESAT-A's elements under the stand-in's number and name."""
    record = dict(json.loads(catalog_bytes())["records"][0])
    record.update(NORAD_CAT_ID=STAND_IN, OBJECT_NAME=STAND_IN_NAME, OBJECT_ID="2026-999Z")
    return record


def stand_in_catalogue() -> bytes:
    """The stand-in's element set, to upload by hand: it is labelled as real, like the
    object it stands in for, and says that it is made up."""
    document = {
        "format": "orbit-watch/gp-catalog",
        "format_version": "1.0",
        "simulated": False,
        "description": (
            "LOCAL TEST: a made-up element set for the local stack's stand-in for a real "
            "object, copied from SIM-CUBESAT-A. Not a real orbit."
        ),
        "records": [stand_in_record()],
    }
    return dumps_pretty(document, sort_keys=False).encode("utf-8")


def made_up_observer() -> StationProfile:
    """SIM-CUBESAT-A's camera profile, at a made-up observer's own place, to five decimals as
    a published file gives it."""
    profile = load_profile("sim-cmos-gps")
    station = replace(
        profile.station,
        id="MADE-UP-OBSERVER",
        name="A made-up observer, for the local stack",
        latitude_deg=61.49911,
        longitude_deg=23.78712,
        iod_station_number=None,
    )
    return replace(profile, station=station)


def published_observations() -> bytes:
    """Observations of the stand-in as a made-up observer "published" them: not SIMULATED,
    with a source.origin like SCORE's, in a window that ended before the stack starts."""
    start, end = (parse_utc(t) for t in PUBLISHED_WINDOW)
    observed = simulate(
        parse_catalog(stand_in_catalogue()),
        STAND_IN,
        made_up_observer(),
        start,
        end,
        seed=PUBLISHED_SEED,
        max_passes=1,
    )
    document = json.loads(owjson.write_observation_set(observed))
    document["format_version"] = "1.1"
    document["simulated"] = False
    document["source"] = {
        "software": "orbit-watch local stack",
        "notes": "LOCAL TEST: made up for the local stack, not real observations.",
        "origin": {
            "name": MADE_UP_SOURCE,
            "url": "https://example.org",
            "licence": "CC-BY-4.0",
            "observers": [EXAMPLE_ORCID],
            "observation_ids": [str(i + 1) for i in range(len(document["observations"]))],
        },
    }
    return dumps_pretty(document, sort_keys=False).encode("utf-8")


def stand_in_observations(
    profile: StationProfile, start: datetime, end: datetime, seed: int
) -> bytes:
    """A simulated station's SIMULATED observations of the stand-in, along its element set,
    as the service's simulator makes them (D-50)."""
    observed = simulate(
        parse_catalog(stand_in_catalogue()),
        STAND_IN,
        profile,
        start,
        end,
        seed=seed,
        max_passes=2,
        notes="SIMULATED observations of the local stack's stand-in for a real object.",
    )
    return owjson.write_observation_set(observed).encode("utf-8")

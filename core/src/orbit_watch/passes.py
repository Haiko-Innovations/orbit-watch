"""A station's passes of an object, and the part of each that the station can see (phase 5,
step 5.7; decisions P5-12, D-57).

A pass runs from rise to set above an elevation limit. Its visible part is where the
object is sunlit and the station's sky is dark (``orbit_watch.sun``); the simulator
observes only there (issue #7), and step 5.7's third part lists the passes for a request.
The visible part is found by sampling the pass every ``STEP_S`` seconds: its start and end
are the first and last visible samples, and its peak is the highest of them.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any

import numpy as np

from orbit_watch import sun
from orbit_watch.catalog import Catalog, timescale
from orbit_watch.geometry import topos
from orbit_watch.model import Station
from orbit_watch.timeutil import add_seconds, format_utc

STEP_S = 10  # the visible part's resolution


@dataclass(frozen=True)
class Pass:
    """One pass above the elevation limit, and its visible part if it has one."""

    rise: datetime
    culmination: datetime
    set: datetime
    max_elevation_deg: float
    visible_start: datetime | None = None
    visible_peak: datetime | None = None
    visible_end: datetime | None = None
    visible_max_elevation_deg: float | None = None

    @property
    def visible(self) -> bool:
        return self.visible_peak is not None

    def public(self) -> dict[str, Any]:
        def t(value: datetime | None) -> str | None:
            return None if value is None else format_utc(value)

        return {
            "rise": t(self.rise),
            "culmination": t(self.culmination),
            "set": t(self.set),
            "max_elevation_deg": round(self.max_elevation_deg, 1),
            "visible": self.visible,
            "visible_start": t(self.visible_start),
            "visible_peak": t(self.visible_peak),
            "visible_end": t(self.visible_end),
            "visible_max_elevation_deg": (
                None
                if self.visible_max_elevation_deg is None
                else round(self.visible_max_elevation_deg, 1)
            ),
        }


def _whole_second(moment: datetime) -> datetime:
    return add_seconds(moment.replace(microsecond=0), round(moment.microsecond / 1e6))


def _intervals(times, events, start: datetime, end: datetime) -> list[tuple[datetime, datetime]]:
    """Rise-to-set intervals from Skyfield's events (0 rise, 1 culmination, 2 set); a pass
    under way when the window opens or closes is cut at the window's edge."""
    intervals: list[tuple[datetime, datetime]] = []
    rise: datetime | None = None
    began = False
    for t, event in zip(times, events, strict=True):
        moment = t.utc_datetime()
        if event == 0:
            rise, began = moment, True
        elif event == 2:
            intervals.append((rise if began and rise is not None else start, moment))
            rise, began = None, True
        elif not began:  # the window opened during a pass
            rise, began = start, True
    if rise is not None:
        intervals.append((rise, end))
    return intervals


def passes(
    catalog: Catalog,
    norad_id: int,
    station: Station,
    start: datetime,
    end: datetime,
    min_elevation_deg: float,
    dark_sky_deg: float = sun.DARK_SKY_SUN_ELEVATION_DEG,
) -> list[Pass]:
    """The object's passes over the station in the window, above ``min_elevation_deg``, each
    with its visible part: sunlit, under a sky darker than ``dark_sky_deg``."""
    ts = timescale()
    satellite = catalog.satellite(norad_id)
    here = topos(station)
    times, events = satellite.find_events(
        here, ts.from_datetime(start), ts.from_datetime(end), altitude_degrees=min_elevation_deg
    )
    found = []
    for rise, setting in _intervals(times, events, start, end):
        seconds = np.arange(0.0, (setting - rise).total_seconds() + 1e-9, STEP_S)
        if seconds[-1] < (setting - rise).total_seconds():
            seconds = np.append(seconds, (setting - rise).total_seconds())
        t = ts.from_datetimes([rise + timedelta(seconds=float(s)) for s in seconds])
        elevation = (satellite - here).at(t).altaz()[0].degrees
        lit = sun.sunlit(satellite.at(t).position.km, t)
        visible = (elevation >= min_elevation_deg) & lit & sun.dark(station, t, dark_sky_deg)
        top = int(np.argmax(elevation))
        moments = t.utc_datetime()
        details: dict[str, Any] = {}
        if visible.any():
            where = np.flatnonzero(visible)
            peak = int(where[np.argmax(elevation[where])])
            details = {
                "visible_start": _whole_second(moments[where[0]]),
                "visible_peak": _whole_second(moments[peak]),
                "visible_end": _whole_second(moments[where[-1]]),
                "visible_max_elevation_deg": float(elevation[peak]),
            }
        found.append(
            Pass(
                rise=_whole_second(rise),
                culmination=_whole_second(moments[top]),
                set=_whole_second(setting),
                max_elevation_deg=float(elevation[top]),
                **details,
            )
        )
    return found

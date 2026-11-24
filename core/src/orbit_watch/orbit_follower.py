"""The follower fetches reference orbits (phase 5, step 5.4; decisions P5-02, P5-03, D-48).

Each run of the follower fetches what the open requests for real objects need, a few
objects per run, the objects asked for least recently first, ``PAUSE_S`` apart:

* **CelesTrak** for a request whose window has not ended and starts within a day: the
  object's current GP data, one object by its catalogue number, CSV with gzip, at most once
  per two-hour update (P5-02). When the object's operator publishes its orbit (its target
  has ``operator_orbits``), also its current SupGP data the same way, of which the sets of
  the operator's orbit are kept (P6-03, D-63). Its ``target`` is ``SUPGP``.
* **SatChecker** for a request whose window has ended, such as a replay (P5-10): the set
  nearest the middle of the window, asked for once, unless a stored set is within a day of
  it (P5-03).

Only objects on the allow-list that are not SIMULATED, in requests that are open, funded
or reserved. With the requests left in a run, it fetches CelesTrak's groups and SupGP
sources that the allow-list is built from, each at most once a day (P5-08, D-49, P6-04,
D-62). A SupGP source's answer stops CelesTrak as a group's does.

**Any answer that is not 200 with the object's element sets, or no answer at all, stops
that source.** Nothing more is fetched from it until an administrator resumes it, since
CelesTrak asks for a person to look, and no answer may mean that its firewall blocks the
service's address. After a 500 or a 503, or no answer, the source also waits at least 15
minutes, even once resumed. An object that answered 404 is not asked for again until an
administrator says so. ``/v1/health/reference-orbits`` reports a stop, so the hourly uptime
check opens an alert issue.

The requests are made outside the database's lock, one at a time. Each is recorded as asked
for just before it is made, so that another process does not make it too, and each answer
is kept in a transaction of its own.
"""

from __future__ import annotations

import time
import urllib.request
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import TYPE_CHECKING, Any

from orbit_watch import allowlist, satchecker
from orbit_watch.catalog import SOURCE_KEY, parse_catalog
from orbit_watch.fetch import UPDATE_INTERVAL_S, FetchError, build_url, download_gp
from orbit_watch.lifecycle import Status
from orbit_watch.supgp import SERVICE as SUPGP_SERVICE
from orbit_watch.supgp import build_url as supgp_url
from orbit_watch.supgp import download_supgp, sup_sets
from orbit_watch.timeutil import format_utc, parse_utc

if TYPE_CHECKING:  # pragma: no cover
    from orbit_watch.service import RequestService
    from orbit_watch.storage import Database

SOURCES = ("celestrak", "satchecker")
SUPGP = "supgp"  # the target of a request for an object's current SupGP data
REQUESTS_PER_RUN = 3  # a run stays short: at most this many requests
PAUSE_S = 2.0  # between two requests of one run
UPDATE = timedelta(seconds=UPDATE_INTERVAL_S)  # CelesTrak updates GP data every two hours
BUSY_WAIT = timedelta(minutes=15)  # after a 500 or a 503, or no answer
LEAD = timedelta(days=1)  # CelesTrak: from a day before the window starts
NEAR_ENOUGH = timedelta(days=1)  # SatChecker: a stored set this near the middle will do
DAILY = timedelta(days=1)  # CelesTrak's groups for the allow-list: at most once a day
OPEN_STATUSES = (Status.OPEN, Status.FUNDED, Status.RESERVED)
TLE_LIMIT = 100_000  # a TLE holds catalogue numbers below this


@dataclass(frozen=True)
class Want:
    """One request to a source: an object's current GP sets (``target`` is ''), its current
    SupGP sets (``target`` is ``SUPGP``), the set nearest a time in the past (``target`` is
    that time), or the objects of one of CelesTrak's groups or SupGP sources for the
    allow-list (``group``; ``norad_id`` is 0)."""

    source: str
    norad_id: int
    target: str
    request_id: str
    group: str = ""

    def public(self) -> dict[str, Any]:
        if self.group:
            return {"source": self.source, "group": self.group}
        view: dict[str, Any] = {"source": self.source, "norad_id": self.norad_id}
        if self.target == SUPGP:
            view["data"] = "supgp"
        elif self.target:
            view["nearest"] = self.target
        return view


@dataclass
class Fetcher:
    """How the follower reaches the sources; tests give local stand-ins."""

    opener: Callable = urllib.request.urlopen
    sleep: Callable[[float], None] = field(default=time.sleep)
    requests_per_run: int = REQUESTS_PER_RUN
    groups: tuple[str, ...] = allowlist.GROUPS  # CelesTrak's groups and SupGP sources


def _epoch(text: str) -> datetime | None:
    try:
        return parse_utc(text if text.endswith("Z") else text + "Z")
    except ValueError:
        return None


def wanted(service: RequestService, now: datetime) -> list[Want]:
    """What the open requests for real objects need now, one per object and target."""
    targets = service.targets()
    simulated = service.simulated_objects()
    found: dict[tuple[str, int, str], Want] = {}
    for request_id, record in sorted(service.records.items()):
        terms = record.terms
        norad = terms.target_norad_id
        if record.status not in OPEN_STATUSES or norad in simulated:
            continue
        if norad not in targets:
            continue
        if terms.window_end > now:
            if terms.window_start - LEAD > now:
                continue
            key = ("celestrak", norad, "")
        else:
            middle = terms.window_start + (terms.window_end - terms.window_start) / 2
            epochs = [_epoch(s.epoch) for s in service.verifying_sets(norad)]
            if any(e is not None and abs(e - middle) <= NEAR_ENOUGH for e in epochs):
                continue
            key = ("satchecker", norad, format_utc(middle))
        found.setdefault(key, Want(*key, request_id))
        if key[0] == "celestrak" and targets[norad].operator_orbits:
            supgp = ("celestrak", norad, SUPGP)  # after GP, which verification uses now
            found.setdefault(supgp, Want(*supgp, request_id))
    return list(found.values())


def _due(row: dict[str, Any] | None, want: Want, now: datetime) -> bool:
    if row is None:
        return True
    if row["status"] == 404:
        return False  # it has no public data: not asked for again
    if want.source == "satchecker" and row["status"] == 200:
        return False  # the past does not change: asked for once
    return parse_utc(row["asked_at"]) <= now - UPDATE


def _sources(db: Database) -> dict[str, dict[str, Any]]:
    return {row["source"]: row for row in db.query("SELECT * FROM orbit_sources")}


def available(db: Database, source: str, now: datetime) -> bool:
    """Whether the follower may ask ``source`` now: not stopped, and not waiting."""
    row = _sources(db)[source]
    if row["stopped_at"] is not None:
        return False
    return row["not_before"] is None or parse_utc(row["not_before"]) <= now


def _group_due(row: dict[str, Any] | None, now: datetime) -> bool:
    """A group is fetched once a day; after an answer that was not 200, or none, it may be
    asked for again after two hours, once a person has resumed CelesTrak."""
    if row is None:
        return True
    wait = DAILY if row["status"] == 200 else UPDATE
    return parse_utc(row["asked_at"]) <= now - wait


def _group_order(group: str, row: dict[str, Any] | None) -> tuple[bool, str]:
    """The excluded groups first, since the included groups and sources count only once
    those are in; then the one asked for least recently."""
    return group not in allowlist.EXCLUDED_GROUPS, row["asked_at"] if row else ""


def _group_want(group: str) -> Want:
    return Want("celestrak", 0, "", "", group=group)


def plan(
    db: Database,
    service: RequestService,
    now: datetime,
    limit: int,
    groups: tuple[str, ...] = allowlist.GROUPS,
) -> list[Want]:
    """The requests of this run: the objects asked for least recently first, then the
    ``groups`` that are due, the excluded ones first."""
    asks = {
        (row["source"], int(row["norad_id"]), row["target"]): row
        for row in db.query("SELECT * FROM orbit_asks")
    }
    due = []
    for want in wanted(service, now):
        row = asks.get((want.source, want.norad_id, want.target))
        if _due(row, want, now) and available(db, want.source, now):
            due.append((row["asked_at"] if row else "", want.request_id, want))
    wants = [want for _, _, want in sorted(due, key=lambda item: item[:2])]
    if available(db, "celestrak", now):
        asked = {row["group_name"]: row for row in db.query("SELECT * FROM allowlist_groups")}
        wants += [
            _group_want(group)
            for group in sorted(groups, key=lambda g: _group_order(g, asked.get(g)))
            if _group_due(asked.get(group), now)
        ]
    return wants[:limit]


def claim(db: Database, want: Want, now: datetime) -> bool:
    """Record the request as asked for, just before it is made, if the source may still be
    asked and no other process has asked for it meanwhile. Call it in a transaction."""
    if not available(db, want.source, now):
        return False
    if want.group:
        rows = db.query("SELECT * FROM allowlist_groups WHERE group_name = ?", (want.group,))
        if not _group_due(rows[0] if rows else None, now):
            return False
        db.execute(
            "INSERT INTO allowlist_groups (group_name, asked_at, status) VALUES (?, ?, NULL) "
            "ON CONFLICT (group_name) DO UPDATE SET asked_at = excluded.asked_at, status = NULL",
            (want.group, format_utc(now)),
            state=False,
        )
        return True
    rows = db.query(
        "SELECT * FROM orbit_asks WHERE source = ? AND norad_id = ? AND target = ?",
        (want.source, want.norad_id, want.target),
    )
    if not _due(rows[0] if rows else None, want, now):
        return False
    db.execute(
        "INSERT INTO orbit_asks (source, norad_id, target, asked_at, status) "
        "VALUES (?, ?, ?, ?, NULL) ON CONFLICT (source, norad_id, target) "
        "DO UPDATE SET asked_at = excluded.asked_at, status = NULL",
        (want.source, want.norad_id, want.target, format_utc(now)),
        state=False,
    )
    return True


def fetch_group(want: Want, opener: Callable) -> bytes:
    """One request for a CelesTrak group's GP data, or a SupGP source's data, CSV with gzip.
    Raises ``FetchError`` with the HTTP status, or None without an answer."""
    if allowlist.is_operator_source(want.group):
        return download_supgp("SOURCE", want.group, opener=opener)
    return download_gp("GROUP", want.group, opener=opener)


def fetch(want: Want, opener: Callable) -> list[dict[str, Any]]:
    """One request to the source: the object's element sets, each naming where it came
    from. Raises ``FetchError`` with the HTTP status, or None without an answer."""
    if want.target == SUPGP:
        return _fetch_supgp(want, opener)
    if want.source == "celestrak":
        body = download_gp("CATNR", str(want.norad_id), opener=opener)
        catalog = parse_catalog(body)
        others = sorted(set(catalog.sets) - {want.norad_id})
        records = catalog.sets.get(want.norad_id, [])
        if others or not records:
            raise FetchError(
                f"CelesTrak's answer for object {want.norad_id} holds the element sets of "
                f"{', '.join(map(str, others)) or 'no object'}",
                200,
            )
        url = build_url("CATNR", str(want.norad_id))
        return [{**r, SOURCE_KEY: {"service": "CelesTrak", "url": url}} for r in records]
    kind = "tle" if want.norad_id < TLE_LIMIT else "omm"
    nearest = satchecker.fetch_nearest(
        want.norad_id, parse_utc(want.target), kind=kind, opener=opener
    )
    return [nearest.record]


def _fetch_supgp(want: Want, opener: Callable) -> list[dict[str, Any]]:
    """The object's current sets of its operator's orbit from CelesTrak's SupGP, each
    naming its ``DATA_SOURCE``. Sets of other kinds, such as almanacs, are left out."""
    body = download_supgp("CATNR", str(want.norad_id), opener=opener)
    catalog = parse_catalog(body)
    others = sorted(set(catalog.sets) - {want.norad_id})
    if others or want.norad_id not in catalog.sets:
        raise FetchError(
            f"CelesTrak's SupGP answer for object {want.norad_id} holds the element sets of "
            f"{', '.join(map(str, others)) or 'no object'}",
            200,
        )
    url = supgp_url("CATNR", str(want.norad_id))
    return [
        {
            **sup.element_set.record,
            SOURCE_KEY: {
                "service": SUPGP_SERVICE,
                "url": url,
                "data_source": sup.data_source,
                "rms_km": sup.rms_km,
            },
        }
        for sup in sup_sets(catalog, want.norad_id)
        if sup.operator_orbit
    ]


def _record_status(db: Database, want: Want, status: int | None) -> None:
    if want.group:
        db.execute(
            "UPDATE allowlist_groups SET status = ? WHERE group_name = ?",
            (status, want.group),
            state=False,
        )
        return
    db.execute(
        "UPDATE orbit_asks SET status = ? WHERE source = ? AND norad_id = ? AND target = ?",
        (status, want.source, want.norad_id, want.target),
        state=False,
    )


def answered(db: Database, want: Want, now: datetime) -> None:
    """Record a 200 with element sets. Call it in a transaction."""
    _record_status(db, want, 200)
    db.execute(
        "UPDATE orbit_sources SET last_answer_at = ? WHERE source = ?",
        (format_utc(now), want.source),
        state=False,
    )


def stop(db: Database, want: Want, error: FetchError, now: datetime) -> None:
    """Stop asking the source, and say why, until a person resumes it. Call it in a
    transaction."""
    busy = error.status is None or error.status in (500, 503)
    db.execute(
        "UPDATE orbit_sources SET stopped_at = ?, stop_status = ?, stop_norad_id = ?, "
        "stop_reason = ?, not_before = ? WHERE source = ?",
        (
            format_utc(now),
            error.status,
            None if want.group else want.norad_id,
            str(error)[:500],
            format_utc(now + BUSY_WAIT) if busy else None,
            want.source,
        ),
        state=False,
    )
    _record_status(db, want, error.status)


def resume(
    db: Database, source: str, by: str, now: datetime, ask_again: tuple[int, ...] = ()
) -> None:
    """A person clears the stop. A wait after a 500 or a 503 still holds. ``ask_again``
    forgets what the source answered for these objects, a 404 included. Call it in a
    transaction."""
    if source not in SOURCES:
        raise ValueError(f"source must be one of {', '.join(SOURCES)}")
    db.execute(
        "UPDATE orbit_sources SET stopped_at = NULL, stop_status = NULL, stop_norad_id = NULL, "
        "stop_reason = NULL, resumed_at = ?, resumed_by = ? WHERE source = ?",
        (format_utc(now), by, source),
        state=False,
    )
    for norad in ask_again:
        db.execute(
            "DELETE FROM orbit_asks WHERE source = ? AND norad_id = ?",
            (source, norad),
            state=False,
        )


def status(db: Database, now: datetime, enabled: bool) -> dict[str, Any]:
    """What anyone may see of the fetching: whether a source is stopped, why and since
    when, and the objects without public data. ``status`` is ``stopped`` when any source
    is, ``off`` when the service does not fetch, and ``ok`` otherwise."""
    sources = {}
    for name, row in sorted(_sources(db).items()):
        waiting = row["not_before"] is not None and parse_utc(row["not_before"]) > now
        state = "stopped" if row["stopped_at"] else "waiting" if waiting else "ok"
        sources[name] = {
            "status": state,
            "stopped_at": row["stopped_at"],
            "http_status": row["stop_status"],
            "norad_id": row["stop_norad_id"],
            "reason": row["stop_reason"],
            "not_before": row["not_before"] if waiting else None,
            "last_answer_at": row["last_answer_at"],
            "resumed_at": row["resumed_at"],
        }
    missing = db.query(
        "SELECT norad_id, target FROM orbit_asks WHERE source = 'celestrak' AND status = 404 "
        "ORDER BY norad_id"
    )
    stopped = any(s["status"] == "stopped" for s in sources.values())
    return {
        "status": "off" if not enabled else "stopped" if stopped else "ok",
        "sources": sources,
        "objects_without_public_data": [int(r["norad_id"]) for r in missing if not r["target"]],
        "objects_without_supgp_data": [int(r["norad_id"]) for r in missing if r["target"] == SUPGP],
    }

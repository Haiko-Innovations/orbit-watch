"""Past reference orbits from the IAU CPS's SatChecker (decision P5-03).

CelesTrak gives only current element sets by URL. SatChecker keeps the element sets of
Space-Track and CelesTrak and gives the one nearest a given time, without an account
(https://satchecker.readthedocs.io/en/latest/tools_data_access.html, version 1.9.0,
read 2026-11-20):

* ``get-nearest-tle`` for the past, since TLEs "remain the record for historical dates";
* ``get-nearest-omm`` where OMM data exists;
* ``get-omm-data`` for every OMM of one object in a period, with when SatChecker collected each
  and from where ("celestrak" or "spacetrack"): the GP sets that were available at a time
  (decision P6-02, read 2026-11-23).

This module makes one request per call and never retries. A caller that makes several
requests waits ``PAUSE_S`` between them and stops at the first answer that is not 200
(``orbit_watch.orbit_cache``). A TLE is converted to OMM form with sgp4's exporter, so the
catalogue reads only OMM; TLEs hold catalogue numbers below 100,000 only.

Acknowledgement that SatChecker asks for: "This research made use of data and/or services
provided by the International Astronomical Union Centre for the Protection of the Dark and
Quiet Sky (IAU CPS) SatHub."
"""

from __future__ import annotations

import http.client
import json
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from sgp4 import exporter
from sgp4.api import Satrec

from orbit_watch.canonical import dumps_compact, sha256_bytes
from orbit_watch.catalog import REQUIRED_OMM_FIELDS, SOURCE_KEY
from orbit_watch.fetch import USER_AGENT, FetchError, read_body

BASE_URL = "https://satchecker.cps.iau.org/tools/"
SERVICE = "IAU CPS SatChecker"
KINDS = ("tle", "omm")
PAUSE_S = 2.0  # between two requests to SatChecker
MAX_BYTES = 1024 * 1024
MAX_PERIOD_DAYS = 31  # one request for a month of one object's sets at most
UNIX_EPOCH_JD = 2440587.5


class SatCheckerError(FetchError):
    """SatChecker answered with something other than one element set, or did not answer;
    stop asking. ``status`` is the answer's HTTP status, or None without an answer."""


@dataclass(frozen=True)
class NearestSet:
    """One element set from SatChecker: its answer as received, and the catalogue record."""

    norad_id: int
    kind: str
    answer: bytes  # the body SatChecker sent, kept as it was
    record: dict[str, Any]  # OMM fields, with ``source`` naming where they came from
    sha256: str  # of the original element set: the TLE's two lines, or the OMM fields
    epoch: str


def julian_date(when: datetime) -> float:
    return when.timestamp() / 86400 + UNIX_EPOCH_JD


def nearest_url(kind: str, norad_id: int, when: datetime) -> str:
    if kind not in KINDS:
        raise ValueError(f"kind must be one of {', '.join(KINDS)}")
    query = urllib.parse.urlencode(
        {"id": str(norad_id), "id_type": "catalog", "epoch": f"{julian_date(when):.8f}"}
    )
    return f"{BASE_URL}get-nearest-{kind}/?{query}"


def tle_sha256(line1: str, line2: str) -> str:
    return sha256_bytes(f"{line1.rstrip()}\n{line2.rstrip()}\n".encode("ascii"))


def omm_sha256(elements: dict[str, Any]) -> str:
    return sha256_bytes(dumps_compact(elements).encode("utf-8"))


def history_url(norad_id: int, start: datetime, end: datetime) -> str:
    query = urllib.parse.urlencode(
        {
            "id": str(norad_id),
            "id_type": "catalog",
            "start_date_jd": f"{julian_date(start):.8f}",
            "end_date_jd": f"{julian_date(end):.8f}",
        }
    )
    return f"{BASE_URL}get-omm-data/?{query}"


def download_nearest(
    norad_id: int,
    when: datetime,
    *,
    kind: str = "tle",
    opener: Callable = urllib.request.urlopen,
) -> bytes:
    """One request for the element set of ``norad_id`` nearest ``when``, never retried; the
    answer's body if it is 200. Raises ``SatCheckerError`` otherwise."""
    return download(nearest_url(kind, norad_id, when), opener=opener)


def download(url: str, *, opener: Callable = urllib.request.urlopen) -> bytes:
    """One request to SatChecker, never retried; the answer's body if it is 200."""
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
        detail = exc.read(300).decode("utf-8", errors="replace").strip()
        raise SatCheckerError(
            f"SatChecker answered HTTP {exc.code} for {url}: {detail} (not retrying)", exc.code
        ) from None
    except urllib.error.URLError as exc:
        raise SatCheckerError(f"could not reach SatChecker: {exc.reason}") from None
    except (OSError, http.client.HTTPException) as exc:
        raise SatCheckerError(f"no answer from SatChecker: {exc or type(exc).__name__}") from None
    except FetchError as exc:
        raise SatCheckerError(str(exc), 200) from None
    if status != 200:
        raise SatCheckerError(f"SatChecker answered HTTP {status} for {url} (not retrying)", status)
    return body


def fetch_nearest(
    norad_id: int,
    when: datetime,
    *,
    kind: str = "tle",
    opener: Callable = urllib.request.urlopen,
) -> NearestSet:
    """The element set of ``norad_id`` nearest ``when``: one request, never retried."""
    body = download_nearest(norad_id, when, kind=kind, opener=opener)
    try:
        return parse_answer(body, norad_id, kind, endpoint=f"get-nearest-{kind}")
    except SatCheckerError as exc:
        exc.status = 200
        raise


def parse_answer(body: bytes, norad_id: int, kind: str, *, endpoint: str) -> NearestSet:
    """Read a SatChecker answer with one element set and convert it to a catalogue record."""
    try:
        document = json.loads(body.decode("utf-8"))
        answer = document[0] if isinstance(document, list) else document
        data = answer["orbital_data"]
        version = str(answer.get("version", ""))
    except (ValueError, UnicodeDecodeError, LookupError, TypeError):
        raise SatCheckerError(
            f"SatChecker's answer is not the expected JSON: {body[:200]!r}"
        ) from None
    if not isinstance(data, list) or len(data) != 1 or not isinstance(data[0], dict):
        count = len(data) if isinstance(data, list) else "no"
        raise SatCheckerError(f"SatChecker returned {count} element sets for {norad_id}, not one")
    item = data[0]
    source: dict[str, Any] = {
        "service": SERVICE,
        "version": version,
        "endpoint": endpoint,
        "data_source": str(item.get("data_source", "")),
        "date_collected": str(item.get("date_collected", "")),
    }
    if kind == "tle":
        line1, line2 = str(item.get("tle_line1", "")), str(item.get("tle_line2", ""))
        try:
            satrec = Satrec.twoline2rv(line1, line2)
        except (ValueError, IndexError) as exc:
            raise SatCheckerError(
                f"SatChecker's TLE for {norad_id} cannot be read: {exc}"
            ) from None
        if satrec.error:
            raise SatCheckerError(f"SatChecker's TLE for {norad_id} cannot be read")
        name = str(item.get("satellite_name") or norad_id)
        record = exporter.export_omm(satrec, name)
        source["tle_line1"], source["tle_line2"] = line1, line2
        digest = tle_sha256(line1, line2)
    elif kind == "omm":
        record, digest = _omm_elements(item, norad_id)
    else:
        raise ValueError(f"kind must be one of {', '.join(KINDS)}")
    _check_object(record, norad_id)
    source["original_sha256"] = digest
    record[SOURCE_KEY] = source
    return NearestSet(norad_id, kind, body, record, digest, str(record["EPOCH"]))


def _omm_elements(item: dict[str, Any], norad_id: int) -> tuple[dict[str, Any], str]:
    elements = item.get("orbital_elements")
    if not isinstance(elements, dict):
        raise SatCheckerError(f"SatChecker's OMM for {norad_id} has no orbital elements")
    missing = [f for f in REQUIRED_OMM_FIELDS if f not in elements]
    if missing:
        raise SatCheckerError(
            f"SatChecker's OMM for {norad_id} lacks OMM field(s): {', '.join(missing)}"
        )
    return dict(elements), omm_sha256(elements)


def _check_object(record: dict[str, Any], norad_id: int) -> None:
    try:
        delivered = int(record["NORAD_CAT_ID"])
    except (TypeError, ValueError):
        raise SatCheckerError("SatChecker's element set has no catalogue number") from None
    if delivered != norad_id:
        raise SatCheckerError(
            f"SatChecker returned an element set of object {delivered}, not {norad_id}"
        )


def fetch_history(
    norad_id: int,
    start: datetime,
    end: datetime,
    *,
    opener: Callable = urllib.request.urlopen,
) -> list[NearestSet]:
    """Every OMM that SatChecker keeps of ``norad_id`` with an epoch from ``start`` to ``end``:
    one request, never retried. Sets that CelesTrak and Space-Track both gave appear once, with
    the earlier collection time. Oldest epoch first."""
    if end <= start:
        raise ValueError("the period must end after it starts")
    if (end - start).total_seconds() > MAX_PERIOD_DAYS * 86400:
        raise ValueError(f"ask for at most {MAX_PERIOD_DAYS} days at a time")
    body = download(history_url(norad_id, start, end), opener=opener)
    try:
        return parse_history(body, norad_id)
    except SatCheckerError as exc:
        exc.status = 200
        raise


def parse_history(body: bytes, norad_id: int) -> list[NearestSet]:
    """Read a ``get-omm-data`` answer: ``{"count", "data": [...], "source", "version"}``."""
    try:
        document = json.loads(body.decode("utf-8"))
        items = document["data"]
        version = str(document.get("version", ""))
    except (ValueError, UnicodeDecodeError, LookupError, TypeError):
        raise SatCheckerError(
            f"SatChecker's answer is not the expected JSON: {body[:200]!r}"
        ) from None
    if not isinstance(items, list) or not all(isinstance(item, dict) for item in items):
        raise SatCheckerError(f"SatChecker's answer for {norad_id} has no list of element sets")
    kept: dict[str, NearestSet] = {}
    for item in items:
        record, digest = _omm_elements(item, norad_id)
        _check_object(record, norad_id)
        collected = str(item.get("date_collected", ""))
        if digest in kept and kept[digest].record[SOURCE_KEY]["date_collected"] <= collected:
            continue
        record[SOURCE_KEY] = {
            "service": SERVICE,
            "version": version,
            "endpoint": "get-omm-data",
            "data_source": str(item.get("data_source", "")),
            "date_collected": collected,
            "original_sha256": digest,
        }
        kept[digest] = NearestSet(norad_id, "omm", b"", record, digest, str(record["EPOCH"]))
    return sorted(kept.values(), key=lambda s: (s.epoch, s.sha256))

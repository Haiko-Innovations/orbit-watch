"""Operators' own orbits from CelesTrak's supplemental GP (decision P6-03).

CelesTrak's supplemental GP element sets (SupGP) are "derived directly from owner/operator-
supplied orbital data": SpaceX's public Starlink ephemerides; the ephemerides of OneWeb,
Kuiper, AST SpaceMobile and others on Space-Track, with each operator's permission; Planet's;
NASA's ISS ephemeris in 6-hour segments; and the laser-ranging predictions (CPF)
(https://celestrak.org/NORAD/elements/supplemental/, read 2026-11-23).

How to ask (https://celestrak.org/NORAD/documentation/sup-gp-queries.php, updated 2026-05-26):
``sup-gp.php?{CATNR|SOURCE|...}=value&FORMAT=csv``. Each set has the OMM fields, the ``RMS`` of
CelesTrak's fit to the operator's data in kilometres, and a ``DATA_SOURCE`` such as ``AST-E``
or ``CPF``. One object may have several sets: several prediction centres, or several epochs.
"SupGP data is fitted from the current epoch forward, as opposed to GP data where that is fit to
past observations." CelesTrak keeps no history of SupGP.

CelesTrak's usage policy (updated 2026-11-16) applies as for GP: "For SupGP data ... please use a
2-hour minimum, as well", CSV, compressed, and stop at the first answer that is not 200. So this
module, like ``orbit_watch.fetch``, makes one request per call, never retries, and does not
download the same file again within two hours unless forced. Nothing it fetches is committed
(decisions D-06 and P5-05).
"""

from __future__ import annotations

import time
import urllib.parse
import urllib.request
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from orbit_watch.catalog import Catalog, ElementSet, parse_catalog
from orbit_watch.fetch import FetchError, download_omm_csv, save_once

SUPGP_URL = "https://celestrak.org/NORAD/elements/supplemental/sup-gp.php"
QUERY_KEYS = ("CATNR", "SOURCE")
SERVICE = "CelesTrak SupGP"
# DATA_SOURCE values whose sets are fitted to an operator's ephemeris or state vectors, or to
# the laser-ranging predictions: "-E" (ephemeris), "-RE" (rapid ephemeris), "-SV" (state
# vectors) and "CPF". Almanacs ("-A"), 11-parameter data ("-11P") and TLEs passed on as they
# came ("-TLE") are not an operator's precise orbit.
OPERATOR_SUFFIXES = ("-E", "-RE", "-SV")
OPERATOR_EXACT = ("CPF",)


def is_operator_orbit(data_source: str) -> bool:
    """Whether a SupGP set of this ``DATA_SOURCE`` is fitted to an operator's precise orbit."""
    return data_source in OPERATOR_EXACT or data_source.endswith(OPERATOR_SUFFIXES)


def build_url(key: str, value: str) -> str:
    if key not in QUERY_KEYS:
        raise ValueError(f"query must be one of {', '.join(QUERY_KEYS)}")
    return SUPGP_URL + "?" + urllib.parse.urlencode({key: value, "FORMAT": "csv"})


def download_supgp(key: str, value: str, *, opener: Callable = urllib.request.urlopen) -> bytes:
    """One request for SupGP data (OMM CSV), never retried. Raises ``FetchError`` when the
    answer is not 200 with element sets that each name their ``DATA_SOURCE``."""
    body = download_omm_csv(build_url(key, value), f"SupGP data for {key}={value}", opener=opener)
    catalog = parse_catalog(body)
    unnamed = [
        norad_id
        for norad_id, records in catalog.sets.items()
        if any(not str(record.get("DATA_SOURCE") or "").strip() for record in records)
    ]
    if unnamed:
        raise FetchError(
            f"CelesTrak's SupGP answer for {key}={value} has element sets without a "
            f"DATA_SOURCE (object {unnamed[0]}); not using it",
            200,
        )
    return body


def fetch_supgp(
    key: str,
    value: str,
    output: Path,
    *,
    force: bool = False,
    opener: Callable = urllib.request.urlopen,
    now: Callable[[], float] = time.time,
) -> str:
    """Download SupGP data (OMM CSV) for one query to ``output``. Returns a status message."""
    return save_once(
        build_url(key, value),
        output,
        lambda: download_supgp(key, value, opener=opener),
        what="SupGP data",
        force=force,
        now=now,
    )


@dataclass(frozen=True)
class SupSet:
    """One SupGP element set: the set, where CelesTrak took it from, and how well it fits."""

    element_set: ElementSet
    data_source: str
    rms_km: float | None  # CelesTrak's fit to the operator's data

    @property
    def operator_orbit(self) -> bool:
        return is_operator_orbit(self.data_source)


def sup_sets(catalog: Catalog, norad_id: int) -> list[SupSet]:
    """Every SupGP set of one object, oldest epoch first."""
    found = []
    for element_set in catalog.element_sets(norad_id):
        record = element_set.record
        try:
            rms = float(record["RMS"]) if str(record.get("RMS", "")).strip() else None
        except ValueError:
            rms = None
        found.append(SupSet(element_set, str(record.get("DATA_SOURCE", "")).strip(), rms))
    return found

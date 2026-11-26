"""Build a target policy (allow-list) from public GP data.

Phase 0 rule: requests may only target civilian objects. The allow-list is
the union of the objects in the GP files you include (for example CelesTrak
groups such as "cubesat", "amateur", "education" or "science"), minus the
objects in the GP files you exclude (for example the "military" group), minus
objects whose names match conservative patterns for military, intelligence
and government security payloads. Objects that are not in the public GP
catalogue (classified objects) can never be on the list.

The service builds its list the same way (phase 5, step 5.4; decisions P5-08 and D-49):
from CelesTrak's small civilian groups, which its follower fetches at most once a day,
minus the excluded groups and the name patterns, plus the objects an administrator adds
with a public reason, to which the name patterns apply too. ``combine`` does this.

Since step 6.2 (decisions P6-04 and D-62) the list also holds the objects whose operators
publish their orbits: those of CelesTrak's small SupGP sources (``OPERATOR_SOURCES``), read
once a day as the groups are, and Starlink objects that an administrator adds one at a time
after one SupGP query shows SpaceX's ephemeris for them. The name patterns apply to them as
to every other object, and leave out the navigation satellites of GPS, GLONASS and BeiDou
and the dual-use satellites that the laser-ranging list holds.
"""

from __future__ import annotations

import re
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from typing import Any

from orbit_watch.canonical import sha256_bytes
from orbit_watch.catalog import parse_catalog
from orbit_watch.documents import TargetPolicy
from orbit_watch.supgp import is_operator_orbit

# Conservative name patterns. A civilian object wrongly excluded is a small
# loss; a military object wrongly included is not acceptable.
DEFAULT_EXCLUDED_NAME_PATTERNS = (
    r"^USA[ -]?\d",
    r"\bNROL\b",
    r"\bNOSS\b",
    r"STARSHIELD",
    r"^COSMOS\b",
    r"^KOSMOS\b",
    r"^YAOGAN\b",
    r"^SHIYAN\b",
    r"^SJ-",
    r"^TJS\b",
    r"^IGS\b",
    r"^OFEQ\b",
    r"^SAR-LUPE\b",
    r"^SARAH\b",
    r"^CSO-",
    r"^HELIOS\b",
    r"^MUOS\b",
    r"^WGS\b",
    r"^AEHF\b",
    r"^SBIRS\b",
    r"^DMSP\b",
    r"^MILSTAR\b",
    # Navigation systems run by armed forces or for them (P6-04, D-62): GPS, GLONASS and
    # BeiDou. CelesTrak's names are such as "GPS BIII-6 (PRN 28)", "COSMOS 2569
    # (GLONASS-K2)" and "BEIDOU-3 M1"; the laser-ranging list's are "GPS082",
    # "GLONASS128" and "BEIDOU3M1".
    r"^GPS",
    r"\bNAVSTAR\b",
    r"GLONASS",
    r"^BEIDOU",
    # Dual-use satellites of the laser-ranging list (D-62): PAZ, which Spain's Ministry of
    # Defence owns and is the main customer of, and QZS-6 and QZS-7, which carry the US
    # Space Force's space domain awareness sensors.
    r"^PAZ\b",
    r"^QZS-?[67]\b",
)

# CelesTrak's groups that the service's list is built from (P5-08), as named on
# https://celestrak.org/NORAD/elements/ (read on 2026-11-21). Large groups, such as
# ``starlink`` and ``active``, are never fetched: an administrator adds such an object.
INCLUDED_GROUPS = ("science", "education", "amateur", "cubesat")
EXCLUDED_GROUPS = ("military", "radar")

# CelesTrak's SupGP sources whose operators publish their orbits (P6-04, D-62), read once a
# day like the groups: AST SpaceMobile's, the laser-ranging predictions, NASA's ISS
# ephemeris, Kuiper's, OneWeb's and Planet's. The names are the SOURCE values of
# https://celestrak.org/NORAD/documentation/sup-gp-queries.php (read on 2026-11-24).
# Starlink's list is large, so its objects are added one at a time with SpaceX's ephemeris
# (``ADDED_OPERATOR_SOURCES``). GPS's and GLONASS's sources are never read.
OPERATOR_SOURCES = ("AST-E", "CPF", "ISS-E", "Kuiper-E", "OneWeb-E", "Planet-E")
ADDED_OPERATOR_SOURCES = ("SpaceX-E",)

# What the follower fetches once a day: the excluded groups first.
GROUPS = EXCLUDED_GROUPS + INCLUDED_GROUPS + OPERATOR_SOURCES
INCLUDED = INCLUDED_GROUPS + OPERATOR_SOURCES  # count only once the excluded ones are in


def _patterns() -> list[re.Pattern[str]]:
    return [re.compile(p, re.IGNORECASE) for p in DEFAULT_EXCLUDED_NAME_PATTERNS]


# SGP4 and the TLE's Alpha-5 encoding take catalogue numbers up to 339999. CelesTrak gives
# objects not yet catalogued, such as those of a launch days ago, temporary numbers of nine
# digits; they cannot be propagated here, so they are left off the list (D-65).
MAX_CATALOGUE_NUMBER = 339_999


def is_operator_source(name: str) -> bool:
    """Whether a name of ``GROUPS`` is one of CelesTrak's SupGP sources, not a GP group."""
    return name in OPERATOR_SOURCES


def plain_name(name: str) -> str:
    """A SupGP object's name without the prediction centre that the laser-ranging list
    adds, as in "LAGEOS1 [DGF]"."""
    return re.sub(r"\s*\[[^\]]*\]\s*$", "", name).strip() or name


def operator_members(body: bytes) -> dict[int, str]:
    """The objects of one SupGP source's answer that have an operator's orbit, by name,
    read from the sets' fields without building their orbits. Temporary catalogue numbers,
    above ``MAX_CATALOGUE_NUMBER``, are left out."""
    catalog = parse_catalog(body)
    return {
        norad: plain_name(catalog.name(norad))
        for norad in sorted(catalog.sets)
        if norad <= MAX_CATALOGUE_NUMBER
        and any(
            is_operator_orbit(str(record.get("DATA_SOURCE", "")).strip())
            for record in catalog.sets[norad]
        )
    }


def excluded_name(name: str) -> bool:
    """Whether a name matches the patterns for military, intelligence and government
    security payloads."""
    return any(p.search(name) for p in _patterns())


def build_policy(
    include: list[bytes],
    exclude: list[bytes],
    *,
    use_default_patterns: bool = True,
    extra_patterns: tuple[str, ...] = (),
) -> dict:
    patterns = [
        re.compile(p, re.IGNORECASE)
        for p in (DEFAULT_EXCLUDED_NAME_PATTERNS if use_default_patterns else ()) + extra_patterns
    ]
    candidates: dict[int, str] = {}
    built_from = []
    for data in include:
        catalog = parse_catalog(data)
        built_from.append(
            {"role": "include", "sha256": sha256_bytes(data), "records": len(catalog.records)}
        )
        for norad_id in catalog.records:
            candidates[norad_id] = catalog.name(norad_id)
    excluded_ids: set[int] = set()
    for data in exclude:
        catalog = parse_catalog(data)
        built_from.append(
            {"role": "exclude", "sha256": sha256_bytes(data), "records": len(catalog.records)}
        )
        excluded_ids.update(catalog.records)
    allow = []
    dropped_by_name = 0
    for norad_id in sorted(candidates):
        name = candidates[norad_id]
        if norad_id in excluded_ids:
            continue
        if any(p.search(name) for p in patterns):
            dropped_by_name += 1
            continue
        allow.append({"norad_id": norad_id, "name": name})
    return {
        "format": "orbit-watch/target-policy",
        "format_version": "1.0",
        "simulated": any(parse_catalog(d).simulated for d in include),
        "description": (
            f"Built by orbit-watch allowlist build from {len(include)} included and "
            f"{len(exclude)} excluded GP file(s); {len(allow)} objects allowed, "
            f"{len(candidates) - len(allow) - dropped_by_name} removed by exclusion files and "
            f"{dropped_by_name} by name patterns."
        ),
        "built_from": built_from,
        "allow": allow,
    }


@dataclass(frozen=True)
class Target:
    """An object on the service's list, and why it is there."""

    norad_id: int
    name: str | None
    simulated: bool
    groups: tuple[str, ...] = ()  # CelesTrak's groups that hold it
    reason: str | None = None  # an administrator's addition: the public reason
    added_at: str | None = None
    operator_orbits: tuple[str, ...] = ()  # SupGP sources with its operator's orbit

    @property
    def source(self) -> str:
        if self.reason is not None:
            return "administrator"
        return "celestrak" if self.groups or self.operator_orbits else "service"

    def public(self) -> dict[str, Any]:
        view: dict[str, Any] = {
            "norad_id": self.norad_id,
            "name": self.name,
            "simulated": self.simulated,
            "source": self.source,
        }
        if self.groups:
            view["groups"] = list(self.groups)
        if self.operator_orbits:
            view["operator_orbits"] = list(self.operator_orbits)
        if self.reason is not None:
            view["reason"] = self.reason
            view["added_at"] = self.added_at
        return view


def combine(
    own: bytes,
    groups: Mapping[str, Mapping[int, str]],
    additions: Mapping[int, Mapping[str, Any]],
    other_names: Mapping[int, Iterable[str]] | None = None,
) -> dict[int, Target]:
    """The service's list (D-49, D-62): its own list (``own``, a target policy) as it is,
    plus the objects of CelesTrak's included ``groups`` and SupGP sources and the
    administrator's ``additions``, minus the objects of the excluded groups and those with a
    name that matches the patterns. ``other_names`` are more names of an object, such as
    those of its stored element sets: the patterns apply to them too. The objects of the
    own list are SIMULATED when it is. The included groups and sources count only once
    every excluded group has been fetched, so that an object of both is never allowed in
    between."""
    policy = TargetPolicy.parse(own)
    targets = {
        norad: Target(norad, name, policy.simulated) for norad, name in policy.allowed.items()
    }
    excluded = {norad for group in EXCLUDED_GROUPS for norad in groups.get(group, {})}
    patterns = _patterns()
    other_names = other_names or {}

    def refused(norad: int, name: str) -> bool:
        names = [name, *other_names.get(norad, ())]
        return norad in excluded or any(p.search(n) for p in patterns for n in names)

    found: dict[int, tuple[list[str], list[str]]] = {}
    for group in INCLUDED if all(g in groups for g in EXCLUDED_GROUPS) else ():
        for norad, name in groups.get(group, {}).items():
            names, held_by = found.setdefault(norad, ([], []))
            names.append(name)
            held_by.append(group)
    for norad, (names, held_by) in found.items():
        if norad in targets or any(refused(norad, n) for n in names):
            continue
        targets[norad] = Target(
            norad,
            names[0],  # a GP group's name before a SupGP source's
            False,
            groups=tuple(g for g in held_by if not is_operator_source(g)),
            operator_orbits=tuple(g for g in held_by if is_operator_source(g)),
        )
    for norad, added in additions.items():
        if norad in targets and targets[norad].source == "service":
            continue
        group_names = found.get(norad, ([], []))[0]
        if any(refused(norad, n) for n in [added["name"], *group_names]):
            continue
        held = targets.get(norad)
        operator = added.get("operator_source")
        operator_orbits = held.operator_orbits if held else ()
        if operator and operator not in operator_orbits:
            operator_orbits = (*operator_orbits, operator)
        targets[norad] = Target(
            norad,
            held.name if held else added["name"],
            False,
            groups=held.groups if held else (),
            reason=added["reason"],
            added_at=added["added_at"],
            operator_orbits=operator_orbits,
        )
    return dict(sorted(targets.items()))

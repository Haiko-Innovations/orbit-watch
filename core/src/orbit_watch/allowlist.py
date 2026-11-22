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
"""

from __future__ import annotations

import re
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from typing import Any

from orbit_watch.canonical import sha256_bytes
from orbit_watch.catalog import parse_catalog
from orbit_watch.documents import TargetPolicy

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
)

# CelesTrak's groups that the service's list is built from (P5-08), as named on
# https://celestrak.org/NORAD/elements/ (read on 2026-11-21). Large groups, such as
# ``starlink`` and ``active``, are never fetched: an administrator adds such an object.
INCLUDED_GROUPS = ("science", "education", "amateur", "cubesat")
EXCLUDED_GROUPS = ("military", "radar")
GROUPS = EXCLUDED_GROUPS + INCLUDED_GROUPS  # the excluded ones are fetched first


def _patterns() -> list[re.Pattern[str]]:
    return [re.compile(p, re.IGNORECASE) for p in DEFAULT_EXCLUDED_NAME_PATTERNS]


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

    @property
    def source(self) -> str:
        if self.reason is not None:
            return "administrator"
        return "celestrak" if self.groups else "service"

    def public(self) -> dict[str, Any]:
        view: dict[str, Any] = {
            "norad_id": self.norad_id,
            "name": self.name,
            "simulated": self.simulated,
            "source": self.source,
        }
        if self.groups:
            view["groups"] = list(self.groups)
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
    """The service's list (D-49): its own list (``own``, a target policy) as it is, plus
    the objects of CelesTrak's included ``groups`` and the administrator's ``additions``,
    minus the objects of the excluded groups and those with a name that matches the
    patterns. ``other_names`` are more names of an object, such as those of its stored
    element sets: the patterns apply to them too. The objects of the own list are SIMULATED
    when it is. The included groups count only once every excluded group has been
    fetched, so that an object of both is never allowed in between."""
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

    found: dict[int, tuple[str, list[str]]] = {}
    for group in INCLUDED_GROUPS if all(g in groups for g in EXCLUDED_GROUPS) else ():
        for norad, name in groups.get(group, {}).items():
            found.setdefault(norad, (name, []))[1].append(group)
    for norad, (name, held_by) in found.items():
        if norad not in targets and not refused(norad, name):
            targets[norad] = Target(norad, name, False, groups=tuple(held_by))
    for norad, added in additions.items():
        if norad in targets and targets[norad].source == "service":
            continue
        if refused(norad, added["name"]):
            continue
        held_by = targets[norad].groups if norad in targets else ()
        targets[norad] = Target(
            norad,
            targets[norad].name if norad in targets else added["name"],
            False,
            groups=held_by,
            reason=added["reason"],
            added_at=added["added_at"],
        )
    return dict(sorted(targets.items()))

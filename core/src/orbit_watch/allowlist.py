"""Build a target policy (allow-list) from public GP data.

Phase 0 rule: requests may only target civilian objects. The allow-list is
the union of the objects in the GP files you include (for example CelesTrak
groups such as "cubesat", "amateur", "education" or "science"), minus the
objects in the GP files you exclude (for example the "military" group), minus
objects whose names match conservative patterns for military, intelligence
and government security payloads. Objects that are not in the public GP
catalogue (classified objects) can never be on the list.
"""

from __future__ import annotations

import re

from orbit_watch.canonical import sha256_bytes
from orbit_watch.catalog import parse_catalog

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

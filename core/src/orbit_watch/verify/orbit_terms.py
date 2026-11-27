"""The orbit term of method 3.0.0 (phase 6, step 6.3, decisions P6-05, D-67 and D-68).

Method 2.1.0 allowed every reference orbit the same 5 km, in every direction, up to seven
days from its epoch (D-08). Method 3.0.0 allows each element set what step 6.1 measured for
sets like it: by the set's kind (an operator's orbit, a laser-ranging prediction or a GP
set), the object's orbit class and the set's age, and separately radially, along the track
and across it (D-67, choice a).

Each value is the 90th percentile of ``docs/reference-orbit-accuracy.md`` for its row,
rounded up: to the next whole kilometre along the track, and to the next half kilometre
radially and across it. Bins measured in finer steps are joined by their largest 90th
percentile. Past a row's last age the residual check is inconclusive, as past 2.1.0's
seven days (choice b). Orbits that were not measured keep method 2.1.0's 5 km and seven
days (choice c).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from orbit_watch.supgp import is_operator_orbit

DASH = "\u2013"  # an en dash, in ranges
LASER_RANGING = "CPF"

KINDS = {
    "operator": "an operator's orbit via CelesTrak SupGP",
    "laser-ranging": "a laser-ranging prediction via CelesTrak SupGP",
    "gp": "a GP set",
    "not-measured": "an orbit class not measured in step 6.1",
}

# (kind, orbit class) -> rows of (oldest age in days, radial, in-track, cross-track km).
# A set's age is the largest distance of an observation from its epoch.
TERMS: dict[tuple[str, str], tuple[tuple[float, float, float, float], ...]] = {
    # Operators' sets up to a day old (D-61, D-66): AST SpaceMobile, Kuiper, OneWeb, Planet.
    ("operator", "LEO"): ((1.0, 0.5, 2.0, 0.5),),
    # Laser-ranging predictions up to three days old (D-66).
    ("laser-ranging", "LEO"): ((3.0, 0.5, 2.0, 0.5),),
    ("laser-ranging", "MEO"): ((3.0, 0.5, 1.0, 0.5),),
    ("laser-ranging", "GEO"): ((3.0, 1.5, 3.0, 1.5),),
    # GP sets of every source, against operators' orbits (D-60, D-67).
    ("gp", "LEO"): ((1.0, 0.5, 4.0, 0.5), (2.0, 0.5, 9.0, 0.5), (3.0, 0.5, 16.0, 0.5)),
    ("gp", "MEO"): ((3.0, 1.0, 5.0, 0.5), (7.0, 1.5, 7.0, 0.5)),
    ("gp", "GEO"): (
        (1.0, 2.0, 4.0, 4.5),
        (2.0, 2.0, 5.0, 5.5),
        (3.0, 2.5, 8.0, 7.0),
        (5.0, 3.0, 12.0, 8.5),
    ),
    # Not measured: method 2.1.0's values (D-08), in every direction.
    ("not-measured", "HEO"): ((7.0, 5.0, 5.0, 5.0),),
}


@dataclass(frozen=True)
class OrbitTerm:
    kind: str
    orbit: str
    age_days: str  # the row's ages, as "1-2" with an en dash
    radial_km: float
    in_track_km: float
    cross_track_km: float

    def public(self) -> dict[str, Any]:
        return {
            "kind": self.kind,
            "description": KINDS[self.kind],
            "orbit_class": self.orbit,
            "age_days": self.age_days,
            "radial_km": self.radial_km,
            "in_track_km": self.in_track_km,
            "cross_track_km": self.cross_track_km,
        }


def orbit_class(record: dict[str, Any]) -> str:
    """LEO, MEO, GEO or HEO, from the element set's mean motion and eccentricity."""
    mean_motion = float(record["MEAN_MOTION"])  # revolutions a day
    eccentricity = float(record["ECCENTRICITY"])
    if eccentricity >= 0.25:
        return "HEO"
    if mean_motion >= 11.25:
        return "LEO"
    if 0.9 <= mean_motion <= 1.1:
        return "GEO"
    return "MEO"


def kinds_for(record: dict[str, Any]) -> list[str]:
    """The kinds whose terms may apply to a set, most specific first. An operator's set past
    its own ages is taken as a GP set: two to three days old, those of satellites that
    manoeuvre aged like GP (D-61)."""
    orbit = orbit_class(record)
    data_source = str(record.get("DATA_SOURCE") or "").strip()
    kinds = []
    if data_source and is_operator_orbit(data_source):
        kinds.append("laser-ranging" if data_source == LASER_RANGING else "operator")
    kinds.append("gp" if ("gp", orbit) in TERMS else "not-measured")
    return [kind for kind in kinds if (kind, orbit) in TERMS]


def _label(rows: tuple, index: int) -> str:
    low = 0.0 if index == 0 else rows[index - 1][0]
    return f"{low:g}{DASH}{rows[index][0]:g}"


def term_for(record: dict[str, Any], age_days: float, simulated: bool = False) -> OrbitTerm | None:
    """The term for a set at an age, or None when the set is too old for every kind that
    applies. A SIMULATED set is the truth its observations are computed from, so its age
    does not limit it: past the last row it keeps the last row's values."""
    orbit = orbit_class(record)
    kinds = kinds_for(record)
    for kind in kinds:
        rows = TERMS[(kind, orbit)]
        for index, (oldest, radial, in_track, cross) in enumerate(rows):
            if age_days <= oldest:
                return OrbitTerm(kind, orbit, _label(rows, index), radial, in_track, cross)
    if simulated:
        kind = kinds[-1]
        rows = TERMS[(kind, orbit)]
        oldest, radial, in_track, cross = rows[-1]
        return OrbitTerm(kind, orbit, _label(rows, len(rows) - 1), radial, in_track, cross)
    return None


def oldest_age(record: dict[str, Any]) -> float:
    """The largest age any kind that applies to the set allows."""
    orbit = orbit_class(record)
    return max(TERMS[(kind, orbit)][-1][0] for kind in kinds_for(record))


def table() -> list[dict[str, Any]]:
    """Every row, for the method's parameters in a report."""
    rows = []
    for (kind, orbit), values in TERMS.items():
        for index, (_, radial, in_track, cross) in enumerate(values):
            rows.append(OrbitTerm(kind, orbit, _label(values, index), radial, in_track, cross))
    return [row.public() for row in rows]

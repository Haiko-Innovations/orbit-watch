"""Observation station simulator (SIMULATED data only).

Produces positional observations of an object from public or synthetic GP
orbit data with SGP4 (through Skyfield), and adds configurable noise, timing
error, clock offset and missing observations. Everything it produces is
marked ``"simulated": true``.

Determinism: the simulator uses ``random.Random(seed)`` and draws normal
deviates with the Box-Muller transform built only on ``random()``, whose
sequence Python guarantees across versions. The same inputs and seed give
the same observations.

Not modelled (yet): illumination (sunlit object, dark sky), weather,
atmospheric refraction, stellar aberration, light travel time and
star-catalogue errors.
"""

from __future__ import annotations

import json
import math
import random
from dataclasses import dataclass
from datetime import datetime
from importlib import resources
from pathlib import Path

from orbit_watch import __version__
from orbit_watch.catalog import Catalog, timescale
from orbit_watch.formats.owjson import FormatError
from orbit_watch.geometry import predict, topos
from orbit_watch.model import Observation, ObservationSet, Station, Target
from orbit_watch.schema import validate
from orbit_watch.timeutil import add_seconds

ARCSEC_PER_DEG = 3600.0


@dataclass(frozen=True)
class StationProfile:
    id: str
    description: str
    station: Station
    angle_type: str
    frame: str | None
    angle_noise_arcsec: float
    time_noise_s: float
    clock_offset_s: float
    declared_angle_uncertainty_arcsec: float
    declared_time_uncertainty_s: float
    cadence_s: float
    points_per_pass: int
    min_elevation_deg: float
    dropout_probability: float

    @classmethod
    def from_document(cls, doc: dict) -> StationProfile:
        problems = validate(doc, "station-profile")
        if problems:
            raise FormatError("invalid station profile", problems)
        return cls(
            id=doc["id"],
            description=doc["description"],
            station=Station.from_document(doc["station"]),
            angle_type=doc["angle_type"],
            frame=doc.get("frame"),
            angle_noise_arcsec=float(doc["angle_noise_arcsec"]),
            time_noise_s=float(doc["time_noise_s"]),
            clock_offset_s=float(doc["clock_offset_s"]),
            declared_angle_uncertainty_arcsec=float(doc["declared_angle_uncertainty_arcsec"]),
            declared_time_uncertainty_s=float(doc["declared_time_uncertainty_s"]),
            cadence_s=float(doc["cadence_s"]),
            points_per_pass=int(doc["points_per_pass"]),
            min_elevation_deg=float(doc["min_elevation_deg"]),
            dropout_probability=float(doc["dropout_probability"]),
        )


def builtin_profiles() -> list[str]:
    folder = resources.files("orbit_watch.data").joinpath("stations")
    return sorted(p.name[:-5] for p in folder.iterdir() if p.name.endswith(".json"))


def load_profile(name_or_path: str) -> StationProfile:
    """Load a station profile by built-in name (e.g. "sim-cmos-gps") or file path."""
    if name_or_path in builtin_profiles():
        text = (
            resources.files("orbit_watch.data")
            .joinpath("stations", f"{name_or_path}.json")
            .read_text(encoding="utf-8")
        )
    else:
        text = Path(name_or_path).read_text(encoding="utf-8")
    return StationProfile.from_document(json.loads(text))


class DeterministicRandom:
    """Uniform and normal deviates that are stable across Python versions."""

    def __init__(self, seed: int):
        self._random = random.Random(seed)

    def uniform(self) -> float:
        return self._random.random()

    def normal(self) -> float:
        # Box-Muller; 1 - random() lies in (0, 1], so the logarithm is finite.
        u1 = 1.0 - self._random.random()
        u2 = self._random.random()
        return math.sqrt(-2.0 * math.log(u1)) * math.cos(2.0 * math.pi * u2)


def culminations(
    catalog: Catalog,
    norad_id: int,
    station: Station,
    start: datetime,
    end: datetime,
    min_elevation_deg: float,
) -> list[datetime]:
    """Times of highest elevation of passes above the elevation limit, rounded to seconds."""
    ts = timescale()
    satellite = catalog.satellite(norad_id)
    times, events = satellite.find_events(
        topos(station),
        ts.from_datetime(start),
        ts.from_datetime(end),
        altitude_degrees=min_elevation_deg,
    )
    result = []
    for t, event in zip(times, events, strict=True):
        if event == 1:
            moment = t.utc_datetime()
            result.append(
                add_seconds(moment.replace(microsecond=0), round(moment.microsecond / 1e6))
            )
    return result


def simulate(
    catalog: Catalog,
    target_id: int,
    profile: StationProfile,
    start: datetime,
    end: datetime,
    *,
    seed: int,
    observed_id: int | None = None,
    max_passes: int | None = None,
    time_shift_s: float = 0.0,
    notes: str | None = None,
) -> ObservationSet:
    """Simulate one station observing an object.

    ``target_id`` is the object the observer claims to have observed;
    ``observed_id`` (default: the same) is the object whose positions are
    actually generated, which lets tests build wrong-target deliveries.
    ``time_shift_s`` moves every observation in time after pass selection
    (used to build deliveries that miss the requested window).
    """
    observed_id = target_id if observed_id is None else observed_id
    rng = DeterministicRandom(seed)
    passes = culminations(
        catalog, observed_id, profile.station, start, end, profile.min_elevation_deg
    )
    if max_passes is not None:
        passes = passes[:max_passes]
    candidates: list[datetime] = []
    n = profile.points_per_pass
    for culmination in passes:
        for k in range(n):
            offset = (k - (n - 1) / 2.0) * profile.cadence_s
            candidates.append(add_seconds(culmination, offset + time_shift_s))

    draws = []
    for label in candidates:
        dropped = rng.uniform() < profile.dropout_probability
        jitter = rng.normal() * profile.time_noise_s
        noise_1 = rng.normal() * profile.angle_noise_arcsec
        noise_2 = rng.normal() * profile.angle_noise_arcsec
        # The station clock reads clock_offset_s ahead of UTC, so the object
        # was really observed clock_offset_s earlier than the label says.
        true_time = add_seconds(label, -profile.clock_offset_s + jitter)
        draws.append((label, true_time, dropped, noise_1, noise_2))

    observations: list[Observation] = []
    if draws:
        truth = predict(
            catalog.satellite(observed_id),
            profile.station,
            [d[1] for d in draws],
            profile.angle_type,
            profile.frame,
        )
        for index, (label, _true, dropped, noise_1, noise_2) in enumerate(draws):
            elevation = float(truth.elevation_deg[index])
            if dropped or elevation < profile.min_elevation_deg:
                continue
            a1 = float(truth.angle_1_deg[index])
            a2 = float(truth.angle_2_deg[index])
            a2_noisy = a2 + noise_2 / ARCSEC_PER_DEG
            a1_noisy = a1 + noise_1 / ARCSEC_PER_DEG / max(math.cos(math.radians(a2)), 1e-6)
            a2_noisy = max(-90.0, min(90.0, a2_noisy))
            label_ms = add_seconds(
                label.replace(microsecond=0), round(label.microsecond / 1000) / 1000
            )
            common = dict(
                time=label_ms,
                time_uncertainty_s=profile.declared_time_uncertainty_s,
                angle_uncertainty_arcsec=profile.declared_angle_uncertainty_arcsec,
            )
            if profile.angle_type == "radec":
                observations.append(
                    Observation(
                        angle_type="radec",
                        frame=profile.frame,
                        ra_deg=a1_noisy % 360.0,
                        dec_deg=a2_noisy,
                        **common,
                    )
                )
            else:
                observations.append(
                    Observation(
                        angle_type="azel", az_deg=a1_noisy % 360.0, el_deg=a2_noisy, **common
                    )
                )

    description = (
        f"SIMULATED by the Orbit Watch simulator: profile {profile.id}, seed {seed}. "
        "Not real observations."
    )
    if notes:
        description += " " + notes
    return ObservationSet(
        station=profile.station,
        target=Target(norad_id=target_id),
        observations=observations,
        simulated=True,
        source={"software": f"orbit-watch {__version__} simulator", "notes": description},
    )

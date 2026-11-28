"""The orbit fit's example (phase 6, step 6.4, D-70): three SIMULATED stations observe a
SIMULATED object for a day, and the fit starts from its set moved some 4 km along the
track. Committed in ``examples/orbit-fit/`` and compared byte for byte in CI."""

from __future__ import annotations

from dataclasses import replace
from datetime import timedelta
from importlib import resources
from pathlib import Path
from typing import Any

from orbit_watch import orbit_fit
from orbit_watch.canonical import dumps_pretty, write_text
from orbit_watch.catalog import parse_catalog
from orbit_watch.formats import owjson
from orbit_watch.model import Station
from orbit_watch.sim.simulator import load_profile, simulate

NORAD_ID = 339001
DAYS = 1.0
STATIONS = (
    Station("SIM-ESPOO", 60.205, 24.655, 40.0, "Simulated station near Espoo, Finland", 9901),
    Station("SIM-GRAZ", 47.07, 15.49, 490.0, "Simulated station near Graz, Austria", 9906),
    Station("SIM-MADRID", 40.42, -3.70, 660.0, "Simulated station near Madrid, Spain", 9907),
)
# The start set: the true set, its mean anomaly 0.03 degrees ahead and its mean motion
# 2e-5 revolutions a day faster, about 4 km along the track by the end of the day.
MEAN_ANOMALY_OFFSET_DEG = 0.03
MEAN_MOTION_OFFSET = 2e-5


def _truth() -> bytes:
    return resources.files("orbit_watch.data").joinpath("catalog.json").read_bytes()


def start_catalog() -> bytes:
    record = dict(parse_catalog(_truth()).record(NORAD_ID))
    record["MEAN_ANOMALY"] = round(float(record["MEAN_ANOMALY"]) + MEAN_ANOMALY_OFFSET_DEG, 4)
    record["MEAN_MOTION"] = round(float(record["MEAN_MOTION"]) + MEAN_MOTION_OFFSET, 8)
    document = {
        "format": "orbit-watch/gp-catalog",
        "format_version": "1.0",
        "simulated": True,
        "description": (
            "SIMULATED: the start set of the orbit fit's example, the true set moved about "
            "4 km along the track. Not a real orbit."
        ),
        "records": [record],
    }
    return dumps_pretty(document, sort_keys=False).encode("utf-8")


def observation_files() -> dict[str, bytes]:
    truth = parse_catalog(_truth())
    profile = load_profile("sim-cmos-gps")
    start = truth.element_sets(NORAD_ID)[0].epoch
    files = {}
    for seed, station in enumerate(STATIONS, start=1):
        observed = simulate(
            truth,
            NORAD_ID,
            replace(profile, station=station),
            start,
            start + timedelta(days=DAYS),
            seed=seed,
        )
        files[f"{station.id}.json"] = owjson.write_observation_set(observed).encode("utf-8")
    return files


def run_fit_example(out_dir: str | Path) -> dict[str, Any]:
    out = Path(out_dir)
    (out / "observations").mkdir(parents=True, exist_ok=True)
    catalog = start_catalog()
    write_text(out / "catalog.json", catalog.decode("utf-8"))
    sets = []
    for name, data in observation_files().items():
        write_text(out / "observations" / name, data.decode("utf-8"))
        sets.append(owjson.read_observation_set(data))
    parsed = parse_catalog(catalog)
    start = orbit_fit.start_set_for(parsed.element_sets(NORAD_ID), sets)
    document = orbit_fit.fit(start, sets, simulated_catalog=parsed.simulated)
    write_text(out / "fit.json", dumps_pretty(document, sort_keys=False))
    write_text(out / "README.md", _readme(document))
    return document


def _readme(document: dict[str, Any]) -> str:
    result = document["result"]
    along = result["rms_along_track_arcsec"]
    across = result["rms_cross_track_arcsec"]
    names = "\n".join(f"- `observations/{s.id}.json`" for s in STATIONS)
    span = result["span_days"] * 24
    return f"""# The orbit fit's example

**SIMULATED.** Three simulated stations watch the simulated object {NORAD_ID} for a day
and see it in the first night's passes, over {span:.1f} hours:

{names}

The fit starts from `catalog.json`, the true set moved about 4 km along the track, and
gives `fit.json` ([D-70](../../docs/decisions.md#d-70-orbit-determination-in-the-core)):

```
orbit-watch fit-orbit observations/*.json --catalog catalog.json --out fit.json
```

It uses {result["used"]} of {result["observations"]} observations, with an RMS of
{along:g} arcseconds along the motion and {across:g} across it. `orbit-watch demo
--orbit-fit` makes the directory again, and CI compares it byte for byte.

{document["notice"]}
"""

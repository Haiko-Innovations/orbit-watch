"""The six SIMULATED test datasets of phase 0 and the demo that verifies them.

Each scenario is one delivery answering the same simulated request: "observe
SIM-CUBESAT-A on the night of 1-2 November 2026". The window is the evening and
night in Finland, because optical observers cannot see satellites in daylight
(the simulator itself does not model illumination). The expected verification
result and the checks that must fail are part of the scenario definition, and
the test suite holds the implementation to them.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import dataclass, field
from importlib import resources
from pathlib import Path

from orbit_watch import SIMULATION_NOTICE, quality
from orbit_watch.canonical import dumps_pretty, sha256_bytes, write_text
from orbit_watch.catalog import parse_catalog
from orbit_watch.formats import iod, load_observation_sets, owjson
from orbit_watch.formats.sites import Sites
from orbit_watch.sim.simulator import load_profile, simulate
from orbit_watch.timeutil import parse_utc
from orbit_watch.verify.engine import VerificationInput, render_text, verify

REQUEST_ID = "SIM-REQ-0001"
TARGET = 339001
WINDOW_START = "2026-11-01T15:00:00.000Z"
WINDOW_END = "2026-11-02T03:00:00.000Z"

REQUEST = {
    "format": "orbit-watch/request",
    "format_version": "1.0",
    "simulated": True,
    "request_id": REQUEST_ID,
    "title": "SIMULATED: identify and track SIM-CUBESAT-A after deployment",
    "target": {"norad_id": TARGET, "name": "SIM-CUBESAT-A (SIMULATED)"},
    "window": {"start": WINDOW_START, "end": WINDOW_END},
    "requirements": {
        "min_observations": 6,
        "max_angle_uncertainty_arcsec": 60.0,
        "max_time_uncertainty_s": 0.1,
        "angle_types": ["radec", "azel"],
    },
}


@dataclass
class Scenario:
    name: str
    title: str
    expected_verdict: str
    expected_failures: list[str]
    build: Callable[[dict], bytes] = field(repr=False)


def _packaged(name: str) -> bytes:
    return resources.files("orbit_watch.data").joinpath(name).read_bytes()


def _sim_json(catalog, **kwargs) -> bytes:
    observation_set = simulate(catalog, **kwargs)
    return owjson.write_observation_set(observation_set).encode("utf-8")


def _window(days_after: int = 0):
    from datetime import timedelta

    return (
        parse_utc(WINDOW_START) + timedelta(days=days_after),
        parse_utc(WINDOW_END) + timedelta(days=days_after),
    )


def _acceptable(ctx: dict) -> bytes:
    start, end = _window()
    return _sim_json(
        ctx["catalog"],
        target_id=TARGET,
        profile=load_profile("sim-cmos-gps"),
        start=start,
        end=end,
        seed=101,
        max_passes=2,
    )


def _invalid(ctx: dict) -> bytes:
    document = json.loads(ctx["datasets"]["acceptable"])
    observations = document["observations"]
    del observations[1]["time"]
    observations[3]["dec_deg"] = 95.5
    observations[5]["angle_type"] = "ra-dec"
    document["source"]["notes"] = (
        "SIMULATED and deliberately broken: one observation has no time, one has a declination "
        "of 95.5 degrees and one has an unknown angle type."
    )
    return dumps_pretty(document, sort_keys=False).encode("utf-8")


def _late(ctx: dict) -> bytes:
    start, end = _window(days_after=1)
    return _sim_json(
        ctx["catalog"],
        target_id=TARGET,
        profile=load_profile("sim-cmos-gps"),
        start=start,
        end=end,
        seed=102,
        max_passes=2,
        notes="Observed one day after the requested window closed.",
    )


def _duplicate(ctx: dict) -> bytes:
    document = json.loads(ctx["datasets"]["acceptable"])
    document["source"]["notes"] = (
        "SIMULATED resubmission: the observations of the acceptable dataset, delivered again."
    )
    return dumps_pretty(document, sort_keys=False).encode("utf-8")


def _wrong_target(ctx: dict) -> bytes:
    start, end = _window()
    return _sim_json(
        ctx["catalog"],
        target_id=TARGET,
        observed_id=339002,
        profile=load_profile("sim-cmos-gps"),
        start=start,
        end=end,
        seed=103,
        max_passes=2,
        notes="Claims SIM-CUBESAT-A but the positions are of SIM-CUBESAT-B, which "
        "trails it by about 8 seconds in the same orbit (a typical "
        "post-deployment mix-up).",
    )


def _too_imprecise(ctx: dict) -> bytes:
    start, end = _window()
    return _sim_json(
        ctx["catalog"],
        target_id=TARGET,
        profile=load_profile("sim-visual-binoculars"),
        start=start,
        end=end,
        seed=104,
        max_passes=3,
    )


SCENARIOS = [
    Scenario(
        "acceptable", "Good CMOS station with GPS timing, two passes", "pass", [], _acceptable
    ),
    Scenario(
        "invalid",
        "Broken file: missing time, impossible declination, unknown angle type",
        "fail",
        ["format"],
        _invalid,
    ),
    Scenario(
        "late",
        "Observed one day after the requested window",
        "fail",
        ["time_window", "min_observations"],
        _late,
    ),
    Scenario(
        "duplicate",
        "The acceptable observations delivered again",
        "fail",
        ["duplicates"],
        _duplicate,
    ),
    Scenario(
        "wrong_target",
        "Positions of the neighbouring CubeSat, labelled as the requested one",
        "fail",
        ["orbit_residuals"],
        _wrong_target,
    ),
    Scenario(
        "too_imprecise",
        "Visual observer with binoculars and a stopwatch",
        "fail",
        ["declared_uncertainty"],
        _too_imprecise,
    ),
]


def run_demo(out_dir: str | Path) -> list[dict]:
    """Generate the six datasets, verify each and write everything under out_dir."""
    out = Path(out_dir)
    (out / "datasets").mkdir(parents=True, exist_ok=True)
    catalog_bytes = _packaged("catalog.json")
    policy_bytes = _packaged("target-policy.json")
    request_bytes = dumps_pretty(REQUEST, sort_keys=False).encode("utf-8")
    write_text(out / "catalog.json", catalog_bytes.decode("utf-8"))
    write_text(out / "target-policy.json", policy_bytes.decode("utf-8"))
    write_text(out / "request.json", request_bytes.decode("utf-8"))

    ctx: dict = {"catalog": parse_catalog(catalog_bytes), "datasets": {}}
    results = []
    for scenario in SCENARIOS:
        data = scenario.build(ctx)
        ctx["datasets"][scenario.name] = data
        folder = out / "datasets" / scenario.name
        folder.mkdir(parents=True, exist_ok=True)
        write_text(folder / "observations.json", data.decode("utf-8"))
        delivery = {
            "format": "orbit-watch/delivery",
            "format_version": "1.0",
            "simulated": True,
            "delivery_id": f"SIM-DEL-{scenario.name.replace('_', '-')}",
            "request_id": REQUEST_ID,
            "observations": {
                "file": "observations.json",
                "format": "json",
                "sha256": sha256_bytes(data),
            },
        }
        write_text(folder / "delivery.json", dumps_pretty(delivery, sort_keys=False))
        previous = [] if scenario.name == "acceptable" else [ctx["datasets"]["acceptable"]]
        report = verify(
            VerificationInput(
                request=request_bytes,
                observations=data,
                observations_format="json",
                catalog=catalog_bytes,
                policy=policy_bytes,
                previous=previous,
                declared_sha256=delivery["observations"]["sha256"],
            )
        )
        write_text(folder / "report.json", dumps_pretty(report, sort_keys=False))
        write_text(folder / "report.txt", render_text(report))
        failed = [c["id"] for c in report["checks"] if c["result"] == "fail"]
        results.append(
            {
                "dataset": scenario.name,
                "title": scenario.title,
                "expected_verdict": scenario.expected_verdict,
                "verdict": report["verdict"],
                "expected_failures": scenario.expected_failures,
                "failed_checks": failed,
                "as_expected": report["verdict"] == scenario.expected_verdict
                and failed == scenario.expected_failures,
            }
        )
    write_text(out / "summary.txt", summary_table(results))
    build_quality_example(out / "quality", ctx["catalog"])
    write_text(out / "README.md", _readme(results))
    return results


QUALITY_OBJECTS = (339001, 339002, 339003)
QUALITY_NIGHTS = ("2026-11-01", "2026-11-02", "2026-11-03")


def build_quality_example(out: Path, catalog) -> dict:
    """A SIMULATED station whose clock starts running 0.25 s ahead of UTC on the third night.

    Writes observations.iod (three objects, three nights), sites.json and the
    quality meter report.
    """
    import dataclasses
    from datetime import timedelta

    out.mkdir(parents=True, exist_ok=True)
    profile = load_profile("sim-clock-offset")
    fixed = dataclasses.replace(profile, clock_offset_s=0.0)
    sets = []
    for night_index, night in enumerate(QUALITY_NIGHTS):
        start = parse_utc(f"{night}T15:00:00Z")
        end = start + timedelta(hours=12)
        for object_index, norad_id in enumerate(QUALITY_OBJECTS):
            sets.append(
                simulate(
                    catalog,
                    norad_id,
                    fixed if night_index < 2 else profile,
                    start,
                    end,
                    seed=200 + 10 * night_index + object_index,
                    max_passes=2,
                )
            )
    iod_text = iod.write_iod(sets)
    write_text(out / "observations.iod", iod_text)
    station = profile.station
    sites = {
        "format": "orbit-watch/sites",
        "format_version": "1.0",
        "simulated": True,
        "sites": [{**station.to_document(), "simulated": True}],
    }
    write_text(out / "sites.json", dumps_pretty(sites, sort_keys=False))
    loaded = load_observation_sets(
        out / "observations.iod",
        data=iod_text.encode("utf-8"),
        sites=Sites.load(out / "sites.json"),
    )
    report = quality.score_station(loaded.sets, catalog)
    write_text(out / "report.json", dumps_pretty(report, sort_keys=False))
    write_text(out / "report.txt", quality.render_text(report))
    return report


def summary_table(results: list[dict]) -> str:
    lines = [
        "SIMULATED DATA - Orbit Watch phase 0 demo",
        "",
        f"{'dataset':<15}{'expected':<10}{'verdict':<14}{'failed checks':<36}ok",
    ]
    for r in results:
        failed = ", ".join(r["failed_checks"]) or "-"
        lines.append(
            f"{r['dataset']:<15}{r['expected_verdict']:<10}{r['verdict']:<14}"
            f"{failed:<36}{'yes' if r['as_expected'] else 'NO'}"
        )
    return "\n".join(lines) + "\n"


def _readme(results: list[dict]) -> str:
    rows = "\n".join(
        f"| [`{r['dataset']}`](datasets/{r['dataset']}/report.txt) | {r['title']} | "
        f"{r['verdict']} | {', '.join(r['failed_checks']) or '-'} |"
        for r in results
    )
    return f"""# Orbit Watch demo output (SIMULATED)

> {SIMULATION_NOTICE}

Generated by `orbit-watch demo`. Every file here can be regenerated
byte for byte with the same software versions.

- `request.json`: the simulated request (object 339001, SIM-CUBESAT-A, on the
  night of 1-2 November 2026)
- `catalog.json`: the simulated reference orbits (GP elements in OMM form)
- `target-policy.json`: the simulated allow-list
- `datasets/<name>/`: one delivery each: `observations.json`, `delivery.json`
  (with the SHA-256 of the observations), `report.json` (the verification
  report) and `report.txt` (the same report as plain text)

| Dataset | Scenario | Verdict | Failed checks |
|---|---|---|---|
{rows}

`quality/` holds a SIMULATED station whose clock is fine for two nights and
runs 0.25 s ahead of UTC on the third: `observations.iod`, `sites.json` and
the station quality meter's `report.txt` and `report.json`.

To verify one delivery yourself:

```sh
orbit-watch validate datasets/wrong_target/delivery.json --request request.json \\
  --catalog catalog.json --policy target-policy.json \\
  --previous datasets/acceptable/observations.json
```

To run the station quality meter:

```sh
orbit-watch score-station quality/observations.iod --sites quality/sites.json \\
  --catalog catalog.json
```
"""

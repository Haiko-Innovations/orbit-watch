"""Command-line interface: ``orbit-watch <command>``."""

from __future__ import annotations

import argparse
import os
import sys
from datetime import UTC, datetime
from pathlib import Path

from orbit_watch import SIMULATION_NOTICE, __version__
from orbit_watch.canonical import dumps_pretty, write_text
from orbit_watch.formats import FORMATS, FormatError, Sites, load_observation_sets, owjson
from orbit_watch.formats import iod as iod_format
from orbit_watch.formats import tdm as tdm_format

EXIT_OK = 0
EXIT_FAILED = 1  # the command ran, but the result is negative (e.g. verification failed)
EXIT_USAGE = 2  # bad input, missing files, unsupported options
EXIT_INCONCLUSIVE = 3  # verification could not decide


def _err(message: str) -> None:
    print(f"orbit-watch: {message}", file=sys.stderr)


def _creation_time() -> datetime:
    """Current time, or SOURCE_DATE_EPOCH for reproducible output."""
    epoch = os.environ.get("SOURCE_DATE_EPOCH")
    if epoch:
        return datetime.fromtimestamp(int(epoch), tz=UTC)
    return datetime.now(tz=UTC).replace(microsecond=0)


def _output_format(path: Path, explicit: str | None) -> str:
    if explicit:
        return explicit
    suffix = path.suffix.lower()
    mapping = {".json": "json", ".iod": "iod", ".tdm": "tdm", ".kvn": "tdm"}
    if suffix not in mapping:
        raise FormatError(f"cannot tell the output format from {path.name!r}; use --to")
    return mapping[suffix]


def _load_sites(path: str | None) -> Sites:
    return Sites.load(path) if path else Sites.empty()


def cmd_convert(args: argparse.Namespace) -> int:
    source = Path(args.input)
    target = Path(args.output)
    loaded = load_observation_sets(
        source,
        input_format=args.input_format,
        sites=_load_sites(args.sites),
        default_angle_uncertainty_arcsec=args.default_angle_uncertainty_arcsec,
        default_time_uncertainty_s=args.default_time_uncertainty_s,
    )
    for message in loaded.warnings:
        _err(f"warning: {message}")
    for message in loaded.skipped:
        _err(f"skipped: {message}")
    fmt = _output_format(target, args.output_format)
    if fmt == "json":
        if len(loaded.sets) == 1:
            outputs = [(target, loaded.sets[0])]
        else:
            outputs = [
                (
                    target.with_name(
                        f"{target.stem}-{s.station.id}-{s.target.norad_id}{target.suffix}"
                    ),
                    s,
                )
                for s in loaded.sets
            ]
        for path, observation_set in outputs:
            write_text(path, owjson.write_observation_set(observation_set))
            print(f"wrote {path} ({len(observation_set.observations)} observations)")
    elif fmt == "iod":
        write_text(target, iod_format.write_iod(loaded.sets))
        print(f"wrote {target}")
    else:
        write_text(target, tdm_format.write_tdm(loaded.sets, creation_date=_creation_time()))
        print(f"wrote {target}")
    if any(s.simulated for s in loaded.sets):
        print("note: the input is marked as SIMULATED data; the output keeps that marking")
    return EXIT_OK


def _write_observation_sets(sets, target: Path, fmt: str) -> list[Path]:
    if fmt == "json":
        if len(sets) == 1:
            outputs = [(target, sets[0])]
        else:
            outputs = [
                (
                    target.with_name(
                        f"{target.stem}-{s.station.id}-{s.target.norad_id}{target.suffix}"
                    ),
                    s,
                )
                for s in sets
            ]
        for path, observation_set in outputs:
            write_text(path, owjson.write_observation_set(observation_set))
        return [p for p, _ in outputs]
    if fmt == "iod":
        write_text(target, iod_format.write_iod(sets))
    else:
        write_text(target, tdm_format.write_tdm(sets, creation_date=_creation_time()))
    return [target]


def cmd_simulate(args: argparse.Namespace) -> int:
    from orbit_watch.catalog import parse_catalog
    from orbit_watch.sim.simulator import load_profile, simulate
    from orbit_watch.timeutil import parse_utc

    catalog_bytes = Path(args.catalog).read_bytes() if args.catalog else _packaged("catalog.json")
    catalog = parse_catalog(catalog_bytes)
    for norad_id in {args.target, args.observed or args.target}:
        if norad_id not in catalog:
            raise FormatError(f"object {norad_id} is not in the catalogue")
    observation_set = simulate(
        catalog,
        args.target,
        load_profile(args.profile),
        parse_utc(args.start),
        parse_utc(args.end),
        seed=args.seed,
        observed_id=args.observed,
        max_passes=args.max_passes,
    )
    if not observation_set.observations:
        _err("no observations: the object does not pass above the elevation limit in the window")
        return EXIT_FAILED
    target = Path(args.output)
    fmt = _output_format(target, args.output_format)
    for path in _write_observation_sets([observation_set], target, fmt):
        print(f"wrote {path} ({len(observation_set.observations)} SIMULATED observations)")
    print(SIMULATION_NOTICE)
    return EXIT_OK


def _packaged(name: str) -> bytes:
    from importlib import resources

    return resources.files("orbit_watch.data").joinpath(name).read_bytes()


def cmd_validate(args: argparse.Namespace) -> int:
    from orbit_watch.documents import Delivery, is_delivery_manifest
    from orbit_watch.verify.engine import UsageError, VerificationInput, render_text, verify

    source = Path(args.input)
    data = source.read_bytes()
    declared = args.declared_sha256
    observations_format = args.input_format
    if is_delivery_manifest(data):
        delivery = Delivery.parse(data)
        observation_path = source.parent / delivery.file
        data = observation_path.read_bytes()
        declared = delivery.sha256
        observations_format = observations_format or delivery.format
    request_bytes = Path(args.request).read_bytes()
    try:
        report = verify(
            VerificationInput(
                request=request_bytes,
                observations=data,
                observations_format=observations_format,
                catalog=Path(args.catalog).read_bytes(),
                policy=Path(args.policy).read_bytes(),
                previous=[Path(p).read_bytes() for p in args.previous],
                declared_sha256=declared,
                sites=_load_sites(args.sites),
            )
        )
    except UsageError as exc:
        _err(str(exc))
        return EXIT_USAGE
    if args.report:
        write_text(args.report, dumps_pretty(report, sort_keys=False))
    if args.json:
        sys.stdout.write(dumps_pretty(report, sort_keys=False))
    else:
        sys.stdout.write(render_text(report))
        if args.report:
            print(f"report written to {args.report}")
    return {"pass": EXIT_OK, "fail": EXIT_FAILED}.get(report["verdict"], EXIT_INCONCLUSIVE)


def cmd_demo(args: argparse.Namespace) -> int:
    from orbit_watch.sim.scenarios import run_demo, summary_table

    results = run_demo(args.out)
    sys.stdout.write(summary_table(results))
    print()
    print(f"Datasets, delivery manifests and verification reports are in {args.out}/")
    print(f"Read {args.out}/datasets/wrong_target/report.txt for a full explanation.")
    print(SIMULATION_NOTICE)
    return EXIT_OK if all(r["as_expected"] for r in results) else EXIT_FAILED


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="orbit-watch",
        description=(
            "Orbit Watch phase 0: observation formats, station simulator, verification "
            "engine and station quality meter. Simulated data is always labelled as such."
        ),
    )
    parser.add_argument("--version", action="version", version=f"orbit-watch {__version__}")
    commands = parser.add_subparsers(dest="command", metavar="command")
    commands.required = True

    convert = commands.add_parser(
        "convert",
        help="convert observations between Orbit Watch JSON, IOD and CCSDS TDM",
        description="Convert observations between Orbit Watch JSON, IOD and a CCSDS TDM subset.",
    )
    convert.add_argument("input", help="input file (.json, .iod, .tdm, or detected from content)")
    convert.add_argument("-o", "--output", required=True, help="output file")
    convert.add_argument("--from", dest="input_format", choices=FORMATS, help="input format")
    convert.add_argument("--to", dest="output_format", choices=FORMATS, help="output format")
    convert.add_argument(
        "--sites", help="sites file with station coordinates (needed for IOD and TDM)"
    )
    convert.add_argument(
        "--default-angle-uncertainty-arcsec",
        type=float,
        help="used when the input gives no angle uncertainty",
    )
    convert.add_argument(
        "--default-time-uncertainty-s",
        type=float,
        help="used when the input gives no time uncertainty",
    )
    convert.set_defaults(handler=cmd_convert)

    demo = commands.add_parser(
        "demo",
        help="generate the six SIMULATED test datasets and verify them",
        description="Generate the six SIMULATED test datasets (acceptable, invalid, late, "
        "duplicate, wrong target, too imprecise), verify each one and write the reports.",
    )
    demo.add_argument("--out", default="orbit-watch-demo", help="output directory")
    demo.set_defaults(handler=cmd_demo)

    simulate = commands.add_parser(
        "simulate",
        help="simulate observations of an object from a station profile (SIMULATED data)",
        description="Simulate positional observations with SGP4 from GP orbit data. "
        "The output is always marked as SIMULATED.",
    )
    simulate.add_argument("--target", type=int, required=True, help="catalogue number to claim")
    simulate.add_argument(
        "--observed", type=int, help="catalogue number actually observed (default: the target)"
    )
    simulate.add_argument(
        "--profile",
        default="sim-cmos-gps",
        help="built-in profile name or profile file (default: sim-cmos-gps)",
    )
    simulate.add_argument("--start", required=True, help="window start, UTC (YYYY-MM-DDThh:mm:ssZ)")
    simulate.add_argument("--end", required=True, help="window end, UTC")
    simulate.add_argument("--seed", type=int, default=1, help="random seed (default 1)")
    simulate.add_argument("--max-passes", type=int, help="use at most this many passes")
    simulate.add_argument(
        "--catalog",
        help="GP catalogue (CelesTrak JSON/CSV); default: the built-in SIMULATED catalogue",
    )
    simulate.add_argument("-o", "--output", required=True, help="output file (.json, .iod, .tdm)")
    simulate.add_argument("--to", dest="output_format", choices=FORMATS, help="output format")
    simulate.set_defaults(handler=cmd_simulate)

    validate = commands.add_parser(
        "validate",
        help="verify a delivery against a request and a public reference orbit",
        description="Run the deterministic automated verification and explain every check.",
    )
    validate.add_argument("input", help="delivery manifest or observation file")
    validate.add_argument("--request", required=True, help="request file")
    validate.add_argument("--catalog", required=True, help="reference orbits (GP data)")
    validate.add_argument("--policy", required=True, help="target policy (allow-list)")
    validate.add_argument(
        "--previous",
        action="append",
        default=[],
        help="an earlier delivery's observation file (repeatable)",
    )
    validate.add_argument("--sites", help="sites file (for IOD and TDM input)")
    validate.add_argument("--from", dest="input_format", choices=FORMATS, help="input format")
    validate.add_argument("--declared-sha256", help="expected SHA-256 of the observation file")
    validate.add_argument("--report", help="write the JSON report to this file")
    validate.add_argument("--json", action="store_true", help="print the JSON report")
    validate.set_defaults(handler=cmd_validate)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return args.handler(args)
    except FormatError as exc:
        _err(str(exc))
        for problem in exc.problems[:50]:
            _err(f"  {problem}")
        return EXIT_USAGE
    except (OSError, ValueError) as exc:
        _err(str(exc))
        return EXIT_USAGE

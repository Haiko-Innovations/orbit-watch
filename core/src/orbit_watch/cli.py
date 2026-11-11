"""Command-line interface: ``orbit-watch <command>``."""

from __future__ import annotations

import argparse
import os
import sys
from datetime import UTC, datetime
from pathlib import Path

from orbit_watch import __version__
from orbit_watch.canonical import write_text
from orbit_watch.formats import FORMATS, FormatError, Sites, load_observation_sets, owjson
from orbit_watch.formats import iod as iod_format
from orbit_watch.formats import tdm as tdm_format

EXIT_OK = 0
EXIT_FAILED = 1  # the command ran, but the result is negative (e.g. verification failed)
EXIT_USAGE = 2  # bad input, missing files, unsupported options


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

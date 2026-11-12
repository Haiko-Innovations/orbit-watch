"""Command-line interface: ``orbit-watch <command>``."""

from __future__ import annotations

import argparse
import os
import sys
from datetime import UTC, datetime
from pathlib import Path

from orbit_watch import SIMULATION_NOTICE, __version__
from orbit_watch.canonical import dumps_pretty, write_text
from orbit_watch.chain import ChainError
from orbit_watch.client import ClientError
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

    if args.phase == 2:
        return _demo_phase2(args)
    if args.phase == 1:
        from orbit_watch.sim.phase1_demo import run_phase1_demo

        out = args.out or "orbit-watch-demo-phase1"
        summary = run_phase1_demo(out)
        for request_id, item in summary["requests"].items():
            print(
                f"{request_id}  {item['summary']['outcome']:<10}data {item['publication']['state']}"
            )
        print(f"\nTranscript: {out}/transcript.md")
        print(SIMULATION_NOTICE)
        return EXIT_OK
    args.out = args.out or "orbit-watch-demo"

    results = run_demo(args.out)
    sys.stdout.write(summary_table(results))
    print()
    print(f"Datasets, delivery manifests and verification reports are in {args.out}/")
    print(f"Read {args.out}/datasets/wrong_target/report.txt for a full explanation.")
    print(SIMULATION_NOTICE)
    return EXIT_OK if all(r["as_expected"] for r in results) else EXIT_FAILED


def _demo_phase2(args: argparse.Namespace) -> int:
    """The phase 2 demo against a request service on a chain (step 2.8)."""
    import tempfile

    try:
        from web3 import Web3

        from orbit_watch.chain.networks import public_rpc
        from orbit_watch.sim.phase2_demo import ChainClock, Settings, run_phase2_demo
    except ImportError:
        _err(
            'the phase 2 demo needs the optional "evm" and "api" dependencies: '
            'pip install "orbit-watch[api,evm]"'
        )
        return EXIT_USAGE
    key = args.key or os.environ.get("ORBIT_WATCH_KEY")
    api = args.api or os.environ.get("ORBIT_WATCH_API") or "http://127.0.0.1:8000"
    if not (key and args.wallets and args.password_file):
        _err(
            "the phase 2 demo needs an admin key (--key or $ORBIT_WATCH_KEY), --wallets "
            "and --password-file"
        )
        return EXIT_USAGE
    rpc = args.rpc or os.environ.get("ORBIT_WATCH_RPC") or public_rpc(84532)
    settings = Settings(
        api=api,
        admin_key=key,
        wallets=Path(args.wallets),
        password_file=Path(args.password_file),
        rpc=rpc,
        minutes=args.minutes,
        prefix=args.id_prefix,
    )
    out = args.out or "orbit-watch-demo-phase2"
    clock = ChainClock(Web3(Web3.HTTPProvider(rpc)))
    with tempfile.TemporaryDirectory(prefix="orbit-watch-demo-") as work:
        summary = run_phase2_demo(settings, clock, out, Path(work))
    for request_id, item in summary["requests"].items():
        print(f"{request_id}  {item['outcome']:<10}on chain: {item['on_chain']}")
    print(f"\nTranscript: {out}/transcript.md")
    print(f"{SIMULATION_NOTICE} {summary['chain']['notice']}.")
    return EXIT_OK


def cmd_score_station(args: argparse.Namespace) -> int:
    from orbit_watch import quality
    from orbit_watch.catalog import parse_catalog

    catalog = parse_catalog(Path(args.catalog).read_bytes())
    sites = _load_sites(args.sites)
    sets = []
    for name in args.inputs:
        loaded = load_observation_sets(Path(name), input_format=args.input_format, sites=sites)
        for message in loaded.warnings:
            _err(f"warning: {message}")
        for message in loaded.skipped:
            _err(f"skipped: {message}")
        sets.extend(loaded.sets)
    stations = sorted({s.station.id for s in sets})
    if args.station:
        sets = [s for s in sets if s.station.id == args.station]
    elif len(stations) > 1:
        raise FormatError(
            f"the input has several stations ({', '.join(stations)}); choose one with --station"
        )
    if not sets:
        raise FormatError("no observations for the chosen station")
    report = quality.score_station(sets, catalog)
    if args.report:
        write_text(args.report, dumps_pretty(report, sort_keys=False))
    if args.json:
        sys.stdout.write(dumps_pretty(report, sort_keys=False))
    else:
        sys.stdout.write(quality.render_text(report))
    return EXIT_OK


def cmd_fetch_gp(args: argparse.Namespace) -> int:
    from orbit_watch.fetch import FetchError, fetch_gp

    queries = [
        (k, v)
        for k, v in (("CATNR", args.catnr), ("GROUP", args.group), ("INTDES", args.intdes))
        if v
    ]
    if len(queries) != 1:
        raise FormatError("give exactly one of --catnr, --group or --intdes")
    key, value = queries[0]
    try:
        print(fetch_gp(key, value, Path(args.output), force=args.force))
    except FetchError as exc:
        _err(str(exc))
        return EXIT_FAILED
    print(
        "Source: CelesTrak (https://celestrak.org), GP data from the US Space Force. "
        "Please follow the CelesTrak usage policy: https://celestrak.org/usage-policy.php"
    )
    return EXIT_OK


def cmd_allowlist_build(args: argparse.Namespace) -> int:
    from orbit_watch.allowlist import build_policy

    policy = build_policy(
        [Path(p).read_bytes() for p in args.include],
        [Path(p).read_bytes() for p in args.exclude],
        use_default_patterns=not args.no_default_patterns,
        extra_patterns=tuple(args.exclude_name),
    )
    write_text(args.output, dumps_pretty(policy, sort_keys=False))
    print(f"wrote {args.output}: {policy['description']}")
    return EXIT_OK


def _service_inputs(args: argparse.Namespace):
    from orbit_watch.reviewers import ReviewerRegistry
    from orbit_watch.service import VerificationContext

    notes = []
    catalog = Path(args.catalog).read_bytes() if args.catalog else _packaged("catalog.json")
    policy = Path(args.policy).read_bytes() if args.policy else _packaged("target-policy.json")
    reviewers = Path(args.reviewers).read_bytes() if args.reviewers else _packaged("reviewers.json")
    for option, name in (
        ("catalog", "reference orbits"),
        ("policy", "allow-list"),
        ("reviewers", "reviewer registry"),
    ):
        if getattr(args, option) is None:
            notes.append(f"using the built-in SIMULATED {name}")
    context = VerificationContext(catalog=catalog, policy=policy, sites=_load_sites(args.sites))
    return ReviewerRegistry.parse(reviewers), context, notes


def cmd_serve(args: argparse.Namespace) -> int:
    try:
        import uvicorn

        from orbit_watch.api import create_app
    except ImportError:
        _err('the API needs the optional "api" dependencies: pip install "orbit-watch[api]"')
        return EXIT_USAGE
    from orbit_watch.service import open_service

    registry, context, notes = _service_inputs(args)
    chain = None
    if args.network:
        if not args.verifier_keystore:
            _err(f"on {args.network}, give --verifier-keystore")
            return EXIT_USAGE
        _apply_network(args)
    if args.chain_rpc or args.escrow or args.verifier_keystore:
        if not (args.chain_rpc and args.escrow and args.verifier_keystore):
            _err(
                "on a chain, give --chain-rpc, --escrow and --verifier-keystore together, or "
                "--network and --verifier-keystore"
            )
            return EXIT_USAGE
        try:
            chain = _chain_link(args)
        except ImportError:
            _err('the chain needs the optional "evm" dependencies: pip install "orbit-watch[evm]"')
            return EXIT_USAGE
    service = open_service(args.dir, registry, context, chain=chain)
    for note in notes:
        print(f"note: {note}")
    print(f"Orbit Watch API {__version__} for {args.dir} on http://{args.host}:{args.port}/v1/")
    if chain is None:
        print("Phase 1 prototype: local use only, no TLS. All bundled data is SIMULATED.")
    else:
        print("Phase 2 prototype: local use only, no TLS. All bundled data is SIMULATED.")
        print(
            f"On chain {chain.chain.chain_id} ({chain.notice}): escrow "
            f"{chain.chain.escrow.address}, verifier {chain.verifier.address}"
        )
    try:
        uvicorn.run(create_app(service), host=args.host, port=args.port)
    finally:
        service.storage.close()
    return EXIT_OK


def _apply_network(args: argparse.Namespace) -> None:
    """Fill in the chain settings from a known deployment (step 2.7)."""
    from orbit_watch.chain import ChainError
    from orbit_watch.chain.networks import deployment, public_rpc

    record = deployment(args.network)
    if args.escrow and args.escrow.lower() != record["escrow"].lower():
        raise ChainError(
            "other_escrow", f"--escrow is not the escrow of {args.network} ({record['escrow']})"
        )
    args.escrow = record["escrow"]
    args.chain_rpc = args.chain_rpc or public_rpc(record["chain_id"])
    if args.from_block is None:
        args.from_block = record["from_block"]


def _chain_link(args: argparse.Namespace):
    """The service's link to a testnet chain, with the verifier key (step 2.6)."""
    import stat

    from web3 import Web3

    from orbit_watch.chain.client import OrbitWatchChain
    from orbit_watch.chain.link import ChainLink
    from orbit_watch.chain.wallet import load_keystore, read_password

    chain = OrbitWatchChain(Web3(Web3.HTTPProvider(args.chain_rpc)), args.escrow)
    keystore = Path(args.verifier_keystore)
    if keystore.stat().st_mode & (stat.S_IRWXG | stat.S_IRWXO):
        _err(f"warning: {keystore} can be read by other users; chmod 600 it")
    password = read_password(
        args.verifier_password_file,
        "verifier keystore password: ",
        env="ORBIT_WATCH_VERIFIER_PASSWORD_FILE",
    )
    return ChainLink(chain, load_keystore(keystore, password), from_block=args.from_block or 0)


def cmd_keys_create(args: argparse.Namespace) -> int:
    from orbit_watch.api import keys
    from orbit_watch.storage import Storage

    storage = Storage(args.dir)
    try:
        with storage.db.transaction():
            key = keys.create_key(storage.db, args.party, args.role, datetime.now(tz=UTC))
    except keys.ApiKeyError as error:
        _err(str(error))
        return EXIT_USAGE
    finally:
        storage.close()
    print(key)
    _err(f"created a {args.role} key for {args.party}; it is shown only this once")
    return EXIT_OK


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="orbit-watch",
        description=(
            "Orbit Watch: observation formats, station simulator, verification engine, "
            "station quality meter, and the phase 1 request API (server and client). "
            "Simulated data is always labelled as such."
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
    demo.add_argument(
        "--out",
        help="output directory (default: orbit-watch-demo, or "
        "orbit-watch-demo-phase1 with --phase 1)",
    )
    demo.add_argument(
        "--phase",
        type=int,
        choices=(0, 1, 2),
        default=0,
        help="0: the six verification datasets (default); 1: five requests "
        "through the whole request chain; 2: the same five requests on a testnet chain, "
        "against a running service",
    )
    phase2 = demo.add_argument_group(
        "phase 2 (testnet chain)",
        "Runs against a request service on a chain (orbit-watch serve --network "
        "base-sepolia). Every party signs with its own keystore from --wallets.",
    )
    phase2.add_argument(
        "--api", help="the service (default: $ORBIT_WATCH_API or http://127.0.0.1:8000)"
    )
    phase2.add_argument("--key", help="an admin API key (prefer $ORBIT_WATCH_KEY)")
    phase2.add_argument(
        "--wallets",
        help="directory of the parties' encrypted keystores, named <role>-<id>.json "
        "(requester-sim-cubesat-team.json, station-SIM-ESPOO.json, reviewer-sim-aino.json, …)",
    )
    phase2.add_argument("--password-file", help="the keystores' password file")
    phase2.add_argument(
        "--rpc", help="the wallets' RPC endpoint (default $ORBIT_WATCH_RPC, or Base Sepolia's)"
    )
    phase2.add_argument(
        "--minutes",
        type=float,
        default=6.0,
        help="challenge period and review time in minutes (default 6)",
    )
    phase2.add_argument(
        "--id-prefix",
        default="SIM-REQ-200",
        help="request IDs are this prefix and 1 to 5 (default SIM-REQ-200); a new run on "
        "the same escrow needs a new prefix",
    )
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

    score = commands.add_parser(
        "score-station",
        help="station quality meter: accuracy, timing errors and development over time",
        description="Compare your own observations with public reference orbits: measurement "
        "scatter, systematic timing offsets (clock errors) and how they develop night by night.",
    )
    score.add_argument("inputs", nargs="+", help="observation files (.json, .iod, .tdm)")
    score.add_argument("--catalog", required=True, help="reference orbits (GP data, OMM JSON/CSV)")
    score.add_argument("--sites", help="sites file with station coordinates (IOD and TDM)")
    score.add_argument("--station", help="station to score when the input has several")
    score.add_argument("--from", dest="input_format", choices=FORMATS, help="input format")
    score.add_argument("--report", help="write the JSON report to this file")
    score.add_argument("--json", action="store_true", help="print the JSON report")
    score.set_defaults(handler=cmd_score_station)

    fetch = commands.add_parser(
        "fetch-gp",
        help="download public GP orbit data from CelesTrak (one request, no retries)",
        description="Download current GP element sets in OMM JSON form from CelesTrak. "
        "Makes exactly one request, never retries, and does not download the same file "
        "again within two hours (CelesTrak updates GP data every two hours).",
    )
    fetch.add_argument("--catnr", help="catalogue number")
    fetch.add_argument("--group", help="CelesTrak group, e.g. cubesat, amateur, science")
    fetch.add_argument("--intdes", help="international designator, e.g. 2026-123")
    fetch.add_argument("-o", "--output", required=True, help="output file (.json)")
    fetch.add_argument(
        "--force", action="store_true", help="download even if the file is younger than two hours"
    )
    fetch.set_defaults(handler=cmd_fetch_gp)

    allowlist = commands.add_parser(
        "allowlist",
        help="build the target allow-list from public GP data",
        description="Build a target policy (allow-list) for civilian objects.",
    )
    allowlist_commands = allowlist.add_subparsers(dest="allowlist_command", metavar="command")
    allowlist_commands.required = True
    build = allowlist_commands.add_parser(
        "build",
        help="allow the objects of some GP files, minus others",
        description="Allow the objects in the --include GP files, minus those in the --exclude "
        "GP files and those whose names match conservative military/intelligence patterns.",
    )
    build.add_argument(
        "--include",
        action="append",
        required=True,
        help="GP file whose objects are allowed (repeatable)",
    )
    build.add_argument(
        "--exclude",
        action="append",
        default=[],
        help="GP file whose objects are never allowed (repeatable)",
    )
    build.add_argument(
        "--exclude-name",
        action="append",
        default=[],
        help="extra regular expression for names to exclude (repeatable)",
    )
    build.add_argument(
        "--no-default-patterns",
        action="store_true",
        help="do not apply the built-in name exclusion patterns",
    )
    build.add_argument("-o", "--output", required=True, help="output target policy file")
    build.set_defaults(handler=cmd_allowlist_build)

    from orbit_watch.cli_client import add_commands

    add_commands(commands)

    serve = commands.add_parser(
        "serve",
        help="run the phase 1 HTTP API for a service directory (local use only)",
        description="Run the phase 1 HTTP API. The service's state lives in --dir. "
        "Needs the optional api dependencies. Local use only: no TLS.",
    )
    serve.add_argument("--dir", required=True, help="service directory (created if missing)")
    serve.add_argument("--host", default="127.0.0.1", help="address to listen on")
    serve.add_argument("--port", type=int, default=8000, help="port (default 8000)")
    serve.add_argument("--catalog", help="reference orbits (default: built-in SIMULATED)")
    serve.add_argument("--policy", help="target allow-list (default: built-in SIMULATED)")
    serve.add_argument("--reviewers", help="reviewer registry (default: built-in SIMULATED)")
    serve.add_argument("--sites", help="sites file for IOD and TDM deliveries")
    chain = serve.add_argument_group(
        "testnet chain (phase 2)",
        "Settle funded requests on the escrow contract of Base Sepolia or a local Anvil "
        "chain. The service holds only the verifier key; every party signs its own "
        "transactions.",
    )
    chain.add_argument(
        "--network",
        choices=["base-sepolia"],
        help="a deployment this version knows: its escrow, first block and public RPC "
        "endpoint (override the endpoint with --chain-rpc)",
    )
    chain.add_argument("--chain-rpc", help="the chain's JSON-RPC endpoint")
    chain.add_argument("--escrow", help="the escrow contract's address")
    chain.add_argument(
        "--verifier-keystore", help="encrypted keystore of the verifier key (outside the repo)"
    )
    chain.add_argument(
        "--verifier-password-file",
        help="file with the keystore's password (or $ORBIT_WATCH_VERIFIER_PASSWORD_FILE; "
        "otherwise it is asked for)",
    )
    chain.add_argument(
        "--from-block",
        type=int,
        default=None,
        help="the escrow's deployment block (default: the network's, or 0)",
    )
    serve.set_defaults(handler=cmd_serve)

    keys_parser = commands.add_parser(
        "keys",
        help="manage API keys of a service directory",
        description="Manage API keys. Run while the server is stopped; a running server "
        "holds the database.",
    )
    keys_commands = keys_parser.add_subparsers(dest="keys_command", metavar="command")
    keys_commands.required = True
    create = keys_commands.add_parser("create", help="create a key and print it once")
    create.add_argument("--dir", required=True, help="service directory")
    create.add_argument(
        "--role", required=True, choices=["requester", "station", "reviewer", "admin"]
    )
    create.add_argument("--party", required=True, help="party, e.g. station:SIM-ESPOO")
    create.set_defaults(handler=cmd_keys_create)
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
    except ClientError as exc:
        _err(f"{exc.code}: {exc}")
        return EXIT_FAILED if exc.status else EXIT_USAGE
    except ChainError as exc:
        _err(f"{exc.code}: {exc}")
        return EXIT_FAILED
    except (OSError, ValueError) as exc:
        _err(str(exc))
        return EXIT_USAGE

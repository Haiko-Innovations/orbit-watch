"""Command-line interface: ``orbit-watch <command>``."""

from __future__ import annotations

import argparse
import os
import sys
from datetime import UTC, datetime
from pathlib import Path

from orbit_watch import SIMULATION_NOTICE, __version__
from orbit_watch.backup import BackupError
from orbit_watch.canonical import dumps_pretty, write_text
from orbit_watch.chain import ChainError
from orbit_watch.client import ClientError
from orbit_watch.formats import FORMATS, FormatError, Sites, load_observation_sets, owjson
from orbit_watch.formats import iod as iod_format
from orbit_watch.formats import tdm as tdm_format
from orbit_watch.storage import StorageError

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


SATCHECKER_CREDIT = (
    "Source: the IAU CPS's SatChecker (https://satchecker.cps.iau.org), element sets from "
    'Space-Track and CelesTrak. "This research made use of data and/or services provided by '
    "the International Astronomical Union Centre for the Protection of the Dark and Quiet Sky "
    '(IAU CPS) SatHub." Not for redistribution: see docs/data-sources.md.'
)


def cmd_fetch_satchecker(args: argparse.Namespace) -> int:
    from orbit_watch import orbit_cache
    from orbit_watch.fetch import FetchError
    from orbit_watch.ids import parse_catalog_number
    from orbit_watch.satchecker import fetch_nearest
    from orbit_watch.timeutil import parse_utc

    try:
        when = parse_utc(args.near)
    except ValueError as exc:
        raise FormatError(f"--near: {exc}") from None
    norad_id = parse_catalog_number(args.catnr)
    try:
        nearest = fetch_nearest(norad_id, when, kind="omm" if args.omm else "tle")
    except FetchError as exc:
        _err(str(exc))
        return EXIT_FAILED
    document = {
        "format": "orbit-watch/gp-catalog",
        "format_version": "1.0",
        "simulated": False,
        "description": "A real element set from the IAU CPS's SatChecker. Not for "
        "redistribution (decision D-06).",
        "records": [nearest.record],
    }
    write_text(args.output, dumps_pretty(document, sort_keys=False))
    print(f"wrote {args.output}: object {norad_id}, epoch {nearest.epoch}")
    if args.manifest:
        cache_dir = Path(args.cache) if args.cache else orbit_cache.default_cache_dir()
        orbit_cache.store(cache_dir, nearest)
        path = Path(args.manifest)
        manifest = (
            orbit_cache.parse_manifest(path.read_bytes())
            if path.exists()
            else orbit_cache.Manifest([], "Real reference orbits, fetched on demand.")
        )
        if manifest.add(nearest):
            orbit_cache.write_manifest(path, manifest)
            print(f"named it in {path}, and kept SatChecker's answer in {cache_dir}")
        else:
            print(f"{path} already names it")
    print(SATCHECKER_CREDIT)
    return EXIT_OK


def cmd_fetch_orbits(args: argparse.Namespace) -> int:
    from orbit_watch import orbit_cache
    from orbit_watch.fetch import FetchError

    try:
        manifest = orbit_cache.parse_manifest(Path(args.manifest).read_bytes())
    except orbit_cache.CacheError as exc:
        raise FormatError(f"{args.manifest}: {exc}") from None
    cache_dir = Path(args.cache) if args.cache else orbit_cache.default_cache_dir()
    try:
        fetched, present = orbit_cache.fill(manifest.entries, cache_dir, log=print)
    except (FetchError, orbit_cache.CacheError) as exc:
        _err(f"{exc}. Stopped at the first problem; nothing more was asked for.")
        return EXIT_FAILED
    print(f"{fetched} element set(s) fetched, {present} already in {cache_dir}")
    if args.output:
        write_text(args.output, orbit_cache.catalog_from_cache(manifest, cache_dir).decode())
        print(f"wrote {args.output} ({len(manifest.entries)} element set(s))")
    if fetched:
        print(SATCHECKER_CREDIT)
    return EXIT_OK


def cmd_fetch_score(args: argparse.Namespace) -> int:
    import json as json_module

    from orbit_watch import score
    from orbit_watch.fetch import FetchError
    from orbit_watch.ids import parse_catalog_number
    from orbit_watch.timeutil import parse_utc

    try:
        start, end = parse_utc(args.start), parse_utc(args.end)
    except ValueError as exc:
        raise FormatError(f"--start/--end: {exc}") from None
    norad_id = parse_catalog_number(args.catnr)
    try:
        fetched = score.fetch_window(norad_id, start, end)
    except (FetchError, ValueError) as exc:
        _err(f"{exc}. Stopped at the first problem; nothing more was asked for.")
        return EXIT_FAILED
    write_text(args.output, json_module.dumps(fetched, indent=1, ensure_ascii=False) + "\n")
    print(f"wrote {args.output}: {fetched['count']} observation(s) of {norad_id} from SCORE")
    print(f"Source: {score.NAME} ({score.SITE_URL}), {score.LICENCE}: credit the observers.")
    return EXIT_OK


def cmd_convert_score(args: argparse.Namespace) -> int:
    import json as json_module

    from orbit_watch import score

    assumed = score.Assumed(args.assume_angle_uncertainty, args.assume_time_uncertainty)
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    documents = []
    for path in args.inputs:
        try:
            documents.append(json_module.loads(Path(path).read_text(encoding="utf-8")))
        except ValueError as exc:
            raise FormatError(f"{path}: {exc}") from None
    try:
        sets, skipped = score.convert(documents, assumed)
    except (ValueError, KeyError) as exc:
        raise FormatError(f"cannot convert: {exc}") from None
    for observation_set in sets:
        target = out / score.file_name(observation_set)
        write_text(target, owjson.write_observation_set(observation_set))
        print(f"wrote {target} ({len(observation_set.observations)} observation(s))")
    for reason, count in sorted(skipped.items()):
        print(f"left out {count}: {reason}")
    if args.credits and sets:
        write_text(args.credits, score.credits_markdown(sets))
        print(f"wrote {args.credits}")
    stations = len({s.station.id for s in sets})
    print(
        f"{len(sets)} track(s) from {stations} station(s). {score.LICENCE}: credit the "
        "observers by their ORCID iDs."
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


class ServeError(Exception):
    """A setting the service cannot start with (``serve_app``)."""


VERIFIER_KEY_VARIABLE = "ORBIT_WATCH_VERIFIER_KEY"
# Operations (step 4.6): read-only mode, and backups for a schedule with their token.
READ_ONLY_VARIABLE = "ORBIT_WATCH_READ_ONLY"
BACKUP_TOKEN_VARIABLE = "ORBIT_WATCH_BACKUP_TOKEN"
BACKUP_RECIPIENT_VARIABLE = "ORBIT_WATCH_BACKUP_RECIPIENT"
BACKUP_IDENTITY_VARIABLE = "ORBIT_WATCH_BACKUP_IDENTITY_FILE"
_TRUE, _FALSE = ("1", "true", "yes", "on"), ("", "0", "false", "no", "off")


def _read_only(args: argparse.Namespace, environ) -> bool:
    """``--read-only``, or ``$ORBIT_WATCH_READ_ONLY`` set to 1, true, yes or on."""
    setting = (environ.get(READ_ONLY_VARIABLE) or "").strip().lower()
    if setting not in _TRUE + _FALSE:
        raise ServeError(f"${READ_ONLY_VARIABLE}: give 1 or 0 (true or false), not {setting!r}")
    return bool(getattr(args, "read_only", False)) or setting in _TRUE


def serve_app(args: argparse.Namespace, *, environ=None):
    """The service's ASGI application from ``orbit-watch serve``'s options: what ``serve``
    runs, and what ``orbit_watch.asgi`` gives any ASGI server (step 4.5). Returns the
    application, the service and the lines to tell the operator. Raises ``ServeError``."""
    environ = os.environ if environ is None else environ
    try:
        from orbit_watch.api import create_app
    except ImportError:
        raise ServeError(
            'the API needs the optional "api" dependencies: pip install "orbit-watch[api]"'
        ) from None
    from orbit_watch.api.limits import Limits, LimitsError
    from orbit_watch.service import open_service

    if args.web and not (Path(args.web) / "index.html").is_file():
        raise ServeError(
            f"{args.web} has no index.html: build the web application (cd web && npm run build)"
        )
    for origin in args.origin or ():
        if not origin.startswith(("http://", "https://")) or origin.rstrip("/").count("/") > 2:
            raise ServeError(f"--origin {origin}: give a web origin such as https://orbit.example")
    try:
        limits = Limits.parse(args.limits)
    except LimitsError as error:
        raise ServeError(f"--limits: {error}") from None
    station_decimals = _station_decimals(args.station_decimals)
    if station_decimals == -1:
        raise ServeError("--station-decimals: give a whole number from 0 to 8, or off")
    read_only = _read_only(args, environ)
    backup_token = environ.get(BACKUP_TOKEN_VARIABLE) or None
    backup_recipient = (
        getattr(args, "backup_recipient", None) or environ.get(BACKUP_RECIPIENT_VARIABLE) or None
    )
    if backup_token and not backup_recipient:
        raise ServeError(
            f"${BACKUP_TOKEN_VARIABLE} needs the age public key that backups are encrypted to: "
            f"--backup-recipient or ${BACKUP_RECIPIENT_VARIABLE}"
        )
    if backup_recipient:
        from orbit_watch import backup

        try:
            backup.recipient(backup_recipient)
        except backup.BackupError as error:
            raise ServeError(f"--backup-recipient: {error}") from None
    registry, context, notes = _service_inputs(args)
    verifier_key = environ.get(VERIFIER_KEY_VARIABLE) or None
    chain = None
    if args.network:
        if not (args.verifier_keystore or verifier_key):
            raise ServeError(
                f"on {args.network}, give --verifier-keystore, or the key in "
                f"${VERIFIER_KEY_VARIABLE}"
            )
        _apply_network(args)
    if args.chain_rpc or args.escrow or args.verifier_keystore:
        if not (args.chain_rpc and args.escrow and (args.verifier_keystore or verifier_key)):
            raise ServeError(
                "on a chain, give --chain-rpc, --escrow and --verifier-keystore together, or "
                "--network and --verifier-keystore"
            )
        try:
            chain = _chain_link(args, verifier_key)
        except ImportError:
            raise ServeError(
                'the chain needs the optional "evm" dependencies: pip install "orbit-watch[evm]"'
            ) from None
    database = _database(args, environ)
    if database is None:
        raise ServeError(
            "give the service's PostgreSQL database: --database, or "
            f"{' or '.join('$' + name for name in DATABASE_VARIABLES)}"
        )
    role = environ.get(DATABASE_ROLE_VARIABLE) or None
    service = open_service(
        _with_sslmode(database, environ.get(DATABASE_SSLMODE_VARIABLE)),
        registry,
        context,
        chain=chain,
        database_role=role,
    )
    lines = [f"note: {note}" for note in notes]
    origins = args.origin or _default_origins(args.host, args.port)
    lines.append(f"Orbit Watch API {__version__} for {_database_name(service)}")
    if role:
        lines.append(f"Changes run as the database role {role}")
    if args.web:
        lines.append(f"Web application on http://{args.host}:{args.port}/")
    if chain is None:
        lines.append("Local use without a chain, no TLS. All bundled data is SIMULATED.")
    else:
        lines.append("Testnet only, no real value. All bundled data is SIMULATED.")
        lines.append(f"Wallets sign in from: {', '.join(origins)}")
        lines.append(
            f"On chain {chain.chain.chain_id} ({chain.notice}): escrow "
            f"{chain.chain.escrow.address}, verifier {chain.verifier.address}"
        )
    secret = next((environ[n] for n in FOLLOW_SECRET_VARIABLES if environ.get(n)), None)
    app = create_app(
        service,
        web=args.web,
        origins=origins,
        follow_secret=secret,
        limits=limits,
        client_ip_header=args.client_ip_header,
        station_decimals=station_decimals,
        read_only=read_only,
        backup_token=backup_token,
        backup_recipient=backup_recipient,
    )
    if limits is None:
        lines.append("Limits against abuse: off")
    else:
        where = f"the {args.client_ip_header} header" if args.client_ip_header else "connections"
        lines.append(f"Limits against abuse: on (IP addresses from {where})")
    if station_decimals is None:
        lines.append("Station coordinates: kept as given")
    else:
        lines.append(f"Station coordinates: kept to {station_decimals} decimals of a degree")
    if secret:
        lines.append("A schedule may run the follower: /v1/internal/follow (with its secret)")
    if backup_token:
        lines.append(
            "A schedule may take backups: /v1/internal/backup (with its token), encrypted to "
            f"{backup_recipient.strip()}"
        )
    if read_only:
        lines.append("READ-ONLY: every change is refused and the follower waits")
    return app, service, lines


def cmd_serve(args: argparse.Namespace) -> int:
    try:
        import uvicorn
    except ImportError:
        _err('the API needs the optional "api" dependencies: pip install "orbit-watch[api]"')
        return EXIT_USAGE
    try:
        app, service, lines = serve_app(args)
    except ServeError as error:
        _err(str(error))
        return EXIT_USAGE
    for line in lines:
        print(line)
    print(f"Listening on http://{args.host}:{args.port}/v1/")
    chain = service.chain
    if chain is not None and app.state.api.read_only:
        # Following the chain writes, and read-only mode writes nothing (step 4.6).
        print(f"Read-only: the chain as last followed, block {chain.synced_block()}")
    elif chain is not None:
        # Catch up before answering, so the first request does not wait for it.
        try:
            chain.sync()
        except Exception as error:  # the node is down; each request tries again
            _err(f"warning: cannot read the chain yet: {error}")
        else:
            print(f"Followed the chain to block {chain.synced_block()}")
    from orbit_watch.api import start_follower

    if args.follow:
        start_follower(app, args.follow)
        print(f"The follower runs every {args.follow:g} seconds")
    try:
        uvicorn.run(app, host=args.host, port=args.port, access_log=args.access_log)
    finally:
        service.storage.close()
    return EXIT_OK


def _station_decimals(setting: str) -> int | None:
    """``--station-decimals``: None for off, -1 for a setting that is neither."""
    text = setting.strip().lower()
    if text == "off":
        return None
    if text.isdigit() and int(text) <= 8:
        return int(text)
    return -1


def _default_origins(host: str, port: int) -> list[str]:
    """Where a browser opens the service by default: its own address."""
    origins = [f"http://{host}:{port}"]
    if host == "127.0.0.1":
        origins.append(f"http://localhost:{port}")
    return origins


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
    # The dedicated endpoint, if given, with the public one as its fallback (step 4.3).
    args.fallback_rpc = public_rpc(record["chain_id"])
    args.chain_rpc = args.chain_rpc or args.fallback_rpc
    if getattr(args, "safe", None) is None:
        args.safe = record.get("safe")


def _chain_link(args: argparse.Namespace, verifier_key: str | None = None):
    """The service's link to a testnet chain, with the verifier key (step 2.6): from its
    keystore, or else as ``verifier_key`` (``$ORBIT_WATCH_VERIFIER_KEY``, step 4.5)."""
    import stat

    from web3 import Web3

    from orbit_watch.chain.client import OrbitWatchChain
    from orbit_watch.chain.link import ChainLink
    from orbit_watch.chain.rpc import ServiceRpc, service_endpoints
    from orbit_watch.chain.wallet import load_keystore, read_password

    # The endpoint's URL may hold a provider's key: it is never printed (step 4.3).
    endpoints = service_endpoints(args.chain_rpc, getattr(args, "fallback_rpc", None))
    chain = OrbitWatchChain(Web3(ServiceRpc(endpoints)), args.escrow)
    if args.verifier_keystore:
        keystore = Path(args.verifier_keystore)
        if keystore.stat().st_mode & (stat.S_IRWXG | stat.S_IRWXO):
            _err(f"warning: {keystore} can be read by other users; chmod 600 it")
        password = read_password(
            args.verifier_password_file,
            "verifier keystore password: ",
            env="ORBIT_WATCH_VERIFIER_PASSWORD_FILE",
        )
        verifier = load_keystore(keystore, password)
    else:
        from eth_account import Account

        try:
            verifier = Account.from_key(verifier_key)
        except Exception:  # never say more: the message would hold the key
            raise ServeError(f"${VERIFIER_KEY_VARIABLE} is not a private key") from None
    return ChainLink(
        chain,
        verifier,
        from_block=args.from_block,
        safe=getattr(args, "safe", None),
        confirmations=args.confirmations,
    )


DATABASE_VARIABLES = ("ORBIT_WATCH_DATABASE_URL", "DATABASE_URL")
# The role that the service's changes run as, and the TLS mode to connect with (step 4.5).
DATABASE_ROLE_VARIABLE = "ORBIT_WATCH_DATABASE_ROLE"
DATABASE_SSLMODE_VARIABLE = "ORBIT_WATCH_DATABASE_SSLMODE"
# The follower's secret for a schedule (step 4.2): Vercel's cron jobs send CRON_SECRET.
FOLLOW_SECRET_VARIABLES = ("ORBIT_WATCH_FOLLOW_SECRET", "CRON_SECRET")
DATABASE_HELP = (
    "the service's PostgreSQL database, as a libpq URL or connection string (default: "
    "$ORBIT_WATCH_DATABASE_URL or $DATABASE_URL; a password on the command line ends up in "
    "the shell history)"
)


def _database(args: argparse.Namespace, environ=None) -> str | None:
    """The service's PostgreSQL database: --database, or the first of
    ``DATABASE_VARIABLES`` that is set (decision P4-04)."""
    environ = os.environ if environ is None else environ
    found = args.database or next(
        (environ[name] for name in DATABASE_VARIABLES if environ.get(name)), None
    )
    if not found:
        _err(
            "give the service's PostgreSQL database: --database, or "
            f"{' or '.join('$' + name for name in DATABASE_VARIABLES)}"
        )
    return found


def _with_sslmode(database: str, sslmode: str | None) -> str:
    """The connection string with libpq's ``sslmode`` set (``verify-full`` on the public
    service, P4-10), and the root certificates that ``verify-full`` checks against."""
    if not sslmode:
        return database
    from psycopg.conninfo import conninfo_to_dict, make_conninfo

    params = conninfo_to_dict(database)
    params["sslmode"] = sslmode
    if sslmode == "verify-full" and not params.get("sslrootcert"):
        try:
            import certifi  # comes with the evm extra (requests)

            params["sslrootcert"] = certifi.where()
        except ImportError:
            params["sslrootcert"] = "system"
    return make_conninfo(**params)


def _database_name(service) -> str:
    """The database and schema, for messages; never the connection string, which may hold
    a password."""
    db = service.storage.db
    info = db.connection.info
    return f"the database {info.dbname} on {info.host}, schema {db.schema}"


def cmd_keys_create(args: argparse.Namespace) -> int:
    from orbit_watch.api import keys
    from orbit_watch.storage import Storage

    database = _database(args)
    if database is None:
        return EXIT_USAGE
    storage = Storage(database)
    try:
        with storage.db.transaction():
            key = keys.create_key(storage.db, args.party, args.role, datetime.now(tz=UTC))
    except keys.ApiKeyError as error:
        _err(str(error))
        return EXIT_USAGE
    finally:
        storage.close()
    print(key)
    article = "an" if args.role == "admin" else "a"
    _err(f"created {article} {args.role} key for {args.party}; it is shown only this once")
    return EXIT_OK


def cmd_backup_create(args: argparse.Namespace) -> int:
    """Take an encrypted backup of a service's database into a file (step 4.6): for a
    server of our own (decision P4-05); the public service's schedule calls the API."""
    from orbit_watch import backup
    from orbit_watch.storage import Database

    recipient = args.recipient or os.environ.get(BACKUP_RECIPIENT_VARIABLE)
    if not recipient:
        _err(f"give the age public key to encrypt to: --recipient or ${BACKUP_RECIPIENT_VARIABLE}")
        return EXIT_USAGE
    database = _database(args)
    if database is None:
        return EXIT_USAGE
    output = Path(args.output)
    if output.exists():
        _err(f"{output} exists: a backup never overwrites a file")
        return EXIT_USAGE
    with Database(database) as db:
        if not db.schema_version():
            _err(f"schema {db.schema} has no Orbit Watch tables")
            return EXIT_USAGE
        with db.transaction():
            archive = backup.take(db, datetime.now(tz=UTC))
    encrypted = backup.encrypt(archive, recipient)
    output.write_bytes(encrypted)
    print(f"{output}: {len(encrypted)} bytes, encrypted to {recipient.strip()}")
    return EXIT_OK


def cmd_backup_restore(args: argparse.Namespace) -> int:
    """Restore a backup into an empty database (step 4.6)."""
    from orbit_watch import backup
    from orbit_watch.storage import Database

    data = Path(args.file).read_bytes()
    if backup.is_encrypted(data):
        identity_file = args.identity or os.environ.get(BACKUP_IDENTITY_VARIABLE)
        if not identity_file:
            _err(
                "the backup is encrypted: give the age private key's file with --identity or "
                f"${BACKUP_IDENTITY_VARIABLE}"
            )
            return EXIT_USAGE
        data = backup.decrypt(data, Path(identity_file).read_text(encoding="utf-8"))
    database = _database(args)
    if database is None:
        return EXIT_USAGE
    with Database(database) as db:
        result = backup.restore(db, data)
        name = f"schema {db.schema} of the database {db.connection.info.dbname}"
    rows = sum(entry["rows"] for entry in result["tables"])
    print(
        f"Restored the backup of {result['taken_at']} (Orbit Watch {result['service_version']}, "
        f"schema version {result['schema_version']}) into {name}: {len(result['tables'])} "
        f"tables, {rows} rows; schema version now {result['restored_schema_version']}"
    )
    for entry in result["tables"]:
        print(f"  {entry['name']}: {entry['rows']}")
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
        description="Download current GP element sets in OMM CSV form from CelesTrak, "
        "compressed. Makes exactly one request, never retries, and does not download the same "
        "file again within two hours (CelesTrak updates GP data every two hours). Ask for one "
        "object or a small group: CelesTrak limits large lists such as 'active'.",
    )
    fetch.add_argument("--catnr", help="catalogue number")
    fetch.add_argument("--group", help="CelesTrak group, e.g. cubesat, amateur, science")
    fetch.add_argument("--intdes", help="international designator, e.g. 2026-123")
    fetch.add_argument("-o", "--output", required=True, help="output file (.csv)")
    fetch.add_argument(
        "--force", action="store_true", help="download even if the file is younger than two hours"
    )
    fetch.set_defaults(handler=cmd_fetch_gp)

    past = commands.add_parser(
        "fetch-satchecker",
        help="download the past element set nearest a time from the IAU CPS's SatChecker",
        description="Download the element set of one object nearest a given time from the "
        "IAU CPS's SatChecker (one request, no retries), for observations from the past. "
        "TLEs are converted to OMM form. With --manifest, the set is also named in a "
        "reference-orbit manifest and SatChecker's answer kept in the cache.",
    )
    past.add_argument("--catnr", required=True, help="catalogue number")
    past.add_argument(
        "--near", required=True, help="the time, UTC (YYYY-MM-DDThh:mm:ssZ), e.g. mid-track"
    )
    past.add_argument(
        "--omm", action="store_true", help="ask for an OMM instead of a TLE (newer data only)"
    )
    past.add_argument("-o", "--output", required=True, help="output catalogue (.json)")
    past.add_argument("--manifest", help="name the set in this manifest (created if missing)")
    past.add_argument("--cache", help="cache directory (default: $ORBIT_WATCH_CACHE or ~/.cache)")
    past.set_defaults(handler=cmd_fetch_satchecker)

    score_fetch = commands.add_parser(
        "fetch-score",
        help="download real observations of one object from the IAU CPS's SCORE (CC BY 4.0)",
        description="Download SCORE's observations of one object in a time window, politely: "
        "pages of at most 100, at least a second apart, stopping at the first answer that is "
        "not 200. The observations are CC BY 4.0: credit the observers.",
    )
    score_fetch.add_argument("--catnr", required=True, help="catalogue number")
    score_fetch.add_argument("--start", required=True, help="window start, UTC")
    score_fetch.add_argument("--end", required=True, help="window end, UTC")
    score_fetch.add_argument("-o", "--output", required=True, help="output file (.json)")
    score_fetch.set_defaults(handler=cmd_fetch_score)

    score_convert = commands.add_parser(
        "convert-score",
        help="convert observations fetched from SCORE into Orbit Watch observation sets",
        description="Group observations fetched with fetch-score into tracks (one object, one "
        "station: place, instrument and observers), and write each track as an observation set "
        "(format 1.1) that names SCORE, the observers, SCORE's observation IDs and the "
        "licence. SCORE often gives no uncertainty: the --assume options say what to assume, "
        "and each file records it. Without them such observations are left out.",
    )
    score_convert.add_argument("inputs", nargs="+", help="files written by fetch-score")
    score_convert.add_argument("--out", required=True, help="output directory")
    score_convert.add_argument(
        "--assume-angle-uncertainty",
        type=float,
        metavar="ARCSEC",
        help="one-sigma angle uncertainty to assume where SCORE gives none",
    )
    score_convert.add_argument(
        "--assume-time-uncertainty",
        type=float,
        metavar="SECONDS",
        help="time uncertainty to assume where SCORE gives none",
    )
    score_convert.add_argument(
        "--credits", help="also write the credits (observers, statements) to this Markdown file"
    )
    score_convert.set_defaults(handler=cmd_convert_score)

    orbits = commands.add_parser(
        "fetch-orbits",
        help="fetch the element sets a reference-orbit manifest names into the local cache",
        description="Fetch every element set that a reference-orbit manifest names and the "
        "cache lacks, from the IAU CPS's SatChecker: one request at a time, two seconds apart, "
        "stopping at the first answer that is not 200 and at any set whose SHA-256 is not the "
        "manifest's. Real element sets are never committed (decision D-06).",
    )
    orbits.add_argument("manifest", help="an orbit-watch/reference-orbits manifest")
    orbits.add_argument("--cache", help="cache directory (default: $ORBIT_WATCH_CACHE or ~/.cache)")
    orbits.add_argument("-o", "--output", help="also write the catalogue the manifest names")
    orbits.set_defaults(handler=cmd_fetch_orbits)

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
        help="run the HTTP API for a service's PostgreSQL database",
        description="Run the HTTP API. The service's state lives in PostgreSQL (--database). "
        "Needs the optional api dependencies. No TLS of its own: put it behind a proxy or a "
        "platform that provides HTTPS.",
    )
    serve.add_argument(
        "--database",
        help=DATABASE_HELP,
    )
    serve.add_argument("--host", default="127.0.0.1", help="address to listen on")
    serve.add_argument(
        "--follow",
        type=float,
        default=0,
        metavar="SECONDS",
        help="run the follower in this process every SECONDS: apply the chain's events and "
        "passed deadlines, attest and settle without anyone calling tick (default: off; a "
        "schedule can call /v1/internal/follow with $ORBIT_WATCH_FOLLOW_SECRET instead)",
    )
    serve.add_argument("--port", type=int, default=8000, help="port (default 8000)")
    serve.add_argument(
        "--limits",
        default=os.environ.get("ORBIT_WATCH_LIMITS"),
        metavar="SETTING",
        help="limits against abuse (default: $ORBIT_WATCH_LIMITS, or else the defaults): off, "
        'or a JSON object that changes some, e.g. \'{"quality": {"ip": [60, 3600]}}\' '
        "(docs/api.md)",
    )
    serve.add_argument(
        "--client-ip-header",
        default=os.environ.get("ORBIT_WATCH_CLIENT_IP_HEADER") or None,
        metavar="HEADER",
        help="behind a proxy you trust, the header it sets to the caller's IP address, e.g. "
        "x-real-ip on Vercel (default: $ORBIT_WATCH_CLIENT_IP_HEADER, or else the "
        "connection's address). Never name a header that callers can set themselves",
    )
    serve.add_argument(
        "--station-decimals",
        default=os.environ.get("ORBIT_WATCH_STATION_DECIMALS") or "2",
        metavar="N",
        help="keep station coordinates to N decimals of a degree: profiles are rounded and "
        "more precise delivered files refused (default: $ORBIT_WATCH_STATION_DECIMALS, or "
        "else 2, about a kilometre; off keeps them as given). Docs: personal-data.md",
    )
    serve.add_argument(
        "--read-only",
        action="store_true",
        help="refuse every change and let the follower wait, for maintenance; reading, the "
        "public pages and signing in still work (or $ORBIT_WATCH_READ_ONLY=1). Docs: "
        "operations.md",
    )
    serve.add_argument(
        "--backup-recipient",
        metavar="AGE_PUBLIC_KEY",
        help="the age public key (age1…) that backups are encrypted to (default: "
        "$ORBIT_WATCH_BACKUP_RECIPIENT). With $ORBIT_WATCH_BACKUP_TOKEN, a schedule may take "
        "backups at /v1/internal/backup. Docs: operations.md",
    )
    serve.add_argument(
        "--access-log",
        action="store_true",
        help="log every request with the caller's IP address (off by default: the service "
        "writes no IP address to its logs; keep such a log for at most 30 days)",
    )
    serve.add_argument("--catalog", help="reference orbits (default: built-in SIMULATED)")
    serve.add_argument("--policy", help="target allow-list (default: built-in SIMULATED)")
    serve.add_argument("--reviewers", help="reviewer registry (default: built-in SIMULATED)")
    serve.add_argument("--sites", help="sites file for IOD and TDM deliveries")
    serve.add_argument(
        "--web",
        metavar="DIR",
        help="also serve the built web application from DIR (web/dist) at / (phase 3)",
    )
    serve.add_argument(
        "--origin",
        action="append",
        metavar="URL",
        help="a web origin that browsers may sign in from, as they see it (repeatable; "
        "default: http://HOST:PORT, and http://localhost:PORT on 127.0.0.1)",
    )
    chain = serve.add_argument_group(
        "testnet chain (phase 2)",
        "Settle funded requests on the escrow contract of Base Sepolia or a local Anvil "
        "chain. The service holds only the verifier key; every party signs its own "
        "transactions.",
    )
    chain.add_argument(
        "--network",
        choices=["base-sepolia"],
        help="a deployment this version knows: its escrow and public RPC endpoint "
        "(override the endpoint with --chain-rpc)",
    )
    chain.add_argument(
        "--chain-rpc",
        default=os.environ.get("ORBIT_WATCH_CHAIN_RPC") or None,
        help="the chain's JSON-RPC endpoint (default: $ORBIT_WATCH_CHAIN_RPC). A dedicated "
        "endpoint's URL holds its key: give it in the environment, not here, where other "
        "users of the machine can see it. With --network, the public endpoint is its "
        "fallback",
    )
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
        help="a new service directory follows the chain from this block (default: the "
        "current block, since no earlier event can belong to its requests)",
    )
    chain.add_argument(
        "--confirmations",
        type=int,
        default=None,
        metavar="BLOCKS",
        help="apply a block's events once this many blocks follow it (default: 10 on Base "
        "Sepolia, about two seconds; 0 on a local Anvil chain)",
    )
    chain.add_argument(
        "--safe",
        help="the Safe that proposes to the reviewer registry's timelock, for the "
        "administrator view (default with --network: the deployment's Safe)",
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
    create.add_argument(
        "--database",
        help=DATABASE_HELP,
    )
    create.add_argument(
        "--role", required=True, choices=["requester", "station", "reviewer", "admin"]
    )
    create.add_argument("--party", required=True, help="party, e.g. station:SIM-ESPOO")
    create.set_defaults(handler=cmd_keys_create)

    backup_parser = commands.add_parser(
        "backup",
        help="take or restore an encrypted backup of a service's database",
        description="Backups of a service's database, encrypted with age to the maintainer's "
        "public key (step 4.6, docs/operations.md). Needs the optional api dependencies.",
    )
    backup_commands = backup_parser.add_subparsers(dest="backup_command", metavar="command")
    backup_commands.required = True
    take = backup_commands.add_parser(
        "create", help="take a backup into a new file, encrypted to an age public key"
    )
    take.add_argument("--database", help=DATABASE_HELP)
    take.add_argument(
        "--recipient",
        metavar="AGE_PUBLIC_KEY",
        help="the age public key, age1… (default: $ORBIT_WATCH_BACKUP_RECIPIENT)",
    )
    take.add_argument("--output", required=True, help="the new file (….tar.gz.age)")
    take.set_defaults(handler=cmd_backup_create)
    restore = backup_commands.add_parser("restore", help="restore a backup into an empty database")
    restore.add_argument("file", help="the backup (….tar.gz.age, or a decrypted ….tar.gz)")
    restore.add_argument(
        "--identity",
        metavar="FILE",
        help="the age private key's file, as age-keygen writes it (default: "
        "$ORBIT_WATCH_BACKUP_IDENTITY_FILE)",
    )
    restore.add_argument(
        "--database", help=DATABASE_HELP + "; it must be empty: a new database or schema"
    )
    restore.set_defaults(handler=cmd_backup_restore)
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
    except (ChainError, BackupError, StorageError) as exc:
        _err(f"{exc.code}: {exc}")
        return EXIT_FAILED
    except (OSError, ValueError) as exc:
        _err(str(exc))
        return EXIT_USAGE

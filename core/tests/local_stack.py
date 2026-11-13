"""A local stack for developing and testing the web application (phase 3, step 3.1).

One command starts, on this machine only:

* a LOCAL Anvil chain with Base Sepolia's EAS code and fresh Orbit Watch contracts, whose
  clock starts at 2026-11-01 12:00 UTC, before the SIMULATED requests' window; on port
  8545 by default, where wallets look for a local chain (31337);
* the request service on that chain, with the API and, given ``--web``, the built web
  application on one port;
* SIMULATED parties (a requester, four stations, the reviewers) with LOCAL TEST keys and
  registered wallets, and worthless TestUSD for the requester;
* three SIMULATED requests: two funded and open for observers, one opened but not funded;
* one SIMULATED request that ran its course: SIM-ESPOO delivered good observations, nobody
  challenged, and the escrow credited the station 1 TESTUSD and the requester 0.3 back,
  for them to withdraw. Seeding it moves the chain's clock to 2026-11-02 05:01 UTC;
* fresh SIMULATED good observations of SIM-CUBESAT-A by SIM-ESPOO, never delivered yet,
  in ``datasets/`` (the service refuses data delivered before).

    cd contracts && forge build
    cd ../web && npm run build
    cd ../core && uv run python tests/local_stack.py --web ../web/dist

It writes ``local-stack.json`` (the URLs, every party's API key, wallet address and
keystore) into its directory and runs until stopped; a temporary directory is removed
then. Nothing here touches a public network. The keys are public test keys that anyone
can recompute from the parties' names: never use them anywhere but a local chain.
"""

from __future__ import annotations

import argparse
import io
import json
import shutil
import signal
import sys
import tempfile
import threading
import time
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

from anvil import Deployment, unavailable
from chain_world import GENESIS, PLATFORM, REGISTRY, REVIEWERS, VERIFIER
from helpers import catalog_bytes, policy_bytes

from orbit_watch.catalog import parse_catalog
from orbit_watch.sim.phase1_demo import ESPOO, KUOPIO, OULU, REQUESTER, TAMPERE, _deliveries
from orbit_watch.sim.phase1_demo import _packaged as packaged
from orbit_watch.sim.phase1_demo import _request_bytes as request_bytes
from orbit_watch.sim.scenarios import TARGET, _sim_json, _window
from orbit_watch.sim.simulator import load_profile
from orbit_watch.timeutil import parse_utc

STATIONS = (ESPOO, OULU, KUOPIO, TAMPERE)
PASSWORD = "local stack test password"  # protects LOCAL TEST keys only
BUDGET = 100_000_000  # 100 TestUSD (6 decimals), worthless
DELIVERY_DEADLINE = "2026-11-03T12:00:00Z"
DEV_SERVER_PORT = 5173  # npm run dev (web/vite.config.ts)
REQUESTS = [  # request id, title, funded
    ("SIM-REQ-3001", "Identify and track SIM-CUBESAT-A after deployment", True),
    ("SIM-REQ-3002", "Track SIM-CUBESAT-A on its second night", True),
    ("SIM-REQ-3003", "Confirm SIM-CUBESAT-A's orbit (not funded yet)", False),
]
SETTLED = ("SIM-REQ-3000", "Identify SIM-CUBESAT-A (delivered and accepted)")
AFTER_WINDOW = "2026-11-02T04:00:00Z"  # the requests' window ended at 03:00
AFTER_CHALLENGE = "2026-11-02T05:01:00Z"  # its one-hour challenge period is over
ADMIN = "admin:local"
FRESH_SEEDS = (201, 202)  # SIM-ESPOO's good observations for tests, unlike the seeded ones


class StackError(RuntimeError):
    pass


class LocalStack:
    """The running stack; ``stop()`` ends it."""

    def __init__(self, directory: Path, port: int, web: Path | None, chain_port: int = 0):
        import uvicorn

        from orbit_watch.api import create_app, keys
        from orbit_watch.chain.client import OrbitWatchChain
        from orbit_watch.chain.link import ChainLink
        from orbit_watch.service import VerificationContext, open_service

        self.directory = directory
        self.datasets: list[str] = []
        self.parties = [REQUESTER, *STATIONS, *REVIEWERS]
        self.deployment = Deployment(
            GENESIS,
            reviewers=REVIEWERS,
            platform=PLATFORM,
            verifier=VERIFIER,
            parties=[*self.parties, PLATFORM],
            port=chain_port,
        )
        local = self.deployment.chain
        self.rpc = local.w3.provider.endpoint_uri
        local.send(
            self.deployment.deployer,
            self.deployment.usd.functions.mint(self.address(REQUESTER), BUDGET),
        )
        chain = OrbitWatchChain(local.w3, self.deployment.escrow.address)
        link = ChainLink(chain, self.deployment.accounts[VERIFIER], receipt_timeout=30)
        context = VerificationContext(catalog=catalog_bytes(), policy=policy_bytes())
        self.service = open_service(directory / "service", REGISTRY, context, chain=link)
        with self.service.storage.db.transaction():
            now = link.now()
            self.admin = keys.create_key(self.service.storage.db, ADMIN, "admin", now)
            self.keys = {
                party: keys.create_key(self.service.storage.db, party, party.split(":")[0], now)
                for party in self.parties
            }
        self.api = f"http://127.0.0.1:{port}"
        # Browsers sign in from the stack itself or from Vite's development server.
        self.origins = [
            f"http://{host}:{p}"
            for p in (port, DEV_SERVER_PORT)
            for host in ("127.0.0.1", "localhost")
        ]
        self.server = uvicorn.Server(
            uvicorn.Config(
                create_app(self.service, web=web, origins=self.origins),
                host="127.0.0.1",
                port=port,
                log_level="warning",
            )
        )
        self.thread = threading.Thread(target=self.server.run, daemon=True)
        self.thread.start()
        deadline = time.monotonic() + 15
        while not self.server.started and time.monotonic() < deadline:
            if not self.thread.is_alive():
                raise StackError(f"the server did not start on port {port}")
            time.sleep(0.05)
        if not self.server.started:
            raise StackError(f"the server did not start on port {port}")

    def address(self, party: str) -> str:
        return self.deployment.accounts[party].address

    def keystore(self, party: str) -> Path:
        return self.directory / "wallets" / f"{party.replace(':', '-')}.json"

    def write_wallets(self) -> None:
        from eth_account import Account

        wallets = self.directory / "wallets"
        wallets.mkdir(parents=True, exist_ok=True)
        (wallets / "password").write_text(PASSWORD + "\n", encoding="utf-8")
        for party in self.parties:
            encrypted = Account.encrypt(
                self.deployment.accounts[party].key, PASSWORD, kdf="pbkdf2", iterations=1000
            )
            self.keystore(party).write_text(json.dumps(encrypted), encoding="utf-8")

    def cli(self, party: str, *argv: str, sign: bool = False) -> str:
        """Run ``orbit-watch`` as ``party``, with its own keystore when it signs."""
        from orbit_watch.cli import main

        key = self.admin if party == ADMIN else self.keys[party]
        args = [*argv, "--json", "--api", self.api, "--key", key]
        if sign:
            args += [
                "--keystore",
                str(self.keystore(party)),
                "--password-file",
                str(self.directory / "wallets" / "password"),
                "--rpc",
                self.rpc,
            ]
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            code = main(args)
        if code != 0:
            raise StackError(f"{party}: orbit-watch {' '.join(argv)}: {err.getvalue().strip()}")
        return out.getvalue()

    def seed(self) -> None:
        """Wallets for every party and the SIMULATED requests."""
        self.write_wallets()
        for party in self.parties:
            self.cli(party, "wallet", "register", sign=True)
        documents = self.directory / "requests"
        documents.mkdir(exist_ok=True)
        for request_id, title, funded in REQUESTS:
            document = documents / f"{request_id}.json"
            document.write_bytes(request_bytes(request_id, title))
            self.cli(
                REQUESTER,
                "request",
                "create",
                str(document),
                "--delivery-deadline",
                DELIVERY_DEADLINE,
            )
            self.cli(REQUESTER, "request", "open", request_id)
            if funded:
                self.cli(
                    REQUESTER,
                    "request",
                    "fund",
                    request_id,
                    "--observer",
                    "1",
                    "--reviewer",
                    "0.1",
                    sign=True,
                )

    def travel(self, when: str) -> None:
        """Move the local chain's clock forward (only a local chain can)."""
        self.service.chain.chain.travel_to(int(parse_utc(when).timestamp()))

    def seed_settled(self) -> None:
        """A request that ran its course, so that SIM-ESPOO and the requester have credit in
        the escrow to withdraw."""
        request_id, title = SETTLED
        documents = self.directory / "requests"
        document = documents / f"{request_id}.json"
        document.write_bytes(request_bytes(request_id, title))
        self.cli(
            REQUESTER,
            "request",
            "create",
            str(document),
            "--delivery-deadline",
            DELIVERY_DEADLINE,
            "--challenge-period-hours",
            "1",
        )
        self.cli(REQUESTER, "request", "open", request_id)
        self.cli(
            REQUESTER,
            "request",
            "fund",
            request_id,
            "--observer",
            "1",
            "--reviewer",
            "0.1",
            sign=True,
        )
        self.cli(ESPOO, "reserve", request_id, sign=True)
        self.travel(AFTER_WINDOW)
        observations = documents / f"{request_id}.observations.json"
        good = _deliveries(parse_catalog(packaged("catalog.json")))["SIM-REQ-1001"]
        observations.write_bytes(good)
        self.cli(ESPOO, "submit", str(observations), "--request", request_id, sign=True)
        self.travel(AFTER_CHALLENGE)
        self.cli(ADMIN, "admin", "tick")
        settled = json.loads(self.cli(REQUESTER, "request", "show", request_id))
        if settled["summary"]["outcome"] != "accepted":
            raise StackError(f"{request_id} was not accepted: {settled['summary']}")

    def write_datasets(self) -> list[str]:
        """Good observations that pass verification and were never delivered."""
        folder = self.directory / "datasets"
        folder.mkdir(exist_ok=True)
        catalog = parse_catalog(packaged("catalog.json"))
        start, end = _window()
        written = []
        for seed in FRESH_SEEDS:
            path = folder / f"station-SIM-ESPOO-{seed}.json"
            path.write_bytes(
                _sim_json(
                    catalog,
                    target_id=TARGET,
                    profile=load_profile("sim-cmos-gps"),
                    start=start,
                    end=end,
                    seed=seed,
                    max_passes=2,
                )
            )
            written.append(str(path))
        return written

    def describe(self) -> dict:
        return {
            "notice": "LOCAL Anvil test chain, no real value. All data and parties are SIMULATED.",
            "api": self.api,
            "web": self.api + "/",
            "origins": self.origins,
            "chain_rpc": self.rpc,
            "chain_id": 31337,
            "escrow": self.deployment.escrow.address,
            "token": self.deployment.usd.address,
            "admin_key": self.admin,
            "password_file": str(self.directory / "wallets" / "password"),
            "parties": {
                party: {
                    "key": self.keys[party],
                    "address": self.address(party),
                    "keystore": str(self.keystore(party)),
                    "private_key": "0x" + self.deployment.accounts[party].key.hex(),
                }
                for party in self.parties
            },
            "requests": [request_id for request_id, _, _ in REQUESTS],
            "settled": SETTLED[0],
            "datasets": {ESPOO: self.datasets},
        }

    def stop(self) -> None:
        self.server.should_exit = True
        self.thread.join(timeout=10)
        self.service.storage.close()
        self.deployment.chain.stop()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Run a LOCAL Orbit Watch stack (Anvil, contracts, service, SIMULATED "
        "parties and requests) for the web application. No real value."
    )
    parser.add_argument("--port", type=int, default=8787, help="API and web port (8787)")
    parser.add_argument("--web", type=Path, help="the built web application (web/dist)")
    parser.add_argument(
        "--chain-port",
        type=int,
        default=8545,
        help="the local chain's port (8545, where wallets look for chain 31337; 0: any free one)",
    )
    parser.add_argument(
        "--dir", type=Path, help="where the stack keeps its state (default: a new temporary one)"
    )
    parser.add_argument(
        "--replace",
        action="store_true",
        help="start afresh in --dir if it holds an earlier local stack (its local-stack.json)",
    )
    args = parser.parse_args(argv)
    reason = unavailable()
    if reason:
        print(f"local stack: {reason}", file=sys.stderr)
        return 2
    temporary = args.dir is None
    directory = args.dir or Path(tempfile.mkdtemp(prefix="orbit-watch-local-"))
    if args.replace and (directory / "local-stack.json").is_file():
        shutil.rmtree(directory)  # an earlier local stack's state, and nothing else
    if (directory / "service").exists():
        print(f"local stack: {directory} is in use; give a new --dir", file=sys.stderr)
        return 2
    directory.mkdir(parents=True, exist_ok=True)

    stack = LocalStack(directory, args.port, args.web, args.chain_port)
    stopped = threading.Event()
    for sig in (signal.SIGINT, signal.SIGTERM):
        signal.signal(sig, lambda *_: stopped.set())
    try:
        stack.seed()
        stack.seed_settled()
        stack.datasets = stack.write_datasets()
        info = directory / "local-stack.json"
        info.write_text(json.dumps(stack.describe(), indent=2) + "\n", encoding="utf-8")
        print("LOCAL Anvil test chain, no real value. All data and parties are SIMULATED.")
        print(f"API: {stack.api}/v1/   chain: {stack.rpc}")
        if args.web:
            print(f"Web application: {stack.api}/")
        print(f"Keys, wallets and addresses: {info}")
        # The end-to-end tests read the keys from this line (web/playwright.config.ts).
        print(f"Ready (local-stack.json: {info}). Stop with Ctrl+C.", flush=True)
        stopped.wait()
    finally:
        stack.stop()
        if temporary:
            shutil.rmtree(directory, ignore_errors=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())

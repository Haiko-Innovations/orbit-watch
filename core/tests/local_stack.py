"""A local stack for developing and testing the web application (phase 3, step 3.1).

One command starts, on this machine only:

* a LOCAL Anvil chain with Base Sepolia's EAS code and fresh Orbit Watch contracts, whose
  clock starts at 2026-11-01 12:00 UTC, before the SIMULATED requests' window;
* the request service on that chain, with the API and, given ``--web``, the built web
  application on one port;
* SIMULATED parties (a requester, four stations, the reviewers) with LOCAL TEST keys and
  registered wallets, and worthless TestUSD for the requester;
* three SIMULATED requests: two funded and open for observers, one opened but not funded.

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

from orbit_watch.sim.phase1_demo import ESPOO, KUOPIO, OULU, REQUESTER, TAMPERE
from orbit_watch.sim.phase1_demo import _request_bytes as request_bytes

STATIONS = (ESPOO, OULU, KUOPIO, TAMPERE)
PASSWORD = "local stack test password"  # protects LOCAL TEST keys only
BUDGET = 100_000_000  # 100 TestUSD (6 decimals), worthless
DELIVERY_DEADLINE = "2026-11-03T12:00:00Z"
REQUESTS = [  # request id, title, funded
    ("SIM-REQ-3001", "Identify and track SIM-CUBESAT-A after deployment", True),
    ("SIM-REQ-3002", "Track SIM-CUBESAT-A on its second night", True),
    ("SIM-REQ-3003", "Confirm SIM-CUBESAT-A's orbit (not funded yet)", False),
]


class StackError(RuntimeError):
    pass


class LocalStack:
    """The running stack; ``stop()`` ends it."""

    def __init__(self, directory: Path, port: int, web: Path | None):
        import uvicorn

        from orbit_watch.api import create_app, keys
        from orbit_watch.chain.client import OrbitWatchChain
        from orbit_watch.chain.link import ChainLink
        from orbit_watch.service import VerificationContext, open_service

        self.directory = directory
        self.parties = [REQUESTER, *STATIONS, *REVIEWERS]
        self.deployment = Deployment(
            GENESIS,
            reviewers=REVIEWERS,
            platform=PLATFORM,
            verifier=VERIFIER,
            parties=[*self.parties, PLATFORM],
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
            self.admin = keys.create_key(self.service.storage.db, "admin:local", "admin", now)
            self.keys = {
                party: keys.create_key(self.service.storage.db, party, party.split(":")[0], now)
                for party in self.parties
            }
        self.api = f"http://127.0.0.1:{port}"
        self.server = uvicorn.Server(
            uvicorn.Config(
                create_app(self.service, web=web),
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

        args = [*argv, "--json", "--api", self.api, "--key", self.keys[party]]
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

    def describe(self) -> dict:
        return {
            "notice": "LOCAL Anvil test chain, no real value. All data and parties are SIMULATED.",
            "api": self.api,
            "web": self.api + "/",
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
        "--dir", type=Path, help="where the stack keeps its state (default: a new temporary one)"
    )
    args = parser.parse_args(argv)
    reason = unavailable()
    if reason:
        print(f"local stack: {reason}", file=sys.stderr)
        return 2
    temporary = args.dir is None
    directory = args.dir or Path(tempfile.mkdtemp(prefix="orbit-watch-local-"))
    if (directory / "service").exists():
        print(f"local stack: {directory} is in use; give a new --dir", file=sys.stderr)
        return 2
    directory.mkdir(parents=True, exist_ok=True)

    stack = LocalStack(directory, args.port, args.web)
    stopped = threading.Event()
    for sig in (signal.SIGINT, signal.SIGTERM):
        signal.signal(sig, lambda *_: stopped.set())
    try:
        stack.seed()
        info = directory / "local-stack.json"
        info.write_text(json.dumps(stack.describe(), indent=2) + "\n", encoding="utf-8")
        print("LOCAL Anvil test chain, no real value. All data and parties are SIMULATED.")
        print(f"API: {stack.api}/v1/   chain: {stack.rpc}")
        if args.web:
            print(f"Web application: {stack.api}/")
        print(f"Keys, wallets and addresses: {info}")
        print("Ready. Stop with Ctrl+C.", flush=True)
        stopped.wait()
    finally:
        stack.stop()
        if temporary:
            shutil.rmtree(directory, ignore_errors=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())

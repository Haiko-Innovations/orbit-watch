"""A local stack for developing and testing the web application (phase 3, step 3.1).

One command starts, on this machine only:

* a LOCAL Anvil chain with Base Sepolia's EAS code and fresh Orbit Watch contracts, whose
  clock starts at 2026-11-01 12:00 UTC, before the SIMULATED requests' window; on port
  8545 by default, where wallets look for a local chain (31337). As on Base Sepolia, a
  timelock owns the reviewer registry and a 2-of-3 Safe of LOCAL TEST signers proposes to
  it; the local timelock waits 60 seconds, not 48 hours;
* the request service on that chain, with the API and, given ``--web``, the built web
  application on one port. Its PostgreSQL database is a schema on the server named by
  ``ORBIT_WATCH_TEST_DATABASE_URL``, or else on a PostgreSQL that the stack starts in
  Docker and removes when it stops (tests/postgres.py). With ``--image``, the service
  runs from that container image instead (step 4.2): this process seeds the database on
  a port of its own, then hands the database over to the container, which serves the
  port, read-only and without state of its own;
* SIMULATED parties (a requester, four stations, the reviewers, an administrator) with
  LOCAL TEST keys and registered wallets, and worthless TestUSD for the requester;
* six SIMULATED requests: five funded (four open for observers), one opened but not funded;
* one SIMULATED request that ran its course: SIM-ESPOO delivered good observations, nobody
  challenged, and the escrow credited the station 1 TESTUSD and the requester 0.3 back
  (and as much again from the replay below),
  for them to withdraw. Seeding it moves the chain's clock to 2026-11-02 05:01 UTC;
* SIM-REQ-3006 in review: SIM-ESPOO delivered good observations, the requester challenged
  them, and the escrow chose three reviewers, who have their tasks;
* fresh SIMULATED good observations of SIM-CUBESAT-A by SIM-ESPOO, never delivered yet,
  in ``datasets/`` (the service refuses data delivered before);
* a stand-in for a real object (tests/stand_ins.py, decision D-53), on the allow-list with
  an element set uploaded by hand, all made up: SIM-REQ-3010, a SIMULATED request for it that
  SIM-ESPOO fulfilled with SIMULATED observations along its orbit, in its challenge period;
  REQ-3011, a real request for it, funded and open; and REPLAY-3020, a replay of made-up
  "published" observations of it, which station:LOCAL-REPLAY delivered and which settled.

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
import os
import shutil
import signal
import socket
import subprocess
import sys
import tempfile
import threading
import time
import urllib.request
import uuid
from contextlib import redirect_stderr, redirect_stdout
from dataclasses import replace
from pathlib import Path

from anvil import LOCAL_TIMELOCK_DELAY, SAFE_SIGNERS, SAFE_THRESHOLD, Deployment, unavailable
from chain_world import GENESIS, PLATFORM, REGISTRY, REVIEWERS, VERIFIER
from helpers import catalog_bytes, policy_bytes
from postgres import SERVER_VARIABLE, Container, docker_available, drop_schema, new_schema
from stand_ins import (
    STAND_IN,
    STAND_IN_NAME,
    STAND_IN_REASON,
    published_observations,
    stand_in_catalogue,
    stand_in_observations,
)

from orbit_watch.api.privacy import STATION_DECIMALS
from orbit_watch.canonical import dumps_pretty
from orbit_watch.catalog import parse_catalog
from orbit_watch.sim.phase1_demo import ESPOO, KUOPIO, OULU, REQUESTER, TAMPERE, _deliveries
from orbit_watch.sim.phase1_demo import _packaged as packaged
from orbit_watch.sim.phase1_demo import _request_bytes as request_bytes
from orbit_watch.sim.scenarios import REQUEST, TARGET, _sim_json, _window
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
    ("SIM-REQ-3004", "Follow SIM-CUBESAT-A after its first manoeuvre", True),
    ("SIM-REQ-3005", "Check SIM-CUBESAT-A's period", True),
    ("SIM-REQ-3006", "Re-check SIM-CUBESAT-A (challenged, in review)", True),
]
SETTLED = ("SIM-REQ-3000", "Identify SIM-CUBESAT-A (delivered and accepted)")
AFTER_WINDOW = "2026-11-02T04:00:00Z"  # the requests' window ended at 03:00
AFTER_CHALLENGE = "2026-11-02T05:01:00Z"  # its one-hour challenge period is over
ADMIN = "admin:local"
FRESH_SEEDS = (201, 202)  # SIM-ESPOO's good observations for tests, unlike the seeded ones
IN_REVIEW = "SIM-REQ-3006"
IN_REVIEW_SEED = 203
# A stand-in for a real object, and its replay (step 5.5, decision D-53): all made up.
REPLAY_STATION = "station:LOCAL-REPLAY"
REAL_OBJECT_REQUESTS = [  # request id, title, SIMULATED
    ("SIM-REQ-3010", "Track the stand-in for a real object with simulated stations", True),
    ("REQ-3011", "Real observations of the stand-in for a real object", False),
]
OBSERVED_STAND_IN = "SIM-REQ-3010"  # SIM-ESPOO delivers SIMULATED observations of it
REPLAY = "REPLAY-3020"
STAND_IN_SEED = 204


class StackError(RuntimeError):
    pass


def free_port() -> int:
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        return probe.getsockname()[1]


class LocalStack:
    """The running stack; ``stop()`` ends it."""

    def __init__(
        self,
        directory: Path,
        port: int,
        web: Path | None,
        chain_port: int = 0,
        image: str | None = None,
    ):
        self.directory = directory
        self.port = port
        self.image = image
        self.service_container: str | None = None
        self.container: Container | None = None
        server = os.environ.get(SERVER_VARIABLE)
        if not server:
            self.container = Container("orbit-watch-local-db")
            server = self.container.conninfo
        self.db_server = server
        self.schema, self.database = new_schema(server, prefix="local_stack")
        try:
            self._start(directory, port, web, chain_port)
        except BaseException:
            self._remove_database()
            raise

    def _start(self, directory: Path, port: int, web: Path | None, chain_port: int) -> None:
        import uvicorn

        from orbit_watch.api import create_app, keys
        from orbit_watch.chain.client import OrbitWatchChain
        from orbit_watch.chain.link import ChainLink
        from orbit_watch.service import VerificationContext, open_service

        self.directory = directory
        self.datasets: list[str] = []
        self.in_review: dict = {}
        self.parties = [REQUESTER, *STATIONS, REPLAY_STATION, *REVIEWERS]
        self.deployment = Deployment(
            GENESIS,
            reviewers=REVIEWERS,
            platform=PLATFORM,
            verifier=VERIFIER,
            parties=[*self.parties, PLATFORM, ADMIN],
            port=chain_port,
            governance=True,
        )
        local = self.deployment.chain
        self.rpc = local.w3.provider.endpoint_uri
        local.send(
            self.deployment.deployer,
            self.deployment.usd.functions.mint(self.address(REQUESTER), BUDGET),
        )
        chain = OrbitWatchChain(local.w3, self.deployment.escrow.address)
        link = ChainLink(
            chain,
            self.deployment.accounts[VERIFIER],
            receipt_timeout=30,
            safe=self.deployment.safe.address,
        )
        context = VerificationContext(catalog=catalog_bytes(), policy=policy_bytes())
        self.service = open_service(self.database, REGISTRY, context, chain=link)
        with self.service.storage.db.transaction():
            now = link.now()
            self.admin = keys.create_key(self.service.storage.db, ADMIN, "admin", now)
            self.keys = {
                party: keys.create_key(self.service.storage.db, party, party.split(":")[0], now)
                for party in self.parties
            }
        # With an image, this process serves only while it seeds, on a port of its own.
        own_port = free_port() if self.image else port
        self.api = f"http://127.0.0.1:{own_port}"
        # Browsers sign in from the stack itself or from Vite's development server.
        self.origins = [
            f"http://{host}:{p}"
            for p in (port, DEV_SERVER_PORT)
            for host in ("127.0.0.1", "localhost")
        ]
        # Seeded without the station coordinates' precision (the phase 1 demo's deliveries
        # are more precise), which applies from then on, as in `orbit-watch serve`.
        self.app = create_app(self.service, web=web, origins=self.origins)
        self.server = uvicorn.Server(
            uvicorn.Config(
                self.app,
                host="127.0.0.1",
                port=own_port,
                log_level="warning",
            )
        )
        self.thread = threading.Thread(target=self.server.run, daemon=True)
        self.thread.start()
        deadline = time.monotonic() + 15
        while not self.server.started and time.monotonic() < deadline:
            if not self.thread.is_alive():
                raise StackError(f"the server did not start on port {own_port}")
            time.sleep(0.05)
        if not self.server.started:
            raise StackError(f"the server did not start on port {own_port}")

    def serve_from_image(self) -> None:
        """Hand the seeded database over to a container of ``image`` (step 4.2), which then
        serves the stack's port: the in-process server stops, and the container runs with a
        read-only file system, as an ordinary user, with the verifier's LOCAL TEST keystore
        mounted read-only. It shares the host's network, where the chain and PostgreSQL
        listen on 127.0.0.1, and listens there too."""
        from eth_account import Account

        self.server.should_exit = True
        self.thread.join(timeout=10)
        wallets = self.directory / "wallets"
        keystore = wallets / "system-verifier.json"
        encrypted = Account.encrypt(
            self.deployment.accounts[VERIFIER].key, PASSWORD, kdf="pbkdf2", iterations=1000
        )
        keystore.write_text(json.dumps(encrypted), encoding="utf-8")
        keystore.chmod(0o600)
        name = f"orbit-watch-stack-service-{uuid.uuid4().hex[:10]}"
        command = [
            "docker", "run", "--detach", "--name", name,
            "--network", "host", "--read-only", "--tmpfs", "/tmp",
            # The host's user, who owns the keystore (readable by its owner only).
            "--user", f"{os.getuid()}:{os.getgid()}",
            "--env", f"PORT={self.port}",
            "--env", f"ORBIT_WATCH_DATABASE_URL={self.database}",
            # Every test calls from 127.0.0.1: no limits against abuse (tests/test_limits.py).
            "--env", "ORBIT_WATCH_LIMITS=off",
            "--volume", f"{keystore}:/keys/verifier.json:ro",
            "--volume", f"{wallets / 'password'}:/keys/password:ro",
            self.image,
            "--host", "127.0.0.1",
            "--chain-rpc", self.rpc,
            "--escrow", self.deployment.escrow.address,
            "--safe", self.deployment.safe.address,
            "--verifier-keystore", "/keys/verifier.json",
            "--verifier-password-file", "/keys/password",
        ]  # fmt: skip
        for origin in self.origins:
            command += ["--origin", origin]
        started = subprocess.run(command, capture_output=True, text=True)
        if started.returncode != 0:
            raise StackError(f"docker run {self.image} failed: {started.stderr.strip()}")
        self.service_container = name
        self.api = f"http://127.0.0.1:{self.port}"
        deadline = time.monotonic() + 60
        while True:
            try:
                with urllib.request.urlopen(f"{self.api}/v1/health", timeout=2) as reply:
                    if reply.status == 200:
                        return
            except OSError:
                pass
            running = subprocess.run(
                ["docker", "inspect", "--format", "{{.State.Running}}", name],
                capture_output=True,
                text=True,
            ).stdout.strip()
            if running != "true" or time.monotonic() > deadline:
                logs = subprocess.run(["docker", "logs", name], capture_output=True, text=True)
                raise StackError(
                    f"the service image did not start on port {self.port}:\n"
                    f"{logs.stdout}{logs.stderr}"
                )
            time.sleep(0.3)

    def address(self, party: str) -> str:
        return self.deployment.accounts[party].address

    def keystore(self, party: str) -> Path:
        return self.directory / "wallets" / f"{party.replace(':', '-')}.json"

    def write_wallets(self) -> None:
        from eth_account import Account

        wallets = self.directory / "wallets"
        wallets.mkdir(parents=True, exist_ok=True)
        (wallets / "password").write_text(PASSWORD + "\n", encoding="utf-8")
        for party in [*self.parties, ADMIN]:
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
        for party in [*self.parties, ADMIN]:
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

    def seed_real_object(self) -> None:
        """A stand-in for a real object, made up (tests/stand_ins.py, D-53): on the allow-list
        with a public reason, its element set uploaded by hand; a SIMULATED request for it,
        reserved by SIM-ESPOO, and a real request for it, both funded; and a replay of made-up
        published observations of it, delivered by the replay station before its window's
        reference orbit went stale."""
        documents = self.directory / "requests"
        self.cli(
            ADMIN,
            "admin",
            "allow",
            "--norad-id",
            str(STAND_IN),
            "--name",
            STAND_IN_NAME,
            "--reason",
            STAND_IN_REASON,
        )
        catalogue = documents / "stand-in-element-set.json"
        catalogue.write_bytes(stand_in_catalogue())
        self.cli(ADMIN, "admin", "upload-orbits", str(catalogue))
        for request_id, title, simulated in REAL_OBJECT_REQUESTS:
            document = documents / f"{request_id}.json"
            document.write_bytes(
                dumps_pretty(
                    dict(
                        REQUEST,
                        request_id=request_id,
                        title=f"SIMULATED: {title}" if simulated else title,
                        simulated=simulated,
                        target={"norad_id": STAND_IN, "name": STAND_IN_NAME},
                    ),
                    sort_keys=False,
                ).encode("utf-8")
            )
            self.cli(
                REQUESTER,
                "request",
                "create",
                str(document),
                "--delivery-deadline",
                DELIVERY_DEADLINE,
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
        self.cli(ESPOO, "reserve", OBSERVED_STAND_IN, sign=True)

        published = documents / f"{REPLAY}.published.json"
        published.write_bytes(published_observations())
        self.cli(
            ADMIN,
            "admin",
            "replay",
            str(published),
            "--request-id",
            REPLAY,
            "--requester",
            REQUESTER,
            "--station",
            REPLAY_STATION,
            "--delivery-deadline",
            DELIVERY_DEADLINE,
            "--challenge-period-hours",
            "1",
        )
        self.cli(REQUESTER, "request", "open", REPLAY)
        self.cli(
            REQUESTER,
            "request",
            "fund",
            REPLAY,
            "--observer",
            "1",
            "--reviewer",
            "0.1",
            sign=True,
        )
        self.cli(REPLAY_STATION, "reserve", REPLAY, sign=True)
        self.cli(REPLAY_STATION, "submit", str(published), "--request", REPLAY, sign=True)

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
        # SIM-ESPOO's SIMULATED observations of the stand-in for a real object, along its
        # uploaded element set (D-50).
        stand_in = documents / f"{OBSERVED_STAND_IN}.observations.json"
        start, end = _window()
        stand_in.write_bytes(
            stand_in_observations(self.espoo_profile(), start, end, seed=STAND_IN_SEED)
        )
        self.cli(ESPOO, "submit", str(stand_in), "--request", OBSERVED_STAND_IN, sign=True)
        self.travel(AFTER_CHALLENGE)
        self.cli(ADMIN, "admin", "tick")
        for settled_id in (request_id, REPLAY):
            settled = json.loads(self.cli(REQUESTER, "request", "show", settled_id))
            if settled["summary"]["outcome"] != "accepted":
                raise StackError(f"{settled_id} was not accepted: {settled['summary']}")
        observed = json.loads(self.cli(REQUESTER, "request", "show", OBSERVED_STAND_IN))
        if observed["summary"]["automated_verdict"] != "pass":
            raise StackError(f"{OBSERVED_STAND_IN} did not pass: {observed['summary']}")

    @staticmethod
    def espoo_profile():
        """SIM-ESPOO's profile at its place to about a kilometre, as the service keeps it
        (step 4.4)."""
        profile = load_profile("sim-cmos-gps")
        station = profile.station
        place = replace(
            station,
            latitude_deg=round(station.latitude_deg, STATION_DECIMALS),
            longitude_deg=round(station.longitude_deg, STATION_DECIMALS),
        )
        return replace(profile, station=place)

    def wrong_target_observations(self) -> bytes:
        """SIM-ESPOO's SIMULATED positions of SIM-CUBESAT-B, labelled as the requests' target:
        a delivery that fails verification (the scenario ``wrong_target``)."""
        start, end = _window()
        return _sim_json(
            parse_catalog(packaged("catalog.json")),
            target_id=TARGET,
            observed_id=339002,
            profile=self.espoo_profile(),
            start=start,
            end=end,
            seed=103,
            max_passes=2,
            notes="SIMULATED: positions of SIM-CUBESAT-B, labelled as SIM-CUBESAT-A.",
        )

    def good_observations(self, seed: int) -> bytes:
        """SIM-ESPOO's SIMULATED good observations of the requests' target, drawn with ``seed``."""
        start, end = _window()
        return _sim_json(
            parse_catalog(packaged("catalog.json")),
            target_id=TARGET,
            profile=self.espoo_profile(),
            start=start,
            end=end,
            seed=seed,
            max_passes=2,
        )

    def seed_in_review(self) -> dict:
        """A request whose result its requester challenged, so that the escrow chose three
        reviewers: the reviewer view's tests vote on it."""
        observations = self.directory / "requests" / f"{IN_REVIEW}.observations.json"
        observations.write_bytes(self.good_observations(IN_REVIEW_SEED))
        self.cli(ESPOO, "reserve", IN_REVIEW, sign=True)
        self.cli(ESPOO, "submit", str(observations), "--request", IN_REVIEW, sign=True)
        self.cli(
            REQUESTER,
            "challenge",
            IN_REVIEW,
            "--reason",
            "SIMULATED: the track may belong to the neighbouring CubeSat.",
            sign=True,
        )
        record = json.loads(self.cli(REQUESTER, "request", "show", IN_REVIEW))["record"]
        if record["status"] != "in_review":
            raise StackError(f"{IN_REVIEW} is {record['status']}, not in review")
        return {
            "request_id": IN_REVIEW,
            "reviewers": record["reviewers"],
            "delivery_sha256": record["delivery_sha256"],
        }

    def write_datasets(self) -> list[str]:
        """Good observations that pass verification and were never delivered."""
        folder = self.directory / "datasets"
        folder.mkdir(exist_ok=True)
        written = []
        for seed in FRESH_SEEDS:
            path = folder / f"station-SIM-ESPOO-{seed}.json"
            path.write_bytes(self.good_observations(seed))
            written.append(str(path))
        self.wrong_target = folder / "station-SIM-ESPOO-wrong-target.json"
        self.wrong_target.write_bytes(self.wrong_target_observations())
        return written

    def describe(self) -> dict:
        return {
            "notice": (
                "LOCAL Anvil test chain, no real value. All data and parties are SIMULATED, "
                "but for a made-up stand-in for a real object and its replay."
            ),
            "api": self.api,
            "web": self.api + "/",
            "origins": self.origins,
            "served_by": f"container image {self.image}" if self.image else "the stack's process",
            "chain_rpc": self.rpc,
            "chain_id": 31337,
            "escrow": self.deployment.escrow.address,
            "token": self.deployment.usd.address,
            "admin_key": self.admin,
            # A LOCAL PostgreSQL with trust authentication: no password to protect.
            "database": self.database,
            "admin": {
                "party": ADMIN,
                "key": self.admin,
                "address": self.address(ADMIN),
                "keystore": str(self.keystore(ADMIN)),
                "private_key": "0x" + self.deployment.accounts[ADMIN].key.hex(),
            },
            "governance": {
                "registry": self.deployment.registry.address,
                "timelock": self.deployment.timelock.address,
                "min_delay_seconds": LOCAL_TIMELOCK_DELAY,
                "safe": self.deployment.safe.address,
                "threshold": SAFE_THRESHOLD,
                "signers": [
                    {
                        "name": name,
                        "address": account.address,
                        "private_key": "0x" + account.key.hex(),
                    }
                    for name, account in zip(
                        SAFE_SIGNERS, self.deployment.safe_signers, strict=True
                    )
                ],
            },
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
            "wrong_target": {ESPOO: str(self.wrong_target)},
            "in_review": self.in_review,
            "stand_in": {"norad_id": STAND_IN, "name": STAND_IN_NAME},
            "real_object_requests": [request_id for request_id, _, _ in REAL_OBJECT_REQUESTS],
            "observed_stand_in": OBSERVED_STAND_IN,
            "replay": {"request_id": REPLAY, "station": REPLAY_STATION},
        }

    def stop(self) -> None:
        self.server.should_exit = True
        self.thread.join(timeout=10)
        if self.service_container is not None:
            subprocess.run(["docker", "rm", "--force", self.service_container], capture_output=True)
        self.service.storage.close()
        self.deployment.chain.stop()
        self._remove_database()

    def _remove_database(self) -> None:
        """The stack's schema goes, and the PostgreSQL it started with it."""
        if self.container is not None:
            self.container.stop()
        else:
            drop_schema(self.db_server, self.schema)


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
        "--image",
        help="serve the API and the web application from this container image of the "
        "service (step 4.2; build it with docker build at the repository's root)",
    )
    parser.add_argument(
        "--replace",
        action="store_true",
        help="start afresh in --dir if it holds an earlier local stack (its local-stack.json)",
    )
    args = parser.parse_args(argv)
    reason = unavailable()
    if reason is None and not os.environ.get(SERVER_VARIABLE) and not docker_available():
        reason = f"PostgreSQL is needed: install Docker, or set {SERVER_VARIABLE}"
    if reason:
        print(f"local stack: {reason}", file=sys.stderr)
        return 2
    temporary = args.dir is None
    directory = args.dir or Path(tempfile.mkdtemp(prefix="orbit-watch-local-"))
    if args.replace and (directory / "local-stack.json").is_file():
        shutil.rmtree(directory)  # an earlier local stack's state, and nothing else
    if (directory / "local-stack.json").exists():
        print(
            f"local stack: {directory} holds a local stack; give --replace or a new --dir",
            file=sys.stderr,
        )
        return 2
    directory.mkdir(parents=True, exist_ok=True)

    if args.image and not docker_available():
        print("local stack: --image needs Docker", file=sys.stderr)
        return 2
    stack = LocalStack(directory, args.port, args.web, args.chain_port, args.image)
    stopped = threading.Event()
    for sig in (signal.SIGINT, signal.SIGTERM):
        signal.signal(sig, lambda *_: stopped.set())
    try:
        stack.seed()
        stack.seed_real_object()
        stack.seed_settled()
        stack.in_review = stack.seed_in_review()
        stack.datasets = stack.write_datasets()
        if args.image:
            stack.serve_from_image()  # `orbit-watch serve`: its defaults apply
        else:
            stack.app.state.api.station_decimals = STATION_DECIMALS
        info = directory / "local-stack.json"
        info.write_text(json.dumps(stack.describe(), indent=2) + "\n", encoding="utf-8")
        print(
            "LOCAL Anvil test chain, no real value. All data and parties are SIMULATED, but "
            "for a made-up stand-in for a real object and its replay."
        )
        print(f"API: {stack.api}/v1/   chain: {stack.rpc}   PostgreSQL schema: {stack.schema}")
        if args.image:
            print(f"Served by the container image {args.image}")
        elif args.web:
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

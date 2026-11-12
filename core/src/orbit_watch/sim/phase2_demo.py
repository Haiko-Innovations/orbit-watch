"""The phase 2 demo (SIMULATED data, testnet tokens of no value): five requests on chain.

The five requests of the phase 1 demo, now settled on the escrow contract. Every party
runs the command line with its own encrypted keystore; the service holds only the verifier
key and follows the chain, which decides reviewer rounds and payments:

* ``…1``: good delivery, nobody challenges -> accepted; the station withdraws its reward;
* ``…2``: positions of the neighbouring CubeSat, the station challenges, the reviewers
  reject -> rejected;
* ``…3``: a visual observer's imprecise delivery, nobody challenges -> rejected;
* ``…4``: good delivery from an Az/El station, the requester challenges, only one reviewer
  answers in time -> disputed;
* ``…5``: reserved but never delivered -> expired.

It also shows that a party outside a round cannot vote, that nobody can withdraw money not
owed to them, and that a retry pays nothing twice. The deadlines are minutes long, and the
demo waits for them on the chain's clock (a local chain in the tests moves its clock
instead). Run it against a service on a chain, ``orbit-watch serve --network base-sepolia``:
``orbit-watch demo --phase 2`` (see docs/phase-2-summary.md).

Output: ``transcript.md``, ``summary.json`` and ``README.md``.
"""

from __future__ import annotations

import hashlib
import io
import json
import sys
import time
from contextlib import redirect_stderr, redirect_stdout
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, Protocol

from orbit_watch import SIMULATION_NOTICE
from orbit_watch.canonical import dumps_pretty, write_text
from orbit_watch.catalog import parse_catalog
from orbit_watch.sim.phase1_demo import ESPOO, KUOPIO, OULU, REQUESTER, TAMPERE, _deliveries
from orbit_watch.sim.phase1_demo import _packaged as packaged
from orbit_watch.sim.phase1_demo import _request_bytes as request_bytes
from orbit_watch.timeutil import format_utc, parse_utc

ADMIN = "admin"
STATIONS = (ESPOO, OULU, KUOPIO, TAMPERE)
RUBBER_STAMPER = "reviewer:sim-aino"  # approves every task without looking
OBSERVER_REWARD = "1"  # token amounts, as the command line takes them
REVIEWER_REWARD = "0.1"
DEFAULT_PREFIX = "SIM-REQ-200"
EAS_SCAN = {84532: "https://base-sepolia.easscan.org"}
PLAN = [  # number, title, station, delivered dataset (None: never delivered)
    (1, "Identify and track SIM-CUBESAT-A (good delivery)", ESPOO, "SIM-REQ-1001"),
    (2, "Identify and track SIM-CUBESAT-A (wrong object delivered)", ESPOO, "SIM-REQ-1002"),
    (3, "Identify and track SIM-CUBESAT-A (too imprecise)", OULU, "SIM-REQ-1003"),
    (4, "Identify and track SIM-CUBESAT-A (challenged, disputed)", KUOPIO, "SIM-REQ-1004"),
    (5, "Identify and track SIM-CUBESAT-A (never delivered)", TAMPERE, None),
]


class Clock(Protocol):
    """The chain's clock: the time of the latest block."""

    def now(self) -> datetime: ...

    def wait_until(self, when: datetime) -> None: ...


class ChainClock:
    """Waits on a live chain by polling its latest block."""

    def __init__(self, w3: Any, poll_seconds: float = 5.0):
        self.w3 = w3
        self.poll_seconds = poll_seconds

    def now(self) -> datetime:
        return datetime.fromtimestamp(self.w3.eth.get_block("latest")["timestamp"], tz=UTC)

    def wait_until(self, when: datetime) -> None:
        while (now := self.now()) < when:
            left = (when - now).total_seconds()
            print(f"waiting {left:.0f} s for the chain's clock", file=sys.stderr)
            time.sleep(min(self.poll_seconds, max(left, 1.0)))


@dataclass
class Settings:
    api: str  # the request service on a chain
    admin_key: str
    wallets: Path  # <role>-<id>.json keystores, e.g. station-SIM-ESPOO.json
    password_file: Path
    rpc: str  # the endpoint the parties' wallets send through
    minutes: float = 6.0  # challenge period and review time
    prefix: str = DEFAULT_PREFIX


class DemoError(RuntimeError):
    pass


@dataclass
class Refusal:
    code: str
    message: str


@dataclass
class ChainDemo:
    settings: Settings
    clock: Clock
    work: Path  # API keys and delivery files of this run (not part of the output)
    keys: dict[str, str] = field(default_factory=dict)
    addresses: dict[str, str] = field(default_factory=dict)
    rows: list[str] = field(default_factory=list)
    checks: list[tuple[str, str]] = field(default_factory=list)
    seen: set[tuple[str, str]] = field(default_factory=set)
    delivered: dict[str, bytes] = field(default_factory=dict)
    info: dict[str, Any] = field(default_factory=dict)  # GET /v1/chain
    chain: Any = None  # OrbitWatchChain, for the attempts straight on chain
    ids: dict[int, str] = field(default_factory=dict)
    parties: list[str] = field(default_factory=list)
    start_block: int = 0

    # ------------------------------------------------------------------ the command line

    def cli(self, party: str, *argv: str, sign: bool = False) -> Any:
        """Run ``orbit-watch`` as ``party`` (its API key; with ``sign``, its own keystore)."""
        code, out, err = self._run(party, argv, sign)
        if code != 0:
            raise DemoError(f"{party}: orbit-watch {' '.join(argv)}: {err.strip()}")
        return json.loads(out) if out.strip() else None

    def refused(self, party: str, *argv: str, sign: bool = False) -> Refusal:
        """Run a command that must be refused; returns the refusal."""
        code, _, err = self._run(party, argv, sign)
        if code == 0:
            raise DemoError(f"{party}: orbit-watch {' '.join(argv)} was not refused")
        line = err.strip().splitlines()[-1].removeprefix("orbit-watch: ")
        name, _, message = line.partition(": ")
        return Refusal(name, message)

    def _run(self, party: str, argv: tuple[str, ...], sign: bool) -> tuple[int, str, str]:
        from orbit_watch.cli import main

        key = self.settings.admin_key if party == ADMIN else self.keys[party]
        args = [*argv, "--json", "--api", self.settings.api, "--key", key]
        if sign:
            args += [
                "--keystore",
                str(self.keystore(party)),
                "--password-file",
                str(self.settings.password_file),
                "--rpc",
                self.settings.rpc,
            ]
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            code = main(args)
        return code, out.getvalue(), err.getvalue()

    def keystore(self, party: str) -> Path:
        return self.settings.wallets / f"{party.replace(':', '-')}.json"

    # ------------------------------------------------------------------ the transcript

    def log(self, who: str, what: str, links: str = "") -> None:
        when = self.clock.now().strftime("%Y-%m-%d %H:%M:%S")
        self.rows.append(f"| {when} | {who} | {what} | {links} |")

    def link(self, label: str, tx_hash: str, explorer: str | None) -> str:
        return f"[{label}]({explorer})" if explorer else f"{label} `{tx_hash[:10]}…`"

    def new_events(self, request_id: str, keep: tuple[str, ...] = ()) -> str:
        """Links to the request's chain events not shown yet, except the ``keep`` ones,
        which a later line shows."""
        links = []
        for event in self.show(request_id)["chain"]["events"]:
            if (event["tx_hash"], event["event"]) in self.seen or event["event"] in keep:
                continue
            self.seen.add((event["tx_hash"], event["event"]))
            links.append(self.link(event["event"], event["tx_hash"], event["explorer"]))
        return ", ".join(links)

    def show(self, request_id: str) -> dict[str, Any]:
        return self.cli(REQUESTER, "request", "show", request_id)

    def party_of(self, address: str) -> str:
        return next((p for p, a in self.addresses.items() if a == address), address)

    def amount(self, units: int) -> str:
        from orbit_watch.cli_client import amount

        return amount(units, self.info["token"])

    # ------------------------------------------------------------------ the run

    def run(self) -> dict[str, Any]:
        self.info = self.cli(ADMIN, "chain")
        self.chain = self._chain_client()
        self.start_block = self.chain.latest_block()
        self.ids = {n: f"{self.settings.prefix}{n}" for n, *_ in PLAN}
        reviewers = sorted(
            path.stem.replace("-", ":", 1) for path in self.settings.wallets.glob("reviewer-*.json")
        )
        self.parties = [REQUESTER, *STATIONS, *reviewers]
        self.setup()
        before = self.balances()
        self.fund_and_reserve()
        self.deliver()
        self.unauthorised_before_settlement()
        self.challenge_and_review()
        self.wait_for_deadlines()
        self.withdraw_all()
        self.retries()
        after = self.balances()
        return self.summary(before, after)

    def _chain_client(self) -> Any:
        from web3 import Web3

        from orbit_watch.chain.client import OrbitWatchChain

        return OrbitWatchChain(Web3(Web3.HTTPProvider(self.settings.rpc)), self.info["escrow"])

    def setup(self) -> None:
        self.work.mkdir(parents=True, exist_ok=True)
        for party in self.parties:
            target = self.work / f"{party.replace(':', '_')}.key"
            role = party.split(":")[0]
            code, _, err = self._run(ADMIN, ("admin", "key", party, role, "-o", str(target)), False)
            if code != 0:
                raise DemoError(f"admin key {party}: {err.strip()}")
            self.keys[party] = target.read_text(encoding="utf-8").strip()
            view = self.cli(party, "wallet", "register", sign=True)
            self.addresses[party] = view["address"]
        self.log(
            ADMIN,
            f"gives {len(self.parties)} parties API keys; each registers its own wallet "
            "with a signature (requester, four stations, reviewers)",
        )

    def balances(self) -> dict[str, dict[str, int]]:
        found = {}
        for party in self.parties:
            view = self.cli(party, "balance", party)
            found[party] = {"balance": view["balance"], "withdrawable": view["withdrawable"]}
        return found

    def fund_and_reserve(self) -> None:
        now = self.clock.now()
        deadline = format_utc(now + timedelta(minutes=4 * self.settings.minutes))
        hours = str(self.settings.minutes / 60)
        for n, title, _, _ in PLAN:
            rid = self.ids[n]
            document = self.work / f"{rid}.json"
            document.write_bytes(request_bytes(rid, title))
            self.cli(
                REQUESTER,
                "request",
                "create",
                str(document),
                "--delivery-deadline",
                deadline,
                "--reservation-hours",
                str(4 * self.settings.minutes / 60),
                "--challenge-period-hours",
                hours,
                "--review-hours",
                hours,
            )
            self.cli(REQUESTER, "request", "open", rid)
            self.cli(
                REQUESTER,
                "request",
                "fund",
                rid,
                "--observer",
                OBSERVER_REWARD,
                "--reviewer",
                REVIEWER_REWARD,
                sign=True,
            )
            deposit = self.show(rid)["record"]["split"]["total"]
            self.log(
                REQUESTER,
                f"creates, opens and funds {rid}: approves and deposits {self.amount(deposit)} "
                f"(observer {OBSERVER_REWARD}, reviewers {REVIEWER_REWARD} each, "
                f"platform fee 0); delivery deadline {deadline[11:19]}",
                self.new_events(rid),
            )
        for n, _, station, _ in PLAN:
            rid = self.ids[n]
            self.cli(station, "reserve", rid, sign=True)
            self.log(station, f"reserves {rid}", self.new_events(rid))

    def deliver(self) -> None:
        deliveries = _deliveries(parse_catalog(packaged("catalog.json")))
        for n, _, station, dataset in PLAN:
            if dataset is None:
                continue
            rid = self.ids[n]
            data = deliveries[dataset]
            self.delivered[rid] = data
            path = self.work / f"{rid}.observations.json"
            path.write_bytes(data)
            self.cli(station, "submit", str(path), "--request", rid, sign=True)
            view = self.show(rid)
            self.log(
                station,
                f"delivers {rid} (SHA-256 on chain, file to the service): automated "
                f"verification **{view['summary']['automated_verdict']}**, attested by the "
                f"service's verifier key; challenge period until "
                f"{view['record']['challenge_deadline'][11:19]}",
                self.new_events(rid),
            )

    def unauthorised_before_settlement(self) -> None:
        """Nobody takes money that is not owed to them (completion criterion 9)."""
        station = TAMPERE  # reserved the request whose deposit is still held
        refusal = self.refused(station, "wallet", "withdraw", sign=True)
        self.checks.append(
            (
                f"`{station}` asks to withdraw while {self.ids[5]}'s deposit is held",
                f"refused by the API: `{refusal.code}`",
            )
        )
        refusal = self._on_chain(station, self.chain.withdraw_call())
        self.checks.append(
            (f"`{station}` calls `withdraw` on the escrow itself", f"refused: `{refusal}`")
        )
        refusal = self._on_chain(ESPOO, self.chain.cancel_call(self.ids[5]))
        self.checks.append(
            (f"`{ESPOO}` tries to cancel {self.ids[5]} (not its request)", f"refused: `{refusal}`")
        )
        self.log(
            "others",
            "try to withdraw or cancel money that is not theirs: refused (see the checks)",
        )

    def _on_chain(self, party: str, call: Any) -> str:
        """Send ``call`` straight to the chain with ``party``'s own key; returns the refusal."""
        from orbit_watch.chain import ChainError
        from orbit_watch.chain.wallet import open_wallet

        wallet = open_wallet(
            self.settings.rpc, self.keystore(party), str(self.settings.password_file)
        )
        try:
            tx_hash = wallet.send(self.chain.unsigned(wallet.address, call))
        except ChainError as error:
            return error.code
        raise DemoError(f"{party}: {call.function} was not refused ({tx_hash})")

    def challenge_and_review(self) -> None:
        rejected, disputed = self.ids[2], self.ids[4]
        self.cli(
            ESPOO, "challenge", rejected, "--reason", "I am sure this was SIM-CUBESAT-A.", sign=True
        )
        view = self.show(rejected)
        self.log(
            ESPOO,
            f"challenges {rejected}; the escrow chooses the reviewers "
            f"{', '.join(view['record']['reviewers'])}",
            self.new_events(rejected),
        )
        self.cli(
            REQUESTER,
            "challenge",
            disputed,
            "--reason",
            "Second opinion before we update our orbit.",
            sign=True,
        )
        view = self.show(disputed)
        slow = view["record"]["reviewers"]
        self.log(
            REQUESTER,
            f"challenges {disputed}; the escrow chooses the reviewers {', '.join(slow)}",
            self.new_events(disputed),
        )
        self.outsider_votes(rejected)
        # Every reviewer of the first round answers; in the second only the first one does,
        # so that round ends without a majority.
        for reviewer in self.show(rejected)["record"]["reviewers"]:
            self.answer(reviewer, rejected)
        self.answer(slow[0], disputed)
        view = self.show(rejected)
        self.log("service", self.outcome(rejected, view), self.new_events(rejected))

    def outsider_votes(self, request_id: str) -> None:
        """A reviewer outside the round cannot vote (completion criterion 9)."""
        round_ = set(self.show(request_id)["record"]["reviewers"])
        outsiders = [p for p in self.parties if p.startswith("reviewer:") and p not in round_]
        # A registered reviewer who is not in this round, if there is one.
        outsiders.sort(key=lambda p: not self.chain.is_reviewer(self.addresses[p]))
        voter = outsiders[0] if outsiders else ESPOO
        stored = self.chain.request(request_id)
        call = self.chain.vote_call(
            request_id,
            delivery_sha256=stored["deliverySha256"],
            approve=True,
            reason_sha256=hashlib.sha256(b"Looks fine.").digest(),
            observer=stored["station"],
            result_attestation=stored["resultAttestation"],
        )
        refusal = self._on_chain(voter, call)
        self.checks.append(
            (
                f"`{voter}`, outside the round, votes on {request_id} on chain",
                f"refused: `{refusal}`",
            )
        )

    def answer(self, reviewer: str, request_id: str) -> None:
        sha = hashlib.sha256(self.delivered[request_id]).hexdigest()
        tasks = self.cli(reviewer, "review", "list")["tasks"]
        task = next((t for t in tasks if t["observations_sha256"] == sha), None)
        if task is None:  # the round was decided before this reviewer's turn
            return
        approve = reviewer == RUBBER_STAMPER or task["automated_verdict"] == "pass"
        reason = (
            "Looks fine."
            if reviewer == RUBBER_STAMPER
            else "Residuals follow the reference orbit."
            if approve
            else "The track runs about 8 s behind the requested object."
        )
        code, _, err = self._run(
            reviewer,
            (
                "review",
                "answer",
                task["task_id"],
                "--approve" if approve else "--reject",
                "--reason",
                reason,
            ),
            True,
        )
        if code != 0:
            if "forbidden_in_status" in err or "wrong_status" in err:
                return  # decided by the other votes first
            raise DemoError(f"{reviewer}: review answer: {err.strip()}")
        vote = "approve" if approve else "reject"
        self.log(
            reviewer,
            f"votes {vote} on {request_id}: an EAS attestation signed with its own key",
            self.new_events(request_id, keep=("Settled",)),
        )

    def outcome(self, request_id: str, view: dict[str, Any]) -> str:
        summary = view["summary"]
        if summary["settlement"] is None:
            return f"{request_id}: {summary['status']}"
        payouts = summary["settlement"]["plan"]["payouts"]
        paid = ", ".join(f"{p['party']} +{self.amount(p['points'])}" for p in payouts)
        return (
            f"{request_id}: {summary['outcome_reason']} -> **{summary['outcome']}**; "
            f"the service settles on chain: {paid or 'nothing moved'}"
        )

    def wait_for_deadlines(self) -> None:
        deadlines: dict[str, datetime] = {}
        for n in (1, 3):
            deadlines[self.ids[n]] = parse_utc(
                self.show(self.ids[n])["record"]["challenge_deadline"]
            )
        deadlines[self.ids[4]] = parse_utc(self.show(self.ids[4])["record"]["review_deadline"])
        deadlines[self.ids[5]] = parse_utc(
            self.show(self.ids[5])["record"]["terms"]["delivery_deadline"]
        )
        for when in sorted(set(deadlines.values())):
            self.clock.wait_until(when)
            self.cli(ADMIN, "admin", "tick")
            for rid, due in sorted(deadlines.items()):
                if due == when:
                    self.log("service", self.outcome(rid, self.show(rid)), self.new_events(rid))

    def withdraw_all(self) -> None:
        for party in self.parties:
            owed = self.cli(party, "balance", party)["withdrawable"]
            if not owed:
                continue
            result = self.cli(party, "wallet", "withdraw", sign=True)
            tx = result["transaction"]
            self.log(
                party,
                f"withdraws {self.amount(owed)}: a token transfer to its own wallet",
                self.link("Withdrawn", tx["tx_hash"], tx["explorer"]),
            )

    def retries(self) -> None:
        """A retry never pays twice (completion criterion 10)."""
        tick = self.cli(ADMIN, "admin", "tick")
        self.checks.append(("`admin tick` once more", f"sent {len(tick['sent'])} transactions"))
        refusal = self._on_chain(ESPOO, self.chain.settle_call(self.ids[1]))
        self.checks.append(
            (f"`{ESPOO}` settles {self.ids[1]} again on chain", f"refused: `{refusal}`")
        )
        refusal = self.refused(ESPOO, "wallet", "withdraw", sign=True)
        self.checks.append((f"`{ESPOO}` withdraws again", f"refused by the API: `{refusal.code}`"))
        self.log("everyone", "retries: nothing is paid twice (see the checks)")

    # ------------------------------------------------------------------ the output

    def attestations(self) -> list[dict[str, Any]]:
        from orbit_watch.chain import request_key

        keys = {request_key(rid): rid for rid in self.ids.values()}
        found = []
        for event in self.chain.events(self.start_block, self.chain.latest_block()):
            rid = keys.get(event.args.get("requestId", b""))
            if rid is None or event.name not in ("VerificationRecorded", "Voted"):
                continue
            found.append(
                {
                    "request_id": rid,
                    "kind": "automated result" if event.name == "VerificationRecorded" else "vote",
                    "by": "service (verifier key)"
                    if event.name == "VerificationRecorded"
                    else self.party_of(event.args["reviewer"]),
                    "uid": "0x" + event.args["attestation"].hex(),
                    "tx_hash": event.tx_hash,
                }
            )
        return found

    def summary(self, before: dict, after: dict) -> dict[str, Any]:
        views = {rid: self.show(rid) for rid in self.ids.values()}
        return {
            "notice": SIMULATION_NOTICE,
            "chain": {
                key: self.info[key]
                for key in (
                    "chain_id",
                    "network",
                    "notice",
                    "escrow",
                    "registry",
                    "verifier",
                    "explorer",
                )
            },
            "token": self.info["token"],
            "parties": self.addresses,
            "requests": {
                rid: {
                    "outcome": view["summary"]["outcome"],
                    "reason": view["summary"]["outcome_reason"],
                    "automated_verdict": view["summary"]["automated_verdict"],
                    "reviewers": view["summary"]["reviewers"],
                    "votes": view["summary"]["votes"],
                    "payouts": view["summary"]["settlement"]["plan"]["payouts"],
                    "on_chain": view["chain"]["status"],
                    "events": view["chain"]["events"],
                }
                for rid, view in views.items()
            },
            "attestations": self.attestations(),
            "balances": {"before": before, "after": after},
            "checks": [{"what": what, "result": result} for what, result in self.checks],
        }


def run_phase2_demo(settings: Settings, clock: Clock, out_dir: str | Path, work: Path) -> dict:
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    demo = ChainDemo(settings, clock, work)
    summary = demo.run()
    write_text(out / "summary.json", dumps_pretty(summary, sort_keys=False))
    write_text(out / "transcript.md", _transcript(demo, summary))
    write_text(out / "README.md", _readme(summary))
    return summary


def _address(summary: dict[str, Any], address: str) -> str:
    explorer = summary["chain"]["explorer"]
    return f"[`{address}`]({explorer}/address/{address})" if explorer else f"`{address}`"


def _transcript(demo: ChainDemo, summary: dict[str, Any]) -> str:
    chain, token = summary["chain"], summary["token"]
    amount = demo.amount
    parties = "\n".join(
        f"| {party} | {_address(summary, address)} |"
        for party, address in summary["parties"].items()
    )
    outcomes = "\n".join(
        f"| {rid} | {item['outcome']} | {item['automated_verdict'] or '-'} | "
        f"{', '.join(f'{p["party"]} +{amount(p["points"])}' for p in item['payouts']) or '-'} |"
        for rid, item in summary["requests"].items()
    )
    moves = []
    for party in summary["parties"]:
        start = summary["balances"]["before"][party]["balance"]
        end = summary["balances"]["after"][party]["balance"]
        if start != end:
            sign = "+" if end > start else "-"
            moves.append(
                f"| {party} | {amount(start)} | {amount(end)} | {sign}{amount(abs(end - start))} |"
            )
    scan = EAS_SCAN.get(chain["chain_id"])
    attestations = "\n".join(
        f"| {a['request_id']} | {a['kind']} | {a['by']} | "
        + (
            f"[`{a['uid'][:18]}…`]({scan}/attestation/view/{a['uid']})"
            if scan
            else f"`{a['uid'][:18]}…`"
        )
        + " |"
        for a in summary["attestations"]
    )
    checks = "\n".join(f"| {c['what']} | {c['result']} |" for c in summary["checks"])
    rows = "\n".join(demo.rows)
    notice = chain["notice"][0].upper() + chain["notice"][1:]
    minutes = demo.settings.minutes
    return f"""# Orbit Watch phase 2 demo (SIMULATED, {chain["notice"]})

> {SIMULATION_NOTICE}
>
> **{notice}.** The token is {token["symbol"]} `{token["address"]}`.

The five simulated requests of the phase 1 demo run through the whole chain on the
{chain["network"]} (chain {chain["chain_id"]}). The escrow
{_address(summary, chain["escrow"])} holds the deposits, the automated results and the
votes are EAS attestations, and the chain decides the reviewer rounds and the payments.
Every party signs with its own wallet from the command line; the service holds only the
verifier key {_address(summary, chain["verifier"])}. `{RUBBER_STAMPER}` approves every
task without looking; the other reviewers answer carefully. The challenge period and the
review time are {minutes:g} minutes, and the delivery deadline is {4 * minutes:g} minutes
after funding.

## Parties and their wallets

| Party | Wallet |
|---|---|
{parties}

## What happened

| Time (UTC, the chain's clock) | Who | What | On chain |
|---|---|---|---|
{rows}

## Outcomes

| Request | Outcome | Automated result | Paid out |
|---|---|---|---|
{outcomes}

## Token transfers

Wallet balances before and after the demo: every deposit was paid out or refunded,
and each party withdrew its own credit.

| Party | Before | After | Change |
|---|---|---|---|
{chr(10).join(moves)}

## Attestations

| Request | What | By | Attestation |
|---|---|---|---|
{attestations}

## Checks

What the demo tried that must not work.

| Attempt | Result |
|---|---|
{checks}
"""


def _readme(summary: dict[str, Any]) -> str:
    chain = summary["chain"]
    return f"""# Orbit Watch phase 2 demo output (SIMULATED, {chain["notice"]})

> {SIMULATION_NOTICE}

Recorded by `orbit-watch demo --phase 2` against the request service on
{chain["network"]}. The chain is live, so a new run gives new transactions:
this is a record of one run, with links to every transaction. CI runs the
same demo on a local chain (`core/tests/test_phase2_demo.py`).

- `transcript.md`: the parties' wallets, what happened with transaction links,
  the outcomes, the token transfers, the EAS attestations and the checks
- `summary.json`: the same as data

How to run it: [docs/phase-2-summary.md](../../docs/phase-2-summary.md).
"""

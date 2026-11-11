"""The phase 1 demo (SIMULATED): five requests through the whole chain.

Runs the request service with the points ledger on a fixed, simulated clock:

* SIM-REQ-1001: good delivery, nobody challenges -> accepted, published at once;
* SIM-REQ-1002: positions of the neighbouring CubeSat, the observer challenges,
  reviewers reject 2-0 -> rejected, published after a 7-day embargo;
* SIM-REQ-1003: a visual observer's imprecise delivery, nobody challenges -> rejected;
* SIM-REQ-1004: good delivery from an Az/El station, the requester challenges,
  only one reviewer answers in time -> disputed (dispute rule), 14-day embargo;
* SIM-REQ-1005: reserved but never delivered -> expired, full refund.

One reviewer approves every task without looking; the others answer
correctly. The output (``transcript.md``, ``summary.json``, ``README.md``) is
deterministic and committed in ``examples/phase1/``.
"""

from __future__ import annotations

from importlib import resources
from pathlib import Path
from typing import Any

from orbit_watch import SIMULATION_NOTICE
from orbit_watch import lifecycle as lc
from orbit_watch.canonical import dumps_pretty, write_text
from orbit_watch.catalog import parse_catalog
from orbit_watch.formats import owjson
from orbit_watch.reviewers import ReviewerRegistry
from orbit_watch.service import RequestService, ServiceError, VerificationContext
from orbit_watch.settlement.ledger import LedgerAdapter
from orbit_watch.sim import scenarios
from orbit_watch.sim.simulator import load_profile, simulate
from orbit_watch.timeutil import format_utc, parse_utc

REQUESTER = "requester:sim-cubesat-team"
ESPOO, OULU, KUOPIO, TAMPERE = (
    "station:SIM-ESPOO",
    "station:SIM-OULU",
    "station:SIM-KUOPIO",
    "station:SIM-TAMPERE",
)
RUBBER_STAMPER = "reviewer:sim-aino"
SPLIT = lc.RewardSplit(observer=100, reviewer=10, platform_fee=0)
FINAL_TIME = "2026-11-10T00:00:00Z"
PLAN = [  # request id, title, embargo days
    ("SIM-REQ-1001", "Identify and track SIM-CUBESAT-A (good delivery)", 0),
    ("SIM-REQ-1002", "Identify and track SIM-CUBESAT-A (wrong object delivered)", 7),
    ("SIM-REQ-1003", "Identify and track SIM-CUBESAT-A (too imprecise)", 0),
    ("SIM-REQ-1004", "Identify and track SIM-CUBESAT-A (challenged, disputed)", 14),
    ("SIM-REQ-1005", "Identify and track SIM-CUBESAT-A (never delivered)", 0),
]


def _packaged(name: str) -> bytes:
    return resources.files("orbit_watch.data").joinpath(name).read_bytes()


def _request_bytes(request_id: str, title: str) -> bytes:
    document = dict(scenarios.REQUEST, request_id=request_id, title=f"SIMULATED: {title}")
    return dumps_pretty(document, sort_keys=False).encode("utf-8")


def _deliveries(catalog) -> dict[str, bytes]:
    ctx: dict[str, Any] = {"catalog": catalog, "datasets": {}}
    azel = simulate(
        catalog,
        scenarios.TARGET,
        load_profile("sim-azel-mount"),
        parse_utc(scenarios.WINDOW_START),
        parse_utc(scenarios.WINDOW_END),
        seed=401,
        max_passes=2,
    )
    return {
        "SIM-REQ-1001": scenarios._acceptable(ctx),
        "SIM-REQ-1002": scenarios._wrong_target(ctx),
        "SIM-REQ-1003": scenarios._too_imprecise(ctx),
        "SIM-REQ-1004": owjson.write_observation_set(azel).encode("utf-8"),
    }


class Demo:
    def __init__(self) -> None:
        catalog = _packaged("catalog.json")
        self.service = RequestService(
            LedgerAdapter(),
            ReviewerRegistry.parse(_packaged("reviewers.json")),
            VerificationContext(catalog=catalog, policy=_packaged("target-policy.json")),
            task_salt="orbit-watch-phase1-demo",
        )
        self.catalog = parse_catalog(catalog)
        self.lines: list[str] = []

    def log(self, when: str, actor: str, text: str) -> None:
        self.lines.append(f"| {when[:16].replace('T', ' ')} | {actor} | {text} |")

    def outcome_text(self, request_id: str) -> str:
        record = self.service.records[request_id]
        if record.status is not lc.Status.SETTLED:
            return str(record.status)
        payouts = self.service.settlements[request_id]["plan"]["payouts"]
        paid = ", ".join(f"{p['party']} +{p['points']}" for p in payouts) or "no points"
        return f"**{record.outcome}**, settled: {paid}"

    def tick(self, when: str) -> None:
        for request_id in self.service.tick(parse_utc(when)):
            reason = self.service.records[request_id].outcome_reason
            self.log(when, "clock", f"{request_id}: {reason} -> {self.outcome_text(request_id)}")

    def answer_tasks(self, reviewer: str, when: str, skip: frozenset[str] = frozenset()) -> None:
        """Answer every open task, except real tasks of the requests in ``skip``."""
        now = parse_utc(when)
        for task in self.service.assignments(reviewer, now):
            calibration = self.service.calibration_tasks.get(task["task_id"])
            real = self.service.real_tasks.get(task["task_id"])
            if real is not None and real[0] in skip:
                continue
            if reviewer == RUBBER_STAMPER:
                approve, reason = True, "Looks fine."
            elif calibration is not None:
                approve = calibration.expected == "approve"
            else:
                approve = task["automated_verdict"] == "pass"
            if reviewer != RUBBER_STAMPER:
                reason = (
                    "Residuals follow the reference orbit."
                    if approve
                    else "The track runs about 8 s behind the requested object."
                )
            try:
                self.service.review(task["task_id"], reviewer, approve, reason, now)
            except ServiceError as error:
                if error.code != "forbidden_in_status":
                    raise
                continue  # the round was decided before this answer
            answer = "approve" if approve else "reject"
            if calibration is not None:
                verdict = "correct" if calibration.correct else "wrong"
                self.log(when, reviewer, f"answers a calibration task: {answer} ({verdict})")
            else:
                self.log(when, reviewer, f"answers the {real[0]} task: {answer}")

    def run(self) -> dict[str, Any]:
        service = self.service
        service.adapter.grant(REQUESTER, 1000, key="demo/budget")
        self.log("2026-11-01T11:00:00Z", "admin", f"grants {REQUESTER} 1000 points")
        when = "2026-11-01T12:00:00Z"
        for request_id, title, embargo in PLAN:
            service.create(
                _request_bytes(request_id, title), REQUESTER, parse_utc(when), embargo_days=embargo
            )
            service.open(request_id, REQUESTER, parse_utc(when))
            service.fund(request_id, REQUESTER, SPLIT, parse_utc(when))
        self.log(
            when,
            REQUESTER,
            "creates, opens and funds SIM-REQ-1001 to 1005 "
            f"({SPLIT.total} points each: observer {SPLIT.observer}, "
            f"reviewers {SPLIT.reviewer} each, platform fee {SPLIT.platform_fee})",
        )
        when = "2026-11-01T12:10:00Z"
        for request_id, station in (
            ("SIM-REQ-1001", ESPOO),
            ("SIM-REQ-1002", ESPOO),
            ("SIM-REQ-1003", OULU),
            ("SIM-REQ-1004", KUOPIO),
            ("SIM-REQ-1005", TAMPERE),
        ):
            service.reserve(request_id, station, parse_utc(when))
            self.log(when, station, f"reserves {request_id}")

        deliveries = _deliveries(self.catalog)
        when = "2026-11-02T04:00:00Z"
        for request_id, station in (
            ("SIM-REQ-1001", ESPOO),
            ("SIM-REQ-1002", ESPOO),
            ("SIM-REQ-1003", OULU),
            ("SIM-REQ-1004", KUOPIO),
        ):
            record = service.deliver(request_id, station, deliveries[request_id], parse_utc(when))
            self.log(
                when,
                station,
                f"delivers {request_id}: automated verification "
                f"**{record.automated_verdict}**, challenge period until "
                f"{format_utc(record.challenge_deadline)[:16].replace('T', ' ')}",
            )

        when = "2026-11-02T05:00:00Z"
        record = service.challenge(
            "SIM-REQ-1002", ESPOO, "I am sure this was SIM-CUBESAT-A.", parse_utc(when)
        )
        self.log(when, ESPOO, f"challenges SIM-REQ-1002; reviewers {', '.join(record.reviewers)}")
        record = service.challenge(
            "SIM-REQ-1004", REQUESTER, "Second opinion before we update our orbit.", parse_utc(when)
        )
        self.log(
            when, REQUESTER, f"challenges SIM-REQ-1004; reviewers {', '.join(record.reviewers)}"
        )

        # Reviewers answer their queues. In SIM-REQ-1004 only the first reviewer
        # answers in time, so that round ends without a majority.
        when = "2026-11-02T06:00:00Z"
        slow = service.records["SIM-REQ-1004"].reviewers
        involved = sorted(set(service.records["SIM-REQ-1002"].reviewers) | set(slow))
        for reviewer in involved:
            skip = frozenset() if reviewer == slow[0] else frozenset({"SIM-REQ-1004"})
            self.answer_tasks(reviewer, when, skip)
        if service.records["SIM-REQ-1002"].status is lc.Status.SETTLED:
            self.log(
                when,
                "service",
                f"SIM-REQ-1002: "
                f"{service.records['SIM-REQ-1002'].outcome_reason} -> "
                f"{self.outcome_text('SIM-REQ-1002')}",
            )

        for when in (
            "2026-11-03T03:00:00Z",
            "2026-11-03T04:00:00Z",
            "2026-11-04T05:00:00Z",
            FINAL_TIME,
        ):
            self.tick(when)

        final = parse_utc(FINAL_TIME)
        reviewers = sorted(
            {r for rec in service.records.values() for r in rec.reviewers}
            | {t.reviewer for t in service.calibration_tasks.values()}
        )
        parties = [REQUESTER, ESPOO, OULU, KUOPIO, TAMPERE, *reviewers]
        return {
            "notice": SIMULATION_NOTICE,
            "as_of": FINAL_TIME,
            "requests": {
                rid: {
                    "summary": service.summary(rid),
                    "publication": service.publication(rid, final),
                }
                for rid in sorted(service.records)
            },
            "balances": {party: service.adapter.balance(party) for party in parties},
            "escrow_total": sum(service.adapter.escrow(rid) for rid in service.records),
            "reviewer_profiles": {r: service.reviewer_profile(r, final) for r in reviewers},
            "journal_entries": len(service.adapter.journal),
        }


def run_phase1_demo(out_dir: str | Path) -> dict[str, Any]:
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    demo = Demo()
    summary = demo.run()
    write_text(out / "summary.json", dumps_pretty(summary, sort_keys=False))
    write_text(out / "transcript.md", _transcript(demo, summary))
    write_text(out / "README.md", _readme())
    return summary


def _transcript(demo: Demo, summary: dict[str, Any]) -> str:
    rows = "\n".join(demo.lines)
    outcomes = "\n".join(
        f"| {rid} | {item['summary']['outcome']} | {item['summary']['automated_verdict'] or '-'} "
        f"| {item['publication']['state']} | {item['publication']['public_from'] or '-'} |"
        for rid, item in summary["requests"].items()
    )
    balances = "\n".join(
        f"| {party} | {points} |" for party, points in summary["balances"].items() if points
    )
    profiles = "\n".join(
        f"| {r} | {p['calibration']['correct']}/{p['calibration']['answered']} | "
        f"{'-' if p['votes']['approval_rate'] is None else f'{p["votes"]["approval_rate"]:.0%}'} "
        f"| {', '.join(p['flags']) or '-'} |"
        for r, p in summary["reviewer_profiles"].items()
    )
    return f"""# Orbit Watch phase 1 demo (SIMULATED)

> {SIMULATION_NOTICE}

Five simulated requests run through the whole chain on a simulated clock. Points
are bookkeeping only: no money and no blockchain.

## What happened

| Time (UTC) | Who | What |
|---|---|---|
{rows}

## Outcomes on {summary["as_of"][:10]}

| Request | Outcome | Automated result | Data | Public from |
|---|---|---|---|---|
{outcomes}

## Points

| Party | Points |
|---|---|
{balances}

Points in escrow: {summary["escrow_total"]}. Every deposit was paid out or refunded.

## Reviewers

`{RUBBER_STAMPER}` approves every task without looking; the others answer
carefully. Calibration tasks are mixed into their queues.

| Reviewer | Calibration correct | Approval rate | Flags |
|---|---|---|---|
{profiles}
"""


def _readme() -> str:
    return f"""# Orbit Watch phase 1 demo output (SIMULATED)

> {SIMULATION_NOTICE}

Generated by `orbit-watch demo --phase 1`. CI regenerates it and requires a
byte-identical result.

- `transcript.md`: what happened, the outcomes, the points and the reviewer profiles
- `summary.json`: the same as data (request summaries, publication state,
  balances, reviewer profiles)

The demo runs the request service in memory on a simulated clock. To run the
same chain through the HTTP API and the command line, see `docs/api.md`.
"""

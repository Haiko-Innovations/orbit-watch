"""The settlement scenario suite: the same scenarios for every adapter.

Each scenario drives a request through the lifecycle and mirrors every step to
a settlement adapter, the way the phase 1 service will. ``check_adapter``
runs all scenarios against a fresh adapter each and returns the problems it
finds; an adapter is correct when the list is empty. The phase 2 testnet
adapter must pass the same suite (plan, section 6).

What is checked in every scenario:

* the outcome and every party's net change in points;
* conservation: deposit = rewards + refunds, the escrow ends at zero and no
  points are created or lost;
* idempotency: replaying every call with the same keys changes nothing, and a
  second settlement under a new key is refused.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any

from orbit_watch import lifecycle as lc
from orbit_watch.lifecycle import Status
from orbit_watch.settlement import (
    RULES_VERSION,
    SettlementAdapter,
    SettlementError,
    settlement_plan,
)
from orbit_watch.timeutil import parse_utc

T0 = parse_utc("2026-11-01T12:00:00Z")
REQUESTER = "requester:alice"
STATION = "station:SIM-ESPOO"
OTHER_STATION = "station:SIM-TAMPERE"
R1, R2, R3 = "reviewer:r1", "reviewer:r2", "reviewer:r3"
REVIEWERS = (R1, R2, R3)
PLATFORM = "platform:orbit-watch"
VERIFIER = "system:verifier"
SHA = "d" * 64
REPORT = "e" * 64
SPLIT = lc.RewardSplit(observer=100, reviewer=10, platform_fee=5)  # deposit 135
BUDGET = 1000


def at(minutes: float) -> datetime:
    return T0 + timedelta(minutes=minutes)


def scenario_terms(request_id: str) -> lc.Terms:
    return lc.Terms(
        request_id=request_id,
        request_sha256="c" * 64,
        requester=REQUESTER,
        target_norad_id=339001,
        window_start=parse_utc("2026-11-01T15:00:00Z"),
        window_end=parse_utc("2026-11-02T03:00:00Z"),
        delivery_deadline=parse_utc("2026-11-03T03:00:00Z"),
        reservation_hours=6,
    )


@dataclass
class Advance:
    """Let time pass (deadlines apply)."""

    to: datetime


Step = Any  # a lifecycle event or Advance


@dataclass
class Scenario:
    name: str
    description: str
    steps: list[Step]
    outcome: Status
    net: dict[str, int]  # expected change in points per party; others unchanged
    funded: bool = True


def _deliver_path(verdict: str, reviewers: tuple[str, ...] = ()) -> list[Step]:
    return [
        lc.Open(at(1)),
        lc.Fund(at(2), SPLIT),
        lc.Reserve(at(3), STATION),
        lc.Deliver(at(300), STATION, SHA),
        lc.RecordVerification(at(310), verdict, REPORT, reviewers),
    ]


END_OF_CHALLENGE = at(310 + 24 * 60 + 1)

SCENARIOS: list[Scenario] = [
    Scenario(
        "accepted_unchallenged",
        "Automated verification passes and nobody challenges.",
        [*_deliver_path("pass"), Advance(END_OF_CHALLENGE)],
        Status.ACCEPTED,
        {REQUESTER: -105, STATION: 100, PLATFORM: 5},
    ),
    Scenario(
        "rejected_unchallenged",
        "Automated verification fails and nobody challenges: full refund.",
        [*_deliver_path("fail"), Advance(END_OF_CHALLENGE)],
        Status.REJECTED,
        {},
    ),
    Scenario(
        "challenged_and_accepted",
        "The observer challenges a failed result; two reviewers approve.",
        [
            *_deliver_path("fail"),
            lc.Challenge(at(320), STATION, REVIEWERS, "orbit too old"),
            lc.Vote(at(330), R1, True),
            lc.Vote(at(340), R2, True),
        ],
        Status.ACCEPTED,
        {REQUESTER: -125, STATION: 100, R1: 10, R2: 10, PLATFORM: 5},
    ),
    Scenario(
        "challenged_and_rejected",
        "The requester challenges a pass; the reviewers reject 2-1. All three are paid.",
        [
            *_deliver_path("pass"),
            lc.Challenge(at(320), REQUESTER, REVIEWERS),
            lc.Vote(at(330), R1, False),
            lc.Vote(at(340), R2, True),
            lc.Vote(at(350), R3, False),
        ],
        Status.REJECTED,
        {REQUESTER: -30, R1: 10, R2: 10, R3: 10},
    ),
    Scenario(
        "disputed",
        "One reviewer votes before the deadline: dispute. The one review is paid, the "
        "observer gets nothing, the rest is refunded.",
        [
            *_deliver_path("pass"),
            lc.Challenge(at(320), REQUESTER, REVIEWERS),
            lc.Vote(at(330), R1, True),
            Advance(at(320 + 48 * 60 + 1)),
        ],
        Status.DISPUTED,
        {REQUESTER: -10, R1: 10},
    ),
    Scenario(
        "inconclusive_then_accepted",
        "An inconclusive result goes to reviewers, who approve.",
        [
            *_deliver_path("inconclusive", REVIEWERS),
            lc.Vote(at(330), R2, True),
            lc.Vote(at(340), R3, True),
        ],
        Status.ACCEPTED,
        {REQUESTER: -125, STATION: 100, R2: 10, R3: 10, PLATFORM: 5},
    ),
    Scenario(
        "expired_without_delivery",
        "A station reserves but never delivers: full refund after the deadline.",
        [
            lc.Open(at(1)),
            lc.Fund(at(2), SPLIT),
            lc.Reserve(at(3), STATION),
            Advance(parse_utc("2026-11-03T03:00:01Z")),
        ],
        Status.EXPIRED,
        {},
    ),
    Scenario(
        "cancelled_after_funding",
        "The requester cancels before anyone reserves: full refund.",
        [lc.Open(at(1)), lc.Fund(at(2), SPLIT), lc.Cancel(at(5), REQUESTER)],
        Status.CANCELLED,
        {},
    ),
    Scenario(
        "lapsed_reservation_then_other_station",
        "The first reservation lapses; another station delivers and is paid.",
        [
            lc.Open(at(1)),
            lc.Fund(at(2), SPLIT),
            lc.Reserve(at(3), STATION),
            Advance(at(3 + 6 * 60 + 1)),
            lc.Reserve(at(400), OTHER_STATION),
            lc.Deliver(at(500), OTHER_STATION, SHA),
            lc.RecordVerification(at(510), "pass", REPORT),
            Advance(at(510 + 24 * 60 + 1)),
        ],
        Status.ACCEPTED,
        {REQUESTER: -105, OTHER_STATION: 100, PLATFORM: 5},
    ),
    Scenario(
        "unfunded_accepted",
        "A volunteer request without points: nothing moves.",
        [
            lc.Open(at(1)),
            lc.Reserve(at(3), STATION),
            lc.Deliver(at(300), STATION, SHA),
            lc.RecordVerification(at(310), "pass", REPORT),
            Advance(END_OF_CHALLENGE),
        ],
        Status.ACCEPTED,
        {},
        funded=False,
    ),
]

PARTIES = (REQUESTER, STATION, OTHER_STATION, R1, R2, R3, PLATFORM)


@dataclass
class Driver:
    """Applies lifecycle events and mirrors them to an adapter, logging every call."""

    adapter: SettlementAdapter
    record: lc.RequestRecord
    calls: list[tuple[str, tuple, dict]] = field(default_factory=list)
    _count: int = 0

    def _call(self, method: str, *args: Any, key: str) -> Any:
        self.calls.append((method, args, {"key": key}))
        return getattr(self.adapter, method)(*args, key=key)

    def _key(self, label: str) -> str:
        self._count += 1
        return f"{self.record.request_id}/{self._count:03d}/{label}"

    def step(self, step: Step) -> None:
        rid = self.record.request_id
        if isinstance(step, Advance):
            self.record = lc.advance(self.record, step.to)
            return
        self.record = lc.apply(self.record, step)
        if isinstance(step, lc.Fund):
            self._call("fund", rid, self.record.requester, step.split.total, key=self._key("fund"))
        elif isinstance(step, lc.Reserve):
            self._call("reserve", rid, step.station, key=self._key("reserve"))
        elif isinstance(step, lc.RecordVerification):
            self._call(
                "attest",
                rid,
                VERIFIER,
                "automated_verification",
                step.report_sha256,
                step.verdict,
                key=self._key("verification"),
            )
        elif isinstance(step, lc.Vote):
            self._call(
                "attest",
                rid,
                step.reviewer,
                "review_vote",
                self.record.delivery_sha256 or "",
                "approve" if step.approve else "reject",
                key=self._key("vote"),
            )

    def settle(self, when: datetime) -> None:
        """Pay out by the shared rules, then mark the request settled."""
        rid = self.record.request_id
        plan = settlement_plan(self.record, platform=PLATFORM)
        if self.record.status in (Status.EXPIRED, Status.CANCELLED) and plan.deposit:
            self._call("refund", rid, self.record.requester, key=f"{rid}/settle")
        else:
            self._call("settle", plan, key=f"{rid}/settle")
        self.record = lc.apply(self.record, lc.Settle(when))

    def replay(self) -> None:
        for method, args, kwargs in self.calls:
            getattr(self.adapter, method)(*args, **kwargs)


AdapterFactory = Callable[[dict[str, int]], SettlementAdapter]


def run_scenario(factory: AdapterFactory, scenario: Scenario) -> list[str]:
    """Run one scenario on a fresh adapter. Returns problems (empty when correct)."""
    problems: list[str] = []
    adapter = factory({REQUESTER: BUDGET})
    before = {party: adapter.balance(party) for party in PARTIES}
    record = lc.create(scenario_terms(f"SIM-{scenario.name}"), T0)
    driver = Driver(adapter, record)
    for step in scenario.steps:
        driver.step(step)
    if driver.record.status is not scenario.outcome:
        return [f"{scenario.name}: outcome {driver.record.status}, expected {scenario.outcome}"]
    plan = settlement_plan(driver.record, platform=PLATFORM)
    if plan.paid_out != plan.deposit:
        problems.append(f"{scenario.name}: plan pays {plan.paid_out} of {plan.deposit}")
    driver.settle(driver.record.updated_at)
    rid = driver.record.request_id
    after = {party: adapter.balance(party) for party in PARTIES}
    net = {
        party: after[party] - before[party] for party in PARTIES if after[party] != before[party]
    }
    if net != scenario.net:
        problems.append(f"{scenario.name}: net change {net}, expected {scenario.net}")
    if sum(net.values()) != 0:
        problems.append(f"{scenario.name}: points created or lost ({sum(net.values())})")
    if adapter.escrow(rid) != 0:
        problems.append(f"{scenario.name}: {adapter.escrow(rid)} points left in escrow")
    expected_deposit = SPLIT.total if scenario.funded else 0
    if plan.deposit != expected_deposit:
        problems.append(f"{scenario.name}: deposit {plan.deposit}, expected {expected_deposit}")
    # Idempotency: replaying every call with its key has no second effect.
    try:
        driver.replay()
    except SettlementError as error:
        problems.append(f"{scenario.name}: replaying the calls was refused ({error.code})")
    replayed = {party: adapter.balance(party) for party in PARTIES}
    if replayed != after:
        problems.append(f"{scenario.name}: replaying the calls changed balances")
    # A second settlement under a new key is refused.
    try:
        adapter.settle(plan, key=f"{rid}/settle-again")
        problems.append(f"{scenario.name}: a second settlement was accepted")
    except SettlementError as error:
        if error.code != "already_settled":
            problems.append(f"{scenario.name}: second settlement refused with {error.code}")
    return problems


def check_adapter(factory: AdapterFactory) -> list[str]:
    """Run the whole suite. An adapter is correct when this returns an empty list."""
    problems: list[str] = []
    for scenario in SCENARIOS:
        problems.extend(run_scenario(factory, scenario))
    return problems


def _seconds(when: datetime) -> int:
    delta = (when - T0).total_seconds()
    if delta != int(delta):  # pragma: no cover - the scenarios use whole seconds
        raise ValueError(f"{when} is not a whole number of seconds after T0")
    return int(delta)


def _hours_to_seconds(hours: float) -> int:
    seconds = hours * 3600
    if seconds != int(seconds):  # pragma: no cover - the scenarios use whole seconds
        raise ValueError(f"{hours} hours is not a whole number of seconds")
    return int(seconds)


def _fixture_step(step: Step, requester: str) -> dict[str, Any]:
    if isinstance(step, Advance):
        return {"action": "wait", "at": _seconds(step.to)}
    at = _seconds(step.at)
    if isinstance(step, lc.Open):
        return {"action": "open", "at": at}
    if isinstance(step, lc.Fund):
        return {"action": "fund", "at": at, "party": requester}
    if isinstance(step, lc.Reserve):
        return {"action": "reserve", "at": at, "party": step.station}
    if isinstance(step, lc.Deliver):
        return {"action": "deliver", "at": at, "party": step.station}
    if isinstance(step, lc.RecordVerification):
        return {
            "action": "verify",
            "at": at,
            "verdict": step.verdict,
            "reviewers": list(step.reviewers),
        }
    if isinstance(step, lc.Challenge):
        return {
            "action": "challenge",
            "at": at,
            "party": step.party,
            "reviewers": list(step.reviewers),
        }
    if isinstance(step, lc.Vote):
        return {"action": "vote", "at": at, "party": step.reviewer, "approve": step.approve}
    if isinstance(step, lc.Cancel):
        return {"action": "cancel", "at": at, "party": step.party}
    raise TypeError(f"no fixture form for {step!r}")  # pragma: no cover


def contract_fixture() -> dict[str, Any]:
    """The suite as data, for the Solidity tests of the escrow contract (phase 2).

    The contract tests replay every funded scenario on chain and check the same outcome
    and net changes, so the escrow and the ledger follow the same rules. Times are whole
    seconds after ``T0``. Write it with ``python -m orbit_watch.settlement.scenarios``.
    """
    scenarios = []
    for scenario in SCENARIOS:
        terms = scenario_terms(f"SIM-{scenario.name}")
        scenarios.append(
            {
                "name": scenario.name,
                "description": scenario.description,
                "funded": scenario.funded,
                "requester": terms.requester,
                "terms": {
                    "delivery_deadline": _seconds(terms.delivery_deadline),
                    "reservation_seconds": _hours_to_seconds(terms.reservation_hours),
                    "verification_timeout_seconds": _hours_to_seconds(
                        terms.verification_timeout_hours
                    ),
                    "challenge_seconds": _hours_to_seconds(terms.challenge_period_hours),
                    "review_seconds": _hours_to_seconds(terms.review_hours),
                },
                "steps": [_fixture_step(step, terms.requester) for step in scenario.steps],
                "outcome": str(scenario.outcome),
                "net": [
                    {"party": party, "change": change}
                    for party, change in sorted(scenario.net.items())
                ],
            }
        )
    return {
        "about": (
            "SIMULATED settlement scenarios for the escrow contract tests. Generated from "
            "core/src/orbit_watch/settlement/scenarios.py with "
            "`python -m orbit_watch.settlement.scenarios`; do not edit by hand."
        ),
        "simulated": True,
        "rules_version": RULES_VERSION,
        "t0": int(T0.timestamp()),
        "budget": BUDGET,
        "split": {
            "observer": SPLIT.observer,
            "reviewer": SPLIT.reviewer,
            "platform_fee": SPLIT.platform_fee,
        },
        "platform": PLATFORM,
        "parties": list(PARTIES),
        "scenarios": scenarios,
    }


def contract_fixture_json() -> str:
    import json

    return json.dumps(contract_fixture(), indent=2, ensure_ascii=False) + "\n"


def ledger_factory(budgets: dict[str, int]):
    from orbit_watch.settlement.ledger import LedgerAdapter

    ledger = LedgerAdapter()
    for party, points in sorted(budgets.items()):
        ledger.grant(party, points, key=f"budget/{party}")
    return ledger


if __name__ == "__main__":  # pragma: no cover - exercised by the fixture test
    import sys

    sys.stdout.write(contract_fixture_json())

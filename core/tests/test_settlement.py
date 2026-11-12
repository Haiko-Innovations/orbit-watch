"""Settlement rules, the ledger adapter and the adapter scenario suite (step 1.2)."""

import json
import random
import subprocess
import sys
from datetime import timedelta
from pathlib import Path

import pytest

from orbit_watch import lifecycle as lc
from orbit_watch.lifecycle import Status
from orbit_watch.settlement import (
    Payout,
    SettlementError,
    SettlementPlan,
    settlement_plan,
)
from orbit_watch.settlement import scenarios as sc
from orbit_watch.settlement.ledger import LedgerAdapter, Posting


@pytest.mark.parametrize("scenario", sc.SCENARIOS, ids=lambda s: s.name)
def test_ledger_passes_every_scenario(scenario):
    assert sc.run_scenario(sc.ledger_factory, scenario) == []


def test_suite_as_a_whole():
    assert sc.check_adapter(sc.ledger_factory) == []
    assert len(sc.SCENARIOS) >= 10


# ------------------------------------------------------------------ the suite catches bugs


class ForgetfulLedger(LedgerAdapter):
    """Ignores idempotency keys."""

    def _idempotent(self, key, fingerprint):
        return None


class GenerousLedger(LedgerAdapter):
    """Pays observers twice: creates points out of nothing."""

    def settle(self, plan, *, key, record=None):
        receipt = super().settle(plan, key=key)
        for payout in plan.payouts:
            if payout.reason == "observer_reward":
                self._record(
                    key + "/bonus",
                    {"bonus": key},
                    "bonus",
                    plan.request_id,
                    [
                        Posting("issuance", -payout.points),
                        Posting(f"party:{payout.party}", payout.points),
                    ],
                    "bonus",
                )
        return receipt


class TwiceSettlingLedger(LedgerAdapter):
    """Forgets which requests were settled."""

    def settle(self, plan, *, key, record=None):
        self._settled.pop(plan.request_id, None)
        return super().settle(plan, key=key)


def factory_for(cls):
    def factory(budgets):
        ledger = cls()
        for party, points in budgets.items():
            ledger.grant(party, points, key=f"budget/{party}")
        return ledger

    return factory


@pytest.mark.parametrize(
    ("cls", "symptom"),
    [
        (ForgetfulLedger, "replaying the calls"),
        (GenerousLedger, "net change"),
        (TwiceSettlingLedger, "second settlement"),
    ],
)
def test_the_suite_catches_broken_adapters(cls, symptom):
    problems = sc.check_adapter(factory_for(cls))
    assert any(symptom in p for p in problems), problems


# ------------------------------------------------------------------ rules


def finished(outcome_steps, split=sc.SPLIT):
    record = lc.create(sc.scenario_terms("SIM-RULES"), sc.T0)
    for step in outcome_steps:
        record = (
            lc.advance(record, step.to) if isinstance(step, sc.Advance) else lc.apply(record, step)
        )
    return record


def test_plan_for_each_outcome():
    by_name = {s.name: s for s in sc.SCENARIOS}
    record = finished(by_name["challenged_and_accepted"].steps)
    plan = settlement_plan(record, platform=sc.PLATFORM)
    assert plan.deposit == 135 and plan.paid_out == 135
    assert plan.payouts == (
        Payout(sc.STATION, 100, "observer_reward"),
        Payout(sc.R1, 10, "review"),
        Payout(sc.R2, 10, "review"),
        Payout(sc.PLATFORM, 5, "platform_fee"),
        Payout(sc.REQUESTER, 10, "refund"),
    )
    disputed = settlement_plan(finished(by_name["disputed"].steps), platform=sc.PLATFORM)
    assert [p.reason for p in disputed.payouts] == ["review", "refund"]
    assert settlement_plan(finished(by_name["unfunded_accepted"].steps)).payouts == ()


def test_no_plan_before_an_outcome():
    record = finished([lc.Open(sc.at(1))])
    with pytest.raises(SettlementError) as error:
        settlement_plan(record)
    assert error.value.code == "not_finished"


def test_plan_after_settling_is_the_same():
    steps = sc.SCENARIOS[0].steps
    record = finished(steps)
    settled = lc.apply(record, lc.Settle(record.updated_at))
    assert settlement_plan(settled, platform=sc.PLATFORM) == settlement_plan(
        record, platform=sc.PLATFORM
    )


# ------------------------------------------------------------------ ledger


def test_ledger_refuses_bad_calls():
    ledger = LedgerAdapter()
    ledger.grant("alice", 50, key="g1")
    cases = [
        (lambda: ledger.fund("R1", "alice", 60, key="f1"), "insufficient_points"),
        (lambda: ledger.fund("R1", "alice", 0, key="f2"), "invalid_amount"),
        (lambda: ledger.grant("alice", 5, key=""), "missing_key"),
        (lambda: ledger.grant("bob", 5, key="g1"), "key_reused"),
    ]
    for call, code in cases:
        with pytest.raises(SettlementError) as error:
            call()
        assert error.value.code == code
    ledger.fund("R1", "alice", 40, key="f3")
    with pytest.raises(SettlementError) as error:
        ledger.fund("R1", "alice", 5, key="f4")
    assert error.value.code == "already_funded"
    unbalanced = SettlementPlan("R1", "accepted", 40, (Payout("bob", 30, "observer_reward"),))
    with pytest.raises(SettlementError) as error:
        ledger.settle(unbalanced, key="s1")
    assert error.value.code == "unbalanced_plan"
    wrong_deposit = SettlementPlan("R1", "rejected", 30, (Payout("alice", 30, "refund"),))
    with pytest.raises(SettlementError) as error:
        ledger.settle(wrong_deposit, key="s2")
    assert error.value.code == "escrow_mismatch"
    ledger.refund("R1", "alice", key="r1")
    assert ledger.balance("alice") == 50 and ledger.escrow("R1") == 0
    with pytest.raises(SettlementError) as error:
        ledger.refund("R1", "alice", key="r2")
    assert error.value.code == "already_settled"


def test_journal_is_balanced_and_exports_deterministically():
    exports = []
    for _ in range(2):
        ledger = sc.ledger_factory({sc.REQUESTER: 500})
        driver = sc.Driver(ledger, lc.create(sc.scenario_terms("SIM-X"), sc.T0))
        for step in sc.SCENARIOS[2].steps:
            driver.step(step)
        driver.settle(driver.record.updated_at)
        assert ledger.total() == 0
        assert all(sum(p["amount"] for p in e["postings"]) == 0 for e in ledger.export()["journal"])
        exports.append(ledger.export())
    assert exports[0] == exports[1]
    kinds = [a["kind"] for a in exports[0]["attestations"]]
    assert kinds == ["automated_verification", "review_vote", "review_vote"]


# ------------------------------------------------------------------ property


def random_step(choice, now, rng, parties):
    if choice == 0:
        return lc.Open(now)
    if choice == 1:
        split = lc.RewardSplit(rng.randint(0, 200), rng.randint(0, 20), rng.randint(0, 9))
        return lc.Fund(now, split)
    if choice == 2:
        return lc.Reserve(now, rng.choice(parties))
    if choice == 3:
        return lc.Deliver(now, rng.choice(parties), sc.SHA)
    if choice == 4:
        verdict = rng.choice(["pass", "fail", "inconclusive"])
        return lc.RecordVerification(now, verdict, sc.REPORT, tuple(rng.sample(parties, 3)))
    if choice == 5:
        return lc.Challenge(now, rng.choice(parties), tuple(rng.sample(parties, 3)))
    if choice == 6:
        return lc.Vote(now, rng.choice(parties), rng.random() < 0.5)
    return lc.Cancel(now, rng.choice(parties))


@pytest.mark.parametrize("seed", range(100))
def test_points_are_never_created_or_lost(seed):
    """Random request histories: whatever happens, the books balance."""
    rng = random.Random(seed)
    ledger = sc.ledger_factory({sc.REQUESTER: sc.BUDGET})
    driver = sc.Driver(ledger, lc.create(sc.scenario_terms(f"SIM-RANDOM-{seed}"), sc.T0))
    parties = [sc.REQUESTER, sc.STATION, sc.OTHER_STATION, *sc.REVIEWERS]
    now = sc.T0
    for _ in range(30):
        now += timedelta(minutes=rng.choice([1, 30, 120, 900]))
        step = random_step(rng.randrange(8), now, rng, parties)
        try:
            driver.step(step)
        except (lc.TransitionError, SettlementError):
            continue
    driver.record = lc.advance(driver.record, now + timedelta(days=30))
    if driver.record.status in lc.OUTCOMES:
        plan = settlement_plan(driver.record, platform=sc.PLATFORM)
        assert plan.paid_out == plan.deposit
        driver.settle(driver.record.updated_at)
        assert driver.record.status is Status.SETTLED
        assert ledger.escrow(driver.record.request_id) == 0
    held = sum(ledger.balance(p) for p in [*parties, sc.PLATFORM])
    assert held + ledger.escrow(driver.record.request_id) == sc.BUDGET
    assert ledger.total() == 0


# ------------------------------------------------------------------ contract fixture

CONTRACT_FIXTURE = (
    Path(__file__).resolve().parents[2] / "contracts/test/fixtures/settlement-scenarios.json"
)


def test_the_contract_fixture_is_current():
    """The escrow contract's tests replay this suite. Regenerate the file in ``core/`` with
    ``uv run python -m orbit_watch.settlement.scenarios > <the fixture path>``."""
    assert CONTRACT_FIXTURE.read_text(encoding="utf-8") == sc.contract_fixture_json()


def test_the_contract_fixture_covers_every_scenario():
    fixture = json.loads(sc.contract_fixture_json())
    assert fixture["simulated"] is True and fixture["rules_version"] == "1.0"
    assert [s["name"] for s in fixture["scenarios"]] == [s.name for s in sc.SCENARIOS]
    for scenario, exported in zip(sc.SCENARIOS, fixture["scenarios"], strict=True):
        assert len(exported["steps"]) == len(scenario.steps)
        assert {n["party"]: n["change"] for n in exported["net"]} == scenario.net
        assert sum(n["change"] for n in exported["net"]) == 0
    actions = {step["action"] for s in fixture["scenarios"] for step in s["steps"]}
    assert actions == {
        "open",
        "fund",
        "reserve",
        "deliver",
        "verify",
        "challenge",
        "vote",
        "cancel",
        "wait",
    }


def test_the_fixture_command_prints_the_fixture():
    printed = subprocess.run(
        [sys.executable, "-m", "orbit_watch.settlement.scenarios"],
        check=True,
        capture_output=True,
        text=True,
    ).stdout
    assert printed == sc.contract_fixture_json()

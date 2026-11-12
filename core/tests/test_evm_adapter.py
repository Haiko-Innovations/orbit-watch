"""The evm-testnet settlement adapter (phase 2, step 2.5) on a local Anvil chain.

The phase 1 settlement scenario suite must pass against the escrow contract exactly as it
passes against the points ledger (decision P2-08). Every chain here is local, its parties
are SIMULATED and their accounts are local test accounts (see tests/anvil.py).
"""

from datetime import timedelta

import pytest
from anvil import CONTRACTS_OUT, Deployment, require_local_chain, test_account

from orbit_watch import lifecycle as lc
from orbit_watch.settlement import SettlementError
from orbit_watch.settlement import scenarios as sc

GENESIS = int(sc.T0.timestamp()) - 86400  # the chain starts a day before the scenarios


@pytest.fixture
def deployments():
    require_local_chain()
    made: list[Deployment] = []
    yield made
    for deployment in made:
        deployment.chain.stop()


def deploy(made, budgets):
    deployment = Deployment(
        GENESIS,
        reviewers=list(sc.REVIEWERS),
        platform=sc.PLATFORM,
        verifier=sc.VERIFIER,
        parties=list(sc.PARTIES),
    )
    made.append(deployment)
    for party, amount in sorted(budgets.items()):
        deployment.give_budget(party, amount)
    return deployment


def adapter_for(deployment):
    from orbit_watch.chain.client import OrbitWatchChain
    from orbit_watch.settlement.evm import EvmTestnetAdapter

    chain = OrbitWatchChain(deployment.chain.w3, deployment.escrow.address)
    return EvmTestnetAdapter(
        chain,
        deployment.accounts,
        platform=sc.PLATFORM,
        verifier=sc.VERIFIER,
        follow_record_time=True,
    )


def test_the_adapter_passes_the_settlement_scenario_suite(deployments):
    """All ten scenarios, each on a fresh chain: outcomes, every party's net change, nothing
    left in escrow, replayed calls without effect, and a second settlement refused. Each
    settlement is also checked against the shared rules, payout by payout."""
    assert sc.check_adapter(lambda budgets: adapter_for(deploy(deployments, budgets))) == []


def test_the_abis_in_the_package_match_the_contracts():
    require_local_chain()
    from orbit_watch.chain import abi

    for name in abi.SOURCES:
        assert abi.load(name) == abi.from_foundry(CONTRACTS_OUT, name), (
            f"{name}.json is stale: run python -m orbit_watch.chain.abi ../contracts/out"
        )


# ------------------------------------------------------------------ refusals


def funded(deployments):
    """A funded request on a fresh chain, with its adapter and driver."""
    deployment = deploy(deployments, {sc.REQUESTER: sc.BUDGET})
    adapter = adapter_for(deployment)
    driver = sc.Driver(adapter, lc.create(sc.scenario_terms("SIM-REQ-EVM"), sc.T0))
    driver.step(lc.Open(sc.at(1)))
    driver.step(lc.Fund(sc.at(2), sc.SPLIT))
    return adapter, driver


def test_refusals_carry_the_contracts_error(deployments):
    adapter, driver = funded(deployments)
    record = lc.apply(driver.record, lc.Reserve(sc.at(3), sc.STATION))
    with pytest.raises(SettlementError) as error:  # the requester cannot reserve
        adapter.reserve("SIM-REQ-EVM", sc.REQUESTER, key="k1", record=record)
    assert error.value.code == "requester_cannot_reserve"
    with pytest.raises(SettlementError) as error:  # funding twice
        adapter.fund("SIM-REQ-EVM", sc.REQUESTER, sc.SPLIT.total, key="k2", record=driver.record)
    assert error.value.code == "already_funded"


def test_keys_are_idempotent_and_never_reused(deployments):
    adapter, driver = funded(deployments)
    record = lc.apply(driver.record, lc.Reserve(sc.at(3), sc.STATION))
    first = adapter.reserve("SIM-REQ-EVM", sc.STATION, key="reserve", record=record)
    assert first.reference.startswith("0x")
    again = adapter.reserve("SIM-REQ-EVM", sc.STATION, key="reserve", record=record)
    assert again == first  # no second transaction
    with pytest.raises(SettlementError) as error:
        adapter.reserve("SIM-REQ-EVM", sc.OTHER_STATION, key="reserve", record=record)
    assert error.value.code == "key_reused"


def test_the_adapter_needs_the_record_and_accounts(deployments):
    adapter, driver = funded(deployments)
    with pytest.raises(SettlementError) as error:
        adapter.reserve("SIM-REQ-EVM", sc.STATION, key="r")
    assert error.value.code == "record_required"
    record = lc.apply(driver.record, lc.Reserve(sc.at(3), "station:unknown"))
    with pytest.raises(SettlementError) as error:
        adapter.reserve("SIM-REQ-EVM", "station:unknown", key="r2", record=record)
    assert error.value.code == "no_account"


def test_a_round_the_chain_did_not_choose_is_refused(deployments):
    """The lifecycle record's reviewers must be the escrow's. Here the record names a
    reviewer the chain never chose, and the adapter says so."""
    adapter, driver = funded(deployments)
    driver.step(lc.Reserve(sc.at(3), sc.STATION))
    driver.step(lc.Deliver(sc.at(300), sc.STATION, sc.SHA))
    driver.step(lc.RecordVerification(sc.at(310), "pass", sc.REPORT))
    wrong = (sc.R1, sc.R2, "reviewer:somebody-else")
    record = lc.apply(driver.record, lc.Challenge(sc.at(320), sc.REQUESTER, wrong, "why"))
    adapter.accounts["reviewer:somebody-else"] = test_account("reviewer:somebody-else")
    with pytest.raises(SettlementError) as error:
        adapter.challenge("SIM-REQ-EVM", sc.REQUESTER, "why", key="c", record=record)
    assert error.value.code == "reviewers_differ"


def test_settlement_needs_a_finished_request(deployments):
    from orbit_watch.settlement import settlement_plan

    adapter, driver = funded(deployments)
    later = lc.advance(driver.record, sc.at(2) + timedelta(days=3))  # expired
    plan = settlement_plan(later)
    with pytest.raises(SettlementError) as error:  # an expiry is a refund, not a payout
        adapter.refund("SIM-REQ-EVM", sc.REQUESTER, key="x", record=driver.record)
    assert error.value.code == "not_refundable"
    adapter.refund("SIM-REQ-EVM", sc.REQUESTER, key="refund", record=later)
    with pytest.raises(SettlementError) as error:
        adapter.settle(plan, key="again", record=later)
    assert error.value.code == "already_settled"
    assert adapter.balance(sc.REQUESTER) == sc.BUDGET


def test_the_adapter_notices_when_the_chain_and_the_rules_disagree(deployments):
    """A plan that differs from what the escrow pays (here: the observer reward goes to the
    requester) is reported, payout by payout, after the chain has settled."""
    import dataclasses

    from orbit_watch.settlement import Payout, settlement_plan

    adapter, driver = funded(deployments)
    for step in [
        lc.Reserve(sc.at(3), sc.STATION),
        lc.Deliver(sc.at(300), sc.STATION, sc.SHA),
        lc.RecordVerification(sc.at(310), "pass", sc.REPORT),
        sc.Advance(sc.END_OF_CHALLENGE),
    ]:
        driver.step(step)
    plan = settlement_plan(driver.record, platform=sc.PLATFORM)
    wrong = dataclasses.replace(
        plan,
        payouts=tuple(
            Payout(sc.REQUESTER, p.points, p.reason) if p.reason == "observer_reward" else p
            for p in plan.payouts
        ),
    )
    with pytest.raises(SettlementError) as error:
        adapter.settle(wrong, key="settle", record=driver.record)
    assert error.value.code == "chain_disagrees"

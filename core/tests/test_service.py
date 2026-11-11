"""Optimistic verification end to end (phase 1, step 1.3).

These tests run the real automated verification engine on the committed
SIMULATED datasets, the lifecycle, the reviewer selection and the points
ledger together.
"""

import json
from datetime import timedelta

import pytest
from helpers import catalog_bytes, packaged, policy_bytes, request_bytes

from orbit_watch import lifecycle as lc
from orbit_watch.canonical import sha256_bytes
from orbit_watch.formats import owjson
from orbit_watch.lifecycle import Status
from orbit_watch.reviewers import Reviewer, ReviewerError, ReviewerRegistry
from orbit_watch.service import RequestService, ServiceError, VerificationContext
from orbit_watch.settlement.ledger import LedgerAdapter
from orbit_watch.sim.simulator import load_profile, simulate
from orbit_watch.timeutil import parse_utc

REQUESTER = "requester:sim-cubesat-team"
STATION = "station:SIM-ESPOO"
PLATFORM = "platform:orbit-watch"
SPLIT = lc.RewardSplit(observer=100, reviewer=10, platform_fee=5)  # deposit 135
T0 = parse_utc("2026-11-01T12:00:00Z")
DELIVERY = parse_utc("2026-11-02T04:00:00Z")
REQUEST_ID = "SIM-REQ-0001"


def h(hours: float):
    return DELIVERY + timedelta(hours=hours)


@pytest.fixture
def datasets(examples_dir):
    base = examples_dir / "simulated" / "datasets"
    return {
        name: (base / name / "observations.json").read_bytes()
        for name in ("acceptable", "wrong_target")
    }


def make_service(registry=None, budget=1000):
    ledger = LedgerAdapter()
    if budget:
        ledger.grant(REQUESTER, budget, key="budget")
    registry = registry or ReviewerRegistry.parse(packaged("reviewers.json"))
    context = VerificationContext(catalog=catalog_bytes(), policy=policy_bytes())
    return RequestService(ledger, registry, context), ledger


def funded_and_reserved(service, request=None):
    record = service.create(request or request_bytes(), REQUESTER, T0)
    rid = record.request_id
    service.open(rid, REQUESTER, T0 + timedelta(minutes=1))
    service.fund(rid, REQUESTER, SPLIT, T0 + timedelta(minutes=2))
    service.reserve(rid, STATION, T0 + timedelta(minutes=5))
    return rid


def net(ledger, party, start=0):
    return ledger.balance(party) - start


def test_unchallenged_pass_becomes_final_and_is_paid(datasets):
    service, ledger = make_service()
    rid = funded_and_reserved(service)
    record = service.deliver(rid, STATION, datasets["acceptable"], DELIVERY)
    assert record.status is Status.CHALLENGE_PERIOD and record.automated_verdict == "pass"
    assert service.tick(h(23.9)) == []  # still within the challenge period
    assert service.tick(h(24)) == [rid]
    record = service.records[rid]
    assert record.status is Status.SETTLED and record.outcome is Status.ACCEPTED
    assert ledger.balance(STATION) == 100 and ledger.balance(PLATFORM) == 5
    assert ledger.balance(REQUESTER) == 1000 - 105
    assert ledger.escrow(rid) == 0
    kinds = [a["kind"] for a in ledger.attestations]
    assert kinds == ["automated_verification"]


def test_failed_delivery_challenged_by_the_observer_and_rejected(datasets):
    service, ledger = make_service()
    rid = funded_and_reserved(service)
    record = service.deliver(rid, STATION, datasets["wrong_target"], DELIVERY)
    assert record.automated_verdict == "fail"
    record = service.challenge(rid, STATION, "I am sure this was SIM-CUBESAT-A", h(1))
    assert record.status is Status.IN_REVIEW and record.challenger == STATION
    first, second, _third = record.reviewers
    service.vote(rid, first, False, "Positions trail the reference orbit by 7.9 s", h(2))
    record = service.vote(rid, second, False, "Same object as SIM-CUBESAT-B", h(3))
    assert record.status is Status.SETTLED and record.outcome is Status.REJECTED
    assert ledger.balance(first) == 10 and ledger.balance(second) == 10
    assert ledger.balance(STATION) == 0
    assert ledger.balance(REQUESTER) == 1000 - 20
    assert record.challenge_reason == "I am sure this was SIM-CUBESAT-A"
    assert [r for r, _ in record.vote_reasons] == [first, second]


def test_pass_challenged_by_the_requester_and_accepted_two_to_one(datasets):
    service, ledger = make_service()
    rid = funded_and_reserved(service)
    service.deliver(rid, STATION, datasets["acceptable"], DELIVERY)
    record = service.challenge(rid, REQUESTER, "Please check the timing", h(1))
    r1, r2, r3 = record.reviewers
    service.vote(rid, r1, True, "Residuals within limits", h(2))
    service.vote(rid, r2, False, "Timing looks suspicious", h(3))
    record = service.vote(rid, r3, True, "Timing is fine at 0.01 s", h(4))
    assert record.outcome is Status.ACCEPTED and record.status is Status.SETTLED
    assert [ledger.balance(r) for r in (r1, r2, r3)] == [10, 10, 10]
    assert ledger.balance(STATION) == 100 and ledger.balance(PLATFORM) == 5
    assert ledger.balance(REQUESTER) == 1000 - 135


def test_no_majority_is_a_dispute_settled_by_the_dispute_rule(datasets):
    service, ledger = make_service()
    rid = funded_and_reserved(service)
    service.deliver(rid, STATION, datasets["acceptable"], DELIVERY)
    record = service.challenge(rid, REQUESTER, "Second opinion, please", h(1))
    service.vote(rid, record.reviewers[0], True, "Looks right", h(2))
    assert service.tick(h(1 + 48)) == [rid]
    record = service.records[rid]
    assert record.outcome is Status.DISPUTED and record.status is Status.SETTLED
    # Completed review paid, observer nothing, the rest refunded; nothing locked.
    assert ledger.balance(record.reviewers[0]) == 10
    assert ledger.balance(STATION) == 0
    assert ledger.balance(REQUESTER) == 1000 - 10
    assert ledger.escrow(rid) == 0


def test_inconclusive_result_goes_straight_to_independent_reviewers():
    service, ledger = make_service()
    start, end = "2026-11-11T15:00:00Z", "2026-11-12T03:00:00Z"
    request = request_bytes(start=start, end=end)
    observed = simulate(
        service_catalog(),
        339001,
        load_profile("sim-cmos-gps"),
        parse_utc(start),
        parse_utc(end),
        seed=7,
        max_passes=2,
    )
    data = owjson.write_observation_set(observed).encode()
    record = service.create(request, REQUESTER, parse_utc("2026-11-11T12:00:00Z"))
    rid = record.request_id
    service.open(rid, REQUESTER, parse_utc("2026-11-11T12:01:00Z"))
    service.fund(rid, REQUESTER, SPLIT, parse_utc("2026-11-11T12:02:00Z"))
    service.reserve(rid, STATION, parse_utc("2026-11-11T12:03:00Z"))
    record = service.deliver(rid, STATION, data, parse_utc("2026-11-12T04:00:00Z"))
    assert record.automated_verdict == "inconclusive" and record.status is Status.IN_REVIEW
    assert record.challenger is None and len(record.reviewers) == 3
    for index, reviewer in enumerate(record.reviewers[:2]):
        record = service.vote(
            rid,
            reviewer,
            True,
            "Orbit is old but the track matches",
            parse_utc(f"2026-11-12T0{5 + index}:00:00Z"),
        )
    assert record.outcome is Status.ACCEPTED
    assert ledger.balance(STATION) == 100


def service_catalog():
    from orbit_watch.catalog import parse_catalog

    return parse_catalog(catalog_bytes())


# ------------------------------------------------------------------ reviewers


def test_reviewer_selection_is_fixed_independent_and_spread():
    registry = ReviewerRegistry.parse(packaged("reviewers.json"))
    parties = {REQUESTER, STATION}
    first = registry.select(REQUEST_ID, "a" * 64, parties)
    assert first == registry.select(REQUEST_ID, "a" * 64, parties)
    # Bertil is affiliated with the station and Dana with the requester.
    assert "reviewer:sim-bertil" not in first and "reviewer:sim-dana" not in first
    assert not set(first) & parties
    chosen = {r for n in range(40) for r in registry.select(REQUEST_ID, f"{n:064x}", parties)}
    assert chosen == {
        "reviewer:sim-aino",
        "reviewer:sim-chen",
        "reviewer:sim-eero",
        "reviewer:sim-fatima",
    }


def test_not_enough_independent_reviewers(datasets):
    small = ReviewerRegistry(
        [
            Reviewer("reviewer:x"),
            Reviewer("reviewer:y"),
            Reviewer("reviewer:z", affiliations=frozenset({STATION})),
        ]
    )
    with pytest.raises(ReviewerError) as error:
        small.select(REQUEST_ID, "a" * 64, {REQUESTER, STATION})
    assert error.value.code == "not_enough_reviewers"
    service, _ = make_service(registry=small)
    rid = funded_and_reserved(service)
    service.deliver(rid, STATION, datasets["acceptable"], DELIVERY)
    with pytest.raises(ServiceError) as error:
        service.challenge(rid, REQUESTER, "Check it", h(1))
    assert error.value.code == "not_enough_reviewers"
    assert service.records[rid].status is Status.CHALLENGE_PERIOD


def test_registry_rejects_duplicates():
    with pytest.raises(ReviewerError):
        ReviewerRegistry([Reviewer("reviewer:x"), Reviewer("reviewer:x")])


# ------------------------------------------------------------------ refusals


def test_refusals_have_stable_codes(datasets):
    service, _ = make_service()
    rid = funded_and_reserved(service)
    service.deliver(rid, STATION, datasets["acceptable"], DELIVERY)
    cases = [
        (lambda: service.challenge(rid, REQUESTER, "  ", h(1)), "reason_required"),
        (lambda: service.challenge(rid, "station:SIM-OTHER", "why", h(1)), "not_a_party"),
        (lambda: service.open(rid, STATION, h(1)), "not_requester"),
        (lambda: service.report("SIM-NOPE"), "no_report"),
        (lambda: service.reserve("SIM-NOPE", STATION, h(1)), "unknown_request"),
    ]
    for call, code in cases:
        with pytest.raises(ServiceError) as error:
            call()
        assert error.value.code == code
    record = service.challenge(rid, REQUESTER, "Check it", h(1))
    with pytest.raises(ServiceError) as error:
        service.vote(rid, "reviewer:sim-dana", True, "ok", h(2))
    assert error.value.code == "not_assigned"
    with pytest.raises(ServiceError) as error:
        service.vote(rid, record.reviewers[0], True, "", h(2))
    assert error.value.code == "reason_required"


def test_challenge_after_the_deadline_is_refused_and_the_result_stands(datasets):
    service, ledger = make_service()
    rid = funded_and_reserved(service)
    service.deliver(rid, STATION, datasets["acceptable"], DELIVERY)
    with pytest.raises(ServiceError) as error:
        service.challenge(rid, REQUESTER, "Too late?", h(25))
    assert error.value.code == "forbidden_in_status"
    # A refused call changes nothing; the clock settles the request.
    assert service.records[rid].status is Status.CHALLENGE_PERIOD
    service.tick(h(25))
    assert service.records[rid].status is Status.SETTLED
    assert ledger.balance(STATION) == 100


def test_funding_without_points_leaves_the_request_unchanged():
    service, ledger = make_service(budget=0)
    record = service.create(request_bytes(), REQUESTER, T0)
    service.open(record.request_id, REQUESTER, T0 + timedelta(minutes=1))
    with pytest.raises(ServiceError) as error:
        service.fund(record.request_id, REQUESTER, SPLIT, T0 + timedelta(minutes=2))
    assert error.value.code == "insufficient_points"
    assert service.records[record.request_id].status is Status.OPEN
    assert ledger.escrow(record.request_id) == 0


def test_expired_request_is_refunded_by_the_clock():
    service, ledger = make_service()
    rid = funded_and_reserved(service)
    assert ledger.balance(REQUESTER) == 1000 - 135
    service.tick(parse_utc("2026-11-03T03:00:00Z"))
    record = service.records[rid]
    assert record.outcome is Status.EXPIRED and record.status is Status.SETTLED
    assert ledger.balance(REQUESTER) == 1000


def test_the_same_file_delivered_to_another_request_fails_as_a_duplicate(datasets):
    service, _ = make_service()
    first = funded_and_reserved(service)
    service.deliver(first, STATION, datasets["acceptable"], DELIVERY)
    second_request = request_bytes(request_id="SIM-REQ-0002")
    second = funded_and_reserved(service, second_request)
    record = service.deliver(second, STATION, datasets["acceptable"], DELIVERY)
    assert record.automated_verdict == "fail"
    report = json.loads(service.report(second))
    failed = [c["id"] for c in report["checks"] if c["result"] == "fail"]
    assert failed == ["duplicates"]


def test_reports_and_summaries(datasets):
    service, _ = make_service()
    rid = funded_and_reserved(service)
    service.deliver(rid, STATION, datasets["acceptable"], DELIVERY)
    report = service.report(rid)
    assert sha256_bytes(report) == service.records[rid].report_sha256
    assert sha256_bytes(datasets["acceptable"]) in service.files
    service.tick(h(24))
    summary = service.summary(rid)
    assert summary["status"] == "settled" and summary["outcome"] == "accepted"
    assert summary["settlement"]["plan"]["deposit"] == 135

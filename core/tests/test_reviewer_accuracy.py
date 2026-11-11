"""Reviewer accuracy with known-answer calibration tasks (phase 1, step 1.4)."""

import json
from datetime import timedelta
from pathlib import Path

import pytest
from helpers import request_bytes
from test_service import (
    DELIVERY,
    REQUESTER,
    SPLIT,
    STATION,
    T0,
    funded_and_reserved,
    make_service,
)

from orbit_watch import calibration as cal
from orbit_watch.lifecycle import Status
from orbit_watch.service import ServiceError

ELIGIBLE = ("reviewer:sim-aino", "reviewer:sim-chen", "reviewer:sim-eero", "reviewer:sim-fatima")


def h(hours):
    return DELIVERY + timedelta(hours=hours)


@pytest.mark.parametrize(
    ("kind", "verdict"), [("correct_target", "pass"), ("wrong_target", "fail")]
)
def test_calibration_files_have_the_intended_automated_result(kind, verdict):
    request, observations, report, result = cal.build_files(kind, f"test|{kind}")
    assert result == verdict
    assert json.loads(report)["verdict"] == verdict
    assert json.loads(observations)["simulated"] is True
    again = cal.build_files(kind, f"test|{kind}")
    assert again == (request, observations, report, result)  # deterministic
    other = cal.build_files(kind, f"test|{kind}|2")
    assert json.loads(other[0])["request_id"] != json.loads(request)["request_id"]


def test_kinds_are_balanced_per_reviewer():
    history = []
    for n in range(10):
        kind = cal.choose_kind("r", history, f"s{n}")
        history.append(
            cal.CalibrationTask(f"t{n}", "r", kind, cal.KINDS[kind], "", "", "", "", "", T0, T0)
        )
    approve = sum(1 for t in history if t.expected == "approve")
    assert approve == 5


def challenged(service, request_id="SIM-REQ-0001"):
    rid = funded_and_reserved(service, request_bytes(request_id=request_id))
    service.deliver(rid, STATION, ACCEPTABLE, DELIVERY)
    service.challenge(rid, REQUESTER, "Second opinion, please", h(1))
    return rid


ACCEPTABLE = (
    Path(__file__).resolve().parents[2] / "examples/simulated/datasets/acceptable/observations.json"
).read_bytes()


def test_real_and_calibration_tasks_look_the_same():
    service, _ = make_service()
    rid = challenged(service)
    record = service.records[rid]
    for reviewer in record.reviewers:
        tasks = service.assignments(reviewer, h(2))
        assert len(tasks) == 2  # one real, one calibration
        assert {tuple(sorted(t)) for t in tasks} == {tuple(sorted(tasks[0]))}
        assert tasks == sorted(tasks, key=lambda t: t["task_id"])
        for task in tasks:
            assert task["task_id"].startswith("task-") and rid not in task["task_id"]
            for key in ("request_sha256", "observations_sha256", "report_sha256"):
                assert task[key] in service.files
    assert not service.assignments("reviewer:sim-dana", h(2))  # not in the round


def test_answering_routes_real_votes_and_keeps_calibration_out_of_the_books():
    service, ledger = make_service()
    rid = challenged(service)
    reviewer = service.records[rid].reviewers[0]
    real_id = next(k for k, v in service.real_tasks.items() if v == (rid, reviewer))
    calibration_id = next(
        t.task_id for t in service.calibration_tasks.values() if t.reviewer == reviewer
    )
    balances = ledger.account_balances()
    assert service.review(calibration_id, reviewer, True, "Track matches", h(2)) == {
        "task_id": calibration_id,
        "recorded": True,
    }
    assert ledger.account_balances() == balances  # calibration moves no points
    assert service.records[rid].votes == ()
    service.review(real_id, reviewer, True, "Residuals are fine", h(3))
    assert service.records[rid].votes == ((reviewer, True),)
    assert service.assignments(reviewer, h(4)) == []


def test_review_refusals():
    service, _ = make_service()
    rid = challenged(service)
    first, second, _ = service.records[rid].reviewers
    task = next(t for t in service.calibration_tasks.values() if t.reviewer == first)
    cases = [
        (lambda: service.review(task.task_id, second, True, "ok", h(2)), "not_your_task"),
        (lambda: service.review(task.task_id, first, True, " ", h(2)), "reason_required"),
        (lambda: service.review("task-nope", first, True, "ok", h(2)), "unknown_task"),
        (lambda: service.review(task.task_id, first, True, "ok", h(100)), "forbidden_in_status"),
    ]
    for call, code in cases:
        with pytest.raises(ServiceError) as error:
            call()
        assert error.value.code == code
    service.review(task.task_id, first, False, "Wrong object", h(2))
    with pytest.raises(ServiceError) as error:
        service.review(task.task_id, first, False, "Again", h(3))
    assert error.value.code == "already_voted"


def answer_everything(service, policies, now):
    for reviewer, policy in policies.items():
        for task in service.assignments(reviewer, now):
            approve = policy(service, task)
            try:
                service.review(task["task_id"], reviewer, approve, "Reviewed the residuals", now)
            except ServiceError as error:
                assert error.code == "forbidden_in_status"  # the round was already decided


def careful(service, task):
    calibration = service.calibration_tasks.get(task["task_id"])
    if calibration is not None:
        return calibration.expected == "approve"
    return task["automated_verdict"] == "pass"


def test_a_rubber_stamper_shows_low_accuracy_and_a_careful_reviewer_does_not():
    service, _ = make_service()
    policies = {
        "reviewer:sim-aino": lambda service, task: True,  # approves everything
        "reviewer:sim-chen": careful,
        "reviewer:sim-eero": careful,
        "reviewer:sim-fatima": careful,
    }
    for n in range(10):
        challenged(service, request_id=f"SIM-REQ-{n:04d}")
        answer_everything(service, policies, h(2 + n))
    now = h(100)
    rubber = service.reviewer_profile("reviewer:sim-aino", now)
    good = service.reviewer_profile("reviewer:sim-chen", now)
    assert rubber["calibration"]["answered"] >= cal.MIN_ANSWERED_FOR_FLAG
    assert rubber["calibration"]["accuracy"] == pytest.approx(0.5, abs=0.1)
    assert "low_accuracy" in rubber["flags"]
    assert rubber["votes"]["approval_rate"] == 1.0
    assert "approves_almost_everything" in rubber["flags"]
    assert good["calibration"]["accuracy"] == 1.0
    assert good["flags"] == []
    # Every round was decided and settled; reviewers who voted were paid.
    assert all(r.status is Status.SETTLED for r in service.records.values())


def test_missed_tasks_are_shown():
    service, _ = make_service()
    rid = challenged(service)
    reviewer = service.records[rid].reviewers[0]
    profile = service.reviewer_profile(reviewer, h(1 + 49))
    assert profile["calibration"]["missed"] == 1 and "missed_tasks" in profile["flags"]
    assert profile["calibration"]["accuracy"] is None


def test_profiles_are_deterministic():
    profiles = []
    for _ in range(2):
        service, _ = make_service()
        rid = challenged(service)
        for reviewer in service.records[rid].reviewers:
            answer_everything(service, {reviewer: careful}, h(2))
        profiles.append([service.reviewer_profile(r, h(60)) for r in ELIGIBLE])
        ids = sorted(service.calibration_tasks)
        profiles.append(ids)
    assert profiles[0] == profiles[2] and profiles[1] == profiles[3]


def test_inconclusive_rounds_also_get_calibration_tasks():
    from test_service import service_catalog

    from orbit_watch.formats import owjson
    from orbit_watch.sim.simulator import load_profile, simulate
    from orbit_watch.timeutil import parse_utc

    service, _ = make_service()
    start, end = "2026-11-11T15:00:00Z", "2026-11-12T03:00:00Z"
    observed = simulate(
        service_catalog(),
        339001,
        load_profile("sim-cmos-gps"),
        parse_utc(start),
        parse_utc(end),
        seed=7,
        max_passes=2,
    )
    record = service.create(
        request_bytes(start=start, end=end), REQUESTER, parse_utc("2026-11-11T12:00:00Z")
    )
    rid = record.request_id
    service.open(rid, REQUESTER, parse_utc("2026-11-11T12:01:00Z"))
    service.fund(rid, REQUESTER, SPLIT, parse_utc("2026-11-11T12:02:00Z"))
    service.reserve(rid, STATION, parse_utc("2026-11-11T12:03:00Z"))
    record = service.deliver(
        rid,
        STATION,
        owjson.write_observation_set(observed).encode(),
        parse_utc("2026-11-12T04:00:00Z"),
    )
    assert record.status is Status.IN_REVIEW
    reviewer = record.reviewers[0]
    tasks = service.assignments(reviewer, parse_utc("2026-11-12T05:00:00Z"))
    assert len(tasks) == 2
    assert any(t["challenge_reason"] == "The automated result was inconclusive." for t in tasks)

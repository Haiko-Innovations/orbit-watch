"""Reviewer accuracy with known-answer tasks (phase 1, step 1.4).

Each time a reviewer is assigned to a real reviewer round, the service also
gives them calibration tasks: SIMULATED deliveries whose correct answer is
known. Reviewers see real and calibration tasks in one queue, in the same
shape, and cannot tell them apart. Their answers to calibration tasks measure
their accuracy, which is shown on their profile. A reviewer who approves
everything shows low accuracy.

Calibration kinds (correct answer in brackets):

* ``correct_target`` (approve): the station observed the requested object;
  the automated check passed and the requester asks for a second look;
* ``wrong_target`` (reject): the positions belong to the neighbouring object
  in the same orbit; the automated check failed and the observer disputes it.

Kinds are balanced per reviewer, so guessing one answer always scores about
50 %. In phase 1 every delivery is simulated, so calibration tasks look like
real ones. With real data, calibration has to use archived real deliveries
with settled answers; see docs/reviewer-accuracy.md.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import datetime, timedelta
from importlib import resources
from typing import Any

from orbit_watch.canonical import dumps_pretty, sha256_bytes
from orbit_watch.catalog import parse_catalog
from orbit_watch.formats import owjson
from orbit_watch.sim.scenarios import REQUEST, TARGET
from orbit_watch.sim.simulator import load_profile, simulate
from orbit_watch.timeutil import format_utc, parse_utc
from orbit_watch.verify.engine import VerificationInput, verify

CALIBRATION_VERSION = "1.0"
KINDS = {"correct_target": "approve", "wrong_target": "reject"}
NEIGHBOUR = 339002  # SIM-CUBESAT-B, about 8 s behind SIM-CUBESAT-A
PROFILES = ("sim-cmos-gps", "sim-azel-mount")
CHALLENGES = {
    "correct_target": (
        "Please confirm that this track is our satellite.",
        "We expected a slightly different position; please check.",
        "Second opinion requested before we update our orbit.",
    ),
    "wrong_target": (
        "I am sure this was the requested object.",
        "The automated check used old elements; the track is right.",
        "My timing is GPS-disciplined; please review the residuals.",
    ),
}
# Profiles need at least this many answered tasks before they show flags.
MIN_ANSWERED_FOR_FLAG = 5
LOW_ACCURACY = 0.8
RUBBER_STAMP_APPROVAL_RATE = 0.95
MIN_VOTES_FOR_RUBBER_STAMP = 10


def _number(text: str) -> int:
    return int(hashlib.sha256(text.encode("utf-8")).hexdigest()[:12], 16)


@dataclass
class CalibrationTask:
    task_id: str
    reviewer: str
    kind: str
    expected: str  # "approve" or "reject"
    request_sha256: str
    observations_sha256: str
    report_sha256: str
    automated_verdict: str
    challenge_reason: str
    created_at: datetime
    due_at: datetime
    answer: str | None = None
    reason: str | None = None
    answered_at: datetime | None = None

    @property
    def correct(self) -> bool | None:
        return None if self.answer is None else self.answer == self.expected


def choose_kind(reviewer: str, history: list[CalibrationTask], source: str) -> str:
    """Balance the kinds per reviewer; break ties by a hash of the source."""
    approve = sum(1 for t in history if t.expected == "approve")
    reject = len(history) - approve
    if approve != reject:
        return "wrong_target" if approve > reject else "correct_target"
    return sorted(KINDS)[_number(f"{reviewer}|{source}|kind") % len(KINDS)]


def build_files(kind: str, source: str) -> tuple[bytes, bytes, bytes, str]:
    """Request, observations and automated report for one calibration task.

    ``source`` (for example the real request id, the reviewer and a counter)
    seeds everything, so the same source always gives the same files.
    """
    seed = _number(f"calibration/{CALIBRATION_VERSION}|{source}")
    request = dict(REQUEST)
    request["request_id"] = f"SIM-REQ-{seed % 10**8:08d}"
    request_bytes = dumps_pretty(request, sort_keys=False).encode("utf-8")
    catalog_bytes = resources.files("orbit_watch.data").joinpath("catalog.json").read_bytes()
    policy_bytes = resources.files("orbit_watch.data").joinpath("target-policy.json").read_bytes()
    catalog = parse_catalog(catalog_bytes)
    profile = load_profile(PROFILES[seed % len(PROFILES)])
    observed = TARGET if kind == "correct_target" else NEIGHBOUR
    observation_set = simulate(
        catalog,
        TARGET,
        profile,
        parse_utc(REQUEST["window"]["start"]),
        parse_utc(REQUEST["window"]["end"]),
        seed=seed % 2**31,
        observed_id=observed,
        max_passes=1 + seed % 2,
    )
    observations = owjson.write_observation_set(observation_set).encode("utf-8")
    report = verify(
        VerificationInput(
            request=request_bytes,
            observations=observations,
            observations_format="json",
            catalog=catalog_bytes,
            policy=policy_bytes,
            declared_sha256=sha256_bytes(observations),
        )
    )
    report_bytes = dumps_pretty(report, sort_keys=False).encode("utf-8")
    return request_bytes, observations, report_bytes, report["verdict"]


def challenge_text(kind: str, source: str) -> str:
    options = CHALLENGES[kind]
    return options[_number(f"{source}|reason") % len(options)]


def profile(
    reviewer: str, tasks: list[CalibrationTask], votes: list[tuple[bool, str | None]], now: datetime
) -> dict[str, Any]:
    """Accuracy profile of one reviewer.

    ``votes`` are the reviewer's real votes as (approved, decided outcome or None).
    """
    own = [t for t in tasks if t.reviewer == reviewer]
    answered = [t for t in own if t.answer is not None]
    correct = sum(1 for t in answered if t.correct)
    missed = sum(1 for t in own if t.answer is None and t.due_at <= now)
    approvals = sum(1 for t in answered if t.answer == "approve") + sum(1 for a, _ in votes if a)
    total_votes = len(answered) + len(votes)
    decided = [(a, outcome) for a, outcome in votes if outcome in ("accepted", "rejected")]
    agreed = sum(1 for a, outcome in decided if a == (outcome == "accepted"))
    accuracy = correct / len(answered) if answered else None
    approval_rate = approvals / total_votes if total_votes else None
    flags = []
    if accuracy is not None and len(answered) >= MIN_ANSWERED_FOR_FLAG and accuracy < LOW_ACCURACY:
        flags.append("low_accuracy")
    if (
        approval_rate is not None
        and total_votes >= MIN_VOTES_FOR_RUBBER_STAMP
        and approval_rate >= RUBBER_STAMP_APPROVAL_RATE
    ):
        flags.append("approves_almost_everything")
    if missed:
        flags.append("missed_tasks")
    return {
        "reviewer": reviewer,
        "as_of": format_utc(now),
        "calibration_version": CALIBRATION_VERSION,
        "calibration": {
            "answered": len(answered),
            "correct": correct,
            "accuracy": None if accuracy is None else round(accuracy, 4),
            "missed": missed,
            "open": sum(1 for t in own if t.answer is None and t.due_at > now),
        },
        "votes": {
            "total": total_votes,
            "approvals": approvals,
            "approval_rate": None if approval_rate is None else round(approval_rate, 4),
            "real_rounds": len(votes),
            "agreed_with_outcome": agreed,
            "decided_rounds": len(decided),
        },
        "flags": flags,
    }


def due(now: datetime, hours: float) -> datetime:
    return now + timedelta(hours=hours)

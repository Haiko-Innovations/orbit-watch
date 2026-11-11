"""Optimistic verification: the request service (phase 1, step 1.3).

The service ties the parts together the way the phase 1 API will use them:

1. a station delivers an observation file; the service keeps it by its SHA-256
   and runs the automated verification engine at once;
2. the result is published and attested; ``pass`` and ``fail`` start the
   challenge period, ``inconclusive`` goes straight to reviewers;
3. if nobody challenges before the deadline, the automated result is final;
4. a challenge by the requester or the observer starts a reviewer round: three
   pre-approved, independent reviewers chosen by ``ReviewerRegistry.select``;
   two equal votes decide, and every vote carries a reason;
5. no majority by the review deadline is a dispute;
6. every outcome is settled at once through the settlement adapter, by the
   shared settlement rules.

The service holds everything in memory and takes the time from its callers
(an injected clock, decision P-05), so it is deterministic and easy to test.
Storage comes in step 1.5 and the HTTP API in step 1.6.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from orbit_watch import calibration as cal
from orbit_watch import lifecycle as lc
from orbit_watch.canonical import dumps_pretty, sha256_bytes
from orbit_watch.formats import Sites
from orbit_watch.lifecycle import RequestRecord, Status, TransitionError
from orbit_watch.reviewers import ReviewerError, ReviewerRegistry
from orbit_watch.settlement import SettlementAdapter, SettlementError, settlement_plan
from orbit_watch.timeutil import format_utc
from orbit_watch.verify.engine import UsageError, VerificationInput, verify

VERIFIER = "system:verifier"
PLATFORM = "platform:orbit-watch"


class ServiceError(ValueError):
    """A refused call. ``code`` is stable and maps to an API error later."""

    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


@dataclass
class VerificationContext:
    """What automated verification compares deliveries with."""

    catalog: bytes
    policy: bytes
    sites: Sites | None = None


@dataclass
class Delivered:
    """What the service keeps about one delivery."""

    request_id: str
    station: str
    observations_sha256: str
    observations_format: str | None
    report_sha256: str
    verdict: str


@dataclass
class RequestService:
    adapter: SettlementAdapter
    reviewers: ReviewerRegistry
    context: VerificationContext
    platform: str = PLATFORM
    records: dict[str, RequestRecord] = field(default_factory=dict)
    request_documents: dict[str, bytes] = field(default_factory=dict)
    files: dict[str, bytes] = field(default_factory=dict)  # content-addressed by SHA-256
    deliveries: dict[str, Delivered] = field(default_factory=dict)  # by request id
    settlements: dict[str, dict[str, Any]] = field(default_factory=dict)  # by request id
    # Reviewer tasks (step 1.4). Task ids are opaque, so real tasks and known-answer
    # calibration tasks cannot be told apart.
    calibration_per_assignment: int = 1
    task_salt: str = "orbit-watch-tasks"
    real_tasks: dict[str, tuple[str, str]] = field(default_factory=dict)  # id -> request, reviewer
    calibration_tasks: dict[str, cal.CalibrationTask] = field(default_factory=dict)

    # ------------------------------------------------------------------ helpers

    def _record(self, request_id: str) -> RequestRecord:
        try:
            return self.records[request_id]
        except KeyError:
            raise ServiceError("unknown_request", f"no request {request_id!r}") from None

    def _apply(self, request_id: str, event: lc.Event) -> RequestRecord:
        try:
            record = lc.apply(self._record(request_id), event)
        except TransitionError as error:
            raise ServiceError(error.code, str(error)) from None
        self.records[request_id] = record
        return self._settle_if_finished(request_id, event.at)

    def _store(self, data: bytes) -> str:
        digest = sha256_bytes(data)
        self.files.setdefault(digest, data)
        return digest

    def _settle_if_finished(self, request_id: str, now: datetime) -> RequestRecord:
        record = self.records[request_id]
        if record.status not in lc.OUTCOMES:
            return record
        plan = settlement_plan(record, platform=self.platform)
        key = f"{request_id}/settle"
        try:
            if record.status in (Status.EXPIRED, Status.CANCELLED) and plan.deposit:
                receipt = self.adapter.refund(request_id, record.requester, key=key)
            else:
                receipt = self.adapter.settle(plan, key=key)
        except SettlementError as error:  # pragma: no cover - the rules keep these consistent
            raise ServiceError(error.code, str(error)) from None
        self.settlements[request_id] = {"plan": plan.to_document(), "reference": receipt.reference}
        record = lc.apply(record, lc.Settle(max(now, record.updated_at)))
        self.records[request_id] = record
        return record

    # ------------------------------------------------------------------ requester

    def create(
        self, request_bytes: bytes, requester: str, now: datetime, **terms: Any
    ) -> RequestRecord:
        try:
            parsed_terms = lc.terms_from_request(request_bytes, requester, **terms)
        except ValueError as error:
            raise ServiceError("invalid_request", str(error)) from None
        request_id = parsed_terms.request_id
        if request_id in self.records:
            raise ServiceError("duplicate_request", f"request {request_id} already exists")
        self.request_documents[request_id] = request_bytes
        self._store(request_bytes)
        self.records[request_id] = lc.create(parsed_terms, now)
        return self.records[request_id]

    def _require_requester(self, request_id: str, party: str) -> None:
        if party != self._record(request_id).requester:
            raise ServiceError("not_requester", "only the requester can do this")

    def open(self, request_id: str, party: str, now: datetime) -> RequestRecord:
        self._require_requester(request_id, party)
        return self._apply(request_id, lc.Open(now))

    def fund(
        self, request_id: str, party: str, split: lc.RewardSplit, now: datetime
    ) -> RequestRecord:
        self._require_requester(request_id, party)
        before = self._record(request_id)
        record = self._apply(request_id, lc.Fund(now, split))
        try:
            self.adapter.fund(request_id, party, split.total, key=f"{request_id}/fund")
        except SettlementError as error:
            self.records[request_id] = before  # keep the lifecycle and the books in step
            raise ServiceError(error.code, str(error)) from None
        return record

    def cancel(self, request_id: str, party: str, now: datetime) -> RequestRecord:
        return self._apply(request_id, lc.Cancel(now, party))

    # ------------------------------------------------------------------ station

    def reserve(self, request_id: str, station: str, now: datetime) -> RequestRecord:
        record = self._apply(request_id, lc.Reserve(now, station))
        count = sum(1 for h in record.history if h.event == "reserve")
        self.adapter.reserve(request_id, station, key=f"{request_id}/reserve/{count}")
        return record

    def deliver(
        self,
        request_id: str,
        station: str,
        observations: bytes,
        now: datetime,
        observations_format: str | None = None,
    ) -> RequestRecord:
        """Accept a delivery and run automated verification at once."""
        observations_sha256 = sha256_bytes(observations)
        self._apply(request_id, lc.Deliver(now, station, observations_sha256))
        self._store(observations)
        previous = sorted(
            (self.files[d.observations_sha256] for d in self.deliveries.values()),
            key=sha256_bytes,
        )
        try:
            report = verify(
                VerificationInput(
                    request=self.request_documents[request_id],
                    observations=observations,
                    observations_format=observations_format,
                    catalog=self.context.catalog,
                    policy=self.context.policy,
                    previous=previous,
                    declared_sha256=observations_sha256,
                    sites=self.context.sites,
                )
            )
        except UsageError as error:  # a configuration problem, not the station's fault
            raise ServiceError("verification_unavailable", str(error)) from None
        report_bytes = dumps_pretty(report, sort_keys=False).encode("utf-8")
        report_sha256 = self._store(report_bytes)
        verdict = report["verdict"]
        self.deliveries[request_id] = Delivered(
            request_id, station, observations_sha256, observations_format, report_sha256, verdict
        )
        self.adapter.attest(
            request_id,
            VERIFIER,
            "automated_verification",
            report_sha256,
            verdict,
            key=f"{request_id}/verification",
        )
        reviewers: tuple[str, ...] = ()
        if verdict == "inconclusive":
            reviewers = self._select(request_id, observations_sha256, challenger=None)
        record = self._apply(
            request_id, lc.RecordVerification(now, verdict, report_sha256, reviewers)
        )
        if record.status is Status.IN_REVIEW:
            self._assign(request_id, now)
        return record

    # ------------------------------------------------------------------ challenges

    def _select(
        self, request_id: str, delivery_sha256: str, challenger: str | None
    ) -> tuple[str, ...]:
        record = self._record(request_id)
        parties = {record.requester, record.observer or "", challenger or ""}
        try:
            return self.reviewers.select(request_id, delivery_sha256, parties)
        except ReviewerError as error:
            raise ServiceError(error.code, str(error)) from None

    def challenge(self, request_id: str, party: str, reason: str, now: datetime) -> RequestRecord:
        if not reason.strip():
            raise ServiceError("reason_required", "a challenge must say why")
        record = lc.advance(self._record(request_id), now)
        self.records[request_id] = record
        if record.status is not Status.CHALLENGE_PERIOD:
            self._settle_if_finished(request_id, now)
            raise ServiceError(
                "forbidden_in_status",
                f"'challenge' is not allowed when the request is {self.records[request_id].status}",
            )
        reviewers = self._select(request_id, record.delivery_sha256 or "", challenger=party)
        record = self._apply(request_id, lc.Challenge(now, party, reviewers, reason))
        self._assign(request_id, now)
        return record

    def vote(
        self, request_id: str, reviewer: str, approve: bool, reason: str, now: datetime
    ) -> RequestRecord:
        if not reason.strip():
            raise ServiceError("reason_required", "a review must give its reasons")
        record = self._apply(request_id, lc.Vote(now, reviewer, approve, reason))
        delivered = self.deliveries[request_id]
        self.adapter.attest(
            request_id,
            reviewer,
            "review_vote",
            delivered.observations_sha256,
            "approve" if approve else "reject",
            key=f"{request_id}/vote/{reviewer}",
        )
        return record

    # ------------------------------------------------------------------ reviewer tasks

    def _task_id(self, *parts: str) -> str:
        return "task-" + sha256_bytes("|".join((self.task_salt, *parts)).encode())[:20]

    def _assign(self, request_id: str, now: datetime) -> None:
        """Give each reviewer of the round its real task and its calibration tasks."""
        record = self._record(request_id)
        due = record.review_deadline or now
        for reviewer in record.reviewers:
            self.real_tasks[self._task_id("real", request_id, reviewer)] = (request_id, reviewer)
            for number in range(self.calibration_per_assignment):
                source = f"{request_id}|{reviewer}|{number}"
                history = [t for t in self.calibration_tasks.values() if t.reviewer == reviewer]
                kind = cal.choose_kind(reviewer, history, source)
                request_bytes, observations, report, verdict = cal.build_files(kind, source)
                task = cal.CalibrationTask(
                    task_id=self._task_id("calibration", source),
                    reviewer=reviewer,
                    kind=kind,
                    expected=cal.KINDS[kind],
                    request_sha256=self._store(request_bytes),
                    observations_sha256=self._store(observations),
                    report_sha256=self._store(report),
                    automated_verdict=verdict,
                    challenge_reason=cal.challenge_text(kind, source),
                    created_at=now,
                    due_at=due,
                )
                self.calibration_tasks[task.task_id] = task

    def assignments(self, reviewer: str, now: datetime) -> list[dict[str, Any]]:
        """Open review tasks of a reviewer, real and calibration alike, in one shape."""
        open_tasks = []
        for task_id, (request_id, assigned) in self.real_tasks.items():
            record = lc.advance(self._record(request_id), now)
            voted = any(r == assigned for r, _ in record.votes)
            if assigned != reviewer or record.status is not Status.IN_REVIEW or voted:
                continue
            delivered = self.deliveries[request_id]
            open_tasks.append(
                {
                    "task_id": task_id,
                    "request_sha256": sha256_bytes(self.request_documents[request_id]),
                    "observations_sha256": delivered.observations_sha256,
                    "report_sha256": delivered.report_sha256,
                    "automated_verdict": delivered.verdict,
                    "challenge_reason": record.challenge_reason
                    or "The automated result was inconclusive.",
                    "due": format_utc(record.review_deadline),
                }
            )
        for task in self.calibration_tasks.values():
            if task.reviewer != reviewer or task.answer is not None or task.due_at <= now:
                continue
            open_tasks.append(
                {
                    "task_id": task.task_id,
                    "request_sha256": task.request_sha256,
                    "observations_sha256": task.observations_sha256,
                    "report_sha256": task.report_sha256,
                    "automated_verdict": task.automated_verdict,
                    "challenge_reason": task.challenge_reason,
                    "due": format_utc(task.due_at),
                }
            )
        return sorted(open_tasks, key=lambda t: t["task_id"])

    def review(
        self, task_id: str, reviewer: str, approve: bool, reason: str, now: datetime
    ) -> dict[str, Any]:
        """Answer a review task. The answer never says whether the task was real."""
        if not reason.strip():
            raise ServiceError("reason_required", "a review must give its reasons")
        if task_id in self.real_tasks:
            request_id, assigned = self.real_tasks[task_id]
            if assigned != reviewer:
                raise ServiceError("not_your_task", "this task belongs to another reviewer")
            self.vote(request_id, reviewer, approve, reason, now)
            return {"task_id": task_id, "recorded": True}
        task = self.calibration_tasks.get(task_id)
        if task is None:
            raise ServiceError("unknown_task", f"no task {task_id!r}")
        if task.reviewer != reviewer:
            raise ServiceError("not_your_task", "this task belongs to another reviewer")
        if task.answer is not None:
            raise ServiceError("already_voted", f"{reviewer} has already voted")
        if now >= task.due_at:
            raise ServiceError("forbidden_in_status", "the review deadline has passed")
        task.answer = "approve" if approve else "reject"
        task.reason = reason
        task.answered_at = now
        return {"task_id": task_id, "recorded": True}

    def reviewer_profile(self, reviewer: str, now: datetime) -> dict[str, Any]:
        """Accuracy on calibration tasks and voting behaviour in real rounds."""
        votes = []
        for request_id in sorted(self.records):
            record = self.records[request_id]
            for voter, approve in record.votes:
                if voter == reviewer:
                    outcome = None if record.outcome is None else str(record.outcome)
                    votes.append((approve, outcome))
        return cal.profile(reviewer, list(self.calibration_tasks.values()), votes, now)

    # ------------------------------------------------------------------ time

    def tick(self, now: datetime) -> list[str]:
        """Apply passed deadlines to every request and settle finished ones."""
        changed = []
        for request_id in sorted(self.records):
            before = self.records[request_id]
            if before.status is Status.SETTLED:
                continue
            self.records[request_id] = lc.advance(before, now)
            after = self._settle_if_finished(request_id, now)
            if after != before:
                changed.append(request_id)
        return changed

    # ------------------------------------------------------------------ reading

    def report(self, request_id: str) -> bytes:
        try:
            return self.files[self.deliveries[request_id].report_sha256]
        except KeyError:
            raise ServiceError("no_report", f"request {request_id} has no report yet") from None

    def summary(self, request_id: str) -> dict[str, Any]:
        record = self._record(request_id)
        delivered = self.deliveries.get(request_id)
        return {
            "request_id": request_id,
            "status": str(record.status),
            "outcome": None if record.outcome is None else str(record.outcome),
            "outcome_reason": record.outcome_reason,
            "automated_verdict": None if delivered is None else delivered.verdict,
            "reviewers": list(record.reviewers),
            "votes": [[r, a] for r, a in record.votes],
            "settlement": self.settlements.get(request_id),
        }

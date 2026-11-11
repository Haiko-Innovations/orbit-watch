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

The service takes the time from its callers (an injected clock, decision
P-05), so it is deterministic and easy to test. It keeps its working state in
memory; with ``open_service`` it also writes every change to SQLite and the
file store (step 1.5), one transaction per call. A refused call (any
``ServiceError``) changes nothing: the transaction is rolled back and the
state reloaded. The HTTP API comes in step 1.6.
"""

from __future__ import annotations

import functools
import json
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

from orbit_watch import calibration as cal
from orbit_watch import lifecycle as lc
from orbit_watch.canonical import dumps_pretty, sha256_bytes
from orbit_watch.formats import Sites
from orbit_watch.lifecycle import RequestRecord, Status, TransitionError
from orbit_watch.reviewers import ReviewerError, ReviewerRegistry
from orbit_watch.settlement import SettlementAdapter, SettlementError, settlement_plan
from orbit_watch.storage import Storage, StoredFiles
from orbit_watch.timeutil import format_utc
from orbit_watch.verify.engine import UsageError, VerificationInput, verify

VERIFIER = "system:verifier"
PLATFORM = "platform:orbit-watch"


def _atomic[F: Callable[..., Any]](method: F) -> F:
    """One transaction per call when the service is stored; reload on failure."""

    @functools.wraps(method)
    def wrapper(self: RequestService, *args: Any, **kwargs: Any) -> Any:
        if self.storage is None:
            return method(self, *args, **kwargs)
        try:
            with self.storage.db.transaction():
                return method(self, *args, **kwargs)
        except BaseException:
            self._reload()
            raise

    return wrapper  # type: ignore[return-value]


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
    storage: Storage | None = None

    # ------------------------------------------------------------------ persistence

    def _save_record(self, record: RequestRecord) -> RequestRecord:
        self.records[record.request_id] = record
        if self.storage is not None:
            self.storage.db.execute(
                "INSERT INTO requests (request_id, requester, status, request_sha256, "
                "record_json, updated_at) VALUES (?, ?, ?, ?, ?, ?) "
                "ON CONFLICT (request_id) DO UPDATE SET status = excluded.status, "
                "record_json = excluded.record_json, updated_at = excluded.updated_at",
                (
                    record.request_id,
                    record.requester,
                    str(record.status),
                    sha256_bytes(self.request_documents[record.request_id]),
                    json.dumps(record.to_document(), sort_keys=True),
                    format_utc(record.updated_at),
                ),
            )
        return record

    def _save_delivery(self, delivered: Delivered) -> None:
        self.deliveries[delivered.request_id] = delivered
        if self.storage is not None:
            self.storage.db.execute(
                "INSERT INTO deliveries (request_id, station, observations_sha256, "
                "observations_format, report_sha256, verdict) VALUES (?, ?, ?, ?, ?, ?)",
                (
                    delivered.request_id,
                    delivered.station,
                    delivered.observations_sha256,
                    delivered.observations_format,
                    delivered.report_sha256,
                    delivered.verdict,
                ),
            )

    def _save_settlement(self, request_id: str, settlement: dict[str, Any]) -> None:
        self.settlements[request_id] = settlement
        if self.storage is not None:
            self.storage.db.execute(
                "INSERT INTO settlements (request_id, plan_json, reference) VALUES (?, ?, ?)",
                (
                    request_id,
                    json.dumps(settlement["plan"], sort_keys=True),
                    settlement["reference"],
                ),
            )

    def _save_real_task(self, task_id: str, request_id: str, reviewer: str) -> None:
        self.real_tasks[task_id] = (request_id, reviewer)
        if self.storage is not None:
            self.storage.db.execute(
                "INSERT INTO review_tasks (task_id, reviewer, kind, request_id) "
                "VALUES (?, ?, 'real', ?) ON CONFLICT (task_id) DO NOTHING",
                (task_id, reviewer, request_id),
            )

    def _save_calibration_task(self, task: cal.CalibrationTask) -> None:
        self.calibration_tasks[task.task_id] = task
        if self.storage is not None:
            self.storage.db.execute(
                "INSERT INTO review_tasks (task_id, reviewer, kind, calibration_json) "
                "VALUES (?, ?, 'calibration', ?) ON CONFLICT (task_id) DO UPDATE SET "
                "calibration_json = excluded.calibration_json",
                (task.task_id, task.reviewer, json.dumps(task.to_document(), sort_keys=True)),
            )

    def _reload(self) -> None:
        """Rebuild the working state from storage (after a rollback or on start)."""
        if self.storage is None:  # pragma: no cover - only called when stored
            return
        db = self.storage.db
        self.files = StoredFiles(self.storage)  # type: ignore[assignment]
        self.request_documents = {
            row["request_id"]: self.storage.files.get(row["request_sha256"])
            for row in db.query("SELECT request_id, request_sha256 FROM requests")
        }
        self.records = {
            row["request_id"]: lc.record_from_document(json.loads(row["record_json"]))
            for row in db.query("SELECT request_id, record_json FROM requests ORDER BY request_id")
        }
        self.deliveries = {
            row["request_id"]: Delivered(
                row["request_id"],
                row["station"],
                row["observations_sha256"],
                row["observations_format"],
                row["report_sha256"],
                row["verdict"],
            )
            for row in db.query("SELECT * FROM deliveries ORDER BY request_id")
        }
        self.settlements = {
            row["request_id"]: {"plan": json.loads(row["plan_json"]), "reference": row["reference"]}
            for row in db.query("SELECT * FROM settlements ORDER BY request_id")
        }
        self.real_tasks = {}
        self.calibration_tasks = {}
        for row in db.query("SELECT * FROM review_tasks ORDER BY task_id"):
            if row["kind"] == "real":
                self.real_tasks[row["task_id"]] = (row["request_id"], row["reviewer"])
            else:
                task = cal.CalibrationTask.from_document(json.loads(row["calibration_json"]))
                self.calibration_tasks[task.task_id] = task
        reload = getattr(self.adapter, "reload", None)
        if reload is not None:
            reload()

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
        self._save_record(record)
        return self._settle_if_finished(request_id, event.at)

    def _store(self, data: bytes) -> str:
        if self.storage is not None:
            return self.storage.put_file(data)
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
        self._save_settlement(
            request_id, {"plan": plan.to_document(), "reference": receipt.reference}
        )
        record = lc.apply(record, lc.Settle(max(now, record.updated_at)))
        return self._save_record(record)

    # ------------------------------------------------------------------ requester

    @_atomic
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
        return self._save_record(lc.create(parsed_terms, now))

    def _require_requester(self, request_id: str, party: str) -> None:
        if party != self._record(request_id).requester:
            raise ServiceError("not_requester", "only the requester can do this")

    @_atomic
    def open(self, request_id: str, party: str, now: datetime) -> RequestRecord:
        self._require_requester(request_id, party)
        return self._apply(request_id, lc.Open(now))

    @_atomic
    def fund(
        self, request_id: str, party: str, split: lc.RewardSplit, now: datetime
    ) -> RequestRecord:
        self._require_requester(request_id, party)
        before = self._record(request_id)
        record = self._apply(request_id, lc.Fund(now, split))
        try:
            self.adapter.fund(request_id, party, split.total, key=f"{request_id}/fund")
        except SettlementError as error:
            self._save_record(before)  # keep the lifecycle and the books in step
            raise ServiceError(error.code, str(error)) from None
        return record

    @_atomic
    def cancel(self, request_id: str, party: str, now: datetime) -> RequestRecord:
        return self._apply(request_id, lc.Cancel(now, party))

    # ------------------------------------------------------------------ station

    @_atomic
    def reserve(self, request_id: str, station: str, now: datetime) -> RequestRecord:
        record = self._apply(request_id, lc.Reserve(now, station))
        count = sum(1 for h in record.history if h.event == "reserve")
        self.adapter.reserve(request_id, station, key=f"{request_id}/reserve/{count}")
        return record

    @_atomic
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
        self._save_delivery(
            Delivered(
                request_id,
                station,
                observations_sha256,
                observations_format,
                report_sha256,
                verdict,
            )
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

    @_atomic
    def challenge(self, request_id: str, party: str, reason: str, now: datetime) -> RequestRecord:
        if not reason.strip():
            raise ServiceError("reason_required", "a challenge must say why")
        record = lc.advance(self._record(request_id), now)
        if record.status is not Status.CHALLENGE_PERIOD:
            raise ServiceError(
                "forbidden_in_status",
                f"'challenge' is not allowed when the request is {record.status}",
            )
        self._save_record(record)
        reviewers = self._select(request_id, record.delivery_sha256 or "", challenger=party)
        record = self._apply(request_id, lc.Challenge(now, party, reviewers, reason))
        self._assign(request_id, now)
        return record

    @_atomic
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
            self._save_real_task(self._task_id("real", request_id, reviewer), request_id, reviewer)
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
                self._save_calibration_task(task)

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

    @_atomic
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
        self._save_calibration_task(task)
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

    @_atomic
    def tick(self, now: datetime) -> list[str]:
        """Apply passed deadlines to every request and settle finished ones."""
        changed = []
        for request_id in sorted(self.records):
            before = self.records[request_id]
            if before.status is Status.SETTLED:
                continue
            self._save_record(lc.advance(before, now))
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


def open_service(
    directory: str | Path,
    reviewers: ReviewerRegistry,
    context: VerificationContext,
    **options: Any,
) -> RequestService:
    """A service whose state lives in ``directory`` (SQLite and files) and survives restarts.

    Opening the same directory from a second process fails with
    ``StorageError("in_use")``.
    """
    from orbit_watch.settlement.sqlite_ledger import SqliteLedgerAdapter

    storage = Storage(directory)
    service = RequestService(
        SqliteLedgerAdapter(storage.db), reviewers, context, storage=storage, **options
    )
    service._reload()
    return service

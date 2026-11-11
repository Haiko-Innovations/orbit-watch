"""The request lifecycle: a pure state machine (phase 1, step 1.1).

A request moves through these statuses::

    draft -> open -> (funded) -> reserved -> delivered -> challenge_period
          -> accepted | rejected | (in_review -> accepted | rejected | disputed)
          -> settled

    open, funded, reserved, delivered -> expired -> settled
    draft, open, funded -> cancelled -> settled

``challenge_period`` is the plan's "automatically verified" state: the
automated verification result is published and anyone with a stake may
challenge it until the deadline.

The machine is pure (decisions P-05): ``apply(record, event)`` returns a new
record and never reads a clock, a database or the network. Time comes from
the events. Timeouts are applied by ``advance(record, now)``, at the exact
moment each deadline passes, so the history is the same however often a
scheduler calls it. Money and points are not handled here: settlement
effects come with the settlement adapter (step 1.2).
"""

from __future__ import annotations

import dataclasses
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import StrEnum
from typing import Any

from orbit_watch.canonical import dumps_compact, sha256_bytes
from orbit_watch.timeutil import format_utc

LIFECYCLE_VERSION = "1.0"
MAX_EMBARGO_DAYS = 30
REVIEWERS_PER_ROUND = 3
VOTES_TO_DECIDE = 2

# Default time limits (decision P-07), copied into each request's terms when it opens.
DEFAULT_RESERVATION_HOURS = 72.0
DEFAULT_CHALLENGE_PERIOD_HOURS = 24.0
DEFAULT_REVIEW_HOURS = 48.0
DEFAULT_VERIFICATION_TIMEOUT_HOURS = 24.0
DEFAULT_DELIVERY_GRACE_HOURS = 24.0  # delivery deadline = window end + grace, if not given


class Status(StrEnum):
    DRAFT = "draft"
    OPEN = "open"
    FUNDED = "funded"
    RESERVED = "reserved"
    DELIVERED = "delivered"
    CHALLENGE_PERIOD = "challenge_period"
    IN_REVIEW = "in_review"
    ACCEPTED = "accepted"
    REJECTED = "rejected"
    DISPUTED = "disputed"
    EXPIRED = "expired"
    CANCELLED = "cancelled"
    SETTLED = "settled"


OUTCOMES = (Status.ACCEPTED, Status.REJECTED, Status.DISPUTED, Status.EXPIRED, Status.CANCELLED)


class TransitionError(ValueError):
    """An event that is not allowed. ``code`` is stable; the message explains it."""

    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


# --------------------------------------------------------------------------- terms


@dataclass(frozen=True)
class Terms:
    """What the requester and the observers agree on. Frozen when the request opens."""

    request_id: str
    request_sha256: str  # SHA-256 of the request document (target, window, requirements)
    requester: str
    target_norad_id: int
    window_start: datetime
    window_end: datetime
    delivery_deadline: datetime
    reservation_hours: float = DEFAULT_RESERVATION_HOURS
    challenge_period_hours: float = DEFAULT_CHALLENGE_PERIOD_HOURS
    review_hours: float = DEFAULT_REVIEW_HOURS
    verification_timeout_hours: float = DEFAULT_VERIFICATION_TIMEOUT_HOURS
    embargo_days: int = 0
    licence: str = "CC-BY-4.0"
    verification_method: str = "orbit-watch-automated-verification 1.0.0"

    def problems(self) -> list[str]:
        found = []
        if self.window_end <= self.window_start:
            found.append("the window ends before it starts")
        if self.delivery_deadline < self.window_end:
            found.append("the delivery deadline is before the end of the window")
        for name in (
            "reservation_hours",
            "challenge_period_hours",
            "review_hours",
            "verification_timeout_hours",
        ):
            if not getattr(self, name) > 0:
                found.append(f"{name} must be positive")
        if not 0 <= self.embargo_days <= MAX_EMBARGO_DAYS:
            found.append(f"the embargo must be 0 to {MAX_EMBARGO_DAYS} days")
        if not self.requester:
            found.append("the requester is missing")
        return found

    def to_document(self) -> dict[str, Any]:
        return {
            "lifecycle_version": LIFECYCLE_VERSION,
            "request_id": self.request_id,
            "request_sha256": self.request_sha256,
            "requester": self.requester,
            "target_norad_id": self.target_norad_id,
            "window_start": format_utc(self.window_start),
            "window_end": format_utc(self.window_end),
            "delivery_deadline": format_utc(self.delivery_deadline),
            "reservation_hours": self.reservation_hours,
            "challenge_period_hours": self.challenge_period_hours,
            "review_hours": self.review_hours,
            "verification_timeout_hours": self.verification_timeout_hours,
            "embargo_days": self.embargo_days,
            "licence": self.licence,
            "verification_method": self.verification_method,
        }

    def sha256(self) -> str:
        return sha256_bytes(dumps_compact(self.to_document()).encode("utf-8"))


def terms_from_request(
    request_bytes: bytes,
    requester: str,
    *,
    delivery_deadline: datetime | None = None,
    **overrides: Any,
) -> Terms:
    """Build terms from an Orbit Watch request document and lifecycle parameters."""
    from orbit_watch.documents import Request

    request = Request.parse(request_bytes)
    deadline = delivery_deadline or request.window_end + timedelta(
        hours=DEFAULT_DELIVERY_GRACE_HOURS
    )
    return Terms(
        request_id=request.request_id,
        request_sha256=sha256_bytes(request_bytes),
        requester=requester,
        target_norad_id=request.norad_id,
        window_start=request.window_start,
        window_end=request.window_end,
        delivery_deadline=deadline,
        **overrides,
    )


# --------------------------------------------------------------------------- rewards


@dataclass(frozen=True)
class RewardSplit:
    """How the deposit of a funded request is divided. Locked when it is funded (P-06).

    The deposit is ``observer + REVIEWERS_PER_ROUND * reviewer + platform_fee``
    points. The reviewer share is the challenge-round reserve: it pays the
    reviewers if there is a reviewer round, and goes back to the requester if
    there is not.
    """

    observer: int
    reviewer: int  # per completed review
    platform_fee: int = 0

    @property
    def challenge_reserve(self) -> int:
        return REVIEWERS_PER_ROUND * self.reviewer

    @property
    def total(self) -> int:
        return self.observer + self.challenge_reserve + self.platform_fee

    def problems(self) -> list[str]:
        found = []
        for name in ("observer", "reviewer", "platform_fee"):
            value = getattr(self, name)
            if not isinstance(value, int) or isinstance(value, bool) or value < 0:
                found.append(f"{name} must be a whole number of points, zero or more")
        if not found and self.total <= 0:
            found.append("the deposit must be at least one point")
        return found

    def to_document(self) -> dict[str, int]:
        return {
            "observer": self.observer,
            "reviewer": self.reviewer,
            "platform_fee": self.platform_fee,
            "challenge_reserve": self.challenge_reserve,
            "total": self.total,
        }


# --------------------------------------------------------------------------- events


@dataclass(frozen=True)
class ReviseTerms:
    at: datetime
    terms: Terms


@dataclass(frozen=True)
class Open:
    at: datetime


@dataclass(frozen=True)
class Fund:
    at: datetime
    split: RewardSplit


@dataclass(frozen=True)
class Reserve:
    at: datetime
    station: str


@dataclass(frozen=True)
class Deliver:
    at: datetime
    station: str
    delivery_sha256: str


@dataclass(frozen=True)
class RecordVerification:
    """The automated verification result. An inconclusive result goes straight to
    a reviewer round, so it needs the reviewers."""

    at: datetime
    verdict: str  # "pass", "fail" or "inconclusive"
    report_sha256: str
    reviewers: tuple[str, ...] = ()


@dataclass(frozen=True)
class Challenge:
    at: datetime
    party: str
    reviewers: tuple[str, ...]
    reason: str = ""


@dataclass(frozen=True)
class Vote:
    at: datetime
    reviewer: str
    approve: bool
    reason: str = ""


@dataclass(frozen=True)
class Cancel:
    at: datetime
    party: str


@dataclass(frozen=True)
class Settle:
    at: datetime


Event = (
    ReviseTerms
    | Open
    | Fund
    | Reserve
    | Deliver
    | RecordVerification
    | Challenge
    | Vote
    | Cancel
    | Settle
)

# Which events each status accepts. Timeouts are not events; see TIMEOUTS.
ALLOWED: dict[Status, tuple[type, ...]] = {
    Status.DRAFT: (ReviseTerms, Open, Cancel),
    Status.OPEN: (Fund, Reserve, Cancel),
    Status.FUNDED: (Reserve, Cancel),
    Status.RESERVED: (Deliver,),
    Status.DELIVERED: (RecordVerification,),
    Status.CHALLENGE_PERIOD: (Challenge,),
    Status.IN_REVIEW: (Vote,),
    Status.ACCEPTED: (Settle,),
    Status.REJECTED: (Settle,),
    Status.DISPUTED: (Settle,),
    Status.EXPIRED: (Settle,),
    Status.CANCELLED: (Settle,),
    Status.SETTLED: (),
}

# Deadlines that move a request on by themselves: (status, deadline, resulting status(es)).
TIMEOUTS: tuple[tuple[Status, str, str], ...] = (
    (Status.RESERVED, "reservation expires", "open or funded (the reservation lapses)"),
    (Status.OPEN, "delivery deadline", "expired"),
    (Status.FUNDED, "delivery deadline", "expired"),
    (Status.RESERVED, "delivery deadline", "expired"),
    (Status.DELIVERED, "verification timeout", "expired"),
    (Status.CHALLENGE_PERIOD, "challenge deadline", "accepted (pass) or rejected (fail)"),
    (Status.IN_REVIEW, "review deadline", "disputed (no 2-of-3 majority)"),
)


# --------------------------------------------------------------------------- record


@dataclass(frozen=True)
class HistoryEntry:
    at: datetime
    event: str
    from_status: Status
    to_status: Status
    detail: str = ""


@dataclass(frozen=True)
class RequestRecord:
    request_id: str
    requester: str
    status: Status
    terms: Terms
    created_at: datetime
    updated_at: datetime
    terms_sha256: str | None = None
    funded_points: int = 0
    split: RewardSplit | None = None
    reserved_by: str | None = None
    reservation_expires_at: datetime | None = None
    observer: str | None = None
    delivery_sha256: str | None = None
    delivered_at: datetime | None = None
    automated_verdict: str | None = None
    report_sha256: str | None = None
    challenge_deadline: datetime | None = None
    challenger: str | None = None
    reviewers: tuple[str, ...] = ()
    votes: tuple[tuple[str, bool], ...] = ()
    vote_reasons: tuple[tuple[str, str], ...] = ()
    challenge_reason: str | None = None
    review_deadline: datetime | None = None
    outcome: Status | None = None
    outcome_reason: str | None = None
    history: tuple[HistoryEntry, ...] = field(default=())

    def to_document(self) -> dict[str, Any]:
        """Deterministic JSON-ready form, for storage and hashing."""

        def t(value: datetime | None) -> str | None:
            return None if value is None else format_utc(value)

        return {
            "lifecycle_version": LIFECYCLE_VERSION,
            "request_id": self.request_id,
            "requester": self.requester,
            "status": str(self.status),
            "terms": self.terms.to_document(),
            "terms_sha256": self.terms_sha256,
            "created_at": t(self.created_at),
            "updated_at": t(self.updated_at),
            "funded_points": self.funded_points,
            "split": None if self.split is None else self.split.to_document(),
            "reserved_by": self.reserved_by,
            "reservation_expires_at": t(self.reservation_expires_at),
            "observer": self.observer,
            "delivery_sha256": self.delivery_sha256,
            "delivered_at": t(self.delivered_at),
            "automated_verdict": self.automated_verdict,
            "report_sha256": self.report_sha256,
            "challenge_deadline": t(self.challenge_deadline),
            "challenger": self.challenger,
            "reviewers": list(self.reviewers),
            "votes": [[reviewer, approve] for reviewer, approve in self.votes],
            "vote_reasons": [[reviewer, reason] for reviewer, reason in self.vote_reasons],
            "challenge_reason": self.challenge_reason,
            "review_deadline": t(self.review_deadline),
            "outcome": None if self.outcome is None else str(self.outcome),
            "outcome_reason": self.outcome_reason,
            "history": [
                {
                    "at": t(h.at),
                    "event": h.event,
                    "from": str(h.from_status),
                    "to": str(h.to_status),
                    "detail": h.detail,
                }
                for h in self.history
            ],
        }


def create(terms: Terms, at: datetime) -> RequestRecord:
    """A new request in draft."""
    return RequestRecord(
        request_id=terms.request_id,
        requester=terms.requester,
        status=Status.DRAFT,
        terms=terms,
        created_at=at,
        updated_at=at,
        history=(HistoryEntry(at, "create", Status.DRAFT, Status.DRAFT),),
    )


def _hours(value: float) -> timedelta:
    return timedelta(hours=value)


def _move(
    record: RequestRecord, at: datetime, event: str, to: Status, detail: str = "", **changes: Any
) -> RequestRecord:
    entry = HistoryEntry(at, event, record.status, to, detail)
    return dataclasses.replace(
        record, status=to, updated_at=at, history=(*record.history, entry), **changes
    )


def _finish(
    record: RequestRecord, at: datetime, event: str, outcome: Status, reason: str, **changes: Any
) -> RequestRecord:
    return _move(
        record, at, event, outcome, reason, outcome=outcome, outcome_reason=reason, **changes
    )


# --------------------------------------------------------------------------- timeouts


def next_deadline(record: RequestRecord) -> tuple[datetime, str] | None:
    """The earliest deadline that would move this request on, if any."""
    terms = record.terms
    candidates: list[tuple[datetime, str]] = []
    if record.status is Status.RESERVED and record.reservation_expires_at is not None:
        candidates.append((record.reservation_expires_at, "reservation_lapsed"))
    if record.status in (Status.OPEN, Status.FUNDED, Status.RESERVED):
        candidates.append((terms.delivery_deadline, "delivery_deadline_passed"))
    if record.status is Status.DELIVERED and record.delivered_at is not None:
        candidates.append(
            (
                record.delivered_at + _hours(terms.verification_timeout_hours),
                "verification_timed_out",
            )
        )
    if record.status is Status.CHALLENGE_PERIOD and record.challenge_deadline is not None:
        candidates.append((record.challenge_deadline, "challenge_period_ended"))
    if record.status is Status.IN_REVIEW and record.review_deadline is not None:
        candidates.append((record.review_deadline, "review_deadline_passed"))
    if not candidates:
        return None
    # A lapsed reservation is handled before a delivery deadline at the same moment.
    order = {"reservation_lapsed": 0}
    return min(candidates, key=lambda c: (c[0], order.get(c[1], 1)))


def _timeout(record: RequestRecord, at: datetime, kind: str) -> RequestRecord:
    if kind == "reservation_lapsed":
        back = Status.FUNDED if record.funded_points > 0 else Status.OPEN
        return _move(
            record,
            at,
            kind,
            back,
            f"reservation by {record.reserved_by} lapsed",
            reserved_by=None,
            reservation_expires_at=None,
        )
    if kind == "delivery_deadline_passed":
        return _finish(
            record,
            at,
            kind,
            Status.EXPIRED,
            "no delivery before the deadline",
            reserved_by=None,
            reservation_expires_at=None,
        )
    if kind == "verification_timed_out":
        return _finish(record, at, kind, Status.EXPIRED, "automated verification did not finish")
    if kind == "challenge_period_ended":
        if record.automated_verdict == "pass":
            return _finish(
                record,
                at,
                kind,
                Status.ACCEPTED,
                "automated verification passed and nobody challenged it",
            )
        return _finish(
            record,
            at,
            kind,
            Status.REJECTED,
            "automated verification failed and nobody challenged it",
        )
    if kind == "review_deadline_passed":
        return _finish(
            record,
            at,
            kind,
            Status.DISPUTED,
            f"no {VOTES_TO_DECIDE}-of-{REVIEWERS_PER_ROUND} majority before the review deadline",
        )
    raise AssertionError(kind)


def advance(record: RequestRecord, now: datetime) -> RequestRecord:
    """Apply every deadline that has passed by ``now``, each at its own time."""
    if now < record.updated_at:
        raise TransitionError(
            "out_of_order",
            f"time {format_utc(now)} is before the last change {format_utc(record.updated_at)}",
        )
    while True:
        due = next_deadline(record)
        if due is None or due[0] > now:
            return record
        record = _timeout(record, due[0], due[1])


# --------------------------------------------------------------------------- events


def _event_name(event: Event) -> str:
    return {
        ReviseTerms: "revise_terms",
        Open: "open",
        Fund: "fund",
        Reserve: "reserve",
        Deliver: "deliver",
        RecordVerification: "record_verification",
        Challenge: "challenge",
        Vote: "vote",
        Cancel: "cancel",
        Settle: "settle",
    }[type(event)]


def _check_reviewers(record: RequestRecord, reviewers: tuple[str, ...]) -> None:
    if len(reviewers) != REVIEWERS_PER_ROUND or len(set(reviewers)) != REVIEWERS_PER_ROUND:
        raise TransitionError(
            "invalid_reviewers", f"a reviewer round needs {REVIEWERS_PER_ROUND} different reviewers"
        )
    conflicted = sorted({record.requester, record.observer or ""} & set(reviewers))
    if conflicted:
        raise TransitionError(
            "conflict_of_interest",
            f"{', '.join(conflicted)} cannot review a request they are a party to",
        )


def apply(record: RequestRecord, event: Event) -> RequestRecord:
    """Apply one event. Deadlines up to the event's time are applied first."""
    record = advance(record, event.at)
    name = _event_name(event)
    if not isinstance(event, ALLOWED[record.status]):
        raise TransitionError(
            "forbidden_in_status",
            f"'{name}' is not allowed when the request is {record.status}",
        )
    at = event.at
    terms = record.terms

    if isinstance(event, ReviseTerms):
        if event.terms.request_id != record.request_id or event.terms.requester != record.requester:
            raise TransitionError("invalid_terms", "the request id and requester cannot change")
        return _move(record, at, name, Status.DRAFT, terms=event.terms)

    if isinstance(event, Open):
        problems = terms.problems()
        if problems:
            raise TransitionError("invalid_terms", "; ".join(problems))
        if at >= terms.delivery_deadline:
            raise TransitionError("deadline_passed", "the delivery deadline has already passed")
        return _move(
            record,
            at,
            name,
            Status.OPEN,
            f"terms {terms.sha256()[:16]}",
            terms_sha256=terms.sha256(),
        )

    if isinstance(event, Fund):
        problems = event.split.problems()
        if problems:
            raise TransitionError("invalid_amount", "; ".join(problems))
        return _move(
            record,
            at,
            name,
            Status.FUNDED,
            f"{event.split.total} points",
            funded_points=event.split.total,
            split=event.split,
        )

    if isinstance(event, Reserve):
        if event.station == record.requester:
            raise TransitionError(
                "conflict_of_interest", "the requester cannot reserve their own request"
            )
        expires = min(at + _hours(terms.reservation_hours), terms.delivery_deadline)
        return _move(
            record,
            at,
            name,
            Status.RESERVED,
            f"by {event.station}",
            reserved_by=event.station,
            reservation_expires_at=expires,
        )

    if isinstance(event, Deliver):
        if event.station != record.reserved_by:
            raise TransitionError(
                "not_reserved_by_station",
                f"the request is reserved by {record.reserved_by}, not {event.station}",
            )
        return _move(
            record,
            at,
            name,
            Status.DELIVERED,
            f"sha256 {event.delivery_sha256[:16]}",
            observer=event.station,
            delivery_sha256=event.delivery_sha256,
            delivered_at=at,
            reservation_expires_at=None,
        )

    if isinstance(event, RecordVerification):
        if event.verdict not in ("pass", "fail", "inconclusive"):
            raise TransitionError("invalid_verdict", f"unknown verdict {event.verdict!r}")
        common = dict(automated_verdict=event.verdict, report_sha256=event.report_sha256)
        if event.verdict == "inconclusive":
            _check_reviewers(record, event.reviewers)
            return _move(
                record,
                at,
                name,
                Status.IN_REVIEW,
                "inconclusive result goes straight to reviewers",
                reviewers=event.reviewers,
                review_deadline=at + _hours(terms.review_hours),
                **common,
            )
        return _move(
            record,
            at,
            name,
            Status.CHALLENGE_PERIOD,
            f"verdict {event.verdict}",
            challenge_deadline=at + _hours(terms.challenge_period_hours),
            **common,
        )

    if isinstance(event, Challenge):
        if event.party not in (record.requester, record.observer):
            raise TransitionError("not_a_party", "only the requester or the observer can challenge")
        _check_reviewers(record, event.reviewers)
        return _move(
            record,
            at,
            name,
            Status.IN_REVIEW,
            f"by {event.party}",
            challenger=event.party,
            challenge_reason=event.reason,
            reviewers=event.reviewers,
            review_deadline=at + _hours(terms.review_hours),
        )

    if isinstance(event, Vote):
        if event.reviewer not in record.reviewers:
            raise TransitionError("not_assigned", f"{event.reviewer} is not a reviewer here")
        if any(reviewer == event.reviewer for reviewer, _ in record.votes):
            raise TransitionError("already_voted", f"{event.reviewer} has already voted")
        votes = (*record.votes, (event.reviewer, event.approve))
        reasons = (*record.vote_reasons, (event.reviewer, event.reason))
        approvals = sum(1 for _, approve in votes if approve)
        rejections = len(votes) - approvals
        detail = f"{event.reviewer}: {'approve' if event.approve else 'reject'}"
        if approvals >= VOTES_TO_DECIDE:
            return _finish(
                record,
                at,
                name,
                Status.ACCEPTED,
                f"reviewers approved {approvals}-{rejections}",
                votes=votes,
                vote_reasons=reasons,
            )
        if rejections >= VOTES_TO_DECIDE:
            return _finish(
                record,
                at,
                name,
                Status.REJECTED,
                f"reviewers rejected {rejections}-{approvals}",
                votes=votes,
                vote_reasons=reasons,
            )
        return _move(record, at, name, Status.IN_REVIEW, detail, votes=votes, vote_reasons=reasons)

    if isinstance(event, Cancel):
        if event.party != record.requester:
            raise TransitionError("not_requester", "only the requester can cancel")
        return _finish(record, at, name, Status.CANCELLED, "cancelled by the requester")

    if isinstance(event, Settle):
        return _move(record, at, name, Status.SETTLED, f"outcome {record.outcome}")

    raise AssertionError(name)  # pragma: no cover


def mermaid_diagram() -> str:
    """The state diagram in Mermaid syntax. Tests keep it consistent with ``ALLOWED``
    and with docs/lifecycle.md."""
    lines = ["stateDiagram-v2", "    [*] --> draft: create"]
    edges = [
        ("draft", "open", "open"),
        ("draft", "cancelled", "cancel"),
        ("open", "funded", "fund"),
        ("open", "reserved", "reserve"),
        ("open", "cancelled", "cancel"),
        ("open", "expired", "delivery deadline"),
        ("funded", "reserved", "reserve"),
        ("funded", "cancelled", "cancel"),
        ("funded", "expired", "delivery deadline"),
        ("reserved", "open", "reservation lapses (unfunded)"),
        ("reserved", "funded", "reservation lapses (funded)"),
        ("reserved", "delivered", "deliver"),
        ("reserved", "expired", "delivery deadline"),
        ("delivered", "challenge_period", "verification pass/fail"),
        ("delivered", "in_review", "verification inconclusive"),
        ("delivered", "expired", "verification timeout"),
        ("challenge_period", "in_review", "challenge"),
        ("challenge_period", "accepted", "deadline, pass"),
        ("challenge_period", "rejected", "deadline, fail"),
        ("in_review", "accepted", "2 of 3 approve"),
        ("in_review", "rejected", "2 of 3 reject"),
        ("in_review", "disputed", "review deadline"),
    ]
    lines += [f"    {a} --> {b}: {label}" for a, b, label in edges]
    lines += [f"    {outcome} --> settled: settle" for outcome in OUTCOMES]
    lines.append("    settled --> [*]")
    return "\n".join(lines) + "\n"

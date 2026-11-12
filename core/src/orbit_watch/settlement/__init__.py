"""Settlement: who gets what when a request ends (phase 1, step 1.2).

Two parts, deliberately separate:

* ``settlement_plan(record)`` is the **rule**: a pure function from a finished
  request (its outcome, votes and locked reward split) to a list of payouts.
  The rule is the same for every adapter, so the points ledger of phase 1 and
  the testnet escrow of phase 2 pay exactly the same amounts.
* A ``SettlementAdapter`` **executes** plans: ``fund``, ``reserve``, ``deliver``,
  ``attest``, ``challenge``, ``settle`` and ``refund``. The default adapter is the
  points-only ledger (``orbit_watch.settlement.ledger``); phase 2 adds the
  ``evm-testnet`` adapter (``orbit_watch.settlement.evm``).

Every mutating call may carry ``record``, the request's lifecycle record right
after the event. The ledger needs nothing from it. An adapter on a chain needs
the terms, the reward split, the delivery, the reviewers and the time of the
event, and takes them from the record (adapter interface 2, decision D-22).

Every mutating adapter call takes an idempotency key. Repeating a call with the
same key and the same arguments returns the first receipt and has no second
effect; reusing a key for different arguments is an error. A request can be
settled only once, whatever the key.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol

from orbit_watch.lifecycle import OUTCOMES, REVIEWERS_PER_ROUND, RequestRecord, Status

RULES_VERSION = "1.0"


class SettlementError(ValueError):
    """A settlement operation was refused. ``code`` is stable."""

    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


@dataclass(frozen=True)
class Payout:
    party: str
    points: int
    reason: str  # "observer_reward", "review", "platform_fee" or "refund"


@dataclass(frozen=True)
class SettlementPlan:
    request_id: str
    outcome: str
    deposit: int
    payouts: tuple[Payout, ...]
    rules_version: str = RULES_VERSION

    @property
    def paid_out(self) -> int:
        return sum(p.points for p in self.payouts)

    def to_document(self) -> dict[str, Any]:
        return {
            "rules_version": self.rules_version,
            "request_id": self.request_id,
            "outcome": self.outcome,
            "deposit": self.deposit,
            "payouts": [
                {"party": p.party, "points": p.points, "reason": p.reason} for p in self.payouts
            ],
        }


def settlement_plan(
    record: RequestRecord, platform: str = "platform:orbit-watch"
) -> SettlementPlan:
    """The payouts for a request that has reached an outcome.

    Rules (version 1.0):

    * **accepted**: the observer gets the observer reward and the platform gets
      its fee;
    * **rejected**, **disputed**, **expired**, **cancelled**: no observer reward
      and no platform fee;
    * in every outcome, each reviewer who **completed a review** (cast a vote)
      gets the reviewer reward, whatever the outcome; reviewers who did not vote
      before the round closed get nothing;
    * everything else goes back to the requester. Nothing is ever left in escrow.

    An unfunded request settles with an empty plan.
    """
    status = record.outcome if record.status is Status.SETTLED else record.status
    if status not in OUTCOMES:
        raise SettlementError("not_finished", f"a request that is {record.status} has no outcome")
    split = record.split
    if split is None or record.funded_points == 0:
        return SettlementPlan(record.request_id, str(status), 0, ())
    payouts: list[Payout] = []
    if status is Status.ACCEPTED and split.observer:
        if record.observer is None:  # pragma: no cover - guaranteed by the lifecycle
            raise SettlementError("no_observer", "an accepted request must have an observer")
        payouts.append(Payout(record.observer, split.observer, "observer_reward"))
    voters = [reviewer for reviewer, _ in record.votes]
    if len(voters) > REVIEWERS_PER_ROUND:  # pragma: no cover - guaranteed by the lifecycle
        raise SettlementError("too_many_votes", "more votes than reviewers")
    if split.reviewer:
        payouts.extend(Payout(reviewer, split.reviewer, "review") for reviewer in voters)
    if status is Status.ACCEPTED and split.platform_fee:
        payouts.append(Payout(platform, split.platform_fee, "platform_fee"))
    refund = record.funded_points - sum(p.points for p in payouts)
    if refund < 0:  # pragma: no cover - the split guarantees enough
        raise SettlementError("overdrawn", "payouts exceed the deposit")
    if refund:
        payouts.append(Payout(record.requester, refund, "refund"))
    return SettlementPlan(record.request_id, str(status), record.funded_points, tuple(payouts))


@dataclass(frozen=True)
class Receipt:
    """The result of an adapter call. ``reference`` identifies it in the adapter
    (a journal sequence number for the ledger, a transaction hash on a chain)."""

    key: str
    operation: str
    request_id: str | None
    reference: str
    details: tuple[tuple[str, Any], ...] = ()


class SettlementAdapter(Protocol):
    """What every settlement adapter provides. All amounts are whole units (points on the
    ledger, the token's smallest unit on a chain).

    ``record`` is the request's lifecycle record right after the event the call mirrors.
    """

    name: str

    def fund(
        self,
        request_id: str,
        requester: str,
        points: int,
        *,
        key: str,
        record: RequestRecord | None = None,
    ) -> Receipt:
        """Move ``points`` from the requester into the request's escrow."""

    def reserve(
        self, request_id: str, station: str, *, key: str, record: RequestRecord | None = None
    ) -> Receipt:
        """Record that a station reserved the request (no points move)."""

    def deliver(
        self,
        request_id: str,
        station: str,
        delivery_sha256: str,
        *,
        key: str,
        record: RequestRecord | None = None,
    ) -> Receipt:
        """Record a delivery by its SHA-256 (no points move)."""

    def attest(
        self,
        request_id: str,
        attester: str,
        kind: str,
        subject_sha256: str,
        value: str,
        *,
        key: str,
        record: RequestRecord | None = None,
    ) -> Receipt:
        """Record a signed statement: an automated verification result or a review vote."""

    def challenge(
        self,
        request_id: str,
        party: str,
        reason: str,
        *,
        key: str,
        record: RequestRecord | None = None,
    ) -> Receipt:
        """Record a challenge by the requester or the observer (no points move)."""

    def settle(
        self, plan: SettlementPlan, *, key: str, record: RequestRecord | None = None
    ) -> Receipt:
        """Pay out a settlement plan from escrow. Refused if the request was settled."""

    def refund(
        self, request_id: str, requester: str, *, key: str, record: RequestRecord | None = None
    ) -> Receipt:
        """Return the whole escrow to the requester (expired or cancelled requests)."""

    def balance(self, party: str) -> int:
        """Points a party holds."""

    def escrow(self, request_id: str) -> int:
        """Points held for a request."""

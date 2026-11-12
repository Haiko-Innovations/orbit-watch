"""The default settlement adapter: a points-only, double-entry ledger.

No money and no blockchain. Points are whole numbers. Every journal entry is
balanced (its postings sum to zero), so points are never created or lost
except by an explicit ``grant`` from the issuance account. The journal is
append-only and can be exported as deterministic JSON (storage comes in
step 1.5).

Accounts:

* ``issuance``: the source of all points; its balance is minus the total granted;
* ``party:<id>``: what a requester, station, reviewer or the platform holds;
* ``escrow:<request id>``: points held for a funded request.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from typing import Any

from orbit_watch.canonical import dumps_compact, sha256_bytes
from orbit_watch.lifecycle import RequestRecord
from orbit_watch.settlement import Receipt, SettlementError, SettlementPlan

ISSUANCE = "issuance"


def party_account(party: str) -> str:
    return f"party:{party}"


def escrow_account(request_id: str) -> str:
    return f"escrow:{request_id}"


@dataclass(frozen=True)
class Posting:
    account: str
    amount: int  # positive adds to the account, negative takes from it


@dataclass(frozen=True)
class JournalEntry:
    seq: int
    key: str
    operation: str
    request_id: str | None
    postings: tuple[Posting, ...]
    memo: str

    def to_document(self) -> dict[str, Any]:
        return {
            "seq": self.seq,
            "key": self.key,
            "operation": self.operation,
            "request_id": self.request_id,
            "postings": [{"account": p.account, "amount": p.amount} for p in self.postings],
            "memo": self.memo,
        }


class LedgerAdapter:
    """Points ledger implementing the ``SettlementAdapter`` protocol."""

    name = "ledger"

    def __init__(self) -> None:
        self.journal: list[JournalEntry] = []
        self._balances: dict[str, int] = defaultdict(int)
        self._by_key: dict[str, tuple[str, Receipt]] = {}
        self._settled: dict[str, str] = {}  # request id -> key of the settling entry
        self.attestations: list[dict[str, str]] = []

    # ------------------------------------------------------------------ queries

    def balance(self, party: str) -> int:
        return self._balances[party_account(party)]

    def escrow(self, request_id: str) -> int:
        return self._balances[escrow_account(request_id)]

    def account_balances(self) -> dict[str, int]:
        return {account: amount for account, amount in sorted(self._balances.items()) if amount}

    def total(self) -> int:
        """Sum over all accounts. Always zero for a balanced journal."""
        return sum(self._balances.values())

    def export(self) -> dict[str, Any]:
        return {
            "adapter": self.name,
            "journal": [entry.to_document() for entry in self.journal],
            "attestations": list(self.attestations),
            "balances": self.account_balances(),
        }

    # ------------------------------------------------------------------ internals

    def _idempotent(self, key: str, fingerprint: dict[str, Any]) -> Receipt | None:
        if not key:
            raise SettlementError("missing_key", "every call needs an idempotency key")
        digest = sha256_bytes(dumps_compact(fingerprint).encode("utf-8"))
        if key in self._by_key:
            seen_digest, receipt = self._by_key[key]
            if seen_digest != digest:
                raise SettlementError(
                    "key_reused", f"idempotency key {key!r} was already used for another call"
                )
            return receipt
        return None

    def _record(
        self,
        key: str,
        fingerprint: dict[str, Any],
        operation: str,
        request_id: str | None,
        postings: list[Posting],
        memo: str,
    ) -> Receipt:
        if sum(p.amount for p in postings) != 0:  # pragma: no cover - internal guarantee
            raise AssertionError("unbalanced journal entry")
        for posting in postings:
            if posting.account != ISSUANCE and self._balances[posting.account] + posting.amount < 0:
                raise SettlementError(
                    "insufficient_points",
                    f"{posting.account} holds {self._balances[posting.account]} points, "
                    f"{-posting.amount} needed",
                )
        entry = JournalEntry(
            len(self.journal) + 1,
            key,
            operation,
            request_id,
            tuple(p for p in postings if p.amount),
            memo,
        )
        self.journal.append(entry)
        for posting in entry.postings:
            self._balances[posting.account] += posting.amount
        receipt = Receipt(
            key,
            operation,
            request_id,
            f"ledger:{entry.seq}",
            tuple((p.account, p.amount) for p in entry.postings),
        )
        digest = sha256_bytes(dumps_compact(fingerprint).encode("utf-8"))
        self._by_key[key] = (digest, receipt)
        return receipt

    # ------------------------------------------------------------------ operations

    def grant(self, party: str, points: int, *, key: str) -> Receipt:
        """Give points to a party from the issuance account (phase 1 budgets)."""
        fingerprint = {"op": "grant", "party": party, "points": points}
        if (seen := self._idempotent(key, fingerprint)) is not None:
            return seen
        _positive(points)
        return self._record(
            key,
            fingerprint,
            "grant",
            None,
            [Posting(ISSUANCE, -points), Posting(party_account(party), points)],
            f"grant to {party}",
        )

    def fund(
        self,
        request_id: str,
        requester: str,
        points: int,
        *,
        key: str,
        record: RequestRecord | None = None,
    ) -> Receipt:
        fingerprint = {
            "op": "fund",
            "request": request_id,
            "requester": requester,
            "points": points,
        }
        if (seen := self._idempotent(key, fingerprint)) is not None:
            return seen
        _positive(points)
        if self.escrow(request_id) or request_id in self._settled:
            raise SettlementError("already_funded", f"request {request_id} is already funded")
        return self._record(
            key,
            fingerprint,
            "fund",
            request_id,
            [
                Posting(party_account(requester), -points),
                Posting(escrow_account(request_id), points),
            ],
            f"deposit by {requester}",
        )

    def reserve(
        self, request_id: str, station: str, *, key: str, record: RequestRecord | None = None
    ) -> Receipt:
        fingerprint = {"op": "reserve", "request": request_id, "station": station}
        if (seen := self._idempotent(key, fingerprint)) is not None:
            return seen
        return self._record(key, fingerprint, "reserve", request_id, [], f"reserved by {station}")

    def deliver(
        self,
        request_id: str,
        station: str,
        delivery_sha256: str,
        *,
        key: str,
        record: RequestRecord | None = None,
    ) -> Receipt:
        """No points move and nothing is journaled: the lifecycle keeps the delivery."""
        return _not_journaled(key, "deliver", request_id)

    def challenge(
        self,
        request_id: str,
        party: str,
        reason: str,
        *,
        key: str,
        record: RequestRecord | None = None,
    ) -> Receipt:
        """No points move and nothing is journaled: the lifecycle keeps the challenge."""
        return _not_journaled(key, "challenge", request_id)

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
        fingerprint = {
            "op": "attest",
            "request": request_id,
            "attester": attester,
            "kind": kind,
            "subject": subject_sha256,
            "value": value,
        }
        if (seen := self._idempotent(key, fingerprint)) is not None:
            return seen
        receipt = self._record(
            key, fingerprint, "attest", request_id, [], f"{kind} by {attester}: {value}"
        )
        self.attestations.append(
            {
                "request_id": request_id,
                "attester": attester,
                "kind": kind,
                "subject_sha256": subject_sha256,
                "value": value,
                "reference": receipt.reference,
            }
        )
        return receipt

    def settle(
        self, plan: SettlementPlan, *, key: str, record: RequestRecord | None = None
    ) -> Receipt:
        fingerprint = {"op": "settle", "plan": plan.to_document()}
        if (seen := self._idempotent(key, fingerprint)) is not None:
            return seen
        if plan.request_id in self._settled:
            raise SettlementError(
                "already_settled", f"request {plan.request_id} was already settled"
            )
        if plan.paid_out != plan.deposit:
            raise SettlementError(
                "unbalanced_plan",
                f"the plan pays {plan.paid_out} points of a {plan.deposit} deposit",
            )
        held = self.escrow(plan.request_id)
        if held != plan.deposit:
            raise SettlementError(
                "escrow_mismatch", f"escrow holds {held} points, the plan expects {plan.deposit}"
            )
        postings = [Posting(escrow_account(plan.request_id), -plan.deposit)]
        postings += [Posting(party_account(p.party), p.points) for p in plan.payouts]
        receipt = self._record(
            key, fingerprint, "settle", plan.request_id, postings, f"outcome {plan.outcome}"
        )
        self._settled[plan.request_id] = key
        return receipt

    def refund(
        self, request_id: str, requester: str, *, key: str, record: RequestRecord | None = None
    ) -> Receipt:
        fingerprint = {"op": "refund", "request": request_id, "requester": requester}
        if (seen := self._idempotent(key, fingerprint)) is not None:
            return seen
        if request_id in self._settled:
            raise SettlementError("already_settled", f"request {request_id} was already settled")
        held = self.escrow(request_id)
        receipt = self._record(
            key,
            fingerprint,
            "refund",
            request_id,
            [Posting(escrow_account(request_id), -held), Posting(party_account(requester), held)],
            f"refund to {requester}",
        )
        self._settled[request_id] = key
        return receipt


def _not_journaled(key: str, operation: str, request_id: str) -> Receipt:
    if not key:
        raise SettlementError("missing_key", "every call needs an idempotency key")
    return Receipt(key, operation, request_id, "ledger:not-journaled")


def _positive(points: int) -> None:
    if not isinstance(points, int) or isinstance(points, bool) or points <= 0:
        raise SettlementError("invalid_amount", "amounts are positive whole numbers of points")

"""The ``evm-testnet`` settlement adapter (phase 2, step 2.5).

**Testnet only** (Base Sepolia or a local Anvil chain). The escrow contract applies
settlement rules 1.0 itself; this adapter mirrors each lifecycle event to the chain and
checks that the chain paid exactly what the shared rules (``settlement_plan``) say.

| Call | On chain | Signed by |
|---|---|---|
| ``fund`` | ``escrow.fund`` with the request's terms and split | the requester |
| ``reserve`` | ``escrow.reserve`` | the station |
| ``deliver`` | ``escrow.deliver`` | the station |
| ``attest`` (automated result) | EAS attestation, result schema | the verifier key |
| ``challenge`` | ``escrow.challenge`` | the requester or the observer |
| ``attest`` (review vote) | EAS attestation, vote schema | the reviewer |
| ``settle`` | ``escrow.settle`` | the operator (by default the verifier key) |
| ``refund`` | ``escrow.cancel`` if cancelled, ``escrow.settle`` if expired | requester, operator |

Each call needs ``record``, the lifecycle record right after the event (decision D-22).
Unfunded requests never touch the chain. Payouts are credited on chain; ``balance`` is
what a party holds plus what it can withdraw.

Idempotency follows the adapter contract: a key seen before with the same arguments
returns its first receipt without a new transaction; with other arguments it is refused
(``key_reused``). This adapter keeps its keys in memory; persisting them comes with the
service (step 2.6).
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from eth_account.signers.local import LocalAccount

from orbit_watch.canonical import dumps_compact, sha256_bytes
from orbit_watch.chain import (
    ANVIL_CHAIN_ID,
    ChainError,
    bytes32_from_sha256,
    sha256_of_text,
    unix_seconds,
    whole_seconds,
)
from orbit_watch.chain.client import OrbitWatchChain, Sent
from orbit_watch.lifecycle import RequestRecord, Status
from orbit_watch.settlement import Receipt, SettlementError, SettlementPlan

NOT_ON_CHAIN = "evm-testnet:not-on-chain"


class EvmTestnetAdapter:
    """Settlement on the escrow contract; implements ``SettlementAdapter``.

    ``accounts`` maps party IDs to their signing accounts. ``platform`` is the party that
    receives platform fees; its address is the escrow's fee recipient. With
    ``follow_record_time`` (local Anvil chain only) the chain's clock follows the record:
    each transaction is mined at the time of the record's last change, so a simulated
    history plays out on chain at exactly its own times.
    """

    name = "evm-testnet"

    def __init__(
        self,
        chain: OrbitWatchChain,
        accounts: Mapping[str, LocalAccount],
        *,
        platform: str,
        verifier: str = "system:verifier",
        operator: str | None = None,
        follow_record_time: bool = False,
    ):
        if follow_record_time and chain.chain_id != ANVIL_CHAIN_ID:
            raise SettlementError(
                "not_local", "following simulated time is possible only on a local Anvil chain"
            )
        self.chain = chain
        self.accounts = dict(accounts)
        self.platform = platform
        self.verifier = verifier
        self.operator = operator or verifier
        self.follow_record_time = follow_record_time
        self._by_key: dict[str, tuple[str, Receipt]] = {}
        self._settled_off_chain: set[str] = set()

    # ------------------------------------------------------------------ queries

    def balance(self, party: str) -> int:
        """What the party holds plus what it can withdraw from the escrow."""
        address = self.address(party)
        return self.chain.token_balance(address) + self.chain.owed(address)

    def escrow(self, request_id: str) -> int:
        """What the escrow holds for the request (nothing once settled)."""
        if self.chain.status(request_id) in ("None", "Settled"):
            return 0
        return self.chain.deposit(request_id)

    def address(self, party: str) -> str:
        if party == self.platform:
            return self.chain.fee_recipient
        return self._account(party).address

    # ------------------------------------------------------------------ operations

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

        def act(record: RequestRecord) -> Sent:
            split, terms = record.split, record.terms
            if split is None or split.total != points or record.terms_sha256 is None:
                raise SettlementError("invalid_amount", "the record's split does not match")
            return self.chain.fund(
                self._account(requester),
                request_id,
                {
                    "termsHash": bytes32_from_sha256(record.terms_sha256),
                    "deliveryDeadline": unix_seconds(terms.delivery_deadline),
                    "reservationSeconds": whole_seconds(terms.reservation_hours),
                    "verificationTimeoutSeconds": whole_seconds(terms.verification_timeout_hours),
                    "challengeSeconds": whole_seconds(terms.challenge_period_hours),
                    "reviewSeconds": whole_seconds(terms.review_hours),
                },
                {
                    "observerReward": split.observer,
                    "reviewerReward": split.reviewer,
                    "platformFee": split.platform_fee,
                },
            )

        return self._run(key, fingerprint, "fund", request_id, record, act)

    def reserve(
        self, request_id: str, station: str, *, key: str, record: RequestRecord | None = None
    ) -> Receipt:
        fingerprint = {"op": "reserve", "request": request_id, "station": station}
        return self._run(
            key,
            fingerprint,
            "reserve",
            request_id,
            record,
            lambda _: self.chain.reserve(self._account(station), request_id),
        )

    def deliver(
        self,
        request_id: str,
        station: str,
        delivery_sha256: str,
        *,
        key: str,
        record: RequestRecord | None = None,
    ) -> Receipt:
        fingerprint = {
            "op": "deliver",
            "request": request_id,
            "station": station,
            "delivery": delivery_sha256,
        }
        return self._run(
            key,
            fingerprint,
            "deliver",
            request_id,
            record,
            lambda _: self.chain.deliver(
                self._account(station), request_id, bytes32_from_sha256(delivery_sha256)
            ),
        )

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
        if kind == "automated_verification":
            act = self._result(request_id, attester, subject_sha256, value)
        elif kind == "review_vote":
            act = self._vote(request_id, attester, subject_sha256, value)
        else:
            raise SettlementError("invalid_attestation", f"unknown attestation kind {kind!r}")
        return self._run(key, fingerprint, "attest", request_id, record, act)

    def challenge(
        self,
        request_id: str,
        party: str,
        reason: str,
        *,
        key: str,
        record: RequestRecord | None = None,
    ) -> Receipt:
        fingerprint = {"op": "challenge", "request": request_id, "party": party, "reason": reason}

        def act(record: RequestRecord) -> Sent:
            sent = self.chain.challenge(self._account(party), request_id, sha256_of_text(reason))
            self._check_round(request_id, record)
            return sent

        return self._run(key, fingerprint, "challenge", request_id, record, act)

    def settle(
        self, plan: SettlementPlan, *, key: str, record: RequestRecord | None = None
    ) -> Receipt:
        fingerprint = {"op": "settle", "plan": plan.to_document()}
        if plan.deposit == 0:  # an unfunded request: nothing on chain, settled once here
            if key not in self._by_key and plan.request_id in self._settled_off_chain:
                raise SettlementError(
                    "already_settled", f"request {plan.request_id} was already settled"
                )
            receipt = self._run(key, fingerprint, "settle", plan.request_id, record, None)
            self._settled_off_chain.add(plan.request_id)
            return receipt

        def act(_: RequestRecord) -> Sent:
            self._refuse_if_settled(plan.request_id)
            sent = self.chain.settle(self._account(self.operator), plan.request_id)
            self._check_credits(
                sent, [(p.party, p.points, p.reason) for p in plan.payouts], plan.request_id
            )
            return sent

        return self._run(key, fingerprint, "settle", plan.request_id, record, act)

    def refund(
        self, request_id: str, requester: str, *, key: str, record: RequestRecord | None = None
    ) -> Receipt:
        fingerprint = {"op": "refund", "request": request_id, "requester": requester}

        def act(record: RequestRecord) -> Sent:
            self._refuse_if_settled(request_id)
            deposit = self.chain.deposit(request_id)
            # The lifecycle says why: a cancellation is the requester's own call, an expiry
            # is settled like any outcome.
            if record.status is Status.CANCELLED:
                sent = self.chain.cancel(self._account(requester), request_id)
            elif record.status is Status.EXPIRED:
                sent = self.chain.settle(self._account(self.operator), request_id)
            else:
                raise SettlementError(
                    "not_refundable", f"a request that is {record.status} is not refunded"
                )
            self._check_credits(sent, [(requester, deposit, "refund")], request_id)
            return sent

        return self._run(key, fingerprint, "refund", request_id, record, act)

    # ------------------------------------------------------------------ attestations

    def _result(self, request_id: str, attester: str, report_sha256: str, verdict: str):
        if attester != self.verifier:
            raise SettlementError("not_the_verifier", f"{attester} is not the verifier")

        def act(record: RequestRecord) -> Sent:
            if record.delivery_sha256 is None or record.observer is None:
                raise SettlementError("not_delivered", f"request {request_id} has no delivery")
            method, _, version = record.terms.verification_method.rpartition(" ")
            sent = self.chain.attest_result(
                self._account(attester),
                request_id,
                delivery_sha256=bytes32_from_sha256(record.delivery_sha256),
                report_sha256=bytes32_from_sha256(report_sha256),
                verdict=verdict,
                method=method or record.terms.verification_method,
                method_version=version,
                observer=self.address(record.observer),
            )
            if verdict == "inconclusive":
                self._check_round(request_id, record)
            return sent

        return act

    def _vote(self, request_id: str, reviewer: str, delivery_sha256: str, value: str):
        if value not in ("approve", "reject"):
            raise SettlementError("invalid_attestation", f"a vote is approve or reject: {value!r}")

        def act(record: RequestRecord) -> Sent:
            reasons = dict(record.vote_reasons)
            on_chain = self.chain.request(request_id)
            return self.chain.attest_vote(
                self._account(reviewer),
                request_id,
                delivery_sha256=bytes32_from_sha256(delivery_sha256),
                approve=value == "approve",
                reason_sha256=sha256_of_text(reasons.get(reviewer, "")),
                observer=on_chain["station"],
                result_attestation=on_chain["resultAttestation"],
            )

        return act

    # ------------------------------------------------------------------ checks

    def _check_round(self, request_id: str, record: RequestRecord) -> None:
        """The reviewers the escrow chose must be the record's reviewers. (In step 2.6 the
        service takes the round from the chain instead.)"""
        chosen = set(self.chain.request(request_id)["reviewers"])
        expected = {self.address(reviewer) for reviewer in record.reviewers}
        if chosen != expected:
            raise SettlementError(
                "reviewers_differ",
                f"the escrow chose {sorted(chosen)}, the record has {sorted(expected)}",
            )

    def _check_credits(
        self, sent: Sent, expected: list[tuple[str, int, str]], request_id: str
    ) -> None:
        """The chain's payouts must equal the shared rules' plan, payout by payout."""
        paid = sorted((c.party, c.amount, c.reason) for c in self.chain.credits(sent))
        planned = sorted((self.address(p), amount, reason) for p, amount, reason in expected)
        if paid != planned:
            raise SettlementError(
                "chain_disagrees",
                f"request {request_id}: the escrow paid {paid}, the rules say {planned}",
            )

    def _refuse_if_settled(self, request_id: str) -> None:
        if self.chain.status(request_id) == "Settled":
            raise SettlementError("already_settled", f"request {request_id} was already settled")

    # ------------------------------------------------------------------ internals

    def _account(self, party: str) -> LocalAccount:
        try:
            return self.accounts[party]
        except KeyError:
            raise SettlementError("no_account", f"no signing account for {party}") from None

    def _run(
        self,
        key: str,
        fingerprint: dict[str, Any],
        operation: str,
        request_id: str,
        record: RequestRecord | None,
        act: Any,
    ) -> Receipt:
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
        if record is None:
            raise SettlementError(
                "record_required", f"the {self.name} adapter needs the lifecycle record"
            )
        if act is None or not record.funded_points:  # unfunded requests stay off chain
            receipt = Receipt(key, operation, request_id, NOT_ON_CHAIN)
        else:
            if self.follow_record_time:
                self.chain.travel_to(unix_seconds(record.updated_at))
            try:
                sent = act(record)
            except ChainError as error:
                raise SettlementError(error.code, str(error)) from None
            receipt = Receipt(
                key,
                operation,
                request_id,
                sent.tx_hash,
                (("chain_id", self.chain.chain_id), ("block", sent.block)),
            )
        self._by_key[key] = (digest, receipt)
        return receipt

"""The request service on a testnet chain (phase 2, step 2.6).

**Testnet only** (Base Sepolia or a local Anvil chain). With a ``ChainLink`` the service
works with the escrow contract instead of the points ledger, for every funded request:

* **The parties sign** (decision P2-09). A party's action on a funded request is prepared
  as unsigned transactions, which the party signs with its own wallet and sends itself.
  No party key ever reaches the service. What stays off chain goes to the service: the
  observation file, and the text of challenge and vote reasons (by their SHA-256).
* **The chain decides** (decision P2-10). The service follows the escrow's events and
  applies each to the request's lifecycle record at its block's time, transaction by
  transaction. A request is on chain from a ``Funded`` event that matches its terms, its
  split and its requester's wallet; anything that does not fit is shown as a conflict and
  never applied.
* **The service holds one key**, the verifier key: it attests automated results and
  settles requests whose outcome is reached (anyone may settle, P2-05).
* **Transactions** that parties report and that the service sends are shown as pending,
  confirmed or failed, with block explorer links.

Unfunded requests never touch the chain and work as in phase 1 (decision D-19).
"""

from __future__ import annotations

import contextlib
import re
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

from eth_account import Account
from eth_account.messages import encode_defunct
from eth_account.signers.local import LocalAccount
from eth_utils import is_address, to_checksum_address

from orbit_watch import lifecycle as lc
from orbit_watch.canonical import sha256_bytes
from orbit_watch.chain import (
    ANVIL_CHAIN_ID,
    CREDIT_REASONS,
    EXPLORERS,
    STATUSES,
    SUPPORTED_CHAINS,
    WALLET_PREFIX,
    ChainError,
    bytes32_from_sha256,
    explorer_link,
    notice,
    request_key,
    sha256_of_text,
    snake_case,
    unix_seconds,
    wallet_message,
    whole_seconds,
)
from orbit_watch.chain.client import VERDICTS, Call, Event, OrbitWatchChain
from orbit_watch.lifecycle import RequestRecord, Status, TransitionError
from orbit_watch.service import VERIFIER, ServiceError
from orbit_watch.settlement import settlement_plan
from orbit_watch.timeutil import format_utc

if TYPE_CHECKING:  # pragma: no cover
    from orbit_watch.service import RequestService

LOG_CHUNK = 2000  # blocks per eth_getLogs call; public RPC endpoints limit the range
ZERO_ADDRESS = "0x" + "00" * 20
_TX_HASH = re.compile(r"0x[0-9a-fA-F]{64}")
# The escrow's own events that belong to another event of the same transaction.
_FOLLOWERS = ("ReviewStarted", "Credited", "Withdrawn")


@dataclass(frozen=True)
class Prepared:
    """Transactions a party signs with its own wallet, in order."""

    request_id: str | None
    action: str
    transactions: tuple[tuple[str, dict[str, Any]], ...]  # (action, unsigned transaction)
    notice: str

    def to_document(self) -> dict[str, Any]:
        return {
            "request_id": self.request_id,
            "action": self.action,
            "sign": [
                {"action": action, "transaction": transaction}
                for action, transaction in self.transactions
            ],
            "notice": self.notice,
            "next": "Sign and send each transaction in order with your own wallet, then "
            "report its hash (POST /v1/transactions). Nothing changes until the chain "
            "confirms it.",
        }


def _at(seconds: int) -> datetime:
    return datetime.fromtimestamp(seconds, tz=UTC)


class ChainLink:
    """Puts a stored ``RequestService`` on the chain of ``chain`` (see the module text).

    ``verifier`` is the service's only key and must be the escrow's verifier. The service
    reads the chain from ``from_block`` (the escrow's deployment block) and waits up to
    ``receipt_timeout`` seconds for a transaction before calling it pending.
    """

    def __init__(
        self,
        chain: OrbitWatchChain,
        verifier: LocalAccount,
        *,
        from_block: int = 0,
        receipt_timeout: float = 60.0,
    ):
        if verifier.address != chain.verifier:
            raise ChainError(
                "not_the_verifier",
                f"the verifier key is {verifier.address}, the escrow's verifier is "
                f"{chain.verifier}",
            )
        self.chain = chain
        self.verifier = verifier
        self.from_block = from_block
        self.receipt_timeout = receipt_timeout
        self.notice = notice(chain.chain_id)
        self._service: RequestService | None = None
        self._token: dict[str, Any] | None = None

    # ------------------------------------------------------------------ set-up

    def attach(self, service: RequestService) -> None:
        """Bind to ``service``. A service directory follows one escrow on one chain, from
        its first start; a directory started without a chain cannot move onto one."""
        if service.storage is None:
            raise ValueError("the chain needs a stored service (open_service)")
        self._service = service
        settings = self._settings()
        wanted = {"chain_id": str(self.chain.chain_id), "escrow": self.chain.escrow.address}
        if not settings:
            if service.records:
                raise ChainError(
                    "not_a_chain_service",
                    "this service directory was started without a chain; use a new one",
                )
            with self.db.transaction():
                for name, value in {**wanted, "synced_block": str(self.from_block - 1)}.items():
                    self.db.execute(
                        "INSERT INTO chain_settings (name, value) VALUES (?, ?)", (name, value)
                    )
            return
        for name, value in wanted.items():
            if settings.get(name) != value:
                raise ChainError(
                    "other_chain",
                    f"this service directory follows {name} {settings.get(name)}, not {value}",
                )

    @property
    def service(self) -> RequestService:
        if self._service is None:  # pragma: no cover - attach() is always called first
            raise RuntimeError("the chain link is not attached to a service")
        return self._service

    @property
    def db(self) -> Any:
        assert self.service.storage is not None
        return self.service.storage.db

    def _settings(self) -> dict[str, str]:
        return {r["name"]: r["value"] for r in self.db.query("SELECT * FROM chain_settings")}

    def now(self) -> datetime:
        """The chain's clock: the latest block's time."""
        return _at(self.chain.now())

    # ------------------------------------------------------------------ wallets

    def wallet(self, party: str) -> str | None:
        rows = self.db.query("SELECT address FROM wallets WHERE party = ?", (party,))
        return rows[0]["address"] if rows else None

    def party_of(self, address: str) -> str:
        """The party whose wallet ``address`` is, or ``wallet:<address>`` if none is."""
        address = to_checksum_address(address)
        rows = self.db.query("SELECT party FROM wallets WHERE address = ?", (address,))
        return rows[0]["party"] if rows else WALLET_PREFIX + address

    def address_of(self, party: str) -> str | None:
        if party.startswith(WALLET_PREFIX):
            return to_checksum_address(party[len(WALLET_PREFIX) :])
        if party == self.service.platform:
            return self.chain.fee_recipient
        return self.wallet(party)

    def wallet_view(self, party: str) -> dict[str, Any]:
        return {
            "party": party,
            "address": self.wallet(party),
            "message": wallet_message(party, self.chain.chain_id, self.chain.escrow.address),
            "notice": self.notice,
        }

    def register_wallet(
        self, party: str, address: str, signature: str, now: datetime
    ) -> dict[str, Any]:
        """Register ``address`` for ``party``, proven by an EIP-191 signature of
        ``wallet_message``. Once set, a party's wallet does not change."""
        if not isinstance(address, str) or not is_address(address):
            raise ServiceError("invalid_address", f"not an address: {address!r}")
        address = to_checksum_address(address)
        message = wallet_message(party, self.chain.chain_id, self.chain.escrow.address)
        try:
            signer = Account.recover_message(encode_defunct(text=message), signature=signature)
        except Exception:  # any malformed signature
            signer = None
        if signer != address:
            raise ServiceError(
                "bad_signature", f"the signature is not {address}'s signature of: {message}"
            )
        existing = self.wallet(party)
        if existing == address:
            return self.wallet_view(party)
        if existing is not None:
            raise ServiceError("wallet_already_set", f"{party} already has the wallet {existing}")
        if address in (self.chain.verifier, self.chain.fee_recipient):
            raise ServiceError("address_taken", f"{address} is one of Orbit Watch's own")
        owner = self.party_of(address)
        if not owner.startswith(WALLET_PREFIX):
            raise ServiceError("address_taken", f"{address} is already {owner}'s wallet")
        self.db.execute(
            "INSERT INTO wallets (party, address, signature, registered_at) VALUES (?, ?, ?, ?)",
            (party, address, signature, format_utc(now)),
        )
        return self.wallet_view(party)

    def _wallet_required(self, party: str) -> str:
        address = self.wallet(party)
        if address is None:
            raise ServiceError(
                "no_wallet",
                f"{party} has no wallet yet: register one first (orbit-watch wallet register)",
            )
        return address

    # ------------------------------------------------------------------ preparing

    def on_chain(self, request_id: str) -> bool:
        """Whether the request was funded on chain (and so lives there from now on)."""
        return bool(
            self.db.query(
                "SELECT 1 FROM chain_events WHERE request_id = ? AND event = 'Funded'",
                (request_id,),
            )
        )

    def _check(self, record: RequestRecord, event: lc.Event) -> None:
        """Refuse at once what the lifecycle would refuse when the chain confirms it."""
        try:
            lc.apply(record, event)
        except TransitionError as error:
            raise ServiceError(error.code, str(error)) from None

    def _prepared(self, request_id: str | None, action: str, sender: str, *calls) -> Prepared:
        return Prepared(
            request_id,
            action,
            tuple((name, self.chain.unsigned(sender, call)) for name, call in calls),
            self.notice,
        )

    def chain_terms(self, record: RequestRecord) -> dict[str, Any]:
        terms = record.terms
        if record.terms_sha256 is None:
            raise ServiceError("forbidden_in_status", "the request is not open yet")
        try:
            return {
                "termsHash": bytes32_from_sha256(record.terms_sha256),
                "deliveryDeadline": unix_seconds(terms.delivery_deadline),
                "reservationSeconds": whole_seconds(terms.reservation_hours),
                "verificationTimeoutSeconds": whole_seconds(terms.verification_timeout_hours),
                "challengeSeconds": whole_seconds(terms.challenge_period_hours),
                "reviewSeconds": whole_seconds(terms.review_hours),
            }
        except ValueError as error:
            raise ServiceError("invalid_terms", f"on chain, {error}") from None

    def prepare_fund(
        self, request_id: str, party: str, split: lc.RewardSplit, now: datetime
    ) -> Prepared:
        record = self.service._record(request_id)
        self._check(record, lc.Fund(now, split))
        sender = self._wallet_required(party)
        if self.chain.status(request_id) != "None":
            raise ServiceError(
                "already_on_chain",
                f"request ID {request_id} is already funded on chain, not through this "
                "request: create the request again under a new ID",
            )
        if split.platform_fee and self.chain.fee_recipient == ZERO_ADDRESS:
            raise ServiceError("fee_without_recipient", "this escrow takes no platform fee")
        held = self.chain.token_balance(sender)
        if held < split.total:
            token = self.token()
            raise ServiceError(
                "insufficient_balance",
                f"{sender} holds {held} and the deposit is {split.total} (in units of "
                f"{token['symbol']}, {token['decimals']} decimals): get testnet tokens from "
                "the faucet first",
            )
        terms = self.chain_terms(record)
        split_on_chain = {
            "observerReward": split.observer,
            "reviewerReward": split.reviewer,
            "platformFee": split.platform_fee,
        }
        return self._prepared(
            request_id,
            "fund",
            sender,
            ("approve", self.chain.approve_call(split.total)),
            ("fund", self.chain.fund_call(request_id, terms, split_on_chain)),
        )

    def prepare_cancel(self, request_id: str, party: str, now: datetime) -> Prepared:
        record = self.service._record(request_id)
        self._check(record, lc.Cancel(now, party))
        sender = self._wallet_required(party)
        return self._prepared(
            request_id, "cancel", sender, ("cancel", self.chain.cancel_call(request_id))
        )

    def prepare_reserve(self, request_id: str, station: str, now: datetime) -> Prepared:
        record = self.service._record(request_id)
        self._check(record, lc.Reserve(now, station))
        sender = self._wallet_required(station)
        return self._prepared(
            request_id, "reserve", sender, ("reserve", self.chain.reserve_call(request_id))
        )

    def prepare_delivery(
        self,
        request_id: str,
        station: str,
        observations: bytes,
        now: datetime,
        observations_format: str | None,
    ) -> Prepared | None:
        """Keep the file and prepare ``deliver`` with its SHA-256. If the station already
        delivered this file on chain, verification runs at once and nothing is to sign."""
        record = self.service._record(request_id)
        digest = sha256_bytes(observations)
        current = lc.advance(record, now)
        delivered_already = (
            current.status is Status.DELIVERED
            and current.observer == station
            and current.delivery_sha256 == digest
        )
        if not delivered_already:
            self._check(record, lc.Deliver(now, station, digest))
        sender = self._wallet_required(station)
        self.service._store(observations)
        self.db.execute(
            "INSERT INTO chain_uploads (request_id, sha256, station, format) VALUES (?, ?, ?, ?) "
            "ON CONFLICT (request_id, sha256) DO UPDATE SET format = excluded.format",
            (request_id, digest, station, observations_format),
        )
        if delivered_already:
            self.follow_up()
            return None
        return self._prepared(
            request_id,
            "deliver",
            sender,
            ("deliver", self.chain.deliver_call(request_id, bytes32_from_sha256(digest))),
        )

    def _keep_text(self, text: str) -> bytes:
        digest = sha256_of_text(text)
        self.db.execute(
            "INSERT INTO chain_texts (sha256, text) VALUES (?, ?) ON CONFLICT DO NOTHING",
            (digest.hex(), text),
        )
        return digest

    def prepare_challenge(
        self, request_id: str, party: str, reason: str, now: datetime
    ) -> Prepared:
        record = lc.advance(self.service._record(request_id), now)
        if record.status is not Status.CHALLENGE_PERIOD:
            raise ServiceError(
                "forbidden_in_status",
                f"'challenge' is not allowed when the request is {record.status}",
            )
        if party not in (record.requester, record.observer):
            raise ServiceError("not_a_party", "only the requester or the observer can challenge")
        sender = self._wallet_required(party)
        digest = self._keep_text(reason)
        return self._prepared(
            request_id,
            "challenge",
            sender,
            ("challenge", self.chain.challenge_call(request_id, digest)),
        )

    def prepare_vote(
        self, request_id: str, reviewer: str, approve: bool, reason: str, now: datetime
    ) -> Prepared:
        record = self.service._record(request_id)
        self._check(record, lc.Vote(now, reviewer, approve, reason))
        sender = self._wallet_required(reviewer)
        digest = self._keep_text(reason)
        on = self.chain.request(request_id)
        call = self.chain.vote_call(
            request_id,
            delivery_sha256=on["deliverySha256"],
            approve=approve,
            reason_sha256=digest,
            observer=on["station"],
            result_attestation=on["resultAttestation"],
        )
        return self._prepared(request_id, "vote", sender, ("attest_vote", call))

    def prepare_withdraw(self, party: str) -> Prepared:
        sender = self._wallet_required(party)
        if self.chain.owed(sender) == 0:
            raise ServiceError("nothing_to_withdraw", f"{party} has nothing to withdraw")
        return self._prepared(None, "withdraw", sender, ("withdraw", self.chain.withdraw_call()))

    # ------------------------------------------------------------------ transactions

    def report(
        self, party: str, tx_hash: str, now: datetime, *, admin: bool = False
    ) -> dict[str, Any]:
        """Watch a transaction a party sent with its own wallet; apply it once mined."""
        if not isinstance(tx_hash, str) or not _TX_HASH.fullmatch(tx_hash):
            raise ServiceError("invalid_tx_hash", f"not a transaction hash: {tx_hash!r}")
        tx_hash = tx_hash.lower()
        transaction = self.chain.transaction(tx_hash)
        if transaction is None:
            raise ServiceError(
                "unknown_transaction", f"the chain does not know transaction {tx_hash}"
            )
        sender = to_checksum_address(transaction["from"])
        if not admin and sender != self.wallet(party):
            raise ServiceError(
                "not_your_transaction", f"{tx_hash} was sent by {sender}, not by your wallet"
            )
        action, key = self.chain.describe(transaction)
        if action == "other":
            raise ServiceError(
                "not_orbit_watch", f"{tx_hash} is not a call to the escrow, EAS or the token"
            )
        request_id = self._request_ids().get(key) if key else None
        self._track(tx_hash, self.party_of(sender), action, request_id, now)
        self._refresh(tx_hash, wait=self.receipt_timeout)
        self.sync()
        self.follow_up()
        return self.transaction_view(tx_hash)

    def _track(
        self, tx_hash: str, party: str, action: str, request_id: str | None, now: datetime
    ) -> None:
        self.db.execute(
            "INSERT INTO transactions (tx_hash, party, action, request_id, status, reported_at) "
            "VALUES (?, ?, ?, ?, 'pending', ?) ON CONFLICT (tx_hash) DO NOTHING",
            (tx_hash, party, action, request_id, format_utc(now)),
        )

    def _refresh(self, tx_hash: str, wait: float = 0) -> None:
        """Update a watched transaction from the chain."""
        if wait:
            # Pending or failed: the receipt below tells which.
            with contextlib.suppress(ChainError):
                self.chain.wait(tx_hash, timeout=wait)
        receipt = self.chain.receipt(tx_hash)
        if receipt is None:
            return
        status = "confirmed" if receipt["status"] == 1 else "failed"
        error = None if status == "confirmed" else self._why_failed(tx_hash, receipt)
        self.db.execute(
            "UPDATE transactions SET status = ?, block = ?, error = ? WHERE tx_hash = ?",
            (status, receipt["blockNumber"], error, tx_hash),
        )

    def _why_failed(self, tx_hash: str, receipt: Any) -> str:
        """Best effort: replay the failed call just before its block for the error."""
        from web3.exceptions import ContractLogicError

        transaction = self.chain.transaction(tx_hash)
        call = {key: transaction[key] for key in ("from", "to", "input", "value")}
        call["data"] = call.pop("input")
        try:
            self.chain.w3.eth.call(call, receipt["blockNumber"] - 1)
        except ContractLogicError as error:
            return str(self.chain.decode_error(error).code)
        except Exception:  # a node that cannot replay
            return "transaction_failed"
        return "transaction_failed"

    def _send_own(self, action: str, request_id: str, call: Call) -> str | None:
        """Send one of the service's own transactions, signed by the verifier key."""
        try:
            tx_hash = self.chain.submit(self.verifier, call)
        except ChainError as error:
            # One row per action and request, however often it is retried.
            self._conflict(
                f"service:{action}:{request_id}", -1, request_id, error.code, f"refused: {error}"
            )
            return None
        self._track(tx_hash, VERIFIER, action, request_id, self.now())
        self._refresh(tx_hash, wait=self.receipt_timeout)
        return tx_hash

    def _pending(self, request_id: str, action: str) -> bool:
        return bool(
            self.db.query(
                "SELECT 1 FROM transactions WHERE request_id = ? AND action = ? "
                "AND status = 'pending'",
                (request_id, action),
            )
        )

    # ------------------------------------------------------------------ following the chain

    def _request_ids(self) -> dict[str, str]:
        return {request_key(rid).hex(): rid for rid in self.service.records}

    def sync(self) -> list[str]:
        """Apply the escrow's new events to the requests they belong to. Returns the IDs of
        the requests that changed."""
        latest = self.chain.latest_block()
        start = int(self._settings()["synced_block"]) + 1
        changed: list[str] = []
        try:
            with self.db.transaction():
                for row in self.db.query(
                    "SELECT tx_hash FROM transactions WHERE status = 'pending'"
                ):
                    self._refresh(row["tx_hash"])
                if start > latest:
                    return changed
                ids = self._request_ids()
                while start <= latest:
                    end = min(latest, start + LOG_CHUNK - 1)
                    changed += self._mirror(self.chain.events(start, end), ids)
                    start = end + 1
                self.db.execute(
                    "UPDATE chain_settings SET value = ? WHERE name = 'synced_block'",
                    (str(latest),),
                )
        except BaseException:
            self.service._reload()
            raise
        return sorted(set(changed))

    def _mirror(self, events: list[Event], ids: dict[str, str]) -> list[str]:
        changed = []
        for index, event in enumerate(events):
            if event.name in _FOLLOWERS:
                continue
            request_id = ids.get(event.args["requestId"].hex())
            if request_id is None:  # another user of the same escrow
                continue
            if event.name != "Funded" and not self.on_chain(request_id):
                continue  # funded by someone else: the Funded conflict says so
            group = [
                e
                for e in events[index + 1 :]
                if e.tx_hash == event.tx_hash and e.args.get("requestId") == event.args["requestId"]
            ]
            at = _at(self.chain.block_time(event.block))
            handler = getattr(self, "_on_" + snake_case(event.name))
            try:
                handler(request_id, event, group, at)
            except (TransitionError, ServiceError, ChainError) as error:
                self._conflict(event.tx_hash, event.log_index, request_id, error.code, str(error))
                continue
            self.db.execute(
                "INSERT INTO chain_events (tx_hash, log_index, block, request_id, event, at) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (
                    event.tx_hash,
                    event.log_index,
                    event.block,
                    request_id,
                    event.name,
                    format_utc(at),
                ),
            )
            changed.append(request_id)
        return changed

    def _conflict(
        self, tx_hash: str, log_index: int, request_id: str, code: str, message: str
    ) -> None:
        self.db.execute(
            "INSERT INTO chain_conflicts (tx_hash, log_index, request_id, code, message) "
            "VALUES (?, ?, ?, ?, ?) ON CONFLICT DO NOTHING",
            (tx_hash, log_index, request_id, code, message),
        )

    def _apply(self, request_id: str, event: lc.Event) -> RequestRecord:
        record = lc.apply(self.service.records[request_id], event)
        return self.service._save_record(record)

    def _text(self, digest: bytes) -> str:
        """A reason by its SHA-256, or a note that only the hash is known (a party that
        challenged or voted on chain without giving Orbit Watch the text)."""
        rows = self.db.query("SELECT text FROM chain_texts WHERE sha256 = ?", (digest.hex(),))
        return (
            rows[0]["text"]
            if rows
            else f"(reason not given to Orbit Watch; SHA-256 {digest.hex()})"
        )

    def _round(self, group: list[Event]) -> tuple[str, ...]:
        started = next(e for e in group if e.name == "ReviewStarted")
        return tuple(self.party_of(address) for address in started.args["reviewers"])

    def _on_funded(self, request_id: str, event: Event, group: list[Event], at: datetime) -> None:
        record = self.service.records[request_id]
        problems = []
        if to_checksum_address(event.args["requester"]) != self.wallet(record.requester):
            problems.append(f"funded by {event.args['requester']}, not by the requester's wallet")
        if record.terms_sha256 is None:
            problems.append("the request was not open")
        else:
            on = self.chain.request(request_id)
            if any(on[name] != value for name, value in self.chain_terms(record).items()):
                problems.append("funded with other terms")
        if problems:
            raise ServiceError("foreign_funding", "; ".join(problems))
        split = lc.RewardSplit(on["observerReward"], on["reviewerReward"], on["platformFee"])
        self._apply(request_id, lc.Fund(at, split))

    def _on_cancelled(
        self, request_id: str, event: Event, group: list[Event], at: datetime
    ) -> None:
        self._apply(request_id, lc.Cancel(at, self.service.records[request_id].requester))

    def _on_reserved(self, request_id: str, event: Event, group: list[Event], at: datetime) -> None:
        self._apply(request_id, lc.Reserve(at, self.party_of(event.args["station"])))

    def _on_delivered(
        self, request_id: str, event: Event, group: list[Event], at: datetime
    ) -> None:
        station = self.party_of(event.args["station"])
        self._apply(request_id, lc.Deliver(at, station, event.args["deliverySha256"].hex()))

    def _on_verification_recorded(
        self, request_id: str, event: Event, group: list[Event], at: datetime
    ) -> None:
        verdict = VERDICTS[event.args["verdict"]]
        fields = self.chain.attestation(event.args["attestation"])["fields"]
        reviewers = self._round(group) if verdict == "inconclusive" else ()
        record = self._apply(
            request_id,
            lc.RecordVerification(at, verdict, fields["reportSha256"].hex(), reviewers),
        )
        if record.status is Status.IN_REVIEW:
            self.service._assign(request_id, at)

    def _on_challenged(
        self, request_id: str, event: Event, group: list[Event], at: datetime
    ) -> None:
        party = self.party_of(event.args["challenger"])
        reason = self._text(event.args["reasonSha256"])
        self._apply(request_id, lc.Challenge(at, party, self._round(group), reason))
        self.service._assign(request_id, at)

    def _on_voted(self, request_id: str, event: Event, group: list[Event], at: datetime) -> None:
        record = self.service.records[request_id]
        address = to_checksum_address(event.args["reviewer"])
        reviewer = next((r for r in record.reviewers if self.address_of(r) == address), None)
        if reviewer is None:
            raise ServiceError("not_assigned", f"{address} is not a reviewer of this round")
        fields = self.chain.attestation(event.args["attestation"])["fields"]
        reason = self._text(fields["reasonSha256"])
        self._apply(request_id, lc.Vote(at, reviewer, event.args["approve"], reason))

    def _on_settled(self, request_id: str, event: Event, group: list[Event], at: datetime) -> None:
        record = lc.advance(self.service.records[request_id], at)
        outcome = STATUSES[event.args["outcome"]].lower()
        if record.status not in lc.OUTCOMES or str(record.status) != outcome:
            raise ServiceError(
                "chain_disagrees", f"the escrow settled {outcome}, the record is {record.status}"
            )
        plan = settlement_plan(record, platform=self.service.platform)
        planned = sorted(
            (self.address_of(p.party), p.points, p.reason) for p in plan.payouts if p.points
        )
        paid = sorted(
            (
                to_checksum_address(e.args["party"]),
                e.args["amount"],
                CREDIT_REASONS[e.args["reason"]],
            )
            for e in group
            if e.name == "Credited"
        )
        if paid != planned:
            raise ServiceError(
                "chain_disagrees", f"the escrow paid {paid}, the rules say {planned}"
            )
        self.service._save_record(record)
        self.service._save_settlement(
            request_id, {"plan": plan.to_document(), "reference": event.tx_hash}
        )
        self._apply(request_id, lc.Settle(at))

    # ------------------------------------------------------------------ the service's own work

    def follow_up(self) -> list[str]:
        """Do the service's own part on chain: attest the automated result of every delivery
        whose file it holds, and settle every request whose outcome is reached. Returns the
        hashes of the transactions it sent."""
        self.sync()
        now = self.now()
        sent = []
        for request_id in sorted(self.service.records):
            record = self.service.records[request_id]
            if record.status is Status.SETTLED or not self.on_chain(request_id):
                continue
            current = lc.advance(record, now)
            tx_hash = None
            if current.status is Status.DELIVERED and not self._pending(
                request_id, "attest_result"
            ):
                tx_hash = self._attest_result(request_id, current)
            elif (
                current.status in lc.OUTCOMES
                and current.status is not Status.CANCELLED
                and not self._pending(request_id, "settle")
                and self.chain.status(request_id) != "Settled"
            ):
                tx_hash = self._send_own("settle", request_id, self.chain.settle_call(request_id))
            if tx_hash:
                sent.append(tx_hash)
        if sent:
            self.sync()
        return sent

    def _attest_result(self, request_id: str, record: RequestRecord) -> str | None:
        rows = self.db.query(
            "SELECT * FROM chain_uploads WHERE request_id = ? AND sha256 = ?",
            (request_id, record.delivery_sha256),
        )
        if not rows:  # the station has not uploaded the file it delivered
            return None
        delivered = self.service.deliveries.get(request_id)
        if delivered is None:
            delivered = self.service._verify(
                request_id,
                rows[0]["station"],
                self.service.files[rows[0]["sha256"]],
                rows[0]["format"],
            )
        method, _, version = record.terms.verification_method.rpartition(" ")
        observer = self.address_of(record.observer or "")
        call = self.chain.result_call(
            request_id,
            delivery_sha256=bytes32_from_sha256(delivered.observations_sha256),
            report_sha256=bytes32_from_sha256(delivered.report_sha256),
            verdict=delivered.verdict,
            method=method or record.terms.verification_method,
            method_version=version,
            observer=observer or ZERO_ADDRESS,
        )
        return self._send_own("attest_result", request_id, call)

    # ------------------------------------------------------------------ views

    def token(self) -> dict[str, Any]:
        if self._token is None:
            self._token = self.chain.token_info()
        return self._token

    def info(self) -> dict[str, Any]:
        chain = self.chain
        return {
            "chain_id": chain.chain_id,
            "network": SUPPORTED_CHAINS[chain.chain_id],
            "notice": self.notice,
            "escrow": chain.escrow.address,
            "token": self.token(),
            "eas": chain.eas.address,
            "result_schema": "0x" + chain.result_schema.hex(),
            "vote_schema": "0x" + chain.vote_schema.hex(),
            "verifier": chain.verifier,
            "fee_recipient": chain.fee_recipient,
            "explorer": EXPLORERS.get(chain.chain_id),
            "local": chain.chain_id == ANVIL_CHAIN_ID,
            "synced_block": int(self._settings()["synced_block"]),
        }

    def balance(self, party: str) -> dict[str, Any]:
        address = self.address_of(party)
        return {
            "party": party,
            "address": address,
            "balance": None if address is None else self.chain.token_balance(address),
            "withdrawable": None if address is None else self.chain.owed(address),
            "token": self.token(),
            "notice": self.notice,
        }

    def transaction_view(self, tx_hash: str) -> dict[str, Any]:
        row = self.db.query("SELECT * FROM transactions WHERE tx_hash = ?", (tx_hash,))[0]
        return self._row_view(row)

    def _row_view(self, row: Any) -> dict[str, Any]:
        return {
            "tx_hash": row["tx_hash"],
            "party": row["party"],
            "action": row["action"],
            "request_id": row["request_id"],
            "status": row["status"],
            "block": row["block"],
            "error": row["error"],
            "explorer": explorer_link(self.chain.chain_id, row["tx_hash"]),
        }

    def transactions(
        self, party: str | None = None, request_id: str | None = None
    ) -> list[dict[str, Any]]:
        sql, args = "SELECT * FROM transactions WHERE 1 = 1", []
        if party is not None:
            sql += " AND party = ?"
            args.append(party)
        if request_id is not None:
            sql += " AND request_id = ?"
            args.append(request_id)
        rows = self.db.query(sql + " ORDER BY reported_at, tx_hash", tuple(args))
        return [self._row_view(row) for row in rows]

    def request_view(self, request_id: str) -> dict[str, Any]:
        on_chain = self.on_chain(request_id)
        events = self.db.query(
            "SELECT * FROM chain_events WHERE request_id = ? ORDER BY block, log_index",
            (request_id,),
        )
        conflicts = self.db.query(
            "SELECT * FROM chain_conflicts WHERE request_id = ? ORDER BY rowid", (request_id,)
        )
        return {
            "on_chain": on_chain,
            "key": "0x" + request_key(request_id).hex(),
            "status": self.chain.status(request_id) if on_chain else None,
            "token": self.token(),
            "events": [
                {
                    "event": row["event"],
                    "at": row["at"],
                    "block": row["block"],
                    "tx_hash": row["tx_hash"],
                    "explorer": explorer_link(self.chain.chain_id, row["tx_hash"]),
                }
                for row in events
            ],
            "transactions": [
                t for t in self.transactions(request_id=request_id) if t["status"] != "confirmed"
            ],
            "conflicts": [
                {"code": row["code"], "message": row["message"], "tx_hash": row["tx_hash"]}
                for row in conflicts
            ],
            "notice": self.notice,
        }

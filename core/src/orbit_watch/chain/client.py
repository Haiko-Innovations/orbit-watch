"""A client for the Orbit Watch escrow, its EAS schemas and its token (phase 2, steps 2.5-2.6).

Each call to the chain is first a ``Call``: a contract, a function and its arguments. A
``Call`` can be sent, signed by an account given to the client (the service's own verifier
key, or a test account), or turned into an unsigned transaction that a party signs with its
own wallet (decision P2-09). Refused calls raise ``ChainError`` with the contract's custom
error in snake case as ``code``.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from functools import cache
from typing import Any

from eth_abi import decode as abi_decode
from eth_abi import encode as abi_encode
from eth_account.signers.local import LocalAccount
from eth_utils import function_signature_to_4byte_selector, to_checksum_address
from web3 import Web3
from web3.exceptions import ContractLogicError, TimeExhausted, TransactionNotFound
from web3.logs import DISCARD

from orbit_watch.chain import (
    ANVIL_CHAIN_ID,
    CREDIT_REASONS,
    STATUSES,
    ChainError,
    request_key,
    require_supported,
    snake_case,
)
from orbit_watch.chain.abi import EAS_ERRORS, load

ZERO_UID = b"\x00" * 32
# Blocks per eth_getLogs call to start with. Endpoints limit the range (Base's public one to
# 200 blocks), so a refused range is narrowed to the limit the endpoint names, or halved.
LOG_CHUNK = 2000
MIN_LOG_CHUNK = 10
NO_EXPIRATION = 0
VERDICTS = ("none", "pass", "fail", "inconclusive")  # the escrow's Verdict enum
RESULT_FIELDS = ["string", "bytes32", "bytes32", "string", "string", "string"]
VOTE_FIELDS = ["string", "bytes32", "bool", "bytes32"]


@dataclass(frozen=True)
class Credit:
    """One payout credited by a settlement (a ``Credited`` event)."""

    party: str  # checksum address
    amount: int
    reason: str  # "observer_reward", "review", "platform_fee" or "refund"


@dataclass(frozen=True)
class Sent:
    """A mined transaction."""

    tx_hash: str
    block: int
    receipt: Any


@dataclass(frozen=True)
class Call:
    """One contract function call, not yet signed."""

    contract: Any  # a web3 contract
    function: str
    args: tuple[Any, ...] = ()

    def bound(self) -> Any:
        return getattr(self.contract.functions, self.function)(*self.args)


@dataclass(frozen=True)
class Event:
    """One decoded escrow event."""

    name: str
    args: dict[str, Any]
    block: int
    tx_hash: str
    log_index: int


class OrbitWatchChain:
    """The escrow at ``escrow_address`` and the EAS contract and token it names."""

    def __init__(self, w3: Web3, escrow_address: str):
        self.w3 = w3
        self.chain_id = w3.eth.chain_id
        require_supported(self.chain_id)
        self.escrow = w3.eth.contract(
            address=to_checksum_address(escrow_address), abi=load("OrbitWatchEscrow")
        )
        self.eas = w3.eth.contract(address=self.escrow.functions.eas().call(), abi=load("IEAS"))
        self.token = w3.eth.contract(
            address=self.escrow.functions.token().call(), abi=load("IERC20Metadata")
        )
        self.result_schema = self.escrow.functions.resultSchemaUid().call()
        self.vote_schema = self.escrow.functions.voteSchemaUid().call()
        self.fee_recipient = self.escrow.functions.feeRecipient().call()
        self.verifier = self.escrow.functions.verifier().call()
        self._events = {
            event().topic: event()
            for event in (getattr(self.escrow.events, e["name"]) for e in self._event_abis())
        }
        self._block_times: dict[int, int] = {}
        self.log_chunk = LOG_CHUNK

    def _event_abis(self) -> list[dict[str, Any]]:
        return [item for item in self.escrow.abi if item.get("type") == "event"]

    # ------------------------------------------------------------------ reading

    def status(self, request_id: str) -> str:
        """The request's status now, with passed deadlines applied (``statusOf``)."""
        return STATUSES[self.escrow.functions.statusOf(request_key(request_id)).call()]

    def request(self, request_id: str) -> dict[str, Any]:
        """The stored request (``getRequest``) as a dict with the Solidity field names."""
        outputs = next(
            item
            for item in self.escrow.abi
            if item.get("type") == "function" and item["name"] == "getRequest"
        )["outputs"][0]["components"]
        values = self.escrow.functions.getRequest(request_key(request_id)).call()
        return {field["name"]: value for field, value in zip(outputs, values, strict=True)}

    def deposit(self, request_id: str) -> int:
        return self.escrow.functions.depositOf(request_key(request_id)).call()

    def owed(self, address: str) -> int:
        return self.escrow.functions.owed(to_checksum_address(address)).call()

    def token_balance(self, address: str) -> int:
        return self.token.functions.balanceOf(to_checksum_address(address)).call()

    def token_info(self) -> dict[str, Any]:
        """The token's address, symbol and decimals, read from the token (decision P2-02)."""
        return {
            "address": self.token.address,
            "symbol": self.token.functions.symbol().call(),
            "decimals": self.token.functions.decimals().call(),
        }

    def is_reviewer(self, address: str) -> bool:
        registry = self.w3.eth.contract(
            address=self.escrow.functions.registry().call(),
            abi=load("OrbitWatchReviewerRegistry"),
        )
        return registry.functions.isReviewer(to_checksum_address(address)).call()

    def credits(self, sent: Sent) -> list[Credit]:
        """The payouts a settlement transaction credited."""
        # Other events in the same transaction (Settled, the token's Transfer) are skipped.
        events = self.escrow.events.Credited().process_receipt(sent.receipt, errors=DISCARD)
        return [
            Credit(e["args"]["party"], e["args"]["amount"], CREDIT_REASONS[e["args"]["reason"]])
            for e in events
        ]

    def latest_block(self) -> int:
        return self.w3.eth.block_number

    def now(self) -> int:
        """The latest block's time (Unix seconds): the clock the escrow's deadlines use."""
        block = self.w3.eth.get_block("latest")
        self._block_times[block["number"]] = block["timestamp"]
        return block["timestamp"]

    def block_time(self, number: int) -> int:
        if number not in self._block_times:
            self._block_times[number] = self.w3.eth.get_block(number)["timestamp"]
        return self._block_times[number]

    def events(self, from_block: int, to_block: int) -> list[Event]:
        """The escrow's events in a block range, in chain order, read in ranges the endpoint
        accepts."""
        logs: list[Any] = []
        start = from_block
        while start <= to_block:
            end = min(to_block, start + self.log_chunk - 1)
            try:
                logs += self._query_logs(start, end)
            except Exception as error:
                smaller = _smaller_range(error, self.log_chunk)
                if smaller is None:
                    raise
                self.log_chunk = smaller
                continue
            start = end + 1
        found = []
        for log in sorted(logs, key=lambda item: (item["blockNumber"], item["logIndex"])):
            event = self._events.get(log["topics"][0].to_0x_hex()) if log["topics"] else None
            if event is None:  # pragma: no cover - the escrow emits only its own events
                continue
            decoded = event.process_log(log)
            found.append(
                Event(
                    decoded["event"],
                    dict(decoded["args"]),
                    log["blockNumber"],
                    log["transactionHash"].to_0x_hex(),
                    log["logIndex"],
                )
            )
        return found

    def _query_logs(self, from_block: int, to_block: int) -> list[Any]:
        """One eth_getLogs call for the escrow's logs."""
        return list(
            self.w3.eth.get_logs(
                {"address": self.escrow.address, "fromBlock": from_block, "toBlock": to_block}
            )
        )

    def attestation(self, uid: bytes) -> dict[str, Any]:
        """An attestation of one of the escrow's schemas, with its data decoded."""
        attestation = self.eas.functions.getAttestation(uid).call()
        names = [o["name"] for o in _outputs(self.eas.abi, "getAttestation")]
        found = dict(zip(names, attestation, strict=True))
        if found["schema"] == self.result_schema:
            keys = ["requestId", "deliverySha256", "reportSha256", "verdict", "method", "version"]
            found["fields"] = dict(zip(keys, abi_decode(RESULT_FIELDS, found["data"]), strict=True))
        elif found["schema"] == self.vote_schema:
            keys = ["requestId", "deliverySha256", "approve", "reasonSha256"]
            found["fields"] = dict(zip(keys, abi_decode(VOTE_FIELDS, found["data"]), strict=True))
        return found

    # ------------------------------------------------------------------ calls

    def approve_call(self, amount: int) -> Call:
        """Let the escrow take exactly ``amount`` of the token (the deposit) when funding."""
        return Call(self.token, "approve", (self.escrow.address, amount))

    def fund_call(self, request_id: str, terms: dict[str, Any], split: dict[str, int]) -> Call:
        """``terms``: termsHash, deliveryDeadline, reservationSeconds,
        verificationTimeoutSeconds, challengeSeconds, reviewSeconds. ``split``:
        observerReward, reviewerReward, platformFee."""
        return Call(self.escrow, "fund", (request_key(request_id), terms, split))

    def cancel_call(self, request_id: str) -> Call:
        return Call(self.escrow, "cancel", (request_key(request_id),))

    def reserve_call(self, request_id: str) -> Call:
        return Call(self.escrow, "reserve", (request_key(request_id),))

    def deliver_call(self, request_id: str, delivery_sha256: bytes) -> Call:
        return Call(self.escrow, "deliver", (request_key(request_id), delivery_sha256))

    def challenge_call(self, request_id: str, reason_sha256: bytes) -> Call:
        return Call(self.escrow, "challenge", (request_key(request_id), reason_sha256))

    def settle_call(self, request_id: str) -> Call:
        return Call(self.escrow, "settle", (request_key(request_id),))

    def withdraw_call(self) -> Call:
        return Call(self.escrow, "withdraw")

    def result_call(
        self,
        request_id: str,
        *,
        delivery_sha256: bytes,
        report_sha256: bytes,
        verdict: str,
        method: str,
        method_version: str,
        observer: str,
    ) -> Call:
        data = abi_encode(
            RESULT_FIELDS,
            [request_id, delivery_sha256, report_sha256, verdict, method, method_version],
        )
        return self._attest_call(self.result_schema, observer, ZERO_UID, data)

    def vote_call(
        self,
        request_id: str,
        *,
        delivery_sha256: bytes,
        approve: bool,
        reason_sha256: bytes,
        observer: str,
        result_attestation: bytes,
    ) -> Call:
        data = abi_encode(VOTE_FIELDS, [request_id, delivery_sha256, approve, reason_sha256])
        return self._attest_call(self.vote_schema, observer, result_attestation, data)

    def _attest_call(self, schema: bytes, recipient: str, ref_uid: bytes, data: bytes) -> Call:
        request = (
            schema,
            (to_checksum_address(recipient), NO_EXPIRATION, False, ref_uid, data, 0),
        )
        return Call(self.eas, "attest", (request,))

    def unsigned(self, sender: str, call: Call) -> dict[str, Any]:
        """The transaction for ``sender`` to sign with its own wallet: no nonce, gas or fees,
        which the wallet fills in when it sends."""
        return {
            "chainId": self.chain_id,
            "from": to_checksum_address(sender),
            "to": call.contract.address,
            "data": call.contract.encode_abi(call.function, args=list(call.args)),
            "value": 0,
        }

    def describe(self, transaction: dict[str, Any]) -> tuple[str, str | None]:
        """What a transaction to the escrow, EAS or the token does: (action, request key hex).
        The action is the function name, or ``attest_result`` / ``attest_vote``."""
        to = to_checksum_address(transaction["to"]) if transaction.get("to") else None
        data = transaction.get("input") or transaction.get("data") or b""
        targets = {self.escrow.address: self.escrow, self.eas.address: self.eas}
        targets[self.token.address] = self.token
        contract = targets.get(to) if to else None
        if contract is None:
            return "other", None
        try:
            function, args = contract.decode_function_input(data)
        except ValueError:
            return "other", None
        name = function.fn_name
        if contract is self.token:
            return name, None
        if contract is self.eas:
            if name != "attest":
                return name, None
            request = args["request"]  # decoded with the struct's field names
            schema, payload = request["schema"], request["data"]["data"]
            fields = VOTE_FIELDS if schema == self.vote_schema else RESULT_FIELDS
            kind = "attest_vote" if schema == self.vote_schema else "attest_result"
            try:
                request_id = abi_decode(fields, payload)[0]
            except Exception:  # malformed data: not one of ours
                return "attest", None
            return kind, request_key(request_id).hex()
        key = args.get("requestId")
        return name, key.hex() if isinstance(key, bytes) else None

    # ------------------------------------------------------------------ the parties' calls

    def fund(
        self, account: LocalAccount, request_id: str, terms: dict[str, Any], split: dict[str, int]
    ) -> Sent:
        return self._send(account, self.fund_call(request_id, terms, split))

    def cancel(self, account: LocalAccount, request_id: str) -> Sent:
        return self._send(account, self.cancel_call(request_id))

    def reserve(self, account: LocalAccount, request_id: str) -> Sent:
        return self._send(account, self.reserve_call(request_id))

    def deliver(self, account: LocalAccount, request_id: str, delivery_sha256: bytes) -> Sent:
        return self._send(account, self.deliver_call(request_id, delivery_sha256))

    def challenge(self, account: LocalAccount, request_id: str, reason_sha256: bytes) -> Sent:
        return self._send(account, self.challenge_call(request_id, reason_sha256))

    def settle(self, account: LocalAccount, request_id: str) -> Sent:
        return self._send(account, self.settle_call(request_id))

    def withdraw(self, account: LocalAccount) -> Sent:
        return self._send(account, self.withdraw_call())

    def attest_result(self, verifier: LocalAccount, request_id: str, **fields: Any) -> Sent:
        return self._send(verifier, self.result_call(request_id, **fields))

    def attest_vote(self, reviewer: LocalAccount, request_id: str, **fields: Any) -> Sent:
        return self._send(reviewer, self.vote_call(request_id, **fields))

    # ------------------------------------------------------------------ local chain only

    def travel_to(self, timestamp: int) -> None:
        """On a local Anvil chain, move the clock to ``timestamp`` (never back): an empty
        block is mined at that time, so that reads and gas estimates see it, and the next
        transaction is mined with the same timestamp, which Anvil allows."""
        if self.chain_id != ANVIL_CHAIN_ID:
            raise ChainError("not_local", "only a local Anvil chain can move its clock")
        latest = self.w3.eth.get_block("latest")["timestamp"]
        if timestamp > latest:
            self.w3.provider.make_request("evm_mine", [timestamp])
            latest = timestamp
        self.w3.provider.make_request("evm_setNextBlockTimestamp", [latest])

    # ------------------------------------------------------------------ sending

    def submit(self, account: LocalAccount, call: Call) -> str:
        """Sign ``call`` with ``account`` and send it. Returns the transaction hash at once."""
        try:
            transaction = call.bound().build_transaction(
                {
                    "from": account.address,
                    "chainId": self.chain_id,
                    "nonce": self.w3.eth.get_transaction_count(account.address, "pending"),
                }
            )
        except ContractLogicError as error:  # refused while estimating gas
            raise self.decode_error(error) from None
        transaction["gas"] = with_margin(transaction["gas"])
        signed = account.sign_transaction(transaction)
        return self.w3.eth.send_raw_transaction(signed.raw_transaction).to_0x_hex()

    def wait(self, tx_hash: str, timeout: float = 120) -> Sent:
        """Wait for a transaction. ``ChainError("pending")`` if it is not mined in time,
        ``ChainError("transaction_failed")`` if it was mined and failed."""
        try:
            receipt = self.w3.eth.wait_for_transaction_receipt(tx_hash, timeout=timeout)
        except TimeExhausted:
            raise ChainError("pending", f"transaction {tx_hash} is not mined yet") from None
        if receipt["status"] != 1:
            raise ChainError("transaction_failed", f"transaction {tx_hash} failed on chain")
        return Sent(tx_hash, receipt["blockNumber"], receipt)

    def receipt(self, tx_hash: str) -> Any | None:
        """The receipt of a mined transaction, or None while it is pending."""
        try:
            return self.w3.eth.get_transaction_receipt(tx_hash)
        except TransactionNotFound:
            return None

    def transaction(self, tx_hash: str) -> Any | None:
        try:
            return self.w3.eth.get_transaction(tx_hash)
        except TransactionNotFound:
            return None

    def _send(self, account: LocalAccount, call: Call) -> Sent:
        return self.wait(self.submit(account, call))

    def decode_error(self, error: ContractLogicError) -> ChainError:
        data = error.data if isinstance(error.data, str) else ""
        return self.decode_revert(data) or ChainError("reverted", str(error), {"data": data})

    def decode_revert(self, data: str) -> ChainError | None:
        return decode_revert(data)


def with_margin(gas: int) -> int:
    """A gas estimate plus 25 %. An estimate is the exact minimum for the block it was made
    against; the block the transaction lands in can cost a little more (a later time stored
    by EAS, for example), and an exact limit then runs out of gas."""
    return gas * 5 // 4


@cache
def _known_errors() -> dict[bytes, tuple[str, list[str], list[str]]]:
    return _error_table(load("OrbitWatchEscrow") + load("IERC20Errors") + EAS_ERRORS)


def decode_revert(data: str) -> ChainError | None:
    """An Orbit Watch, EAS or token custom error from revert data (hex), or None if it is
    not one of them."""
    raw = bytes.fromhex(data[2:]) if isinstance(data, str) and data.startswith("0x") else b""
    known = _known_errors().get(raw[:4])
    if known is None:
        return None
    name, types, names = known
    values = abi_decode(types, raw[4:]) if types else ()
    args = dict(zip(names, values, strict=True))
    if name == "WrongStatus":
        args["status"] = STATUSES[args["status"]]
        if args["status"] == "Settled":
            return ChainError("already_settled", "the request was already settled", args)
    return ChainError(snake_case(name), f"{name}({_show(args)})", args)


def _outputs(abi: list[dict[str, Any]], function: str) -> list[dict[str, Any]]:
    item = next(i for i in abi if i.get("type") == "function" and i["name"] == function)
    return item["outputs"][0]["components"]


def _error_table(abi: list[dict[str, Any]]) -> dict[bytes, tuple[str, list[str], list[str]]]:
    table = {}
    for item in abi:
        if item.get("type") != "error":
            continue
        types = [_abi_type(i) for i in item["inputs"]]
        selector = function_signature_to_4byte_selector(f"{item['name']}({','.join(types)})")
        table[selector] = (item["name"], types, [i["name"] for i in item["inputs"]])
    return table


def _abi_type(item: dict[str, Any]) -> str:
    if item["type"].startswith("tuple"):  # pragma: no cover - no tuple errors in our ABIs
        inner = ",".join(_abi_type(c) for c in item["components"])
        return f"({inner}){item['type'][5:]}"
    return item["type"]


def _show(args: dict[str, Any]) -> str:
    def one(value: Any) -> str:
        return "0x" + value.hex() if isinstance(value, bytes) else str(value)

    return ", ".join(f"{k}={one(v)}" for k, v in args.items())


def _smaller_range(error: Exception, chunk: int) -> int | None:
    """The eth_getLogs block range to try after ``error``, if the endpoint refused ``chunk``
    blocks as too many: the limit it names (Base's public endpoint: "eth_getLogs is limited to
    a 200 range"), or else half. None if the error is something else, or nothing smaller is
    left to try."""
    response = getattr(error, "response", None)
    text = f"{error} {getattr(response, 'text', '') or ''}".lower()
    named = re.search(r"limited to an? (\d+) range", text)
    if named and MIN_LOG_CHUNK <= int(named.group(1)) < chunk:
        return int(named.group(1))
    refused = getattr(response, "status_code", None) == 413 or any(
        word in text for word in ("block range", "range too", "too many", "limit exceeded")
    )
    if not refused or chunk <= MIN_LOG_CHUNK:
        return None
    return max(MIN_LOG_CHUNK, chunk // 2)

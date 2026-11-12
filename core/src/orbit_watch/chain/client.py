"""A client for the Orbit Watch escrow, its EAS schemas and its token (phase 2, step 2.5).

Every transaction is signed by the account given to the call, which is the party's own
(decision P2-09). Refused calls raise ``ChainError`` with the contract's custom error in
snake case as ``code``.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from eth_abi import decode as abi_decode
from eth_abi import encode as abi_encode
from eth_account.signers.local import LocalAccount
from eth_utils import function_signature_to_4byte_selector, to_checksum_address
from web3 import Web3
from web3.exceptions import ContractLogicError
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
NO_EXPIRATION = 0


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
            address=self.escrow.functions.token().call(), abi=load("IERC20")
        )
        self.result_schema = self.escrow.functions.resultSchemaUid().call()
        self.vote_schema = self.escrow.functions.voteSchemaUid().call()
        self.fee_recipient = self.escrow.functions.feeRecipient().call()
        self._errors = _error_table(load("OrbitWatchEscrow") + load("IERC20Errors") + EAS_ERRORS)

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

    def credits(self, sent: Sent) -> list[Credit]:
        """The payouts a settlement transaction credited."""
        # Other events in the same transaction (Settled, the token's Transfer) are skipped.
        events = self.escrow.events.Credited().process_receipt(sent.receipt, errors=DISCARD)
        return [
            Credit(e["args"]["party"], e["args"]["amount"], CREDIT_REASONS[e["args"]["reason"]])
            for e in events
        ]

    # ------------------------------------------------------------------ the parties' calls

    def fund(
        self, account: LocalAccount, request_id: str, terms: dict[str, Any], split: dict[str, int]
    ) -> Sent:
        """``terms``: termsHash, deliveryDeadline, reservationSeconds,
        verificationTimeoutSeconds, challengeSeconds, reviewSeconds. ``split``:
        observerReward, reviewerReward, platformFee."""
        return self._send(
            account, self.escrow.functions.fund(request_key(request_id), terms, split)
        )

    def cancel(self, account: LocalAccount, request_id: str) -> Sent:
        return self._send(account, self.escrow.functions.cancel(request_key(request_id)))

    def reserve(self, account: LocalAccount, request_id: str) -> Sent:
        return self._send(account, self.escrow.functions.reserve(request_key(request_id)))

    def deliver(self, account: LocalAccount, request_id: str, delivery_sha256: bytes) -> Sent:
        return self._send(
            account, self.escrow.functions.deliver(request_key(request_id), delivery_sha256)
        )

    def challenge(self, account: LocalAccount, request_id: str, reason_sha256: bytes) -> Sent:
        return self._send(
            account, self.escrow.functions.challenge(request_key(request_id), reason_sha256)
        )

    def settle(self, account: LocalAccount, request_id: str) -> Sent:
        return self._send(account, self.escrow.functions.settle(request_key(request_id)))

    def withdraw(self, account: LocalAccount) -> Sent:
        return self._send(account, self.escrow.functions.withdraw())

    # ------------------------------------------------------------------ attestations

    def attest_result(
        self,
        verifier: LocalAccount,
        request_id: str,
        *,
        delivery_sha256: bytes,
        report_sha256: bytes,
        verdict: str,
        method: str,
        method_version: str,
        observer: str,
    ) -> Sent:
        data = abi_encode(
            ["string", "bytes32", "bytes32", "string", "string", "string"],
            [request_id, delivery_sha256, report_sha256, verdict, method, method_version],
        )
        return self._attest(verifier, self.result_schema, observer, ZERO_UID, data)

    def attest_vote(
        self,
        reviewer: LocalAccount,
        request_id: str,
        *,
        delivery_sha256: bytes,
        approve: bool,
        reason_sha256: bytes,
        observer: str,
        result_attestation: bytes,
    ) -> Sent:
        data = abi_encode(
            ["string", "bytes32", "bool", "bytes32"],
            [request_id, delivery_sha256, approve, reason_sha256],
        )
        return self._attest(reviewer, self.vote_schema, observer, result_attestation, data)

    def _attest(
        self, account: LocalAccount, schema: bytes, recipient: str, ref_uid: bytes, data: bytes
    ) -> Sent:
        request = (
            schema,
            (to_checksum_address(recipient), NO_EXPIRATION, False, ref_uid, data, 0),
        )
        return self._send(account, self.eas.functions.attest(request))

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

    def _send(self, account: LocalAccount, call: Any) -> Sent:
        try:
            transaction = call.build_transaction(
                {
                    "from": account.address,
                    "chainId": self.chain_id,
                    "nonce": self.w3.eth.get_transaction_count(account.address, "pending"),
                }
            )
        except ContractLogicError as error:  # refused while estimating gas
            raise self._decode(error) from None
        signed = account.sign_transaction(transaction)
        tx_hash = self.w3.eth.send_raw_transaction(signed.raw_transaction)
        receipt = self.w3.eth.wait_for_transaction_receipt(tx_hash, timeout=120)
        if receipt["status"] != 1:
            raise ChainError(
                "transaction_failed", f"transaction {tx_hash.to_0x_hex()} failed on chain"
            )
        return Sent(tx_hash.to_0x_hex(), receipt["blockNumber"], receipt)

    def _decode(self, error: ContractLogicError) -> ChainError:
        data = error.data if isinstance(error.data, str) else ""
        raw = bytes.fromhex(data[2:]) if data.startswith("0x") else b""
        known = self._errors.get(raw[:4])
        if known is None:
            return ChainError("reverted", str(error), {"data": data})
        name, types, names = known
        values = abi_decode(types, raw[4:]) if types else ()
        args = dict(zip(names, values, strict=True))
        if name == "WrongStatus":
            args["status"] = STATUSES[args["status"]]
            if args["status"] == "Settled":
                return ChainError("already_settled", "the request was already settled", args)
        return ChainError(snake_case(name), f"{name}({_show(args)})", args)


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

"""Signing on the user's side (phase 2, step 2.6, decision P2-09).

The command line signs with an **encrypted keystore** that the user created, for example
with Foundry's ``cast wallet import <name>`` (which writes it to ``~/.foundry/keystores``).
The key is decrypted in the user's own process, used to sign, and never sent anywhere: the
Orbit Watch API only ever sees addresses, signatures and signed transactions' hashes.

The password comes from a file (``--password-file``, or ``ORBIT_WATCH_PASSWORD_FILE``) or
is asked for; it is never taken from the command line. Orbit Watch never asks for a seed
phrase or a private key.
"""

from __future__ import annotations

import getpass
import json
import os
from pathlib import Path
from typing import Any

from eth_account import Account
from eth_account.messages import encode_defunct
from eth_account.signers.local import LocalAccount
from eth_utils import to_checksum_address
from web3 import Web3
from web3.exceptions import ContractLogicError, TimeExhausted, Web3RPCError

from orbit_watch.chain import ChainError, require_supported
from orbit_watch.chain.client import decode_revert, with_margin

PASSWORD_FILE_ENV = "ORBIT_WATCH_PASSWORD_FILE"


def read_password(
    password_file: str | None,
    prompt: str = "keystore password: ",
    env: str = PASSWORD_FILE_ENV,
) -> str:
    """The keystore password, from ``password_file``, the file named by ``$env``
    (``ORBIT_WATCH_PASSWORD_FILE``) or a prompt that does not echo."""
    path = password_file or os.environ.get(env)
    if path:
        return Path(path).read_text(encoding="utf-8").rstrip("\r\n")
    return getpass.getpass(prompt)


def load_keystore(path: str | Path, password: str) -> LocalAccount:
    """Decrypt an encrypted JSON keystore (Web3 Secret Storage, as ``cast wallet import``
    writes it)."""
    try:
        keyfile = json.loads(Path(path).read_text(encoding="utf-8"))
        return Account.from_key(Account.decrypt(keyfile, password))
    except (OSError, ValueError) as error:
        raise ChainError("bad_keystore", f"cannot open the keystore {path}: {error}") from None


class Wallet:
    """A user's own account and the RPC endpoint it sends through."""

    def __init__(self, w3: Web3, account: LocalAccount, *, timeout: float = 120):
        self.w3 = w3
        self.account = account
        self.timeout = timeout

    @property
    def address(self) -> str:
        return self.account.address

    def sign_message(self, text: str) -> str:
        """An EIP-191 signature of ``text`` (the same as ``cast wallet sign``)."""
        return self.account.sign_message(encode_defunct(text=text)).signature.to_0x_hex()

    def send(self, unsigned: dict[str, Any]) -> str:
        """Fill in nonce, gas and fees, sign, send and wait for one unsigned transaction
        that the API prepared. Returns its hash once mined (or, if it is still pending
        after the timeout, at once). A refusal raises ``ChainError`` with the contract's
        error in snake case, before anything is sent; so does a node that refuses it, for
        example for lack of testnet ETH for gas (``rpc_error``)."""
        try:
            return self._send(unsigned)
        except Web3RPCError as error:
            raise ChainError("rpc_error", f"the chain's node refused: {error}") from None

    def _send(self, unsigned: dict[str, Any]) -> str:
        chain_id = self.w3.eth.chain_id
        require_supported(chain_id)
        if unsigned.get("chainId") != chain_id:
            raise ChainError(
                "wrong_chain",
                f"the transaction is for chain {unsigned.get('chainId')}, "
                f"the RPC endpoint is chain {chain_id}",
            )
        if to_checksum_address(unsigned["from"]) != self.address:
            raise ChainError(
                "wrong_wallet",
                f"the transaction is for {unsigned['from']}, this keystore is {self.address}",
            )
        transaction = {
            "chainId": chain_id,
            "from": self.address,
            "to": to_checksum_address(unsigned["to"]),
            "data": unsigned["data"],
            "value": int(unsigned.get("value", 0)),
            "nonce": self.w3.eth.get_transaction_count(self.address, "pending"),
        }
        try:
            transaction["gas"] = with_margin(self.w3.eth.estimate_gas(transaction))
        except ContractLogicError as error:
            data = error.data if isinstance(error.data, str) else ""
            raise decode_revert(data) or ChainError("reverted", str(error)) from None
        priority = self.w3.eth.max_priority_fee
        base = self.w3.eth.get_block("latest")["baseFeePerGas"]
        transaction["maxPriorityFeePerGas"] = priority
        transaction["maxFeePerGas"] = 2 * base + priority
        signed = self.account.sign_transaction(transaction)
        tx_hash = self.w3.eth.send_raw_transaction(signed.raw_transaction).to_0x_hex()
        try:
            receipt = self.w3.eth.wait_for_transaction_receipt(tx_hash, timeout=self.timeout)
        except TimeExhausted:
            return tx_hash
        if receipt["status"] != 1:
            raise ChainError(
                "transaction_failed", f"transaction {tx_hash} failed", {"tx_hash": tx_hash}
            )
        return tx_hash


def open_wallet(
    rpc: str, keystore: str | Path, password_file: str | None = None, timeout: float = 120
) -> Wallet:
    w3 = Web3(Web3.HTTPProvider(rpc))
    return Wallet(w3, load_keystore(keystore, read_password(password_file)), timeout=timeout)

"""Talking to the Orbit Watch contracts (phase 2, step 2.5).

**Testnet only.** Everything here refuses every chain except Base Sepolia
(chain ID 84532) and a local Anvil chain (31337). Needs the ``evm`` extra
(web3.py, decision P2-08): ``pip install "orbit-watch[evm]"``.

* ``OrbitWatchChain`` (in ``orbit_watch.chain.client``) reads the escrow and
  sends transactions and EAS attestations, each signed by the party's own
  account.
* ``orbit_watch.settlement.evm`` builds the ``evm-testnet`` settlement adapter
  on top of it.
"""

from __future__ import annotations

import hashlib
import re
from datetime import datetime

BASE_SEPOLIA_CHAIN_ID = 84532
ANVIL_CHAIN_ID = 31337
SUPPORTED_CHAINS = {
    BASE_SEPOLIA_CHAIN_ID: "Base Sepolia testnet",
    ANVIL_CHAIN_ID: "local Anvil chain",
}
# Block explorer for links (decision P2-10). A local chain has none.
EXPLORERS = {BASE_SEPOLIA_CHAIN_ID: "https://sepolia.basescan.org"}
# Shown with every chain-related output (decision P2-10).
TESTNET_NOTICE = "Base Sepolia testnet, no real value"

# Names of the escrow's enums, in their Solidity order.
STATUSES = (
    "None",
    "Funded",
    "Reserved",
    "Delivered",
    "ChallengePeriod",
    "InReview",
    "Accepted",
    "Rejected",
    "Disputed",
    "Expired",
    "Cancelled",
    "Settled",
)
CREDIT_REASONS = {0: "observer_reward", 1: "review", 2: "platform_fee", 3: "refund"}

_HEX64 = re.compile(r"[0-9a-f]{64}")


class ChainError(RuntimeError):
    """A chain call was refused or failed. ``code`` is stable: a contract's custom error in
    snake case (``wrong_status``, ``not_the_verifier``, ...) or one of ``unsupported_chain``,
    ``transaction_failed``, ``reverted``, ``not_local``."""

    def __init__(self, code: str, message: str, details: dict | None = None):
        super().__init__(message)
        self.code = code
        self.details = details or {}


def require_supported(chain_id: int) -> None:
    if chain_id not in SUPPORTED_CHAINS:
        raise ChainError(
            "unsupported_chain",
            f"chain {chain_id} is not supported: Orbit Watch phase 2 runs only on the "
            "Base Sepolia testnet (84532) or a local Anvil chain (31337)",
        )


def request_key(request_id: str) -> bytes:
    """The escrow's key of an Orbit Watch request ID: ``keccak256(bytes(request_id))``."""
    from eth_utils import keccak

    return keccak(text=request_id)


def bytes32_from_sha256(hex_digest: str) -> bytes:
    """A lower-case hex SHA-256, as Orbit Watch writes them, as ``bytes32``."""
    if not _HEX64.fullmatch(hex_digest):
        raise ValueError(f"not a lower-case hex SHA-256: {hex_digest!r}")
    return bytes.fromhex(hex_digest)


def sha256_of_text(text: str) -> bytes:
    """``bytes32`` SHA-256 of a text, for example a challenge or vote reason."""
    return hashlib.sha256(text.encode("utf-8")).digest()


def unix_seconds(when: datetime) -> int:
    seconds = when.timestamp()
    if seconds != int(seconds):
        raise ValueError(f"{when} is not a whole second; the chain counts whole seconds")
    return int(seconds)


def whole_seconds(hours: float) -> int:
    seconds = hours * 3600
    if seconds != int(seconds) or seconds <= 0:
        raise ValueError(f"{hours} hours is not a positive whole number of seconds")
    return int(seconds)


def snake_case(name: str) -> str:
    return re.sub(r"(?<!^)(?=[A-Z])", "_", name).lower()


def explorer_link(chain_id: int, tx_hash: str) -> str | None:
    base = EXPLORERS.get(chain_id)
    return f"{base}/tx/{tx_hash}" if base else None

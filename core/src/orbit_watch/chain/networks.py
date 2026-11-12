"""Known testnet deployments of the Orbit Watch contracts (phase 2, step 2.7; decision D-24).

``deployments/<network>.json`` in this package is the deployment record that
``contracts/script/DeployOrbitWatch.s.sol`` wrote; a test keeps it equal to the copy in
``contracts/deployments/``. The server takes the escrow and its first block from it
(``orbit-watch serve --network base-sepolia``), and the command line falls back to the
network's public RPC endpoint.

**Testnet only, no real value.**
"""

from __future__ import annotations

import json
from importlib import resources
from pathlib import Path
from typing import Any

from orbit_watch.chain import BASE_SEPOLIA_CHAIN_ID, ChainError, require_supported

BASE_SEPOLIA = "base-sepolia"
NETWORKS = {BASE_SEPOLIA: BASE_SEPOLIA_CHAIN_ID}
# Base's public endpoint: free, rate limited and best effort, not for production
# (docs.base.org/network-information). Enough for a local testnet prototype.
PUBLIC_RPC = {BASE_SEPOLIA_CHAIN_ID: "https://sepolia.base.org"}

RECORD_FIELDS = (
    "network",
    "chain_id",
    "from_block",
    "deployer",
    "escrow",
    "escrow_version",
    "registry",
    "timelock",
    "timelock_min_delay_seconds",
    "safe",
    "safe_signers",
    "safe_threshold",
    "reviewers",
    "verifier",
    "fee_recipient",
    "token",
    "eas",
    "result_schema_uid",
    "vote_schema_uid",
)


def public_rpc(chain_id: int) -> str | None:
    return PUBLIC_RPC.get(chain_id)


def read_record(path: Path) -> dict[str, Any]:
    """A deployment record as the deployment script writes it, checked for completeness."""
    return parse_record(path.read_text(encoding="utf-8"), str(path))


def parse_record(text: str, where: str) -> dict[str, Any]:
    record = json.loads(text)
    missing = [field for field in RECORD_FIELDS if field not in record]
    if missing:
        raise ChainError("invalid_deployment", f"{where} lacks {', '.join(missing)}")
    require_supported(record["chain_id"])
    return record


def deployment(network: str) -> dict[str, Any]:
    """The packaged deployment record of ``network``, for example ``base-sepolia``."""
    if network not in NETWORKS:
        raise ChainError(
            "unknown_network", f"unknown network {network!r}; known: {', '.join(NETWORKS)}"
        )
    resource = resources.files("orbit_watch.chain") / "deployments" / f"{network}.json"
    if not resource.is_file():
        raise ChainError(
            "not_deployed",
            f"this version of Orbit Watch has no deployment on {network}; give --chain-rpc, "
            "--escrow and --from-block instead",
        )
    record = parse_record(resource.read_text(encoding="utf-8"), f"the {network} deployment")
    if record["chain_id"] != NETWORKS[network]:
        raise ChainError("invalid_deployment", f"the {network} deployment names another chain")
    return record

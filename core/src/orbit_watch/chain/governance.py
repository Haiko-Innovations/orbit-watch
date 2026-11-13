"""Governance of the reviewer registry, for the administrator view (phase 3, step 3.7).

On Base Sepolia an OpenZeppelin ``TimelockController`` owns the reviewer registry, and its
only proposer is a 2-of-3 Safe (step 2.7). Changing the reviewers takes three steps, and
Orbit Watch can take none of them for anyone (decision D-32):

1. the Safe's owners propose, sign and execute ``timelock.schedule(...)`` in the Safe's own
   app;
2. the timelock waits its minimum delay (48 hours on Base Sepolia);
3. anyone calls ``timelock.execute(...)``.

Orbit Watch prepares the data for steps 1 and 3, as a file for the Safe app's Transaction
Builder too, and shows the timelock's operations from its events (``ChainLink`` mirrors
them). It holds no key of the Safe or the timelock.
"""

from __future__ import annotations

import json
import secrets
from typing import Any

from eth_utils import is_address, keccak, to_checksum_address

from orbit_watch.chain import ChainError
from orbit_watch.chain.abi import load
from orbit_watch.chain.client import OrbitWatchChain

ZERO_BYTES32 = b"\x00" * 32
# OpenZeppelin 5's TimelockController.OperationState, in order.
OPERATION_STATES = ("unset", "waiting", "ready", "done")
# The Safe{Wallet} app reads ?safe=<chain short name>:<address>. Short names from
# ethereum-lists/chains (eip155-84532: "basesep"); the app's routes from
# safe-wallet-monorepo apps/web/src/config/routes.ts.
SAFE_APP = "https://app.safe.global"
SAFE_CHAIN_PREFIXES = {84532: "basesep"}
# The Transaction Builder's batch file (safe-react-apps apps/tx-builder, BatchFile).
BATCH_FILE_VERSION = "1.0"
ACTIONS = {"add": "addReviewer", "remove": "removeReviewer"}


def _serialize(value: Any) -> str:
    """The Transaction Builder's ``serializeJSONObject``: sorted keys listed first, then
    each value followed by a comma."""
    if isinstance(value, list):
        return "[" + ",".join(_serialize(item) for item in value) + "]"
    if isinstance(value, dict):
        keys = sorted(value)
        listed = json.dumps(keys, separators=(",", ":"), ensure_ascii=False)
        return "{" + listed + "".join(_serialize(value[k]) + "," for k in keys) + "}"
    return json.dumps(value, separators=(",", ":"), ensure_ascii=False)


def batch_checksum(batch: dict[str, Any]) -> str:
    """The checksum the Transaction Builder checks when it loads a batch file: Keccak-256
    of the file without its checksum, with the batch's name left out."""
    meta = {k: v for k, v in batch["meta"].items() if k != "checksum"}
    return "0x" + keccak(text=_serialize({**batch, "meta": {**meta, "name": None}})).hex()


def batch_file(
    chain_id: int,
    safe: str | None,
    name: str,
    description: str,
    transactions: list[dict[str, str]],
    created_at_ms: int,
) -> dict[str, Any]:
    """A batch file to load in the Safe app's Transaction Builder (raw calldata)."""
    meta: dict[str, Any] = {"name": name, "description": description}
    if safe is not None:
        meta["createdFromSafeAddress"] = safe
    batch = {
        "version": BATCH_FILE_VERSION,
        "chainId": str(chain_id),
        "createdAt": created_at_ms,
        "meta": meta,
        "transactions": [
            {"to": t["to"], "value": t["value"], "data": t["data"]} for t in transactions
        ],
    }
    batch["meta"]["checksum"] = batch_checksum(batch)
    return batch


def safe_app_links(chain_id: int, safe: str | None) -> dict[str, str] | None:
    prefix = SAFE_CHAIN_PREFIXES.get(chain_id)
    if prefix is None or safe is None:
        return None
    query = f"?safe={prefix}:{safe}"
    return {
        "home": f"{SAFE_APP}/home{query}",
        "queue": f"{SAFE_APP}/transactions/queue{query}",
        "history": f"{SAFE_APP}/transactions/history{query}",
    }


class Governance:
    """The registry of ``chain``'s escrow, the timelock that owns it and ``safe``, the
    timelock's proposer (from the deployment record or ``serve --safe``)."""

    def __init__(self, chain: OrbitWatchChain, safe: str | None = None):
        self.chain = chain
        self.registry = chain.registry
        self.timelock = chain.timelock
        self.safe = None if safe is None else to_checksum_address(safe)

    def require_timelock(self) -> Any:
        if self.timelock is None:
            raise ChainError(
                "no_timelock",
                f"the registry's owner {self.registry.functions.owner().call()} is not a "
                "timelock: change the reviewers with that account directly",
            )
        return self.timelock

    # ------------------------------------------------------------------ views

    def registry_view(self) -> dict[str, Any]:
        registry = self.registry.functions
        timelock = self.timelock
        return {
            "address": self.registry.address,
            "owner": registry.owner().call(),
            "owner_kind": "timelock" if timelock is not None else "other",
            "pending_owner": registry.pendingOwner().call(),
            "max_reviewers": registry.MAX_REVIEWERS().call(),
            "reviewers": list(registry.reviewers().call()),
            "timelock": None
            if timelock is None
            else {
                "address": timelock.address,
                "min_delay_seconds": timelock.functions.getMinDelay().call(),
            },
        }

    def safe_view(self) -> dict[str, Any] | None:
        if self.safe is None:
            return None
        view: dict[str, Any] = {
            "address": self.safe,
            "app": safe_app_links(self.chain.chain_id, self.safe),
        }
        safe = self.chain.w3.eth.contract(address=self.safe, abi=load("ISafe"))
        try:
            view["owners"] = list(safe.functions.getOwners().call())
            view["threshold"] = safe.functions.getThreshold().call()
            view["nonce"] = safe.functions.nonce().call()
        except Exception:  # no Safe at that address
            view["problem"] = f"{self.safe} does not answer as a Safe"
        if self.timelock is not None:
            role = self.timelock.functions.PROPOSER_ROLE().call()
            view["proposer"] = self.timelock.functions.hasRole(role, self.safe).call()
        return view

    def operation_state(self, operation_id: str) -> tuple[str, int]:
        """(state, ready time in Unix seconds; 1 once done, 0 if unknown)."""
        timelock = self.require_timelock()
        key = bytes.fromhex(operation_id.removeprefix("0x"))
        state = OPERATION_STATES[timelock.functions.getOperationState(key).call()]
        return state, timelock.functions.getTimestamp(key).call()

    def describe_call(self, target: str, data: str) -> str:
        """What one call of an operation does, in words."""
        if to_checksum_address(target) == self.registry.address:
            try:
                function, args = self.registry.decode_function_input(data)
            except Exception:  # calldata that is not the registry's
                return f"an unknown call to the reviewer registry ({data[:10]})"
            shown = ", ".join(str(value) for value in args.values())
            return f"registry.{function.fn_name}({shown})"
        return f"a call to {target} ({data[:10]})"

    # ------------------------------------------------------------------ preparing

    def prepare(self, action: str, reviewer: str, created_at_ms: int) -> dict[str, Any]:
        """The data to add or remove one reviewer through the timelock: the Safe schedules,
        anyone executes after the delay. Nothing is sent and nothing is kept: the timelock's
        CallScheduled event tells the rest."""
        if action not in ACTIONS:
            raise ChainError("invalid_action", "action must be add or remove")
        if not isinstance(reviewer, str) or not is_address(reviewer):
            raise ChainError("invalid_address", f"not an address: {reviewer!r}")
        address = to_checksum_address(reviewer)
        if int(address, 16) == 0:
            raise ChainError("invalid_address", "the zero address cannot review")
        timelock = self.require_timelock()
        registry = self.registry.functions
        current = registry.isReviewer(address).call()
        if action == "add" and current:
            raise ChainError("already_reviewer", f"{address} is already a reviewer")
        if action == "remove" and not current:
            raise ChainError("not_a_reviewer", f"{address} is not a reviewer")
        if action == "add" and len(registry.reviewers().call()) >= registry.MAX_REVIEWERS().call():
            raise ChainError("registry_full", "the registry has its maximum number of reviewers")
        function = ACTIONS[action]
        data = self.registry.encode_abi(function, args=[address])
        salt = secrets.token_bytes(32)
        delay = timelock.functions.getMinDelay().call()
        target = self.registry.address
        operation_id = timelock.functions.hashOperation(target, 0, data, ZERO_BYTES32, salt).call()
        schedule = {
            "to": timelock.address,
            "value": "0",
            "data": timelock.encode_abi(
                "schedule", args=[target, 0, data, ZERO_BYTES32, salt, delay]
            ),
        }
        execute = {
            "to": timelock.address,
            "value": "0",
            "data": timelock.encode_abi("execute", args=[target, 0, data, ZERO_BYTES32, salt]),
        }
        words = "Add" if action == "add" else "Remove"
        return {
            "action": action,
            "reviewer": address,
            "call": {
                "to": target,
                "value": "0",
                "data": data,
                "function": f"{function}({address})",
            },
            "operation_id": "0x" + operation_id.hex(),
            "predecessor": "0x" + ZERO_BYTES32.hex(),
            "salt": "0x" + salt.hex(),
            "delay_seconds": delay,
            "schedule": schedule,
            "execute": execute,
            "safe": self.safe_view(),
            "batch_file": batch_file(
                self.chain.chain_id,
                self.safe,
                f"Orbit Watch: schedule {function}({address})",
                f"{words} reviewer {address} in the Orbit Watch reviewer registry "
                f"{target}, through the timelock {timelock.address}. The timelock waits "
                f"{delay} seconds before anyone can execute it.",
                [schedule],
                created_at_ms,
            ),
        }

    def execute_data(self, calls: list[dict[str, Any]], predecessor: str, salt: str) -> dict:
        """``execute`` (one call) or ``executeBatch`` (several) for a scheduled operation."""
        timelock = self.require_timelock()
        pred = bytes.fromhex(predecessor.removeprefix("0x"))
        salt_bytes = bytes.fromhex(salt.removeprefix("0x"))
        if len(calls) == 1:
            call = calls[0]
            data = timelock.encode_abi(
                "execute",
                args=[call["target"], int(call["value"]), call["data"], pred, salt_bytes],
            )
        else:
            data = timelock.encode_abi(
                "executeBatch",
                args=[
                    [c["target"] for c in calls],
                    [int(c["value"]) for c in calls],
                    [c["data"] for c in calls],
                    pred,
                    salt_bytes,
                ],
            )
        return {"to": timelock.address, "value": "0", "data": data}

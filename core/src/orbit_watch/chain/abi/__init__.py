"""ABIs of the contracts Orbit Watch talks to (phase 2).

The files are generated from the Foundry build of ``contracts/`` and must match
it; a test checks this. Regenerate after changing a contract::

    cd contracts && forge build
    cd ../core && uv run python -m orbit_watch.chain.abi ../contracts/out
"""

from __future__ import annotations

import json
import sys
from functools import cache
from importlib import resources
from pathlib import Path
from typing import Any

# Published name -> (Foundry source file, contract name)
SOURCES: dict[str, tuple[str, str]] = {
    "OrbitWatchEscrow": ("OrbitWatchEscrow.sol", "OrbitWatchEscrow"),
    "OrbitWatchReviewerRegistry": ("OrbitWatchReviewerRegistry.sol", "OrbitWatchReviewerRegistry"),
    "IEAS": ("IEAS.sol", "IEAS"),
    "IERC20": ("IERC20.sol", "IERC20"),
    "IERC20Metadata": ("IERC20Metadata.sol", "IERC20Metadata"),
    "IERC20Errors": ("draft-IERC6093.sol", "IERC20Errors"),
    # Governance of the reviewer registry (step 3.7): the timelock that owns it and the Safe
    # that proposes to the timelock.
    "TimelockController": ("TimelockController.sol", "TimelockController"),
    "ISafe": ("ISafe.sol", "ISafe"),
}

# Errors of the EAS contract on Base Sepolia (EAS 1.4.1-beta.3, vendored in the Optimism
# monorepo), which the IEAS interface does not declare.
EAS_ERRORS = [
    {"type": "error", "name": name, "inputs": []}
    for name in (
        "AccessDenied",
        "AlreadyRevoked",
        "InsufficientValue",
        "InvalidAttestation",
        "InvalidExpirationTime",
        "InvalidSchema",
        "Irrevocable",
        "NotFound",
        "NotPayable",
        "WrongSchema",
    )
]


@cache
def load(name: str) -> list[dict[str, Any]]:
    """The ABI of ``name`` (one of ``SOURCES``)."""
    text = resources.files(__package__).joinpath(f"{name}.json").read_text(encoding="utf-8")
    return json.loads(text)


def from_foundry(out_dir: Path, name: str) -> list[dict[str, Any]]:
    source, contract = SOURCES[name]
    artifact = json.loads((out_dir / source / f"{contract}.json").read_text(encoding="utf-8"))
    return artifact["abi"]


def render(abi: list[dict[str, Any]]) -> str:
    return json.dumps(abi, indent=2, sort_keys=True) + "\n"


def main(argv: list[str]) -> int:  # pragma: no cover - a developer tool, run by hand
    if len(argv) != 1:
        print("usage: python -m orbit_watch.chain.abi <contracts/out>", file=sys.stderr)
        return 2
    out_dir = Path(argv[0])
    here = Path(__file__).parent
    for name in SOURCES:
        (here / f"{name}.json").write_text(render(from_foundry(out_dir, name)), encoding="utf-8")
        print(f"wrote {name}.json")
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main(sys.argv[1:]))

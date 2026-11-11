"""Deterministic JSON output and hashing.

Reports and generated datasets must be byte-identical for identical input,
across runs, machines and supported Python versions. Floats are rounded by
the code that produces them; this module only fixes key order, separators,
encoding and the trailing newline.
"""

from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path
from typing import Any


def _clean(value: Any) -> Any:
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ValueError("non-finite float in canonical JSON")
        if value == 0.0:
            return 0.0  # normalise -0.0
        return value
    if isinstance(value, dict):
        return {str(k): _clean(v) for k, v in value.items()}
    if isinstance(value, list | tuple):
        return [_clean(v) for v in value]
    return value


def dumps_pretty(document: Any, *, sort_keys: bool = True) -> str:
    """Human-readable, deterministic JSON with a trailing newline."""
    return json.dumps(_clean(document), indent=2, sort_keys=sort_keys, ensure_ascii=False) + "\n"


def dumps_compact(document: Any) -> str:
    """Compact canonical JSON (sorted keys, no whitespace) used for hashing."""
    return json.dumps(_clean(document), sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: str | Path) -> str:
    return sha256_bytes(Path(path).read_bytes())


def write_text(path: str | Path, text: str) -> None:
    """Write UTF-8 text with LF line endings regardless of platform."""
    Path(path).write_bytes(text.encode("utf-8"))

"""API keys (decision P-04): one key per party and role, stored only as a hash.

A key is ``ow_`` followed by 43 random URL-safe characters (256 bits). The
database keeps its SHA-256, the party and the role; the key itself is shown
once, when it is created. High-entropy random keys need no slow password hash.
"""

from __future__ import annotations

import secrets
from dataclasses import dataclass
from datetime import datetime

from orbit_watch.canonical import sha256_bytes
from orbit_watch.storage import Database
from orbit_watch.timeutil import format_utc

ROLES = ("requester", "station", "reviewer", "admin")
PREFIX = "ow_"


class ApiKeyError(ValueError):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


@dataclass(frozen=True)
class Principal:
    party: str
    role: str


def key_hash(key: str) -> str:
    return sha256_bytes(key.encode("utf-8"))


def create_key(db: Database, party: str, role: str, now: datetime) -> str:
    """Create a key and return it. It cannot be shown again."""
    if role not in ROLES:
        raise ApiKeyError("invalid_role", f"role must be one of {', '.join(ROLES)}")
    if not party.startswith(f"{role}:") or len(party) <= len(role) + 1 or len(party) > 128:
        raise ApiKeyError("invalid_party", f"a {role} key needs a party named '{role}:<name>'")
    key = PREFIX + secrets.token_urlsafe(32)
    db.execute(
        "INSERT INTO api_keys (key_hash, party, role, created_at) VALUES (?, ?, ?, ?)",
        (key_hash(key), party, role, format_utc(now)),
    )
    return key


def lookup(db: Database, key: str) -> Principal | None:
    if not key.startswith(PREFIX):
        return None
    rows = db.query(
        "SELECT party, role FROM api_keys WHERE key_hash = ? AND revoked = 0", (key_hash(key),)
    )
    return Principal(rows[0]["party"], rows[0]["role"]) if rows else None


def revoke_party(db: Database, party: str) -> int:
    """Revoke every key of a party. Returns how many were revoked."""
    cursor = db.execute("UPDATE api_keys SET revoked = 1 WHERE party = ? AND revoked = 0", (party,))
    return cursor.rowcount

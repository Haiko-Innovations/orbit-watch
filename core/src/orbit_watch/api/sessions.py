"""Signing in with a wallet (phase 3, step 3.2; decisions P3-04, P3-05).

The browser signs in with Sign-In with Ethereum (ERC-4361). The service writes the whole
message: its own origin, the wallet's address, a statement naming the party, the chain, a
single-use nonce and a short expiry. The wallet signs it (ERC-191, as ``personal_sign``),
and the service checks that the message is one it wrote, for that origin and that address,
still unused and unexpired, and that the signature is the address's. It then sets a
session cookie that scripts cannot read. The cookie is random; the database keeps only its
SHA-256, as for API keys.

Times here are wall-clock times: a wallet shows them to its user, and a session lasts real
hours even when the service follows a local chain whose clock is elsewhere.

Only externally owned accounts sign in (ERC-191 recovery); contract accounts (ERC-1271)
come later.
"""

from __future__ import annotations

import re
import secrets
import string
from dataclasses import dataclass
from datetime import datetime, timedelta
from urllib.parse import urlsplit

from orbit_watch.canonical import sha256_bytes
from orbit_watch.storage import Database
from orbit_watch.timeutil import format_utc, parse_utc

COOKIE = "ow_session"
CHALLENGE_LIFETIME = timedelta(minutes=5)
SESSION_LIFETIME = timedelta(hours=12)
NONCE_ALPHABET = string.ascii_letters + string.digits
# Parties that sign up themselves (P3-05): a role, a colon and a plain name.
SIGN_UP_ROLES = ("requester", "station")
SIGN_UP_PARTY = re.compile(r"^(requester|station):[A-Za-z0-9][A-Za-z0-9._-]{1,62}$")


class SessionError(ValueError):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


@dataclass(frozen=True)
class Session:
    party: str
    role: str
    address: str
    origin: str
    expires_at: datetime

    def view(self) -> dict[str, str]:
        return {
            "party": self.party,
            "role": self.role,
            "address": self.address,
            "expires_at": format_utc(self.expires_at),
        }


def normalise_origin(origin: str) -> str:
    """``scheme://host[:port]``, lower case, without a path; refuses anything else."""
    parts = urlsplit(origin.strip())
    if parts.scheme not in ("http", "https") or not parts.netloc or parts.path not in ("", "/"):
        raise SessionError("invalid_origin", f"not a web origin: {origin!r}")
    if parts.query or parts.fragment or "@" in parts.netloc:
        raise SessionError("invalid_origin", f"not a web origin: {origin!r}")
    return f"{parts.scheme}://{parts.netloc}".lower()


def checked_address(address: object) -> str:
    from eth_utils import is_address, to_checksum_address  # the evm extra

    if not isinstance(address, str) or not is_address(address):
        raise SessionError("invalid_address", f"not an address: {address!r}")
    return to_checksum_address(address)


def siwe_message(
    *,
    origin: str,
    address: str,
    statement: str,
    chain_id: int,
    nonce: str,
    issued_at: datetime,
    expires_at: datetime,
) -> str:
    """An ERC-4361 message, laid out as viem's ``createSiweMessage`` lays it out. The scheme
    is always written, because a wallet assumes https when it is missing."""
    if "\n" in statement:
        raise ValueError("an ERC-4361 statement has no line breaks")
    return (
        f"{origin} wants you to sign in with your Ethereum account:\n"
        f"{address}\n\n"
        f"{statement}\n\n"
        f"URI: {origin}/\n"
        f"Version: 1\n"
        f"Chain ID: {chain_id}\n"
        f"Nonce: {nonce}\n"
        f"Issued At: {format_utc(issued_at)}\n"
        f"Expiration Time: {format_utc(expires_at)}"
    )


def statement(party: str, sign_up: bool) -> str:
    action = "Sign up to Orbit Watch as" if sign_up else "Sign in to Orbit Watch as"
    return f"{action} {party}. Testnet only, no real value. Signing sends no transaction."


def issue_challenge(
    db: Database,
    *,
    origin: str,
    address: str,
    party: str,
    sign_up: bool,
    chain_id: int,
    now: datetime,
) -> str:
    """Write and remember a message for ``address`` to sign at ``origin``."""
    nonce = "".join(secrets.choice(NONCE_ALPHABET) for _ in range(17))
    expires = now + CHALLENGE_LIFETIME
    message = siwe_message(
        origin=origin,
        address=address,
        statement=statement(party, sign_up),
        chain_id=chain_id,
        nonce=nonce,
        issued_at=now,
        expires_at=expires,
    )
    db.execute(
        "INSERT INTO signin_challenges (nonce, address, origin, message, sign_up_party, "
        "issued_at, expires_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
        (
            nonce,
            address,
            origin,
            message,
            party if sign_up else None,
            format_utc(now),
            format_utc(expires),
        ),
    )
    return message


@dataclass(frozen=True)
class Signed:
    """A message the service wrote, signed by its address."""

    address: str
    sign_up_party: str | None
    message: str
    signature: str


def redeem(
    db: Database, *, origin: str, message: object, signature: object, now: datetime
) -> Signed:
    """Check a signed message and use it up. Refuses messages the service did not write,
    for another origin, used, expired, or not signed by their address."""
    if not isinstance(message, str) or not isinstance(signature, str):
        raise SessionError("invalid_signature", "give the message and its signature")
    found = re.search(r"^Nonce: ([A-Za-z0-9]{8,64})$", message, re.MULTILINE)
    rows = (
        db.query("SELECT * FROM signin_challenges WHERE nonce = ?", (found.group(1),))
        if found
        else []
    )
    if not rows or rows[0]["message"] != message:
        raise SessionError("unknown_message", "this is not a sign-in message the service wrote")
    row = rows[0]
    if row["origin"] != origin:
        raise SessionError("wrong_origin", f"this message was written for {row['origin']}")
    if row["used_at"] is not None:
        raise SessionError("message_used", "this sign-in message was used already")
    if now >= parse_utc(row["expires_at"]):
        raise SessionError("message_expired", "this sign-in message has expired: ask for a new one")
    from eth_account import Account  # the evm extra
    from eth_account.messages import encode_defunct

    try:
        signer = Account.recover_message(encode_defunct(text=message), signature=signature)
    except Exception:  # any malformed signature
        signer = None
    if signer != row["address"]:
        raise SessionError("bad_signature", f"the signature is not {row['address']}'s")
    db.execute(
        "UPDATE signin_challenges SET used_at = ? WHERE nonce = ?", (format_utc(now), row["nonce"])
    )
    return Signed(row["address"], row["sign_up_party"], message, signature)


def token_hash(token: str) -> str:
    return sha256_bytes(token.encode("utf-8"))


def create_session(
    db: Database, *, party: str, role: str, address: str, origin: str, now: datetime
) -> tuple[str, Session]:
    """A new session; returns the cookie value, shown only to the browser that signed."""
    token = secrets.token_urlsafe(32)
    expires = now + SESSION_LIFETIME
    db.execute(
        "INSERT INTO sessions (token_hash, party, role, address, origin, created_at, expires_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?)",
        (token_hash(token), party, role, address, origin, format_utc(now), format_utc(expires)),
    )
    return token, Session(party, role, address, origin, expires)


def lookup(db: Database, token: str | None, now: datetime) -> Session | None:
    if not token or len(token) > 128:
        return None
    rows = db.query(
        "SELECT * FROM sessions WHERE token_hash = ? AND ended_at IS NULL", (token_hash(token),)
    )
    if not rows:
        return None
    row = rows[0]
    expires = parse_utc(row["expires_at"])
    if now >= expires:
        return None
    return Session(row["party"], row["role"], row["address"], row["origin"], expires)


def end(db: Database, token: str | None, now: datetime) -> bool:
    if not token:
        return False
    cursor = db.execute(
        "UPDATE sessions SET ended_at = ? WHERE token_hash = ? AND ended_at IS NULL",
        (format_utc(now), token_hash(token)),
    )
    return cursor.rowcount > 0


def party_taken(db: Database, party: str) -> bool:
    """Whether a party of this name exists: it has an API key or a wallet."""
    return bool(
        db.query("SELECT 1 FROM api_keys WHERE party = ? LIMIT 1", (party,))
        or db.query("SELECT 1 FROM wallets WHERE party = ? LIMIT 1", (party,))
    )

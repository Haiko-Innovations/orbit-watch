"""Limits against abuse (phase 4, step 4.3; decision P4-08).

The service counts, in its database, the calls that cost it or others the most: sign-in
and sign-up attempts, new requests, uploads and quality meter runs, and every call of
the public pages, which anyone may make without a key. It counts per IP
address and, for calls with a key or a session, per party, in fixed windows. A call over
a limit is refused with ``429 Too Many Requests`` and ``Retry-After``, before it does
anything; a refused call is not counted. Counting happens in a transaction of its own, so
a call that fails afterwards still counts: failed sign-ins are what a limit is for.

An IP address is never stored: the service keeps a SHA-256 of it keyed with a random key
of the database, and deletes every count when its window is over. IPv6 addresses count
per /64 network, which one host or home usually has to itself.

Which address is the caller's: the connection's own, or, behind a proxy the service
trusts, the header that proxy sets (``client_ip_header``: ``x-real-ip`` on Vercel). Of a
list, the last entry counts, the one the nearest proxy added.

The limits are settings (``ORBIT_WATCH_LIMITS``): ``off``, or a JSON object that changes
some of the defaults, such as ``{"quality": {"ip": [60, 3600]}, "upload": {"party": null}}``.
"""

from __future__ import annotations

import hashlib
import ipaddress
import json
import math
from dataclasses import dataclass
from typing import Any

from orbit_watch.storage import Database


@dataclass(frozen=True)
class Rule:
    """At most ``count`` calls per window of ``seconds``."""

    count: int
    seconds: int

    def to_document(self) -> list[int]:
        return [self.count, self.seconds]


# The defaults (decision D-36): generous for a person, tight for a script.
DEFAULTS: dict[str, dict[str, Rule | None]] = {
    # POST /v1/session/challenge and POST /v1/session
    "sign_in": {"ip": Rule(30, 600), "party": None},
    # a challenge that signs up a new party
    "sign_up": {"ip": Rule(10, 3600), "party": None},
    # POST /v1/requests
    "new_request": {"ip": Rule(60, 3600), "party": Rule(20, 3600)},
    # POST /v1/requests/{id}/deliveries
    "upload": {"ip": Rule(60, 3600), "party": Rule(20, 3600)},
    # POST /v1/public/quality
    "quality": {"ip": Rule(30, 3600), "party": None},
    # GET /v1/public/... and /v1/chain: pages anyone may read, without a key
    "public": {"ip": Rule(600, 600), "party": None},
}
SUBJECTS = ("ip", "party")


class RateLimited(Exception):
    """A call over a limit: ``429`` with ``Retry-After``."""

    code = "rate_limited"

    def __init__(self, name: str, subject: str, rule: Rule, retry_after: int):
        per = "IP address" if subject == "ip" else "party"
        super().__init__(
            f"too many calls ({name}): at most {rule.count} per {rule.seconds} seconds per "
            f"{per}; try again in {retry_after} seconds"
        )
        self.retry_after = retry_after


class LimitsError(ValueError):
    pass


class Limits:
    """The limits a service applies."""

    def __init__(self, rules: dict[str, dict[str, Rule | None]] | None = None):
        self.rules = {name: dict(subjects) for name, subjects in (rules or DEFAULTS).items()}
        self._key: str | None = None

    @classmethod
    def parse(cls, text: str | None) -> Limits | None:
        """The limits a setting names: the defaults when empty, None for ``off``, or the
        defaults changed by a JSON object."""
        if text is None or not text.strip():
            return cls()
        if text.strip().lower() == "off":
            return None
        try:
            document = json.loads(text)
        except json.JSONDecodeError as error:
            raise LimitsError(f"the limits are not JSON: {error}") from None
        if not isinstance(document, dict):
            raise LimitsError('the limits must be "off" or a JSON object')
        rules = {name: dict(subjects) for name, subjects in DEFAULTS.items()}
        for name, subjects in document.items():
            if name not in rules:
                raise LimitsError(f"no such limit: {name} (known: {', '.join(rules)})")
            if not isinstance(subjects, dict) or not set(subjects) <= set(SUBJECTS):
                raise LimitsError(f"{name}: give an object with ip and/or party")
            for subject, value in subjects.items():
                rules[name][subject] = _rule(name, subject, value)
        return cls(rules)

    def describe(self) -> dict[str, Any]:
        return {
            name: {s: (r.to_document() if r else None) for s, r in subjects.items()}
            for name, subjects in self.rules.items()
        }

    def _subject_key(self, db: Database) -> str:
        if self._key is None:
            self._key = db.query("SELECT limit_key FROM service_state WHERE id = 1")[0]["limit_key"]
        return self._key

    def hit(self, db: Database, *names: str, ip: str | None, party: str | None, now: float) -> None:
        """Count one call against each of ``names`` for ``ip`` and ``party``, or raise
        ``RateLimited`` and count nothing. In the caller's transaction."""
        checks = []
        for name in names:
            rules = self.rules.get(name, {})
            if rules.get("ip") and ip is not None:
                checks.append((name, "ip", "ip:" + self._hashed(db, ip), rules["ip"]))
            if rules.get("party") and party is not None:
                checks.append((name, "party", "party:" + party, rules["party"]))
        if not checks:
            return
        moment = math.floor(now)
        db.execute("DELETE FROM rate_limits WHERE expires_at <= ?", (moment,), state=False)
        windows = []
        for name, kind, subject, rule in checks:
            start = moment - moment % rule.seconds
            rows = db.query(
                "SELECT hits FROM rate_limits WHERE name = ? AND subject = ? AND window_start = ?",
                (name, subject, start),
            )
            if rows and rows[0]["hits"] >= rule.count:
                raise RateLimited(name, kind, rule, max(1, start + rule.seconds - moment))
            windows.append((name, subject, start, start + rule.seconds))
        for name, subject, start, end in windows:
            db.execute(
                "INSERT INTO rate_limits (name, subject, window_start, hits, expires_at) "
                "VALUES (?, ?, ?, 1, ?) ON CONFLICT (name, subject, window_start) "
                "DO UPDATE SET hits = rate_limits.hits + 1",
                (name, subject, start, end),
                state=False,
            )

    def _hashed(self, db: Database, ip: str) -> str:
        key = self._subject_key(db).encode("ascii")
        return hashlib.sha256(key + b"|" + network_of(ip).encode("utf-8")).hexdigest()


def _rule(name: str, subject: str, value: Any) -> Rule | None:
    if value is None:
        return None
    if (
        not isinstance(value, list)
        or len(value) != 2
        or not all(isinstance(v, int) and not isinstance(v, bool) and v > 0 for v in value)
    ):
        raise LimitsError(f"{name}.{subject}: give [calls, seconds], both positive, or null")
    return Rule(value[0], value[1])


def network_of(address: str) -> str:
    """What one caller counts as: an IPv4 address, or an IPv6 address's /64 network."""
    try:
        parsed = ipaddress.ip_address(address.strip())
    except ValueError:
        return address.strip()  # not an address (a test client): counted as it is
    if isinstance(parsed, ipaddress.IPv6Address):
        if parsed.ipv4_mapped is not None:
            return str(parsed.ipv4_mapped)
        return str(ipaddress.IPv6Network((parsed, 64), strict=False))
    return str(parsed)


def client_ip(header_value: str | None, peer: str | None) -> str | None:
    """The caller's address: the trusted proxy's header (its last entry), or the peer."""
    if header_value:
        last = header_value.split(",")[-1].strip()
        if last:
            return last
    return peer

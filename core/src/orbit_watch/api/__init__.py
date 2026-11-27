"""The phase 1 HTTP API (step 1.6), built on Starlette (decision D-16).

Every call except ``GET /v1/health`` and the public ones needs an API key
(``Authorization: Bearer ow_...``) or, in the browser, a session from signing in with
the party's wallet (step 3.2, ``api.sessions``). Keys belong to one party and one role
(decision P-04):

* ``requester``: create, open, fund and cancel requests, challenge results;
* ``station``: reserve requests, deliver observation files, challenge results;
* ``reviewer``: list review tasks and answer them;
* ``admin``: grant points, create keys, apply deadlines; and, in the administrator view
  (step 3.7), see every request, transaction, conflict and event, prepare reviewer registry
  changes for the Safe to propose, and make SIMULATED observation files.

A station key can deliver, but it can never move points.

Every call that changes something needs an ``Idempotency-Key`` header. The
first successful response is stored with the change, in the same database
transaction. Repeating the call with the same key returns that response and
changes nothing; reusing the key for a different call is refused
(``key_reused``). Refused calls are not stored, because they change nothing.

One lock serialises all calls, in this process and, through PostgreSQL's
advisory lock, across every process that shares the database (step 4.2): each
keeps a copy of the state in memory and reloads it when another one changed it.

**On a testnet chain** (step 2.6) the API never sees a party's key. A change
to a funded request is answered with ``202 Accepted`` and the unsigned
transactions to sign (``sign``); the party signs and sends them with its own
wallet and reports each hash (``POST /v1/transactions``). The service follows
the chain, which decides: every call first applies the escrow's new events.
Every chain-related answer carries a ``notice`` ("Base Sepolia testnet, no
real value").

**Public pages** (step 3.7) need no key either: the station quality meter
(``POST /v1/public/quality``) scores an observation file without keeping it, and the
attestation browser (``GET /v1/public/attestations``) lists the EAS attestations of the
requests the service follows, with EAS Scan links on Base Sepolia.

**Operations** (step 4.6): in **read-only mode** (``serve --read-only``) every change is
refused with ``503 read_only``, the follower waits, and reading, the public pages and
signing in still work. With a backup token, a schedule takes an encrypted **backup** of the
database (``GET /v1/internal/backup``, ``orbit_watch.backup``).

**The web application** (step 3.1): given the directory of its build, the API
serves it at ``/`` on its own origin, so the browser talks to one server only.
Every response carries a strict content security policy: the pages load only
their own files and talk only to this API (decision D-25).
"""

from __future__ import annotations

import hmac
import json
import logging
import secrets
import threading
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from importlib import resources
from pathlib import Path
from typing import Any

from starlette.applications import Starlette
from starlette.concurrency import run_in_threadpool
from starlette.middleware import Middleware
from starlette.requests import Request
from starlette.responses import JSONResponse, Response, StreamingResponse
from starlette.routing import Mount, Route
from starlette.staticfiles import StaticFiles

from orbit_watch import __version__, allowlist, backup, orbit_follower, orbits, station_place, sun
from orbit_watch import lifecycle as lc
from orbit_watch.api import keys, privacy, sessions
from orbit_watch.api.limits import Limits, RateLimited, client_ip
from orbit_watch.api.sessions import SessionError
from orbit_watch.canonical import dumps_pretty, sha256_bytes
from orbit_watch.catalog import CatalogError
from orbit_watch.chain import WALLET_PREFIX, ChainError
from orbit_watch.fetch import FetchError
from orbit_watch.schema import validate
from orbit_watch.service import RequestService, ServiceError, method_version
from orbit_watch.settlement import SettlementError
from orbit_watch.timeutil import format_utc, parse_utc

# Every body, whatever the route: under Vercel's 4.5 MB for a function (decision P4-08).
MAX_BODY_BYTES = 4_000_000
# The public quality meter scores one observation file at a time, outside the service lock.
MAX_QUALITY_BYTES = 2 * 1024 * 1024
MAX_SIMULATED_PASSES = 6
# The web application loads only its own files and talks only to this API (decision
# D-25). Wallet extensions inject their providers themselves; EIP-6963 wallet icons are
# data: URLs.
CONTENT_SECURITY_POLICY = "; ".join(
    [
        "default-src 'self'",
        "script-src 'self'",
        "style-src 'self'",
        "img-src 'self' data:",
        "connect-src 'self'",
        "object-src 'none'",
        "base-uri 'none'",
        "form-action 'self'",
        "frame-ancestors 'none'",
    ]
)
SECURITY_HEADERS = [
    (b"content-security-policy", CONTENT_SECURITY_POLICY.encode("ascii")),
    (b"x-content-type-options", b"nosniff"),
    (b"referrer-policy", b"no-referrer"),
    (b"cross-origin-opener-policy", b"same-origin"),
]
TERMS_FIELDS = {
    "delivery_deadline": str,
    "reservation_hours": (int, float),
    "challenge_period_hours": (int, float),
    "review_hours": (int, float),
    "verification_timeout_hours": (int, float),
    "embargo_days": int,
}

# HTTP status for each stable error code. Anything else is 422.
STATUS = {
    "unauthorized": 401,
    "forbidden_origin": 403,
    "wrong_origin": 403,
    "unknown_wallet": 404,
    "no_profile": 404,
    "no_reference_orbit": 409,
    "profile_required": 409,
    "real_request": 409,
    "not_reserved_by_you": 409,
    "party_taken": 409,
    "forbidden_role": 403,
    "replay_admin_only": 403,
    "replay_station_only": 403,
    "reference_orbit_pending": 409,
    "not_requester": 403,
    "not_a_party": 403,
    "not_your_task": 403,
    "not_yourself": 403,
    "not_your_transaction": 403,
    "unknown_request": 404,
    "unknown_task": 404,
    "no_report": 404,
    "unknown_file": 404,
    "not_found": 404,
    "unknown_transaction": 404,
    "not_on_chain": 404,
    "forbidden_in_status": 409,
    "already_voted": 409,
    "already_funded": 409,
    "already_settled": 409,
    "duplicate_request": 409,
    "key_reused": 409,
    "sign_on_chain": 409,
    "already_on_chain": 409,
    "no_wallet": 409,
    "wallet_already_set": 409,
    "address_taken": 409,
    "nothing_to_withdraw": 409,
    "transaction_pending": 409,
    "insufficient_balance": 409,
    "points_not_used": 409,
    "already_reviewer": 409,
    "already_allowed": 409,
    "not_a_reviewer": 409,
    "registry_full": 409,
    "no_timelock": 409,
    "unknown_scenario": 404,
    "unknown_profile": 404,
    "unknown_target": 404,
    "too_large": 413,
    "rate_limited": 429,
    "verification_unavailable": 503,
    "chain_unavailable": 503,
    "read_only": 503,
}
PASS_LIST_SPAN = timedelta(days=7)  # a station's pass list covers at most this (D-58)
# A pass list plans observations: a set up to a week from the window predicts its passes
# to within seconds, so it is not held to the verification method's age limit (D-69).
PASS_LIST_AGE_DAYS = 7.0
READ_ONLY_MESSAGE = (
    "the service is read-only for maintenance: nothing can be changed right now, but "
    "everything can be read"
)


class ApiError(Exception):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


def _error_response(code: str, message: str) -> JSONResponse:
    return JSONResponse(
        {"error": {"code": code, "message": message}}, status_code=STATUS.get(code, 422)
    )


async def _handle_api_error(request: Request, exc: Exception) -> Response:
    code = getattr(exc, "code", "invalid")
    response = _error_response(code, str(exc))
    retry_after = getattr(exc, "retry_after", None)
    if retry_after is not None:
        response.headers["Retry-After"] = str(retry_after)
    return response


def _signs_up(body: bytes) -> bool:
    """Whether a sign-in challenge asks to sign up a new party."""
    try:
        document = json.loads(body.decode("utf-8")) if body else {}
    except (UnicodeDecodeError, json.JSONDecodeError):
        return False
    return isinstance(document, dict) and document.get("sign_up") is not None


def _json(body: bytes) -> dict[str, Any]:
    try:
        document = json.loads(body.decode("utf-8")) if body else {}
    except (UnicodeDecodeError, json.JSONDecodeError):
        raise ApiError("invalid_body", "the body is not UTF-8 JSON") from None
    if not isinstance(document, dict):
        raise ApiError("invalid_body", "the body must be a JSON object")
    return document


def _utc_field(document: dict[str, Any], name: str) -> datetime:
    try:
        return parse_utc(_field(document, name, str))
    except ValueError:
        raise ApiError("invalid_body", f"field {name!r} is not a UTC time") from None


def _field(document: dict[str, Any], name: str, kind: type | tuple[type, ...]) -> Any:
    value = document.get(name)
    if not isinstance(value, kind) or (isinstance(value, bool) and kind is not bool):
        raise ApiError("invalid_body", f"field {name!r} is missing or has the wrong type")
    return value


def _request_and_terms(document: dict[str, Any]) -> tuple[bytes, dict[str, Any]]:
    """A request document and its terms from a body ``{"request": …, "terms": …}``."""
    request_document = _field(document, "request", dict)
    terms = document.get("terms", {})
    if not isinstance(terms, dict) or set(terms) - set(TERMS_FIELDS):
        raise ApiError("invalid_body", f"terms may only contain {', '.join(TERMS_FIELDS)}")
    options: dict[str, Any] = {}
    for name, kind in TERMS_FIELDS.items():
        if name in terms:
            value = _field(terms, name, kind)
            if name == "delivery_deadline":
                try:
                    value = parse_utc(value)
                except ValueError as error:
                    raise ApiError("invalid_body", str(error)) from None
            options[name] = value
    return dumps_pretty(request_document, sort_keys=False).encode("utf-8"), options


FOLLOW_MAX_AGE = 1800.0  # seconds: twice the 15-minute schedule (decision P4-06)
log = logging.getLogger("orbit_watch.api")


class Api:
    def __init__(
        self,
        service: RequestService,
        clock: Callable[[], datetime],
        *,
        origins: tuple[str, ...] = (),
        wall_clock: Callable[[], datetime] | None = None,
        follow_secret: str | None = None,
        follow_max_age: float = FOLLOW_MAX_AGE,
        limits: Limits | None = None,
        client_ip_header: str | None = None,
        station_decimals: int | None = None,
        read_only: bool = False,
        backup_token: str | None = None,
        backup_recipient: str | None = None,
        orbit_fetcher: orbit_follower.Fetcher | None = None,
    ):
        if service.storage is None:
            raise ValueError("the API needs a stored service (open_service)")
        self.service = service
        self.db = service.storage.db
        self.clock = clock
        self.chain = service.chain  # an orbit_watch.chain.link.ChainLink, or None
        self.lock = threading.Lock()
        # The web application's origins: where a browser may sign in from (step 3.2).
        self.origins = tuple(sessions.normalise_origin(o) for o in origins)
        # Sessions live in wall-clock time, whatever the chain's clock says.
        self.wall_clock = wall_clock or (lambda: datetime.now(tz=UTC))
        # The follower (step 4.2): the schedule's secret, and how old its last run may be.
        self.follow_secret = follow_secret or None
        self.follow_max_age = follow_max_age
        # Limits against abuse (step 4.3): None applies none.
        self.limits = limits
        self.client_ip_header = client_ip_header.lower() if client_ip_header else None
        # Station coordinates to this many decimals (step 4.4): None keeps them as given.
        self.station_decimals = station_decimals
        # Operations (step 4.6): read-only mode, and backups for a schedule with the token,
        # encrypted to the age public key.
        self.read_only = read_only
        if backup_token and not backup_recipient:
            raise ValueError("backups need the age public key they are encrypted to")
        if backup_recipient:
            backup.recipient(backup_recipient)  # checked now, not at the first backup
        self.backup_token = backup_token or None
        self.backup_recipient = backup_recipient or None
        # Reference orbits (step 5.4): the follower fetches them when this is given.
        self.orbit_fetcher = orbit_fetcher

    # ------------------------------------------------------------------ plumbing

    def _principal(self, request: Request, mutating: bool = False) -> keys.Principal:
        """The caller: an API key, or else a browser session. A change made with a session
        must come from the page it was signed in on (the browser sets ``Origin``)."""
        header = request.headers.get("authorization", "")
        if header:
            scheme, _, token = header.partition(" ")
            principal = keys.lookup(self.db, token.strip()) if scheme.lower() == "bearer" else None
            if principal is None:
                raise ApiError(
                    "unauthorized", "a valid API key is required (Authorization: Bearer)"
                )
            return principal
        _token, session = self._session(request, self.wall_clock())
        if session is None:
            raise ApiError(
                "unauthorized",
                "sign in with your wallet, or give an API key (Authorization: Bearer)",
            )
        if mutating and self._origin(request) != session.origin:
            raise ApiError("wrong_origin", f"this session belongs to {session.origin}")
        return keys.Principal(session.party, session.role)

    def _session(
        self, request: Request, now: datetime
    ) -> tuple[str | None, sessions.Session | None]:
        """The browser's session and its cookie's value. A session signed in over HTTPS
        counts only under its own cookie's name, so a cookie without the prefix, which
        another site could have planted, cannot carry it (step 4.7)."""
        for name in sessions.COOKIES:
            token = request.cookies.get(name)
            if not token:
                continue
            session = sessions.lookup(self.db, token, now)
            if session is not None and sessions.cookie_name(session.origin) == name:
                return token, session
        return None, None

    @staticmethod
    def _forget_cookies(response: Response) -> None:
        for name in sessions.COOKIES:
            response.delete_cookie(
                name,
                path="/",
                secure=name == sessions.SECURE_COOKIE,
                httponly=True,
                samesite="strict",
            )

    def _origin(self, request: Request) -> str:
        """The page's origin, which browsers send with every change: one of this service's."""
        origin = request.headers.get("origin", "")
        try:
            normalised = sessions.normalise_origin(origin)
        except SessionError:
            normalised = ""
        if normalised not in self.origins:
            raise ApiError(
                "forbidden_origin",
                f"{origin or 'a request without an Origin'} is not one of this service's web "
                "origins (orbit-watch serve --origin)",
            )
        return normalised

    @staticmethod
    def _require(principal: keys.Principal, *roles: str) -> None:
        if principal.role not in roles:
            raise ApiError(
                "forbidden_role",
                f"a {principal.role} key cannot do this (needs {' or '.join(roles)})",
            )

    def endpoint(
        self,
        work: Callable[..., Any],
        *,
        mutating: bool,
        store_response: Callable[[Any], Any] | None = None,
        limit: str | None = None,
    ):
        """Wrap a handler: authenticate, count against ``limit``, serialise, run in one
        transaction, idempotency. Bodies are at most ``MAX_BODY_BYTES`` (``BodyLimit``)."""

        async def handler(request: Request) -> Response:
            body = await request.body()
            return await run_in_threadpool(
                self._run, request, body, work, mutating, store_response, limit
            )

        return handler

    def caller_ip(self, request: Request) -> str | None:
        """The caller's IP address: the trusted proxy's header, or the connection's."""
        header = request.headers.get(self.client_ip_header) if self.client_ip_header else None
        return client_ip(header, request.client.host if request.client else None)

    def _limit_alone(self, name: str, request: Request) -> None:
        """``_limit`` for a call that does not hold the lock otherwise."""
        with self.lock:
            self._limit(request, None, name)

    def _limit(self, request: Request, party: str | None, *names: str) -> None:
        """Count one call against each of the limits ``names``, in a transaction of its
        own, so that it counts even if the call then fails; or refuse it, counting nothing
        (step 4.3). Under ``self.lock``."""
        if self.limits is None:
            return
        with self.db.transaction():
            self.limits.hit(
                self.db,
                *names,
                ip=self.caller_ip(request),
                party=party,
                now=self.wall_clock().timestamp(),
            )

    def _run(
        self,
        request: Request,
        body: bytes,
        work: Callable[..., Any],
        mutating: bool,
        store_response: Callable[[Any], Any] | None,
        limit: str | None = None,
    ) -> Response:
        if mutating and self.read_only:
            raise ApiError("read_only", READ_ONLY_MESSAGE)
        with self.lock:
            principal = self._principal(request, mutating)
            if limit is not None:
                self._limit(request, principal.party, limit)
            self._follow_chain()
            now = self.clock()
            if not mutating:
                # In a transaction too: under the lock, the copy of the state in memory is
                # checked against the database before anything is read (step 4.2).
                with self.db.transaction():
                    return self._respond(work(principal, request, body, now))
            key = request.headers.get("idempotency-key", "").strip()
            if not key or len(key) > 128:
                raise ApiError(
                    "idempotency_key_required",
                    "changes need an Idempotency-Key header (1 to 128 characters)",
                )
            request_hash = sha256_bytes(
                b"|".join(
                    [
                        request.method.encode(),
                        request.url.path.encode(),
                        request.url.query.encode(),
                        body,
                    ]
                )
            )
            try:
                # The key is looked up in the change's own transaction, under the lock: two
                # processes that get the same call never both make the change.
                with self.db.transaction():
                    moment = int(self.wall_clock().timestamp())
                    stored = self.db.query(
                        "SELECT request_hash, status_code, response_json, expires_at "
                        "FROM idempotency WHERE party = ? AND idempotency_key = ?",
                        (principal.party, key),
                    )
                    if stored and (stored[0]["expires_at"] or 0) <= moment:
                        # Remembered for a day only (step 4.4): after that, a new call.
                        self.db.execute(
                            "DELETE FROM idempotency WHERE party = ? AND idempotency_key = ?",
                            (principal.party, key),
                            state=False,
                        )
                        stored = []
                    if stored:
                        if stored[0]["request_hash"] != request_hash:
                            raise ApiError(
                                "key_reused",
                                "this Idempotency-Key was already used for a different call",
                            )
                        return JSONResponse(
                            json.loads(stored[0]["response_json"]),
                            status_code=stored[0]["status_code"],
                            headers={"Idempotent-Replayed": "true"},
                        )
                    status, payload = work(principal, request, body, now, key)
                    kept = store_response(payload) if store_response else payload
                    lifetime = int(privacy.IDEMPOTENCY_LIFETIME.total_seconds())
                    self.db.execute(
                        "INSERT INTO idempotency (party, idempotency_key, request_hash, "
                        "status_code, response_json, path, expires_at) "
                        "VALUES (?, ?, ?, ?, ?, ?, ?)",
                        (
                            principal.party,
                            key,
                            request_hash,
                            status,
                            json.dumps(kept),
                            request.url.path,
                            moment + lifetime,
                        ),
                    )
            except BaseException:
                self.service._reload()
                raise
            return JSONResponse(payload, status_code=status)

    def _follow_chain(self) -> None:
        """Apply the escrow's new events before anything else: the chain decides. Not in
        read-only mode, which changes nothing: reads show the chain as last followed."""
        if self.chain is None or self.read_only:
            return
        try:
            self.chain.sync()
        except Exception as error:  # the node is down, or answers nonsense
            raise ApiError("chain_unavailable", f"cannot read the chain: {error}") from None

    def _require_chain(self) -> Any:
        if self.chain is None:
            raise ApiError("not_on_chain", "this service does not run on a chain")
        return self.chain

    @staticmethod
    def _signing(prepared: Any) -> tuple[int, dict[str, Any]]:
        return 202, prepared.to_document()

    @staticmethod
    def _respond(result: Any) -> Response:
        if isinstance(result, Response):
            return result
        return JSONResponse(result)

    def _record_view(self, request_id: str) -> dict[str, Any]:
        record = self.service.records[request_id]
        view = {
            "summary": self.service.summary(request_id),
            "record": record.to_document(),
            "publication": self.service.publication(request_id, self.clock()),
        }
        if self.chain is not None:
            view["chain"] = self.chain.request_view(request_id)
        return view

    # ------------------------------------------------------------------ handlers

    # ------------------------------------------------------------------ the follower (4.2)

    def follow_once(self) -> dict[str, Any]:
        """The service's own work, without anyone calling ``tick`` (decision P4-06): apply
        the chain's new events and passed deadlines, attest results and settle what is
        decided. A schedule, a timer or ``serve --follow`` calls it; any number of processes
        may, since the database's lock makes them take turns."""
        with self.lock:
            self._follow_chain()
            with self.db.transaction():
                changed = self.service.tick(self.clock())
                sent = self.chain.follow_up() if self.chain is not None else []
                # What the service no longer needs goes too (step 4.4).
                privacy.sweep(self.db, self.wall_clock())
                followed = format_utc(self.wall_clock())
                # Not part of the state a process keeps in memory: no reload elsewhere.
                self.db.execute(
                    "UPDATE service_state SET followed_at = ? WHERE id = 1",
                    (followed,),
                    state=False,
                )
        result: dict[str, Any] = {"changed": changed, "sent": sent, "followed_at": followed}
        if self.chain is not None:
            result["synced_block"] = self.chain.synced_block()
            result["notice"] = self.chain.notice
        if self.orbit_fetcher is not None:
            result["reference_orbits"] = self.fetch_reference_orbits()
        return result

    def fetch_reference_orbits(self) -> list[dict[str, Any]]:
        """The follower's fetching of reference orbits (step 5.4, decision D-48): a few
        requests to CelesTrak or SatChecker, one at a time, outside the database's lock. The
        first answer that is not 200 with element sets stops its source until a person
        resumes it (``orbit_watch.orbit_follower``)."""
        fetcher = self.orbit_fetcher
        if fetcher is None:
            return []
        with self.lock, self.db.transaction():
            wants = orbit_follower.plan(
                self.db,
                self.service,
                self.wall_clock(),
                fetcher.requests_per_run,
                fetcher.groups,
            )
        done: list[dict[str, Any]] = []
        for want in wants:
            with self.lock, self.db.transaction():
                if not orbit_follower.claim(self.db, want, self.wall_clock()):
                    continue  # stopped by an earlier answer, or asked for by another process
            if done:
                fetcher.sleep(orbit_follower.PAUSE_S)
            try:
                if want.group:
                    body = orbit_follower.fetch_group(want, fetcher.opener)
                else:
                    records = orbit_follower.fetch(want, fetcher.opener)
            except FetchError as error:
                with self.lock, self.db.transaction():
                    stopped = orbit_follower.stop(self.db, want, error, self.wall_clock())
                if stopped:
                    log.warning("fetching reference orbits stopped: %s", error)
                    done.append({**want.public(), "stopped": str(error)})
                else:
                    log.warning("no answer; trying once more in two hours: %s", error)
                    done.append({**want.public(), "waiting": str(error)})
                continue
            try:
                with self.lock, self.db.transaction():
                    if want.group:
                        objects = self.service.keep_group(want.group, body, self.wall_clock())
                        result = {"objects": objects}
                    else:
                        kept, already = self.service.keep_element_sets(
                            records, want.source, self.wall_clock()
                        )
                        result = {"kept": len(kept), "already_kept": already}
                    orbit_follower.answered(self.db, want, self.wall_clock())
            except (CatalogError, ServiceError, ValueError, KeyError) as error:
                # An answer of 200 that the service cannot read stops the source too, and
                # says why, instead of failing every run (D-65).
                self.service._reload()
                unreadable = FetchError(f"could not read the answer: {error}", 200)
                with self.lock, self.db.transaction():
                    orbit_follower.stop(self.db, want, unreadable, self.wall_clock())
                log.warning("fetching reference orbits stopped: %s", unreadable)
                done.append({**want.public(), "stopped": str(unreadable)})
                continue
            done.append({**want.public(), **result})
        return done

    async def internal_follow(self, request: Request) -> Response:
        """``GET`` or ``POST /v1/internal/follow``, for a schedule: ``Authorization: Bearer``
        with the follower's secret. Without a secret configured there is no such route."""
        if self.follow_secret is None:
            raise ApiError("not_found", "the follower is not enabled on this service")
        scheme, _, token = request.headers.get("authorization", "").partition(" ")
        if scheme.lower() != "bearer" or not hmac.compare_digest(
            token.strip().encode(), self.follow_secret.encode()
        ):
            raise ApiError("unauthorized", "the follower's secret is required")
        if self.read_only:
            raise ApiError("read_only", f"{READ_ONLY_MESSAGE}; the follower waits")
        return JSONResponse(await run_in_threadpool(self.follow_once))

    def take_backup(self) -> bytes:
        """A backup of the database, encrypted to the backup's public key (step 4.6). In
        one transaction, under the lock that every change takes."""
        if self.backup_recipient is None:
            raise ApiError("not_found", "backups are not enabled on this service")
        with self.lock, self.db.transaction():
            archive = backup.take(self.db, self.wall_clock())
        encrypted = backup.encrypt(archive, self.backup_recipient)
        log.info("backup taken: %d bytes encrypted", len(encrypted))
        return encrypted

    async def internal_backup(self, request: Request) -> Response:
        """``GET /v1/internal/backup``, for a schedule: ``Authorization: Bearer`` with the
        backup token. The answer is the encrypted archive, streamed, so that it may be larger
        than a function's response limit. Without a token configured there is no such
        route."""
        if self.backup_token is None:
            raise ApiError("not_found", "backups are not enabled on this service")
        scheme, _, token = request.headers.get("authorization", "").partition(" ")
        if scheme.lower() != "bearer" or not hmac.compare_digest(
            token.strip().encode(), self.backup_token.encode()
        ):
            raise ApiError("unauthorized", "the backup token is required")
        data = await run_in_threadpool(self.take_backup)
        stamp = self.wall_clock().strftime("%Y%m%dT%H%M%SZ")
        chunk = 1024 * 1024
        return StreamingResponse(
            (data[i : i + chunk] for i in range(0, len(data), chunk)),
            media_type="application/octet-stream",
            headers={
                "Content-Disposition": f'attachment; filename="orbit-watch-{stamp}.tar.gz.age"',
                "Cache-Control": "no-store",
            },
        )

    def follower_status(self) -> dict[str, Any]:
        """When the follower of any process last ran, and whether that is recent enough."""
        with self.lock:
            row = self.db.query("SELECT followed_at FROM service_state WHERE id = 1")[0]
            synced = self.chain.synced_block() if self.chain is not None else None
        followed = row["followed_at"]
        age = None
        if followed is not None:
            age = (self.wall_clock() - parse_utc(followed)).total_seconds()
        return {
            "status": "never" if age is None else "ok" if age <= self.follow_max_age else "behind",
            "followed_at": followed,
            "age_seconds": None if age is None else round(age),
            "max_age_seconds": self.follow_max_age,
            "synced_block": synced,
        }

    def follower_health(self, request: Request) -> Response:
        """``GET /v1/health/follower``, for monitoring: 200 while the follower keeps up,
        503 when its last run is older than ``follow_max_age`` seconds, or it never ran."""
        document = self.follower_status()
        return JSONResponse(document, status_code=200 if document["status"] == "ok" else 503)

    def reference_orbits_status(self) -> dict[str, Any]:
        with self.lock:
            return orbit_follower.status(
                self.db, self.wall_clock(), enabled=self.orbit_fetcher is not None
            )

    def reference_orbits_health(self, request: Request) -> Response:
        """``GET /v1/health/reference-orbits``, for monitoring (step 5.4): 503 while the
        follower has stopped fetching from a source and waits for a person, 200 otherwise,
        and when the service does not fetch."""
        document = self.reference_orbits_status()
        return JSONResponse(document, status_code=503 if document["status"] == "stopped" else 200)

    def health(self, request: Request) -> Response:
        notice = "Local use without a chain. All bundled data is SIMULATED."
        if self.chain is not None:
            label = self.chain.notice
            notice = f"{label[:1].upper()}{label[1:]}. All bundled data is SIMULATED."
        return JSONResponse(
            {
                "status": "ok",
                "version": __version__,
                "notice": notice,
                "read_only": self.read_only,
            }
        )

    def create_request(self, principal, request, body, now, key):
        self._require(principal, "requester")
        document = _json(body)
        request_bytes, options = _request_and_terms(document)
        record = self.service.create(request_bytes, principal.party, now, **options)
        return 201, self._record_view(record.request_id)

    def admin_create_replay(self, principal, request, body, now, key):
        """A replay request (format 1.1) for a requester, who then publishes and funds it
        as usual (P5-10, D-51)."""
        self._require(principal, "admin")
        document = _json(body)
        requester = _field(document, "requester", str)
        if not requester.startswith("requester:") or len(requester) > 128:
            raise ApiError("invalid_body", "requester must be a party named 'requester:<name>'")
        request_bytes, options = _request_and_terms(document)
        record = self.service.create(
            request_bytes, requester, now, replay_by=principal.party, **options
        )
        return 201, self._record_view(record.request_id)

    def _requester_action(self, action: str):
        def work(principal, request, body, now, key):
            self._require(principal, "requester")
            request_id = request.path_params["request_id"]
            party = principal.party
            if action == "open":
                self.service.open(request_id, party, now)
            elif action == "cancel":
                if self.service.on_chain(request_id):
                    self.service._require_requester(request_id, party)
                    return self._signing(self.chain.prepare_cancel(request_id, party, now))
                self.service.cancel(request_id, party, now)
            else:
                document = _json(body)
                split = lc.RewardSplit(
                    _field(document, "observer", int),
                    _field(document, "reviewer", int),
                    document.get("platform_fee", 0),
                )
                if self.chain is not None:
                    self.service._require_requester(request_id, party)
                    return self._signing(self.chain.prepare_fund(request_id, party, split, now))
                self.service.fund(request_id, party, split, now)
            return 200, self._record_view(request_id)

        return work

    def reserve(self, principal, request, body, now, key):
        self._require(principal, "station")
        request_id = request.path_params["request_id"]
        self.service.check_reserve(request_id, principal.party)
        if self.service.on_chain(request_id):
            return self._signing(self.chain.prepare_reserve(request_id, principal.party, now))
        self.service.reserve(request_id, principal.party, now)
        return 200, self._record_view(request_id)

    def deliver(self, principal, request, body, now, key):
        self._require(principal, "station")
        request_id = request.path_params["request_id"]
        declared = request.headers.get("content-sha256")
        if declared and declared.lower() != sha256_bytes(body):
            raise ApiError("hash_mismatch", "the body does not match its Content-SHA256 header")
        fmt = request.query_params.get("format")
        if fmt not in (None, "json", "iod", "tdm"):
            raise ApiError("invalid_format", "format must be json, iod or tdm")
        sites = self._station_place(request_id, principal.party, body, fmt)
        if self.service.on_chain(request_id):
            prepared = self.chain.prepare_delivery(
                request_id, principal.party, body, now, fmt, sites
            )
            if prepared is not None:
                return self._signing(prepared)
            return 200, self._record_view(request_id)
        self.service.deliver(
            request_id, principal.party, body, now, observations_format=fmt, sites=sites
        )
        return 200, self._record_view(request_id)

    def _station_place(
        self, request_id: str, station: str, body: bytes, fmt: str | None
    ) -> bytes | None:
        """The station profile is the station's place for every format (P5-11, D-55): a
        JSON file must name its place, and an IOD or TDM file is placed there by the sites
        document returned. The public service needs a profile; without its setting, a
        station without one delivers as before. A replay delivers a published file as it
        is: its place was published with it, and verification needs it (D-51)."""
        if self.service.replay_of(request_id) is not None:
            self.service.check_delivery(request_id, station, body)
            return None
        found = self._profile(station)
        if found is None:
            if self.station_decimals is not None:
                raise ApiError(
                    "profile_required",
                    'register your station\'s profile first, on the page "Your station": '
                    "it is your station's place for every delivery",
                )
            return None
        profile = found["profile"]
        if found["place"] != "exact":  # a profile saved before the choice: to a kilometre
            profile = privacy.rounded_station(profile, self._kilometre())
        try:
            return station_place.sites_for(profile, body, fmt)
        except station_place.PlaceError as error:
            raise ApiError(error.code, str(error)) from None

    def challenge(self, principal, request, body, now, key):
        self._require(principal, "requester", "station")
        request_id = request.path_params["request_id"]
        reason = _field(_json(body), "reason", str)
        if self.service.on_chain(request_id):
            if not reason.strip():
                raise ApiError("reason_required", "a challenge must say why")
            return self._signing(
                self.chain.prepare_challenge(request_id, principal.party, reason, now)
            )
        self.service.challenge(request_id, principal.party, reason, now)
        return 200, self._record_view(request_id)

    def list_requests(self, principal, request, body, now):
        return {
            "requests": [
                {
                    "request_id": rid,
                    "requester": record.requester,
                    "title": json.loads(self.service.request_documents[rid]).get("title"),
                    "reserved_by": record.reserved_by,
                    "observer": record.observer,
                    "status": str(record.status),
                    "outcome": None if record.outcome is None else str(record.outcome),
                    "labels": self.service.labels(rid),
                }
                for rid, record in sorted(self.service.records.items())
            ]
        }

    def get_request(self, principal, request, body, now):
        request_id = request.path_params["request_id"]
        if request_id not in self.service.records:
            raise ApiError("unknown_request", f"no request {request_id!r}")
        view = self._record_view(request_id)
        if not self.service.can_read_request_data(request_id, principal.party, principal.role, now):
            # The reasons people wrote are for the request's parties and the administrators
            # until it is published (personal-data.md; step 4.7, ASVS 8.2.2).
            record = view["record"]
            record["challenge_reason"] = None
            record["vote_reasons"] = []
            view["reasons_hidden"] = True
        return view

    def get_report(self, principal, request, body, now):
        request_id = request.path_params["request_id"]
        if request_id not in self.service.records or not self.service.can_read_request_data(
            request_id, principal.party, principal.role, now
        ):
            raise ApiError("no_report", f"no report for {request_id!r} that you may read")
        report = self.service.report(request_id)
        return Response(report, media_type="application/json")

    def get_file(self, principal, request, body, now):
        sha256 = request.path_params["sha256"]
        if not self.service.can_read_file(sha256, principal.party, principal.role, now):
            raise ApiError("unknown_file", f"no file {sha256} that you may read")
        return Response(self.service.files[sha256], media_type="application/octet-stream")

    # ------------------------------------------------------------------ public (no key)

    def public(self, work: Callable[..., Any]):
        async def handler(request: Request) -> Response:
            return await run_in_threadpool(self._run_public, request, work)

        return handler

    def _run_public(self, request: Request, work: Callable[..., Any]) -> Response:
        with self.lock:
            self._limit(request, None, "public")  # anyone may call these (step 4.3)
            self._follow_chain()
            with self.db.transaction():
                return self._respond(work(request, self.clock()))

    # ------------------------------------------------------------------ sessions (step 3.2)

    def session_route(self, work: Callable[..., Any], *, limited: bool = False):
        """Sign-in calls: no key, no idempotency record, one transaction, wall-clock time.
        ``limited`` calls count against the sign-in limit, and sign-ups against the sign-up
        limit too (step 4.3)."""

        async def handler(request: Request) -> Response:
            body = await request.body()
            if len(body) > 64 * 1024:
                raise ApiError("too_large", "the body is larger than 64 KiB")
            return await run_in_threadpool(self._run_session, request, body, work, limited)

        return handler

    def _run_session(
        self, request: Request, body: bytes, work: Callable[..., Any], limited: bool = False
    ) -> Response:
        with self.lock:
            if limited:
                names = ("sign_in", "sign_up") if _signs_up(body) else ("sign_in",)
                self._limit(request, None, *names)
            with self.db.transaction():
                return self._respond(work(request, body, self.wall_clock()))

    def session_challenge(self, request, body, now):
        chain = self._require_chain()  # wallets belong to the chain
        origin = self._origin(request)
        document = _json(body)
        address = sessions.checked_address(document.get("address"))
        sign_up = document.get("sign_up")
        owner = chain.party_of(address)
        if sign_up is None:
            if owner.startswith(WALLET_PREFIX):
                raise ApiError(
                    "unknown_wallet",
                    f"{address} is no party's wallet yet: sign up, or register it with "
                    "orbit-watch wallet register",
                )
            party = owner
        else:
            if not isinstance(sign_up, dict):
                raise ApiError("invalid_body", "sign_up must be an object with a party")
            party = _field(sign_up, "party", str)
            if not sessions.SIGN_UP_PARTY.match(party):
                raise ApiError(
                    "invalid_party",
                    "sign up as requester:<name> or station:<name>: 2 to 63 letters, digits, "
                    "dots, dashes or underscores, starting with a letter or digit",
                )
            if sessions.party_taken(self.db, party):
                raise ApiError("party_taken", f"{party} already exists: choose another name")
            if not owner.startswith(WALLET_PREFIX):
                raise ApiError(
                    "address_taken", f"{address} is already {owner}'s wallet: sign in instead"
                )
        privacy.sweep(self.db, now)  # also where no follower runs (step 4.4)
        message = sessions.issue_challenge(
            self.db,
            origin=origin,
            address=address,
            party=party,
            sign_up=sign_up is not None,
            chain_id=chain.chain.chain_id,
            now=now,
        )
        return {"message": message, "party": party, "sign_up": sign_up is not None}

    def sign_in(self, request, body, now):
        chain = self._require_chain()
        origin = self._origin(request)
        document = _json(body)
        signed = sessions.redeem(
            self.db,
            origin=origin,
            message=document.get("message"),
            signature=document.get("signature"),
            now=now,
        )
        if signed.sign_up_party is not None:
            party = signed.sign_up_party
            if sessions.party_taken(self.db, party):
                raise ApiError("party_taken", f"{party} already exists: choose another name")
            chain.register_signed_up_wallet(
                party, signed.address, signed.message, signed.signature, now
            )
        else:
            party = chain.party_of(signed.address)
            if party.startswith(WALLET_PREFIX):
                raise ApiError("unknown_wallet", f"{signed.address} is no party's wallet")
        role = party.split(":", 1)[0]
        if role not in keys.ROLES:
            raise ApiError("forbidden_role", f"{party} cannot sign in")
        # A new sign-in ends the session this browser had (step 4.7, ASVS 7.2.4).
        previous, _ = self._session(request, now)
        sessions.end(self.db, previous, now)
        token, session = sessions.create_session(
            self.db, party=party, role=role, address=signed.address, origin=origin, now=now
        )
        response = JSONResponse({"session": session.view(), "notice": chain.notice})
        response.set_cookie(
            sessions.cookie_name(origin),
            token,
            max_age=int(sessions.SESSION_LIFETIME.total_seconds()),
            path="/",
            secure=origin.startswith("https://"),
            httponly=True,
            samesite="strict",
        )
        return response

    def get_session(self, request, body, now):
        """Who is signed in: the session, or null (not an error: a page asks on every load)."""
        _token, session = self._session(request, now)
        return {"session": None if session is None else session.view()}

    def sign_out(self, request, body, now):
        self._origin(request)
        token, _session = self._session(request, now)
        sessions.end(self.db, token, now)
        response = JSONResponse({"signed_out": True})
        self._forget_cookies(response)
        return response

    def end_sessions(self, request, body, now):
        """End every session of the signed-in party, in every browser (step 4.4)."""
        self._origin(request)
        _token, session = self._session(request, now)
        if session is None:
            raise ApiError("unauthorized", "sign in to end your sessions")
        ended = sessions.end_all(self.db, session.party)
        response = JSONResponse({"party": session.party, "ended": ended})
        self._forget_cookies(response)
        return response

    def public_requests(self, request, now):
        return {"requests": self.service.published(now)}

    def public_targets(self, request, now):
        """The objects requests may target: the allow-list (decisions D-05, D-49 and D-62),
        which is public. Each says whether it is SIMULATED and why it is on the list: the
        service's own list, CelesTrak's groups and SupGP sources with its operator's orbit,
        or an administrator's addition with its reason. ``simulated`` is true when every
        target is."""
        targets = list(self.service.targets().values())
        groups = self.service.allowlist_groups
        return {
            "targets": [t.public() for t in targets],
            "simulated": bool(targets) and all(t.simulated for t in targets),
            "description": (
                "Civilian objects only (decision D-05): the service's own list, CelesTrak's "
                f"groups {', '.join(allowlist.INCLUDED_GROUPS)}, the objects whose operators "
                "publish their orbits in CelesTrak's SupGP sources "
                f"{', '.join(allowlist.OPERATOR_SOURCES)}, and the objects an administrator "
                "added with a public reason, minus CelesTrak's groups "
                f"{', '.join(allowlist.EXCLUDED_GROUPS)} and names that match the patterns for "
                "military, intelligence and government security payloads, the navigation "
                "satellites of GPS, GLONASS and BeiDou among them (decisions D-49 and D-62)."
            ),
            "groups": [
                {
                    "group": group,
                    "data": "supgp" if allowlist.is_operator_source(group) else "gp",
                    "role": "include" if group in allowlist.INCLUDED else "exclude",
                    "fetched_at": groups[group]["fetched_at"] if group in groups else None,
                    "objects": len(groups[group]["members"]) if group in groups else None,
                }
                for group in allowlist.GROUPS
            ],
        }

    def public_reference_orbits(self, request, now):
        """The real element sets the service keeps, by name: object, epoch, source and
        SHA-256, never the elements (step 5.4, decision P5-05). ``?norad_id=`` picks one
        object."""
        value = request.query_params.get("norad_id")
        norad_id = None
        if value is not None:
            try:
                norad_id = int(value)
            except ValueError:
                raise ApiError("invalid_query", "norad_id must be a catalogue number") from None
        return {
            "element_sets": self.service.reference_orbits(norad_id),
            "note": (
                "Real element sets that the service verifies deliveries against, named but "
                "not served: fetch the same set from its source by the object and the epoch."
            ),
        }

    def admin_upload_element_sets(self, principal, request, body, now, key):
        """``POST /v1/admin/element-sets``: real element sets uploaded by hand, for example
        when CelesTrak cannot be reached (P5-02). The body is an orbit-watch/gp-catalog
        document, or CelesTrak's OMM JSON or CSV. They are labelled as uploaded."""
        self._require(principal, "admin")
        try:
            records = orbits.read_upload(body)
        except orbits.OrbitError as error:
            raise ApiError(error.code, str(error)) from None
        kept, already = self.service.keep_element_sets(
            records, "uploaded", self.wall_clock(), uploaded_by=principal.party
        )
        return 200, {"kept": [s.public() for s in kept], "already_kept": already}

    def admin_allow_object(self, principal, request, body, now, key):
        """``POST /v1/admin/allowlist``: an administrator adds a real object to the list,
        such as one of a large group that is not fetched, after checking its owner in the
        satellite catalogue (P5-08, D-49). The reason is public; the name patterns and the
        excluded groups still apply. ``operator_source``, such as ``SpaceX-E`` for a
        Starlink object, says that one SupGP query has shown its operator's orbit (P6-04,
        D-62)."""
        self._require(principal, "admin")
        document = _json(body)
        norad_id = _field(document, "norad_id", int)
        if norad_id < 1 or norad_id > 999_999_999:
            raise ApiError("invalid_body", "norad_id must be a catalogue number")
        operator_source = document.get("operator_source")
        if operator_source is not None and not isinstance(operator_source, str):
            raise ApiError("invalid_body", "operator_source must be a string")
        target = self.service.allow_object(
            norad_id,
            _field(document, "name", str),
            _field(document, "reason", str),
            principal.party,
            self.wall_clock(),
            operator_source,
        )
        return 200, target.public()

    def admin_disallow_object(self, principal, request, body, now, key):
        """``POST /v1/admin/allowlist/remove``: an administrator takes back an addition."""
        self._require(principal, "admin")
        norad_id = _field(_json(body), "norad_id", int)
        self.service.disallow_object(norad_id)
        target = self.service.targets().get(norad_id)
        return 200, {"norad_id": norad_id, "allowed": target is not None}

    def admin_resume_orbit_fetching(self, principal, request, body, now, key):
        """``POST /v1/admin/reference-orbits/resume``: a person has looked at why fetching
        from a source stopped, and lets the follower go on (step 5.4, D-48). ``ask_again``
        lists objects to ask for again, such as one that answered 404 and has public data
        now."""
        self._require(principal, "admin")
        document = _json(body)
        source = _field(document, "source", str)
        if source not in orbit_follower.SOURCES:
            raise ApiError(
                "invalid_body", f"source must be one of {', '.join(orbit_follower.SOURCES)}"
            )
        again = document.get("ask_again", [])
        if not isinstance(again, list) or not all(
            isinstance(n, int) and not isinstance(n, bool) and n > 0 for n in again
        ):
            raise ApiError("invalid_body", "ask_again must be a list of catalogue numbers")
        orbit_follower.resume(self.db, source, principal.party, self.wall_clock(), tuple(again))
        return 200, orbit_follower.status(
            self.db, self.wall_clock(), enabled=self.orbit_fetcher is not None
        )

    # ------------------------------------------------------------------ stations (step 3.5)

    def station_templates(self, request, now):
        """The built-in SIMULATED station profiles, as starting points for a station's own."""
        from orbit_watch.sim.simulator import builtin_profiles

        templates = []
        for name in builtin_profiles():
            text = resources.files("orbit_watch.data").joinpath("stations", f"{name}.json")
            templates.append(json.loads(text.read_text(encoding="utf-8")))
        return {"templates": templates}

    def _own_station(self, principal: keys.Principal, request: Request) -> str:
        party = request.path_params["party"]
        if principal.role != "admin" and principal.party != party:
            raise ApiError("not_yourself", "only the station itself and administrators see this")
        return party

    def _profile(self, party: str) -> dict[str, Any] | None:
        """A station's profile, and how precisely its place is published (D-54): ``place``
        is "exact" or "kilometre", and ``place_chosen`` is false for a profile saved before
        the choice existed, which stays at about a kilometre until its owner chooses."""
        rows = self.db.query("SELECT * FROM station_profiles WHERE party = ?", (party,))
        if not rows:
            return None
        return {
            "party": party,
            "profile": json.loads(rows[0]["profile_json"]),
            "updated_at": rows[0]["updated_at"],
            "place": rows[0]["place"] or "kilometre",
            "place_chosen": rows[0]["place"] is not None,
        }

    def _kilometre(self) -> int:
        """The decimals of "about a kilometre": the service's setting, or two."""
        if self.station_decimals is None:
            return privacy.STATION_DECIMALS
        return self.station_decimals

    def get_station_profile(self, principal, request, body, now):
        party = self._own_station(principal, request)
        found = self._profile(party)
        if found is None:
            raise ApiError("no_profile", f"{party} has no station profile yet")
        return found

    def put_station_profile(self, principal, request, body, now, key):
        self._require(principal, "station")
        party = self._own_station(principal, request)
        given = _json(body)
        document = _field(given, "profile", dict)
        place = given.get("place")
        if place not in privacy.PLACES:
            # The observer chooses, and nothing is chosen in advance (P5-11, D-54).
            raise ApiError(
                "place_required",
                'choose how precisely the station\'s place is published: "exact", or '
                '"kilometre" for about a kilometre',
            )
        problems = validate(document, "station-profile")
        if problems:
            raise ApiError("invalid_profile", "; ".join(problems[:5]))
        name = party.split(":", 1)[1]
        if document["station"]["id"] != name:
            raise ApiError("wrong_station", f"the profile's station id must be {name}")
        if place == "kilometre":
            document = privacy.rounded_station(document, self._kilometre())
        self.db.execute(
            "INSERT INTO station_profiles (party, profile_json, updated_at, place) "
            "VALUES (?, ?, ?, ?) "
            "ON CONFLICT (party) DO UPDATE SET profile_json = excluded.profile_json, "
            "updated_at = excluded.updated_at, place = excluded.place",
            (party, dumps_pretty(document, sort_keys=False), format_utc(now), place),
        )
        return 200, self._profile(party)

    def delete_station_profile(self, principal, request, body, now, key):
        """A station deletes its profile, and with it the copies of its answers that the
        idempotency records keep (step 4.4). Its deliveries stay: they are the record."""
        self._require(principal, "station", "admin")
        party = self._own_station(principal, request)
        deleted = self.db.execute("DELETE FROM station_profiles WHERE party = ?", (party,)).rowcount
        self.db.execute(
            "DELETE FROM idempotency WHERE party = ? AND path = ?",
            (party, request.url.path),
            state=False,
        )
        return 200, {"party": party, "deleted": deleted > 0}

    def request_passes(self, principal, request, body, now):
        """A station's passes of a request's object in its window, each with the part the
        station can see: lit by the Sun under a dark sky (P5-12, D-58). Over the station's
        profile place, above its instrument's elevation limit; the request has none. For a
        request that invites observers, or that the station reserved."""
        from orbit_watch.catalog import parse_catalog
        from orbit_watch.passes import passes
        from orbit_watch.sim.simulator import StationProfile

        self._require(principal, "station")
        request_id = request.path_params["request_id"]
        record = self.service.records.get(request_id)
        visible_to = (lc.Status.OPEN, lc.Status.FUNDED)
        if record is None or not (
            record.status in visible_to
            or (record.status == lc.Status.RESERVED and record.reserved_by == principal.party)
        ):
            raise ApiError(
                "unknown_request",
                f"no request {request_id!r} that invites observers or that you reserved",
            )
        found = self._profile(principal.party)
        if found is None:
            raise ApiError("no_profile", "register your station profile first")
        profile = found["profile"]
        if found["place"] != "exact":
            profile = privacy.rounded_station(profile, self._kilometre())
        station = StationProfile.from_document(profile)
        terms = record.terms
        end = min(terms.window_end, terms.window_start + PASS_LIST_SPAN)
        catalogue = self.service.simulation_catalog(
            terms.target_norad_id, terms.window_start, end, max_age_days=PASS_LIST_AGE_DAYS
        )
        found_passes = passes(
            parse_catalog(catalogue),
            terms.target_norad_id,
            station.station,
            terms.window_start,
            end,
            station.min_elevation_deg,
        )
        return {
            "request_id": request_id,
            "station": principal.party,
            "window_start": format_utc(terms.window_start),
            "window_end": format_utc(end),
            "window_cut": end < terms.window_end,
            "min_elevation_deg": station.min_elevation_deg,
            "dark_sky_deg": sun.DARK_SKY_SUN_ELEVATION_DEG,
            "place": found["place"],
            "reference_orbit": self.service.labels(request_id)["reference_orbit"],
            "passes": [found_pass.public() for found_pass in found_passes],
        }

    def simulate_observations(self, principal, request, body, now):
        """SIMULATED observations of a reserved request's target, made with the station's
        own profile, for it to deliver like any file (no state changes here). Only for a
        SIMULATED request: SIMULATED observations cannot fulfil a real one (D-50)."""
        from orbit_watch.catalog import parse_catalog
        from orbit_watch.documents import Request as RequestDocument
        from orbit_watch.formats import owjson
        from orbit_watch.sim.simulator import StationProfile, simulate

        self._require(principal, "station")
        request_id = request.path_params["request_id"]
        record = self.service.records.get(request_id)
        if record is None:
            raise ApiError("unknown_request", f"no request {request_id!r}")
        if record.status != lc.Status.RESERVED or record.reserved_by != principal.party:
            raise ApiError("not_reserved_by_you", f"{request_id} is not reserved by you")
        if not RequestDocument.parse(self.service.request_documents[request_id]).simulated:
            raise ApiError(
                "real_request",
                f"{request_id} asks for real observations, and SIMULATED ones cannot fulfil "
                "it. Deliver your station's own observations",
            )
        found = self._profile(principal.party)
        if found is None:
            raise ApiError("no_profile", "register your station profile first")
        terms = record.terms
        profile = found["profile"]
        if found["place"] != "exact" and self.station_decimals is not None:
            profile = privacy.rounded_station(profile, self.station_decimals)  # saved earlier
        catalogue = self.service.simulation_catalog(
            terms.target_norad_id, terms.window_start, terms.window_end, method_version(terms)
        )
        observations = simulate(
            parse_catalog(catalogue),
            terms.target_norad_id,
            StationProfile.from_document(profile),
            terms.window_start,
            terms.window_end,
            seed=secrets.randbits(31),
            max_passes=2,
            notes=f"SIMULATED for {principal.party} with its station profile, by Orbit Watch",
        )
        text = owjson.write_observation_set(observations)
        name = principal.party.split(":", 1)[1]
        return {
            "request_id": request_id,
            "file_name": f"{request_id}-{name}-simulated.json",
            "format": "json",
            "observations": text,
            "sha256": sha256_bytes(text.encode("utf-8")),
            "simulated": True,
        }

    def public_open_requests(self, request, now):
        return {"requests": self.service.open_requests()}

    def public_request(self, request, now):
        request_id = request.path_params["request_id"]
        if request_id not in self.service.records:
            raise ApiError("not_found", f"no published request {request_id!r}")
        publication = self.service.publication(request_id, now)
        if publication["state"] != "published":
            raise ApiError("not_found", f"no published request {request_id!r}")
        return {"publication": publication, "summary": self.service.summary(request_id)}

    def public_file(self, request, now):
        sha256 = request.path_params["sha256"]
        if not self.service.can_read_file(sha256, None, None, now):
            raise ApiError("unknown_file", f"no published file {sha256}")
        licence = next(
            (
                self.service.publication(rid, now)["licence_url"]
                for rid in sorted(self.service.records)
                if any(d == sha256 for _, d in self.service.request_files(rid))
            ),
            None,
        )
        headers = {"Cache-Control": "public, max-age=31536000, immutable"}
        if licence:
            headers["Link"] = f'<{licence}>; rel="license"'
        return Response(
            self.service.files[sha256], media_type="application/octet-stream", headers=headers
        )

    def tasks(self, principal, request, body, now):
        self._require(principal, "reviewer")
        return {"tasks": self.service.assignments(principal.party, now)}

    def review(self, principal, request, body, now, key):
        self._require(principal, "reviewer")
        document = _json(body)
        task_id = request.path_params["task_id"]
        approve, reason = _field(document, "approve", bool), _field(document, "reason", str)
        real = self.service.real_tasks.get(task_id)
        if real is not None and self.service.on_chain(real[0]):
            # On chain a vote is the reviewer's own public attestation, so a real task
            # differs from a calibration task here (decision D-23).
            if real[1] != principal.party:
                raise ApiError("not_your_task", "this task belongs to another reviewer")
            if not reason.strip():
                raise ApiError("reason_required", "a review must give its reasons")
            return self._signing(
                self.chain.prepare_vote(real[0], principal.party, approve, reason, now)
            )
        result = self.service.review(task_id, principal.party, approve, reason, now)
        return 200, result

    def profile(self, principal, request, body, now):
        reviewer = request.path_params["reviewer"]
        if principal.role != "admin" and principal.party != reviewer:
            raise ApiError("not_yourself", "only the reviewer or an admin can see this profile")
        return self.service.reviewer_profile(reviewer, now)

    def balance(self, principal, request, body, now):
        party = request.path_params["party"]
        if principal.role != "admin" and principal.party != party:
            raise ApiError("not_yourself", "only the party or an admin can see this balance")
        if self.chain is not None:
            return self.chain.balance(party)
        return {"party": party, "points": self.service.adapter.balance(party)}

    def grant(self, principal, request, body, now, key):
        self._require(principal, "admin")
        if self.chain is not None:
            raise ApiError(
                "points_not_used",
                "on chain, deposits are testnet tokens from a faucet, not points",
            )
        document = _json(body)
        party = _field(document, "party", str)
        points = _field(document, "points", int)
        receipt = self.service.adapter.grant(party, points, key=f"api/{principal.party}/{key}")
        return 200, {
            "party": party,
            "points": self.service.adapter.balance(party),
            "reference": receipt.reference,
        }

    def create_key(self, principal, request, body, now, key):
        self._require(principal, "admin")
        document = _json(body)
        party, role = _field(document, "party", str), _field(document, "role", str)
        try:
            new_key = keys.create_key(self.db, party, role, now)
        except keys.ApiKeyError as error:
            raise ApiError(error.code, str(error)) from None
        return 201, {"party": party, "role": role, "key": new_key}

    def tick(self, principal, request, body, now, key):
        self._require(principal, "admin")
        result: dict[str, Any] = {"changed": self.service.tick(now)}
        if self.chain is not None:
            result["sent"] = self.chain.follow_up()
            result["notice"] = self.chain.notice
        return 200, result

    # ------------------------------------------------------------------ administrator (step 3.7)

    def admin_overview(self, principal, request, body, now):
        """Every request with its status, delivery and payments; the chain's transactions,
        conflicts and latest events."""
        self._require(principal, "admin")
        requests = []
        counts: dict[str, int] = {}
        for rid, record in sorted(self.service.records.items()):
            summary = self.service.summary(rid)
            counts[str(record.status)] = counts.get(str(record.status), 0) + 1
            requests.append(
                {
                    "request_id": rid,
                    "title": json.loads(self.service.request_documents[rid]).get("title"),
                    "requester": record.requester,
                    "status": str(record.status),
                    "outcome": summary["outcome"],
                    "outcome_reason": summary["outcome_reason"],
                    "reserved_by": record.reserved_by,
                    "observer": record.observer,
                    "automated_verdict": summary["automated_verdict"],
                    "reviewers": summary["reviewers"],
                    "votes": summary["votes"],
                    "on_chain": self.service.on_chain(rid),
                    "settlement": summary["settlement"],
                    "labels": summary["labels"],
                }
            )
        view: dict[str, Any] = {"now": format_utc(now), "requests": requests, "counts": counts}
        if self.chain is not None:
            view.update(self.chain.admin_view())
            view["notice"] = self.chain.notice
        else:
            view.update({"chain": None, "events": [], "conflicts": [], "transactions": []})
        return view

    def _wall_ms(self) -> int:
        return int(self.wall_clock().timestamp() * 1000)

    def admin_governance(self, principal, request, body, now):
        self._require(principal, "admin")
        return self._require_chain().governance_view(self._wall_ms())

    def admin_propose(self, principal, request, body, now):
        """The data for the Safe to add or remove a reviewer through the timelock. Nothing
        changes here: the Safe's owners sign in the Safe's own app."""
        self._require(principal, "admin")
        chain = self._require_chain()
        document = _json(body)
        action = _field(document, "action", str)
        reviewer = _field(document, "reviewer", str).strip()
        if not reviewer.startswith("0x"):  # a party name: its registered wallet
            address = chain.address_of(reviewer)
            if address is None:
                raise ApiError("no_wallet", f"{reviewer} has no registered wallet")
            reviewer = address
        proposal = chain.governance.prepare(action, reviewer, self._wall_ms())
        return {"proposal": proposal, "notice": chain.notice}

    def admin_demo_datasets(self, principal, request, body, now):
        """The six SIMULATED test datasets of phase 0 (``orbit-watch demo``)."""
        from orbit_watch.sim.scenarios import REQUEST, SCENARIOS

        self._require(principal, "admin")
        return {
            "request": REQUEST,
            "datasets": [
                {
                    "name": s.name,
                    "title": s.title,
                    "expected_verdict": s.expected_verdict,
                    "expected_failures": s.expected_failures,
                }
                for s in SCENARIOS
            ],
            "simulated": True,
        }

    def admin_demo_dataset(self, principal, request, body, now):
        """One SIMULATED test dataset, made afresh (no state changes here)."""
        from orbit_watch.catalog import parse_catalog
        from orbit_watch.sim.scenarios import SCENARIOS

        self._require(principal, "admin")
        name = request.path_params["name"]
        scenarios = {s.name: s for s in SCENARIOS}
        if name not in scenarios:
            raise ApiError("unknown_scenario", f"no demo dataset {name!r}")
        ctx: dict[str, Any] = {"catalog": parse_catalog(self.service.context.catalog)}
        ctx["datasets"] = {"acceptable": scenarios["acceptable"].build(ctx)}
        data = scenarios[name].build(ctx)
        scenario = scenarios[name]
        return {
            "name": name,
            "file_name": f"demo-{name}.json",
            "format": "json",
            "observations": data.decode("utf-8"),
            "sha256": sha256_bytes(data),
            "expected_verdict": scenario.expected_verdict,
            "expected_failures": scenario.expected_failures,
            "simulated": True,
        }

    def admin_simulate(self, principal, request, body, now):
        """SIMULATED observations by a built-in station profile of an allowed target in a
        window (``orbit-watch simulate``); nothing is kept. A real object is observed along
        its stored element set nearest the window (D-50)."""
        from orbit_watch.catalog import parse_catalog
        from orbit_watch.formats import owjson
        from orbit_watch.sim.simulator import builtin_profiles, load_profile, simulate

        self._require(principal, "admin")
        document = _json(body)
        profile = _field(document, "profile", str)
        if profile not in builtin_profiles():
            raise ApiError("unknown_profile", f"no built-in station profile {profile!r}")
        norad_id = _field(document, "norad_id", int)
        if norad_id not in self.service.targets():
            raise ApiError("unknown_target", f"{norad_id} is not an allowed target")
        start = _utc_field(document, "start")
        end = _utc_field(document, "end")
        if not start < end or (end - start).total_seconds() > 3 * 24 * 3600:
            raise ApiError("invalid_window", "the window must end after it starts, within 3 days")
        catalogue = self.service.simulation_catalog(norad_id, start, end)
        passes = document.get("max_passes", 2)
        if not isinstance(passes, int) or isinstance(passes, bool):
            raise ApiError("invalid_body", "max_passes must be a whole number")
        if not 1 <= passes <= MAX_SIMULATED_PASSES:
            raise ApiError("invalid_body", f"max_passes must be 1 to {MAX_SIMULATED_PASSES}")
        observations = simulate(
            parse_catalog(catalogue),
            norad_id,
            load_profile(profile),
            start,
            end,
            seed=secrets.randbits(31),
            max_passes=passes,
            notes=f"SIMULATED by Orbit Watch for {principal.party} with {profile}",
        )
        text = owjson.write_observation_set(observations)
        return {
            "file_name": f"simulated-{profile}-{norad_id}.json",
            "format": "json",
            "observations": text,
            "count": len(observations.observations),
            "sha256": sha256_bytes(text.encode("utf-8")),
            "simulated": True,
        }

    # ------------------------------------------------------------------ public pages (step 3.7)

    def public_attestations(self, request, now):
        chain = self._require_chain()
        published = {
            rid
            for rid in self.service.records
            if self.service.publication(rid, now)["state"] == "published"
        }
        attestations = chain.attestations()
        for attestation in attestations:
            attestation["published"] = attestation["request_id"] in published
        return {
            "attestations": attestations,
            "eas": chain.chain.eas.address,
            "result_schema": "0x" + chain.chain.result_schema.hex(),
            "vote_schema": "0x" + chain.chain.vote_schema.hex(),
            "notice": chain.notice,
        }

    async def public_quality(self, request: Request) -> Response:
        """The station quality meter: an observation file in, its quality report out. The
        file is not kept, and scoring does not hold the service lock."""
        await run_in_threadpool(self._limit_alone, "quality", request)
        # Read in pieces and stop at the limit: anyone may call this.
        chunks, size = [], 0
        async for chunk in request.stream():
            size += len(chunk)
            if size > MAX_QUALITY_BYTES:
                raise ApiError("too_large", f"the file is larger than {MAX_QUALITY_BYTES} bytes")
            chunks.append(chunk)
        body = b"".join(chunks)
        fmt = request.query_params.get("format")
        if fmt not in (None, "json", "iod", "tdm"):
            raise ApiError("invalid_format", "format must be json, iod or tdm")
        report = await run_in_threadpool(self._score, body, fmt)
        return self._respond(report)

    def _score(self, data: bytes, fmt: str | None) -> dict[str, Any]:
        from orbit_watch import quality
        from orbit_watch.catalog import parse_catalog
        from orbit_watch.formats import load_observation_sets

        try:
            # Without a format, the content tells (the name has no suffix to go by).
            loaded = load_observation_sets("upload", data=data, input_format=fmt)
        except (ValueError, KeyError, IndexError, TypeError) as error:
            raise ApiError("invalid_file", f"cannot read the observations: {error}") from None
        stations = sorted({s.station.id for s in loaded.sets})
        if not loaded.sets:
            raise ApiError("invalid_file", "the file has no observations the meter can use")
        if len(stations) > 1:
            raise ApiError("several_stations", f"the file has several stations: {stations}")
        try:
            objects = sorted({s.target.norad_id for s in loaded.sets})
            catalog = parse_catalog(self.service.catalog_for(objects))
            report = quality.score_station(loaded.sets, catalog)
        except ValueError as error:
            raise ApiError("cannot_score", str(error)) from None
        return {
            "report": report,
            "text": quality.render_text(report),
            "warnings": loaded.warnings,
            "skipped": loaded.skipped,
        }

    # ------------------------------------------------------------------ chain (step 2.6)

    def chain_info(self, request, now):
        return self._require_chain().info()

    def get_wallet(self, principal, request, body, now):
        return self._require_chain().wallet_view(principal.party)

    def register_wallet(self, principal, request, body, now, key):
        chain = self._require_chain()
        document = _json(body)
        return 200, chain.register_wallet(
            principal.party,
            _field(document, "address", str),
            _field(document, "signature", str),
            now,
        )

    def withdraw(self, principal, request, body, now, key):
        return self._signing(self._require_chain().prepare_withdraw(principal.party))

    def report_transaction(self, principal, request, body, now, key):
        chain = self._require_chain()
        tx_hash = _field(_json(body), "tx_hash", str)
        view = chain.report(principal.party, tx_hash, now, admin=principal.role == "admin")
        request_id = view["request_id"]
        return 200, {
            "transaction": view,
            "request": self._record_view(request_id) if request_id else None,
            "notice": chain.notice,
        }

    def list_transactions(self, principal, request, body, now):
        chain = self._require_chain()
        party = None if principal.role == "admin" else principal.party
        request_id = request.query_params.get("request")
        return {
            "transactions": chain.transactions(party=party, request_id=request_id),
            "notice": chain.notice,
        }


class SecurityHeaders:
    """Adds ``SECURITY_HEADERS`` to every HTTP response (pure ASGI middleware)."""

    def __init__(self, app: Any):
        self.app = app

    async def __call__(self, scope: Any, receive: Any, send: Any) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        names = {name for name, _ in SECURITY_HEADERS}

        async def send_with_headers(message: Any) -> None:
            if message["type"] == "http.response.start":
                kept = [h for h in message.get("headers", []) if h[0].lower() not in names]
                message = {**message, "headers": [*kept, *SECURITY_HEADERS]}
            await send(message)

        await self.app(scope, receive, send_with_headers)


class BodyLimit:
    """Refuses a body over ``MAX_BODY_BYTES`` with ``413`` before any route reads it: by
    its ``Content-Length``, or while it arrives (pure ASGI middleware, step 4.3)."""

    def __init__(self, app: Any, max_bytes: int | None = None):
        self.app = app
        self.max_bytes = max_bytes

    async def __call__(self, scope: Any, receive: Any, send: Any) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        limit = self.max_bytes if self.max_bytes is not None else MAX_BODY_BYTES
        headers = dict(scope.get("headers", []))
        length = headers.get(b"content-length")
        too_large = _error_response("too_large", f"the body is larger than {limit} bytes")
        if length is not None:
            try:
                declared = int(length)
            except ValueError:
                declared = limit + 1
            if declared > limit:
                await too_large(scope, receive, send)
                return
        # Read the body here, up to the limit, and hand it on whole.
        chunks, size, more = [], 0, True
        while more:
            message = await receive()
            if message["type"] != "http.request":
                await self.app(scope, _replay([], message, receive), send)
                return
            chunk = message.get("body", b"")
            size += len(chunk)
            if size > limit:
                await too_large(scope, receive, send)
                return
            chunks.append(chunk)
            more = message.get("more_body", False)
        await self.app(scope, _replay(chunks, None, receive), send)


def _replay(chunks: list[bytes], last: Any, receive: Any) -> Any:
    """A ``receive`` that gives the body read so far in one message, then goes on."""
    pending = [{"type": "http.request", "body": b"".join(chunks), "more_body": False}]
    if last is not None:
        pending = [last]

    async def replay() -> Any:
        if pending:
            return pending.pop(0)
        return await receive()

    return replay


def create_app(
    service: RequestService,
    *,
    clock: Callable[[], datetime] | None = None,
    web: str | Path | None = None,
    origins: tuple[str, ...] | list[str] = (),
    wall_clock: Callable[[], datetime] | None = None,
    follow_secret: str | None = None,
    follow_max_age: float = FOLLOW_MAX_AGE,
    limits: Limits | None = None,
    client_ip_header: str | None = None,
    station_decimals: int | None = None,
    read_only: bool = False,
    backup_token: str | None = None,
    backup_recipient: str | None = None,
    orbit_fetcher: orbit_follower.Fetcher | None = None,
) -> Starlette:
    """The ASGI application for a stored service; with ``web``, the directory of the built
    web application, served at ``/`` (step 3.1). Browsers sign in from ``origins`` only
    (step 3.2). With ``follow_secret``, a schedule can run the follower (step 4.2); the
    ``Api`` is ``app.state.api``. ``limits`` (step 4.3) and ``station_decimals`` (step 4.4)
    apply none by default; ``orbit-watch serve`` applies both. ``read_only`` refuses every
    change, and with ``backup_token`` a schedule takes backups encrypted to
    ``backup_recipient`` (step 4.6). With ``orbit_fetcher`` the follower fetches reference
    orbits from CelesTrak and SatChecker (step 5.4)."""
    if clock is None:
        # On a chain the service keeps the chain's time, which its deadlines use.
        clock = service.chain.now if service.chain is not None else lambda: datetime.now(tz=UTC)
    api = Api(
        service,
        clock,
        origins=tuple(origins),
        wall_clock=wall_clock,
        follow_secret=follow_secret,
        follow_max_age=follow_max_age,
        limits=limits,
        client_ip_header=client_ip_header,
        station_decimals=station_decimals,
        read_only=read_only,
        backup_token=backup_token,
        backup_recipient=backup_recipient,
        orbit_fetcher=orbit_fetcher,
    )
    read, change = (
        lambda f: api.endpoint(f, mutating=False),
        lambda f, **kw: api.endpoint(f, mutating=True, **kw),
    )
    routes = [
        Route("/v1/health", api.health, methods=["GET"]),
        # The follower (step 4.2): for a schedule, and for monitoring.
        Route("/v1/internal/follow", api.internal_follow, methods=["GET", "POST"]),
        Route("/v1/health/follower", api.follower_health, methods=["GET"]),
        Route("/v1/health/reference-orbits", api.reference_orbits_health, methods=["GET"]),
        # Backups, for a schedule (step 4.6).
        Route("/v1/internal/backup", api.internal_backup, methods=["GET"]),
        Route("/v1/requests", read(api.list_requests), methods=["GET"]),
        Route("/v1/requests", change(api.create_request, limit="new_request"), methods=["POST"]),
        Route("/v1/requests/{request_id}", read(api.get_request), methods=["GET"]),
        Route(
            "/v1/requests/{request_id}/open",
            change(api._requester_action("open")),
            methods=["POST"],
        ),
        Route(
            "/v1/requests/{request_id}/fund",
            change(api._requester_action("fund")),
            methods=["POST"],
        ),
        Route(
            "/v1/requests/{request_id}/cancel",
            change(api._requester_action("cancel")),
            methods=["POST"],
        ),
        Route("/v1/requests/{request_id}/reserve", change(api.reserve), methods=["POST"]),
        Route(
            "/v1/requests/{request_id}/deliveries",
            change(api.deliver, limit="upload"),
            methods=["POST"],
        ),
        Route("/v1/requests/{request_id}/challenge", change(api.challenge), methods=["POST"]),
        Route("/v1/requests/{request_id}/report", read(api.get_report), methods=["GET"]),
        Route("/v1/files/{sha256}", read(api.get_file), methods=["GET"]),
        Route("/v1/tasks", read(api.tasks), methods=["GET"]),
        Route("/v1/tasks/{task_id}/review", change(api.review), methods=["POST"]),
        Route("/v1/reviewers/{reviewer}/profile", read(api.profile), methods=["GET"]),
        Route("/v1/balances/{party}", read(api.balance), methods=["GET"]),
        Route("/v1/admin/grants", change(api.grant), methods=["POST"]),
        # The new key is returned once and never stored with the idempotency record.
        Route(
            "/v1/admin/keys",
            change(api.create_key, store_response=lambda p: {**p, "key": None}),
            methods=["POST"],
        ),
        Route("/v1/admin/tick", change(api.tick), methods=["POST"]),
        # Reference orbits (step 5.4): uploaded by hand, and named publicly.
        Route("/v1/admin/element-sets", change(api.admin_upload_element_sets), methods=["POST"]),
        Route(
            "/v1/admin/reference-orbits/resume",
            change(api.admin_resume_orbit_fetching),
            methods=["POST"],
        ),
        # Real objects on the allow-list (step 5.4, D-49): an administrator's additions.
        Route("/v1/admin/allowlist", change(api.admin_allow_object), methods=["POST"]),
        Route("/v1/admin/replays", change(api.admin_create_replay), methods=["POST"]),
        Route("/v1/admin/allowlist/remove", change(api.admin_disallow_object), methods=["POST"]),
        # The administrator view (step 3.7): reads, and data for others to sign.
        Route("/v1/admin/overview", read(api.admin_overview), methods=["GET"]),
        Route("/v1/admin/governance", read(api.admin_governance), methods=["GET"]),
        Route("/v1/admin/governance/proposals", read(api.admin_propose), methods=["POST"]),
        Route("/v1/admin/demo-datasets", read(api.admin_demo_datasets), methods=["GET"]),
        Route("/v1/admin/demo-datasets/{name}", read(api.admin_demo_dataset), methods=["POST"]),
        Route("/v1/admin/simulate", read(api.admin_simulate), methods=["POST"]),
        # Public pages (step 3.7).
        Route("/v1/public/quality", api.public_quality, methods=["POST"]),
        Route("/v1/public/attestations", api.public(api.public_attestations), methods=["GET"]),
        # On a testnet chain (step 2.6).
        Route("/v1/chain", api.public(api.chain_info), methods=["GET"]),
        # Signing in with a wallet (step 3.2).
        Route(
            "/v1/session/challenge",
            api.session_route(api.session_challenge, limited=True),
            methods=["POST"],
        ),
        Route("/v1/session", api.session_route(api.get_session), methods=["GET"]),
        Route("/v1/session", api.session_route(api.sign_in, limited=True), methods=["POST"]),
        Route("/v1/session", api.session_route(api.sign_out), methods=["DELETE"]),
        Route("/v1/sessions", api.session_route(api.end_sessions), methods=["DELETE"]),
        Route("/v1/wallet", read(api.get_wallet), methods=["GET"]),
        Route("/v1/wallet", change(api.register_wallet), methods=["POST"]),
        Route("/v1/wallet/withdraw", change(api.withdraw), methods=["POST"]),
        Route("/v1/transactions", read(api.list_transactions), methods=["GET"]),
        Route("/v1/transactions", change(api.report_transaction), methods=["POST"]),
        # Public, no key: settled requests whose embargo has passed (step 1.8).
        Route("/v1/public/requests", api.public(api.public_requests), methods=["GET"]),
        # Stations (step 3.5).
        Route("/v1/public/station-templates", api.public(api.station_templates), methods=["GET"]),
        Route("/v1/stations/{party}/profile", read(api.get_station_profile), methods=["GET"]),
        Route("/v1/stations/{party}/profile", change(api.put_station_profile), methods=["PUT"]),
        Route(
            "/v1/stations/{party}/profile",
            change(api.delete_station_profile),
            methods=["DELETE"],
        ),
        Route(
            "/v1/requests/{request_id}/passes",
            read(api.request_passes),
            methods=["GET"],
        ),
        Route(
            "/v1/requests/{request_id}/simulate",
            read(api.simulate_observations),
            methods=["POST"],
        ),
        # Public, no key: the objects requests may target (step 3.4).
        Route("/v1/public/targets", api.public(api.public_targets), methods=["GET"]),
        Route(
            "/v1/public/reference-orbits",
            api.public(api.public_reference_orbits),
            methods=["GET"],
        ),
        # Public, no key: requests that invite observers (step 3.1, decision D-26).
        Route("/v1/public/open-requests", api.public(api.public_open_requests), methods=["GET"]),
        Route("/v1/public/requests/{request_id}", api.public(api.public_request), methods=["GET"]),
        Route("/v1/public/files/{sha256}", api.public(api.public_file), methods=["GET"]),
    ]
    if web is not None:
        if not (Path(web) / "index.html").is_file():
            raise ValueError(f"{web} has no index.html: build the web application first")
        routes.append(Mount("/", app=StaticFiles(directory=web, html=True), name="web"))
    handlers = {
        ApiError: _handle_api_error,
        ServiceError: _handle_api_error,
        SettlementError: _handle_api_error,
        SessionError: _handle_api_error,
        ChainError: _handle_api_error,
        RateLimited: _handle_api_error,
    }
    app = Starlette(
        routes=routes,
        exception_handlers=handlers,
        middleware=[Middleware(SecurityHeaders), Middleware(BodyLimit)],
    )
    app.state.api = api
    return app


def start_follower(
    app: Starlette, every: float, stop: threading.Event | None = None
) -> threading.Thread:
    """Run the follower every ``every`` seconds in a thread of this process
    (``orbit-watch serve --follow``), for a server of our own (decision P4-05), until
    ``stop`` is set."""
    api: Api = app.state.api
    stop = stop or threading.Event()

    def loop() -> None:
        while not stop.wait(every):
            if api.read_only:  # the follower waits (step 4.6)
                continue
            try:
                api.follow_once()
            except Exception:  # the node or the database is away: the next run tries again
                log.exception("the follower failed")

    thread = threading.Thread(target=loop, name="orbit-watch-follower", daemon=True)
    thread.start()
    return thread

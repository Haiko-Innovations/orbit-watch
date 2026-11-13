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

One lock serialises all calls: the service holds its working state in memory
and the database admits one writer.

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

**The web application** (step 3.1): given the directory of its build, the API
serves it at ``/`` on its own origin, so the browser talks to one server only.
Every response carries a strict content security policy: the pages load only
their own files and talk only to this API (decision D-25).
"""

from __future__ import annotations

import json
import secrets
import threading
from collections.abc import Callable
from datetime import UTC, datetime
from importlib import resources
from pathlib import Path
from typing import Any

from starlette.applications import Starlette
from starlette.concurrency import run_in_threadpool
from starlette.middleware import Middleware
from starlette.requests import Request
from starlette.responses import JSONResponse, Response
from starlette.routing import Mount, Route
from starlette.staticfiles import StaticFiles

from orbit_watch import __version__
from orbit_watch import lifecycle as lc
from orbit_watch.api import keys, sessions
from orbit_watch.api.sessions import SessionError
from orbit_watch.canonical import dumps_pretty, sha256_bytes
from orbit_watch.chain import WALLET_PREFIX, ChainError
from orbit_watch.documents import TargetPolicy
from orbit_watch.schema import validate
from orbit_watch.service import RequestService, ServiceError
from orbit_watch.settlement import SettlementError
from orbit_watch.timeutil import format_utc, parse_utc

MAX_BODY_BYTES = 10 * 1024 * 1024
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
    "not_reserved_by_you": 409,
    "party_taken": 409,
    "forbidden_role": 403,
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
    "insufficient_balance": 409,
    "points_not_used": 409,
    "already_reviewer": 409,
    "not_a_reviewer": 409,
    "registry_full": 409,
    "no_timelock": 409,
    "unknown_scenario": 404,
    "unknown_profile": 404,
    "unknown_target": 404,
    "too_large": 413,
    "verification_unavailable": 503,
    "chain_unavailable": 503,
}


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
    return _error_response(code, str(exc))


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


class Api:
    def __init__(
        self,
        service: RequestService,
        clock: Callable[[], datetime],
        *,
        origins: tuple[str, ...] = (),
        wall_clock: Callable[[], datetime] | None = None,
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
        session = sessions.lookup(self.db, request.cookies.get(sessions.COOKIE), self.wall_clock())
        if session is None:
            raise ApiError(
                "unauthorized",
                "sign in with your wallet, or give an API key (Authorization: Bearer)",
            )
        if mutating and self._origin(request) != session.origin:
            raise ApiError("wrong_origin", f"this session belongs to {session.origin}")
        return keys.Principal(session.party, session.role)

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
    ):
        """Wrap a handler: authenticate, serialise, run in one transaction, idempotency."""

        async def handler(request: Request) -> Response:
            body = await request.body()
            if len(body) > MAX_BODY_BYTES:
                raise ApiError("too_large", f"the body is larger than {MAX_BODY_BYTES} bytes")
            return await run_in_threadpool(self._run, request, body, work, mutating, store_response)

        return handler

    def _run(
        self,
        request: Request,
        body: bytes,
        work: Callable[..., Any],
        mutating: bool,
        store_response: Callable[[Any], Any] | None,
    ) -> Response:
        with self.lock:
            principal = self._principal(request, mutating)
            self._follow_chain()
            now = self.clock()
            if not mutating:
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
            stored = self.db.query(
                "SELECT request_hash, status_code, response_json FROM idempotency "
                "WHERE party = ? AND idempotency_key = ?",
                (principal.party, key),
            )
            if stored:
                if stored[0]["request_hash"] != request_hash:
                    raise ApiError(
                        "key_reused", "this Idempotency-Key was already used for a different call"
                    )
                return JSONResponse(
                    json.loads(stored[0]["response_json"]),
                    status_code=stored[0]["status_code"],
                    headers={"Idempotent-Replayed": "true"},
                )
            try:
                with self.db.transaction():
                    status, payload = work(principal, request, body, now, key)
                    kept = store_response(payload) if store_response else payload
                    self.db.execute(
                        "INSERT INTO idempotency (party, idempotency_key, request_hash, "
                        "status_code, response_json) VALUES (?, ?, ?, ?, ?)",
                        (principal.party, key, request_hash, status, json.dumps(kept)),
                    )
            except BaseException:
                self.service._reload()
                raise
            return JSONResponse(payload, status_code=status)

    def _follow_chain(self) -> None:
        """Apply the escrow's new events before anything else: the chain decides."""
        if self.chain is None:
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

    def health(self, request: Request) -> Response:
        notice = "Phase 1 prototype. All bundled data is SIMULATED."
        if self.chain is not None:
            notice = (
                f"Phase 2 prototype on a chain: {self.chain.notice}. All bundled data is SIMULATED."
            )
        return JSONResponse({"status": "ok", "version": __version__, "notice": notice})

    def create_request(self, principal, request, body, now, key):
        self._require(principal, "requester")
        document = _json(body)
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
        request_bytes = dumps_pretty(request_document, sort_keys=False).encode("utf-8")
        record = self.service.create(request_bytes, principal.party, now, **options)
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
        if self.service.on_chain(request_id):
            prepared = self.chain.prepare_delivery(request_id, principal.party, body, now, fmt)
            if prepared is not None:
                return self._signing(prepared)
            return 200, self._record_view(request_id)
        self.service.deliver(request_id, principal.party, body, now, observations_format=fmt)
        return 200, self._record_view(request_id)

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
                }
                for rid, record in sorted(self.service.records.items())
            ]
        }

    def get_request(self, principal, request, body, now):
        request_id = request.path_params["request_id"]
        if request_id not in self.service.records:
            raise ApiError("unknown_request", f"no request {request_id!r}")
        return self._record_view(request_id)

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
            self._follow_chain()
            return self._respond(work(request, self.clock()))

    # ------------------------------------------------------------------ sessions (step 3.2)

    def session_route(self, work: Callable[..., Any]):
        """Sign-in calls: no key, no idempotency record, one transaction, wall-clock time."""

        async def handler(request: Request) -> Response:
            body = await request.body()
            if len(body) > 64 * 1024:
                raise ApiError("too_large", "the body is larger than 64 KiB")
            return await run_in_threadpool(self._run_session, request, body, work)

        return handler

    def _run_session(self, request: Request, body: bytes, work: Callable[..., Any]) -> Response:
        with self.lock, self.db.transaction():
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
        token, session = sessions.create_session(
            self.db, party=party, role=role, address=signed.address, origin=origin, now=now
        )
        response = JSONResponse({"session": session.view(), "notice": chain.notice})
        response.set_cookie(
            sessions.COOKIE,
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
        session = sessions.lookup(self.db, request.cookies.get(sessions.COOKIE), now)
        return {"session": None if session is None else session.view()}

    def sign_out(self, request, body, now):
        self._origin(request)
        sessions.end(self.db, request.cookies.get(sessions.COOKIE), now)
        response = JSONResponse({"signed_out": True})
        response.delete_cookie(sessions.COOKIE, path="/", httponly=True, samesite="strict")
        return response

    def public_requests(self, request, now):
        return {"requests": self.service.published(now)}

    def public_targets(self, request, now):
        """The objects requests may target: the allow-list (decision D-05), which is public."""
        policy = TargetPolicy.parse(self.service.context.policy)
        return {
            "targets": [
                {"norad_id": norad_id, "name": name}
                for norad_id, name in sorted(policy.allowed.items())
            ],
            "simulated": policy.simulated,
            "description": policy.description,
        }

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
        rows = self.db.query("SELECT * FROM station_profiles WHERE party = ?", (party,))
        if not rows:
            return None
        return {
            "party": party,
            "profile": json.loads(rows[0]["profile_json"]),
            "updated_at": rows[0]["updated_at"],
        }

    def get_station_profile(self, principal, request, body, now):
        party = self._own_station(principal, request)
        found = self._profile(party)
        if found is None:
            raise ApiError("no_profile", f"{party} has no station profile yet")
        return found

    def put_station_profile(self, principal, request, body, now, key):
        self._require(principal, "station")
        party = self._own_station(principal, request)
        document = _field(_json(body), "profile", dict)
        problems = validate(document, "station-profile")
        if problems:
            raise ApiError("invalid_profile", "; ".join(problems[:5]))
        name = party.split(":", 1)[1]
        if document["station"]["id"] != name:
            raise ApiError("wrong_station", f"the profile's station id must be {name}")
        self.db.execute(
            "INSERT INTO station_profiles (party, profile_json, updated_at) VALUES (?, ?, ?) "
            "ON CONFLICT (party) DO UPDATE SET profile_json = excluded.profile_json, "
            "updated_at = excluded.updated_at",
            (party, dumps_pretty(document, sort_keys=False), format_utc(now)),
        )
        return 200, self._profile(party)

    def simulate_observations(self, principal, request, body, now):
        """SIMULATED observations of a reserved request's target, made with the station's
        own profile, for it to deliver like any file (no state changes here)."""
        from orbit_watch.catalog import parse_catalog
        from orbit_watch.formats import owjson
        from orbit_watch.sim.simulator import StationProfile, simulate

        self._require(principal, "station")
        request_id = request.path_params["request_id"]
        record = self.service.records.get(request_id)
        if record is None:
            raise ApiError("unknown_request", f"no request {request_id!r}")
        if record.status != lc.Status.RESERVED or record.reserved_by != principal.party:
            raise ApiError("not_reserved_by_you", f"{request_id} is not reserved by you")
        found = self._profile(principal.party)
        if found is None:
            raise ApiError("no_profile", "register your station profile first")
        terms = record.terms
        observations = simulate(
            parse_catalog(self.service.context.catalog),
            terms.target_norad_id,
            StationProfile.from_document(found["profile"]),
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
        window (``orbit-watch simulate``); nothing is kept."""
        from orbit_watch.catalog import parse_catalog
        from orbit_watch.formats import owjson
        from orbit_watch.sim.simulator import builtin_profiles, load_profile, simulate

        self._require(principal, "admin")
        document = _json(body)
        profile = _field(document, "profile", str)
        if profile not in builtin_profiles():
            raise ApiError("unknown_profile", f"no built-in station profile {profile!r}")
        norad_id = _field(document, "norad_id", int)
        if not TargetPolicy.parse(self.service.context.policy).allows(norad_id):
            raise ApiError("unknown_target", f"{norad_id} is not an allowed target")
        start = _utc_field(document, "start")
        end = _utc_field(document, "end")
        if not start < end or (end - start).total_seconds() > 3 * 24 * 3600:
            raise ApiError("invalid_window", "the window must end after it starts, within 3 days")
        passes = document.get("max_passes", 2)
        if not isinstance(passes, int) or isinstance(passes, bool):
            raise ApiError("invalid_body", "max_passes must be a whole number")
        if not 1 <= passes <= MAX_SIMULATED_PASSES:
            raise ApiError("invalid_body", f"max_passes must be 1 to {MAX_SIMULATED_PASSES}")
        observations = simulate(
            parse_catalog(self.service.context.catalog),
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
            report = quality.score_station(loaded.sets, parse_catalog(self.service.context.catalog))
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


def create_app(
    service: RequestService,
    *,
    clock: Callable[[], datetime] | None = None,
    web: str | Path | None = None,
    origins: tuple[str, ...] | list[str] = (),
    wall_clock: Callable[[], datetime] | None = None,
) -> Starlette:
    """The ASGI application for a stored service; with ``web``, the directory of the built
    web application, served at ``/`` (step 3.1). Browsers sign in from ``origins`` only
    (step 3.2)."""
    if clock is None:
        # On a chain the service keeps the chain's time, which its deadlines use.
        clock = service.chain.now if service.chain is not None else lambda: datetime.now(tz=UTC)
    api = Api(service, clock, origins=tuple(origins), wall_clock=wall_clock)
    read, change = (
        lambda f: api.endpoint(f, mutating=False),
        lambda f, **kw: api.endpoint(f, mutating=True, **kw),
    )
    routes = [
        Route("/v1/health", api.health, methods=["GET"]),
        Route("/v1/requests", read(api.list_requests), methods=["GET"]),
        Route("/v1/requests", change(api.create_request), methods=["POST"]),
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
        Route("/v1/requests/{request_id}/deliveries", change(api.deliver), methods=["POST"]),
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
        Route("/v1/session/challenge", api.session_route(api.session_challenge), methods=["POST"]),
        Route("/v1/session", api.session_route(api.get_session), methods=["GET"]),
        Route("/v1/session", api.session_route(api.sign_in), methods=["POST"]),
        Route("/v1/session", api.session_route(api.sign_out), methods=["DELETE"]),
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
            "/v1/requests/{request_id}/simulate",
            read(api.simulate_observations),
            methods=["POST"],
        ),
        # Public, no key: the objects requests may target (step 3.4).
        Route("/v1/public/targets", api.public(api.public_targets), methods=["GET"]),
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
    }
    return Starlette(
        routes=routes, exception_handlers=handlers, middleware=[Middleware(SecurityHeaders)]
    )

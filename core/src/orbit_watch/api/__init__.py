"""The phase 1 HTTP API (step 1.6), built on Starlette (decision D-16).

Every call except ``GET /v1/health`` needs an API key (``Authorization:
Bearer ow_...``). Keys belong to one party and one role (decision P-04):

* ``requester``: create, open, fund and cancel requests, challenge results;
* ``station``: reserve requests, deliver observation files, challenge results;
* ``reviewer``: list review tasks and answer them;
* ``admin``: grant points, create keys, apply deadlines.

A station key can deliver, but it can never move points.

Every call that changes something needs an ``Idempotency-Key`` header. The
first successful response is stored with the change, in the same database
transaction. Repeating the call with the same key returns that response and
changes nothing; reusing the key for a different call is refused
(``key_reused``). Refused calls are not stored, because they change nothing.

One lock serialises all calls: the service holds its working state in memory
and the database admits one writer.
"""

from __future__ import annotations

import json
import threading
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any

from starlette.applications import Starlette
from starlette.concurrency import run_in_threadpool
from starlette.requests import Request
from starlette.responses import JSONResponse, Response
from starlette.routing import Route

from orbit_watch import __version__
from orbit_watch import lifecycle as lc
from orbit_watch.api import keys
from orbit_watch.canonical import dumps_pretty, sha256_bytes
from orbit_watch.service import RequestService, ServiceError
from orbit_watch.settlement import SettlementError
from orbit_watch.timeutil import parse_utc

MAX_BODY_BYTES = 10 * 1024 * 1024
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
    "forbidden_role": 403,
    "not_requester": 403,
    "not_a_party": 403,
    "not_your_task": 403,
    "not_yourself": 403,
    "unknown_request": 404,
    "unknown_task": 404,
    "no_report": 404,
    "unknown_file": 404,
    "not_found": 404,
    "forbidden_in_status": 409,
    "already_voted": 409,
    "already_funded": 409,
    "already_settled": 409,
    "duplicate_request": 409,
    "key_reused": 409,
    "too_large": 413,
    "verification_unavailable": 503,
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


def _field(document: dict[str, Any], name: str, kind: type | tuple[type, ...]) -> Any:
    value = document.get(name)
    if not isinstance(value, kind) or (isinstance(value, bool) and kind is not bool):
        raise ApiError("invalid_body", f"field {name!r} is missing or has the wrong type")
    return value


class Api:
    def __init__(self, service: RequestService, clock: Callable[[], datetime]):
        if service.storage is None:
            raise ValueError("the API needs a stored service (open_service)")
        self.service = service
        self.db = service.storage.db
        self.clock = clock
        self.lock = threading.Lock()

    # ------------------------------------------------------------------ plumbing

    def _principal(self, request: Request) -> keys.Principal:
        header = request.headers.get("authorization", "")
        scheme, _, token = header.partition(" ")
        principal = keys.lookup(self.db, token.strip()) if scheme.lower() == "bearer" else None
        if principal is None:
            raise ApiError("unauthorized", "a valid API key is required (Authorization: Bearer)")
        return principal

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
            principal = self._principal(request)
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

    @staticmethod
    def _respond(result: Any) -> Response:
        if isinstance(result, Response):
            return result
        return JSONResponse(result)

    def _record_view(self, request_id: str) -> dict[str, Any]:
        record = self.service.records[request_id]
        return {
            "summary": self.service.summary(request_id),
            "record": record.to_document(),
            "publication": self.service.publication(request_id, self.clock()),
        }

    # ------------------------------------------------------------------ handlers

    def health(self, request: Request) -> Response:
        return JSONResponse(
            {
                "status": "ok",
                "version": __version__,
                "notice": "Phase 1 prototype. All bundled data is SIMULATED.",
            }
        )

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
            if action == "open":
                self.service.open(request_id, principal.party, now)
            elif action == "cancel":
                self.service.cancel(request_id, principal.party, now)
            else:
                document = _json(body)
                split = lc.RewardSplit(
                    _field(document, "observer", int),
                    _field(document, "reviewer", int),
                    document.get("platform_fee", 0),
                )
                self.service.fund(request_id, principal.party, split, now)
            return 200, self._record_view(request_id)

        return work

    def reserve(self, principal, request, body, now, key):
        self._require(principal, "station")
        request_id = request.path_params["request_id"]
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
        self.service.deliver(request_id, principal.party, body, now, observations_format=fmt)
        return 200, self._record_view(request_id)

    def challenge(self, principal, request, body, now, key):
        self._require(principal, "requester", "station")
        request_id = request.path_params["request_id"]
        reason = _field(_json(body), "reason", str)
        self.service.challenge(request_id, principal.party, reason, now)
        return 200, self._record_view(request_id)

    def list_requests(self, principal, request, body, now):
        return {
            "requests": [
                {
                    "request_id": rid,
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
            return self._respond(work(request, self.clock()))

    def public_requests(self, request, now):
        return {"requests": self.service.published(now)}

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
        result = self.service.review(
            request.path_params["task_id"],
            principal.party,
            _field(document, "approve", bool),
            _field(document, "reason", str),
            now,
        )
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
        return {"party": party, "points": self.service.adapter.balance(party)}

    def grant(self, principal, request, body, now, key):
        self._require(principal, "admin")
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
        return 200, {"changed": self.service.tick(now)}


def create_app(
    service: RequestService, *, clock: Callable[[], datetime] | None = None
) -> Starlette:
    """The ASGI application for a stored service."""
    api = Api(service, clock or (lambda: datetime.now(tz=UTC)))
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
        # Public, no key: settled requests whose embargo has passed (step 1.8).
        Route("/v1/public/requests", api.public(api.public_requests), methods=["GET"]),
        Route("/v1/public/requests/{request_id}", api.public(api.public_request), methods=["GET"]),
        Route("/v1/public/files/{sha256}", api.public(api.public_file), methods=["GET"]),
    ]
    handlers = {
        ApiError: _handle_api_error,
        ServiceError: _handle_api_error,
        SettlementError: _handle_api_error,
    }
    return Starlette(routes=routes, exception_handlers=handlers)

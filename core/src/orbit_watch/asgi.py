"""The service as an ASGI application, set up by environment variables (phase 4, step 4.5;
decisions P4-05 and D-38).

Any ASGI server runs it (``uvicorn orbit_watch.asgi:app``), and so does Vercel, through the
few lines of ``core/asgi.py``. It is what ``orbit-watch serve`` runs, without the web
application (a host serves that) and without a follower thread (a schedule calls
``/v1/internal/follow``). The settings are ``serve``'s, from the environment
(``docs/deployment.md``):

* ``ORBIT_WATCH_DATABASE_URL`` or ``DATABASE_URL``: the database. Without one, every call is
  answered ``503 not_configured``: a preview deployment has no secrets (decision P4-12).
* ``ORBIT_WATCH_DATABASE_ROLE``: the role every transaction runs as;
  ``ORBIT_WATCH_DATABASE_SSLMODE``: libpq's ``sslmode``, ``verify-full`` in production.
* ``ORBIT_WATCH_NETWORK``: a known testnet, ``base-sepolia``, with
  ``ORBIT_WATCH_VERIFIER_KEY``, the escrow's verifier key, and ``ORBIT_WATCH_CHAIN_RPC``,
  a dedicated RPC endpoint.
* ``ORBIT_WATCH_ORIGINS``: the web origins that browsers sign in from, separated by commas.
* ``ORBIT_WATCH_FOLLOW_SECRET`` or ``CRON_SECRET``, ``ORBIT_WATCH_LIMITS``,
  ``ORBIT_WATCH_CLIENT_IP_HEADER`` and ``ORBIT_WATCH_STATION_DECIMALS``, as for ``serve``.

A service that cannot start answers ``503 not_configured`` too, and its log says why; the
log names no secret.
"""

from __future__ import annotations

import logging
import os
import sys
from typing import Any

from starlette.applications import Starlette
from starlette.middleware import Middleware
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.routing import Route

log = logging.getLogger("orbit_watch.asgi")

NETWORK_VARIABLE = "ORBIT_WATCH_NETWORK"
ORIGINS_VARIABLE = "ORBIT_WATCH_ORIGINS"


def not_configured(message: str) -> Starlette:
    """An application that answers every call ``503 not_configured``."""
    from orbit_watch.api import SecurityHeaders

    async def answer(request: Request) -> JSONResponse:
        return JSONResponse(
            {"error": {"code": "not_configured", "message": message}},
            status_code=503,
            headers={"Cache-Control": "no-store"},
        )

    methods = ["GET", "POST", "PUT", "DELETE"]
    return Starlette(
        routes=[Route("/{path:path}", answer, methods=methods)],
        middleware=[Middleware(SecurityHeaders)],
    )


def serve_arguments(environ: Any) -> list[str]:
    """``orbit-watch serve``'s arguments that the environment gives; the others take their
    defaults from the environment themselves."""
    argv = ["serve"]
    network = (environ.get(NETWORK_VARIABLE) or "").strip()
    if network:
        argv += ["--network", network]
    for origin in (environ.get(ORIGINS_VARIABLE) or "").split(","):
        if origin.strip():
            argv += ["--origin", origin.strip()]
    return argv


def from_environment() -> Starlette:
    """The service, set up by ``os.environ``."""
    from orbit_watch.cli import DATABASE_VARIABLES, ServeError, build_parser, serve_app

    environ = os.environ
    if not any(environ.get(name) for name in DATABASE_VARIABLES):
        return not_configured(
            "this deployment has no database: previews of the service run without one"
        )
    try:
        args = build_parser().parse_args(serve_arguments(environ))
        app, _, lines = serve_app(args, environ=environ)
    except (ServeError, SystemExit) as error:
        log.error("the service cannot start: %s", error)
        return not_configured("the service cannot start; its log says why")
    except Exception as error:  # the database or the chain: the message names no secret
        log.error("the service cannot start: %s: %s", type(error).__name__, error)
        return not_configured("the service cannot start; its log says why")
    for line in lines:
        print(line, file=sys.stderr)
    return app


app = from_environment()

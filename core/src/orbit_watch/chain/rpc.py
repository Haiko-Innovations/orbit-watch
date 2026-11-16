"""The service's JSON-RPC endpoints (phase 4, step 4.3; decision P4-07).

Base's public endpoints are rate limited and "not suitable for production apps", so the
service reads the chain through a dedicated endpoint, whose URL holds the provider's key,
and falls back to the public endpoint when the dedicated one does not answer.

**The dedicated endpoint's URL is a secret.** It comes from ``ORBIT_WATCH_CHAIN_RPC`` (or
``--chain-rpc``) and never reaches a response, a log or the browser:

* a failed call raises a ``RpcUnavailable`` that names the endpoint by its role only
  ("the dedicated endpoint"), with the cause's type and HTTP status, never its text,
  which would hold the URL; the original exception is not chained to it;
* urllib3, which sends the requests, names the request path in its debug lines; a filter
  on its logger replaces any secret part of an endpoint with ``[RPC endpoint]``;
* this provider never logs a URL, and ``str()`` of it names none.

An endpoint is tried after the one before it fails to connect, times out, or answers
with HTTP 429 or 5xx. Any other HTTP error (such as "too many blocks" for a log query)
is the answer, and the caller sees its status and body.
"""

from __future__ import annotations

import logging
import threading
from collections.abc import Sequence
from typing import Any
from urllib.parse import urlsplit

import requests
from web3.providers.base import JSONBaseProvider
from web3.types import RPCEndpoint, RPCResponse

from orbit_watch.chain import ChainError

TIMEOUT = 30.0
REDACTED = "[RPC endpoint]"
ROLES = ("the dedicated endpoint", "the fallback endpoint")
_FALL_THROUGH = {429, 500, 502, 503, 504}


def secret_parts(url: str) -> list[str]:
    """The parts of an endpoint URL that may hold its key: the whole URL, its path and
    query, and a password in it. Longest first."""
    split = urlsplit(url)
    parts = [url]
    path = split.path + (f"?{split.query}" if split.query else "")
    if path not in ("", "/"):
        parts.append(path)
    if split.password:
        parts.append(split.password)
    return sorted({p for p in parts if p}, key=len, reverse=True)


def redact(text: str, secrets: Sequence[str]) -> str:
    for secret in secrets:
        text = text.replace(secret, REDACTED)
    return text


class _Response:
    """What a caller may know of a refused call: its HTTP status and body, redacted."""

    def __init__(self, status_code: int, text: str):
        self.status_code = status_code
        self.text = text


class RpcUnavailable(ChainError):
    """No endpoint answered, or one refused the call. Names no URL."""

    def __init__(self, message: str, response: _Response | None = None):
        super().__init__("chain_unavailable", message)
        self.response = response


class _RedactingFilter(logging.Filter):
    def __init__(self, secrets: Sequence[str]):
        super().__init__()
        self.secrets = list(secrets)

    def filter(self, record: logging.LogRecord) -> bool:
        message = record.getMessage()
        cleaned = redact(message, self.secrets)
        if cleaned != message:
            record.msg, record.args = cleaned, ()
        return True


# urllib3's loggers that may name a request's URL or path.
_URLLIB3_LOGGERS = ("urllib3.connectionpool", "urllib3.util.retry", "urllib3.connection")


class ServiceRpc(JSONBaseProvider):
    """A web3 provider over ``endpoints``, tried in order. The first is the dedicated
    endpoint (secret); the others are fallbacks."""

    def __init__(self, endpoints: Sequence[str], timeout: float = TIMEOUT):
        super().__init__()
        if not endpoints:
            raise ValueError("give at least one RPC endpoint")
        self._endpoints = list(endpoints)
        self._timeout = timeout
        self._local = threading.local()
        self._secrets = sorted(
            {part for url in self._endpoints for part in secret_parts(url)}, key=len, reverse=True
        )
        self._filter = _RedactingFilter(self._secrets)
        for name in _URLLIB3_LOGGERS:
            logging.getLogger(name).addFilter(self._filter)

    def __str__(self) -> str:
        return f"Orbit Watch RPC ({len(self._endpoints)} endpoints)"

    __repr__ = __str__

    def redact(self, text: str) -> str:
        """``text`` without any secret part of the endpoints."""
        return redact(text, self._secrets)

    def _session(self) -> requests.Session:
        session = getattr(self._local, "session", None)
        if session is None:
            session = self._local.session = requests.Session()
        return session

    @staticmethod
    def _role(index: int) -> str:
        return ROLES[min(index, len(ROLES) - 1)]

    def make_request(self, method: RPCEndpoint, params: Any) -> RPCResponse:
        data = self.encode_rpc_request(method, params)
        failures = []
        for index, url in enumerate(self._endpoints):
            role = self._role(index)
            try:
                response = self._session().post(
                    url,
                    data=data,
                    headers={"Content-Type": "application/json"},
                    timeout=self._timeout,
                )
            except requests.RequestException as error:  # no answer: try the next one
                failures.append(f"{role}: {type(error).__name__}")
                continue
            if response.status_code in _FALL_THROUGH:
                failures.append(f"{role}: HTTP {response.status_code}")
                continue
            if response.status_code >= 400:
                raise RpcUnavailable(
                    f"{role} refused {method} (HTTP {response.status_code})",
                    _Response(response.status_code, self.redact(response.text[:2000])),
                )
            try:
                return self.decode_rpc_response(response.content)
            except ValueError:
                failures.append(f"{role}: not JSON-RPC")
                continue
        raise RpcUnavailable(f"no RPC endpoint answered {method} ({'; '.join(failures)})")

    def close(self) -> None:
        for name in _URLLIB3_LOGGERS:
            logging.getLogger(name).removeFilter(self._filter)


def service_endpoints(dedicated: str | None, public: str | None) -> list[str]:
    """The endpoints in order: the dedicated one, then the public one as a fallback."""
    endpoints = [url for url in (dedicated, public) if url]
    return list(dict.fromkeys(endpoints))

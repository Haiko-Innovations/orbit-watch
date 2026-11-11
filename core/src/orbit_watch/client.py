"""A small client for the phase 1 HTTP API, using only the standard library.

Used by the command line (step 1.7). The API address and key come from the
``--api`` and ``--key`` options or from the ``ORBIT_WATCH_API`` and
``ORBIT_WATCH_KEY`` environment variables; the environment keeps keys out of
the shell history.
"""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.parse
import urllib.request
import uuid
from dataclasses import dataclass
from typing import Any

from orbit_watch import __version__

DEFAULT_API = "http://127.0.0.1:8000"
TIMEOUT_S = 120  # deliveries are verified before the API answers


class ClientError(RuntimeError):
    """The API refused a call (``status`` is the HTTP status) or could not be reached
    (``status`` is 0)."""

    def __init__(self, code: str, message: str, status: int = 0):
        super().__init__(message)
        self.code = code
        self.status = status


@dataclass
class Reply:
    status: int
    body: bytes
    replayed: bool

    def json(self) -> Any:
        return json.loads(self.body.decode("utf-8"))


def _is_local(url: str) -> bool:
    host = urllib.parse.urlparse(url).hostname or ""
    return host in ("127.0.0.1", "localhost", "::1")


class ApiClient:
    def __init__(self, api: str | None = None, key: str | None = None):
        self.api = (api or os.environ.get("ORBIT_WATCH_API") or DEFAULT_API).rstrip("/")
        self.key = key or os.environ.get("ORBIT_WATCH_KEY")
        scheme = urllib.parse.urlparse(self.api).scheme
        if scheme not in ("http", "https"):
            raise ClientError(
                "bad_api", f"the API address must start with http:// or https://: {self.api}"
            )
        self.warnings: list[str] = []
        if scheme == "http" and not _is_local(self.api):
            self.warnings.append(
                f"{self.api} is not local and not https: the API key travels unencrypted"
            )

    def request(
        self,
        method: str,
        path: str,
        *,
        body: bytes | None = None,
        content_type: str = "application/json",
        idempotency_key: str | None = None,
        headers: dict[str, str] | None = None,
        auth: bool = True,
    ) -> Reply:
        all_headers = {"User-Agent": f"orbit-watch/{__version__}", "Accept": "application/json"}
        if auth:
            if not self.key:
                raise ClientError("no_key", "no API key: set ORBIT_WATCH_KEY or use --key")
            all_headers["Authorization"] = f"Bearer {self.key}"
        if body is not None:
            all_headers["Content-Type"] = content_type
        if method == "POST":
            all_headers["Idempotency-Key"] = idempotency_key or str(uuid.uuid4())
        all_headers.update(headers or {})
        request = urllib.request.Request(
            self.api + path, data=body, headers=all_headers, method=method
        )
        try:
            with urllib.request.urlopen(request, timeout=TIMEOUT_S) as response:
                return Reply(
                    response.status,
                    response.read(),
                    response.headers.get("Idempotent-Replayed") == "true",
                )
        except urllib.error.HTTPError as error:
            raw = error.read()
            try:
                detail = json.loads(raw.decode("utf-8"))["error"]
                raise ClientError(detail["code"], detail["message"], error.code) from None
            except (ValueError, KeyError, TypeError):
                raise ClientError(
                    "http_error", f"HTTP {error.code} from {self.api}{path}", error.code
                ) from None
        except urllib.error.URLError as error:
            raise ClientError(
                "unreachable",
                f"cannot reach {self.api} ({error.reason}); is the server running? "
                "(orbit-watch serve --dir ...)",
            ) from None

    def get(self, path: str, **kwargs: Any) -> Any:
        return self.request("GET", path, **kwargs).json()

    def post(
        self, path: str, document: dict[str, Any] | None = None, idempotency_key: str | None = None
    ) -> Reply:
        body = json.dumps(document).encode("utf-8") if document is not None else None
        return self.request("POST", path, body=body, idempotency_key=idempotency_key)

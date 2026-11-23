"""Polite download of public GP data from CelesTrak.

CelesTrak usage policy (https://celestrak.org/usage-policy.php, updated 2026-11-16):
GP data is updated once every two hours; download only what you need, once per
update; ask for ``FORMAT=csv`` ("FORMAT=json is ~3 times the size") and for
compressed data; automated clients must stop at the first non-200 response and
report it to a person; after a 500 or a 503 all requests stop for at least 15
minutes. A 403 answers abusive behaviour, and errors ignored again and again put
the address in the firewall. Large lists such as ``active`` are limited (read
again on 2026-11-21).

This module therefore makes exactly one request per call, never retries, asks
for CSV with gzip, and refuses to download the same file again within two hours
unless forced (decisions D-06 and P5-02). The service's follower uses it too
(``orbit_watch.orbit_follower``, decision D-48).
"""

from __future__ import annotations

import gzip
import http.client
import io
import time
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Callable
from pathlib import Path

from orbit_watch import __version__
from orbit_watch.catalog import CatalogError, parse_catalog

GP_URL = "https://celestrak.org/NORAD/elements/gp.php"
QUERY_KEYS = ("CATNR", "INTDES", "GROUP", "NAME")
UPDATE_INTERVAL_S = 2 * 3600
USER_AGENT = f"orbit-watch/{__version__} (+https://github.com/Haiko-Innovations/orbit-watch)"
MAX_BYTES = 50 * 1024 * 1024


class FetchError(RuntimeError):
    """A download that gave no data. ``status`` is the answer's HTTP status, or None when no
    answer came: the server could not be reached, or the connection broke or timed out."""

    def __init__(self, message: str, status: int | None = None):
        super().__init__(message)
        self.status = status


def build_url(key: str, value: str) -> str:
    if key not in QUERY_KEYS:
        raise ValueError(f"query must be one of {', '.join(QUERY_KEYS)}")
    return GP_URL + "?" + urllib.parse.urlencode({key: value, "FORMAT": "csv"})


def advice(status: int) -> str:
    """What CelesTrak's usage policy asks a client to do after an answer that is not 200."""
    if status in (500, 503):
        return (
            "CelesTrak's server is under heavy load: stop all requests for at least 15 minutes, "
            "as its usage policy asks"
        )
    if status == 404:
        return (
            "CelesTrak has no data for this query; do not ask for it again, since every 404 "
            "counts towards its error limit"
        )
    if status == 403:
        return "CelesTrak refused the request; read its message before asking again"
    if status == 301:
        return "the URL is outdated; correct it before asking again"
    return "not retrying, as CelesTrak's usage policy asks"


def read_body(response, limit: int) -> bytes:
    """The answer's body, decompressed if it came with gzip; at most ``limit`` bytes."""
    body = response.read(limit + 1)
    headers = getattr(response, "headers", None)
    encoding = (headers.get("Content-Encoding") or "") if headers is not None else ""
    if encoding.strip().lower() == "gzip":
        if len(body) > limit:
            raise FetchError("response is unexpectedly large; refusing to save it")
        try:
            with gzip.GzipFile(fileobj=io.BytesIO(body)) as stream:
                body = stream.read(limit + 1)
        except (OSError, EOFError) as exc:
            raise FetchError(f"the compressed answer could not be read: {exc}") from None
    if len(body) > limit:
        raise FetchError("response is unexpectedly large; refusing to save it")
    return body


def download_gp(key: str, value: str, *, opener: Callable = urllib.request.urlopen) -> bytes:
    """One request for GP data (OMM CSV), never retried; the answer's body if it is 200 with
    element sets. Raises ``FetchError`` with the HTTP status, or None without an answer."""
    return download_omm_csv(build_url(key, value), f"GP data for {key}={value}", opener=opener)


def download_omm_csv(url: str, what: str, *, opener: Callable = urllib.request.urlopen) -> bytes:
    """One request to CelesTrak for element sets in OMM CSV form, never retried: GP data, or
    supplemental GP (``orbit_watch.supgp``). The answer's body if it is 200 with element sets;
    otherwise ``FetchError`` with the HTTP status and what the usage policy asks next."""
    request = urllib.request.Request(
        url, headers={"User-Agent": USER_AGENT, "Accept-Encoding": "gzip"}
    )
    try:
        with opener(request, timeout=30) as response:
            status = getattr(response, "status", 200)
            body = read_body(response, MAX_BYTES) if status == 200 else b""
    except urllib.error.HTTPError as exc:
        detail = exc.read(300).decode("utf-8", errors="replace").strip()
        raise FetchError(
            f"CelesTrak answered HTTP {exc.code} for {url}: {detail} ({advice(exc.code)})",
            exc.code,
        ) from None
    except urllib.error.URLError as exc:
        raise FetchError(f"could not reach CelesTrak: {exc.reason}") from None
    except (OSError, http.client.HTTPException) as exc:
        raise FetchError(f"no answer from CelesTrak: {exc or type(exc).__name__}") from None
    except FetchError as exc:
        exc.status = 200
        raise
    if status != 200:
        raise FetchError(f"CelesTrak answered HTTP {status} for {url} ({advice(status)})", status)
    try:
        parse_catalog(body)
    except (CatalogError, ValueError, UnicodeDecodeError):
        text = body[:200].decode("utf-8", errors="replace").strip()
        raise FetchError(f"CelesTrak did not return {what}: {text}", 200) from None
    return body


def fetch_gp(
    key: str,
    value: str,
    output: Path,
    *,
    force: bool = False,
    opener: Callable = urllib.request.urlopen,
    now: Callable[[], float] = time.time,
) -> str:
    """Download GP data (OMM CSV) for one query to ``output``. Returns a status message."""
    return save_once(
        build_url(key, value),
        output,
        lambda: download_gp(key, value, opener=opener),
        what="GP data",
        force=force,
        now=now,
    )


def save_once(
    url: str,
    output: Path,
    download: Callable[[], bytes],
    *,
    what: str,
    force: bool = False,
    now: Callable[[], float] = time.time,
) -> str:
    """Save one CelesTrak answer to ``output``, unless the file is younger than two hours:
    CelesTrak updates GP data every two hours and asks for "a 2-hour minimum" for SupGP."""
    if output.exists() and not force:
        age = now() - output.stat().st_mtime
        if age < UPDATE_INTERVAL_S:
            return (
                f"{output} was downloaded {age / 60:.0f} min ago; CelesTrak asks for at least "
                f"two hours between downloads of {what}, so it was not downloaded again "
                "(use --force to override)"
            )
    body = download()
    catalog = parse_catalog(body)
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = output.with_name(output.name + ".part")
    temporary.write_bytes(body)
    temporary.replace(output)
    count = sum(len(sets) for sets in catalog.sets.values())
    return f"wrote {output} ({count} element set(s) from {url})"

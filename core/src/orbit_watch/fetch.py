"""Polite download of public GP data from CelesTrak.

CelesTrak usage policy (https://celestrak.org/usage-policy.php, updated 2026-11-16):
GP data is updated once every two hours; download only what you need, once per
update; ask for ``FORMAT=csv`` ("FORMAT=json is ~3 times the size") and for
compressed data; automated clients must stop at the first non-200 response and
report it to a person; after a 500 or a 503 all requests stop for at least 15
minutes. Repeated downloads of unchanged data get HTTP 403, and too many errors
put the address in the firewall. Large lists such as ``active`` are limited.

This module therefore makes exactly one request per call, never retries, asks
for CSV with gzip, and refuses to download the same file again within two hours
unless forced (decisions D-06 and P5-02).
"""

from __future__ import annotations

import gzip
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
    pass


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
            "CelesTrak has no GP data for this query; do not ask for it again, since every 404 "
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
    url = build_url(key, value)
    if output.exists() and not force:
        age = now() - output.stat().st_mtime
        if age < UPDATE_INTERVAL_S:
            return (
                f"{output} was downloaded {age / 60:.0f} min ago; CelesTrak updates GP data "
                "every 2 hours, so it was not downloaded again (use --force to override)"
            )
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
            f"CelesTrak answered HTTP {exc.code} for {url}: {detail} ({advice(exc.code)})"
        ) from None
    except urllib.error.URLError as exc:
        raise FetchError(f"could not reach CelesTrak: {exc.reason}") from None
    if status != 200:
        raise FetchError(f"CelesTrak answered HTTP {status} for {url} ({advice(status)})")
    try:
        catalog = parse_catalog(body)
    except (CatalogError, ValueError, UnicodeDecodeError):
        text = body[:200].decode("utf-8", errors="replace").strip()
        raise FetchError(f"CelesTrak did not return GP data for {key}={value}: {text}") from None
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = output.with_name(output.name + ".part")
    temporary.write_bytes(body)
    temporary.replace(output)
    return f"wrote {output} ({len(catalog.records)} element set(s) from {url})"

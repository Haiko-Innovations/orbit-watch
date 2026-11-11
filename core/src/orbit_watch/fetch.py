"""Polite download of public GP data from CelesTrak.

CelesTrak usage policy (https://celestrak.org/usage-policy.php, read 2026-11-11):
GP data is updated once every two hours; download only what you need, once per
update; automated clients must stop at the first non-200 response. Repeated
downloads of unchanged data get HTTP 403, and too many errors put the address
in the firewall.

This module therefore makes exactly one request per call, never retries, and
refuses to download the same file again within two hours unless forced.
"""

from __future__ import annotations

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
    return GP_URL + "?" + urllib.parse.urlencode({key: value, "FORMAT": "JSON"})


def fetch_gp(
    key: str,
    value: str,
    output: Path,
    *,
    force: bool = False,
    opener: Callable = urllib.request.urlopen,
    now: Callable[[], float] = time.time,
) -> str:
    """Download GP data (OMM JSON) for one query to ``output``. Returns a status message."""
    url = build_url(key, value)
    if output.exists() and not force:
        age = now() - output.stat().st_mtime
        if age < UPDATE_INTERVAL_S:
            return (
                f"{output} was downloaded {age / 60:.0f} min ago; CelesTrak updates GP data "
                "every 2 hours, so it was not downloaded again (use --force to override)"
            )
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    try:
        with opener(request, timeout=30) as response:
            status = getattr(response, "status", 200)
            body = response.read(MAX_BYTES + 1)
    except urllib.error.HTTPError as exc:
        detail = exc.read(300).decode("utf-8", errors="replace").strip()
        raise FetchError(
            f"CelesTrak answered HTTP {exc.code} for {url}: {detail} "
            "(not retrying, as the CelesTrak usage policy asks)"
        ) from None
    except urllib.error.URLError as exc:
        raise FetchError(f"could not reach CelesTrak: {exc.reason}") from None
    if status != 200:
        raise FetchError(f"CelesTrak answered HTTP {status} for {url} (not retrying)")
    if len(body) > MAX_BYTES:
        raise FetchError("response is unexpectedly large; refusing to save it")
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

import io
import json
import os
import urllib.error

import pytest
from helpers import catalog_bytes

from orbit_watch.allowlist import build_policy
from orbit_watch.cli import main
from orbit_watch.documents import TargetPolicy
from orbit_watch.fetch import FetchError, build_url, fetch_gp

RECORD = json.loads(catalog_bytes())["records"][0]


class FakeResponse(io.BytesIO):
    status = 200

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


def opener_returning(body: bytes, calls: list):
    def opener(request, timeout):
        calls.append(request)
        return FakeResponse(body)

    return opener


def test_url_and_user_agent(tmp_path):
    assert build_url("CATNR", "25544") == (
        "https://celestrak.org/NORAD/elements/gp.php?CATNR=25544&FORMAT=JSON"
    )
    with pytest.raises(ValueError):
        build_url("SPECIAL", "x")
    calls = []
    fetch_gp(
        "GROUP",
        "cubesat",
        tmp_path / "gp.json",
        opener=opener_returning(json.dumps([RECORD]).encode(), calls),
    )
    assert len(calls) == 1
    assert calls[0].get_header("User-agent").startswith("orbit-watch/")


def test_does_not_download_twice_within_two_hours(tmp_path):
    target = tmp_path / "gp.json"
    calls = []
    opener = opener_returning(json.dumps([RECORD]).encode(), calls)
    fetch_gp("CATNR", "339001", target, opener=opener)
    message = fetch_gp("CATNR", "339001", target, opener=opener)
    assert len(calls) == 1 and "not downloaded again" in message
    later = target.stat().st_mtime + 2 * 3600 + 1
    fetch_gp("CATNR", "339001", target, opener=opener, now=lambda: later)
    assert len(calls) == 2


def test_http_error_is_not_retried(tmp_path):
    calls = []

    def opener(request, timeout):
        calls.append(request)
        raise urllib.error.HTTPError(
            request.full_url,
            403,
            "Forbidden",
            {},
            io.BytesIO(b"GP data has not updated since your last download"),
        )

    with pytest.raises(FetchError, match=r"HTTP 403.*not retrying"):
        fetch_gp("GROUP", "active", tmp_path / "gp.json", opener=opener)
    assert len(calls) == 1
    assert not (tmp_path / "gp.json").exists()


def test_non_gp_answer_is_rejected(tmp_path):
    with pytest.raises(FetchError, match="No GP data found"):
        fetch_gp(
            "CATNR", "1", tmp_path / "gp.json", opener=opener_returning(b"No GP data found", [])
        )


def gp(*records):
    return json.dumps(list(records)).encode()


def rec(norad, name):
    return {**RECORD, "NORAD_CAT_ID": norad, "OBJECT_NAME": name}


def test_allowlist_excludes_files_and_name_patterns():
    include = gp(
        rec(1, "CUBESAT ONE"),
        rec(2, "USA 123"),
        rec(3, "COSMOS 2500"),
        rec(4, "SCIENCE SAT"),
        rec(5, "STARSHIELD 1"),
    )
    exclude = gp(rec(4, "SCIENCE SAT"))
    policy = build_policy([include], [exclude])
    assert [a["norad_id"] for a in policy["allow"]] == [1]
    assert "1 removed by exclusion files and 3 by name patterns" in policy["description"]
    assert TargetPolicy.parse(json.dumps(policy).encode()).allows(1)
    relaxed = build_policy([include], [], use_default_patterns=False)
    assert len(relaxed["allow"]) == 5


def test_cli_allowlist_and_submit(tmp_path, capsys, examples_dir):
    include = tmp_path / "cubesat.json"
    include.write_bytes(gp(rec(1, "CUBESAT ONE"), rec(2, "USA 9")))
    out = tmp_path / "policy.json"
    assert main(["allowlist", "build", "--include", str(include), "-o", str(out)]) == 0
    assert json.loads(out.read_text())["allow"] == [{"norad_id": 1, "name": "CUBESAT ONE"}]
    delivery = examples_dir / "simulated" / "datasets" / "acceptable" / "delivery.json"
    # Port 9 (discard) has no API server: the client reports that clearly.
    assert main(["submit", str(delivery), "--api", "http://127.0.0.1:9", "--key", "ow_x"]) == 2
    assert "is the server running" in capsys.readouterr().err


def test_cli_fetch_requires_one_query(tmp_path):
    assert main(["fetch-gp", "-o", str(tmp_path / "x.json")]) == 2
    assert main(["fetch-gp", "--catnr", "1", "--group", "x", "-o", str(tmp_path / "x.json")]) == 2


@pytest.mark.skipif(
    os.environ.get("ORBIT_WATCH_NETWORK_TESTS") != "1",
    reason="set ORBIT_WATCH_NETWORK_TESTS=1 to make one real CelesTrak request",
)
def test_real_celestrak_request(tmp_path):
    message = fetch_gp("CATNR", "25544", tmp_path / "iss.json")
    assert "element set" in message

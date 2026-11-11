"""The whole request chain from the command line, against a real HTTP server (step 1.7)."""

import json
import socket
import threading
import time
from pathlib import Path

import pytest
import uvicorn
from helpers import catalog_bytes, packaged, policy_bytes

from orbit_watch.api import create_app, keys
from orbit_watch.cli import main
from orbit_watch.reviewers import ReviewerRegistry
from orbit_watch.service import VerificationContext, open_service
from orbit_watch.timeutil import parse_utc

ROOT = Path(__file__).resolve().parents[2]
SIMULATED = ROOT / "examples" / "simulated"
REQUESTER = "requester:sim-cubesat-team"
STATION = "station:SIM-ESPOO"


class Clock:
    def __init__(self):
        self.now = parse_utc("2026-11-01T12:00:00Z")

    def __call__(self):
        return self.now

    def at(self, text):
        self.now = parse_utc(text)


def free_port():
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


@pytest.fixture
def server(tmp_path):
    registry = ReviewerRegistry.parse(packaged("reviewers.json"))
    context = VerificationContext(catalog=catalog_bytes(), policy=policy_bytes())
    service = open_service(tmp_path / "service", registry, context)
    clock = Clock()
    with service.storage.db.transaction():
        admin = keys.create_key(service.storage.db, "admin:maintainer", "admin", clock())
    port = free_port()
    config = uvicorn.Config(
        create_app(service, clock=clock), host="127.0.0.1", port=port, log_level="warning"
    )
    runner = uvicorn.Server(config)
    thread = threading.Thread(target=runner.run, daemon=True)
    thread.start()
    deadline = time.monotonic() + 10
    while not runner.started and time.monotonic() < deadline:
        time.sleep(0.05)
    assert runner.started, "the API server did not start"
    yield {
        "api": f"http://127.0.0.1:{port}",
        "admin": admin,
        "clock": clock,
        "service": service,
        "tmp": tmp_path,
    }
    runner.should_exit = True
    thread.join(timeout=10)
    service.storage.close()


def run(server, key, *argv, capsys):
    code = main([*argv, "--api", server["api"], "--key", key])
    captured = capsys.readouterr()
    return code, captured.out, captured.err


def make_key(server, party, role, capsys):
    target = server["tmp"] / f"{party.replace(':', '_')}.key"
    code, _, _ = run(
        server, server["admin"], "admin", "key", party, role, "-o", str(target), capsys=capsys
    )
    assert code == 0 and oct(target.stat().st_mode)[-3:] == "600"
    return target.read_text().strip()


def test_the_whole_chain_from_the_command_line(server, capsys):
    clock = server["clock"]
    requester = make_key(server, REQUESTER, "requester", capsys)
    station = make_key(server, STATION, "station", capsys)
    code, out, _ = run(server, server["admin"], "admin", "grant", REQUESTER, "1000", capsys=capsys)
    assert code == 0 and "1000 points" in out

    code, out, _ = run(
        server, requester, "request", "create", str(SIMULATED / "request.json"), capsys=capsys
    )
    assert code == 0 and "Request SIM-REQ-0001: draft" in out
    clock.at("2026-11-01T12:01:00Z")
    assert run(server, requester, "request", "open", "SIM-REQ-0001", capsys=capsys)[0] == 0
    code, out, _ = run(
        server,
        requester,
        "request",
        "fund",
        "SIM-REQ-0001",
        "--observer",
        "100",
        "--reviewer",
        "10",
        "--platform-fee",
        "5",
        capsys=capsys,
    )
    assert code == 0 and "deposit: 135 points" in out
    code, out, _ = run(server, station, "reserve", "SIM-REQ-0001", capsys=capsys)
    assert code == 0 and f"reserved by {STATION}" in out

    # The station delivers the simulated wrong-target dataset through its manifest.
    clock.at("2026-11-02T04:00:00Z")
    manifest = SIMULATED / "datasets" / "wrong_target" / "delivery.json"
    code, out, err = run(server, station, "submit", str(manifest), capsys=capsys)
    assert code == 0, err
    assert "automated verification: fail" in out and "idempotency key:" in err

    clock.at("2026-11-02T05:00:00Z")
    code, out, _ = run(
        server,
        station,
        "challenge",
        "SIM-REQ-0001",
        "--reason",
        "I am sure this was SIM-CUBESAT-A",
        capsys=capsys,
    )
    assert code == 0 and "in_review" in out
    code, out, _ = run(
        server, requester, "request", "show", "SIM-REQ-0001", "--json", capsys=capsys
    )
    reviewers = json.loads(out)["record"]["reviewers"]

    clock.at("2026-11-02T06:00:00Z")
    for reviewer in reviewers[:2]:
        key = make_key(server, reviewer, "reviewer", capsys)
        code, out, _ = run(server, key, "review", "list", "--json", capsys=capsys)
        tasks = json.loads(out)["tasks"]
        assert len(tasks) == 2
        for task in tasks:
            code, out, _ = run(
                server,
                key,
                "review",
                "answer",
                task["task_id"],
                "--reject",
                "--reason",
                "The track belongs to the neighbouring object",
                capsys=capsys,
            )
            assert code == 0 and "recorded" in out

    code, out, _ = run(server, requester, "request", "show", "SIM-REQ-0001", capsys=capsys)
    assert "settled (rejected)" in out and "+10 (review)" in out
    code, out, _ = run(server, requester, "request", "report", "SIM-REQ-0001", capsys=capsys)
    assert "FAIL" in out and "residuals" in out.lower()
    code, out, _ = run(server, requester, "balance", REQUESTER, capsys=capsys)
    assert out.strip() == f"{REQUESTER}: 980 points"
    code, out, _ = run(server, requester, "request", "list", capsys=capsys)
    assert "SIM-REQ-0001" in out and "rejected" in out


def test_retries_with_the_same_key_are_safe(server, capsys):
    args = ("admin", "grant", REQUESTER, "50", "--idempotency-key", "budget-2026-11")
    first = run(server, server["admin"], *args, capsys=capsys)
    second = run(server, server["admin"], *args, capsys=capsys)
    assert first[1] == second[1] == f"{REQUESTER} now holds 50 points\n"
    assert "replayed" in second[2]


def test_refusals_and_missing_keys_are_clear(server, capsys, monkeypatch):
    station = make_key(server, STATION, "station", capsys)
    code, _, err = run(server, station, "admin", "grant", STATION, "5", capsys=capsys)
    assert code == 1 and "forbidden_role" in err
    monkeypatch.delenv("ORBIT_WATCH_KEY", raising=False)
    assert main(["request", "list", "--api", server["api"]]) == 2
    assert "no_key" in capsys.readouterr().err
    monkeypatch.setenv("ORBIT_WATCH_API", server["api"])
    monkeypatch.setenv("ORBIT_WATCH_KEY", station)
    assert main(["request", "list"]) == 0
    assert "no requests" in capsys.readouterr().out


def test_plain_http_to_another_host_warns(capsys):
    from orbit_watch.client import ApiClient

    client = ApiClient("http://example.org", "ow_x")
    assert client.warnings and "unencrypted" in client.warnings[0]
    assert ApiClient("https://example.org", "ow_x").warnings == []

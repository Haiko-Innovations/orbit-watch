"""The whole request chain from the command line, on a local chain (phase 2, step 2.6).

A real HTTP server follows a local Anvil chain; every party runs the command line with its
own encrypted keystore. The test records everything that reaches the server and checks that
no key, keystore or password is ever among it ("no key ever leaves its owner"). Everything
is LOCAL and SIMULATED.
"""

import json
import socket
import threading
import time
from pathlib import Path

import pytest
from anvil import require_local_chain
from chain_world import PLATFORM, REQUESTER, REVIEWERS, STATION, ChainWorld

from orbit_watch.api import create_app, keys
from orbit_watch.cli import main

ROOT = Path(__file__).resolve().parents[2]
SIMULATED = ROOT / "examples" / "simulated"
RID = "SIM-REQ-0001"
PASSWORD = "local test password"


class Recorder:
    """ASGI middleware that keeps every byte a client sends to the server."""

    def __init__(self, app):
        self.app = app
        self.seen: list[bytes] = []

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)
        self.seen.append(scope["path"].encode() + b"?" + scope.get("query_string", b""))
        self.seen += [name + b": " + value for name, value in scope["headers"]]

        async def recording_receive():
            message = await receive()
            if message["type"] == "http.request":
                self.seen.append(message.get("body", b""))
            return message

        return await self.app(scope, recording_receive, send)


def free_port():
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


@pytest.fixture
def server(tmp_path):
    require_local_chain()
    import uvicorn
    from eth_account import Account

    world = ChainWorld(tmp_path / "service")
    with world.service.storage.db.transaction():
        admin = keys.create_key(world.service.storage.db, "admin:sim", "admin", world.link.now())
    recorder = Recorder(create_app(world.service))
    port = free_port()
    runner = uvicorn.Server(
        uvicorn.Config(recorder, host="127.0.0.1", port=port, log_level="warning")
    )
    thread = threading.Thread(target=runner.run, daemon=True)
    thread.start()
    deadline = time.monotonic() + 10
    while not runner.started and time.monotonic() < deadline:
        time.sleep(0.05)
    assert runner.started, "the API server did not start"
    # Every party's own encrypted keystore and password file, as 'cast wallet import' makes.
    wallets = tmp_path / "wallets"
    wallets.mkdir()
    password_file = wallets / "password"
    password_file.write_text(PASSWORD + "\n")
    keystores = {}
    for party, account in world.deployment.accounts.items():
        keystore = wallets / party.replace(":", "_")
        keystore.write_text(
            json.dumps(Account.encrypt(account.key, PASSWORD, kdf="pbkdf2", iterations=1000))
        )
        keystores[party] = keystore
    yield {
        "world": world,
        "api": f"http://127.0.0.1:{port}",
        "rpc": world.w3.provider.endpoint_uri,
        "admin": admin,
        "keystores": keystores,
        "password_file": password_file,
        "recorder": recorder,
        "tmp": tmp_path,
    }
    runner.should_exit = True
    thread.join(timeout=10)
    world.stop()


def run(server, key, *argv, party=None, capsys):
    signing = []
    if party is not None:
        signing = [
            "--keystore",
            str(server["keystores"][party]),
            "--password-file",
            str(server["password_file"]),
            "--rpc",
            server["rpc"],
        ]
    code = main([*argv, "--api", server["api"], "--key", key, *signing])
    captured = capsys.readouterr()
    return code, captured.out, captured.err


def make_key(server, party, capsys):
    target = server["tmp"] / f"{party.replace(':', '_')}.key"
    role = party.split(":")[0]
    code, _, err = run(
        server, server["admin"], "admin", "key", party, role, "-o", str(target), capsys=capsys
    )
    assert code == 0, err
    return target.read_text().strip()


def test_the_whole_chain_from_the_command_line(server, capsys):
    world = server["world"]
    code, out, _ = run(server, server["admin"], "chain", capsys=capsys)
    assert code == 0 and "local Anvil test chain, no real value" in out and "TESTUSD" in out

    # Every party registers its own wallet first; reviewers too, before any round.
    keys_of = {party: make_key(server, party, capsys) for party in (REQUESTER, STATION, *REVIEWERS)}
    for party, key in keys_of.items():
        code, out, err = run(server, key, "wallet", "register", party=party, capsys=capsys)
        assert code == 0, err
        assert world.address(party) in out

    requester = keys_of[REQUESTER]
    code, out, _ = run(
        server, requester, "request", "create", str(SIMULATED / "request.json"), capsys=capsys
    )
    assert code == 0 and f"Request {RID}: draft" in out
    assert run(server, requester, "request", "open", RID, capsys=capsys)[0] == 0
    code, out, err = run(
        server,
        requester,
        "request",
        "fund",
        RID,
        "--observer",
        "100",
        "--reviewer",
        "10",
        "--platform-fee",
        "5",
        party=REQUESTER,
        capsys=capsys,
    )
    assert code == 0, err
    assert "sent approve:" in err and "sent fund:" in err
    assert "deposit: 135 TESTUSD (observer 100 TESTUSD" in out
    assert "on chain (local Anvil test chain, no real value): Funded" in out

    # The station signs with another wallet: the command line prints the transaction, the
    # wallet sends it (here eth_account, as 'cast send' would), and the hash is reported.
    station = keys_of[STATION]
    code, out, err = run(server, station, "reserve", RID, "--unsigned", capsys=capsys)
    assert code == 0 and "cast send" in err and "orbit-watch tx report" in err
    unsigned = json.loads(out)["sign"][0]["transaction"]
    tx_hash = world.wallet(STATION).send(unsigned)
    code, out, err = run(server, station, "tx", "report", tx_hash, capsys=capsys)
    assert code == 0, err
    assert f"reserved by {STATION}" in out and f"confirmed: reserve for {RID}" in err

    world.travel("2026-11-02T04:00:00Z")
    manifest = SIMULATED / "datasets" / "wrong_target" / "delivery.json"
    code, out, err = run(server, station, "submit", str(manifest), party=STATION, capsys=capsys)
    assert code == 0, err
    assert "automated verification: fail" in out and "VerificationRecorded" in out

    code, out, err = run(
        server,
        station,
        "challenge",
        RID,
        "--reason",
        "I am sure this was SIM-CUBESAT-A",
        party=STATION,
        capsys=capsys,
    )
    assert code == 0, err
    assert "in_review" in out
    code, out, _ = run(server, requester, "request", "show", RID, "--json", capsys=capsys)
    reviewers = json.loads(out)["record"]["reviewers"]
    assert [world.link.address_of(r) for r in reviewers] == list(
        world.chain.request(RID)["reviewers"]
    )

    for reviewer in reviewers[:2]:
        key = keys_of[reviewer]
        code, out, _ = run(server, key, "review", "list", "--json", capsys=capsys)
        for task in json.loads(out)["tasks"]:
            code, out, err = run(
                server,
                key,
                "review",
                "answer",
                task["task_id"],
                "--reject",
                "--reason",
                "The track belongs to the neighbouring object",
                party=reviewer,
                capsys=capsys,
            )
            assert code == 0, err

    code, out, _ = run(server, requester, "request", "show", RID, capsys=capsys)
    assert "settled (rejected)" in out and "+10 TESTUSD (review)" in out
    assert "+115 TESTUSD (refund)" in out and "Settled" in out

    # Credits move as token transfers when withdrawn, each by its own owner.
    reviewer = reviewers[0]
    key = keys_of[reviewer]
    code, out, _ = run(server, key, "balance", reviewer, capsys=capsys)
    assert f"0 TESTUSD in {world.address(reviewer)}, 10 TESTUSD to withdraw" in out
    code, out, err = run(server, key, "wallet", "withdraw", party=reviewer, capsys=capsys)
    assert code == 0 and "sent withdraw" in err, err
    code, out, _ = run(server, key, "balance", reviewer, capsys=capsys)
    assert f"10 TESTUSD in {world.address(reviewer)}, 0 TESTUSD to withdraw" in out
    code, out, err = run(server, requester, "wallet", "withdraw", party=REQUESTER, capsys=capsys)
    assert code == 0, err
    code, out, _ = run(server, requester, "balance", REQUESTER, capsys=capsys)
    assert f"980 TESTUSD in {world.address(REQUESTER)}, 0 TESTUSD to withdraw" in out
    code, out, _ = run(server, server["admin"], "balance", PLATFORM, capsys=capsys)
    assert "0 TESTUSD to withdraw" in out  # rejected: no platform fee
    code, out, _ = run(server, station, "tx", "list", capsys=capsys)
    assert out.count("confirmed:") == 3 and "local Anvil test chain" in out

    # No key ever left its owner: nothing that reached the server holds a private key, a
    # keystore or its password, and neither does anything the service stored.
    secrets = [PASSWORD.encode()]
    for party, account in world.deployment.accounts.items():
        if party == "system:verifier":
            continue  # the service's own key
        raw = bytes(account.key)
        secrets += [raw, raw.hex().encode(), raw.hex().upper().encode()]
        keystore = json.loads(server["keystores"][party].read_text())
        secrets.append(keystore["crypto"]["ciphertext"].encode())
    sent = b"\n".join(server["recorder"].seen)
    assert b"Authorization" in sent or b"authorization" in sent  # the recorder works
    assert not [s for s in secrets if s in sent]
    stored = b"".join(
        path.read_bytes() for path in (server["tmp"] / "service").rglob("*") if path.is_file()
    )
    assert not [s for s in secrets if s in stored]

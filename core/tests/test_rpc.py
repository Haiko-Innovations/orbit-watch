"""The service's RPC endpoints (phase 4, step 4.3; decision P4-07).

The service reads the chain through a dedicated endpoint whose URL holds a key, with the
public endpoint as its fallback. The key must never reach a response, a log or the
browser. Here a LOCAL stand-in for such a provider forwards to a throw-away Anvil chain at
``/v2/<key>`` with a made-up key, and the tests look for the key everywhere. Everything
is LOCAL and SIMULATED.
"""

import argparse
import http.server
import json
import logging
import threading
import urllib.request

import pytest
from helpers import catalog_bytes, policy_bytes
from web3 import Web3

from orbit_watch.chain import ChainError
from orbit_watch.chain.rpc import REDACTED, RpcUnavailable, ServiceRpc, secret_parts

KEY = "sim-made-up-key-7c1e4b9a"  # what a provider's key would be: looked for everywhere


class KeyedEndpoint:
    """A LOCAL stand-in for a dedicated RPC provider: JSON-RPC at ``/v2/<KEY>``, forwarded
    to Anvil. ``mode`` makes it busy (503), limit callers (429) or refuse a call as too
    big (413); like some providers, it then echoes the URL it was called at."""

    def __init__(self, upstream: str):
        self.upstream = upstream
        self.mode = "ok"
        self.calls = 0
        endpoint = self

        class Handler(http.server.BaseHTTPRequestHandler):
            def do_POST(self):
                body = self.rfile.read(int(self.headers.get("Content-Length", 0)))
                if self.path != f"/v2/{KEY}":
                    return self._send(401, b"unknown key")
                endpoint.calls += 1
                codes = {"busy": 503, "limited": 429, "too_big": 413}
                if endpoint.mode in codes:
                    text = f"no: {endpoint.mode} at {endpoint.url}".encode()
                    return self._send(codes[endpoint.mode], text)
                forwarded = urllib.request.Request(
                    upstream, data=body, headers={"Content-Type": "application/json"}
                )
                with urllib.request.urlopen(forwarded, timeout=30) as reply:
                    self._send(200, reply.read())

            def _send(self, code, data):
                self.send_response(code)
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)

            def log_message(self, *args):  # the stand-in's own log is not the service's
                pass

        self.server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.url = f"http://127.0.0.1:{self.server.server_address[1]}/v2/{KEY}"
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()

    def stop(self):
        self.server.shutdown()
        self.server.server_close()


@pytest.fixture
def world(database):
    from anvil import require_local_chain
    from chain_world import ChainWorld

    require_local_chain()
    made = ChainWorld(database)
    yield made
    made.stop()


@pytest.fixture
def endpoint(world):
    made = KeyedEndpoint(world.local.w3.provider.endpoint_uri)
    yield made
    made.stop()


def through(world, *endpoints):
    """The world's service again, reading the chain through ``endpoints`` only."""
    from chain_world import REGISTRY, VERIFIER

    from orbit_watch.chain.client import OrbitWatchChain
    from orbit_watch.chain.link import ChainLink
    from orbit_watch.service import VerificationContext, open_service

    world.service.storage.close()
    chain = OrbitWatchChain(Web3(ServiceRpc(list(endpoints))), world.deployment.escrow.address)
    link = ChainLink(chain, world.account(VERIFIER), receipt_timeout=30)
    context = VerificationContext(catalog=catalog_bytes(), policy=policy_bytes())
    world.service = open_service(world.database, REGISTRY, context, chain=link)
    return world.service


def recording(api):
    """Keep every response the API gives."""
    seen = []
    original = api.http.request

    def request(*args, **kwargs):
        reply = original(*args, **kwargs)
        seen.append(reply.text + str(dict(reply.headers)))
        return reply

    api.http.request = request
    return seen


def test_the_key_is_never_in_a_response_or_a_log(world, endpoint, caplog):
    """The whole chain of a request through the dedicated endpoint, with every log line
    the service, web3, requests and urllib3 write, at debug level."""
    from test_chain_service import Api, deliver, open_and_fund

    caplog.set_level(logging.DEBUG)
    through(world, endpoint.url, world.local.w3.provider.endpoint_uri)
    api = Api(world)
    seen = recording(api)
    open_and_fund(api)
    deliver(api, "acceptable")
    world.travel("2026-11-03T05:00:00Z")
    assert len(api.tick()["sent"]) == 1
    assert api.view()["summary"]["status"] == "settled"
    for path in (
        "/v1/chain",
        "/v1/health",
        "/v1/admin/overview",
        "/v1/admin/governance",
        "/v1/transactions",
        "/v1/public/attestations",
    ):
        api.get(path)
    assert endpoint.calls > 50  # the service read the chain through it
    assert seen and not [text for text in seen if KEY in text]
    assert KEY not in caplog.text
    assert REDACTED in caplog.text  # urllib3 names each request's path, redacted


def test_a_busy_endpoint_falls_back_to_the_public_one(world, endpoint, caplog):
    from test_chain_service import Api, open_and_fund

    caplog.set_level(logging.DEBUG)
    through(world, endpoint.url, world.local.w3.provider.endpoint_uri)
    api = Api(world)
    seen = recording(api)
    for mode in ("busy", "limited"):
        endpoint.mode = mode
        before = endpoint.calls
        assert api.get("/v1/chain").status_code == 200
        assert endpoint.calls > before  # tried first, every time
    open_and_fund(api)  # the whole of it on the fallback
    assert not [text for text in seen if KEY in text]
    assert KEY not in caplog.text


def test_without_an_answer_the_error_names_no_url(world, endpoint, caplog):
    from test_chain_service import Api

    caplog.set_level(logging.DEBUG)
    through(world, endpoint.url)  # no fallback
    api = Api(world)
    seen = recording(api)
    endpoint.mode = "busy"
    reply = api.get("/v1/requests")
    assert reply.status_code == 503
    error = reply.json()["error"]
    assert error["code"] == "chain_unavailable"
    assert "the dedicated endpoint: HTTP 503" in error["message"]
    endpoint.stop()  # nobody answers at all
    reply = api.get("/v1/requests")
    assert reply.status_code == 503
    assert "the dedicated endpoint: ConnectionError" in reply.json()["error"]["message"]
    assert not [text for text in seen if KEY in text]
    assert KEY not in caplog.text


def test_a_refusal_keeps_its_status_and_body_without_the_url(world, endpoint):
    """Some providers refuse a log query over too many blocks with HTTP 413; the service
    then asks for fewer (chain/client.py), which needs the status and the body."""
    provider = ServiceRpc([endpoint.url, world.local.w3.provider.endpoint_uri])
    endpoint.mode = "too_big"
    with pytest.raises(RpcUnavailable) as raised:
        provider.make_request("eth_getLogs", [{}])
    error = raised.value
    assert isinstance(error, ChainError) and error.code == "chain_unavailable"
    assert error.response.status_code == 413
    assert KEY not in error.response.text and REDACTED in error.response.text
    assert KEY not in str(error) and error.__cause__ is None and error.__context__ is None
    assert KEY not in str(provider) and KEY not in repr(provider)
    provider.close()


def test_the_command_line_takes_the_endpoint_from_the_environment(
    world, endpoint, monkeypatch, capsys, tmp_path
):
    from chain_world import VERIFIER
    from eth_account import Account

    from orbit_watch.cli import _chain_link, build_parser

    monkeypatch.setenv("ORBIT_WATCH_CHAIN_RPC", endpoint.url)
    parsed = build_parser().parse_args(["serve", "--escrow", world.chain.escrow.address])
    assert parsed.chain_rpc == endpoint.url
    keystore = tmp_path / "verifier.json"
    password = tmp_path / "password"
    password.write_text("local test password\n")
    encrypted = Account.encrypt(
        world.account(VERIFIER).key, "local test password", kdf="pbkdf2", iterations=1000
    )
    keystore.write_text(json.dumps(encrypted))
    keystore.chmod(0o600)
    args = argparse.Namespace(
        chain_rpc=parsed.chain_rpc,
        escrow=world.chain.escrow.address,
        verifier_keystore=str(keystore),
        verifier_password_file=str(password),
        from_block=0,
        confirmations=None,
        fallback_rpc=world.local.w3.provider.endpoint_uri,
    )
    before = endpoint.calls
    link = _chain_link(args)
    assert endpoint.calls > before
    output = capsys.readouterr()
    assert KEY not in output.out + output.err
    assert KEY not in str(link.chain.w3.provider)


def test_the_secret_parts_of_an_endpoint():
    assert secret_parts("https://base-sepolia.example/v2/abc") == [
        "https://base-sepolia.example/v2/abc",
        "/v2/abc",
    ]
    assert "k3y" in secret_parts("https://rpc.example/?apikey=k3y")[1]
    assert "pa55" in secret_parts("https://user:pa55@rpc.example/")
    assert secret_parts("https://sepolia.base.org") == ["https://sepolia.base.org"]

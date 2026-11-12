"""The phase 2 demo on a local chain (phase 2, step 2.8).

The same demo that ran on Base Sepolia (examples/phase2), against a real HTTP server on a
local Anvil chain, with every party's own encrypted keystore. The chain's clock jumps to each
deadline instead of waiting. Everything is LOCAL and SIMULATED.
"""

import json
import socket
import threading
import time
from datetime import UTC, datetime

import pytest
from anvil import Deployment, require_local_chain
from chain_world import PLATFORM, REGISTRY, REQUESTER, REVIEWERS, VERIFIER
from helpers import catalog_bytes, policy_bytes

from orbit_watch.api import create_app, keys
from orbit_watch.sim.phase2_demo import STATIONS, Settings, run_phase2_demo
from orbit_watch.timeutil import parse_utc

GENESIS = int(parse_utc("2026-11-12T12:00:00Z").timestamp())  # after the requests' window
BUDGET = 100_000_000  # 100 TestUSD (6 decimals), worthless
PASSWORD = "local test password"
PREFIX = "SIM-REQ-200"


class TravelClock:
    """A local chain's clock, moved to each deadline instead of waiting for it."""

    def __init__(self, chain):
        self.chain = chain

    def now(self) -> datetime:
        return datetime.fromtimestamp(self.chain.w3.eth.get_block("latest")["timestamp"], tz=UTC)

    def wait_until(self, when: datetime) -> None:
        if when > self.now():
            self.chain.travel_to(int(when.timestamp()))


def free_port():
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


@pytest.fixture
def setting(tmp_path):
    require_local_chain()
    import uvicorn
    from eth_account import Account

    from orbit_watch.chain.client import OrbitWatchChain
    from orbit_watch.chain.link import ChainLink
    from orbit_watch.service import VerificationContext, open_service

    parties = [REQUESTER, *STATIONS, *REVIEWERS, PLATFORM]
    deployment = Deployment(
        GENESIS, reviewers=REVIEWERS, platform=PLATFORM, verifier=VERIFIER, parties=parties
    )
    local = deployment.chain
    usd = deployment.usd
    local.send(
        deployment.deployer, usd.functions.mint(deployment.accounts[REQUESTER].address, BUDGET)
    )
    chain = OrbitWatchChain(local.w3, deployment.escrow.address)
    link = ChainLink(chain, deployment.accounts[VERIFIER], receipt_timeout=30)
    context = VerificationContext(catalog=catalog_bytes(), policy=policy_bytes())
    service = open_service(tmp_path / "service", REGISTRY, context, chain=link)
    with service.storage.db.transaction():
        admin = keys.create_key(service.storage.db, "admin:sim", "admin", link.now())
    port = free_port()
    runner = uvicorn.Server(
        uvicorn.Config(create_app(service), host="127.0.0.1", port=port, log_level="warning")
    )
    thread = threading.Thread(target=runner.run, daemon=True)
    thread.start()
    deadline = time.monotonic() + 10
    while not runner.started and time.monotonic() < deadline:
        time.sleep(0.05)
    assert runner.started, "the API server did not start"
    wallets = tmp_path / "wallets"
    wallets.mkdir()
    password = wallets / "password"
    password.write_text(PASSWORD + "\n")
    for party in [REQUESTER, *STATIONS, *REVIEWERS]:
        keystore = Account.encrypt(
            deployment.accounts[party].key, PASSWORD, kdf="pbkdf2", iterations=1000
        )
        (wallets / f"{party.replace(':', '-')}.json").write_text(json.dumps(keystore))
    settings = Settings(
        api=f"http://127.0.0.1:{port}",
        admin_key=admin,
        wallets=wallets,
        password_file=password,
        rpc=local.w3.provider.endpoint_uri,
        prefix=PREFIX,
    )
    yield {"settings": settings, "clock": TravelClock(chain), "chain": chain, "tmp": tmp_path}
    runner.should_exit = True
    thread.join(timeout=10)
    service.storage.close()
    local.stop()


def test_the_phase2_demo_on_a_local_chain(setting):
    out = setting["tmp"] / "out"
    summary = run_phase2_demo(setting["settings"], setting["clock"], out, setting["tmp"] / "work")
    requests = summary["requests"]
    outcomes = {rid: item["outcome"] for rid, item in requests.items()}
    assert outcomes == {
        f"{PREFIX}1": "accepted",
        f"{PREFIX}2": "rejected",
        f"{PREFIX}3": "rejected",
        f"{PREFIX}4": "disputed",
        f"{PREFIX}5": "expired",
    }
    assert all(item["on_chain"] == "Settled" for item in requests.values())
    # The rejected request went through a round of the escrow's reviewers.
    assert len(requests[f"{PREFIX}2"]["reviewers"]) == 3
    assert requests[f"{PREFIX}2"]["reason"].startswith("reviewers rejected")

    # Token transfers: what left the requester's wallet arrived in the others' wallets.
    before, after = summary["balances"]["before"], summary["balances"]["after"]
    change = {p: after[p]["balance"] - before[p]["balance"] for p in after}
    assert change["station:SIM-ESPOO"] == 1_000_000  # 1 TestUSD observer reward
    assert sum(change.values()) == 0
    assert all(item["withdrawable"] == 0 for item in after.values())
    chain = setting["chain"]
    assert chain.token_balance(chain.escrow.address) == 0  # nothing left in escrow

    # The results and votes are EAS attestations.
    kinds = [a["kind"] for a in summary["attestations"]]
    assert kinds.count("automated result") == 4 and kinds.count("vote") >= 3

    # Unauthorised parties and retries were refused.
    results = " ".join(check["result"] for check in summary["checks"])
    for code in ("nothing_to_withdraw", "not_requester", "not_assigned", "already_settled"):
        assert code in results
    assert "sent 0 transactions" in results

    transcript = (out / "transcript.md").read_text(encoding="utf-8")
    assert "SIMULATED" in transcript and "local Anvil test chain, no real value" in transcript
    assert transcript.count("| Withdrawn") >= 1 or "Withdrawn `" in transcript
    assert json.loads((out / "summary.json").read_text())["chain"]["chain_id"] == 31337

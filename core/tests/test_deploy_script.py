"""The deployment script on a local chain, run the way docs/base-sepolia.md runs it (step 2.7).

``forge script --broadcast`` with an encrypted keystore deploys the contracts to a local
Anvil chain that carries Base Sepolia's EAS and Safe code; the script's own ``check`` reads
the record back, and the request service starts on the new escrow with the verifier key.
Everything is LOCAL and SIMULATED: test accounts and a worthless token.
"""

import json
import os
import shutil
import subprocess
import time

import pytest
from anvil import REPO, LocalChain, require_local_chain, test_account
from helpers import catalog_bytes, packaged, policy_bytes

from orbit_watch.chain import ChainError
from orbit_watch.chain.networks import read_record

CONTRACTS = REPO / "contracts"
SETTINGS = "deployments/anvil.settings.json"  # relative to contracts/, git-ignored
RECORD = "deployments/anvil.json"
PASSWORD = "local test password"


def forge(*argv: str, env: dict[str, str] | None = None) -> str:
    result = subprocess.run(
        [shutil.which("forge") or "forge", *argv],
        cwd=CONTRACTS,
        env={**os.environ, **(env or {})},
        capture_output=True,
        text=True,
        timeout=600,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    return result.stdout


@pytest.fixture
def chain():
    require_local_chain()
    if shutil.which("forge") is None:
        pytest.fail("Foundry's forge is not on PATH")
    local = LocalChain(int(time.time()))
    local.install_safe()
    yield local
    local.stop()
    for name in (SETTINGS, RECORD):
        (CONTRACTS / name).unlink(missing_ok=True)


def test_the_deployment_script_on_a_local_chain(chain, tmp_path):
    from eth_account import Account

    from orbit_watch.chain.client import OrbitWatchChain
    from orbit_watch.chain.link import ChainLink
    from orbit_watch.reviewers import ReviewerRegistry
    from orbit_watch.service import VerificationContext, open_service

    deployer = test_account("deployer")
    chain.give_gas_money(deployer.address)
    usd = chain.deploy(deployer, "TestUSD.sol", "TestUSD")
    signers = [test_account(f"safe signer {i}").address for i in range(3)]
    reviewers = [test_account(f"reviewer {i}").address for i in range(4)]
    verifier = test_account("verifier")
    (CONTRACTS / SETTINGS).write_text(
        json.dumps(
            {
                "description": "LOCAL test deployment (tests/test_deploy_script.py)",
                "safe_signers": signers,
                "reviewers": reviewers,
                "verifier": verifier.address,
                "fee_recipient": "safe",
                "token": usd.address,
                "safe_salt_nonce": 7,
            }
        )
    )
    # The deployer signs with an encrypted keystore, as in the documented instructions.
    keystore = tmp_path / "deployer.json"
    keystore.write_text(json.dumps(Account.encrypt(deployer.key, PASSWORD)))
    password = tmp_path / "password"
    password.write_text(PASSWORD + "\n")
    rpc = chain.w3.provider.endpoint_uri
    output = forge(
        "script",
        "script/DeployOrbitWatch.s.sol",
        "--rpc-url",
        rpc,
        "--keystore",
        str(keystore),
        "--password-file",
        str(password),
        "--broadcast",
        env={"ORBIT_WATCH_DEPLOY_SETTINGS": SETTINGS, "ORBIT_WATCH_DEPLOY_RECORD": RECORD},
    )
    assert "ONCHAIN EXECUTION COMPLETE & SUCCESSFUL" in output

    record = read_record(CONTRACTS / RECORD)
    assert record["network"] == "anvil" and record["chain_id"] == 31337
    assert record["deployer"] == deployer.address
    assert record["safe_signers"] == signers and record["safe_threshold"] == 2
    assert sorted(record["reviewers"]) == sorted(reviewers)
    assert record["fee_recipient"] == record["safe"]
    assert record["verifier"] == verifier.address and record["token"] == usd.address
    assert record["escrow_version"] == "1.0.0"
    assert record["timelock_min_delay_seconds"] == 48 * 3600
    for name in ("safe", "timelock", "registry", "escrow"):
        assert chain.w3.eth.get_code(record[name]), name
    # The script's own check reads the record back against the chain.
    forge(
        "script",
        "script/DeployOrbitWatch.s.sol",
        "--sig",
        "check(string)",
        RECORD,
        "--rpc-url",
        rpc,
    )

    # The request service follows the new escrow with the verifier key, and only with it.
    context = VerificationContext(catalog=catalog_bytes(), policy=policy_bytes())
    registry = ReviewerRegistry.parse(packaged("reviewers.json"))
    escrow = OrbitWatchChain(chain.w3, record["escrow"])
    with pytest.raises(ChainError) as refused:
        open_service(
            tmp_path / "wrong",
            registry,
            context,
            chain=ChainLink(escrow, deployer, from_block=record["from_block"]),
        )
    assert refused.value.code == "not_the_verifier"
    link = ChainLink(escrow, verifier, from_block=record["from_block"])
    service = open_service(tmp_path / "service", registry, context, chain=link)
    try:
        info = link.info()
        assert info["registry"] == record["registry"]
        assert info["fee_recipient"] == record["safe"]
        assert info["token"]["symbol"] == "TESTUSD"
        assert info["result_schema"] == record["result_schema_uid"]
        assert info["notice"] == "local Anvil test chain, no real value"
    finally:
        service.storage.close()

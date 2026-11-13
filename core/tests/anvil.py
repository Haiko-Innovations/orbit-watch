"""A local Anvil chain for the evm-testnet tests (phase 2, step 2.5).

Each chain gets Base Sepolia's EAS and SchemaRegistry code at their predeploy addresses
(from contracts/test/fixtures/base-sepolia-eas, checked by hash) and fresh Orbit Watch
contracts from the Foundry build (contracts/out). The parties are SIMULATED, and their
accounts are LOCAL TEST ACCOUNTS derived from their names: anyone can recompute the keys,
so they are refused on any chain but a local one.

The tests need web3 (the ``evm`` extra), Foundry's ``anvil`` and ``forge build``. Without
them they are skipped, unless ORBIT_WATCH_EVM_TESTS=1 (as in CI), which makes a missing
piece a failure.
"""

from __future__ import annotations

import json
import os
import shutil
import socket
import subprocess
import time
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
CONTRACTS_OUT = REPO / "contracts" / "out"
EAS_FIXTURES = REPO / "contracts" / "test" / "fixtures" / "base-sepolia-eas"
SAFE_FIXTURES = REPO / "contracts" / "test" / "fixtures" / "base-sepolia-safe"
SCHEMA_REGISTRY_PREDEPLOY = "0x4200000000000000000000000000000000000020"
EAS_PREDEPLOY = "0x4200000000000000000000000000000000000021"
# The same hashes as contracts/test/helpers/BaseSepoliaEas.sol.
EAS_CODEHASH = "5b1a9eac43a2752a4f6b83617cd580cf17abc5b15812c3cea6c26c4dd68fa721"
SCHEMA_REGISTRY_CODEHASH = "87e5c437b0ed0763fb8dc0ab25f25cf5a302057a50de464387b587acec1f040a"
# Canonical Safe 1.4.1, the same hashes as contracts/test/helpers/BaseSepoliaSafe.sol.
SAFE_CODE = {
    "0x29fcB43b46531BcA003ddC8FCB67FFE91900C762": (
        "safe-l2.runtime.hex",
        "b1f926978a0f44a2c0ec8fe822418ae969bd8c3f18d61e5103100339894f81ff",
    ),
    "0x4e1DCf7AD4e460CfD30791CCC4F9c8a4f820ec67": (
        "safe-proxy-factory.runtime.hex",
        "50c3cdc4074750a7a974204a716c999edd37482f907608d960b2b025ee0b3317",
    ),
}
SAFE_L2_SINGLETON = "0x29fcB43b46531BcA003ddC8FCB67FFE91900C762"
SAFE_PROXY_FACTORY = "0x4e1DCf7AD4e460CfD30791CCC4F9c8a4f820ec67"
ZERO_ADDRESS = "0x" + "00" * 20
GAS_MONEY = 10**21  # local test ether for every account
# The local timelock waits a minute (Base Sepolia's waits 48 hours), so that tests can
# move the clock past it without passing the SIMULATED requests' deadlines.
LOCAL_TIMELOCK_DELAY = 60
SAFE_SIGNERS = ("safe:signer-1", "safe:signer-2", "safe:signer-3")
SAFE_THRESHOLD = 2


def unavailable() -> str | None:
    try:
        import web3  # noqa: F401
    except ImportError:
        return "the evm extra (web3) is not installed"
    if shutil.which("anvil") is None:
        return "Foundry's anvil is not on PATH"
    if not (CONTRACTS_OUT / "OrbitWatchEscrow.sol" / "OrbitWatchEscrow.json").exists():
        return "the contracts are not built (cd contracts && forge build)"
    return None


def require_local_chain() -> None:
    reason = unavailable()
    if reason is None:
        return
    if os.environ.get("ORBIT_WATCH_EVM_TESTS") == "1":
        pytest.fail(f"ORBIT_WATCH_EVM_TESTS=1 but {reason}")
    pytest.skip(f"{reason}; set ORBIT_WATCH_EVM_TESTS=1 to require these tests")


def test_account(name: str):
    """A LOCAL TEST ACCOUNT whose key is derived from ``name`` (public, never for a testnet)."""
    from eth_account import Account
    from eth_utils import keccak

    return Account.from_key(keccak(text=f"orbit-watch local test account|{name}"))


test_account.__test__ = False  # not a pytest test


def artifact(source: str, contract: str) -> dict:
    return json.loads((CONTRACTS_OUT / source / f"{contract}.json").read_text(encoding="utf-8"))


class LocalChain:
    """An Anvil process starting at ``genesis`` (Unix seconds)."""

    def __init__(self, genesis: int, port: int = 0):
        from web3 import Web3

        if not port:  # any free port
            with socket.socket() as probe:
                probe.bind(("127.0.0.1", 0))
                port = probe.getsockname()[1]
        self.process = subprocess.Popen(
            [shutil.which("anvil") or "anvil", "--port", str(port), "--timestamp", str(genesis)],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        self.w3 = Web3(Web3.HTTPProvider(f"http://127.0.0.1:{port}"))
        for _ in range(200):
            try:
                if self.w3.eth.chain_id == 31337:
                    break
            except Exception:  # not listening yet
                time.sleep(0.05)
        else:  # pragma: no cover
            self.stop()
            raise RuntimeError("anvil did not start")
        self._install_eas()

    def stop(self) -> None:
        self.process.terminate()
        self.process.wait(timeout=10)

    def rpc(self, method: str, params: list) -> object:
        response = self.w3.provider.make_request(method, params)
        if "error" in response:
            raise RuntimeError(f"{method}: {response['error']}")
        return response.get("result")

    def give_gas_money(self, address: str) -> None:
        self.rpc("anvil_setBalance", [address, hex(GAS_MONEY)])

    def _install_eas(self) -> None:
        from eth_utils import keccak

        for address, file, codehash in (
            (SCHEMA_REGISTRY_PREDEPLOY, "schema-registry.runtime.hex", SCHEMA_REGISTRY_CODEHASH),
            (EAS_PREDEPLOY, "eas.runtime.hex", EAS_CODEHASH),
        ):
            code = (EAS_FIXTURES / file).read_text(encoding="utf-8").strip()
            if keccak(hexstr=code).hex() != codehash:
                raise RuntimeError(f"{file} is not the Base Sepolia code")
            self.rpc("anvil_setCode", [address, code])

    def install_safe(self) -> None:
        """The canonical Safe 1.4.1 code, as on Base Sepolia (for the deployment script)."""
        from eth_utils import keccak

        for address, (file, codehash) in SAFE_CODE.items():
            code = (SAFE_FIXTURES / file).read_text(encoding="utf-8").strip()
            if keccak(hexstr=code).hex() != codehash:
                raise RuntimeError(f"{file} is not the Base Sepolia code")
            self.rpc("anvil_setCode", [address, code])

    def deploy(self, account, source: str, contract: str, *args):
        built = artifact(source, contract)
        factory = self.w3.eth.contract(abi=built["abi"], bytecode=built["bytecode"]["object"])
        receipt = self.send(account, factory.constructor(*args))
        return self.w3.eth.contract(address=receipt["contractAddress"], abi=built["abi"])

    def send(self, account, call):
        transaction = call.build_transaction(
            {
                "from": account.address,
                "nonce": self.w3.eth.get_transaction_count(account.address, "pending"),
                "chainId": 31337,
            }
        )
        signed = account.sign_transaction(transaction)
        tx_hash = self.w3.eth.send_raw_transaction(signed.raw_transaction)
        receipt = self.w3.eth.wait_for_transaction_receipt(tx_hash, timeout=60)
        assert receipt["status"] == 1, f"{contract_name(call)} failed"
        return receipt


def contract_name(call) -> str:
    return getattr(call, "fn_name", type(call).__name__)


class Deployment:
    """A fresh chain with TestUSD, a reviewer registry and the escrow.

    With ``governance``, as on Base Sepolia (step 2.7): a 2-of-3 Safe of LOCAL TEST signers
    and a TimelockController whose only proposer is the Safe, which owns the registry; its
    delay is ``LOCAL_TIMELOCK_DELAY``. Otherwise the deployer's account owns the registry.
    """

    def __init__(
        self,
        genesis: int,
        *,
        reviewers: list[str],
        platform: str,
        verifier: str,
        parties: list[str],
        port: int = 0,
        governance: bool = False,
    ):
        self.chain = LocalChain(genesis, port)
        self.accounts = {party: test_account(party) for party in [*parties, verifier]}
        self.deployer = test_account("deployer")
        for account in [self.deployer, *self.accounts.values()]:
            self.chain.give_gas_money(account.address)
        self.usd = self.chain.deploy(self.deployer, "TestUSD.sol", "TestUSD")
        self.safe = self.timelock = None
        self.safe_signers = [test_account(name) for name in SAFE_SIGNERS]
        owner = self.deployer.address
        if governance:
            self.safe = self._deploy_safe()
            self.timelock = self.chain.deploy(
                self.deployer,
                "TimelockController.sol",
                "TimelockController",
                LOCAL_TIMELOCK_DELAY,
                [self.safe.address],
                [ZERO_ADDRESS],  # anyone may execute
                ZERO_ADDRESS,  # no admin
            )
            owner = self.timelock.address
        self.registry = self.chain.deploy(
            self.deployer,
            "OrbitWatchReviewerRegistry.sol",
            "OrbitWatchReviewerRegistry",
            owner,
            [self.accounts[r].address for r in reviewers],
        )
        self.escrow = self.chain.deploy(
            self.deployer,
            "OrbitWatchEscrow.sol",
            "OrbitWatchEscrow",
            self.usd.address,
            self.accounts[platform].address,
            EAS_PREDEPLOY,
            self.registry.address,
            self.accounts[verifier].address,
        )

    def _deploy_safe(self):
        """A Safe 1.4.1 proxy with the LOCAL TEST signers, made like the deployment script's."""
        self.chain.install_safe()
        for signer in self.safe_signers:
            self.chain.give_gas_money(signer.address)
        w3 = self.chain.w3
        abi = artifact("ISafe.sol", "ISafe")["abi"]
        setup = w3.eth.contract(abi=abi).encode_abi(
            "setup",
            args=[
                [s.address for s in self.safe_signers],
                SAFE_THRESHOLD,
                ZERO_ADDRESS,
                b"",
                ZERO_ADDRESS,
                ZERO_ADDRESS,
                0,
                ZERO_ADDRESS,
            ],
        )
        factory = w3.eth.contract(
            address=SAFE_PROXY_FACTORY, abi=artifact("ISafe.sol", "ISafeProxyFactory")["abi"]
        )
        create = factory.functions.createProxyWithNonce(SAFE_L2_SINGLETON, setup, 0)
        address = create.call({"from": self.deployer.address})
        self.chain.send(self.deployer, create)
        return w3.eth.contract(address=address, abi=abi)

    def safe_execute(self, to: str, data: str, signers: int = SAFE_THRESHOLD):
        """Have the Safe call ``to`` with ``data``, signed by its first ``signers`` LOCAL
        TEST signers (what the Safe's owners do in the Safe app)."""
        from eth_account import Account

        safe = self.safe.functions
        safe_tx_hash = safe.getTransactionHash(
            to, 0, data, 0, 0, 0, 0, ZERO_ADDRESS, ZERO_ADDRESS, safe.nonce().call()
        ).call()
        owners = sorted(self.safe_signers[:signers], key=lambda a: int(a.address, 16))
        signatures = b""
        for owner in owners:
            signed = Account.unsafe_sign_hash(safe_tx_hash, owner.key)
            signatures += signed.r.to_bytes(32, "big") + signed.s.to_bytes(32, "big")
            signatures += bytes([signed.v])
        return self.chain.send(
            owners[0],
            safe.execTransaction(to, 0, data, 0, 0, 0, 0, ZERO_ADDRESS, ZERO_ADDRESS, signatures),
        )

    def give_budget(self, party: str, amount: int) -> None:
        """Mint worthless TestUSD to ``party`` and let the escrow take it when funding."""
        account = self.accounts[party]
        self.chain.send(self.deployer, self.usd.functions.mint(account.address, amount))
        self.chain.send(account, self.usd.functions.approve(self.escrow.address, 2**256 - 1))

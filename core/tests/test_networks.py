"""Known testnet deployments (phase 2, step 2.7): the packaged record and its use.

No chain needed. Before the Base Sepolia deployment exists, the tests check that the
command line says so; afterwards, that the packaged record is the deployment script's own
and matches the committed settings.
"""

import argparse
import json
from pathlib import Path

import pytest

from orbit_watch import cli, cli_client
from orbit_watch.chain import ChainError, networks

REPO = Path(__file__).resolve().parents[2]
DEPLOYMENTS = REPO / "contracts" / "deployments"
SCRIPT_RECORD = DEPLOYMENTS / "base-sepolia.json"
SETTINGS = DEPLOYMENTS / "base-sepolia.settings.json"
PACKAGED = Path(networks.__file__).parent / "deployments" / "base-sepolia.json"
EAS_PREDEPLOY = "0x4200000000000000000000000000000000000021"
FAKE = {
    "network": "base-sepolia",
    "chain_id": 84532,
    "from_block": 123,
    "escrow": "0x00000000000000000000000000000000000000E5",
}


def test_the_packaged_record_is_the_scripts_record():
    assert PACKAGED.exists() == SCRIPT_RECORD.exists()
    if PACKAGED.exists():
        assert PACKAGED.read_bytes() == SCRIPT_RECORD.read_bytes()


def test_the_base_sepolia_deployment_follows_its_settings():
    if not PACKAGED.exists():
        with pytest.raises(ChainError) as refused:
            networks.deployment("base-sepolia")
        assert refused.value.code == "not_deployed"
        return
    record = networks.deployment("base-sepolia")
    settings = json.loads(SETTINGS.read_text(encoding="utf-8"))
    assert record["network"] == "base-sepolia" and record["chain_id"] == 84532
    assert record["safe_signers"] == settings["safe_signers"]
    assert record["safe_threshold"] == 2
    assert sorted(record["reviewers"]) == sorted(settings["reviewers"])
    assert record["verifier"] == settings["verifier"]
    assert record["token"] == settings["token"]
    assert settings["fee_recipient"] == "safe" and record["fee_recipient"] == record["safe"]
    assert record["eas"] == EAS_PREDEPLOY
    assert record["escrow_version"] == "1.0.0"
    assert record["timelock_min_delay_seconds"] == 48 * 3600
    assert record["deployer"] not in (*record["safe_signers"], record["verifier"])


def test_the_settings_name_their_simulated_reviewers():
    settings = json.loads(SETTINGS.read_text(encoding="utf-8"))
    assert "TESTNET" in settings["description"] and "SIMULATED" in settings["description"]
    names = settings["reviewer_names"]
    assert len(names) == len(settings["reviewers"]) >= 3
    assert all(name.startswith("reviewer:sim-") for name in names)


def test_unknown_networks_and_incomplete_records(tmp_path):
    with pytest.raises(ChainError) as refused:
        networks.deployment("base-mainnet")
    assert refused.value.code == "unknown_network"
    record = tmp_path / "record.json"
    record.write_text(json.dumps({"chain_id": 84532}))
    with pytest.raises(ChainError) as refused:
        networks.read_record(record)
    assert refused.value.code == "invalid_deployment"
    assert networks.public_rpc(84532) == "https://sepolia.base.org"
    assert networks.public_rpc(31337) is None


def test_serve_takes_its_settings_from_the_network(monkeypatch):
    monkeypatch.setattr(networks, "deployment", lambda name: FAKE)
    parser = cli.build_parser()
    base = ["serve", "--dir", "x", "--network", "base-sepolia", "--verifier-keystore", "k"]

    args = parser.parse_args(base)
    cli._apply_network(args)
    assert args.escrow == FAKE["escrow"]
    assert args.from_block is None  # a new directory starts at the current block
    assert args.chain_rpc == "https://sepolia.base.org"

    args = parser.parse_args([*base, "--chain-rpc", "http://my-node", "--from-block", "200"])
    cli._apply_network(args)
    assert args.chain_rpc == "http://my-node" and args.from_block == 200

    args = parser.parse_args([*base, "--escrow", "0x00000000000000000000000000000000000000AA"])
    with pytest.raises(ChainError) as refused:
        cli._apply_network(args)
    assert refused.value.code == "other_escrow"

    with pytest.raises(SystemExit):
        parser.parse_args(["serve", "--dir", "x", "--network", "base-mainnet"])


def test_serve_on_a_network_needs_the_verifier_key(capsys):
    code = cli.main(["serve", "--dir", "x", "--network", "base-sepolia"])
    assert code == cli.EXIT_USAGE
    assert "give --verifier-keystore" in capsys.readouterr().err


def test_the_command_line_falls_back_to_the_public_endpoint(monkeypatch):
    pytest.importorskip("web3")
    import orbit_watch.chain.wallet as wallet

    opened = {}
    monkeypatch.delenv("ORBIT_WATCH_RPC", raising=False)
    monkeypatch.setattr(cli_client, "_chain_info", lambda args: {"chain_id": 84532})
    monkeypatch.setattr(
        wallet, "open_wallet", lambda rpc, keystore, password: opened.update(rpc=rpc)
    )
    args = argparse.Namespace(keystore="k", rpc=None, password_file=None)
    cli_client._wallet(args)
    assert opened["rpc"] == "https://sepolia.base.org"
    args = argparse.Namespace(keystore="k", rpc="http://mine", password_file=None)
    cli_client._wallet(args)
    assert opened["rpc"] == "http://mine"

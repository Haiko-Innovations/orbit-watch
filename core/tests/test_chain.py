"""Helpers of orbit_watch.chain (phase 2, step 2.5) that need no chain."""

from datetime import datetime, timedelta

import pytest

pytest.importorskip("web3", reason="needs the evm extra")

from orbit_watch import chain
from orbit_watch.chain import ChainError
from orbit_watch.timeutil import parse_utc


def test_only_base_sepolia_and_a_local_chain_are_supported():
    chain.require_supported(84532)
    chain.require_supported(31337)
    for refused in (1, 8453, 10, 11155420):
        with pytest.raises(ChainError) as error:
            chain.require_supported(refused)
        assert error.value.code == "unsupported_chain"


def test_request_keys_match_the_contract():
    # The same value as contracts/test: keccak256("SIM-REQ-0001").
    from eth_utils import keccak

    assert chain.request_key("SIM-REQ-0001") == keccak(b"SIM-REQ-0001")
    assert len(chain.request_key("x")) == 32


def test_digests_and_times_convert_exactly():
    digest = "d" * 64
    assert chain.bytes32_from_sha256(digest) == bytes.fromhex(digest)
    for bad in ("D" * 64, "d" * 63, "0x" + "d" * 64):
        with pytest.raises(ValueError):
            chain.bytes32_from_sha256(bad)
    assert chain.whole_seconds(24) == 86400 and chain.whole_seconds(0.5) == 1800
    with pytest.raises(ValueError):
        chain.whole_seconds(1 / 7)
    with pytest.raises(ValueError):
        chain.whole_seconds(0)
    when = parse_utc("2026-11-01T12:00:00Z")
    assert chain.unix_seconds(when) == 1793534400
    with pytest.raises(ValueError):
        chain.unix_seconds(when + timedelta(microseconds=1))
    assert isinstance(when, datetime)


def test_names_and_links():
    assert chain.snake_case("NotTheVerifier") == "not_the_verifier"
    assert chain.snake_case("WrongStatus") == "wrong_status"
    assert chain.explorer_link(31337, "0xabc") is None
    assert chain.explorer_link(84532, "0xabc") == "https://sepolia.basescan.org/tx/0xabc"
    assert chain.sha256_of_text("") == bytes.fromhex(
        "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"
    )


def test_an_adapter_on_a_testnet_cannot_move_the_clock():
    from orbit_watch.settlement import SettlementError
    from orbit_watch.settlement.evm import EvmTestnetAdapter

    class Testnet:
        chain_id = 84532

    with pytest.raises(SettlementError) as error:
        EvmTestnetAdapter(Testnet(), {}, platform="platform:x", follow_record_time=True)
    assert error.value.code == "not_local"

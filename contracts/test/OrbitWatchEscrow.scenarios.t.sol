// SPDX-License-Identifier: Apache-2.0
pragma solidity 0.8.38;

import {Test} from "forge-std/Test.sol";
import {stdJson} from "forge-std/StdJson.sol";
import {OrbitWatchEscrow} from "../src/OrbitWatchEscrow.sol";
import {EscrowHarness} from "./helpers/EscrowHarness.sol";
import {TestUSD} from "./mocks/TestUSD.sol";

/// @notice The phase 1 settlement scenario suite, replayed on chain.
/// @dev test/fixtures/settlement-scenarios.json is exported from the Python core
/// (`python -m orbit_watch.settlement.scenarios`), and a Python test checks that it is
/// current. Every funded scenario must end with the same outcome and the same net change for
/// every party as on the phase 1 points ledger. Unfunded scenarios never touch the chain.
contract OrbitWatchEscrowScenariosTest is Test {
    using stdJson for string;

    bytes32 internal constant DELIVERY = keccak256("observations");

    string internal json;

    function setUp() public {
        json = vm.readFile(
            string.concat(vm.projectRoot(), "/test/fixtures/settlement-scenarios.json")
        );
    }

    function test_ThePhase1ScenarioSuite() public {
        assertTrue(json.readBool(".simulated"));
        assertEq(json.readString(".rules_version"), "1.0");
        uint256 ran;
        uint256 i;
        for (; json.keyExists(_at(".scenarios", i)); ++i) {
            if (json.readBool(string.concat(_at(".scenarios", i), ".funded"))) {
                _run(_at(".scenarios", i));
                ++ran;
            }
        }
        assertEq(ran, 9, "funded scenarios");
        assertEq(i, 10, "scenarios");
    }

    // ------------------------------------------------------------------ one scenario

    function _run(string memory s) internal {
        string memory name = json.readString(string.concat(s, ".name"));
        uint256 t0 = json.readUint(".t0");
        vm.warp(t0);

        TestUSD usd = new TestUSD();
        EscrowHarness escrow = new EscrowHarness(usd, _party(json.readString(".platform")));
        bytes32 id = keccak256(bytes(string.concat("SIM-", name)));
        address requester = _party(json.readString(string.concat(s, ".requester")));
        usd.mint(requester, json.readUint(".budget"));

        string[] memory parties = json.readStringArray(".parties");
        int256[] memory before = new int256[](parties.length);
        for (uint256 p; p < parties.length; ++p) {
            before[p] = int256(usd.balanceOf(_party(parties[p])));
        }

        for (uint256 j; json.keyExists(_at(string.concat(s, ".steps"), j)); ++j) {
            _step(escrow, usd, id, s, _at(string.concat(s, ".steps"), j), t0);
        }

        // The outcome, before settlement (a cancellation settles at once).
        OrbitWatchEscrow.Status status = escrow.statusOf(id);
        if (status == OrbitWatchEscrow.Status.Settled) {
            status = escrow.getRequest(id).outcome;
        } else {
            escrow.settle(id);
        }
        assertEq(
            uint8(status),
            uint8(_outcome(json.readString(string.concat(s, ".outcome")))),
            string.concat(name, ": outcome")
        );
        vm.expectRevert(
            abi.encodeWithSelector(
                OrbitWatchEscrow.WrongStatus.selector, id, OrbitWatchEscrow.Status.Settled
            )
        );
        escrow.settle(id);

        for (uint256 p; p < parties.length; ++p) {
            address party = _party(parties[p]);
            if (escrow.owed(party) > 0) {
                vm.prank(party);
                escrow.withdraw();
            }
        }
        assertEq(usd.balanceOf(address(escrow)), 0, string.concat(name, ": left in escrow"));
        assertEq(escrow.totalHeld() + escrow.totalOwed(), 0, string.concat(name, ": owed"));

        for (uint256 p; p < parties.length; ++p) {
            int256 change = int256(usd.balanceOf(_party(parties[p]))) - before[p];
            assertEq(change, _expectedChange(s, parties[p]), string.concat(name, ": ", parties[p]));
        }
    }

    function _step(
        EscrowHarness escrow,
        TestUSD usd,
        bytes32 id,
        string memory s,
        string memory step,
        uint256 t0
    ) internal {
        vm.warp(t0 + json.readUint(string.concat(step, ".at")));
        bytes32 action = keccak256(bytes(json.readString(string.concat(step, ".action"))));
        if (action == keccak256("open") || action == keccak256("wait")) {
            return; // terms are frozen at funding on chain; time has moved above
        }
        address party = action == keccak256("verify")
            ? address(0)
            : _party(json.readString(string.concat(step, ".party")));
        if (action == keccak256("fund")) {
            OrbitWatchEscrow.Terms memory terms = _terms(s, t0);
            OrbitWatchEscrow.Split memory split = OrbitWatchEscrow.Split({
                observerReward: uint128(json.readUint(".split.observer")),
                reviewerReward: uint128(json.readUint(".split.reviewer")),
                platformFee: uint128(json.readUint(".split.platform_fee"))
            });
            vm.startPrank(party);
            usd.approve(address(escrow), type(uint256).max);
            escrow.fund(id, terms, split);
            vm.stopPrank();
        } else if (action == keccak256("reserve")) {
            vm.prank(party);
            escrow.reserve(id);
        } else if (action == keccak256("deliver")) {
            vm.prank(party);
            escrow.deliver(id, DELIVERY);
        } else if (action == keccak256("cancel")) {
            vm.prank(party);
            escrow.cancel(id);
        } else if (action == keccak256("verify")) {
            escrow.recordVerification(
                id,
                _verdict(json.readString(string.concat(step, ".verdict"))),
                _reviewers(string.concat(step, ".reviewers"))
            );
        } else if (action == keccak256("challenge")) {
            escrow.challenge(id, party, _reviewers(string.concat(step, ".reviewers")));
        } else if (action == keccak256("vote")) {
            escrow.vote(id, party, json.readBool(string.concat(step, ".approve")));
        } else {
            revert(string.concat("unknown action in ", step));
        }
    }

    // ------------------------------------------------------------------ fixture helpers

    function _terms(string memory s, uint256 t0)
        internal
        view
        returns (OrbitWatchEscrow.Terms memory)
    {
        string memory t = string.concat(s, ".terms");
        return OrbitWatchEscrow.Terms({
            termsHash: keccak256(bytes(json.readString(string.concat(s, ".name")))),
            deliveryDeadline: uint64(t0 + json.readUint(string.concat(t, ".delivery_deadline"))),
            reservationSeconds: uint32(json.readUint(string.concat(t, ".reservation_seconds"))),
            verificationTimeoutSeconds: uint32(
                json.readUint(string.concat(t, ".verification_timeout_seconds"))
            ),
            challengeSeconds: uint32(json.readUint(string.concat(t, ".challenge_seconds"))),
            reviewSeconds: uint32(json.readUint(string.concat(t, ".review_seconds")))
        });
    }

    function _reviewers(string memory key) internal returns (address[3] memory reviewers) {
        string[] memory names = json.readStringArray(key);
        if (names.length == 0) return reviewers;
        assertEq(names.length, 3, key);
        for (uint256 i; i < 3; ++i) {
            reviewers[i] = _party(names[i]);
        }
    }

    function _expectedChange(string memory s, string memory party) internal view returns (int256) {
        string memory net = string.concat(s, ".net");
        for (uint256 i; json.keyExists(_at(net, i)); ++i) {
            if (
                keccak256(bytes(json.readString(string.concat(_at(net, i), ".party"))))
                    == keccak256(bytes(party))
            ) {
                return json.readInt(string.concat(_at(net, i), ".change"));
            }
        }
        return 0;
    }

    function _party(string memory name) internal returns (address) {
        return makeAddr(name);
    }

    function _at(string memory array, uint256 index) internal pure returns (string memory) {
        return string.concat(array, "[", vm.toString(index), "]");
    }

    function _verdict(string memory verdict) internal pure returns (OrbitWatchEscrow.Verdict) {
        bytes32 v = keccak256(bytes(verdict));
        if (v == keccak256("pass")) return OrbitWatchEscrow.Verdict.Pass;
        if (v == keccak256("fail")) return OrbitWatchEscrow.Verdict.Fail;
        if (v == keccak256("inconclusive")) return OrbitWatchEscrow.Verdict.Inconclusive;
        revert(string.concat("unknown verdict ", verdict));
    }

    function _outcome(string memory outcome) internal pure returns (OrbitWatchEscrow.Status) {
        bytes32 o = keccak256(bytes(outcome));
        if (o == keccak256("accepted")) return OrbitWatchEscrow.Status.Accepted;
        if (o == keccak256("rejected")) return OrbitWatchEscrow.Status.Rejected;
        if (o == keccak256("disputed")) return OrbitWatchEscrow.Status.Disputed;
        if (o == keccak256("expired")) return OrbitWatchEscrow.Status.Expired;
        if (o == keccak256("cancelled")) return OrbitWatchEscrow.Status.Cancelled;
        revert(string.concat("unknown outcome ", outcome));
    }
}

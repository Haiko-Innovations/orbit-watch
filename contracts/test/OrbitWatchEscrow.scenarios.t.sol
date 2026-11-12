// SPDX-License-Identifier: Apache-2.0
pragma solidity 0.8.38;

import {stdJson} from "forge-std/StdJson.sol";
import {IEAS, AttestationRequest, AttestationRequestData} from "eas-contracts/IEAS.sol";
import {OrbitWatchEscrow} from "../src/OrbitWatchEscrow.sol";
import {OrbitWatchReviewerRegistry} from "../src/OrbitWatchReviewerRegistry.sol";
import {BaseSepoliaEas} from "./helpers/BaseSepoliaEas.sol";
import {TestUSD} from "./mocks/TestUSD.sol";

/// @notice The phase 1 settlement scenario suite, replayed on chain.
/// @dev test/fixtures/settlement-scenarios.json is exported from the Python core
/// (`python -m orbit_watch.settlement.scenarios`), and a Python test checks that it is
/// current. Every funded scenario must end with the same outcome and the same net change for
/// every party as on the phase 1 points ledger. Unfunded scenarios never touch the chain.
/// Automated results and votes are attestations made through Base Sepolia's EAS code, and the
/// reviewers chosen on chain must be the scenario's reviewers.
contract OrbitWatchEscrowScenariosTest is BaseSepoliaEas {
    using stdJson for string;

    bytes32 internal constant DELIVERY = keccak256("observations");
    bytes32 internal constant REPORT = keccak256("report");
    bytes32 internal constant REASON = keccak256("reason");

    string internal json;
    IEAS internal eas;
    TestUSD internal usd;
    OrbitWatchEscrow internal escrow;
    address internal verifier = makeAddr("verifier");

    function setUp() public {
        eas = _installEas();
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
        uint256 t0 = json.readUint(".t0");
        vm.warp(t0);
        string[] memory parties = json.readStringArray(".parties");
        _deploy(parties);
        string memory requestId = string.concat("SIM-", json.readString(string.concat(s, ".name")));
        usd.mint(_party(json.readString(string.concat(s, ".requester"))), json.readUint(".budget"));

        int256[] memory before = new int256[](parties.length);
        for (uint256 p; p < parties.length; ++p) {
            before[p] = int256(usd.balanceOf(_party(parties[p])));
        }
        for (uint256 j; json.keyExists(_at(string.concat(s, ".steps"), j)); ++j) {
            _step(requestId, s, _at(string.concat(s, ".steps"), j), t0);
        }
        _settleAndCheck(s, keccak256(bytes(requestId)), parties, before);
    }

    /// @dev A fresh token, registry (with the scenario's reviewers) and escrow.
    function _deploy(string[] memory parties) internal {
        usd = new TestUSD();
        OrbitWatchReviewerRegistry registry =
            new OrbitWatchReviewerRegistry(address(this), new address[](0));
        for (uint256 p; p < parties.length; ++p) {
            if (vm.indexOf(parties[p], "reviewer:") == 0) registry.addReviewer(_party(parties[p]));
        }
        escrow = new OrbitWatchEscrow(
            usd, _party(json.readString(".platform")), eas, registry, verifier
        );
    }

    function _settleAndCheck(
        string memory s,
        bytes32 id,
        string[] memory parties,
        int256[] memory before
    ) internal {
        string memory name = json.readString(string.concat(s, ".name"));
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

    function _step(string memory requestId, string memory s, string memory step, uint256 t0)
        internal
    {
        bytes32 id = keccak256(bytes(requestId));
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
            string memory verdict = json.readString(string.concat(step, ".verdict"));
            bytes memory data = abi.encode(requestId, DELIVERY, REPORT, verdict, "method", "1");
            AttestationRequest memory result =
                _request(escrow.resultSchemaUid(), id, bytes32(0), data);
            vm.prank(verifier); // after building the request: a view call would use up the prank
            eas.attest(result);
            _checkRound(id, string.concat(step, ".reviewers"));
        } else if (action == keccak256("challenge")) {
            vm.prank(party);
            escrow.challenge(id, REASON);
            _checkRound(id, string.concat(step, ".reviewers"));
        } else if (action == keccak256("vote")) {
            bytes memory data = abi.encode(
                requestId, DELIVERY, json.readBool(string.concat(step, ".approve")), REASON
            );
            bytes32 result = escrow.getRequest(id).resultAttestation;
            AttestationRequest memory request = _request(escrow.voteSchemaUid(), id, result, data);
            vm.prank(party);
            eas.attest(request);
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

    /// @dev The reviewers chosen on chain are the scenario's reviewers (in any order).
    function _checkRound(bytes32 id, string memory key) internal {
        string[] memory names = json.readStringArray(key);
        if (names.length == 0) return;
        assertEq(names.length, 3, key);
        address[3] memory round = escrow.getRequest(id).reviewers;
        for (uint256 i; i < 3; ++i) {
            address expected = _party(names[i]);
            assertTrue(
                round[0] == expected || round[1] == expected || round[2] == expected,
                string.concat(names[i], " is not in the round")
            );
        }
    }

    function _request(bytes32 schema, bytes32 id, bytes32 refUid, bytes memory data)
        internal
        view
        returns (AttestationRequest memory)
    {
        return AttestationRequest({
            schema: schema,
            data: AttestationRequestData({
                recipient: escrow.getRequest(id).station,
                expirationTime: 0,
                revocable: false,
                refUID: refUid,
                data: data,
                value: 0
            })
        });
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

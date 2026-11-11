// SPDX-License-Identifier: Apache-2.0
pragma solidity 0.8.38;

import {Test} from "forge-std/Test.sol";
import {OrbitWatchEscrow} from "../../src/OrbitWatchEscrow.sol";
import {EscrowHarness} from "./EscrowHarness.sol";
import {TestUSD} from "../mocks/TestUSD.sol";

/// @notice Shared set-up for the escrow tests: a worthless local token, the escrow behind the
/// test-only harness, and named parties.
abstract contract EscrowTestBase is Test {
    // The example of docs/settlement.md: deposit 100 + 3 × 10 + 5 = 135.
    uint128 internal constant OBSERVER_REWARD = 100e6;
    uint128 internal constant REVIEWER_REWARD = 10e6;
    uint128 internal constant PLATFORM_FEE = 5e6;
    uint256 internal constant DEPOSIT = 135e6;
    uint256 internal constant BUDGET = 1000e6;

    uint32 internal constant RESERVATION = 6 hours;
    uint32 internal constant VERIFICATION_TIMEOUT = 24 hours;
    uint32 internal constant CHALLENGE = 24 hours;
    uint32 internal constant REVIEW = 48 hours;
    uint64 internal constant DELIVERY_WINDOW = 3 days;

    // keccak256 is an opcode; sha256 would be a precompile call and use up vm.prank.
    bytes32 internal constant TERMS = keccak256("terms");
    bytes32 internal constant DELIVERY = keccak256("observations");
    bytes32 internal constant ID = keccak256("SIM-REQ-0001");

    TestUSD internal usd;
    EscrowHarness internal escrow;

    address internal requester = makeAddr("requester");
    address internal station = makeAddr("station");
    address internal otherStation = makeAddr("other station");
    address internal r1 = makeAddr("reviewer 1");
    address internal r2 = makeAddr("reviewer 2");
    address internal r3 = makeAddr("reviewer 3");
    address internal platform = makeAddr("platform");
    address internal stranger = makeAddr("stranger");

    function setUp() public virtual {
        usd = new TestUSD();
        escrow = new EscrowHarness(usd, platform);
        usd.mint(requester, BUDGET);
        vm.prank(requester);
        usd.approve(address(escrow), type(uint256).max);
    }

    function _reviewers() internal view returns (address[3] memory) {
        return [r1, r2, r3];
    }

    function _noReviewers() internal pure returns (address[3] memory none) {}

    function _terms() internal view returns (OrbitWatchEscrow.Terms memory) {
        return OrbitWatchEscrow.Terms({
            termsHash: TERMS,
            deliveryDeadline: uint64(vm.getBlockTimestamp()) + DELIVERY_WINDOW,
            reservationSeconds: RESERVATION,
            verificationTimeoutSeconds: VERIFICATION_TIMEOUT,
            challengeSeconds: CHALLENGE,
            reviewSeconds: REVIEW
        });
    }

    function _split() internal pure returns (OrbitWatchEscrow.Split memory) {
        return OrbitWatchEscrow.Split({
            observerReward: OBSERVER_REWARD,
            reviewerReward: REVIEWER_REWARD,
            platformFee: PLATFORM_FEE
        });
    }

    function _fund() internal {
        OrbitWatchEscrow.Terms memory terms = _terms();
        OrbitWatchEscrow.Split memory split = _split();
        vm.prank(requester);
        escrow.fund(ID, terms, split);
    }

    function _reserveAndDeliver() internal {
        vm.prank(station);
        escrow.reserve(ID);
        skip(1 hours);
        vm.prank(station);
        escrow.deliver(ID, DELIVERY);
        skip(10 minutes);
    }

    /// @dev Funded, reserved, delivered and verified with `verdict` (challenge period open).
    function _toChallengePeriod(OrbitWatchEscrow.Verdict verdict) internal {
        _fund();
        _reserveAndDeliver();
        escrow.recordVerification(ID, verdict, _noReviewers());
    }

    function _status() internal view returns (OrbitWatchEscrow.Status) {
        return escrow.statusOf(ID);
    }

    /// @dev Withdraw for every party that has something owed, so balances can be compared.
    function _withdrawAll() internal {
        address[8] memory parties =
            [requester, station, otherStation, r1, r2, r3, platform, stranger];
        for (uint256 i; i < parties.length; ++i) {
            if (escrow.owed(parties[i]) > 0) {
                vm.prank(parties[i]);
                escrow.withdraw();
            }
        }
    }
}

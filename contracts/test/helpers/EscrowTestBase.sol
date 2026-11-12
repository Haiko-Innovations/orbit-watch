// SPDX-License-Identifier: Apache-2.0
pragma solidity 0.8.38;

import {IEAS, AttestationRequest, AttestationRequestData} from "eas-contracts/IEAS.sol";
import {OrbitWatchEscrow} from "../../src/OrbitWatchEscrow.sol";
import {OrbitWatchReviewerRegistry} from "../../src/OrbitWatchReviewerRegistry.sol";
import {TestUSD} from "../mocks/TestUSD.sol";
import {BaseSepoliaEas} from "./BaseSepoliaEas.sol";

/// @notice Shared set-up for the escrow tests: Base Sepolia's EAS code, a worthless local
/// token, a reviewer registry with three reviewers, the escrow and named parties.
abstract contract EscrowTestBase is BaseSepoliaEas {
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

    string internal constant REQUEST_ID = "SIM-REQ-0001";
    bytes32 internal constant ID = keccak256("SIM-REQ-0001");
    // keccak256 is an opcode; sha256 would be a precompile call and use up vm.prank.
    bytes32 internal constant TERMS = keccak256("terms");
    bytes32 internal constant DELIVERY = keccak256("observations");
    bytes32 internal constant REPORT = keccak256("report");
    bytes32 internal constant REASON = keccak256("reason");
    string internal constant METHOD = "orbit-watch-automated-verification";
    string internal constant METHOD_VERSION = "1.0.0";

    IEAS internal eas;
    TestUSD internal usd;
    OrbitWatchReviewerRegistry internal registry;
    OrbitWatchEscrow internal escrow;

    address internal requester = makeAddr("requester");
    address internal station = makeAddr("station");
    address internal otherStation = makeAddr("other station");
    address internal verifier = makeAddr("verifier");
    address internal r1 = makeAddr("reviewer 1");
    address internal r2 = makeAddr("reviewer 2");
    address internal r3 = makeAddr("reviewer 3");
    address internal platform = makeAddr("platform");
    address internal stranger = makeAddr("stranger");

    function setUp() public virtual {
        eas = _installEas();
        usd = new TestUSD();
        registry = new OrbitWatchReviewerRegistry(address(this));
        registry.addReviewer(r1);
        registry.addReviewer(r2);
        registry.addReviewer(r3);
        escrow = new OrbitWatchEscrow(usd, platform, eas, registry, verifier);
        usd.mint(requester, BUDGET);
        vm.prank(requester);
        usd.approve(address(escrow), type(uint256).max);
    }

    // ------------------------------------------------------------------ requests

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

    /// @dev Funded, reserved, delivered and attested with `verdict` (pass or fail).
    function _toChallengePeriod(string memory verdict) internal {
        _fund();
        _reserveAndDeliver();
        _attestResult(verdict);
    }

    function _challenge(address by) internal {
        vm.prank(by);
        escrow.challenge(ID, REASON);
    }

    function _status() internal view returns (OrbitWatchEscrow.Status) {
        return escrow.statusOf(ID);
    }

    function _round() internal view returns (address[3] memory) {
        return escrow.getRequest(ID).reviewers;
    }

    // ------------------------------------------------------------------ attestations

    function _resultRequest(string memory verdict, bytes32 delivery, address recipient)
        internal
        view
        returns (AttestationRequest memory)
    {
        return AttestationRequest({
            schema: escrow.resultSchemaUid(),
            data: AttestationRequestData({
                recipient: recipient,
                expirationTime: 0,
                revocable: false,
                refUID: bytes32(0),
                data: abi.encode(REQUEST_ID, delivery, REPORT, verdict, METHOD, METHOD_VERSION),
                value: 0
            })
        });
    }

    function _voteRequest(bool approve, bytes32 reason)
        internal
        view
        returns (AttestationRequest memory)
    {
        return AttestationRequest({
            schema: escrow.voteSchemaUid(),
            data: AttestationRequestData({
                recipient: station,
                expirationTime: 0,
                revocable: false,
                refUID: escrow.getRequest(ID).resultAttestation,
                data: abi.encode(REQUEST_ID, DELIVERY, approve, reason),
                value: 0
            })
        });
    }

    function _attestResult(string memory verdict) internal returns (bytes32) {
        AttestationRequest memory request = _resultRequest(verdict, DELIVERY, station);
        vm.prank(verifier);
        return eas.attest(request);
    }

    function _attestVote(address reviewer, bool approve) internal returns (bytes32) {
        AttestationRequest memory request = _voteRequest(approve, REASON);
        vm.prank(reviewer);
        return eas.attest(request);
    }

    /// @dev Expect `attester`'s attestation to be refused with `err` (and so never created).
    function _expectRefused(address attester, AttestationRequest memory request, bytes memory err)
        internal
    {
        vm.expectRevert(err);
        vm.prank(attester);
        eas.attest(request);
    }

    function _wrongStatus(OrbitWatchEscrow.Status status) internal pure returns (bytes memory) {
        return abi.encodeWithSelector(OrbitWatchEscrow.WrongStatus.selector, ID, status);
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

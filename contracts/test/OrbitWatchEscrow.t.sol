// SPDX-License-Identifier: Apache-2.0
pragma solidity 0.8.38;

import {IERC20} from "@openzeppelin/contracts/token/ERC20/IERC20.sol";
import {IEAS} from "eas-contracts/IEAS.sol";
import {OrbitWatchEscrow} from "../src/OrbitWatchEscrow.sol";
import {OrbitWatchReviewerRegistry} from "../src/OrbitWatchReviewerRegistry.sol";
import {EscrowTestBase} from "./helpers/EscrowTestBase.sol";

/// @notice Unit tests: deployment, every transition and refusal, and settlement rules 1.0.
/// Automated results and votes go through EAS (see OrbitWatchEscrow.attestations.t.sol for
/// the attestation rules themselves).
contract OrbitWatchEscrowTest is EscrowTestBase {
    // ------------------------------------------------------------------ deployment

    function test_RefusesEveryChainButBaseSepoliaAndAnvil() public {
        uint256[4] memory refused = [uint256(1), 8453, 10, 11_155_420];
        for (uint256 i; i < refused.length; ++i) {
            vm.chainId(refused[i]);
            vm.expectRevert(
                abi.encodeWithSelector(OrbitWatchEscrow.UnsupportedChain.selector, refused[i])
            );
            new OrbitWatchEscrow(usd, platform, eas, registry, verifier);
        }
        vm.chainId(84_532);
        new OrbitWatchEscrow(usd, platform, eas, registry, verifier);
    }

    function test_RefusesMissingContractsAndVerifier() public {
        address nothing = makeAddr("nothing");
        vm.expectRevert(abi.encodeWithSelector(OrbitWatchEscrow.NotAContract.selector, nothing));
        new OrbitWatchEscrow(IERC20(nothing), platform, eas, registry, verifier);
        vm.expectRevert(abi.encodeWithSelector(OrbitWatchEscrow.NotAContract.selector, nothing));
        new OrbitWatchEscrow(usd, platform, IEAS(nothing), registry, verifier);
        vm.expectRevert(abi.encodeWithSelector(OrbitWatchEscrow.NotAContract.selector, nothing));
        new OrbitWatchEscrow(usd, platform, eas, OrbitWatchReviewerRegistry(nothing), verifier);
        vm.expectRevert(OrbitWatchEscrow.InvalidVerifier.selector);
        new OrbitWatchEscrow(usd, platform, eas, registry, address(0));
    }

    function test_RequestKeyIsKeccakOfTheId() public view {
        assertEq(escrow.requestKey(REQUEST_ID), ID);
    }

    // ------------------------------------------------------------------ fund

    function test_FundLocksTheTermsAndTheSplit() public {
        _fund();
        OrbitWatchEscrow.Request memory r = escrow.getRequest(ID);
        assertEq(r.requester, requester);
        assertEq(r.termsHash, TERMS);
        assertEq(r.deliveryDeadline, vm.getBlockTimestamp() + DELIVERY_WINDOW);
        assertEq(r.reservationSeconds, RESERVATION);
        assertEq(r.challengeSeconds, CHALLENGE);
        assertEq(r.observerReward, OBSERVER_REWARD);
        assertEq(r.reviewerReward, REVIEWER_REWARD);
        assertEq(r.platformFee, PLATFORM_FEE);
        assertEq(uint8(_status()), uint8(OrbitWatchEscrow.Status.Funded));
        assertEq(escrow.depositOf(ID), DEPOSIT);
        assertEq(escrow.totalHeld(), DEPOSIT);
        assertEq(usd.balanceOf(address(escrow)), DEPOSIT);
        assertEq(usd.balanceOf(requester), BUDGET - DEPOSIT);
    }

    function test_FundRefusesBadInput() public {
        _fund();
        OrbitWatchEscrow.Terms memory terms = _terms();
        OrbitWatchEscrow.Split memory split = _split();
        vm.startPrank(requester);
        vm.expectRevert(abi.encodeWithSelector(OrbitWatchEscrow.AlreadyFunded.selector, ID));
        escrow.fund(ID, terms, split);

        bytes32 other = keccak256("SIM-REQ-0002");
        vm.expectRevert(OrbitWatchEscrow.InvalidSplit.selector);
        escrow.fund(other, terms, OrbitWatchEscrow.Split(0, 0, 0));

        terms.termsHash = bytes32(0);
        vm.expectRevert(OrbitWatchEscrow.InvalidTerms.selector);
        escrow.fund(other, terms, split);

        terms = _terms();
        terms.deliveryDeadline = uint64(vm.getBlockTimestamp());
        vm.expectRevert(OrbitWatchEscrow.InvalidTerms.selector);
        escrow.fund(other, terms, split);

        terms = _terms();
        terms.reviewSeconds = 0;
        vm.expectRevert(OrbitWatchEscrow.InvalidTerms.selector);
        escrow.fund(other, terms, split);
        vm.stopPrank();
    }

    function test_AFeeNeedsARecipient() public {
        OrbitWatchEscrow noFees = new OrbitWatchEscrow(usd, address(0), eas, registry, verifier);
        OrbitWatchEscrow.Terms memory terms = _terms();
        vm.startPrank(requester);
        usd.approve(address(noFees), type(uint256).max);
        vm.expectRevert(OrbitWatchEscrow.FeeWithoutRecipient.selector);
        noFees.fund(ID, terms, _split());
        noFees.fund(ID, terms, OrbitWatchEscrow.Split(OBSERVER_REWARD, REVIEWER_REWARD, 0));
        vm.stopPrank();
        assertEq(noFees.depositOf(ID), DEPOSIT - PLATFORM_FEE);
    }

    // ------------------------------------------------------------------ cancel

    function test_CancelRefundsEverythingAtOnce() public {
        _fund();
        vm.prank(stranger);
        vm.expectRevert(abi.encodeWithSelector(OrbitWatchEscrow.NotRequester.selector, ID));
        escrow.cancel(ID);

        vm.prank(requester);
        escrow.cancel(ID);
        assertEq(uint8(_status()), uint8(OrbitWatchEscrow.Status.Settled));
        assertEq(uint8(escrow.getRequest(ID).outcome), uint8(OrbitWatchEscrow.Status.Cancelled));
        assertEq(escrow.owed(requester), DEPOSIT);
        assertEq(escrow.totalHeld(), 0);

        vm.prank(requester);
        assertEq(escrow.withdraw(), DEPOSIT);
        assertEq(usd.balanceOf(requester), BUDGET);
        assertEq(usd.balanceOf(address(escrow)), 0);
    }

    function test_NoCancelAfterAReservation() public {
        _fund();
        vm.prank(station);
        escrow.reserve(ID);
        vm.prank(requester);
        vm.expectRevert(
            abi.encodeWithSelector(
                OrbitWatchEscrow.WrongStatus.selector, ID, OrbitWatchEscrow.Status.Reserved
            )
        );
        escrow.cancel(ID);
        // Once the reservation lapses the request is funded again and can be cancelled.
        skip(RESERVATION);
        vm.prank(requester);
        escrow.cancel(ID);
    }

    // ------------------------------------------------------------------ reserve and deliver

    function test_TheRequesterCannotReserve() public {
        _fund();
        vm.prank(requester);
        vm.expectRevert(
            abi.encodeWithSelector(OrbitWatchEscrow.RequesterCannotReserve.selector, ID)
        );
        escrow.reserve(ID);
    }

    function test_AReservationLapsesAndAnotherStationTakesOver() public {
        _fund();
        vm.prank(station);
        escrow.reserve(ID);
        assertEq(escrow.getRequest(ID).stageEndsAt, vm.getBlockTimestamp() + RESERVATION);

        vm.prank(otherStation);
        vm.expectRevert(
            abi.encodeWithSelector(
                OrbitWatchEscrow.WrongStatus.selector, ID, OrbitWatchEscrow.Status.Reserved
            )
        );
        escrow.reserve(ID);

        skip(RESERVATION - 1);
        assertEq(uint8(_status()), uint8(OrbitWatchEscrow.Status.Reserved));
        skip(1); // the reservation ends exactly at its deadline
        assertEq(uint8(_status()), uint8(OrbitWatchEscrow.Status.Funded));

        vm.prank(station);
        vm.expectRevert(
            abi.encodeWithSelector(
                OrbitWatchEscrow.WrongStatus.selector, ID, OrbitWatchEscrow.Status.Funded
            )
        );
        escrow.deliver(ID, DELIVERY);

        vm.prank(otherStation);
        escrow.reserve(ID);
        vm.prank(otherStation);
        escrow.deliver(ID, DELIVERY);
        assertEq(escrow.getRequest(ID).station, otherStation);
    }

    function test_AReservationNeverOutlastsTheDeliveryDeadline() public {
        _fund();
        skip(DELIVERY_WINDOW - 1 hours);
        vm.prank(station);
        escrow.reserve(ID);
        assertEq(escrow.getRequest(ID).stageEndsAt, escrow.getRequest(ID).deliveryDeadline);
        skip(1 hours);
        assertEq(uint8(_status()), uint8(OrbitWatchEscrow.Status.Expired));
    }

    function test_OnlyTheReservingStationDelivers() public {
        _fund();
        vm.prank(station);
        escrow.reserve(ID);
        vm.prank(otherStation);
        vm.expectRevert(abi.encodeWithSelector(OrbitWatchEscrow.NotReservedByCaller.selector, ID));
        escrow.deliver(ID, DELIVERY);
        vm.prank(station);
        vm.expectRevert(OrbitWatchEscrow.InvalidDelivery.selector);
        escrow.deliver(ID, bytes32(0));
        vm.prank(station);
        escrow.deliver(ID, DELIVERY);
        assertEq(escrow.getRequest(ID).deliverySha256, DELIVERY);
        assertEq(uint8(_status()), uint8(OrbitWatchEscrow.Status.Delivered));
    }

    function test_ExpiredWithoutDeliveryIsRefunded() public {
        _fund();
        vm.prank(station);
        escrow.reserve(ID);
        skip(DELIVERY_WINDOW);
        assertEq(uint8(_status()), uint8(OrbitWatchEscrow.Status.Expired));
        vm.prank(station);
        vm.expectRevert(
            abi.encodeWithSelector(
                OrbitWatchEscrow.WrongStatus.selector, ID, OrbitWatchEscrow.Status.Expired
            )
        );
        escrow.deliver(ID, DELIVERY);
        vm.prank(stranger); // anyone can settle
        escrow.settle(ID);
        assertEq(escrow.owed(requester), DEPOSIT);
        assertEq(escrow.owed(stranger), 0);
    }

    function test_AResultThatNeverComesExpires() public {
        _fund();
        _reserveAndDeliver();
        skip(VERIFICATION_TIMEOUT);
        assertEq(uint8(_status()), uint8(OrbitWatchEscrow.Status.Expired));
        _expectRefused(
            verifier,
            _resultRequest("pass", DELIVERY, station),
            _wrongStatus(OrbitWatchEscrow.Status.Expired)
        );
        escrow.settle(ID);
        assertEq(escrow.owed(requester), DEPOSIT);
        assertEq(escrow.owed(station), 0);
    }

    // ------------------------------------------------------------------ outcomes

    function test_AnUnchallengedPassIsAccepted() public {
        _toChallengePeriod("pass");
        assertEq(uint8(_status()), uint8(OrbitWatchEscrow.Status.ChallengePeriod));
        vm.expectRevert(
            abi.encodeWithSelector(
                OrbitWatchEscrow.WrongStatus.selector, ID, OrbitWatchEscrow.Status.ChallengePeriod
            )
        );
        escrow.settle(ID);
        skip(CHALLENGE);
        assertEq(uint8(_status()), uint8(OrbitWatchEscrow.Status.Accepted));
        escrow.settle(ID);
        assertEq(escrow.owed(station), OBSERVER_REWARD);
        assertEq(escrow.owed(platform), PLATFORM_FEE);
        assertEq(escrow.owed(requester), DEPOSIT - OBSERVER_REWARD - PLATFORM_FEE);
    }

    function test_AnUnchallengedFailIsRejectedAndRefunded() public {
        _toChallengePeriod("fail");
        skip(CHALLENGE);
        assertEq(uint8(_status()), uint8(OrbitWatchEscrow.Status.Rejected));
        escrow.settle(ID);
        assertEq(escrow.owed(requester), DEPOSIT);
        assertEq(escrow.owed(station), 0);
        assertEq(escrow.owed(platform), 0);
    }

    function test_InconclusiveGoesStraightToReviewers() public {
        _fund();
        _reserveAndDeliver();
        _attestResult("inconclusive");
        assertEq(uint8(_status()), uint8(OrbitWatchEscrow.Status.InReview));
        assertEq(escrow.getRequest(ID).stageEndsAt, vm.getBlockTimestamp() + REVIEW);
    }

    function test_OnlyTheRequesterOrTheObserverCanChallenge() public {
        _toChallengePeriod("pass");
        vm.prank(stranger);
        vm.expectRevert(abi.encodeWithSelector(OrbitWatchEscrow.NotAParty.selector, ID, stranger));
        escrow.challenge(ID, REASON);
        vm.prank(station);
        vm.expectRevert(OrbitWatchEscrow.MissingReason.selector);
        escrow.challenge(ID, bytes32(0));
        _challenge(station);
        assertEq(uint8(_status()), uint8(OrbitWatchEscrow.Status.InReview));
    }

    function test_AChallengeAfterTheDeadlineIsTooLate() public {
        _toChallengePeriod("pass");
        skip(CHALLENGE);
        vm.prank(requester);
        vm.expectRevert(
            abi.encodeWithSelector(
                OrbitWatchEscrow.WrongStatus.selector, ID, OrbitWatchEscrow.Status.Accepted
            )
        );
        escrow.challenge(ID, REASON);
    }

    function test_TwoApprovalsAcceptAndTheLateReviewerIsNotPaid() public {
        _toChallengePeriod("fail");
        _challenge(station);
        address[3] memory round = _round();
        _attestVote(round[0], true);
        _attestVote(round[1], true);
        assertEq(uint8(_status()), uint8(OrbitWatchEscrow.Status.Accepted));
        _expectRefused(
            round[2], _voteRequest(true, REASON), _wrongStatus(OrbitWatchEscrow.Status.Accepted)
        );

        // The example of docs/settlement.md: 100 + 10 + 10 + 5, and 10 back.
        escrow.settle(ID);
        assertEq(escrow.owed(station), OBSERVER_REWARD);
        assertEq(escrow.owed(round[0]), REVIEWER_REWARD);
        assertEq(escrow.owed(round[1]), REVIEWER_REWARD);
        assertEq(escrow.owed(round[2]), 0);
        assertEq(escrow.owed(platform), PLATFORM_FEE);
        assertEq(escrow.owed(requester), 10e6);
    }

    function test_ARejectionTwoToOnePaysAllThreeReviews() public {
        _toChallengePeriod("pass");
        _challenge(requester);
        address[3] memory round = _round();
        _attestVote(round[0], false);
        _attestVote(round[1], true);
        assertEq(uint8(_status()), uint8(OrbitWatchEscrow.Status.InReview));
        _attestVote(round[2], false);
        assertEq(uint8(_status()), uint8(OrbitWatchEscrow.Status.Rejected));
        escrow.settle(ID);
        assertEq(escrow.owed(r1) + escrow.owed(r2) + escrow.owed(r3), 3 * REVIEWER_REWARD);
        assertEq(escrow.owed(station), 0);
        assertEq(escrow.owed(platform), 0);
        assertEq(escrow.owed(requester), DEPOSIT - 3 * REVIEWER_REWARD);
    }

    function test_NoMajorityByTheDeadlineIsADispute() public {
        _toChallengePeriod("pass");
        _challenge(requester);
        address[3] memory round = _round();
        _attestVote(round[0], true);
        skip(REVIEW);
        assertEq(uint8(_status()), uint8(OrbitWatchEscrow.Status.Disputed));
        // A vote at the deadline is too late.
        _expectRefused(
            round[1], _voteRequest(true, REASON), _wrongStatus(OrbitWatchEscrow.Status.Disputed)
        );
        escrow.settle(ID);
        // The dispute rule: the completed review is paid, the observer gets nothing.
        assertEq(escrow.owed(round[0]), REVIEWER_REWARD);
        assertEq(escrow.owed(station), 0);
        assertEq(escrow.owed(requester), DEPOSIT - REVIEWER_REWARD);
    }

    // ------------------------------------------------------------------ settle and withdraw

    function test_ARequestIsSettledOnce() public {
        _toChallengePeriod("pass");
        skip(CHALLENGE);
        vm.prank(stranger);
        escrow.settle(ID);
        vm.expectRevert(
            abi.encodeWithSelector(
                OrbitWatchEscrow.WrongStatus.selector, ID, OrbitWatchEscrow.Status.Settled
            )
        );
        escrow.settle(ID);
        assertEq(escrow.totalOwed(), DEPOSIT);
    }

    function test_SettleRefusesUnknownAndUnfinishedRequests() public {
        vm.expectRevert(abi.encodeWithSelector(OrbitWatchEscrow.UnknownRequest.selector, ID));
        escrow.settle(ID);
        _fund();
        vm.expectRevert(
            abi.encodeWithSelector(
                OrbitWatchEscrow.WrongStatus.selector, ID, OrbitWatchEscrow.Status.Funded
            )
        );
        escrow.settle(ID);
    }

    function test_EachPartyWithdrawsOnlyItsOwnCredit() public {
        _toChallengePeriod("pass");
        skip(CHALLENGE);
        escrow.settle(ID);

        vm.prank(stranger);
        vm.expectRevert(OrbitWatchEscrow.NothingToWithdraw.selector);
        escrow.withdraw();

        vm.prank(station);
        assertEq(escrow.withdraw(), OBSERVER_REWARD);
        assertEq(usd.balanceOf(station), OBSERVER_REWARD);
        vm.prank(station);
        vm.expectRevert(OrbitWatchEscrow.NothingToWithdraw.selector);
        escrow.withdraw();

        _withdrawAll();
        assertEq(usd.balanceOf(platform), PLATFORM_FEE);
        assertEq(usd.balanceOf(requester), BUDGET - OBSERVER_REWARD - PLATFORM_FEE);
        assertEq(usd.balanceOf(stranger), 0);
        assertEq(usd.balanceOf(address(escrow)), 0);
        assertEq(escrow.totalOwed(), 0);
    }

    // ------------------------------------------------------------------ fuzz

    /// @notice Whatever the split and however the round goes, each party gets exactly what
    /// settlement rules 1.0 say and the payouts add up to the deposit.
    function testFuzz_SettlementPaysByTheRules(
        uint128 observerReward,
        uint128 reviewerReward,
        uint128 platformFee,
        uint8 path,
        bool[3] memory approvals
    ) public {
        observerReward = uint128(bound(observerReward, 0, 1e15));
        reviewerReward = uint128(bound(reviewerReward, 0, 1e15));
        platformFee = uint128(bound(platformFee, 0, 1e15));
        vm.assume(uint256(observerReward) + 3 * uint256(reviewerReward) + platformFee > 0);
        uint256 deposit = uint256(observerReward) + 3 * uint256(reviewerReward) + platformFee;
        usd.mint(requester, deposit);

        OrbitWatchEscrow.Terms memory terms = _terms();
        vm.prank(requester);
        escrow.fund(ID, terms, OrbitWatchEscrow.Split(observerReward, reviewerReward, platformFee));
        _reserveAndDeliver();

        path = uint8(bound(path, 0, 3));
        uint256 votes;
        if (path == 0) {
            // No round: the automated result stands.
            _attestResult(approvals[0] ? "pass" : "fail");
            skip(CHALLENGE);
        } else {
            if (path == 1) {
                _attestResult("inconclusive");
            } else {
                _attestResult("pass");
                _challenge(path == 2 ? requester : station);
            }
            address[3] memory round = _round();
            for (uint256 i; i < 3; ++i) {
                if (_status() != OrbitWatchEscrow.Status.InReview) break;
                _attestVote(round[i], approvals[i]);
                ++votes;
            }
            skip(REVIEW); // decides nothing more if the round is already decided
        }

        OrbitWatchEscrow.Status outcome = _status();
        escrow.settle(ID);

        bool accepted = outcome == OrbitWatchEscrow.Status.Accepted;
        uint256 toObserver = accepted ? observerReward : 0;
        uint256 toPlatform = accepted ? platformFee : 0;
        uint256 toReviews = votes * reviewerReward;
        assertEq(escrow.owed(station), toObserver);
        assertEq(escrow.owed(platform), toPlatform);
        assertEq(escrow.owed(r1) + escrow.owed(r2) + escrow.owed(r3), toReviews);
        assertEq(escrow.owed(requester), deposit - toObserver - toPlatform - toReviews);
        assertEq(escrow.totalOwed(), deposit);
        assertEq(escrow.totalHeld(), 0);
    }
}

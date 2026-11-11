// SPDX-License-Identifier: Apache-2.0
pragma solidity 0.8.38;

import {IERC20} from "@openzeppelin/contracts/token/ERC20/IERC20.sol";
import {OrbitWatchEscrow} from "../src/OrbitWatchEscrow.sol";
import {EscrowHarness} from "./helpers/EscrowHarness.sol";
import {EscrowTestBase} from "./helpers/EscrowTestBase.sol";

/// @notice Unit tests: every transition, every refusal and the settlement rules 1.0.
contract OrbitWatchEscrowTest is EscrowTestBase {
    // ------------------------------------------------------------------ deployment

    function test_RefusesEveryChainButBaseSepoliaAndAnvil() public {
        uint256[4] memory refused = [uint256(1), 8453, 10, 11_155_420];
        for (uint256 i; i < refused.length; ++i) {
            vm.chainId(refused[i]);
            vm.expectRevert(
                abi.encodeWithSelector(OrbitWatchEscrow.UnsupportedChain.selector, refused[i])
            );
            new OrbitWatchEscrow(usd, platform);
        }
        vm.chainId(84_532);
        new OrbitWatchEscrow(usd, platform);
    }

    function test_RefusesATokenThatIsNotAContract() public {
        vm.expectRevert(OrbitWatchEscrow.InvalidToken.selector);
        new OrbitWatchEscrow(IERC20(makeAddr("not a token")), platform);
    }

    function test_RequestKeyIsKeccakOfTheId() public view {
        assertEq(escrow.requestKey("SIM-REQ-0001"), keccak256("SIM-REQ-0001"));
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
        EscrowHarness noFees = new EscrowHarness(usd, address(0));
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

    function test_AVerificationThatNeverComesExpires() public {
        _fund();
        _reserveAndDeliver();
        skip(VERIFICATION_TIMEOUT);
        assertEq(uint8(_status()), uint8(OrbitWatchEscrow.Status.Expired));
        vm.expectRevert(
            abi.encodeWithSelector(
                OrbitWatchEscrow.WrongStatus.selector, ID, OrbitWatchEscrow.Status.Expired
            )
        );
        escrow.recordVerification(ID, OrbitWatchEscrow.Verdict.Pass, _noReviewers());
        escrow.settle(ID);
        assertEq(escrow.owed(requester), DEPOSIT);
        assertEq(escrow.owed(station), 0);
    }

    // ------------------------------------------------------------------ verification

    function test_AnUnchallengedPassIsAccepted() public {
        _toChallengePeriod(OrbitWatchEscrow.Verdict.Pass);
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
        _toChallengePeriod(OrbitWatchEscrow.Verdict.Fail);
        skip(CHALLENGE);
        assertEq(uint8(_status()), uint8(OrbitWatchEscrow.Status.Rejected));
        escrow.settle(ID);
        assertEq(escrow.owed(requester), DEPOSIT);
        assertEq(escrow.owed(station), 0);
        assertEq(escrow.owed(platform), 0);
    }

    function test_VerificationNeedsAVerdict() public {
        _fund();
        _reserveAndDeliver();
        vm.expectRevert(OrbitWatchEscrow.InvalidVerdict.selector);
        escrow.recordVerification(ID, OrbitWatchEscrow.Verdict.None, _noReviewers());
    }

    function test_InconclusiveGoesStraightToReviewers() public {
        _fund();
        _reserveAndDeliver();
        escrow.recordVerification(ID, OrbitWatchEscrow.Verdict.Inconclusive, _reviewers());
        assertEq(uint8(_status()), uint8(OrbitWatchEscrow.Status.InReview));
        assertEq(escrow.getRequest(ID).stageEndsAt, vm.getBlockTimestamp() + REVIEW);
    }

    // ------------------------------------------------------------------ challenge and review

    function test_OnlyTheRequesterOrTheObserverCanChallenge() public {
        _toChallengePeriod(OrbitWatchEscrow.Verdict.Pass);
        vm.expectRevert(abi.encodeWithSelector(OrbitWatchEscrow.NotAParty.selector, ID, stranger));
        escrow.challenge(ID, stranger, _reviewers());
        escrow.challenge(ID, station, _reviewers());
        assertEq(uint8(_status()), uint8(OrbitWatchEscrow.Status.InReview));
    }

    function test_AChallengeAfterTheDeadlineIsTooLate() public {
        _toChallengePeriod(OrbitWatchEscrow.Verdict.Pass);
        skip(CHALLENGE);
        vm.expectRevert(
            abi.encodeWithSelector(
                OrbitWatchEscrow.WrongStatus.selector, ID, OrbitWatchEscrow.Status.Accepted
            )
        );
        escrow.challenge(ID, requester, _reviewers());
    }

    function test_ARoundNeedsThreeIndependentReviewers() public {
        _toChallengePeriod(OrbitWatchEscrow.Verdict.Pass);
        vm.expectRevert(OrbitWatchEscrow.InvalidReviewers.selector);
        escrow.challenge(ID, requester, [r1, r1, r3]);
        vm.expectRevert(OrbitWatchEscrow.InvalidReviewers.selector);
        escrow.challenge(ID, requester, [r1, r2, address(0)]);
        vm.expectRevert(
            abi.encodeWithSelector(OrbitWatchEscrow.ConflictOfInterest.selector, requester)
        );
        escrow.challenge(ID, requester, [r1, requester, r3]);
        vm.expectRevert(
            abi.encodeWithSelector(OrbitWatchEscrow.ConflictOfInterest.selector, station)
        );
        escrow.challenge(ID, requester, [station, r2, r3]);
    }

    function test_TwoApprovalsAcceptAndTheLateReviewerIsNotPaid() public {
        _toChallengePeriod(OrbitWatchEscrow.Verdict.Fail);
        escrow.challenge(ID, station, _reviewers());
        vm.expectRevert(abi.encodeWithSelector(OrbitWatchEscrow.NotAssigned.selector, ID, stranger));
        escrow.vote(ID, stranger, true);
        escrow.vote(ID, r1, true);
        vm.expectRevert(abi.encodeWithSelector(OrbitWatchEscrow.AlreadyVoted.selector, ID, r1));
        escrow.vote(ID, r1, false);
        escrow.vote(ID, r2, true);
        assertEq(uint8(_status()), uint8(OrbitWatchEscrow.Status.Accepted));
        vm.expectRevert(
            abi.encodeWithSelector(
                OrbitWatchEscrow.WrongStatus.selector, ID, OrbitWatchEscrow.Status.Accepted
            )
        );
        escrow.vote(ID, r3, true);

        // The example of docs/settlement.md: 100 + 10 + 10 + 5, and 10 back.
        escrow.settle(ID);
        assertEq(escrow.owed(station), OBSERVER_REWARD);
        assertEq(escrow.owed(r1), REVIEWER_REWARD);
        assertEq(escrow.owed(r2), REVIEWER_REWARD);
        assertEq(escrow.owed(r3), 0);
        assertEq(escrow.owed(platform), PLATFORM_FEE);
        assertEq(escrow.owed(requester), 10e6);
    }

    function test_ARejectionTwoToOnePaysAllThreeReviews() public {
        _toChallengePeriod(OrbitWatchEscrow.Verdict.Pass);
        escrow.challenge(ID, requester, _reviewers());
        escrow.vote(ID, r1, false);
        escrow.vote(ID, r2, true);
        assertEq(uint8(_status()), uint8(OrbitWatchEscrow.Status.InReview));
        escrow.vote(ID, r3, false);
        assertEq(uint8(_status()), uint8(OrbitWatchEscrow.Status.Rejected));
        escrow.settle(ID);
        assertEq(escrow.owed(r1) + escrow.owed(r2) + escrow.owed(r3), 3 * REVIEWER_REWARD);
        assertEq(escrow.owed(station), 0);
        assertEq(escrow.owed(platform), 0);
        assertEq(escrow.owed(requester), DEPOSIT - 3 * REVIEWER_REWARD);
    }

    function test_NoMajorityByTheDeadlineIsADispute() public {
        _toChallengePeriod(OrbitWatchEscrow.Verdict.Pass);
        escrow.challenge(ID, requester, _reviewers());
        escrow.vote(ID, r1, true);
        skip(REVIEW);
        assertEq(uint8(_status()), uint8(OrbitWatchEscrow.Status.Disputed));
        vm.expectRevert(
            abi.encodeWithSelector(
                OrbitWatchEscrow.WrongStatus.selector, ID, OrbitWatchEscrow.Status.Disputed
            )
        );
        escrow.vote(ID, r2, true); // a vote at the deadline is too late
        escrow.settle(ID);
        // The dispute rule: the completed review is paid, the observer gets nothing.
        assertEq(escrow.owed(r1), REVIEWER_REWARD);
        assertEq(escrow.owed(station), 0);
        assertEq(escrow.owed(requester), DEPOSIT - REVIEWER_REWARD);
    }

    // ------------------------------------------------------------------ settle and withdraw

    function test_ARequestIsSettledOnce() public {
        _toChallengePeriod(OrbitWatchEscrow.Verdict.Pass);
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
        _toChallengePeriod(OrbitWatchEscrow.Verdict.Pass);
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
            escrow.recordVerification(
                ID,
                approvals[0] ? OrbitWatchEscrow.Verdict.Pass : OrbitWatchEscrow.Verdict.Fail,
                _noReviewers()
            );
            skip(CHALLENGE);
        } else {
            if (path == 1) {
                escrow.recordVerification(ID, OrbitWatchEscrow.Verdict.Inconclusive, _reviewers());
            } else {
                escrow.recordVerification(ID, OrbitWatchEscrow.Verdict.Pass, _reviewers());
                escrow.challenge(ID, path == 2 ? requester : station, _reviewers());
            }
            address[3] memory reviewers = _reviewers();
            for (uint256 i; i < 3; ++i) {
                if (_status() != OrbitWatchEscrow.Status.InReview) break;
                escrow.vote(ID, reviewers[i], approvals[i]);
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

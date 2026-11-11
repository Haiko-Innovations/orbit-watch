// SPDX-License-Identifier: Apache-2.0
pragma solidity 0.8.38;

import {Test} from "forge-std/Test.sol";
import {OrbitWatchEscrow} from "../src/OrbitWatchEscrow.sol";
import {TestUSD} from "./mocks/TestUSD.sol";

contract OrbitWatchEscrowTest is Test {
    OrbitWatchEscrow internal escrow;
    TestUSD internal usd;
    address internal requester = makeAddr("requester");
    address internal stranger = makeAddr("stranger");
    bytes32 internal constant REQUEST = keccak256("SIM-REQ-0001");
    // keccak256 is an opcode; sha256 would be a precompile call and use up vm.prank.
    bytes32 internal constant TERMS = keccak256("terms");
    uint64 internal deadline;

    function setUp() public {
        usd = new TestUSD();
        escrow = new OrbitWatchEscrow(usd);
        usd.mint(requester, 1000e6);
        vm.prank(requester);
        usd.approve(address(escrow), type(uint256).max);
        deadline = uint64(block.timestamp + 2 days);
    }

    function _fund() internal {
        vm.prank(requester);
        escrow.fund(REQUEST, TERMS, 100e6, 10e6, 5e6, deadline);
    }

    function test_RefusesEveryChainButBaseSepoliaAndAnvil() public {
        uint256[4] memory refused = [uint256(1), 8453, 10, 11_155_420];
        for (uint256 i; i < refused.length; ++i) {
            vm.chainId(refused[i]);
            vm.expectRevert(
                abi.encodeWithSelector(OrbitWatchEscrow.UnsupportedChain.selector, refused[i])
            );
            new OrbitWatchEscrow(usd);
        }
        vm.chainId(84_532);
        new OrbitWatchEscrow(usd);
    }

    function test_RequestKeyIsKeccakOfTheId() public view {
        assertEq(escrow.requestKey("SIM-REQ-0001"), REQUEST);
    }

    function test_FundLocksTheSplitAndTakesTheDeposit() public {
        vm.expectEmit(address(escrow));
        emit OrbitWatchEscrow.Funded(REQUEST, requester, 135e6, TERMS, deadline);
        _fund();
        OrbitWatchEscrow.Request memory request = escrow.getRequest(REQUEST);
        assertEq(request.requester, requester);
        assertEq(request.deposit, 135e6);
        assertEq(request.observerReward, 100e6);
        assertEq(request.reviewerReward, 10e6);
        assertEq(request.platformFee, 5e6);
        assertEq(request.termsHash, TERMS);
        assertEq(uint8(request.status), uint8(OrbitWatchEscrow.Status.Funded));
        assertEq(usd.balanceOf(address(escrow)), 135e6);
        assertEq(escrow.totalHeld(), 135e6);
        assertEq(usd.balanceOf(requester), 865e6);
    }

    function test_CannotFundTwiceOrWithoutValue() public {
        _fund();
        vm.prank(requester);
        vm.expectRevert(abi.encodeWithSelector(OrbitWatchEscrow.AlreadyFunded.selector, REQUEST));
        escrow.fund(REQUEST, TERMS, 1, 0, 0, deadline);
        vm.prank(requester);
        vm.expectRevert(OrbitWatchEscrow.InvalidSplit.selector);
        escrow.fund(keccak256("other"), TERMS, 0, 0, 0, deadline);
        vm.prank(requester);
        vm.expectRevert(OrbitWatchEscrow.InvalidDeadline.selector);
        escrow.fund(keccak256("other"), TERMS, 1, 0, 0, uint64(block.timestamp));
    }

    function test_RefundOnlyAfterTheDeadlineAndOnlyToTheRequester() public {
        _fund();
        vm.expectRevert(abi.encodeWithSelector(OrbitWatchEscrow.NotRefundable.selector, REQUEST));
        escrow.refund(REQUEST);
        vm.warp(deadline);
        vm.expectEmit(address(escrow));
        emit OrbitWatchEscrow.Refunded(REQUEST, requester, 135e6);
        vm.prank(stranger); // anyone may trigger it, the money goes to the requester
        escrow.refund(REQUEST);
        assertEq(usd.balanceOf(requester), 1000e6);
        assertEq(usd.balanceOf(stranger), 0);
        assertEq(usd.balanceOf(address(escrow)), 0);
        assertEq(escrow.totalHeld(), 0);
    }

    function test_RefundHappensOnce() public {
        _fund();
        vm.warp(deadline);
        escrow.refund(REQUEST);
        vm.expectRevert(abi.encodeWithSelector(OrbitWatchEscrow.NotRefundable.selector, REQUEST));
        escrow.refund(REQUEST);
        bytes32 unknown = keccak256("unknown");
        vm.expectRevert(abi.encodeWithSelector(OrbitWatchEscrow.UnknownRequest.selector, unknown));
        escrow.refund(unknown);
    }

    function testFuzz_FundThenRefundReturnsEverything(
        uint128 observer,
        uint128 reviewer,
        uint128 fee
    ) public {
        observer = uint128(bound(observer, 0, 1e15));
        reviewer = uint128(bound(reviewer, 0, 1e15));
        fee = uint128(bound(fee, 0, 1e15));
        uint256 deposit = uint256(observer) + 3 * uint256(reviewer) + uint256(fee);
        vm.assume(deposit > 0);
        usd.mint(requester, deposit);
        uint256 before = usd.balanceOf(requester);
        vm.prank(requester);
        escrow.fund(REQUEST, TERMS, observer, reviewer, fee, deadline);
        assertEq(usd.balanceOf(address(escrow)), deposit);
        vm.warp(deadline);
        escrow.refund(REQUEST);
        assertEq(usd.balanceOf(requester), before);
        assertEq(escrow.totalHeld(), 0);
    }
}

// SPDX-License-Identifier: Apache-2.0
pragma solidity 0.8.38;

import {Ownable} from "@openzeppelin/contracts/access/Ownable.sol";
import {Test} from "forge-std/Test.sol";
import {OrbitWatchReviewerRegistry} from "../src/OrbitWatchReviewerRegistry.sol";

contract OrbitWatchReviewerRegistryTest is Test {
    OrbitWatchReviewerRegistry internal registry;
    address internal owner = makeAddr("owner");
    address internal stranger = makeAddr("stranger");
    address internal r1 = makeAddr("reviewer 1");
    address internal r2 = makeAddr("reviewer 2");
    address internal requester = makeAddr("requester");
    address internal station = makeAddr("station");

    function setUp() public {
        registry = new OrbitWatchReviewerRegistry(owner);
    }

    function test_OnlyTheOwnerChangesTheRegistry() public {
        bytes memory denied =
            abi.encodeWithSelector(Ownable.OwnableUnauthorizedAccount.selector, stranger);
        vm.startPrank(stranger);
        vm.expectRevert(denied);
        registry.addReviewer(r1);
        vm.expectRevert(denied);
        registry.removeReviewer(r1);
        vm.expectRevert(denied);
        registry.setAffiliation(r1, station, true);
        vm.stopPrank();
    }

    function test_AddAndRemoveReviewers() public {
        vm.startPrank(owner);
        registry.addReviewer(r1);
        registry.addReviewer(r2);
        assertTrue(registry.isReviewer(r1));
        assertEq(registry.reviewers().length, 2);
        vm.expectRevert(
            abi.encodeWithSelector(OrbitWatchReviewerRegistry.AlreadyListed.selector, r1)
        );
        registry.addReviewer(r1);
        vm.expectRevert(OrbitWatchReviewerRegistry.InvalidAddress.selector);
        registry.addReviewer(address(0));
        registry.removeReviewer(r1);
        assertFalse(registry.isReviewer(r1));
        vm.expectRevert(abi.encodeWithSelector(OrbitWatchReviewerRegistry.NotListed.selector, r1));
        registry.removeReviewer(r1);
        vm.stopPrank();
    }

    function test_TheListIsBounded() public {
        vm.startPrank(owner);
        for (uint256 i = 1; i <= registry.MAX_REVIEWERS(); ++i) {
            registry.addReviewer(address(uint160(i)));
        }
        vm.expectRevert(OrbitWatchReviewerRegistry.TooManyReviewers.selector);
        registry.addReviewer(r1);
        vm.stopPrank();
    }

    function test_EligibleReviewersSkipThePartiesAndTheirAffiliates() public {
        address r3 = makeAddr("reviewer 3");
        vm.startPrank(owner);
        registry.addReviewer(r1);
        registry.addReviewer(r2);
        registry.addReviewer(r3);
        registry.addReviewer(station);
        registry.setAffiliation(r2, requester, true);
        vm.stopPrank();
        address[] memory eligible = registry.eligibleReviewers(requester, station);
        assertEq(eligible.length, 2);
        assertEq(eligible[0], r1);
        assertEq(eligible[1], r3);

        vm.prank(owner);
        registry.setAffiliation(r2, requester, false);
        assertEq(registry.eligibleReviewers(requester, station).length, 3);
    }

    function test_OwnershipMovesInTwoSteps() public {
        address next = makeAddr("timelock");
        vm.prank(owner);
        registry.transferOwnership(next);
        assertEq(registry.owner(), owner); // until accepted
        vm.prank(next);
        registry.acceptOwnership();
        assertEq(registry.owner(), next);
    }
}

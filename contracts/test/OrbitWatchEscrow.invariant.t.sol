// SPDX-License-Identifier: Apache-2.0
pragma solidity 0.8.38;

import {Test} from "forge-std/Test.sol";
import {OrbitWatchEscrow} from "../src/OrbitWatchEscrow.sol";
import {TestUSD} from "./mocks/TestUSD.sol";

/// @dev Random sequences of funding, refunding and passing time by several requesters.
contract EscrowHandler is Test {
    OrbitWatchEscrow internal escrow;
    TestUSD internal usd;
    address[] internal actors;
    bytes32[] public keys;
    uint256 public minted;

    constructor(OrbitWatchEscrow escrow_, TestUSD usd_) {
        escrow = escrow_;
        usd = usd_;
        for (uint256 i; i < 3; ++i) {
            address actor = makeAddr(string.concat("requester", vm.toString(i)));
            actors.push(actor);
            usd.mint(actor, 1e18);
            minted += 1e18;
            vm.prank(actor);
            usd.approve(address(escrow), type(uint256).max);
        }
    }

    function fund(uint256 actorSeed, uint128 observer, uint128 reviewer, uint64 lifetime) external {
        address actor = actors[actorSeed % actors.length];
        observer = uint128(bound(observer, 1, 1e12));
        reviewer = uint128(bound(reviewer, 0, 1e12));
        lifetime = uint64(bound(lifetime, 1, 30 days));
        bytes32 key = keccak256(abi.encode(keys.length, actor));
        vm.prank(actor);
        escrow.fund(key, bytes32(0), observer, reviewer, 0, uint64(block.timestamp) + lifetime);
        keys.push(key);
    }

    function refund(uint256 keySeed) external {
        if (keys.length == 0) return;
        bytes32 key = keys[keySeed % keys.length];
        OrbitWatchEscrow.Request memory request = escrow.getRequest(key);
        if (request.status != OrbitWatchEscrow.Status.Funded) return;
        if (block.timestamp < request.deliveryDeadline) return;
        escrow.refund(key);
    }

    function wait(uint32 seconds_) external {
        vm.warp(block.timestamp + bound(seconds_, 0, 10 days));
    }

    function holders() external view returns (address[] memory) {
        return actors;
    }

    function keyCount() external view returns (uint256) {
        return keys.length;
    }
}

contract OrbitWatchEscrowInvariantTest is Test {
    OrbitWatchEscrow internal escrow;
    TestUSD internal usd;
    EscrowHandler internal handler;

    function setUp() public {
        usd = new TestUSD();
        escrow = new OrbitWatchEscrow(usd);
        handler = new EscrowHandler(escrow, usd);
        targetContract(address(handler));
    }

    /// The escrow holds exactly what it owes.
    function invariant_BalanceEqualsWhatIsOwed() public view {
        assertEq(usd.balanceOf(address(escrow)), escrow.totalHeld());
    }

    /// No token is created or lost: requesters plus the escrow hold everything minted.
    function invariant_NothingCreatedOrLost() public view {
        address[] memory holders = handler.holders();
        uint256 total = usd.balanceOf(address(escrow));
        for (uint256 i; i < holders.length; ++i) {
            total += usd.balanceOf(holders[i]);
        }
        assertEq(total, handler.minted());
    }

    /// The sum of the deposits of funded requests is what the escrow holds.
    function invariant_HeldEqualsOpenDeposits() public view {
        uint256 open;
        for (uint256 i; i < handler.keyCount(); ++i) {
            OrbitWatchEscrow.Request memory request = escrow.getRequest(handler.keys(i));
            if (request.status == OrbitWatchEscrow.Status.Funded) open += request.deposit;
        }
        assertEq(open, escrow.totalHeld());
    }
}

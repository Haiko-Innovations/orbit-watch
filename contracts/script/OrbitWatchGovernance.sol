// SPDX-License-Identifier: Apache-2.0
pragma solidity 0.8.38;

import {TimelockController} from "@openzeppelin/contracts/governance/TimelockController.sol";
import {OrbitWatchReviewerRegistry} from "../src/OrbitWatchReviewerRegistry.sol";
import {ISafe} from "./ISafe.sol";

/// @title Orbit Watch governance set-up (decisions P2-07 and D-21)
/// @notice Deploys the reviewer registry behind a public timelock whose only proposer is a
/// Safe 2-of-3 multisig. The tests and the testnet deployment (step 2.7) use this one function,
/// so the tested set-up is the deployed one.
library OrbitWatchGovernance {
    /// @notice Every change to the reviewer list is public this long before it takes effect.
    uint256 internal constant MIN_DELAY = 48 hours;
    uint256 internal constant SIGNERS = 3;
    uint256 internal constant THRESHOLD = 2;

    error NotATwoOfThreeSafe(address safe);

    /// @notice Deploys the timelock and the registry it owns.
    /// - Timelock: minimum delay 48 hours; the Safe is the only proposer and canceller; anyone
    ///   may execute a change once its delay has passed; no administrator, so only the timelock
    ///   itself (that is, the Safe and 48 hours) can change its roles or its delay.
    /// - Registry: owned by the timelock from the start, with `initialReviewers`.
    function deploy(ISafe safe, address[] memory initialReviewers)
        internal
        returns (TimelockController timelock, OrbitWatchReviewerRegistry registry)
    {
        if (
            address(safe).code.length == 0 || safe.getThreshold() != THRESHOLD
                || safe.getOwners().length != SIGNERS
        ) revert NotATwoOfThreeSafe(address(safe));
        address[] memory proposers = new address[](1);
        proposers[0] = address(safe);
        address[] memory executors = new address[](1);
        executors[0] = address(0); // anyone
        timelock = new TimelockController(MIN_DELAY, proposers, executors, address(0));
        registry = new OrbitWatchReviewerRegistry(address(timelock), initialReviewers);
    }
}

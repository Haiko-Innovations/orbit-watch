// SPDX-License-Identifier: Apache-2.0
pragma solidity 0.8.38;

import {IERC20} from "@openzeppelin/contracts/token/ERC20/IERC20.sol";
import {OrbitWatchEscrow} from "../../src/OrbitWatchEscrow.sol";

/// @notice LOCAL TESTS ONLY. Exposes the escrow's verification functions (the automated
/// result, challenges and votes) WITHOUT ANY AUTHORISATION, so that the settlement rules can
/// be tested before step 2.3 connects them to EAS attestations. Never deployed.
contract EscrowHarness is OrbitWatchEscrow {
    constructor(IERC20 token_, address feeRecipient_) OrbitWatchEscrow(token_, feeRecipient_) {}

    function recordVerification(bytes32 requestId, Verdict verdict, address[3] memory reviewers)
        external
    {
        _recordVerification(requestId, verdict, reviewers);
    }

    function challenge(bytes32 requestId, address challenger, address[3] memory reviewers)
        external
    {
        _challenge(requestId, challenger, reviewers);
    }

    function vote(bytes32 requestId, address reviewer, bool approve) external {
        _vote(requestId, reviewer, approve);
    }
}

// SPDX-License-Identifier: Apache-2.0
pragma solidity 0.8.38;

import {Ownable} from "@openzeppelin/contracts/access/Ownable.sol";
import {Ownable2Step} from "@openzeppelin/contracts/access/Ownable2Step.sol";
import {EnumerableSet} from "@openzeppelin/contracts/utils/structs/EnumerableSet.sol";

/// @title Orbit Watch reviewer registry
/// @notice The pre-approved reviewers and their declared affiliations (decision D-13), on the
/// TESTNET. The escrow chooses each round's reviewers from this list.
/// @dev The owner adds and removes reviewers and affiliations. Step 2.4 makes the owner an
/// OpenZeppelin TimelockController whose proposer is a Safe multisig (decision P2-07), so
/// every change is public for 48 hours before it takes effect.
contract OrbitWatchReviewerRegistry is Ownable2Step {
    using EnumerableSet for EnumerableSet.AddressSet;

    /// @notice Bounds the work of choosing reviewers for a round.
    uint256 public constant MAX_REVIEWERS = 64;

    EnumerableSet.AddressSet private _reviewers;

    /// @notice Parties whose requests and deliveries a reviewer must never review, such as
    /// their own stations or their employer.
    mapping(address reviewer => mapping(address party => bool)) public isAffiliated;

    error InvalidAddress();
    error AlreadyListed(address reviewer);
    error NotListed(address reviewer);
    error TooManyReviewers();

    event ReviewerAdded(address indexed reviewer);
    event ReviewerRemoved(address indexed reviewer);
    event AffiliationSet(address indexed reviewer, address indexed party, bool affiliated);

    constructor(address owner_) Ownable(owner_) {}

    function addReviewer(address reviewer) external onlyOwner {
        if (reviewer == address(0)) revert InvalidAddress();
        if (_reviewers.length() >= MAX_REVIEWERS) revert TooManyReviewers();
        if (!_reviewers.add(reviewer)) revert AlreadyListed(reviewer);
        emit ReviewerAdded(reviewer);
    }

    /// @notice A removed reviewer's votes no longer count, also in rounds already under way.
    function removeReviewer(address reviewer) external onlyOwner {
        if (!_reviewers.remove(reviewer)) revert NotListed(reviewer);
        emit ReviewerRemoved(reviewer);
    }

    function setAffiliation(address reviewer, address party, bool affiliated) external onlyOwner {
        if (reviewer == address(0) || party == address(0)) revert InvalidAddress();
        isAffiliated[reviewer][party] = affiliated;
        emit AffiliationSet(reviewer, party, affiliated);
    }

    function isReviewer(address reviewer) external view returns (bool) {
        return _reviewers.contains(reviewer);
    }

    function reviewers() external view returns (address[] memory) {
        return _reviewers.values();
    }

    /// @notice The reviewers who may review a request between `requester` and `observer`:
    /// neither of them, and affiliated with neither.
    function eligibleReviewers(address requester, address observer)
        external
        view
        returns (address[] memory eligible)
    {
        address[] memory all = _reviewers.values();
        eligible = new address[](all.length);
        uint256 n = 0;
        for (uint256 i; i < all.length; ++i) {
            address r = all[i];
            if (
                r != requester && r != observer && !isAffiliated[r][requester]
                    && !isAffiliated[r][observer]
            ) {
                eligible[n++] = r;
            }
        }
        assembly ("memory-safe") {
            mstore(eligible, n) // shorten the array to the eligible ones
        }
    }
}

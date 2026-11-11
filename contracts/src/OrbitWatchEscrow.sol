// SPDX-License-Identifier: Apache-2.0
pragma solidity 0.8.38;

import {IERC20} from "@openzeppelin/contracts/token/ERC20/IERC20.sol";
import {SafeERC20} from "@openzeppelin/contracts/token/ERC20/utils/SafeERC20.sol";

/// @title Orbit Watch escrow
/// @notice Holds TESTNET deposits for Orbit Watch requests (phase 2, step 2.1 skeleton).
/// @dev Testnet only: the constructor refuses every chain except Base Sepolia (84532) and a
/// local Anvil chain (31337). Not upgradeable: no proxy, no owner, no administrator. Money
/// leaves only by the rules of each request. Step 2.1 has funding and the expiry refund;
/// deliveries, settlement and attestations come in steps 2.2 and 2.3.
contract OrbitWatchEscrow {
    using SafeERC20 for IERC20;

    uint256 public constant BASE_SEPOLIA_CHAIN_ID = 84_532;
    uint256 public constant ANVIL_CHAIN_ID = 31_337;
    uint256 public constant REVIEWERS_PER_ROUND = 3;

    enum Status {
        None,
        Funded,
        Refunded
    }

    struct Request {
        address requester;
        uint64 deliveryDeadline;
        Status status;
        uint128 deposit;
        uint128 observerReward;
        uint128 reviewerReward;
        uint128 platformFee;
        bytes32 termsHash;
    }

    /// @notice The settlement token (Circle's testnet USDC on Base Sepolia, decision P2-02).
    IERC20 public immutable token;

    /// @notice Sum of the deposits the escrow still owes; always equals its token balance.
    uint256 public totalHeld;

    mapping(bytes32 requestId => Request) private _requests;

    error UnsupportedChain(uint256 chainId);
    error InvalidSplit();
    error InvalidDeadline();
    error AlreadyFunded(bytes32 requestId);
    error UnknownRequest(bytes32 requestId);
    error NotRefundable(bytes32 requestId);

    event Funded(
        bytes32 indexed requestId,
        address indexed requester,
        uint256 deposit,
        bytes32 termsHash,
        uint64 deliveryDeadline
    );
    event Refunded(bytes32 indexed requestId, address indexed requester, uint256 amount);

    constructor(IERC20 token_) {
        if (block.chainid != BASE_SEPOLIA_CHAIN_ID && block.chainid != ANVIL_CHAIN_ID) {
            revert UnsupportedChain(block.chainid);
        }
        token = token_;
    }

    /// @notice The key of an Orbit Watch request: keccak256 of its request ID string.
    function requestKey(string calldata requestId) external pure returns (bytes32) {
        return keccak256(bytes(requestId));
    }

    /// @notice Deposit a request's rewards. The split is locked here (settlement rules 1.0):
    /// deposit = observer reward + 3 x reviewer reward + platform fee.
    /// @param termsHash SHA-256 of the request's frozen terms (off-chain lifecycle).
    function fund(
        bytes32 requestId,
        bytes32 termsHash,
        uint128 observerReward,
        uint128 reviewerReward,
        uint128 platformFee,
        uint64 deliveryDeadline
    ) external {
        if (_requests[requestId].status != Status.None) {
            revert AlreadyFunded(requestId);
        }
        // Deadlines are hours or days apart; a sequencer shifting time by seconds cannot matter.
        // forge-lint: disable-next-line(block-timestamp)
        if (deliveryDeadline <= block.timestamp) revert InvalidDeadline();
        uint256 deposit = uint256(observerReward) + REVIEWERS_PER_ROUND * uint256(reviewerReward)
            + uint256(platformFee);
        if (deposit == 0 || deposit > type(uint128).max) revert InvalidSplit();

        _requests[requestId] = Request({
            requester: msg.sender,
            deliveryDeadline: deliveryDeadline,
            status: Status.Funded,
            // Checked above: deposit <= type(uint128).max.
            // forge-lint: disable-next-line(unsafe-typecast)
            deposit: uint128(deposit),
            observerReward: observerReward,
            reviewerReward: reviewerReward,
            platformFee: platformFee,
            termsHash: termsHash
        });
        totalHeld += deposit;
        token.safeTransferFrom(msg.sender, address(this), deposit);
        emit Funded(requestId, msg.sender, deposit, termsHash, deliveryDeadline);
    }

    /// @notice Return the whole deposit to the requester once the delivery deadline has passed.
    /// Anyone may call it; the money always goes to the requester. In step 2.1 there are no
    /// deliveries yet, so every funded request becomes refundable at its deadline.
    function refund(bytes32 requestId) external {
        Request storage request = _requests[requestId];
        if (request.status == Status.None) revert UnknownRequest(requestId);
        // forge-lint: disable-next-line(block-timestamp)
        if (request.status != Status.Funded || block.timestamp < request.deliveryDeadline) {
            revert NotRefundable(requestId);
        }
        request.status = Status.Refunded;
        uint256 amount = request.deposit;
        totalHeld -= amount;
        token.safeTransfer(request.requester, amount);
        emit Refunded(requestId, request.requester, amount);
    }

    function getRequest(bytes32 requestId) external view returns (Request memory) {
        return _requests[requestId];
    }
}

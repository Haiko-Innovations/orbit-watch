// SPDX-License-Identifier: Apache-2.0
pragma solidity 0.8.38;

import {IERC20} from "@openzeppelin/contracts/token/ERC20/IERC20.sol";
import {SafeERC20} from "@openzeppelin/contracts/token/ERC20/utils/SafeERC20.sol";

/// @title Orbit Watch escrow
/// @notice Holds TESTNET deposits for Orbit Watch requests and pays them out by settlement
/// rules 1.0, the same rules as the phase 1 points ledger (decisions P2-05, P2-06, D-12).
/// @dev Testnet only: the constructor refuses every chain except Base Sepolia (84532) and a
/// local Anvil chain (31337). Not upgradeable: no proxy, no owner, no administrator. Money
/// leaves only by the rules of each request, and only to the party it is owed to.
///
/// Deadlines are applied lazily: `statusOf` gives a request's status at the current block
/// time, the way the phase 1 lifecycle applies every deadline that has passed. No keeper is
/// needed, and anyone can settle a request once it has an outcome.
///
/// Payouts are credited and then withdrawn by each party (`withdraw`), so a transfer that
/// fails for one party can never block a settlement or another party's money (decision D-19).
///
/// Step 2.2 has the parties' own actions (fund, cancel, reserve, deliver), settlement and
/// withdrawal. Recording the automated result, challenges and votes are internal functions
/// here; step 2.3 connects them to EAS attestations.
contract OrbitWatchEscrow {
    using SafeERC20 for IERC20;

    uint256 public constant BASE_SEPOLIA_CHAIN_ID = 84_532;
    uint256 public constant ANVIL_CHAIN_ID = 31_337;
    uint256 public constant REVIEWERS_PER_ROUND = 3;
    uint256 public constant VOTES_TO_DECIDE = 2;

    /// @notice A request's status. `Disputed` and `Expired` are only ever reached through a
    /// deadline, so `statusOf` returns them but they are never stored.
    enum Status {
        None,
        Funded,
        Reserved,
        Delivered,
        ChallengePeriod,
        InReview,
        Accepted,
        Rejected,
        Disputed,
        Expired,
        Cancelled,
        Settled
    }

    enum Verdict {
        None,
        Pass,
        Fail,
        Inconclusive
    }

    /// @notice Why a payout was credited (the `reason` of a phase 1 payout).
    enum Reason {
        ObserverReward,
        Review,
        PlatformFee,
        Refund
    }

    /// @notice The time limits of a request, from its frozen terms (in whole seconds).
    struct Terms {
        bytes32 termsHash; // SHA-256 of the frozen terms (`terms_sha256` off chain)
        uint64 deliveryDeadline;
        uint32 reservationSeconds;
        uint32 verificationTimeoutSeconds;
        uint32 challengeSeconds;
        uint32 reviewSeconds;
    }

    /// @notice The reward split, locked at funding. Deposit = observer + 3 × reviewer + fee.
    struct Split {
        uint128 observerReward;
        uint128 reviewerReward;
        uint128 platformFee;
    }

    struct Request {
        address requester;
        uint64 deliveryDeadline;
        Status status; // stored status; see statusOf for the status at the current time
        Verdict verdict;
        Status outcome; // set when the request is settled
        address station; // the reserving station; the observer once it has delivered
        uint64 stageEndsAt; // reservation, verification, challenge or review deadline
        uint8 voted; // bit i set: reviewers[i] has voted
        uint8 approved; // bit i set: reviewers[i] approved
        uint32 reservationSeconds;
        uint32 verificationTimeoutSeconds;
        uint32 challengeSeconds;
        uint32 reviewSeconds;
        uint128 observerReward;
        uint128 reviewerReward;
        uint128 platformFee;
        bytes32 termsHash;
        bytes32 deliverySha256;
        address[3] reviewers;
    }

    /// @notice The settlement token (Circle's testnet USDC on Base Sepolia, decision P2-02).
    IERC20 public immutable token;

    /// @notice Who receives platform fees; fixed at deployment. With no recipient (the zero
    /// address) every request must have a zero fee.
    address public immutable feeRecipient;

    /// @notice Deposits of requests that are not settled yet.
    uint256 public totalHeld;

    /// @notice Payouts credited and not yet withdrawn.
    uint256 public totalOwed;

    /// @notice What each party can withdraw.
    mapping(address party => uint256 amount) public owed;

    mapping(bytes32 requestId => Request) private _requests;

    error UnsupportedChain(uint256 chainId);
    error InvalidToken();
    error InvalidSplit();
    error InvalidTerms();
    error FeeWithoutRecipient();
    error AlreadyFunded(bytes32 requestId);
    error UnknownRequest(bytes32 requestId);
    error WrongStatus(bytes32 requestId, Status status);
    error NotRequester(bytes32 requestId);
    error RequesterCannotReserve(bytes32 requestId);
    error NotReservedByCaller(bytes32 requestId);
    error InvalidDelivery();
    error InvalidVerdict();
    error NotAParty(bytes32 requestId, address challenger);
    error InvalidReviewers();
    error ConflictOfInterest(address reviewer);
    error NotAssigned(bytes32 requestId, address reviewer);
    error AlreadyVoted(bytes32 requestId, address reviewer);
    error NothingToWithdraw();

    event Funded(
        bytes32 indexed requestId,
        address indexed requester,
        uint256 deposit,
        bytes32 termsHash,
        uint64 deliveryDeadline
    );
    event Cancelled(bytes32 indexed requestId);
    event Reserved(bytes32 indexed requestId, address indexed station, uint64 until);
    event Delivered(bytes32 indexed requestId, address indexed station, bytes32 deliverySha256);
    event VerificationRecorded(bytes32 indexed requestId, Verdict verdict);
    event ReviewStarted(
        bytes32 indexed requestId, address indexed challenger, address[3] reviewers, uint64 until
    );
    event Voted(bytes32 indexed requestId, address indexed reviewer, bool approve);
    event Settled(bytes32 indexed requestId, Status outcome);
    event Credited(bytes32 indexed requestId, address indexed party, uint256 amount, Reason reason);
    event Withdrawn(address indexed party, uint256 amount);

    // A zero fee recipient is allowed on purpose: it means no platform fees.
    // forge-lint: disable-next-line(missing-zero-check)
    constructor(IERC20 token_, address feeRecipient_) {
        if (block.chainid != BASE_SEPOLIA_CHAIN_ID && block.chainid != ANVIL_CHAIN_ID) {
            revert UnsupportedChain(block.chainid);
        }
        if (address(token_).code.length == 0) revert InvalidToken();
        token = token_;
        feeRecipient = feeRecipient_;
    }

    // ------------------------------------------------------------------ views

    /// @notice The on-chain key of an Orbit Watch request ID, for example "SIM-REQ-0001".
    function requestKey(string calldata requestId) external pure returns (bytes32) {
        return keccak256(bytes(requestId));
    }

    function getRequest(bytes32 requestId) external view returns (Request memory) {
        return _requests[requestId];
    }

    /// @notice A request's status now, with every passed deadline applied.
    function statusOf(bytes32 requestId) public view returns (Status) {
        return _statusNow(_requests[requestId]);
    }

    /// @notice What a request's requester deposited.
    function depositOf(bytes32 requestId) public view returns (uint256) {
        return _deposit(_requests[requestId]);
    }

    // ------------------------------------------------------------------ the parties' actions

    /// @notice Deposit a request's reward split and lock it with the request's terms.
    /// The caller is the requester and must have approved the deposit for this contract.
    function fund(bytes32 requestId, Terms calldata terms, Split calldata split) external {
        Request storage r = _requests[requestId];
        if (r.status != Status.None) revert AlreadyFunded(requestId);
        if (
            terms.termsHash == bytes32(0) || terms.reservationSeconds == 0
                || terms.verificationTimeoutSeconds == 0 || terms.challengeSeconds == 0
                || terms.reviewSeconds == 0
        ) revert InvalidTerms();
        // Deadlines are hours or days apart; a block producer's few seconds of leeway
        // cannot change an outcome in a way that matters (the same holds below).
        // forge-lint: disable-next-line(block-timestamp)
        if (terms.deliveryDeadline <= block.timestamp) revert InvalidTerms();
        uint256 deposit = uint256(split.observerReward) + REVIEWERS_PER_ROUND
            * uint256(split.reviewerReward) + uint256(split.platformFee);
        if (deposit == 0 || deposit > type(uint128).max) revert InvalidSplit();
        if (split.platformFee != 0 && feeRecipient == address(0)) revert FeeWithoutRecipient();

        r.requester = msg.sender;
        r.status = Status.Funded;
        r.termsHash = terms.termsHash;
        r.deliveryDeadline = terms.deliveryDeadline;
        r.reservationSeconds = terms.reservationSeconds;
        r.verificationTimeoutSeconds = terms.verificationTimeoutSeconds;
        r.challengeSeconds = terms.challengeSeconds;
        r.reviewSeconds = terms.reviewSeconds;
        r.observerReward = split.observerReward;
        r.reviewerReward = split.reviewerReward;
        r.platformFee = split.platformFee;
        totalHeld += deposit;

        token.safeTransferFrom(msg.sender, address(this), deposit);
        emit Funded(requestId, msg.sender, deposit, terms.termsHash, terms.deliveryDeadline);
    }

    /// @notice Cancel a funded request before anyone has reserved it. The whole deposit is
    /// credited back to the requester at once.
    function cancel(bytes32 requestId) external {
        Request storage r = _known(requestId);
        if (msg.sender != r.requester) revert NotRequester(requestId);
        _expect(requestId, r, Status.Funded);
        emit Cancelled(requestId);
        _settle(requestId, r, Status.Cancelled);
    }

    /// @notice Reserve a funded request for the calling station, until the reservation time
    /// of the terms has passed (never past the delivery deadline).
    function reserve(bytes32 requestId) external {
        Request storage r = _known(requestId);
        if (msg.sender == r.requester) revert RequesterCannotReserve(requestId);
        _expect(requestId, r, Status.Funded);
        uint256 until = block.timestamp + r.reservationSeconds;
        // forge-lint: disable-next-line(block-timestamp)
        if (until > r.deliveryDeadline) until = r.deliveryDeadline;
        r.status = Status.Reserved;
        r.station = msg.sender;
        // forge-lint: disable-next-line(unsafe-typecast)
        r.stageEndsAt = uint64(until); // at most the uint64 delivery deadline
        emit Reserved(requestId, msg.sender, r.stageEndsAt);
    }

    /// @notice Deliver an observation file, identified by its SHA-256, as the reserving
    /// station. Automated verification must be recorded before its timeout.
    function deliver(bytes32 requestId, bytes32 deliverySha256) external {
        Request storage r = _known(requestId);
        if (deliverySha256 == bytes32(0)) revert InvalidDelivery();
        _expect(requestId, r, Status.Reserved);
        if (msg.sender != r.station) revert NotReservedByCaller(requestId);
        r.status = Status.Delivered;
        r.deliverySha256 = deliverySha256;
        r.stageEndsAt = _after(r.verificationTimeoutSeconds);
        emit Delivered(requestId, msg.sender, deliverySha256);
    }

    /// @notice Settle a request that has an outcome: credit every payout by settlement rules
    /// 1.0. Anyone can call it; a request is settled once.
    function settle(bytes32 requestId) external {
        Request storage r = _known(requestId);
        Status outcome = _statusNow(r);
        if (
            outcome != Status.Accepted && outcome != Status.Rejected && outcome != Status.Disputed
                && outcome != Status.Expired
        ) revert WrongStatus(requestId, outcome);
        _settle(requestId, r, outcome);
    }

    /// @notice Transfer everything credited to the caller.
    function withdraw() external returns (uint256 amount) {
        amount = owed[msg.sender];
        if (amount == 0) revert NothingToWithdraw();
        owed[msg.sender] = 0;
        totalOwed -= amount;
        token.safeTransfer(msg.sender, amount);
        emit Withdrawn(msg.sender, amount);
    }

    // ------------------------------------------------------------------ verification (step 2.3)

    /// @dev The automated result. Pass or fail starts the challenge period; inconclusive
    /// goes straight to the three reviewers.
    function _recordVerification(bytes32 requestId, Verdict verdict, address[3] memory reviewers)
        internal
    {
        Request storage r = _known(requestId);
        _expect(requestId, r, Status.Delivered);
        if (verdict == Verdict.None) revert InvalidVerdict();
        r.verdict = verdict;
        emit VerificationRecorded(requestId, verdict);
        if (verdict == Verdict.Inconclusive) {
            _startReview(requestId, r, address(0), reviewers);
        } else {
            r.status = Status.ChallengePeriod;
            r.stageEndsAt = _after(r.challengeSeconds);
        }
    }

    /// @dev A challenge by the requester or the observer during the challenge period.
    function _challenge(bytes32 requestId, address challenger, address[3] memory reviewers)
        internal
    {
        Request storage r = _known(requestId);
        _expect(requestId, r, Status.ChallengePeriod);
        if (challenger != r.requester && challenger != r.station) {
            revert NotAParty(requestId, challenger);
        }
        _startReview(requestId, r, challenger, reviewers);
    }

    /// @dev A vote by one of the round's reviewers. Two equal votes decide.
    function _vote(bytes32 requestId, address reviewer, bool approve) internal {
        Request storage r = _known(requestId);
        _expect(requestId, r, Status.InReview);
        uint8 bit = 0;
        for (uint256 i; i < REVIEWERS_PER_ROUND; ++i) {
            if (r.reviewers[i] == reviewer) {
                // forge-lint: disable-next-line(unsafe-typecast)
                bit = uint8(1 << i); // i < 3
                break;
            }
        }
        if (bit == 0) revert NotAssigned(requestId, reviewer);
        if (r.voted & bit != 0) revert AlreadyVoted(requestId, reviewer);
        r.voted |= bit;
        if (approve) r.approved |= bit;
        emit Voted(requestId, reviewer, approve);

        uint256 votes = _count(r.voted);
        uint256 approvals = _count(r.approved);
        if (approvals >= VOTES_TO_DECIDE) {
            r.status = Status.Accepted;
        } else if (votes - approvals >= VOTES_TO_DECIDE) {
            r.status = Status.Rejected;
        }
    }

    // ------------------------------------------------------------------ internals

    function _startReview(
        bytes32 requestId,
        Request storage r,
        address challenger,
        address[3] memory reviewers
    ) private {
        (address a, address b, address c) = (reviewers[0], reviewers[1], reviewers[2]);
        if (a == address(0) || b == address(0) || c == address(0) || a == b || a == c || b == c) {
            revert InvalidReviewers();
        }
        _checkIndependent(r, a);
        _checkIndependent(r, b);
        _checkIndependent(r, c);
        r.status = Status.InReview;
        r.reviewers = reviewers;
        r.stageEndsAt = _after(r.reviewSeconds);
        emit ReviewStarted(requestId, challenger, reviewers, r.stageEndsAt);
    }

    /// @dev Neither the requester nor the observer can review their own request.
    function _checkIndependent(Request storage r, address reviewer) private view {
        if (reviewer == r.requester || reviewer == r.station) revert ConflictOfInterest(reviewer);
    }

    /// @dev Settlement rules 1.0 (D-12): the observer reward and the platform fee only when
    /// accepted, every completed review paid whatever the outcome, the rest to the requester.
    function _settle(bytes32 requestId, Request storage r, Status outcome) private {
        uint256 deposit = _deposit(r);
        r.status = Status.Settled;
        r.outcome = outcome;
        totalHeld -= deposit;
        emit Settled(requestId, outcome);

        uint256 paid = 0;
        if (outcome == Status.Accepted) {
            paid += _credit(requestId, r.station, r.observerReward, Reason.ObserverReward);
            paid += _credit(requestId, feeRecipient, r.platformFee, Reason.PlatformFee);
        }
        for (uint256 i; i < REVIEWERS_PER_ROUND; ++i) {
            if (r.voted & (uint256(1) << i) != 0) {
                paid += _credit(requestId, r.reviewers[i], r.reviewerReward, Reason.Review);
            }
        }
        _credit(requestId, r.requester, deposit - paid, Reason.Refund);
    }

    function _credit(bytes32 requestId, address party, uint256 amount, Reason reason)
        private
        returns (uint256)
    {
        if (amount == 0) return 0;
        owed[party] += amount;
        totalOwed += amount;
        emit Credited(requestId, party, amount, reason);
        return amount;
    }

    /// @dev The status at the current block time. Mirrors `advance` of the phase 1 lifecycle:
    /// a lapsed reservation first (back to funded), then the delivery deadline, the
    /// verification timeout, the end of the challenge period and the review deadline.
    function _statusNow(Request storage r) private view returns (Status s) {
        s = r.status;
        uint256 t = block.timestamp;
        // forge-lint: disable-next-line(block-timestamp)
        if (s == Status.Reserved && t >= r.stageEndsAt) s = Status.Funded;
        if (s == Status.Funded || s == Status.Reserved) {
            // forge-lint: disable-next-line(block-timestamp)
            return t >= r.deliveryDeadline ? Status.Expired : s;
        }
        // forge-lint: disable-next-line(block-timestamp)
        if (t < r.stageEndsAt) return s;
        if (s == Status.Delivered) return Status.Expired;
        if (s == Status.ChallengePeriod) {
            return r.verdict == Verdict.Pass ? Status.Accepted : Status.Rejected;
        }
        if (s == Status.InReview) return Status.Disputed;
    }

    function _known(bytes32 requestId) private view returns (Request storage r) {
        r = _requests[requestId];
        if (r.status == Status.None) revert UnknownRequest(requestId);
    }

    function _expect(bytes32 requestId, Request storage r, Status expected) private view {
        Status actual = _statusNow(r);
        if (actual != expected) revert WrongStatus(requestId, actual);
    }

    function _after(uint32 seconds_) private view returns (uint64) {
        // forge-lint: disable-next-line(unsafe-typecast)
        return uint64(block.timestamp + seconds_); // block times fit in uint64 for ages
    }

    function _deposit(Request storage r) private view returns (uint256) {
        return uint256(r.observerReward) + REVIEWERS_PER_ROUND * uint256(r.reviewerReward)
            + uint256(r.platformFee);
    }

    function _count(uint8 bits) private pure returns (uint256 n) {
        for (; bits != 0; bits &= bits - 1) {
            ++n;
        }
    }
}

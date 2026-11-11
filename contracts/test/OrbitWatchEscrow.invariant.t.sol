// SPDX-License-Identifier: Apache-2.0
pragma solidity 0.8.38;

import {StdInvariant} from "forge-std/StdInvariant.sol";
import {Test} from "forge-std/Test.sol";
import {OrbitWatchEscrow} from "../src/OrbitWatchEscrow.sol";
import {EscrowHarness} from "./helpers/EscrowHarness.sol";
import {TestUSD} from "./mocks/TestUSD.sol";

/// @notice Drives many requests at once through random but valid histories: funding,
/// cancelling, reserving, delivering, automated results, challenges, votes, settling,
/// withdrawing and time passing. Every settlement is checked against settlement rules 1.0,
/// and a stranger keeps trying to take money.
contract EscrowHandler is Test {
    EscrowHarness public immutable escrow;
    TestUSD public immutable usd;
    address public immutable platform;
    address public immutable stranger = makeAddr("stranger");

    address[2] internal requesters = [makeAddr("requester A"), makeAddr("requester B")];
    address[2] internal stations = [makeAddr("station A"), makeAddr("station B")];
    address[4] internal reviewerPool = [
        makeAddr("reviewer 1"),
        makeAddr("reviewer 2"),
        makeAddr("reviewer 3"),
        makeAddr("reviewer 4")
    ];

    uint256 public constant START_BALANCE = 1e18;
    uint256 public minted;

    bytes32[] public keys;
    mapping(bytes32 requestId => uint256 count) public settlements;
    string public violation; // empty while every check holds

    constructor(EscrowHarness escrow_, TestUSD usd_, address platform_) {
        escrow = escrow_;
        usd = usd_;
        platform = platform_;
        for (uint256 i; i < requesters.length; ++i) {
            usd.mint(requesters[i], START_BALANCE);
            minted += START_BALANCE;
            vm.prank(requesters[i]);
            usd.approve(address(escrow), type(uint256).max);
        }
    }

    // ------------------------------------------------------------------ actions

    function fund(uint256 who, uint128 observer, uint128 reviewer, uint128 fee, uint256 timing)
        external
    {
        observer = uint128(bound(observer, 0, 1e12));
        reviewer = uint128(bound(reviewer, 0, 1e12));
        fee = uint128(bound(fee, 0, 1e12));
        if (uint256(observer) + reviewer + fee == 0) return;
        OrbitWatchEscrow.Terms memory terms = OrbitWatchEscrow.Terms({
            termsHash: keccak256(abi.encode("terms", keys.length)),
            deliveryDeadline: uint64(vm.getBlockTimestamp() + bound(timing, 1 hours, 10 days)),
            reservationSeconds: uint32(bound(timing >> 64, 1 hours, 3 days)),
            verificationTimeoutSeconds: uint32(bound(timing >> 96, 1 hours, 2 days)),
            challengeSeconds: uint32(bound(timing >> 128, 1 hours, 2 days)),
            reviewSeconds: uint32(bound(timing >> 160, 1 hours, 3 days))
        });
        bytes32 id = keccak256(abi.encode("request", keys.length));
        vm.prank(requesters[who % requesters.length]);
        escrow.fund(id, terms, OrbitWatchEscrow.Split(observer, reviewer, fee));
        keys.push(id);
    }

    function cancel(uint256 k) external {
        (bytes32 id, bool found) = _pick(k);
        if (!found || escrow.statusOf(id) != OrbitWatchEscrow.Status.Funded) return;
        OrbitWatchEscrow.Request memory r = escrow.getRequest(id);
        uint256[] memory before = _owedNow();
        vm.prank(r.requester);
        escrow.cancel(id);
        _settled(id, r, OrbitWatchEscrow.Status.Cancelled, before);
    }

    function reserve(uint256 k, uint256 who) external {
        (bytes32 id, bool found) = _pick(k);
        if (!found || escrow.statusOf(id) != OrbitWatchEscrow.Status.Funded) return;
        vm.prank(stations[who % stations.length]);
        escrow.reserve(id);
    }

    function deliver(uint256 k) external {
        (bytes32 id, bool found) = _pick(k);
        if (!found || escrow.statusOf(id) != OrbitWatchEscrow.Status.Reserved) return;
        vm.prank(escrow.getRequest(id).station);
        escrow.deliver(id, keccak256(abi.encode("delivery", id)));
    }

    function verify(uint256 k, uint256 verdict, uint256 skipReviewer) external {
        (bytes32 id, bool found) = _pick(k);
        if (!found || escrow.statusOf(id) != OrbitWatchEscrow.Status.Delivered) return;
        escrow.recordVerification(
            id, OrbitWatchEscrow.Verdict(1 + verdict % 3), _round(skipReviewer)
        );
    }

    function challenge(uint256 k, bool byRequester, uint256 skipReviewer) external {
        (bytes32 id, bool found) = _pick(k);
        if (!found || escrow.statusOf(id) != OrbitWatchEscrow.Status.ChallengePeriod) return;
        OrbitWatchEscrow.Request memory r = escrow.getRequest(id);
        escrow.challenge(id, byRequester ? r.requester : r.station, _round(skipReviewer));
    }

    function vote(uint256 k, uint256 which, bool approve) external {
        (bytes32 id, bool found) = _pick(k);
        if (!found || escrow.statusOf(id) != OrbitWatchEscrow.Status.InReview) return;
        OrbitWatchEscrow.Request memory r = escrow.getRequest(id);
        uint256 i = which % 3;
        if (r.voted & (uint256(1) << i) != 0) return;
        escrow.vote(id, r.reviewers[i], approve);
    }

    function settle(uint256 k) external {
        (bytes32 id, bool found) = _pick(k);
        if (!found) return;
        OrbitWatchEscrow.Status outcome = escrow.statusOf(id);
        if (
            outcome != OrbitWatchEscrow.Status.Accepted
                && outcome != OrbitWatchEscrow.Status.Rejected
                && outcome != OrbitWatchEscrow.Status.Disputed
                && outcome != OrbitWatchEscrow.Status.Expired
        ) {
            vm.prank(stranger);
            try escrow.settle(id) {
                _fail("settled a request without an outcome, or twice");
            } catch {}
            return;
        }
        OrbitWatchEscrow.Request memory r = escrow.getRequest(id);
        uint256[] memory before = _owedNow();
        vm.prank(stranger); // anyone can settle
        escrow.settle(id);
        _settled(id, r, outcome, before);
    }

    function withdraw(uint256 who) external {
        address[] memory everyone = allParties();
        address party = everyone[who % everyone.length];
        uint256 amount = escrow.owed(party);
        uint256 balance = usd.balanceOf(party);
        vm.prank(party);
        try escrow.withdraw() returns (uint256 paid) {
            if (amount == 0 || paid != amount || usd.balanceOf(party) != balance + amount) {
                _fail("a withdrawal paid something other than what was owed");
            }
        } catch {
            if (amount != 0) _fail("a party could not withdraw what it was owed");
        }
    }

    /// @dev A stranger tries everything that could move someone else's money.
    function strangerTries(uint256 k) external {
        (bytes32 id, bool found) = _pick(k);
        vm.startPrank(stranger);
        try escrow.withdraw() {
            _fail("a stranger withdrew");
        } catch {}
        if (found) {
            try escrow.cancel(id) {
                _fail("a stranger cancelled");
            } catch {}
            try escrow.deliver(id, keccak256("forged")) {
                _fail("a stranger delivered");
            } catch {}
        }
        vm.stopPrank();
    }

    function wait(uint256 seconds_) external {
        skip(bound(seconds_, 1, 2 days));
    }

    // ------------------------------------------------------------------ checks

    /// @dev Settlement rules 1.0, computed independently of the contract.
    function _settled(
        bytes32 id,
        OrbitWatchEscrow.Request memory r,
        OrbitWatchEscrow.Status outcome,
        uint256[] memory before
    ) internal {
        settlements[id] += 1;
        bool accepted = outcome == OrbitWatchEscrow.Status.Accepted;
        uint256 deposit = uint256(r.observerReward) + 3 * uint256(r.reviewerReward) + r.platformFee;
        address[] memory everyone = allParties();
        uint256 total;
        for (uint256 p; p < everyone.length; ++p) {
            address party = everyone[p];
            uint256 expected;
            if (accepted && party == r.station) expected += r.observerReward;
            if (accepted && party == platform) expected += r.platformFee;
            for (uint256 i; i < 3; ++i) {
                if (r.voted & (uint256(1) << i) != 0 && party == r.reviewers[i]) {
                    expected += r.reviewerReward;
                }
            }
            if (party == r.requester) {
                uint256 votes;
                for (uint256 i; i < 3; ++i) {
                    if (r.voted & (uint256(1) << i) != 0) ++votes;
                }
                expected += deposit - votes * r.reviewerReward
                    - (accepted ? uint256(r.observerReward) + r.platformFee : 0);
            }
            uint256 got = escrow.owed(party) - before[p];
            if (got != expected) _fail("a settlement paid a party the wrong amount");
            total += got;
        }
        if (total != deposit) _fail("a settlement did not pay out exactly the deposit");
    }

    function _fail(string memory why) internal {
        if (bytes(violation).length == 0) violation = why;
    }

    // ------------------------------------------------------------------ helpers

    function _pick(uint256 k) internal view returns (bytes32, bool) {
        if (keys.length == 0) return (bytes32(0), false);
        return (keys[k % keys.length], true);
    }

    /// @dev Three different reviewers from the pool of four, leaving one out.
    function _round(uint256 skipReviewer) internal view returns (address[3] memory round) {
        uint256 left = skipReviewer % reviewerPool.length;
        uint256 n;
        for (uint256 i; i < reviewerPool.length; ++i) {
            if (i != left) round[n++] = reviewerPool[i];
        }
    }

    function _owedNow() internal view returns (uint256[] memory owed) {
        address[] memory everyone = allParties();
        owed = new uint256[](everyone.length);
        for (uint256 p; p < everyone.length; ++p) {
            owed[p] = escrow.owed(everyone[p]);
        }
    }

    function allParties() public view returns (address[] memory everyone) {
        everyone = new address[](10);
        everyone[0] = requesters[0];
        everyone[1] = requesters[1];
        everyone[2] = stations[0];
        everyone[3] = stations[1];
        for (uint256 i; i < 4; ++i) {
            everyone[4 + i] = reviewerPool[i];
        }
        everyone[8] = platform;
        everyone[9] = stranger;
    }

    function keyCount() external view returns (uint256) {
        return keys.length;
    }
}

/// @notice Properties that hold after any sequence of the handler's actions.
contract OrbitWatchEscrowInvariantTest is StdInvariant, Test {
    TestUSD internal usd;
    EscrowHarness internal escrow;
    EscrowHandler internal handler;

    function setUp() public {
        usd = new TestUSD();
        escrow = new EscrowHarness(usd, makeAddr("platform"));
        handler = new EscrowHandler(escrow, usd, makeAddr("platform"));
        bytes4[] memory selectors = new bytes4[](11);
        selectors[0] = EscrowHandler.fund.selector;
        selectors[1] = EscrowHandler.cancel.selector;
        selectors[2] = EscrowHandler.reserve.selector;
        selectors[3] = EscrowHandler.deliver.selector;
        selectors[4] = EscrowHandler.verify.selector;
        selectors[5] = EscrowHandler.challenge.selector;
        selectors[6] = EscrowHandler.vote.selector;
        selectors[7] = EscrowHandler.settle.selector;
        selectors[8] = EscrowHandler.withdraw.selector;
        selectors[9] = EscrowHandler.strangerTries.selector;
        selectors[10] = EscrowHandler.wait.selector;
        targetSelector(FuzzSelector({addr: address(handler), selectors: selectors}));
        targetContract(address(handler));
    }

    /// @notice Every settlement paid each party exactly what the rules say, nobody withdrew
    /// more or less than they were owed, and the stranger moved no money.
    function invariant_EveryCheckHolds() public view {
        assertEq(handler.violation(), "");
    }

    /// @notice The escrow's token balance is exactly what it holds and what it owes.
    function invariant_BalanceEqualsWhatIsOwed() public view {
        assertEq(usd.balanceOf(address(escrow)), escrow.totalHeld() + escrow.totalOwed());
    }

    /// @notice No token is created or lost.
    function invariant_NothingCreatedOrLost() public view {
        address[] memory everyone = handler.allParties();
        uint256 sum = usd.balanceOf(address(escrow));
        for (uint256 p; p < everyone.length; ++p) {
            sum += usd.balanceOf(everyone[p]);
        }
        assertEq(sum, handler.minted());
    }

    /// @notice What is held is the deposits of unsettled requests, and what is owed is what
    /// the parties can withdraw.
    function invariant_HeldAndOwedAddUp() public view {
        uint256 held;
        for (uint256 i; i < handler.keyCount(); ++i) {
            bytes32 id = handler.keys(i);
            if (escrow.getRequest(id).status != OrbitWatchEscrow.Status.Settled) {
                held += escrow.depositOf(id);
            }
        }
        assertEq(escrow.totalHeld(), held);
        address[] memory everyone = handler.allParties();
        uint256 owed;
        for (uint256 p; p < everyone.length; ++p) {
            owed += escrow.owed(everyone[p]);
        }
        assertEq(escrow.totalOwed(), owed);
    }

    /// @notice A request is settled at most once, and a settled request was settled once.
    function invariant_SettledOnce() public view {
        for (uint256 i; i < handler.keyCount(); ++i) {
            bytes32 id = handler.keys(i);
            bool settled = escrow.getRequest(id).status == OrbitWatchEscrow.Status.Settled;
            assertEq(handler.settlements(id), settled ? 1 : 0);
        }
    }

    /// @notice The stranger, who is party to nothing, never receives anything.
    function invariant_StrangerGetsNothing() public view {
        assertEq(usd.balanceOf(handler.stranger()), 0);
        assertEq(escrow.owed(handler.stranger()), 0);
    }
}

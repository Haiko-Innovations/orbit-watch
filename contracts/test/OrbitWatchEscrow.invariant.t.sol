// SPDX-License-Identifier: Apache-2.0
pragma solidity 0.8.38;

import {StdInvariant} from "forge-std/StdInvariant.sol";
import {Test} from "forge-std/Test.sol";
import {IEAS, AttestationRequest, AttestationRequestData} from "eas-contracts/IEAS.sol";
import {OrbitWatchEscrow} from "../src/OrbitWatchEscrow.sol";
import {OrbitWatchReviewerRegistry} from "../src/OrbitWatchReviewerRegistry.sol";
import {BaseSepoliaEas} from "./helpers/BaseSepoliaEas.sol";
import {TestUSD} from "./mocks/TestUSD.sol";

/// @notice Drives many requests at once through random but valid histories: funding,
/// cancelling, reserving, delivering, automated results, challenges, votes, settling,
/// withdrawing and time passing. Results and votes are EAS attestations. Every settlement is
/// checked against settlement rules 1.0, and a stranger keeps trying to take money or to
/// attest.
contract EscrowHandler is Test {
    OrbitWatchEscrow public immutable escrow;
    TestUSD public immutable usd;
    IEAS public immutable eas;
    address public immutable platform;
    address public immutable verifier;
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
    mapping(bytes32 requestId => string id) internal names;
    mapping(bytes32 requestId => uint256 count) public settlements;
    string public violation; // empty while every check holds

    constructor(
        OrbitWatchEscrow escrow_,
        TestUSD usd_,
        IEAS eas_,
        address platform_,
        address verifier_
    ) {
        escrow = escrow_;
        usd = usd_;
        eas = eas_;
        platform = platform_;
        verifier = verifier_;
        for (uint256 i; i < requesters.length; ++i) {
            usd.mint(requesters[i], START_BALANCE);
            minted += START_BALANCE;
            vm.prank(requesters[i]);
            usd.approve(address(escrow), type(uint256).max);
        }
    }

    function reviewersInPool() external view returns (address[4] memory) {
        return reviewerPool;
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
        string memory name = string.concat("SIM-REQ-", vm.toString(keys.length));
        bytes32 id = keccak256(bytes(name));
        vm.prank(requesters[who % requesters.length]);
        escrow.fund(id, terms, OrbitWatchEscrow.Split(observer, reviewer, fee));
        keys.push(id);
        names[id] = name;
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
        escrow.deliver(id, _delivery(id));
    }

    function verify(uint256 k, uint256 verdict) external {
        (bytes32 id, bool found) = _pick(k);
        if (!found || escrow.statusOf(id) != OrbitWatchEscrow.Status.Delivered) return;
        string[3] memory verdicts = ["pass", "fail", "inconclusive"];
        AttestationRequest memory request = _resultRequest(id, verdicts[verdict % 3]);
        vm.prank(verifier);
        eas.attest(request);
    }

    function challenge(uint256 k, bool byRequester) external {
        (bytes32 id, bool found) = _pick(k);
        if (!found || escrow.statusOf(id) != OrbitWatchEscrow.Status.ChallengePeriod) return;
        OrbitWatchEscrow.Request memory r = escrow.getRequest(id);
        vm.prank(byRequester ? r.requester : r.station);
        escrow.challenge(id, keccak256("reason"));
    }

    function vote(uint256 k, uint256 which, bool approve) external {
        (bytes32 id, bool found) = _pick(k);
        if (!found || escrow.statusOf(id) != OrbitWatchEscrow.Status.InReview) return;
        OrbitWatchEscrow.Request memory r = escrow.getRequest(id);
        uint256 i = which % 3;
        if (r.voted & (uint256(1) << i) != 0) return;
        AttestationRequest memory request = _voteRequest(id, approve);
        vm.prank(r.reviewers[i]);
        eas.attest(request);
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

    /// @dev A stranger tries everything that could move someone else's money or decide a
    /// request: withdraw, cancel, deliver, attest a result and vote.
    function strangerTries(uint256 k) external {
        (bytes32 id, bool found) = _pick(k);
        vm.prank(stranger);
        try escrow.withdraw() {
            _fail("a stranger withdrew");
        } catch {}
        if (!found) return;
        vm.prank(stranger);
        try escrow.cancel(id) {
            _fail("a stranger cancelled");
        } catch {}
        vm.prank(stranger);
        try escrow.deliver(id, keccak256("forged")) {
            _fail("a stranger delivered");
        } catch {}
        AttestationRequest memory result = _resultRequest(id, "pass");
        vm.prank(stranger);
        try eas.attest(result) {
            _fail("a stranger attested a result");
        } catch {}
        AttestationRequest memory ballot = _voteRequest(id, true);
        vm.prank(stranger);
        try eas.attest(ballot) {
            _fail("a stranger voted");
        } catch {}
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
        uint256 votes;
        for (uint256 i; i < 3; ++i) {
            if (r.voted & (uint256(1) << i) != 0) ++votes;
        }
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

    function _delivery(bytes32 id) internal pure returns (bytes32) {
        return keccak256(abi.encode("delivery", id));
    }

    function _resultRequest(bytes32 id, string memory verdict)
        internal
        view
        returns (AttestationRequest memory)
    {
        bytes memory data =
            abi.encode(names[id], _delivery(id), keccak256("report"), verdict, "method", "1");
        return _request(escrow.resultSchemaUid(), id, bytes32(0), data);
    }

    function _voteRequest(bytes32 id, bool approve)
        internal
        view
        returns (AttestationRequest memory)
    {
        bytes memory data = abi.encode(names[id], _delivery(id), approve, keccak256("reason"));
        return _request(escrow.voteSchemaUid(), id, escrow.getRequest(id).resultAttestation, data);
    }

    function _request(bytes32 schema, bytes32 id, bytes32 refUid, bytes memory data)
        internal
        view
        returns (AttestationRequest memory)
    {
        return AttestationRequest({
            schema: schema,
            data: AttestationRequestData({
                recipient: escrow.getRequest(id).station,
                expirationTime: 0,
                revocable: false,
                refUID: refUid,
                data: data,
                value: 0
            })
        });
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
contract OrbitWatchEscrowInvariantTest is StdInvariant, BaseSepoliaEas {
    TestUSD internal usd;
    OrbitWatchEscrow internal escrow;
    EscrowHandler internal handler;

    function setUp() public {
        IEAS eas = _installEas();
        usd = new TestUSD();
        OrbitWatchReviewerRegistry registry =
            new OrbitWatchReviewerRegistry(address(this), new address[](0));
        escrow =
            new OrbitWatchEscrow(usd, makeAddr("platform"), eas, registry, makeAddr("verifier"));
        handler = new EscrowHandler(escrow, usd, eas, makeAddr("platform"), makeAddr("verifier"));
        address[4] memory pool = handler.reviewersInPool();
        for (uint256 i; i < pool.length; ++i) {
            registry.addReviewer(pool[i]);
        }
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
    /// more or less than they were owed, and the stranger moved no money and decided nothing.
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

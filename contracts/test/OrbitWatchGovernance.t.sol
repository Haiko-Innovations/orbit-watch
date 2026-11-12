// SPDX-License-Identifier: Apache-2.0
pragma solidity 0.8.38;

import {Ownable} from "@openzeppelin/contracts/access/Ownable.sol";
import {IAccessControl} from "@openzeppelin/contracts/access/IAccessControl.sol";
import {TimelockController} from "@openzeppelin/contracts/governance/TimelockController.sol";
import {IEAS, AttestationRequest, AttestationRequestData} from "eas-contracts/IEAS.sol";
import {OrbitWatchEscrow} from "../src/OrbitWatchEscrow.sol";
import {OrbitWatchReviewerRegistry} from "../src/OrbitWatchReviewerRegistry.sol";
import {ISafe} from "../script/ISafe.sol";
import {OrbitWatchGovernance} from "../script/OrbitWatchGovernance.sol";
import {BaseSepoliaEas} from "./helpers/BaseSepoliaEas.sol";
import {BaseSepoliaSafe} from "./helpers/BaseSepoliaSafe.sol";
import {TestUSD} from "./mocks/TestUSD.sol";

/// @dev Calls the library from a contract, so that `expectRevert` sees its revert.
contract GovernanceDeployer {
    function deploy(ISafe safe, address[] memory reviewers)
        external
        returns (TimelockController, OrbitWatchReviewerRegistry)
    {
        return OrbitWatchGovernance.deploy(safe, reviewers);
    }
}

/// @notice The reviewer registry changes only through the Safe 2-of-3 multisig and the 48-hour
/// timelock (decisions P2-07 and D-21). Runs against the canonical Safe 1.4.1 code.
contract OrbitWatchGovernanceTest is BaseSepoliaSafe {
    uint256 internal constant DELAY = 48 hours;
    bytes32 internal constant SALT = keccak256("orbit-watch");

    address internal signerA;
    address internal signerB;
    address internal signerC;
    uint256 internal keyA;
    uint256 internal keyB;
    uint256 internal keyC;

    address internal r1 = makeAddr("reviewer 1");
    address internal r2 = makeAddr("reviewer 2");
    address internal r3 = makeAddr("reviewer 3");
    address internal r4 = makeAddr("reviewer 4");
    address internal station = makeAddr("station");
    address internal stranger = makeAddr("stranger");

    ISafe internal safe;
    TimelockController internal timelock;
    OrbitWatchReviewerRegistry internal registry;
    GovernanceDeployer internal deployer;

    function setUp() public {
        _installSafe();
        (signerA, keyA) = makeAddrAndKey("signer A (test key)");
        (signerB, keyB) = makeAddrAndKey("signer B (test key)");
        (signerC, keyC) = makeAddrAndKey("signer C (test key)");
        safe = _createSafe(_three(signerA, signerB, signerC), 2);
        deployer = new GovernanceDeployer();
        (timelock, registry) = deployer.deploy(safe, _three(r1, r2, r3));
    }

    // ------------------------------------------------------------------ the set-up

    function test_TheSetUpIsTheDecidedOne() public view {
        assertEq(safe.VERSION(), "1.4.1");
        assertEq(safe.getThreshold(), 2);
        assertEq(safe.getOwners().length, 3);

        assertEq(timelock.getMinDelay(), DELAY);
        assertTrue(timelock.hasRole(timelock.PROPOSER_ROLE(), address(safe)));
        assertTrue(timelock.hasRole(timelock.CANCELLER_ROLE(), address(safe)));
        assertTrue(timelock.hasRole(timelock.EXECUTOR_ROLE(), address(0))); // anyone executes
        // No administrator: only the timelock itself can change its roles.
        bytes32 admin = timelock.DEFAULT_ADMIN_ROLE();
        assertTrue(timelock.hasRole(admin, address(timelock)));
        assertFalse(timelock.hasRole(admin, address(safe)));
        // Nobody but the Safe proposes: not the deployer, not a signer alone.
        address[5] memory others = [address(deployer), address(this), signerA, signerB, signerC];
        for (uint256 i; i < others.length; ++i) {
            assertFalse(timelock.hasRole(admin, others[i]));
            assertFalse(timelock.hasRole(timelock.PROPOSER_ROLE(), others[i]));
            assertFalse(timelock.hasRole(timelock.CANCELLER_ROLE(), others[i]));
        }

        assertEq(registry.owner(), address(timelock));
        assertEq(registry.pendingOwner(), address(0));
        assertEq(registry.reviewers().length, 3);
        assertTrue(registry.isReviewer(r1) && registry.isReviewer(r2) && registry.isReviewer(r3));
    }

    function test_OnlyATwoOfThreeSafeIsAccepted() public {
        address[] memory none = new address[](0);
        ISafe oneOfThree = _createSafe(_three(signerA, signerB, signerC), 1);
        vm.expectRevert(
            abi.encodeWithSelector(
                OrbitWatchGovernance.NotATwoOfThreeSafe.selector, address(oneOfThree)
            )
        );
        deployer.deploy(oneOfThree, none);
        vm.expectRevert(
            abi.encodeWithSelector(OrbitWatchGovernance.NotATwoOfThreeSafe.selector, stranger)
        );
        deployer.deploy(ISafe(stranger), none);
    }

    // ------------------------------------------------------------------ the way that works

    function test_AddingAReviewerTakesTwoSignersAndFortyEightHours() public {
        bytes memory call = abi.encodeCall(OrbitWatchReviewerRegistry.addReviewer, (r4));
        bytes32 id = _propose(call, _keys(keyA, keyC));
        assertTrue(timelock.isOperationPending(id));
        assertEq(timelock.getTimestamp(id), vm.getBlockTimestamp() + DELAY);

        // Public for 48 hours: nobody can carry it out before that.
        vm.expectRevert(
            abi.encodeWithSelector(
                TimelockController.TimelockUnexpectedOperationState.selector,
                id,
                bytes32(1 << uint8(TimelockController.OperationState.Ready))
            )
        );
        timelock.execute(address(registry), 0, call, bytes32(0), SALT);
        skip(DELAY - 1);
        assertFalse(timelock.isOperationReady(id));
        skip(1);
        assertTrue(timelock.isOperationReady(id));

        vm.prank(stranger); // anyone may carry out a change whose delay has passed
        timelock.execute(address(registry), 0, call, bytes32(0), SALT);
        assertTrue(registry.isReviewer(r4));
        assertTrue(timelock.isOperationDone(id));
    }

    function test_RemovingAReviewerAndDeclaringAffiliationsGoTheSameWay() public {
        bytes memory remove = abi.encodeCall(OrbitWatchReviewerRegistry.removeReviewer, (r2));
        bytes memory affiliate =
            abi.encodeCall(OrbitWatchReviewerRegistry.setAffiliation, (r1, station, true));
        _propose(remove, _keys(keyB, keyC));
        _propose(affiliate, _keys(keyA, keyB));
        skip(DELAY);
        timelock.execute(address(registry), 0, remove, bytes32(0), SALT);
        timelock.execute(address(registry), 0, affiliate, bytes32(0), SALT);
        assertFalse(registry.isReviewer(r2));
        assertTrue(registry.isAffiliated(r1, station));
    }

    function test_TheSafeCanCancelAPendingChange() public {
        bytes memory call = abi.encodeCall(OrbitWatchReviewerRegistry.addReviewer, (r4));
        bytes32 id = _propose(call, _keys(keyA, keyB));
        _execFromSafe(
            safe,
            address(timelock),
            abi.encodeCall(TimelockController.cancel, (id)),
            _keys(keyB, keyC)
        );
        assertFalse(timelock.isOperation(id));
        skip(DELAY);
        vm.expectRevert();
        timelock.execute(address(registry), 0, call, bytes32(0), SALT);
        assertFalse(registry.isReviewer(r4));
    }

    // ------------------------------------------------------------------ every other way fails

    function test_OneSignatureIsNotEnough() public {
        bytes memory schedule =
            _scheduleCall(abi.encodeCall(OrbitWatchReviewerRegistry.addReviewer, (r4)), DELAY);
        // Safe 1.4.1 error GS020: not enough signatures for the threshold.
        _execFromSafe(safe, address(timelock), schedule, _keys(keyA), bytes("GS020"));
    }

    function test_NoSignerAloneAndNobodyElseCanChangeTheRegistry() public {
        address[5] memory callers =
            [signerA, address(safe), address(deployer), address(this), stranger];
        for (uint256 i; i < callers.length; ++i) {
            vm.prank(callers[i]);
            vm.expectRevert(
                abi.encodeWithSelector(Ownable.OwnableUnauthorizedAccount.selector, callers[i])
            );
            registry.addReviewer(stranger);
        }
        // A signer cannot go to the timelock alone either.
        bytes32 proposer = timelock.PROPOSER_ROLE(); // read before the prank
        vm.prank(signerA);
        vm.expectRevert(
            abi.encodeWithSelector(
                IAccessControl.AccessControlUnauthorizedAccount.selector, signerA, proposer
            )
        );
        timelock.schedule(
            address(registry),
            0,
            abi.encodeCall(OrbitWatchReviewerRegistry.addReviewer, (stranger)),
            bytes32(0),
            SALT,
            DELAY
        );
    }

    function test_AShorterDelayIsRefused() public {
        bytes memory call = abi.encodeCall(OrbitWatchReviewerRegistry.addReviewer, (r4));
        vm.prank(address(safe));
        vm.expectRevert(
            abi.encodeWithSelector(
                TimelockController.TimelockInsufficientDelay.selector, DELAY - 1, DELAY
            )
        );
        timelock.schedule(address(registry), 0, call, bytes32(0), SALT, DELAY - 1);
    }

    function test_TheDelayAndTheRolesChangeOnlyThroughTheTimelock() public {
        vm.prank(address(safe));
        vm.expectRevert(
            abi.encodeWithSelector(
                TimelockController.TimelockUnauthorizedCaller.selector, address(safe)
            )
        );
        timelock.updateDelay(1 hours);

        bytes32 admin = timelock.DEFAULT_ADMIN_ROLE();
        bytes32 proposer = timelock.PROPOSER_ROLE();
        vm.prank(address(safe));
        vm.expectRevert(
            abi.encodeWithSelector(
                IAccessControl.AccessControlUnauthorizedAccount.selector, address(safe), admin
            )
        );
        timelock.grantRole(proposer, stranger);

        // Through the Safe and the timelock it works, after 48 public hours.
        bytes memory shorter = abi.encodeCall(TimelockController.updateDelay, (24 hours));
        _execFromSafe(
            safe,
            address(timelock),
            abi.encodeCall(
                TimelockController.schedule,
                (address(timelock), 0, shorter, bytes32(0), SALT, DELAY)
            ),
            _keys(keyA, keyB)
        );
        skip(DELAY);
        timelock.execute(address(timelock), 0, shorter, bytes32(0), SALT);
        assertEq(timelock.getMinDelay(), 24 hours);
    }

    function test_OwnershipCanOnlyMoveThroughTheTimelock() public {
        vm.prank(signerA);
        vm.expectRevert(
            abi.encodeWithSelector(Ownable.OwnableUnauthorizedAccount.selector, signerA)
        );
        registry.transferOwnership(signerA);
        vm.prank(address(safe));
        vm.expectRevert(
            abi.encodeWithSelector(Ownable.OwnableUnauthorizedAccount.selector, address(safe))
        );
        registry.renounceOwnership();
    }

    // ------------------------------------------------------------------ helpers

    /// @dev The Safe schedules `call` on the registry through the timelock, signed by `keys`.
    function _propose(bytes memory call, uint256[] memory keys) internal returns (bytes32 id) {
        _execFromSafe(safe, address(timelock), _scheduleCall(call, DELAY), keys);
        return timelock.hashOperation(address(registry), 0, call, bytes32(0), SALT);
    }

    function _scheduleCall(bytes memory call, uint256 delay) internal view returns (bytes memory) {
        return abi.encodeCall(
            TimelockController.schedule, (address(registry), 0, call, bytes32(0), SALT, delay)
        );
    }

    function _three(address a, address b, address c) internal pure returns (address[] memory list) {
        list = new address[](3);
        (list[0], list[1], list[2]) = (a, b, c);
    }

    function _keys(uint256 a) internal pure returns (uint256[] memory list) {
        list = new uint256[](1);
        list[0] = a;
    }

    function _keys(uint256 a, uint256 b) internal pure returns (uint256[] memory list) {
        list = new uint256[](2);
        (list[0], list[1]) = (a, b);
    }
}

/// @notice End to end: a reviewer list changed through the Safe and the timelock is the one
/// the escrow chooses its next round from.
contract OrbitWatchGovernanceEndToEndTest is BaseSepoliaSafe, BaseSepoliaEas {
    string internal constant ID = "SIM-REQ-GOV";
    bytes32 internal constant DELIVERY = keccak256("observations");

    IEAS internal eas;
    ISafe internal safe;
    TimelockController internal timelock;
    OrbitWatchReviewerRegistry internal registry;
    OrbitWatchEscrow internal escrow;
    TestUSD internal usd;
    uint256[] internal keys;
    address internal r1 = makeAddr("reviewer 1");
    address internal r4 = makeAddr("reviewer 4");
    address internal requester = makeAddr("requester");
    address internal station = makeAddr("station");
    address internal verifier = makeAddr("verifier");

    function setUp() public {
        _installSafe();
        eas = _installEas();
        (address a, uint256 keyA) = makeAddrAndKey("signer A (test key)");
        (address b, uint256 keyB) = makeAddrAndKey("signer B (test key)");
        keys.push(keyA);
        keys.push(keyB);
        address[] memory signers = new address[](3);
        (signers[0], signers[1], signers[2]) = (a, b, makeAddr("signer C (test key)"));
        safe = _createSafe(signers, 2);
        address[] memory initial = new address[](3);
        (initial[0], initial[1], initial[2]) = (r1, makeAddr("reviewer 2"), makeAddr("reviewer 3"));
        (timelock, registry) = new GovernanceDeployer().deploy(safe, initial);
        usd = new TestUSD();
        escrow = new OrbitWatchEscrow(usd, makeAddr("platform"), eas, registry, verifier);
    }

    function test_AGovernedChangeReachesTheNextRound() public {
        _replaceReviewer1WithReviewer4();
        bytes32 id = _deliveredAndChallenged();
        address[3] memory round = escrow.getRequest(id).reviewers;
        for (uint256 i; i < 3; ++i) {
            assertTrue(round[i] != r1, "a removed reviewer was chosen");
            assertTrue(registry.isReviewer(round[i]));
        }
    }

    /// @dev One batch: two signers, then 48 public hours.
    function _replaceReviewer1WithReviewer4() internal {
        address[] memory targets = new address[](2);
        (targets[0], targets[1]) = (address(registry), address(registry));
        bytes[] memory calls = new bytes[](2);
        calls[0] = abi.encodeCall(OrbitWatchReviewerRegistry.removeReviewer, (r1));
        calls[1] = abi.encodeCall(OrbitWatchReviewerRegistry.addReviewer, (r4));
        uint256[] memory values = new uint256[](2);
        _execFromSafe(
            safe,
            address(timelock),
            abi.encodeCall(
                TimelockController.scheduleBatch,
                (targets, values, calls, bytes32(0), bytes32(0), 48 hours)
            ),
            keys
        );
        skip(48 hours);
        timelock.executeBatch(targets, values, calls, bytes32(0), bytes32(0));
    }

    function _deliveredAndChallenged() internal returns (bytes32 id) {
        id = keccak256(bytes(ID));
        usd.mint(requester, 135);
        OrbitWatchEscrow.Terms memory terms = OrbitWatchEscrow.Terms(
            keccak256("terms"),
            uint64(vm.getBlockTimestamp() + 3 days),
            6 hours,
            1 days,
            1 days,
            2 days
        );
        vm.startPrank(requester);
        usd.approve(address(escrow), 135);
        escrow.fund(id, terms, OrbitWatchEscrow.Split(100, 10, 5));
        vm.stopPrank();
        vm.startPrank(station);
        escrow.reserve(id);
        escrow.deliver(id, DELIVERY);
        vm.stopPrank();
        AttestationRequest memory result = AttestationRequest({
            schema: escrow.resultSchemaUid(),
            data: AttestationRequestData({
                recipient: station,
                expirationTime: 0,
                revocable: false,
                refUID: bytes32(0),
                data: abi.encode(ID, DELIVERY, keccak256("report"), "pass", "m", "1"),
                value: 0
            })
        });
        vm.prank(verifier);
        eas.attest(result);
        vm.prank(requester);
        escrow.challenge(id, keccak256("reason"));
    }
}

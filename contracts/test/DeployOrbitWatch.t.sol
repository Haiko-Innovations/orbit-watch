// SPDX-License-Identifier: Apache-2.0
pragma solidity 0.8.38;

import {TimelockController} from "@openzeppelin/contracts/governance/TimelockController.sol";
import {ISchemaRegistry, SchemaRecord} from "eas-contracts/ISchemaRegistry.sol";
import {OrbitWatchReviewerRegistry} from "../src/OrbitWatchReviewerRegistry.sol";
import {DeployOrbitWatch} from "../script/DeployOrbitWatch.s.sol";
import {ISafe} from "../script/ISafe.sol";
import {BaseSepoliaEas} from "./helpers/BaseSepoliaEas.sol";
import {BaseSepoliaSafe} from "./helpers/BaseSepoliaSafe.sol";
import {TestUSD} from "./mocks/TestUSD.sol";

/// @notice The deployment script (phase 2, step 2.7; decision D-24) against the canonical
/// Safe 1.4.1 and EAS code of Base Sepolia, with test keys and a worthless local token.
contract DeployOrbitWatchTest is BaseSepoliaSafe, BaseSepoliaEas {
    uint256 internal constant DELAY = 48 hours;
    address internal constant BASE_SEPOLIA_USDC = 0x036CbD53842c5426634e7929541eC2318f3dCF7e;

    DeployOrbitWatch internal script;
    TestUSD internal usd;
    address internal signerA;
    address internal signerB;
    address internal signerC;
    uint256 internal keyA;
    uint256 internal keyB;
    uint256 internal keyC;
    address internal verifier = makeAddr("verifier");
    address internal newSigner = makeAddr("new signer");
    address[] internal reviewers;

    function setUp() public {
        _installSafe();
        _installEas();
        usd = new TestUSD();
        script = new DeployOrbitWatch();
        (signerA, keyA) = makeAddrAndKey("signer A (test key)");
        (signerB, keyB) = makeAddrAndKey("signer B (test key)");
        (signerC, keyC) = makeAddrAndKey("signer C (test key)");
        for (uint256 i; i < 4; ++i) {
            reviewers.push(makeAddr(string.concat("reviewer ", vm.toString(i))));
        }
    }

    function _settings() internal view returns (DeployOrbitWatch.Settings memory s) {
        s.signers = new address[](3);
        (s.signers[0], s.signers[1], s.signers[2]) = (signerA, signerB, signerC);
        s.reviewers = reviewers;
        s.verifier = verifier;
        s.feeToSafe = true;
        s.token = usd;
    }

    // ------------------------------------------------------------------ the set-up

    function test_DeploysTheDecidedSetUp() public {
        DeployOrbitWatch.Settings memory s = _settings();
        DeployOrbitWatch.Deployment memory d = script.deploy(s);
        script.checkDeployment(d, s, address(script));
        script.checkDeployment(d, s, address(this));

        assertEq(d.safe.VERSION(), "1.4.1");
        assertEq(d.safe.getThreshold(), 2);
        assertEq(d.timelock.getMinDelay(), DELAY);
        assertEq(d.registry.owner(), address(d.timelock));
        assertEq(d.registry.reviewers().length, 4);
        assertEq(d.escrow.version(), "1.0.0");
        assertEq(d.escrow.feeRecipient(), address(d.safe));
        assertEq(d.escrow.verifier(), verifier);
        assertEq(address(d.escrow.token()), address(usd));
        assertEq(address(d.escrow.registry()), address(d.registry));

        // The escrow registered both schemas, non-revocable, with itself as the resolver.
        ISchemaRegistry schemas = d.escrow.eas().getSchemaRegistry();
        bytes32[2] memory uids = [d.escrow.resultSchemaUid(), d.escrow.voteSchemaUid()];
        for (uint256 i; i < 2; ++i) {
            SchemaRecord memory schema = schemas.getSchema(uids[i]);
            assertEq(schema.uid, uids[i]);
            assertEq(address(schema.resolver), address(d.escrow));
            assertFalse(schema.revocable);
        }
    }

    function test_AnotherFeeRecipientOrNone() public {
        DeployOrbitWatch.Settings memory s = _settings();
        s.feeToSafe = false;
        DeployOrbitWatch.Deployment memory d = script.deploy(s);
        assertEq(d.escrow.feeRecipient(), address(0)); // no platform fees
        script.checkDeployment(d, s, address(script));
    }

    function test_TheSafeChangesTheReviewersThroughTheTimelock() public {
        DeployOrbitWatch.Deployment memory d = script.deploy(_settings());
        address added = makeAddr("added reviewer");
        bytes memory call = abi.encodeCall(OrbitWatchReviewerRegistry.addReviewer, (added));
        bytes memory schedule = abi.encodeCall(
            TimelockController.schedule,
            (address(d.registry), 0, call, bytes32(0), bytes32(0), DELAY)
        );
        _execFromSafe(d.safe, address(d.timelock), schedule, _keys(keyA, keyB));
        skip(DELAY);
        d.timelock.execute(address(d.registry), 0, call, bytes32(0), bytes32(0));
        assertTrue(d.registry.isReviewer(added));
    }

    /// The testnet keys are one maintainer's (D-24); the Safe itself can hand them to three
    /// people later, two signers approving, without a new deployment.
    function test_TheSignersCanBeReplacedWithoutANewDeployment() public {
        DeployOrbitWatch.Deployment memory d = script.deploy(_settings());
        address[] memory owners = d.safe.getOwners();
        // Safe owners form a linked list; the sentinel 0x1 precedes the first one.
        bytes memory swap = abi.encodeCall(ISafe.swapOwner, (address(0x1), owners[0], newSigner));
        _execFromSafe(d.safe, address(d.safe), swap, _keys(keyB, keyC));
        assertTrue(d.safe.isOwner(newSigner));
        assertFalse(d.safe.isOwner(owners[0]));
        assertEq(d.safe.getThreshold(), 2);
        // The timelock is unchanged: the Safe, not its signers, proposes.
        assertTrue(d.timelock.hasRole(d.timelock.PROPOSER_ROLE(), address(d.safe)));
    }

    // ------------------------------------------------------------------ refusals

    function test_RefusesOtherChains() public {
        DeployOrbitWatch.Settings memory s = _settings();
        vm.chainId(1);
        vm.expectRevert(abi.encodeWithSelector(DeployOrbitWatch.UnsupportedChain.selector, 1));
        script.deploy(s);
    }

    function test_OnBaseSepoliaOnlyCirclesTestnetUsdc() public {
        DeployOrbitWatch.Settings memory s = _settings();
        vm.chainId(84_532);
        vm.expectRevert(
            abi.encodeWithSelector(DeployOrbitWatch.NotTheTestnetUsdc.selector, address(usd))
        );
        script.deploy(s);
    }

    function test_RefusesSafeCodeThatIsNotTheCanonicalOne() public {
        DeployOrbitWatch.Settings memory s = _settings();
        address singleton = 0x29fcB43b46531BcA003ddC8FCB67FFE91900C762;
        vm.etch(singleton, hex"00");
        vm.expectRevert(
            abi.encodeWithSelector(DeployOrbitWatch.NotTheCanonicalSafe.selector, singleton)
        );
        script.deploy(s);
    }

    function test_RefusesBadSettings() public {
        DeployOrbitWatch.Settings memory s = _settings();
        s.signers = new address[](2);
        (s.signers[0], s.signers[1]) = (signerA, signerB);
        _expectInvalid("three Safe signers");
        script.deploy(s);

        s = _settings();
        s.signers[2] = signerA;
        _expectInvalid("distinct signers");
        script.deploy(s);

        s = _settings();
        s.signers[1] = verifier;
        _expectInvalid("distinct signers, none of them the verifier");
        script.deploy(s);

        s = _settings();
        s.reviewers = new address[](2);
        (s.reviewers[0], s.reviewers[1]) = (reviewers[0], reviewers[1]);
        _expectInvalid("at least three reviewers");
        script.deploy(s);

        s = _settings();
        s.reviewers[3] = verifier;
        _expectInvalid("the verifier is not a reviewer");
        script.deploy(s);

        s = _settings();
        s.verifier = address(0);
        _expectInvalid("a verifier");
        script.deploy(s);

        s = _settings();
        s.feeToSafe = false;
        s.feeRecipient = address(usd);
        _expectInvalid("the fee recipient is the Safe, an account or zero");
        script.deploy(s);
    }

    function test_CheckFindsADifferentSetUp() public {
        DeployOrbitWatch.Settings memory s = _settings();
        DeployOrbitWatch.Deployment memory d = script.deploy(s);
        s.verifier = makeAddr("someone else");
        vm.expectRevert(
            abi.encodeWithSelector(DeployOrbitWatch.NotAsRecorded.selector, "escrow verifier")
        );
        script.checkDeployment(d, s, address(script));
    }

    // ------------------------------------------------------------------ the committed settings

    function test_TheBaseSepoliaSettingsAreComplete() public view {
        string memory path =
            string.concat(vm.projectRoot(), "/deployments/base-sepolia.settings.json");
        DeployOrbitWatch.Settings memory s = script.readSettings(vm.readFile(path));
        assertEq(s.signers.length, 3);
        assertGe(s.reviewers.length, 3);
        assertTrue(s.feeToSafe);
        assertEq(address(s.token), BASE_SEPOLIA_USDC);
        assertTrue(s.verifier != address(0));
    }

    // ------------------------------------------------------------------ helpers

    function _expectInvalid(string memory reason) internal {
        vm.expectRevert(abi.encodeWithSelector(DeployOrbitWatch.InvalidSettings.selector, reason));
    }

    function _keys(uint256 a, uint256 b) internal pure returns (uint256[] memory keys) {
        keys = new uint256[](2);
        (keys[0], keys[1]) = (a, b);
    }
}

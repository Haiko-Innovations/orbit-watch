// SPDX-License-Identifier: Apache-2.0
pragma solidity 0.8.38;

import {Script} from "forge-std/Script.sol";
import {IERC20} from "@openzeppelin/contracts/token/ERC20/IERC20.sol";
import {TimelockController} from "@openzeppelin/contracts/governance/TimelockController.sol";
import {IEAS} from "eas-contracts/IEAS.sol";
import {OrbitWatchEscrow} from "../src/OrbitWatchEscrow.sol";
import {OrbitWatchReviewerRegistry} from "../src/OrbitWatchReviewerRegistry.sol";
import {ISafe, ISafeProxyFactory} from "./ISafe.sol";
import {OrbitWatchGovernance} from "./OrbitWatchGovernance.sol";

/// @title Orbit Watch deployment (phase 2, step 2.7; decision D-24)
/// @notice Deploys the Orbit Watch contracts on the Base Sepolia TESTNET (or a local Anvil
/// chain), in this order:
/// 1. a Safe 1.4.1 account with three signers and a threshold of two, from the canonical
///    Safe proxy factory;
/// 2. the 48-hour timelock and the reviewer registry it owns (`OrbitWatchGovernance`, the
///    same function the tests use);
/// 3. the escrow, which registers its two EAS schemas itself.
/// The deployer keeps no privilege: the escrow has no owner, the registry belongs to the
/// timelock and the timelock to itself.
///
/// Settings come from a JSON file (`ORBIT_WATCH_DEPLOY_SETTINGS`); the deployment record is
/// written to `ORBIT_WATCH_DEPLOY_RECORD`. `check(record)` reads a record back and checks the
/// deployed contracts against it on chain. See docs/base-sepolia.md.
contract DeployOrbitWatch is Script {
    uint256 internal constant BASE_SEPOLIA = 84_532;
    uint256 internal constant ANVIL = 31_337;

    // Canonical Safe 1.4.1 (safe-deployments, also on Base Sepolia; test/fixtures/base-sepolia-safe).
    address internal constant SAFE_L2_SINGLETON = 0x29fcB43b46531BcA003ddC8FCB67FFE91900C762;
    address internal constant SAFE_PROXY_FACTORY = 0x4e1DCf7AD4e460CfD30791CCC4F9c8a4f820ec67;
    bytes32 internal constant SAFE_L2_CODEHASH =
        0xb1f926978a0f44a2c0ec8fe822418ae969bd8c3f18d61e5103100339894f81ff;
    bytes32 internal constant SAFE_PROXY_FACTORY_CODEHASH =
        0x50c3cdc4074750a7a974204a716c999edd37482f907608d960b2b025ee0b3317;
    // EAS predeploy of OP Stack chains such as Base Sepolia.
    address internal constant EAS_PREDEPLOY = 0x4200000000000000000000000000000000000021;
    // Circle's testnet USDC on Base Sepolia (developers.circle.com, USDC contract addresses).
    address internal constant BASE_SEPOLIA_USDC = 0x036CbD53842c5426634e7929541eC2318f3dCF7e;

    uint256 internal constant SIGNERS = 3;
    uint256 internal constant THRESHOLD = 2;
    uint256 internal constant MIN_REVIEWERS = 3; // a round needs three

    struct Settings {
        address[] signers;
        address[] reviewers;
        address verifier;
        bool feeToSafe; // the platform fee goes to the Safe; otherwise to `feeRecipient`
        address feeRecipient;
        IERC20 token;
        uint256 safeSaltNonce;
    }

    struct Deployment {
        ISafe safe;
        TimelockController timelock;
        OrbitWatchReviewerRegistry registry;
        OrbitWatchEscrow escrow;
    }

    error UnsupportedChain(uint256 chainId);
    error NotTheCanonicalSafe(address target);
    error NoContract(address target);
    error NotTheTestnetUsdc(address token);
    error InvalidSettings(string reason);
    error NotAsRecorded(string what);

    // ------------------------------------------------------------------ deploy

    function run() external returns (Deployment memory d) {
        Settings memory s = readSettings(vm.readFile(vm.envString("ORBIT_WATCH_DEPLOY_SETTINGS")));
        uint256 fromBlock = block.number;
        vm.startBroadcast();
        (, address deployer,) = vm.readCallers(); // the broadcasting account
        d = deploy(s);
        vm.stopBroadcast();
        writeRecord(d, deployer, fromBlock, vm.envString("ORBIT_WATCH_DEPLOY_RECORD"));
    }

    /// @notice Checks the settings and the chain, then deploys. Used by `run` and the tests.
    function deploy(Settings memory s) public returns (Deployment memory d) {
        checkSettings(s);
        bytes memory setup = abi.encodeCall(
            ISafe.setup,
            (s.signers, THRESHOLD, address(0), "", address(0), address(0), 0, payable(address(0)))
        );
        d.safe = ISafe(
            ISafeProxyFactory(SAFE_PROXY_FACTORY)
                .createProxyWithNonce(SAFE_L2_SINGLETON, setup, s.safeSaltNonce)
        );
        (d.timelock, d.registry) = OrbitWatchGovernance.deploy(d.safe, s.reviewers);
        address feeRecipient = s.feeToSafe ? address(d.safe) : s.feeRecipient;
        d.escrow = new OrbitWatchEscrow(
            s.token, feeRecipient, IEAS(EAS_PREDEPLOY), d.registry, s.verifier
        );
    }

    function checkSettings(Settings memory s) public view {
        if (block.chainid != BASE_SEPOLIA && block.chainid != ANVIL) {
            revert UnsupportedChain(block.chainid);
        }
        if (SAFE_L2_SINGLETON.codehash != SAFE_L2_CODEHASH) {
            revert NotTheCanonicalSafe(SAFE_L2_SINGLETON);
        }
        if (SAFE_PROXY_FACTORY.codehash != SAFE_PROXY_FACTORY_CODEHASH) {
            revert NotTheCanonicalSafe(SAFE_PROXY_FACTORY);
        }
        if (EAS_PREDEPLOY.code.length == 0) revert NoContract(EAS_PREDEPLOY);
        if (address(s.token).code.length == 0) revert NoContract(address(s.token));
        if (block.chainid == BASE_SEPOLIA && address(s.token) != BASE_SEPOLIA_USDC) {
            revert NotTheTestnetUsdc(address(s.token));
        }
        if (s.signers.length != SIGNERS) revert InvalidSettings("three Safe signers");
        if (s.reviewers.length < MIN_REVIEWERS) revert InvalidSettings("at least three reviewers");
        if (s.verifier == address(0)) revert InvalidSettings("a verifier");
        if (!s.feeToSafe && s.feeRecipient != address(0) && s.feeRecipient.code.length > 0) {
            // A contract other than the Safe might be unable to withdraw its fees.
            revert InvalidSettings("the fee recipient is the Safe, an account or zero");
        }
        for (uint256 i; i < s.signers.length; ++i) {
            if (s.signers[i] == address(0) || s.signers[i] == s.verifier) {
                revert InvalidSettings("distinct signers, none of them the verifier");
            }
            for (uint256 j = i + 1; j < s.signers.length; ++j) {
                if (s.signers[i] == s.signers[j]) revert InvalidSettings("distinct signers");
            }
        }
        for (uint256 i; i < s.reviewers.length; ++i) {
            if (s.reviewers[i] == s.verifier) {
                revert InvalidSettings("the verifier is not a reviewer");
            }
        }
    }

    // ------------------------------------------------------------------ settings and record

    /// @notice Parses the settings file, for example deployments/base-sepolia.settings.json.
    function readSettings(string memory json) public pure returns (Settings memory s) {
        s.signers = vm.parseJsonAddressArray(json, ".safe_signers");
        s.reviewers = vm.parseJsonAddressArray(json, ".reviewers");
        s.verifier = vm.parseJsonAddress(json, ".verifier");
        string memory fee = vm.parseJsonString(json, ".fee_recipient");
        s.feeToSafe = keccak256(bytes(fee)) == keccak256("safe");
        if (!s.feeToSafe) s.feeRecipient = vm.parseAddress(fee);
        s.token = IERC20(vm.parseJsonAddress(json, ".token"));
        s.safeSaltNonce = vm.parseJsonUint(json, ".safe_salt_nonce");
    }

    function writeRecord(
        Deployment memory d,
        address deployer,
        uint256 fromBlock,
        string memory path
    ) public {
        string memory k = "record";
        vm.serializeString(k, "network", block.chainid == BASE_SEPOLIA ? "base-sepolia" : "anvil");
        vm.serializeUint(k, "chain_id", block.chainid);
        vm.serializeUint(k, "from_block", fromBlock);
        vm.serializeAddress(k, "deployer", deployer);
        vm.serializeAddress(k, "escrow", address(d.escrow));
        vm.serializeString(k, "escrow_version", d.escrow.version());
        vm.serializeAddress(k, "registry", address(d.registry));
        vm.serializeAddress(k, "timelock", address(d.timelock));
        vm.serializeUint(k, "timelock_min_delay_seconds", d.timelock.getMinDelay());
        vm.serializeAddress(k, "safe", address(d.safe));
        vm.serializeAddress(k, "safe_signers", d.safe.getOwners());
        vm.serializeUint(k, "safe_threshold", d.safe.getThreshold());
        vm.serializeAddress(k, "reviewers", d.registry.reviewers());
        vm.serializeAddress(k, "verifier", d.escrow.verifier());
        vm.serializeAddress(k, "fee_recipient", d.escrow.feeRecipient());
        vm.serializeAddress(k, "token", address(d.escrow.token()));
        vm.serializeAddress(k, "eas", address(d.escrow.eas()));
        vm.serializeBytes32(k, "result_schema_uid", d.escrow.resultSchemaUid());
        string memory json = vm.serializeBytes32(k, "vote_schema_uid", d.escrow.voteSchemaUid());
        vm.writeJson(json, path);
    }

    // ------------------------------------------------------------------ check

    /// @notice Reads a deployment record and checks the contracts on chain against it:
    /// `forge script script/DeployOrbitWatch.s.sol --sig "check(string)" <record> --rpc-url …`
    function check(string memory path) external view {
        string memory json = vm.readFile(path);
        if (vm.parseJsonUint(json, ".chain_id") != block.chainid) revert NotAsRecorded("chain");
        Deployment memory d = Deployment({
            safe: ISafe(vm.parseJsonAddress(json, ".safe")),
            timelock: TimelockController(payable(vm.parseJsonAddress(json, ".timelock"))),
            registry: OrbitWatchReviewerRegistry(vm.parseJsonAddress(json, ".registry")),
            escrow: OrbitWatchEscrow(vm.parseJsonAddress(json, ".escrow"))
        });
        Settings memory s;
        s.signers = vm.parseJsonAddressArray(json, ".safe_signers");
        s.reviewers = vm.parseJsonAddressArray(json, ".reviewers");
        s.verifier = vm.parseJsonAddress(json, ".verifier");
        s.feeRecipient = vm.parseJsonAddress(json, ".fee_recipient");
        s.feeToSafe = s.feeRecipient == address(d.safe);
        s.token = IERC20(vm.parseJsonAddress(json, ".token"));
        checkDeployment(d, s, vm.parseJsonAddress(json, ".deployer"));
        if (d.escrow.resultSchemaUid() != vm.parseJsonBytes32(json, ".result_schema_uid")) {
            revert NotAsRecorded("result schema");
        }
        if (d.escrow.voteSchemaUid() != vm.parseJsonBytes32(json, ".vote_schema_uid")) {
            revert NotAsRecorded("vote schema");
        }
    }

    /// @notice The deployed set-up is the decided one (P2-05, P2-07, D-21, D-24), and the
    /// deployer kept no privilege.
    function checkDeployment(Deployment memory d, Settings memory s, address deployer) public view {
        // The Safe: canonical code, 2 of the 3 signers.
        if (address(d.safe).code.length == 0) revert NotAsRecorded("Safe");
        if (d.safe.getThreshold() != THRESHOLD) revert NotAsRecorded("Safe threshold");
        address[] memory owners = d.safe.getOwners();
        if (owners.length != s.signers.length) revert NotAsRecorded("Safe signers");
        for (uint256 i; i < s.signers.length; ++i) {
            if (!d.safe.isOwner(s.signers[i])) revert NotAsRecorded("Safe signers");
        }
        if (keccak256(bytes(d.safe.VERSION())) != keccak256("1.4.1")) {
            revert NotAsRecorded("Safe version");
        }
        // The timelock: 48 hours, the Safe its only proposer and canceller, anyone executes,
        // no administrator but itself.
        TimelockController t = d.timelock;
        if (t.getMinDelay() != OrbitWatchGovernance.MIN_DELAY) revert NotAsRecorded("delay");
        if (!t.hasRole(t.PROPOSER_ROLE(), address(d.safe))) revert NotAsRecorded("proposer");
        if (!t.hasRole(t.CANCELLER_ROLE(), address(d.safe))) revert NotAsRecorded("canceller");
        if (!t.hasRole(t.EXECUTOR_ROLE(), address(0))) revert NotAsRecorded("executor");
        if (!t.hasRole(t.DEFAULT_ADMIN_ROLE(), address(t))) revert NotAsRecorded("admin");
        _noRole(t, deployer);
        for (uint256 i; i < s.signers.length; ++i) {
            _noRole(t, s.signers[i]);
        }
        if (t.hasRole(t.DEFAULT_ADMIN_ROLE(), address(d.safe))) revert NotAsRecorded("admin");
        // The registry: owned by the timelock, with the reviewers.
        if (d.registry.owner() != address(t)) revert NotAsRecorded("registry owner");
        if (d.registry.pendingOwner() != address(0)) revert NotAsRecorded("registry owner");
        address[] memory reviewers = d.registry.reviewers();
        if (reviewers.length != s.reviewers.length) revert NotAsRecorded("reviewers");
        for (uint256 i; i < s.reviewers.length; ++i) {
            if (!d.registry.isReviewer(s.reviewers[i])) revert NotAsRecorded("reviewers");
        }
        // The escrow: no owner to check; its fixed settings.
        OrbitWatchEscrow e = d.escrow;
        if (address(e.registry()) != address(d.registry)) revert NotAsRecorded("escrow registry");
        if (address(e.token()) != address(s.token)) revert NotAsRecorded("escrow token");
        if (address(e.eas()) != EAS_PREDEPLOY) revert NotAsRecorded("escrow EAS");
        if (e.verifier() != s.verifier) revert NotAsRecorded("escrow verifier");
        address feeRecipient = s.feeToSafe ? address(d.safe) : s.feeRecipient;
        if (e.feeRecipient() != feeRecipient) revert NotAsRecorded("escrow fee recipient");
        if (keccak256(bytes(e.version())) != keccak256("1.0.0")) {
            revert NotAsRecorded("escrow version");
        }
    }

    function _noRole(TimelockController t, address who) private view {
        if (
            t.hasRole(t.DEFAULT_ADMIN_ROLE(), who) || t.hasRole(t.PROPOSER_ROLE(), who)
                || t.hasRole(t.CANCELLER_ROLE(), who)
        ) revert NotAsRecorded("a privilege outside the Safe");
    }
}

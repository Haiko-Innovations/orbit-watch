// SPDX-License-Identifier: Apache-2.0
pragma solidity 0.8.38;

import {Test} from "forge-std/Test.sol";
import {ISafe, ISafeProxyFactory} from "../../script/ISafe.sol";

/// @notice Installs the canonical Safe 1.4.1 code (from Base Sepolia, see
/// test/fixtures/base-sepolia-safe) and creates and drives Safe accounts with test keys.
abstract contract BaseSepoliaSafe is Test {
    address internal constant SAFE_L2_SINGLETON = 0x29fcB43b46531BcA003ddC8FCB67FFE91900C762;
    address internal constant SAFE_PROXY_FACTORY = 0x4e1DCf7AD4e460CfD30791CCC4F9c8a4f820ec67;
    bytes32 internal constant SAFE_L2_CODEHASH =
        0xb1f926978a0f44a2c0ec8fe822418ae969bd8c3f18d61e5103100339894f81ff;
    bytes32 internal constant SAFE_PROXY_FACTORY_CODEHASH =
        0x50c3cdc4074750a7a974204a716c999edd37482f907608d960b2b025ee0b3317;

    function _installSafe() internal {
        _etchSafeCode(SAFE_L2_SINGLETON, "safe-l2.runtime.hex", SAFE_L2_CODEHASH);
        _etchSafeCode(
            SAFE_PROXY_FACTORY, "safe-proxy-factory.runtime.hex", SAFE_PROXY_FACTORY_CODEHASH
        );
    }

    /// @dev A new Safe account with `owners` and `threshold`, as the Safe app would create it.
    function _createSafe(address[] memory owners, uint256 threshold) internal returns (ISafe) {
        bytes memory setup = abi.encodeCall(
            ISafe.setup,
            (owners, threshold, address(0), "", address(0), address(0), 0, payable(address(0)))
        );
        return ISafe(
            ISafeProxyFactory(SAFE_PROXY_FACTORY).createProxyWithNonce(SAFE_L2_SINGLETON, setup, 0)
        );
    }

    /// @dev Executes a call from `safe`, signed with `keys` (sorted by signer address, as the
    /// Safe requires).
    function _execFromSafe(ISafe safe, address to, bytes memory data, uint256[] memory keys)
        internal
    {
        _execFromSafe(safe, to, data, keys, "");
    }

    /// @dev The same, expecting the Safe to revert with `expectedRevert` (if not empty).
    function _execFromSafe(
        ISafe safe,
        address to,
        bytes memory data,
        uint256[] memory keys,
        bytes memory expectedRevert
    ) internal {
        bytes memory signatures = _sign(_safeTxHash(safe, to, data), keys);
        if (expectedRevert.length > 0) vm.expectRevert(expectedRevert);
        safe.execTransaction(to, 0, data, 0, 0, 0, 0, address(0), payable(address(0)), signatures);
    }

    function _safeTxHash(ISafe safe, address to, bytes memory data) private view returns (bytes32) {
        return
            safe.getTransactionHash(to, 0, data, 0, 0, 0, 0, address(0), address(0), safe.nonce());
    }

    function _sign(bytes32 hash, uint256[] memory keys) private pure returns (bytes memory out) {
        uint256[] memory sorted = _byAddress(keys);
        for (uint256 i; i < sorted.length; ++i) {
            (uint8 v, bytes32 r, bytes32 s) = vm.sign(sorted[i], hash);
            out = abi.encodePacked(out, r, s, v);
        }
    }

    function _byAddress(uint256[] memory keys) private pure returns (uint256[] memory) {
        for (uint256 i; i < keys.length; ++i) {
            for (uint256 j = i + 1; j < keys.length; ++j) {
                if (vm.addr(keys[j]) < vm.addr(keys[i])) (keys[i], keys[j]) = (keys[j], keys[i]);
            }
        }
        return keys;
    }

    function _etchSafeCode(address target, string memory file, bytes32 codehash) private {
        string memory path =
            string.concat(vm.projectRoot(), "/test/fixtures/base-sepolia-safe/", file);
        bytes memory code = vm.parseBytes(vm.trim(vm.readFile(path)));
        assertEq(keccak256(code), codehash, string.concat(file, " is not the Base Sepolia code"));
        vm.etch(target, code);
    }
}

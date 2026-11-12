// SPDX-License-Identifier: Apache-2.0
pragma solidity 0.8.38;

import {Test} from "forge-std/Test.sol";
import {IEAS} from "eas-contracts/IEAS.sol";

/// @notice Installs the EAS and SchemaRegistry code of Base Sepolia at their predeploy
/// addresses, from test/fixtures/base-sepolia-eas (see its README). The tests thus run against
/// exactly the code the escrow will meet on the testnet, without network access.
abstract contract BaseSepoliaEas is Test {
    address internal constant EAS_PREDEPLOY = 0x4200000000000000000000000000000000000021;
    address internal constant SCHEMA_REGISTRY_PREDEPLOY =
        0x4200000000000000000000000000000000000020;

    // Code hashes of the implementations on Base Sepolia (EAS 1.4.1-beta.3, SchemaRegistry
    // 1.3.1-beta.2), checked on 2026-11-11 with `cast codehash`.
    bytes32 internal constant EAS_CODEHASH =
        0x5b1a9eac43a2752a4f6b83617cd580cf17abc5b15812c3cea6c26c4dd68fa721;
    bytes32 internal constant SCHEMA_REGISTRY_CODEHASH =
        0x87e5c437b0ed0763fb8dc0ab25f25cf5a302057a50de464387b587acec1f040a;

    function _installEas() internal returns (IEAS) {
        _etch(SCHEMA_REGISTRY_PREDEPLOY, "schema-registry.runtime.hex", SCHEMA_REGISTRY_CODEHASH);
        _etch(EAS_PREDEPLOY, "eas.runtime.hex", EAS_CODEHASH);
        return IEAS(EAS_PREDEPLOY);
    }

    function _etch(address target, string memory file, bytes32 codehash) private {
        string memory path =
            string.concat(vm.projectRoot(), "/test/fixtures/base-sepolia-eas/", file);
        bytes memory code = vm.parseBytes(vm.trim(vm.readFile(path)));
        assertEq(keccak256(code), codehash, string.concat(file, " is not the Base Sepolia code"));
        vm.etch(target, code);
    }
}

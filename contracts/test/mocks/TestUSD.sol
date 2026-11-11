// SPDX-License-Identifier: Apache-2.0
pragma solidity 0.8.38;

import {ERC20} from "@openzeppelin/contracts/token/ERC20/ERC20.sol";

/// @notice LOCAL TESTS ONLY. A worthless token with USDC's 6 decimals and an open mint.
/// It is never deployed to any network; Base Sepolia uses Circle's testnet USDC.
contract TestUSD is ERC20 {
    constructor() ERC20("Test USD (local tests only)", "TESTUSD") {}

    function decimals() public pure override returns (uint8) {
        return 6;
    }

    function mint(address to, uint256 amount) external {
        _mint(to, amount);
    }
}

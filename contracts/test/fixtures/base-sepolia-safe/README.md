# Safe 1.4.1 bytecode from Base Sepolia (for local tests)

Runtime bytecode of the canonical Safe 1.4.1 contracts, so the governance tests
run against exactly the multisig code used on the testnet, without network
access in CI (decision D-21).

| File | Contract | Address (canonical, also on Base Sepolia) | Code hash (keccak-256) |
|---|---|---|---|
| `safe-l2.runtime.hex` | SafeL2 1.4.1 (singleton) | `0x29fcB43b46531BcA003ddC8FCB67FFE91900C762` | `0xb1f926978a0f44a2c0ec8fe822418ae969bd8c3f18d61e5103100339894f81ff` |
| `safe-proxy-factory.runtime.hex` | SafeProxyFactory 1.4.1 | `0x4e1DCf7AD4e460CfD30791CCC4F9c8a4f820ec67` | `0x50c3cdc4074750a7a974204a716c999edd37482f907608d960b2b025ee0b3317` |

Fetched on 2026-11-12 at Base Sepolia block 57696889. The addresses and code
hashes are those listed for chain 84532 in
[safe-deployments](https://github.com/safe-global/safe-deployments)
(`src/assets/v1.4.1/`), and the on-chain code hashes match them. The tests
refuse to run if a file's hash differs.

The Safe contracts are LGPL-3.0
([safe-smart-account](https://github.com/safe-global/safe-smart-account) v1.4.1).
This bytecode is used only in tests and is not part of the Orbit Watch
contracts.

To check or refresh (Foundry's `cast`):

```sh
RPC=https://sepolia.base.org
cast codehash 0x29fcB43b46531BcA003ddC8FCB67FFE91900C762 --rpc-url $RPC
cast code 0x29fcB43b46531BcA003ddC8FCB67FFE91900C762 --rpc-url $RPC > safe-l2.runtime.hex
```

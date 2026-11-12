# EAS bytecode from Base Sepolia (for local tests)

Runtime bytecode of the contracts behind Base Sepolia's EAS predeploys, so the
escrow is tested against exactly the code it will meet on the testnet,
without any network access in CI (decision D-20).

| File | Predeploy | Implementation | `version()` | Code hash (keccak-256) |
|---|---|---|---|---|
| `eas.runtime.hex` | EAS `0x4200000000000000000000000000000000000021` | `0xc919d2c8d3a7b617fea7604b68d862027bd02e64` | 1.4.1-beta.3 | `0x5b1a9eac43a2752a4f6b83617cd580cf17abc5b15812c3cea6c26c4dd68fa721` |
| `schema-registry.runtime.hex` | SchemaRegistry `0x4200000000000000000000000000000000000020` | `0xbbac3f3b485099f33ea9450299fdd5fc0a2a0a5a` | 1.3.1-beta.2 | `0x87e5c437b0ed0763fb8dc0ab25f25cf5a302057a50de464387b587acec1f040a` |

Fetched on 2026-11-11 at Base Sepolia block 57519673. The predeploys are
proxies; their implementation addresses are in the EIP-1967 slot
`0x360894a13ba1a3210667c828492db98dca3e2076cc3735a920a3ca505d382bbc`. The
tests place the implementation code directly at the predeploy addresses and
refuse to run if its hash differs from the table.

The source is the EAS code vendored in the Optimism monorepo
(`packages/contracts-bedrock/src/vendor/eas/`, MIT), derived from
[eas-contracts](https://github.com/ethereum-attestation-service/eas-contracts).

To check or refresh (Foundry's `cast`):

```sh
RPC=https://sepolia.base.org
cast storage 0x4200000000000000000000000000000000000021 0x360894a13ba1a3210667c828492db98dca3e2076cc3735a920a3ca505d382bbc --rpc-url $RPC
cast codehash 0xc919d2c8d3a7b617fea7604b68d862027bd02e64 --rpc-url $RPC
cast code 0xc919d2c8d3a7b617fea7604b68d862027bd02e64 --rpc-url $RPC > eas.runtime.hex
```

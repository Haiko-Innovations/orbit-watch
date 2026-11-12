# The evm-testnet settlement adapter

Phase 2, step 2.5. Code: [`core/src/orbit_watch/settlement/evm.py`](../core/src/orbit_watch/settlement/evm.py)
and [`core/src/orbit_watch/chain/`](../core/src/orbit_watch/chain).
Decisions [P2-08](decisions.md#p2-08-python-adapter-on-web3py) and
[D-22](decisions.md#d-22-adapter-interface-2-and-the-evm-testnet-adapter).

> **Testnet only.** The adapter refuses every chain except Base Sepolia
> (84532) and a local Anvil chain (31337). Its tests run only on a local chain.

The adapter puts the phase 1 settlement interface on top of the
[escrow contract](escrow.md) and its [attestations](attestations.md). The
contract applies settlement rules 1.0 itself. After every settlement the
adapter compares what the contract paid with what the shared rules
(`settlement_plan`) say, payout by payout, and reports any difference as
`chain_disagrees`.

## Installing

The adapter needs web3.py 8 (MIT), as the optional `evm` extra:

```sh
pip install "orbit-watch[evm] @ git+https://github.com/Haiko-Innovations/orbit-watch.git#subdirectory=core"
```

Nothing else in Orbit Watch imports it.

## What each call does

| Call | On chain | Signed by |
|---|---|---|
| `fund` | `escrow.fund` with the request's terms (deadlines in whole seconds) and split | the requester |
| `reserve` | `escrow.reserve` | the station |
| `deliver` | `escrow.deliver` with the file's SHA-256 | the station |
| `attest`, automated result | an EAS attestation of the result schema | the verifier key |
| `challenge` | `escrow.challenge` with the SHA-256 of the reason | the requester or the observer |
| `attest`, review vote | an EAS attestation of the vote schema, referencing the result | the reviewer |
| `settle` | `escrow.settle` | the operator (by default the verifier key) |
| `refund` | `escrow.cancel` for a cancelled request, `escrow.settle` for an expired one | the requester, the operator |
| `balance(party)` | what the party holds plus what it can withdraw | |
| `escrow(request)` | what the escrow holds for the request | |

Each party signs with its own account (decision
[P2-09](decisions.md#p2-09-keys-and-wallets)). The adapter is given the
accounts it may sign for. Unfunded requests never touch the chain.

Each call needs the request's lifecycle record right after the event it
mirrors (`record=`). It holds the terms, the split, the delivery, the
reviewers and the time. When the escrow chooses a round's reviewers, the
adapter checks that they are the record's reviewers (`reviewers_differ`
otherwise). From step 2.6 the service takes the round from the chain instead.

Refusals carry the contract's custom error in snake case, for example
`requester_cannot_reserve`, `already_funded` or `not_the_verifier`. A second
settlement is `already_settled`.

**Idempotency.** A key seen before, with the same arguments, returns the
first receipt without a new transaction; with other arguments it is
`key_reused`. In this step the keys are kept in memory; the service stores
them from step 2.6.

## Tests on a local chain

`core/tests/test_evm_adapter.py` runs **the phase 1 settlement scenario
suite** against the escrow, each scenario on a fresh Anvil chain with:

- Base Sepolia's EAS code at the predeploy addresses (checked by hash);
- the contracts from the Foundry build;
- worthless TestUSD.

The simulated parties sign with **local test accounts** whose keys are derived
from their names. Anyone can recompute those keys, so they are only for a
local chain.

With `follow_record_time` (local chain only), the chain's clock follows the
record: every transaction is mined at the exact second of the lifecycle event,
so the deadlines of the scenarios fall on chain exactly as in Python.

Every scenario must give the same outcome and the same net change for every
party as on the points ledger. Every settlement is also checked against the
rules, replayed calls must change nothing, and a second settlement must be
refused.

To run the tests yourself you need [Foundry](https://getfoundry.sh) 1.8.6 on
`PATH`:

```sh
cd contracts && forge build
cd ../core && ORBIT_WATCH_EVM_TESTS=1 uv run pytest tests/test_evm_adapter.py
```

Without `anvil` or the build, these tests are skipped. CI sets
`ORBIT_WATCH_EVM_TESTS=1`, so there a missing piece is a failure. CI also
checks that the ABIs shipped in the package
([`core/src/orbit_watch/chain/abi/`](../core/src/orbit_watch/chain/abi)) match
the contracts.

## Not yet

- The service, the API and the command line still use the points ledger.
  Step 2.6 adds wallets per party, pending, confirmed and failed
  transactions, the chain as the source of truth for payments, and signing
  with the user's own wallet or keystore.
- Deployment to Base Sepolia comes with step 2.7.

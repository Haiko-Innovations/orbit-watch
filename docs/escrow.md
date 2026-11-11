# Escrow contract

Phase 2. Code: [`contracts/src/OrbitWatchEscrow.sol`](../contracts/src/OrbitWatchEscrow.sol).
This page grows with each phase 2 step; it describes what exists now.

> **Testnet only.** The constructor refuses every chain except Base Sepolia
> (84532) and a local Anvil chain (31337).

## Principles

- **One contract for all requests**, not upgradeable: no proxy, no owner, no
  administrator ([P2-05](decisions.md#p2-05-one-non-upgradeable-escrow-contract)).
  A new version is a new contract; existing requests settle in the old one.
- **Money leaves only by a request's rules.** No function lets anyone,
  administrators included, take a deposit.
- **The phase 1 rules, on chain** ([P2-06](decisions.md#p2-06-the-phase-1-rules-on-chain)):
  the split is locked at funding, and the same settlement rules and scenario
  suite apply.
- Transfers go through OpenZeppelin's `SafeERC20`.

## Identifiers

| On chain | Off chain |
|---|---|
| `requestId` = `keccak256(bytes(request_id))` (helper: `requestKey`) | the Orbit Watch request ID, for example `SIM-REQ-0001` |
| `termsHash` | the SHA-256 of the request's frozen terms (`terms_sha256` in the lifecycle record) |

## What exists (step 2.1)

| Function | Who | Does |
|---|---|---|
| `fund(requestId, termsHash, observerReward, reviewerReward, platformFee, deliveryDeadline)` | the requester | takes the deposit (observer + 3 × reviewer + fee) with `transferFrom` and locks the split; once per request |
| `refund(requestId)` | anyone | after the delivery deadline, returns the whole deposit **to the requester**; once |
| `getRequest`, `requestKey`, `token`, `totalHeld` | anyone | read |

In step 2.1 there are no deliveries on chain yet, so every funded request
becomes refundable at its deadline. Deliveries, the challenge period, votes and
settlement come in steps 2.2 and 2.3.

## Tests

`forge test` runs unit tests, a fuzz test (funding then refunding always
returns everything) and invariant tests over random sequences of funding,
refunding and passing time by several requesters:

- the escrow's token balance always equals what it owes (`totalHeld`);
- no token is created or lost;
- `totalHeld` equals the sum of the deposits of funded requests.

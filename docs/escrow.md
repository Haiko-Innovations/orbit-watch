# Escrow contract

Phase 2. Code: [`contracts/src/OrbitWatchEscrow.sol`](../contracts/src/OrbitWatchEscrow.sol).
This page grows with each phase 2 step; it describes what exists now (step 2.2).

> **Testnet only.** The constructor refuses every chain except Base Sepolia
> (84532) and a local Anvil chain (31337). The token is Circle's testnet USDC,
> which has no value.

## Principles

- **One contract for all requests**, not upgradeable: no proxy, no owner, no
  administrator ([P2-05](decisions.md#p2-05-one-non-upgradeable-escrow-contract)).
  A new version is a new contract; existing requests settle in the old one.
- **Money leaves only by a request's rules**, and only to the party it is owed
  to. No function lets anyone, administrators included, take a deposit.
- **The phase 1 rules, on chain** ([P2-06](decisions.md#p2-06-the-phase-1-rules-on-chain)):
  the same lifecycle deadlines and settlement rules 1.0
  ([settlement.md](settlement.md)). The phase 1 scenario suite runs against the
  contract (below).
- **Pull payments** ([D-19](decisions.md#d-19-settlement-on-chain)): settling
  credits each party, and each party withdraws its own credit. A transfer that
  fails for one party can then never hold up a settlement or anyone else's
  money.
- Transfers go through OpenZeppelin's `SafeERC20`.

## Identifiers

| On chain | Off chain |
|---|---|
| `requestId` = `keccak256(bytes(request_id))` (helper: `requestKey`) | the Orbit Watch request ID, for example `SIM-REQ-0001` |
| `termsHash` | the SHA-256 of the request's frozen terms (`terms_sha256` in the lifecycle record) |
| `deliverySha256` | the SHA-256 of the delivered observation file |

Unfunded (volunteer) requests never touch the chain.

## Lifecycle on chain

The same statuses and deadlines as the [phase 1 lifecycle](lifecycle.md), from
funding onwards (drafts and opening stay off chain; the terms that matter on
chain are passed when funding).

Deadlines are applied **lazily**: `statusOf(requestId)` returns the status at
the current block time with every passed deadline applied, exactly as
`advance` does in phase 1. Nobody has to call anything when a deadline passes,
and every function checks the status at the current time. A deadline applies
at the second it is reached: a vote at the review deadline is too late.

| Status now | How it is left |
|---|---|
| `Funded` | `reserve` by a station; `cancel` by the requester; delivery deadline → `Expired` |
| `Reserved` | `deliver` by the reserving station; reservation lapses → `Funded`; delivery deadline → `Expired` |
| `Delivered` | automated result; verification timeout → `Expired` |
| `ChallengePeriod` | challenge by the requester or the observer → `InReview`; deadline → `Accepted` (pass) or `Rejected` (fail) |
| `InReview` | two equal votes → `Accepted` or `Rejected`; review deadline → `Disputed` |
| `Accepted`, `Rejected`, `Disputed`, `Expired` | `settle` by anyone → `Settled` |

`cancel` settles at once (everything back to the requester).

## Functions

| Function | Who | Does |
|---|---|---|
| `fund(requestId, terms, split)` | the requester | takes the deposit (observer + 3 × reviewer + fee) and locks the split and the time limits of the terms, in whole seconds; once per request |
| `cancel(requestId)` | the requester | before any reservation (or after one lapsed); credits the whole deposit back |
| `reserve(requestId)` | any station but the requester | for the reservation time of the terms, never past the delivery deadline |
| `deliver(requestId, deliverySha256)` | the reserving station | records the delivery; the automated result must follow within the verification timeout |
| `settle(requestId)` | anyone | credits the payouts of settlement rules 1.0; once |
| `withdraw()` | anyone with a credit | transfers the caller's own credit |
| `statusOf`, `getRequest`, `depositOf`, `owed`, `totalHeld`, `totalOwed`, `requestKey` | anyone | read |

**Not connected yet (step 2.3).** Recording the automated result, challenges
and votes are internal functions with the full rules: the verdict starts the
challenge period (or, if inconclusive, a reviewer round), only the requester or
the observer can challenge, a round needs three different reviewers who are
neither the requester nor the observer, each reviewer votes once and two equal
votes decide. Step 2.3 connects them to EAS attestations and the reviewer
registry. Until then a delivery on a deployed contract can only expire, and
the requester gets everything back. The tests reach these functions through a
test-only contract (`test/helpers/EscrowHarness.sol`) that is never deployed.

## Settlement rules 1.0

| Outcome | Observer | Each reviewer who voted | Platform fee | Requester |
|---|---|---|---|---|
| `Accepted` | observer reward | reviewer reward | fee | the rest |
| `Rejected`, `Disputed` | – | reviewer reward | – | the rest |
| `Expired`, `Cancelled` | – | – | – | everything |

The platform fee goes to `feeRecipient`, fixed at deployment. With no
recipient, requests must have a zero fee. Each payout emits
`Credited(requestId, party, amount, reason)`, with the same reasons as a phase 1
payout (observer reward, review, platform fee, refund).

## Tests

`forge test` runs:

- **Unit tests** of every transition and refusal, and of each outcome's
  payouts, including the example in [settlement.md](settlement.md).
- **The phase 1 scenario suite on chain.** The Python core exports its
  settlement scenarios to
  [`contracts/test/fixtures/settlement-scenarios.json`](../contracts/test/fixtures/settlement-scenarios.json)
  (simulated parties). The Solidity test replays every funded scenario and
  checks the same outcome and the same net change for every party as the
  points ledger. A Python test fails if the file is not current.
- **A fuzz test** (1000 runs): whatever the split and however the round goes,
  each party gets exactly what the rules say and the payouts add up to the
  deposit.
- **Invariant tests** over random histories of many requests at once (fund,
  cancel, reserve, deliver, automated results, challenges, votes, settle,
  withdraw, time passing), with a stranger who keeps trying to cancel, deliver
  and withdraw:
  - every settlement pays each party exactly what the rules say, computed
    independently in the test, and pays out exactly the deposit;
  - the escrow's balance always equals what it holds plus what it owes;
  - no token is created or lost;
  - a request is settled once;
  - nobody withdraws more or less than their credit, and the stranger never
    gets anything.

Each check was also confirmed to fail on purposely broken versions of the
contract (for example, one that pays the observer in a dispute).

## Known limits

- Tokens sent to the contract directly, not through `fund`, cannot be
  recovered: there is no administrator.
- The token must be a plain ERC-20 such as USDC (no fee on transfer).

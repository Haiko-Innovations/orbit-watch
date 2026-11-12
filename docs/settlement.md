# Settlement

Phase 1, step 1.2. Code: [`core/src/orbit_watch/settlement/`](../core/src/orbit_watch/settlement).

When a request reaches an outcome, its deposit is divided. Two things are kept
apart on purpose:

- **The rule** (`settlement_plan`) decides who gets what. It is a pure function
  of the finished request, the same for every adapter.
- **An adapter** carries the plan out. Phase 1 has one, the points-only
  **ledger**. Phase 2 adds a testnet escrow behind the same interface, and it
  must pass the same scenario suite.

## Reward split

A requester can fund a request with points ([decision P-06](decisions.md#p-06-ledger-points-model)).
The split is locked when the request is funded:

| Part | Paid to | When |
|---|---|---|
| `observer` | the station that delivered | the request is accepted |
| `reviewer`, three times (the challenge-round reserve) | each reviewer who completed a review (cast a vote) | in every outcome, if there was a reviewer round |
| `platform_fee` (0 by default) | the platform | the request is accepted |

Deposit = `observer + 3 × reviewer + platform_fee`. Everything that is not paid
out goes back to the requester. Nothing is ever left in escrow.

## Rules (version 1.0)

| Outcome | Observer | Reviewers who voted | Platform fee | Requester |
|---|---|---|---|---|
| accepted | observer reward | reviewer reward each | fee | the rest |
| rejected | – | reviewer reward each | – | the rest |
| disputed | – | reviewer reward each | – | the rest |
| expired | – | – | – | everything |
| cancelled | – | – | – | everything |

This follows the plan's dispute rule: a dispute pays the completed reviews,
gives the observer nothing, refunds the rest and never locks the deposit. A
reviewer who had not voted when two votes decided the round is not paid.

Example (observer 100, reviewer 10, fee 5; deposit 135): the observer
challenges a failed automated result and two reviewers approve. The observer
gets 100, the two reviewers 10 each, the platform 5, and the requester gets 10
back.

## Adapter interface

Interface 2 ([D-22](decisions.md#d-22-adapter-interface-2-and-the-evm-testnet-adapter)):
every mutating call also takes `record`, the request's lifecycle record right
after the event. The ledger ignores it; the testnet adapter needs the terms,
split, delivery, reviewers and time from it.

| Call | Ledger | `evm-testnet` ([evm-adapter.md](evm-adapter.md)) |
|---|---|---|
| `fund(request, requester, points, key)` | requester's budget → escrow | `escrow.fund` with the terms and split |
| `reserve(request, station, key)` | recorded, no points move | `escrow.reserve` |
| `deliver(request, station, delivery, key)` | nothing journaled | `escrow.deliver` |
| `attest(request, attester, kind, subject, value, key)` | recorded in the journal | EAS attestation (result or vote) |
| `challenge(request, party, reason, key)` | nothing journaled | `escrow.challenge` |
| `settle(plan, key)` | escrow → payouts | `escrow.settle`, checked against the plan payout by payout |
| `refund(request, requester, key)` | escrow → requester | `escrow.cancel` or `escrow.settle` |
| `balance(party)`, `escrow(request)` | journal balances | token balance + credit, chain state |

**Idempotency.** Every mutating call takes a key. The same key with the same
arguments returns the first receipt and has no second effect; the same key with
different arguments is refused (`key_reused`). A request can be settled only
once, whatever the key (`already_settled`).

## The ledger

A double-entry journal of whole points. Every entry's postings sum to zero, so
points are never created or lost, except by an explicit `grant` from the
`issuance` account (budgets in phase 1). Accounts: `issuance`,
`party:<id>`, `escrow:<request id>`. The journal exports as deterministic JSON;
storage comes in step 1.5.

## Scenario suite

[`settlement/scenarios.py`](../core/src/orbit_watch/settlement/scenarios.py) drives
ten request histories through the lifecycle and an adapter: accepted
unchallenged, rejected unchallenged, challenged and accepted, challenged and
rejected 2–1, disputed, inconclusive then accepted, expired without delivery,
cancelled after funding, a lapsed reservation followed by another station, and
an unfunded request. For each it checks:

- the outcome and every party's net change in points;
- deposit = rewards + refunds, escrow ends at zero, nothing created or lost;
- replaying every call with the same keys changes nothing;
- a second settlement under a new key is refused.

`check_adapter(factory)` returns an empty list for a correct adapter.

The same scenarios run against the phase 2 escrow contract: `python -m
orbit_watch.settlement.scenarios` exports them to
[`contracts/test/fixtures/settlement-scenarios.json`](../contracts/test/fixtures/settlement-scenarios.json),
and the contract tests replay every funded one ([escrow.md](escrow.md#tests)). The tests
also run it against deliberately broken ledgers (one that ignores keys, one
that pays twice, one that settles twice) to show that the suite catches them.

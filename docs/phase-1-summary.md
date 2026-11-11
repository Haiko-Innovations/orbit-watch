# Phase 1 summary

**English** · [Suomi](phase-1-summary.fi.md)

Phase 1 (requests, optimistic verification and API) is complete as
**version 0.2.0**. This is the end-of-phase summary the [plan](plan.md#8-deliverables)
asks for.

## What works

Everything runs locally, with points instead of money and no blockchain.

- **Request lifecycle**: draft → open → (funded) → reserved → delivered →
  challenge period → accepted / rejected / (reviewer round → accepted /
  rejected / disputed), plus expired and cancelled; every request ends settled.
  A pure state machine with frozen, hashed terms and deadlines applied at their
  exact time ([lifecycle.md](lifecycle.md)).
- **Optimistic verification**: automated verification runs on delivery; the
  result becomes final unless the requester or the observer challenges it
  within 24 hours; a challenge starts a round of three independent reviewers
  chosen by a hash nobody can steer; two equal votes decide; no majority is a
  dispute ([optimistic-verification.md](optimistic-verification.md)).
- **Settlement** by shared rules through a points ledger: observer reward only
  when accepted, every completed review paid, the rest refunded, nothing locked
  ([settlement.md](settlement.md)). The rules and the scenario suite are ready
  for the phase 2 testnet adapter.
- **Reviewer accuracy** with known-answer calibration tasks mixed into every
  reviewer's queue ([reviewer-accuracy.md](reviewer-accuracy.md)).
- **Storage** in SQLite and content-addressed files; one transaction per call;
  survives restarts ([storage.md](storage.md)).
- **HTTP API** with role-scoped keys and idempotency, and a **command-line
  client** for the whole chain ([api.md](api.md)).
- **Data publication** under CC BY 4.0 after settlement and an optional embargo
  of at most 30 days, with permanent download URLs
  ([data-publication.md](data-publication.md)).

### Completion criteria

| Criterion from the plan | Status |
|---|---|
| The whole chain works with the ledger adapter from the CLI and the API | ✅ tested end to end through a real HTTP server and only the command line |
| Rejection, reservation expiry, challenge and reviewer round, dispute, and reviewer accuracy with known-answer datasets are tested | ✅ |
| Double delivery and double settlement have no double effect, tested | ✅ through the API (idempotent replays, refused second delivery, one settle entry) |

## What is simulated

- All stations, observations, requests, reviewers and the four objects in the
  built-in catalogue. Every simulated document says so itself, and simulated
  observations cannot satisfy a real request.
- Points are bookkeeping, not money. There is no blockchain yet.
- Time in the demo and the tests is a simulated clock.

## How to run it

```sh
pip install "orbit-watch[api] @ git+https://github.com/Haiko-Innovations/orbit-watch.git@v0.2.0#subdirectory=core"
orbit-watch demo --phase 1          # five requests, every outcome, in a few seconds
cat orbit-watch-demo-phase1/transcript.md
```

The same output is committed in [`examples/phase1/`](../examples/phase1). To
run the chain yourself through the API and the command line, see
[api.md](api.md#command-line-client).

## Open problems for the next phase

- **Phase 2 choices**: Base Sepolia or Optimism Sepolia (where EAS and test USDC
  are available according to current documentation), EAS schemas for automated
  results and votes, Foundry for the contracts, and the multisig and timelock
  for the reviewer list.
- **Calibration with real data** must use archived real deliveries with settled
  answers; stock challenge texts and missing attestations would give
  calibration tasks away.
- **Bonds** for reservations, challenges and reviewers (open question of the
  plan).
- **Personal data**: station coordinates become public with the data.
- **A public deployment** (P-03) needs TLS, rate limits, key rotation and
  operations work.
- **A real IOD example** of a civilian object, shared with permission
  ([#8](https://github.com/Haiko-Innovations/orbit-watch/issues/8)).

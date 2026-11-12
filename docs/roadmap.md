# Roadmap and status

**English** · [Suomi](roadmap.fi.md)

This page says where Orbit Watch is now and what comes next. The full starting
plan is in [plan.md](plan.md); decisions and their reasons are in
[decisions.md](decisions.md); released changes are in the
[changelog](../CHANGELOG.md). Work is tracked in
[GitHub milestones](https://github.com/Haiko-Innovations/orbit-watch/milestones).

Every pull request that finishes a roadmap step also updates this page.

## Status (2026-11-12)

**Phase 2 is done** and released as version 0.3.0: settlement on the Base
Sepolia testnet with Circle's testnet USDC. A non-upgradeable escrow holds the
deposits, the automated results and reviewer votes are EAS attestations, the
reviewer registry sits behind a Safe 2-of-3 multisig and a 48-hour timelock,
and the service, API and command line run on the chain with every party
signing with its own wallet. The contracts are deployed on Base Sepolia
([base-sepolia.md](base-sepolia.md)), and the phase 2 demo ran there with a
wallet per party. See the [phase 2 summary](phase-2-summary.md).

Phase 1 was released as version 0.2.0 ([phase 1 summary](phase-1-summary.md))
and phase 0 as
[version 0.1.0](https://github.com/Haiko-Innovations/orbit-watch/releases/tag/v0.1.0);
phase 0's one open criterion, a real public IOD example, is still open
([#8](https://github.com/Haiko-Innovations/orbit-watch/issues/8)).

**Next: phase 3**, the web application, planned in detail before it starts.

## Next steps

### Phase 0 follow-up (milestone "Phase 0 follow-up")

In parallel with phase 1, mostly for the community:

- ✅ Release 0.1.0. Pin the repository on the Haiko Innovations profile.
- A real IOD example of a civilian object, shared with permission ([#8](https://github.com/Haiko-Innovations/orbit-watch/issues/8)).
- Good first issues: older IOD equinoxes ([#4](https://github.com/Haiko-Innovations/orbit-watch/issues/4)),
  a track-order check ([#5](https://github.com/Haiko-Innovations/orbit-watch/issues/5)),
  a DSLR station profile ([#6](https://github.com/Haiko-Innovations/orbit-watch/issues/6)).
- Simulator illumination ([#7](https://github.com/Haiko-Innovations/orbit-watch/issues/7)).

### Phase 1: requests, optimistic verification and API (target version 0.2.0)

Phase 1 turns single verifications into a full request lifecycle, still
without money: a points-only "ledger" adapter follows exactly the rules that
monetary settlement will follow later. The steps below are in dependency
order; each is one pull request (two at most). The domain logic comes first,
without storage or network, so that it can be tested exhaustively; storage and
the API come after.

| Step | Content | Done when |
|---|---|---|
| ✅ **1.1 Request lifecycle** ([#11](https://github.com/Haiko-Innovations/orbit-watch/issues/11)) | State machine: draft → open → (funded) → reserved → delivered → verified → challenge period → accepted / rejected / disputed → settled, plus expired. Terms snapshot with a hash. Injected clock for timeouts. | Every transition and every forbidden transition is tested; state diagram in the docs. |
| ✅ **1.2 Settlement adapter and ledger** ([#12](https://github.com/Haiko-Innovations/orbit-watch/issues/12)) | Interface `fund`, `reserve`, `attest`, `settle`, `refund`. Ledger adapter: integer points, double-entry journal, idempotency keys. A scenario suite that any adapter must pass. | Deposit = rewards + refunds in every scenario; a repeated settle has no second effect. |
| ✅ **1.3 Optimistic verification** ([#13](https://github.com/Haiko-Innovations/orbit-watch/issues/13)) | Automated report → challenge period (default 24 h, fixed in the terms) → if challenged, three pre-approved reviewers, 2 of 3 decides, nobody reviews their own delivery. Dispute rule. Reviewers are paid for completed reviews whatever the outcome. | Unchallenged, challenged-accepted, challenged-rejected and no-majority (dispute) cases tested end to end with the ledger. |
| ✅ **1.4 Reviewer accuracy** ([#14](https://github.com/Haiko-Innovations/orbit-watch/issues/14)) | Known-answer datasets from the simulator are mixed into reviewer assignments; accuracy per reviewer. | A reviewer who approves everything shows low accuracy; tested. |
| ✅ **1.5 Storage** ([#15](https://github.com/Haiko-Innovations/orbit-watch/issues/15)) | SQLite schema and migrations for requests, reservations, deliveries, reports, challenges and the ledger journal; content-addressed file storage. | State survives a restart; migrations tested from empty. |
| ✅ **1.6 API** ([#16](https://github.com/Haiko-Innovations/orbit-watch/issues/16)) | HTTP API for the lifecycle. Role-scoped API keys: a station key can only deliver, never move points. Idempotency keys on every mutating call. | Double delivery and double settlement have no double effect; tested through the API. |
| ✅ **1.7 CLI** ([#17](https://github.com/Haiko-Innovations/orbit-watch/issues/17)) | `submit` and new commands for requests, reservations, challenges and reviews against the API. | The whole chain runs from the command line. |
| ✅ **1.8 Data publication and phase 1 demo** ([#18](https://github.com/Haiko-Innovations/orbit-watch/issues/18)) | Licence (CC BY 4.0 by default), embargo of at most 30 days, file retention and permanent download URLs. A phase 1 demo and the phase 1 report. | The phase 1 completion criteria in [plan.md](plan.md#phase-1-requests-optimistic-verification-and-api-python-or-typescript-lightweight-database) are met; release 0.2.0. |

The decisions P-01 to P-07 in [decisions.md](decisions.md#phase-1-decisions) were
approved on 2026-11-11 ([#10](https://github.com/Haiko-Innovations/orbit-watch/issues/10)).
Step 1.1 is described in [lifecycle.md](lifecycle.md), step 1.2 in
[settlement.md](settlement.md), step 1.3 in
[optimistic-verification.md](optimistic-verification.md), step 1.4 in
[reviewer-accuracy.md](reviewer-accuracy.md), step 1.5 in [storage.md](storage.md),
steps 1.6 and 1.7 in [api.md](api.md), step 1.8 in
[data-publication.md](data-publication.md).

### Phase 2: settlement on a testnet (target version 0.3.0)

Phase 2 moves settlement from the points ledger to an escrow contract on an
EVM L2 **testnet**, with automated results and reviewer votes as **EAS
attestations**. The rules stay exactly those of phase 1: the testnet adapter
must pass the same settlement scenario suite as the ledger. No mainnet, no
token of our own, no real money: testnet USDC has no value.

The choices behind this plan are **decisions P2-01 to P2-11** in
[decisions.md](decisions.md#phase-2-decisions), approved on 2026-11-11
([#27](https://github.com/Haiko-Innovations/orbit-watch/issues/27)). In short: **Base Sepolia**, Circle's **testnet USDC**,
EAS at its predeploy address, **Foundry** and **OpenZeppelin Contracts**, a
non-upgradeable escrow, a reviewer registry behind a **Safe multisig and a
public timelock**, and a Python adapter on **web3.py**.

| Step | Content | Done when |
|---|---|---|
| ✅ **2.1 Contracts project** ([#28](https://github.com/Haiko-Innovations/orbit-watch/issues/28)) | `contracts/` Foundry project, OpenZeppelin pinned, built and tested in the `tarkistus` check; escrow skeleton with `fund` and `refund`; refuses to run on any chain but Base Sepolia or a local Anvil chain. | `forge test` runs in CI; funding and refunding work on a local chain. |
| ✅ **2.2 Settlement rules on chain** ([#29](https://github.com/Haiko-Innovations/orbit-watch/issues/29)) | The phase 1 settlement rules in Solidity: split locked at funding, deadlines on chain, permissionless and idempotent settlement, no administrator access to deposits. | Fuzz and invariant tests: deposit = rewards + refunds, a request is settled once, unauthorised parties cannot withdraw. |
| ✅ **2.3 Attestations** ([#30](https://github.com/Haiko-Innovations/orbit-watch/issues/30)) | EAS schemas for the automated result and for reviewer votes; the escrow reads the automated attestation, opens the challenge period and counts 2-of-3 votes from registered reviewers. | Unchallenged, challenged-accepted, challenged-rejected and dispute settle on chain from attestations. |
| ✅ **2.4 Reviewer registry** ([#31](https://github.com/Haiko-Innovations/orbit-watch/issues/31)) | Registry of reviewer addresses owned by an OpenZeppelin TimelockController whose proposer is a Safe multisig; the privileges are documented in the README. | Adding and removing reviewers works only through the multisig and the timelock; tested. |
| ✅ **2.5 Testnet adapter** ([#32](https://github.com/Haiko-Innovations/orbit-watch/issues/32)) | `evm-testnet` settlement adapter in Python (web3.py): `fund`, `reserve`, `attest`, `settle`, `refund` as transactions and attestations. | The adapter passes the settlement scenario suite against a local Anvil chain in CI. |
| ✅ **2.6 Service, API and CLI** ([#33](https://github.com/Haiko-Innovations/orbit-watch/issues/33)) | Wallet addresses per party; pending, confirmed and failed transactions shown apart; the chain is the source of truth for payments; explorer links; signing with the user's own wallet or keystore. | The whole chain runs from the CLI and the API against a local chain; no key ever leaves its owner. |
| ✅ **2.7 Testnet deployment** ([#34](https://github.com/Haiko-Innovations/orbit-watch/issues/34)) | Deployment scripts and settings for Base Sepolia, schema registration, faucet instructions (testnet ETH and USDC), testnet labels everywhere. | The contracts run on Base Sepolia from the documented instructions. |
| ✅ **2.8 Phase 2 demo** ([#35](https://github.com/Haiko-Innovations/orbit-watch/issues/35)) | A demo on Base Sepolia with separate wallets per party, and the phase 2 summary. | The phase 2 completion criteria in [plan.md](plan.md#phase-2-monetary-settlement-on-a-testnet-evm-l2--eas) are met; release 0.3.0. |

### Phase 3 (later)

A web application with role views, planned in detail when phase 2 is done.

## How we work

- One pull request at a time, branched from `main`, squash-merged by a
  maintainer after the `tarkistus` check passes. No stacked pull requests:
  with squash merges they conflict ([D-10](decisions.md#d-10-one-pull-request-at-a-time-on-main)).
- Every pull request with user-visible changes adds a line to the
  `Unreleased` section of the [changelog](../CHANGELOG.md).
- Releases follow [releasing.md](releasing.md): one minor version per phase
  while the version is 0.x, patch versions for fixes.

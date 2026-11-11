# Roadmap and status

**English** · [Suomi](roadmap.fi.md)

This page says where Orbit Watch is now and what comes next. The full starting
plan is in [plan.md](plan.md); decisions and their reasons are in
[decisions.md](decisions.md); released changes are in the
[changelog](../CHANGELOG.md). Work is tracked in
[GitHub milestones](https://github.com/Haiko-Innovations/orbit-watch/milestones).

Every pull request that finishes a roadmap step also updates this page.

## Status (2026-11-11)

**Phase 0, the open core, is done** and released as
[version 0.1.0](https://github.com/Haiko-Innovations/orbit-watch/releases/tag/v0.1.0).
**Phase 1 is in progress:** the decisions are approved, and step 1.1 (the
request lifecycle) is done.

| Phase 0 completion criterion | Status |
|---|---|
| `pip install` and one command produce a simulated dataset and a verification report | ✅ `orbit-watch demo` |
| All six test datasets get the correct result and an understandable explanation | ✅ checked in CI, byte for byte, on Python 3.12 and 3.15 |
| The quality meter works with simulated data | ✅ |
| …and with one real public IOD example | ❌ open: see [#8](https://github.com/Haiko-Innovations/orbit-watch/issues/8) |
| README, CONTRIBUTING, code of conduct, issue templates, good first issues | ✅ |

The missing real example is a data problem, not a code problem: recent public
IOD observations are almost all of classified objects, which Orbit Watch does
not handle. It does not block phase 1.

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
| **1.2 Settlement adapter and ledger** ([#12](https://github.com/Haiko-Innovations/orbit-watch/issues/12)) | Interface `fund`, `reserve`, `attest`, `settle`, `refund`. Ledger adapter: integer points, double-entry journal, idempotency keys. A scenario suite that any adapter must pass. | Deposit = rewards + refunds in every scenario; a repeated settle has no second effect. |
| **1.3 Optimistic verification** ([#13](https://github.com/Haiko-Innovations/orbit-watch/issues/13)) | Automated report → challenge period (default 24 h, fixed in the terms) → if challenged, three pre-approved reviewers, 2 of 3 decides, nobody reviews their own delivery. Dispute rule. Reviewers are paid for completed reviews whatever the outcome. | Unchallenged, challenged-accepted, challenged-rejected and no-majority (dispute) cases tested end to end with the ledger. |
| **1.4 Reviewer accuracy** ([#14](https://github.com/Haiko-Innovations/orbit-watch/issues/14)) | Known-answer datasets from the simulator are mixed into reviewer assignments; accuracy per reviewer. | A reviewer who approves everything shows low accuracy; tested. |
| **1.5 Storage** ([#15](https://github.com/Haiko-Innovations/orbit-watch/issues/15)) | SQLite schema and migrations for requests, reservations, deliveries, reports, challenges and the ledger journal; content-addressed file storage. | State survives a restart; migrations tested from empty. |
| **1.6 API** ([#16](https://github.com/Haiko-Innovations/orbit-watch/issues/16)) | HTTP API for the lifecycle. Role-scoped API keys: a station key can only deliver, never move points. Idempotency keys on every mutating call. | Double delivery and double settlement have no double effect; tested through the API. |
| **1.7 CLI** ([#17](https://github.com/Haiko-Innovations/orbit-watch/issues/17)) | `submit` and new commands for requests, reservations, challenges and reviews against the API. | The whole chain runs from the command line. |
| **1.8 Data publication and phase 1 demo** ([#18](https://github.com/Haiko-Innovations/orbit-watch/issues/18)) | Licence (CC BY 4.0 by default), embargo of at most 30 days, file retention and permanent download URLs. A phase 1 demo and the phase 1 report. | The phase 1 completion criteria in [plan.md](plan.md#phase-1-requests-optimistic-verification-and-api-python-or-typescript-lightweight-database) are met; release 0.2.0. |

The decisions P-01 to P-07 in [decisions.md](decisions.md#phase-1-decisions) were
approved on 2026-11-11 ([#10](https://github.com/Haiko-Innovations/orbit-watch/issues/10)).
Step 1.1 is described in [lifecycle.md](lifecycle.md).

### Phase 2 and phase 3 (later)

- **Phase 2:** settlement on an EVM L2 testnet with EAS attestations, behind the
  same adapter interface and the same scenario suite as the ledger. No mainnet.
- **Phase 3:** a web application with role views.

These are planned in detail only when phase 1 is done.

## How we work

- One pull request at a time, branched from `main`, squash-merged by a
  maintainer after the `tarkistus` check passes. No stacked pull requests:
  with squash merges they conflict ([D-10](decisions.md#d-10-one-pull-request-at-a-time-on-main)).
- Every pull request with user-visible changes adds a line to the
  `Unreleased` section of the [changelog](../CHANGELOG.md).
- Releases follow [releasing.md](releasing.md): one minor version per phase
  while the version is 0.x, patch versions for fixes.

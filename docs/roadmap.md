# Roadmap and status

**English** · [Suomi](roadmap.fi.md)

This page says where Orbit Watch is now and what comes next. The full starting
plan is in [plan.md](plan.md); decisions and their reasons are in
[decisions.md](decisions.md); released changes are in the
[changelog](../CHANGELOG.md). Work is tracked in
[GitHub milestones](https://github.com/Haiko-Innovations/orbit-watch/milestones).

Every pull request that finishes a roadmap step also updates this page.

## Status (2026-11-14)

**Phase 3 is done** and released as version 0.4.0: the web application.
Every party signs in and signs with its own wallet in the browser; requesters,
observers, reviewers and administrators each have their views; the station
quality meter and the attestation browser are public pages; and every role's
end-to-end test and the accessibility review of every view run in CI against
a local chain. The phase 3 demo ran the whole chain in the browser on Base
Sepolia with a wallet per role. See the [phase 3 summary](phase-3-summary.md).
The service still runs locally only
([P3-10](decisions.md#p3-10-no-public-deployment-in-phase-3)).

**Phase 4 is planned**: a public testnet service, the service and the web
application online on Base Sepolia, still SIMULATED. Its decisions P4-01 to
P4-13 wait for approval ([#67](https://github.com/Haiko-Innovations/orbit-watch/issues/67)).

Phase 2 was released as version 0.3.0 ([phase 2 summary](phase-2-summary.md)),
phase 1 as version 0.2.0 ([phase 1 summary](phase-1-summary.md)) and phase 0
as [version 0.1.0](https://github.com/Haiko-Innovations/orbit-watch/releases/tag/v0.1.0);
phase 0's one open criterion, a real public IOD example, is still open
([#8](https://github.com/Haiko-Innovations/orbit-watch/issues/8)).

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

### Phase 3: web application (target version 0.4.0)

Phase 3 puts the phase 2 system in the browser: one web application with
views for requesters, observers, reviewers and administrators, a station
quality meter and a public attestation browser. Every party signs with its
own wallet in the browser, and the browser holds no privilege the API does not
give: the rules stay in the service and the contracts. Still the testnet only,
and still no public deployment unless decided otherwise.

The choices behind this plan are **decisions P3-01 to P3-11** in
[decisions.md](decisions.md#phase-3-decisions), approved on 2026-11-13
([#46](https://github.com/Haiko-Innovations/orbit-watch/issues/46)). In short: a **TypeScript and React** single-page app built with
**Vite** and served by the Python service, wallets through **viem** and
**EIP-6963**, **Sign-In with Ethereum** with a session cookie, **Biome** and
**TypeScript 7**, end-to-end tests with **Playwright** against a local chain,
and **WCAG 2.2 AA**.

| Step | Content | Done when |
|---|---|---|
| ✅ **3.1 Web project and local stack** ([#47](https://github.com/Haiko-Innovations/orbit-watch/issues/47)) | `web/`: a TypeScript and React single-page app built with Vite, checked in the `tarkistus` check (Biome, type check, unit tests, build) with npm installs that run no scripts; `orbit-watch serve --web` serves it on the API's origin; a local stack in one command (Anvil, contracts, service, simulated parties); public pages for the network and the open requests. | CI builds and tests the app; a Playwright test opens it against the local stack; every page shows the testnet label. |
| ✅ **3.2 Sign in with a wallet** ([#48](https://github.com/Haiko-Innovations/orbit-watch/issues/48)) | Wallet discovery (EIP-6963), the right chain, Sign-In with Ethereum (ERC-4361) with a session cookie, sign-out; requesters and stations sign up themselves. | An end-to-end test signs in with a test wallet; replayed, expired and foreign messages are refused; no key or secret reaches the browser, tested. |
| ✅ **3.3 Transactions in the browser** ([#49](https://github.com/Haiko-Innovations/orbit-watch/issues/49)) | One flow for every prepared transaction: what it does, the wallet signs and sends, pending, confirmed or failed with explorer links; wrong chain, rejected signature and revert explained; balances and withdrawals. | A withdrawal runs end to end in the browser; each failure case is shown and tested. |
| ✅ **3.4 Requester view** ([#50](https://github.com/Haiko-Innovations/orbit-watch/issues/50)) | Create a request (target from the allow-list, window, deadline, delivery requirements), see the split and fees before funding, fund, follow and challenge, download the data and report, see payments and refunds. | End to end: a request created and funded in the browser is delivered and settled, and its report downloaded. |
| ✅ **3.5 Observer view** ([#51](https://github.com/Haiko-Innovations/orbit-watch/issues/51)) | Register a simulated station, browse and reserve open requests, upload observations (SHA-256 checked), see why a delivery was accepted or rejected, challenge, follow rewards. | End to end: reserve and deliver in the browser; accepted and rejected deliveries show their reasons. |
| ✅ **3.6 Reviewer view** ([#52](https://github.com/Haiko-Innovations/orbit-watch/issues/52)) | Assigned tasks, the report and checks, approve or reject with a reason signed as an EAS attestation, rewards and accuracy. | End to end: votes cast in the browser are attestations on the local chain, and the round settles. |
| ✅ **3.7 Administrator view and public pages** ([#53](https://github.com/Haiko-Innovations/orbit-watch/issues/53)) | Requests, deliveries, payments, errors and the event log; `tick`; the reviewer registry, the timelock's queue and Safe transactions to propose in the Safe's own app; simulator and demo datasets; the station quality meter and a public attestation browser. | End to end for the administrator; the view can do nothing the API refuses, tested; public pages work without signing in. |
| ✅ **3.8 Phase 3 demo** ([#54](https://github.com/Haiko-Innovations/orbit-watch/issues/54)) | The whole chain in the browser on Base Sepolia with a wallet per role, an accessibility review of every view, and the phase 3 summary. | The phase 3 completion criteria below are met; release 0.4.0. |

**Phase 3 completion criteria** ([P3-11](decisions.md#p3-11-phase-3-completion-criteria);
the starting plan gives none for phase 3):

1. The web application starts with the documented instructions, on a local
   chain and on Base Sepolia.
2. Each role signs in with its own wallet; no private key, seed phrase or
   server secret reaches the browser or the service, tested.
3. A requester creates, funds and follows a request, downloads its data and
   report, and sees payments and refunds in the browser.
4. An observer registers a simulated station, reserves a request, delivers
   and follows rewards in the browser.
5. A reviewer sees assigned tasks, signs votes with reasons as EAS
   attestations, and sees rewards and accuracy in the browser.
6. An administrator sees requests, deliveries, payments, errors and the event
   log, prepares reviewer changes for the Safe and the timelock, and starts the
   simulator, with no privilege the API does not give, tested.
7. Pending, confirmed and failed transactions are shown apart, with explorer
   links.
8. The station quality meter and the public attestation browser work without
   signing in.
9. The testnet label is visible on every page, and simulated data is labelled.
10. End-to-end tests of every role and accessibility checks of every view run
    in CI against a local chain.

### Phase 4: a public testnet service (target version 0.5.0)

Phase 4 puts the service and the web application online, so that observers
and requesters can try the whole chain with their own wallets without
installing anything. It is still the Base Sepolia testnet only, and everything
is still SIMULATED: no real money, no real observations. On the way, the
service learns to run on its own. It gets limits against abuse, a privacy
notice and terms, backups, monitoring and a review before it is announced.

The choices behind this plan are **decisions P4-01 to P4-13** in
[decisions.md](decisions.md#phase-4-decisions), proposed in [#67](https://github.com/Haiko-Innovations/orbit-watch/issues/67) and
waiting for approval. In short:
- **one small server in Finland** that runs only Orbit Watch, at a
  **subdomain of haikoinnovations.com** with **automatic HTTPS**;
- **one process with SQLite**, as now, which **runs on its own** with a
  dedicated RPC endpoint;
- **limits** without third-party CAPTCHAs, and a **privacy notice and terms**;
- **container images** deployed by digest, **daily backups** off the server,
  and **monitoring**;
- **only the verifier key** on the server.

| Step | Content | Done when |
|---|---|---|
| **4.1 The service runs on its own** ([#68](https://github.com/Haiko-Innovations/orbit-watch/issues/68)) | A background task follows the chain at an interval: it applies events, attests, settles and applies deadlines without `tick`, up to a confirmation depth; it resumes after a restart; a health endpoint and structured logs. | On a local chain a request settles, and another expires, with no API call in between; a restart in the middle resumes; tested. |
| **4.2 Limits and a dedicated RPC endpoint** ([#69](https://github.com/Haiko-Innovations/orbit-watch/issues/69)) | Limits per IP address and per party on sign-in, sign-up, new requests, uploads and the quality meter (`429` with `Retry-After`); the chain read through a dedicated RPC endpoint whose key is a server secret. | Every public and sign-in endpoint's limits tested; the RPC key never in a response, log or the browser, tested. |
| **4.3 Privacy notice and terms** ([#70](https://github.com/Haiko-Innovations/orbit-watch/issues/70)) | Both in English and Finnish, linked from every page; station coordinates to about a kilometre; deleting a station profile and ending sessions; log retention; the session cookie checked against the law, with its source. | The pages work without signing in; deletion and coordinate precision tested; the data inventory documented. |
| **4.4 Container image** ([#71](https://github.com/Haiko-Innovations/orbit-watch/issues/71)) | The web application and the service from the lock files, a base image pinned by digest, a non-root user, a read-only file system; built in CI, published on release tags with its digest. | CI builds the image and runs the end-to-end tests against it; no secret in the image, checked. |
| **4.5 Server, domain and TLS** ([#72](https://github.com/Haiko-Innovations/orbit-watch/issues/72)) | The server, the subdomain, Caddy with automatic HTTPS, a firewall, automatic security updates, a deploy script that runs an image by its digest. | The service answers over HTTPS, not yet announced; a deploy and a rollback done with the script. |
| **4.6 Backups, monitoring and runbooks** ([#73](https://github.com/Haiko-Innovations/orbit-watch/issues/73)) | Daily encrypted backups off the server, kept 14 days; an uptime check with alerts; disk and backup-age checks; a read-only mode; runbooks. | A restore drill passed; an alert reached the maintainer; the runbooks documented. |
| **4.7 Keys and the review before the launch** ([#74](https://github.com/Haiko-Innovations/orbit-watch/issues/74)) | The verifier key to the server and off the maintainer's machine; the Safe's signers as decided; a security checklist, a screen reader test by a person, a real wallet extension. | The review done; each finding fixed or recorded. |
| **4.8 Launch and phase 4 summary** ([#75](https://github.com/Haiko-Innovations/orbit-watch/issues/75)) | The service opens, with a short announcement for the maintainer to post; the phase 4 summary. | The phase 4 completion criteria below are met; release 0.5.0. |

**Phase 4 completion criteria** ([P4-13](decisions.md#p4-13-phase-4-completion-criteria),
proposed):

1. The service and the web application run publicly at their address over
   HTTPS, on Base Sepolia only, with the testnet label and the SIMULATED label
   on every page.
2. Requests are attested, settled and expired on time without anyone calling
   `tick`, and the service resumes after a restart, tested.
3. Every public and sign-in endpoint has documented limits, tested.
4. The privacy notice and the terms are linked from every page, and personal
   data, its retention and its deletion are documented and implemented.
5. The server holds only the verifier key; no secret is in the repository,
   the image or the browser, tested; the runbook for a leaked key is written.
6. A release is deployed from its image by digest with the documented
   script, and a rollback has been done.
7. Backups run every day off the server, and a restore drill has passed.
8. Monitoring alerts the maintainer when the service or its backups fail,
   tried once.
9. The review before the launch is done: the security checklist, a screen
   reader test by a person and a real wallet extension; each finding fixed or
   recorded.
10. Every CI check still passes, including every role's end-to-end test
    against a local chain; release 0.5.0.

## How we work

- One pull request at a time, branched from `main`, squash-merged by a
  maintainer after the `tarkistus` check passes. No stacked pull requests:
  with squash merges they conflict ([D-10](decisions.md#d-10-one-pull-request-at-a-time-on-main)).
- Every pull request with user-visible changes adds a line to the
  `Unreleased` section of the [changelog](../CHANGELOG.md).
- Releases follow [releasing.md](releasing.md): one minor version per phase
  while the version is 0.x, patch versions for fixes.

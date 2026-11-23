# Decision log

Decisions that shape Orbit Watch, with their reasons. Accepted decisions are
changed only by a new entry that replaces the old one. Proposed decisions wait
for a maintainer's approval, which is recorded here with the date. A pull
request that adds an accepted decision is approved by merging it.

Format: **Status** (proposed, accepted, replaced) · **Date** · context,
decision, consequences.

## Accepted decisions (phase 0)

### D-01 Python for the core

Accepted · 2026-11-11. The astronomy community works in Python (Skyfield,
sgp4, Astropy), so the core (`core/`) is Python ≥ 3.12. TypeScript and Solidity
come with the chain and the web in phases 2 and 3.

### D-02 An own lightweight JSON format, with IOD and TDM converters

Accepted · 2026-11-11. One versioned JSON format with a JSON Schema is the
internal format. Observers keep using IOD and CCSDS TDM through converters.
Every format document carries its own version; see
[releasing.md](releasing.md#what-has-a-version).

### D-03 Deterministic, versioned verification

Accepted · 2026-11-11. The same inputs give a byte-identical report. Reports
name the method version, its parameters and the SHA-256 of every input. CI
regenerates the committed demo output on two Python versions and requires an
exact match. Error texts that end up in reports must not depend on the Python
version.

### D-04 Simulated data is always labelled

Accepted · 2026-11-11. Every simulated document says so itself, and simulated
observations can never satisfy a real request. Simulated objects use catalogue
numbers 339001–339009 (Alpha-5 Z9001–Z9009), far from the numbers in use.

### D-05 Civilian objects only, through an allow-list

Accepted · 2026-11-11. Requests may only target objects on an allow-list built
from civilian groups of the public GP catalogue, minus military groups and
conservative name patterns. Classified objects have no public orbit and can
never be on it. Deny by default.

### D-06 No real orbit data in the repository

Accepted · 2026-11-11. CelesTrak states no redistribution terms for GP data,
which comes from the US Space Force. Users download it with `fetch-gp`, which
follows the CelesTrak usage policy: one request, no retries, no repeat download
within two hours.

### D-07 Supply-chain rules

Accepted · 2026-11-11. Actions pinned to commit SHAs, `permissions: contents:
read`, gitleaks in CI, Dependabot with a 14-day cooldown, and uv's
`exclude-newer = "14 days"` so the lock file follows the same rule. CI
installs only hash-checked locked dependencies.

### D-08 The residual check catches gross errors, not arcsecond accuracy

Accepted · 2026-11-11. Public GP orbits are good to about a kilometre, so the
per-observation limit includes an assumed 5 km reference error. The check
finds wrong objects, wrong times and gross errors. Station precision is the
job of the quality meter, which looks at scatter within passes.

### D-09 English first, Finnish translations of key documents

Accepted · 2026-11-11. Code, documentation, commits, issues and pull requests
are in English. README, CONTRIBUTING, the plan and the roadmap have Finnish
translations; if versions differ, English applies.

Replaced on 2026-11-17 by [D-41](#d-41-english-only): English only.

### D-10 One pull request at a time on main

Accepted · 2026-11-11. Stacked pull requests conflicted after squash merges
during phase 0. From now on each pull request branches from `main`, and the
next one starts after the previous one is merged.

## Phase 1 decisions

P-01 to P-07 were proposed for step 1.1 of the
[roadmap](roadmap.md#phase-1-requests-optimistic-verification-and-api-target-version-020)
and approved by the maintainer on 2026-11-11 in
[#10](https://github.com/Haiko-Innovations/orbit-watch/issues/10). Each lists the
alternative that was considered.

### P-01 The phase 1 API is written in Python

Accepted · 2026-11-11. The API can then call the verification engine directly, and
contributors need only one language until phase 2. Alternative: TypeScript,
which the web and chain parts will use later, but which would mean calling the
Python engine across a process boundary. The framework (for example FastAPI or
Litestar) is chosen at step 1.6 after checking their current documentation.

### P-02 SQLite with plain SQL migrations

Replaced by [P4-04](#p4-04-postgresql-wherever-the-service-keeps-state) · 2026-11-14
(accepted 2026-11-11). SQLite from the Python standard library, schema changes as numbered
SQL files, observation files stored by their SHA-256 in a local directory.
Nothing to install, easy to test, enough for a reference implementation.
Alternative: PostgreSQL from the start, which a public service would need later.
The storage layer stays small and uses portable SQL so that a later move is
easy. PostgreSQL is reconsidered when a public service is planned (see P-03).

### P-03 No public deployment in phase 1

Accepted · 2026-11-11. The phase 1 completion criteria need the API to work, not to be
online. A public service brings security, operations and data-protection work
(API keys, personal data of observers) that is better planned separately.
Alternative: a public demo instance on Haiko Innovations infrastructure.

### P-04 Role-scoped API keys

Accepted · 2026-11-11. One key per party and role: requester, station (delivery only),
reviewer (votes only) and administrator. Keys are stored only as hashes. A
station key can never move points. Signed votes come with EAS in phase 2.

### P-05 Pure state machine with an injected clock

Accepted · 2026-11-11. The lifecycle is a pure function from (state, event, time) to a new
state and effects, with no storage or network inside. Timeouts are tested by
moving the clock, never by waiting.

### P-06 Ledger points model

Accepted · 2026-11-11. Integer points (no decimals), a double-entry journal and an
idempotency key on every entry. The split is locked when a request is funded:
observer, reviewers, challenge-round reserve and platform fee (0 by default).
These are the same rules the testnet adapter must follow in phase 2.

### P-07 Default time limits, fixed in the request terms

Accepted · 2026-11-11. Challenge period 24 hours, reservation 72 hours, reviewer round
48 hours, embargo at most 30 days. The values are copied into each request's
terms when it opens, so later changes never affect existing requests.

### D-11 Lifecycle rules of step 1.1

Accepted · 2026-11-11 (with the pull request that implements step 1.1). Details
that P-01 to P-07 left open, chosen to keep the first version simple and strict:

- The delivery deadline defaults to the end of the window plus 24 hours, and
  automated verification must finish within 24 hours of a delivery, otherwise
  the request expires.
- An inconclusive automated result goes straight to a reviewer round instead of
  a challenge period.
- Only the requester and the observer can challenge. Reviewers can be neither.
- A rejected delivery ends the request; re-opening for other stations is
  decided in step 1.3.
- Requests can be cancelled only before a reservation.

### D-12 Settlement rules 1.0

Accepted · 2026-11-11 (with the pull request that implements step 1.2). The
plan fixed the dispute rule; these fix the rest, see [settlement.md](settlement.md):

- The deposit is observer reward + three reviewer rewards (the challenge-round
  reserve) + platform fee, locked at funding.
- The observer reward and the platform fee are paid only when a request is
  accepted.
- Each reviewer who cast a vote is paid, whatever the outcome; a reviewer who
  had not voted when the round was decided is not.
- Everything else goes back to the requester; nothing stays in escrow.
- The rules are a pure function shared by every adapter. An adapter is correct
  only if it passes the scenario suite.

### D-13 Optimistic verification rules

Accepted · 2026-11-11 (with the pull request that implements step 1.3). See
[optimistic-verification.md](optimistic-verification.md):

- Reviewers are pre-approved in a registry and declare affiliations. A round's
  three reviewers are the eligible ones with the lowest SHA-256 score over the
  request, the delivery and the reviewer; nobody chooses them and anyone can
  recompute the choice.
- Neither the requester, the observer, the challenger nor anyone affiliated with
  them can review.
- Challenges and votes must give reasons, which are part of the public record.
- One reviewer round per request. A rejected delivery ends the request; there
  is no re-opening in phase 1 (this settles the open point of D-11).
- The service settles every outcome as soon as it is reached.

### D-14 Reviewer accuracy

Accepted · 2026-11-11 (with the pull request that implements step 1.4). See
[reviewer-accuracy.md](reviewer-accuracy.md):

- Every assignment to a real round comes with one known-answer calibration task
  per reviewer, balanced between "approve" and "reject" answers.
- Real and calibration tasks share one queue and one shape, with opaque task
  ids; answers never reveal which was which.
- Calibration answers move no points and are not attested.
- Profiles show accuracy, approval rate and missed tasks, with flags. In
  phase 1 they inform the maintainers only; they do not change selection or
  payments.

### D-15 Storage consistency

Accepted · 2026-11-11 (with the pull request that implements step 1.5). See
[storage.md](storage.md):

- Each service call is one database transaction; the service keeps a working
  copy in memory and writes every change through.
- Any failure rolls the transaction back and reloads the state, so a refused
  call has no side effects. (A late challenge is now refused without settling
  the request; the next clock tick settles it.)
- One process per service directory, enforced with SQLite's exclusive locking.
- Files are kept by SHA-256 and never deleted; every read checks the hash.
- Migrations are checked by hash and never edited after they are applied.

### D-16 Starlette for the HTTP API

Accepted · 2026-11-11 (with the pull request that implements step 1.6). P-01
left the framework open. Checked on 2026-11-11: FastAPI 0.162 now depends on
Pydantic (a Rust extension), OpenTelemetry and further packages; Litestar 2.25
on about fifteen packages; Starlette 1.10 (BSD-3-Clause), which FastAPI is built
on, only on AnyIO. Orbit Watch already validates its documents with its own
JSON Schemas, so the API uses **Starlette**, served by **uvicorn**, as an
optional `api` extra. The cost: no generated OpenAPI page; the API is described
by hand in [api.md](api.md). Other rules:

- Every change needs an `Idempotency-Key`; the first successful response is
  stored in the same transaction; refused calls are not stored.
- One lock serialises all calls (one writer, working state in memory).
- Keys are `ow_` plus 256 random bits, stored as SHA-256, shown once.

### D-17 Data publication rules

Accepted · 2026-11-11 (with the pull request that implements step 1.8). See
[data-publication.md](data-publication.md):

- A request's files (request, observations, report) become public under
  CC BY 4.0 when the request is settled and its embargo (0–30 days) has passed;
  the embargo runs from settlement.
- Until then only the request's parties and administrators can read them;
  others get `404`.
- Calibration files are never public.
- Public files have permanent, content-addressed URLs and a licence link
  header. The licence is fixed to CC BY 4.0 in phase 1.

## Phase 2 decisions

P2-01 to P2-11 were proposed for the
[roadmap](roadmap.md#phase-2-settlement-on-a-testnet-target-version-030)'s
phase 2 in [#27](https://github.com/Haiko-Innovations/orbit-watch/issues/27)
and approved by the maintainer on 2026-11-11. The one open point, the
signers of the Safe in P2-07, was settled for the testnet in
[D-24](#d-24-the-base-sepolia-deployment). Facts were checked on
2026-11-11; the sources are listed under each decision. Versions and addresses
are settings, re-checked when they are used.

### P2-01 Base Sepolia as the testnet

Accepted · 2026-11-11. Base Sepolia (chain ID 84532) over Optimism Sepolia (11155420).
Both have EAS, Circle's testnet USDC and Safe 1.4.1. Base Sepolia has the newer
EAS deployment (1.2.0 against 1.0.2 on Optimism Sepolia), documents EAS as a
predeploy in its own protocol docs, and has more faucets, including one that
gives both testnet ETH and USDC. Optimism Sepolia is due for an interop upgrade
on 2026-12-03 (pending governance), which could change behaviour during the
phase. The public RPC endpoints of both are rate-limited and best-effort, which
is enough for a demo. Mainnet is never used: the code refuses any chain ID
other than 84532 or a local Anvil chain (31337).
Sources: [EAS deployments](https://github.com/ethereum-attestation-service/eas-contracts#deployments),
[Base: connecting](https://docs.base.org/base-chain/quickstart/connecting-to-base),
[Base: predeploys](https://docs.base.org/specifications/base-protocol/execution/predeploys),
[Base: faucets](https://docs.base.org/base-chain/tools/network-faucets),
[OP: faucets](https://docs.optimism.io/app-developers/tools-sdks/faucets.md),
[OP: interop notice](https://docs.optimism.io/notices/interop-prep.md),
[Safe deployments](https://github.com/safe-global/safe-deployments).

### P2-02 Circle's testnet USDC, no token of our own

Accepted · 2026-11-11. Deposits and rewards are in Circle's testnet USDC on Base Sepolia
(`0x036CbD53842c5426634e7929541eC2318f3dCF7e` at the time of checking; a
setting, and the decimals are read from the contract). Circle states that
testnet USDC has no financial value. Anyone can get 20 USDC per address every
two hours from Circle's public faucet, without an account. Alternative: a
worthless test token deployed by Orbit Watch, which would be easier to hand out
but would look like a token of our own, which the plan rules out.
Sources: [USDC addresses](https://developers.circle.com/stablecoins/usdc-contract-addresses),
[Circle faucet](https://faucet.circle.com/).

### P2-03 EAS attestations with two schemas

Accepted · 2026-11-11. Use EAS at its Base Sepolia predeploy (`EAS`
`0x4200000000000000000000000000000000000021`, `SchemaRegistry`
`0x4200000000000000000000000000000000000020`). Two schemas, registered once and
kept as settings:

- **automated result**: request ID, delivery SHA-256, report SHA-256, verdict,
  verification method and version; attested by the Orbit Watch verifier key;
- **review vote**: request ID, delivery SHA-256, approve or reject, SHA-256 of
  the reason; attested by the reviewer's own address.

Attestations are not revocable: a vote, once cast, stands. Anyone can read and
reuse them without Orbit Watch code, which is the point of using EAS.

### P2-04 Solidity with Foundry and OpenZeppelin Contracts

Accepted · 2026-11-11. Contracts in `contracts/` as a Foundry project; Foundry pinned to
1.8.6 (the newest release older than 14 days; Apache-2.0 and MIT) and
OpenZeppelin Contracts 5.7.0 (MIT), pinned by commit. Custom money-handling
code is kept to the escrow's own rules; transfers go through OpenZeppelin's
`SafeERC20`. CI installs Foundry with the SHA-pinned `foundry-rs/foundry-toolchain`
action (v1.9.2) inside the `tarkistus` check.
Sources: [Foundry releases](https://github.com/foundry-rs/foundry/releases),
[OpenZeppelin releases](https://github.com/OpenZeppelin/openzeppelin-contracts/releases).

### P2-05 One non-upgradeable escrow contract

Accepted · 2026-11-11. One escrow contract holds all requests, each with its own deposit,
locked split, deadlines and state. No proxy and no upgrade path: a new version
is a new contract, and existing requests settle in the old one. No function
lets anyone, administrators included, take a deposit; money leaves only by the
settlement rules. Settlement can be triggered by anyone once its conditions
hold, and it happens once. Alternative: a separate contract per request (clean
isolation, more gas and more moving parts).

### P2-06 The phase 1 rules, on chain

Accepted · 2026-11-11. The escrow implements settlement rules 1.0 exactly
([D-12](#d-12-settlement-rules-10)): observer reward and platform fee (0 by
default, recipient a setting) only when accepted, every completed review paid,
the rest refunded, nothing locked. Challenge, review and delivery deadlines are
checked against block time with the request's terms. The phase 1 scenario
suite is the acceptance test.

### P2-07 Reviewer registry behind a Safe and a timelock

Accepted · 2026-11-11. An on-chain registry of reviewer addresses, owned by an OpenZeppelin
`TimelockController` with a public minimum delay of 48 hours, whose only
proposer is a Safe multisig (2 of 3 signers). Every change is visible for two
days before it takes effect. **Open:** who the three signers are; decided before step 2.4.

### P2-08 Python adapter on web3.py

Accepted · 2026-11-11. The `evm-testnet` settlement adapter is Python, using web3.py 8.0
(MIT), so the request service stays one program. It passes the settlement
scenario suite against a local Anvil chain in CI. CI never talks to a public
testnet and holds no keys. Alternative: a TypeScript service with viem, which
phase 3's web application may use anyway, at the cost of a second runtime now.
Source: [web3.py on PyPI](https://pypi.org/project/web3/).

### P2-09 Keys and wallets

Accepted · 2026-11-11. Every party has its own address and signs its own transactions:
requesters fund, reviewers attest their votes. Orbit Watch never asks for seed
phrases or private keys. The command line signs with an encrypted keystore that
the user creates (for example with Foundry's `cast wallet import`), or prints an
unsigned transaction for an external wallet. The service holds one key, the
verifier key for automated attestations, read from a secret file outside the
repository. Keys for test automation are separate, used only on testnets and
funded only from faucets.

### P2-10 The chain decides payment status

Accepted · 2026-11-11. The chain, not the database, is the primary source of payment
status. The service mirrors it and shows pending, confirmed and failed
transactions apart, each with a block explorer link
(`https://sepolia.basescan.org`). Every chain-related output says "Base Sepolia
testnet, no real value".

### P2-11 Phase 2 has no public deployment

Accepted · 2026-11-11. As in phase 1 (P-03), the service runs locally; only the contracts
and attestations are public, on the testnet. A public demo service is decided
separately.

### D-18 Contract project details

Accepted · 2026-11-11 (with the pull request that implements step 2.1). See
[escrow.md](escrow.md) and [contracts/README.md](../contracts/README.md):

- Solidity 0.8.38 and the EVM version Cancun. Base Sepolia has had Ethereum's
  Dencun changes since 2024-02-21 (Ecotone) and Pectra's since 2025-04-17
  (Isthmus); Cancun is the older of the two, so the bytecode also runs on
  chains that do not have Pectra yet.
- On chain, a request is `keccak256` of its Orbit Watch request ID, and its
  terms are the SHA-256 of the frozen terms (`terms_sha256` in the lifecycle
  record), so the chain and the service refer to the same terms.
- The constructor refuses every chain except Base Sepolia (84532) and Anvil
  (31337); there is no switch to turn this off.
- forge-std and OpenZeppelin Contracts are git submodules pinned to release
  commits. Dependabot is not used for them, because it would move them to the
  newest commit of the default branch rather than to a release; they are
  updated by hand to releases at least 14 days old.
- The worthless `TestUSD` token exists only in the tests and is never deployed.
- Format (`forge fmt`), lint with warnings as errors (`forge lint`), build and
  tests, including fuzz and invariant tests, run in the `tarkistus` check.
  Lint findings that are intentional are silenced line by line with a reason.

### D-19 Settlement on chain

Accepted · 2026-11-11 (with the pull request that implements step 2.2). See
[escrow.md](escrow.md):

- **Pull payments.** Settling credits each party, and each party withdraws its
  own credit. USDC can block addresses; with direct transfers, one blocked
  recipient would make the whole settlement fail and lock the deposit, which
  the dispute rule forbids.
- **Lazy deadlines.** The status is computed at the current block time with
  every passed deadline applied, as in phase 1, so no keeper is needed and
  anyone can settle.
- **Whole seconds.** The time limits are passed in seconds when funding; the
  terms must convert to whole seconds.
- Cancelling settles at once. The platform fee recipient is fixed at
  deployment; without one, fees must be zero.
- Unfunded requests never touch the chain.
- Recording the automated result, challenges and votes are internal functions
  until step 2.3 connects them to attestations and the reviewer registry.
- The phase 1 settlement scenario suite is exported from Python to a fixture
  that the contract tests replay; a Python test keeps the fixture current, so
  the two implementations cannot drift apart unnoticed.

### D-20 Attestations and reviewer rounds on chain

Accepted · 2026-11-12 (with the pull request that implements step 2.3). See
[attestations.md](attestations.md):

- **The escrow is the EAS resolver** of both schemas and registers them itself,
  not revocable. EAS calls it with each new attestation, so a result or a vote
  the rules refuse is never created, and the public record holds only
  attestations that counted.
- **Readable fields.** The request ID is a string, and the verdict is `pass`,
  `fail` or `inconclusive`, so attestations can be read without Orbit Watch
  code. The recipient is the observer, and a vote references the automated
  result (`refUID`).
- **Reviewers are chosen on chain** from the reviewer registry by the phase 1
  rule (lowest score over the request, the delivery and the reviewer;
  Keccak-256 over addresses). Affiliations are kept in the registry. A removed
  reviewer's vote no longer counts. Challenges are plain transactions by the
  requester or the observer.
- **The verifier key is fixed at deployment.** A compromised verifier can only
  attest results that the requester or the observer can still challenge.
- **One attestation at a time.** Batches of two or more are refused. Nothing
  needs them, and it keeps loops over outside input out of the escrow.
- **Tested against Base Sepolia's EAS code.** The tests place the bytecode of
  the implementations behind Base Sepolia's EAS predeploys (EAS 1.4.1-beta.3,
  SchemaRegistry 1.3.1-beta.2, hashes checked) at the predeploy addresses. The
  interfaces come from eas-contracts v1.4.0 (MIT), a submodule pinned by
  commit and updated by hand like the others (D-18).
- Open: an observer could grind the delivered file to steer reviewer
  selection, as in phase 1.

### D-21 Governance of the reviewer registry

Accepted · 2026-11-12 (with the pull request that implements step 2.4). See
[who can change what](../contracts/README.md#privileges-who-can-change-what):

- The registry is owned by an OpenZeppelin `TimelockController` from its
  deployment, with the initial reviewers passed to its constructor. No single
  person ever owns it.
- Timelock: minimum delay 48 hours; the Safe is the only proposer and
  canceller; anyone may execute a change once its delay has passed; no
  administrator, so only the timelock itself (that is, the Safe and 48 hours)
  can change its delay or its roles.
- The Safe is a Safe 1.4.1 account (SafeL2, canonical deployment) with three
  signers and a threshold of two. The deployment function refuses any other
  threshold or number of signers.
- One deployment function (`script/OrbitWatchGovernance.sol`) is used by the
  tests and by the testnet deployment, so the tested set-up is the deployed
  one.
- The tests use the canonical Safe 1.4.1 bytecode from Base Sepolia (checked
  against the code hashes in safe-deployments and on chain) with test keys. The
  Safe code is LGPL-3.0 and is used only in tests.
- The three signers are not needed until the testnet deployment (step 2.7).
  This replaces "decided before step 2.4" in P2-07.

### D-22 Adapter interface 2 and the evm-testnet adapter

Accepted · 2026-11-12 (with the pull request that implements step 2.5). See
[evm-adapter.md](evm-adapter.md) and [settlement.md](settlement.md#adapter-interface):

- **Interface 2.** The phase 1 interface did not carry what a chain needs:
  the terms and split at funding, the delivery, the challenge and the time.
  Every mutating call may now carry `record`, the lifecycle record right after
  the event. `deliver` and `challenge` are new calls. The points ledger
  ignores the record and journals nothing for the two new calls, so phase 1
  behaves exactly as before (the phase 1 demo output is unchanged).
- **The chain applies the rules; the adapter checks them.** After each
  settlement the adapter compares the escrow's `Credited` events with
  `settlement_plan`, payout by payout (`chain_disagrees` otherwise). When the
  escrow chooses reviewers, the adapter checks them against the record.
- **web3.py 8.0 as the optional `evm` extra.** Nothing else imports it. The
  ABIs ship in the package and a test keeps them equal to the Foundry build.
- **Local test accounts** derived from party names, and moving the chain's
  clock to the record's time, are possible only on a local Anvil chain.
- The adapter keeps its idempotency keys in memory. The service persists them
  in step 2.6, which also makes the chain the source of reviewer rounds.

### D-23 The service on a chain

Accepted · 2026-11-12 (with the pull request that implements step 2.6). See
[chain-service.md](chain-service.md):

- **The parties sign; the service prepares.** For a funded request the API
  answers with the unsigned transactions (`202`), which the party signs with
  its own wallet or keystore and sends itself, and then reports by hash. They
  carry no nonce, gas or fees, so a replayed answer stays valid. The service
  never receives a party's key, and it trusts nothing a party reports: it
  reads every transaction and event from the chain. Alternative: the service
  relays signed transactions. It would still have to follow the chain for
  wallets that send on their own, and it would handle more than it needs.
- **The chain decides; the service follows.** Every API call first applies the
  escrow's new events to the lifecycle records, at their block times, one
  transaction at a time. The service's clock is the latest block's time. A
  request is on chain from a `Funded` event by its requester's wallet with its
  terms; an event that does not fit is a conflict, shown and never applied.
  Reviewer rounds come from the chain, and every settlement is compared with
  `settlement_plan`.
- **Wallets are registered with a signature**: EIP-191 over a message that
  names the party, the chain and the escrow. One wallet per party, one party
  per address; a wallet cannot be changed in phase 2. An address no party has
  registered appears as `wallet:<address>`.
- **The service holds only the verifier key**, from an encrypted keystore
  outside the repository. It attests automated results and settles reached
  outcomes when a transaction is reported and on `tick`; there is no
  background worker. A service directory follows one escrow on one chain from
  its first start.
- **What is off chain stays with the service**: observation files, reports and
  the texts of reasons. The chain holds their SHA-256.
- **Idempotency.** The API keeps every answer by its idempotency key (step
  1.6), transactions are tracked by hash, and the escrow itself refuses a
  second funding, settlement or withdrawal. The service does not use the
  adapter's in-memory keys (D-22).
- **Calibration tasks are visible on chain.** A real vote is a public
  attestation that the reviewer signs, so a reviewer can tell a real task from
  a calibration task. Calibration still measures accuracy, but no longer
  unseen. Hiding it would need calibration votes on chain, which would put
  made-up attestations in the public record.
- **Gas estimates get a 25 % margin**, in the service and in the user's
  wallet. An estimate is the exact minimum for the block it was made against,
  and a later block can cost a little more.
- Open: someone can fund an open request's ID first (the requester then
  creates it again under a new ID); chain reorganisations are not handled.

### D-24 The Base Sepolia deployment

Accepted · 2026-11-12 (with the pull request that implements step 2.7). See
[base-sepolia.md](base-sepolia.md) and
[`contracts/script/DeployOrbitWatch.s.sol`](../contracts/script/DeployOrbitWatch.s.sol):

- **One script deploys everything**, in order: a Safe 1.4.1 account (2 of 3)
  from the canonical Safe proxy factory, the timelock and the registry through
  `OrbitWatchGovernance` (D-21), and the escrow 1.0.0. The tests run the same
  function, and a local-chain test runs the script itself with
  `forge script --broadcast` and an encrypted keystore. The script refuses
  other chains, Safe code that is not the canonical 1.4.1 code, a token other
  than Circle's testnet USDC on Base Sepolia, fewer than three reviewers and a
  verifier that is also a signer or a reviewer.
- **A record, checked on chain.** The script writes the deployment record
  (`contracts/deployments/base-sepolia.json`); its `check` reads the record
  back and checks every contract against it: the Safe's signers and threshold,
  the timelock's delay and roles, the registry's owner and reviewers, the
  escrow's fixed settings, and that the deployer kept no privilege. The
  package carries the same record, so `orbit-watch serve --network
  base-sepolia` needs only the verifier key.
- **Settings.** Token: Circle's testnet USDC. Fee recipient: the Safe (the fee
  is 0 unless a request sets one). Initial reviewers: four SIMULATED reviewers
  without declared affiliations (`reviewer:sim-aino`, `-chen`, `-eero`,
  `-fatima`); reviewers with affiliations are added through the Safe and the
  timelock, together with their affiliations.
- **Keys on the testnet: one maintainer holds them all.** Orbit Watch has one
  developer in phase 2. The three Safe signers, the verifier, the deployer and
  the simulated parties are separate testnet-only keys, each an encrypted
  keystore on the machine that runs the service, funded only from faucets
  (P2-09). On the testnet, the 2-of-3 Safe is therefore a technical set-up,
  not a separation between people: one person can change the reviewer list,
  still publicly and only after 48 hours. **Before anything but a testnet,
  the signers must be three people.** The Safe can replace its signers itself
  (two signers approving) without a new deployment; a test shows this.
- **Source verification on Sourcify**, which needs no API key. Transaction
  links stay on Basescan (P2-10).
- Alternative: the deployment as a Python command next to the service. A
  Foundry script keeps deployment in the contracts project, where the tests
  already use the same governance function, and Foundry verifies the sources.

## Phase 3 decisions

P3-01 to P3-11 were proposed for the
[roadmap](roadmap.md#phase-3-web-application-target-version-040)'s phase 3,
the web application, in
[#46](https://github.com/Haiko-Innovations/orbit-watch/issues/46) and approved
by the maintainer on 2026-11-13, P3-10 as proposed: no public demo in phase 3.
Facts were checked on 2026-11-13; the sources are listed under each decision.
Versions are the newest releases at least 14 days old, and they are re-checked
when they are used.

### P3-01 One single-page app, served by the service

Accepted · 2026-11-13. The web application is one single-page app in
TypeScript and React, built with Vite, in `web/`. Its build is static files
that `orbit-watch serve` serves on the API's own origin, so there is no second
server, no cross-origin requests and one place for the rules: the Python
service stays the only backend (P-01, D-16). One app has the plan's role views
side by side, and a party sees the views of its role. Alternatives: Next.js,
which brings a server runtime and a second backend next to the Python API;
plain TypeScript without a framework, which is smaller but known to fewer
contributors.
Sources: [React](https://www.npmjs.com/package/react) 19.1.10 (19.3.1 since
2026-11-13, see D-28),
[Vite](https://www.npmjs.com/package/vite) 8.3.5,
[@vitejs/plugin-react](https://www.npmjs.com/package/@vitejs/plugin-react) 6.1.2
(MIT).

### P3-02 The npm supply chain

Accepted · 2026-11-13. The same rules as the rest of the repository (D-07),
for npm:

- **Node 26**, the Active LTS line ("Lithium"), pinned in `web/.nvmrc` and in
  CI through the SHA-pinned setup action.
- **npm** with its lockfile; CI installs with `npm ci --ignore-scripts`, so no
  package runs code at install time. Exact versions, each the newest release
  at least 14 days old; Dependabot watches `web/` with the 14-day cooldown.
- **Few dependencies**: React, viem and the build and test tools, nothing for
  state, routing or styling that a few lines of our own can do.
- **Biome** for lint and format, **TypeScript 7.0.2** for the type check.
  typescript-eslint, the usual linter for TypeScript, supports TypeScript
  below 6.1 only, so it would hold the type checker back a major version.
- Licences: MIT, Apache-2.0, or MIT OR Apache-2.0; the accessibility checker
  for tests is MPL-2.0 and is used only in development.

Sources: [Node.js releases](https://nodejs.org/en/about/previous-releases),
[npm ci](https://docs.npmjs.com/cli/v11/commands/npm-ci),
[TypeScript](https://www.npmjs.com/package/typescript) 7.0.2 (Apache-2.0),
[typescript-eslint](https://www.npmjs.com/package/typescript-eslint) 8.72.1
(peer dependency `typescript >=4.8.4 <6.1.0`),
[Biome](https://biomejs.dev/) 2.6.4 (MIT OR Apache-2.0).

### P3-03 Wallets through viem and EIP-6963

Accepted · 2026-11-13. The browser talks to wallets with
[viem](https://www.npmjs.com/package/viem) 2.57.13 (MIT) alone. Injected
wallets are discovered with EIP-6963, so several wallet extensions can live
side by side; the app asks the wallet to add or switch to Base Sepolia
(`wallet_addEthereumChain`, EIP-3085, whose status is Stagnant, so the app
also shows the network's settings for adding it by hand). The browser does
little on chain: connect, sign the sign-in message, and send the transactions
the API prepares (D-23). Alternatives: wagmi, which adds connectors, caching
and a query library the app does not need; WalletConnect for mobile wallets,
which needs a project ID from the Reown dashboard, an account with a third
party. Both can come later.
Sources: [EIP-6963](https://eips.ethereum.org/EIPS/eip-6963) (Final),
[EIP-3085](https://eips.ethereum.org/EIPS/eip-3085) (Stagnant),
[viem SIWE utilities](https://viem.sh/docs/siwe/utilities/createSiweMessage),
[Reown AppKit](https://docs.reown.com/appkit/overview).

### P3-04 Sign in with the wallet

Accepted · 2026-11-13. A party signs in with its registered wallet by
Sign-In with Ethereum (ERC-4361, Final). The service writes the message, with
its own domain, the chain, a single-use nonce and an expiry; the wallet signs
it; the service checks the ERC-191 signature against the party's registered
wallet and sets a session cookie that scripts cannot read (HttpOnly,
SameSite=Strict, Secure outside localhost). Requests that change anything also
need a matching `Origin`. Sessions expire and can be ended. Only externally
owned accounts in phase 3: ERC-4361 asks ERC-1271 for contract accounts, which
needs a call to the chain and comes later. The API keys (P-04) stay for the
command line and automation. Alternative: pasting an API key into the browser,
which keeps a long-lived secret in the page.
Source: [ERC-4361](https://eips.ethereum.org/EIPS/eip-4361).

### P3-05 Parties in the browser

Accepted · 2026-11-13. One wallet belongs to one party, as in phase 2. On the
testnet, **requesters and stations sign up themselves** in the browser: they
choose a party ID, and their wallet's signature registers it. **Reviewers**
are added by an administrator, and the escrow chooses them from the on-chain
registry, which only the Safe and the timelock change (D-21). **Administrator
parties** are created only on the server's command line
(`orbit-watch keys create`), never through the web. A public deployment would
need limits on sign-up (P3-10).

### P3-06 The browser holds no privileges

Accepted · 2026-11-13. The web application uses the documented API and the
sign-in endpoints, nothing else; every rule stays in the service and the
contracts, so the browser cannot do what the command line cannot. Before the
wallet signs, the app shows what a prepared transaction does: the contract,
the function and the amounts, read from the call data rather than taken on
trust from the server. No server secret reaches the browser: not the verifier
key, not API keys, not other parties' files before publication (D-17). The
chain stays the source of payment status (P2-10), with explorer links.

### P3-07 Governance through the Safe's own app

Accepted · 2026-11-13. The administrator view shows the reviewer registry, the
timelock's queued operations with their ready times, and the reviewer changes
as Safe transactions (target, call data and the decoded call) to propose and
sign in the Safe's own app, for example with its Transaction Builder. Orbit
Watch uses no Safe API key and holds no signer key; the timelock's 48 hours
stay public. The Safe Transaction Service runs on Base Sepolia and already
lists the deployed Safe (2 of 3, 1.4.1+L2).
Sources: [Safe Transaction Service on Base Sepolia](https://api.safe.global/tx-service/basesep/api/v1/about/),
[Transaction Builder](https://help.safe.global/en/articles/40841-transaction-builder).

### P3-08 Tests

Accepted · 2026-11-13. Unit tests with Vitest; end-to-end tests with
Playwright for every role against a local stack (Anvil, the contracts, the
service), with a test wallet injected into the page as an EIP-1193 provider
that signs with Anvil's test keys; accessibility checks with axe on every view.
All of it runs in the `tarkistus` check; CI never touches a public testnet and
holds no keys (P2-08).
Sources: [Vitest](https://vitest.dev/) 4.1.12 (5.0.5 since 2026-11-13, see D-28) (MIT),
[Playwright](https://playwright.dev/docs/intro) 1.64.1 (Apache-2.0),
[axe-core for Playwright](https://github.com/dequelabs/axe-core-npm) 4.14.0
(MPL-2.0, development only).

### P3-09 Accessibility, language and labels

Accepted · 2026-11-13. WCAG 2.2 level AA: every view works with the keyboard
and a screen reader, in light and dark colours. The interface is in English
(D-09), with its strings in one place so that a Finnish translation can follow.
Every page shows "Base Sepolia testnet, no real value", and simulated data says
so wherever it appears (D-04).
Source: [WCAG 2.2](https://www.w3.org/TR/WCAG22/).

### P3-10 No public deployment in phase 3

Accepted · 2026-11-13. As in phases 1 and 2 (P-03, P2-11), the service and the
web application run locally; the contracts and attestations are public on the
testnet. A public demo is its own decision, because it needs hosting, TLS,
rate limits and limits on sign-up, and the verifier key away from the
maintainer's machine (D-24). The maintainer chose no public demo in phase 3.

### P3-11 Phase 3 completion criteria

Accepted · 2026-11-13. The starting plan gives none for phase 3. Phase 3 is
done when:

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

### D-25 The web project

Accepted · 2026-11-13 (with the pull request that implements step 3.1). See
[web.md](web.md):

- **`web/`** is a Vite project in TypeScript and React (P3-01). Its build,
  `web/dist`, is static files; `orbit-watch serve --web web/dist` serves them
  at `/` next to the API at `/v1/`, so the browser talks to one origin.
- **Pages behind the hash** (`#/requests`): the service serves one
  `index.html` and needs no routing rules, and every page has an address that
  can be shared. A page change moves keyboard focus to the new page's heading.
- **A strict content security policy** on every response: the page runs only
  its own scripts and styles, connects only to its own origin, and cannot be
  framed. The build has no inline scripts. Wallet extensions inject their
  providers themselves, and EIP-6963 wallet icons are `data:` URLs, which the
  policy allows for images.
- **No state, routing or styling libraries**: a small hash router, a resource
  hook and plain CSS with colour tokens for light and dark (P3-02, P3-09).
  The interface's texts live in `web/src/strings.ts`.
- **A local stack in one command** (`core/tests/local_stack.py`): a local
  Anvil chain with Base Sepolia's EAS code and fresh contracts, the service on
  it, SIMULATED parties with public test keys and registered wallets, and
  SIMULATED requests. Its clock starts at 2026-11-01 12:00 UTC, before the
  requests' observation window. Development (`npm run dev`, which forwards `/v1` to it) and the end-to-end
  tests use it. It lives with the tests because it needs the repository: the
  contracts' build and the test fixtures.
- **npm's `min-release-age`** is 14 days in `web/.npmrc`, so not only the
  direct dependencies but their dependencies too are at least 14 days old when
  the lock file is made. Only React, React DOM and scheduler reach the
  browser; everything else is a development tool. Vite's CSS minifier
  (lightningcss) and axe are MPL-2.0, used only at build and test time.

### D-26 Open requests are public

Accepted · 2026-11-13 (with the pull request that implements step 3.1).
`GET /v1/public/open-requests` lists, without a key, every request that
invites observers: opened or funded, and not reserved. It shows the request
document, the terms, the reward split once funded, the requester and the
simulated flag. A request is opened to be seen by observers, its deposit is
public on chain anyway, and an observer should find work before signing up
(the plan's observer view starts with "browses open requests"). Before, any
key could list every request, but nobody without one. Drafts stay the
requester's own, and nothing delivered appears: the observation file and the
report still follow the publication rules (D-17).

### D-27 Signing in with a wallet

Accepted · 2026-11-13 (with the pull request that implements step 3.2). Code:
[`core/src/orbit_watch/api/sessions.py`](../core/src/orbit_watch/api/sessions.py),
[`web/src/wallet/`](../web/src/wallet):

- **The service writes the whole message** (ERC-4361):
  - its own origin, with the scheme always written, because a wallet assumes
    https without one;
  - the wallet's EIP-55 address and a statement naming the party ("Sign in to
    Orbit Watch as station:SIM-ESPOO. Testnet only, no real value. Signing
    sends no transaction.");
  - the chain ID, a 17-character single-use nonce, and an expiry five minutes
    after it is issued.

  A message works once, only from the origin it was written for, and only with
  its address's signature (ERC-191). A signature that fails leaves the message
  usable for its owner.
- **The page checks the message before the wallet sees it**: viem's
  `validateSiweMessage` against the page's own host and scheme, the account
  and the time. A message for another site is never shown for signing.
- **Origins are configured, not taken from the request**:
  - `orbit-watch serve --origin URL`, repeatable, by default
    `http://HOST:PORT`, plus `http://localhost:PORT` when the service listens on
    127.0.0.1;
  - the local stack also allows Vite's development server.

  The `Host` header is never trusted, so a phishing site's server cannot have a
  message written for its own domain.
- **Sessions**:
  - a random cookie `ow_session` (`HttpOnly`, `SameSite=Strict`, `Path=/`,
    `Secure` on https), stored only as its SHA-256;
  - they last 12 hours and end on sign-out;
  - a change made with a session also needs the `Origin` it was signed in on;
  - `GET /v1/session` answers `null` when nobody is signed in, so a page does
    not log an error on every load;
  - sessions and messages use wall-clock time, also when the service follows a
    local chain whose clock is elsewhere.
- **Signing up** (P3-05):
  - requesters and stations only, named `requester:<name>` or
    `station:<name>` (2 to 63 letters, digits, dots, dashes or underscores);
  - a name that has an API key or a wallet is taken;
  - the signed sign-up message names the party and is kept with the wallet
    (migration 0004), so the registration stays verifiable like one made with
    `orbit-watch wallet register`.
- **The wallet code loads only with the sign-in page**, so viem does not
  slow down the public pages.
- **The local stack's chain listens on port 8545** by default, where wallets
  and viem expect a local chain 31337, so a real wallet can be pointed at it.
- **Limits**:
  - only externally owned accounts sign in;
  - revoking a party's API keys does not end its sessions;
  - asking for messages has no rate limit.

  The last two matter only for a public deployment (P3-10).

### D-28 Transactions in the browser

Accepted · 2026-11-13 (with the pull request that implements step 3.3). Code:
[`web/src/chain/`](../web/src/chain),
[`web/src/components/TransactionFlow.tsx`](../web/src/components/TransactionFlow.tsx):

- **The page reads what it is asked to send** (P3-06). For each transaction
  the API prepares, the page decodes the call data with the contracts' own
  ABIs, taken from the files the Python service uses
  (`core/src/orbit_watch/chain/abi/`, which a test keeps equal to the
  Foundry build). It shows the result in words: the contract, the function,
  and the amounts from the call itself, for example "Deposit 1.3 TESTUSD for
  SIM-REQ-3001" with the split.
- **It sends nothing outside these limits.** Before the wallet sees a
  transaction, the page refuses it unless:
  - it is for the service's chain and from the signed-in wallet;
  - it carries no ether;
  - it goes to the escrow (a call this party makes), to the token (`approve`
    for the escrow only), or to EAS (a vote, by its schema);
  - every call about a request names the request shown, as
    `keccak256(request ID)`.
- **One flow for every transaction**:
  1. the wallet signs and sends each transaction in order;
  2. the page reports the hash to the service (`POST /v1/transactions`),
     which waits for the chain and does its own part;
  3. the page shows the result: pending, confirmed or failed, with an
     explorer link on Base Sepolia.

  A transaction that does not confirm stops the ones after it.
- **Failures are explained, not hidden**:
  - a declined wallet prompt ("Nothing was sent");
  - a wallet on another network that does not switch;
  - a wallet whose account is not the signed-in one;
  - a transaction the chain refuses, named from the escrow's own error when
    the wallet passes it on, for example "there is nothing to withdraw any
    more", when another tab withdrew first;
  - a transaction that failed after mining, with the service's reason.
- **The wallet is remembered in memory only.** After a reload the page asks
  which wallet to send with, and nothing about wallets is stored in the
  browser. The wallet code loads only when a transaction is to be sent.
- **The local stack seeds a request that ran its course** (SIM-REQ-3000), so
  that a station and the requester have credit to withdraw. Seeding moves the
  local chain's clock to 2026-11-02 05:01 UTC.
- **Correction to P3-01 and P3-08.** The versions there were picked as the
  most recently published release at least 14 days old, not the highest
  version. React 19.1.10 and Vitest 4.1.12 were published on the same days as
  the higher React 19.3.1 and Vitest 5.0.5. Dependabot proposed both
  (#57, #58), and they were merged on 2026-11-13. Versions are now picked as
  the highest version published at least 14 days ago.

### D-29 The requester's view

Accepted · 2026-11-13 (with the pull request that implements step 3.4):

- **Pages**:
  - **Your requests** (`#/my-requests`): the requests the party created.
  - **New request** (`#/new-request`): the target from the allow-list, the
    window and the deadline in UTC, the requirements and the time limits. It
    creates a draft.
  - **A request's page** (`#/requests/<id>`):
    - its status in words and what happened so far;
    - the terms, and the files with download links;
    - the payments and the chain events;
    - the requester's actions: publish, fund, cancel and challenge.
- **The split before anything is signed.** The fund form shows the deposit
  (observer reward + three review rewards + platform fee) and what each part
  is for. The transaction flow then reads the same amounts from the call data
  of `approve` and `fund` (D-28).
- **The allow-list is public**: `GET /v1/public/targets` (D-05: the list is
  configuration, not a secret). `GET /v1/requests` also gives each request's
  requester and title, so a party can find its own.
- **A requester challenges a passed result** (the form appears only then): a
  failed result already favours the requester. An observer challenges a
  failed one in step 3.5.
- **Someone who is not a party** sees a request's terms and status (any key or
  session may read them, as since phase 1), but not its documents and files
  until they are published (D-17). The page says so instead of failing.
- **Fresh test observations.** The service rightly refuses observations that
  were delivered before, so the local stack writes fresh SIMULATED good
  observations by SIM-ESPOO (`datasets/`, listed in `local-stack.json`). The
  end-to-end tests run the stack in `web/.e2e-stack` and read the parties'
  keys there, to play the station and the administrator through the API until
  their views exist.

### D-30 The observer's view

Accepted · 2026-11-13 (with the pull request that implements step 3.5):

- **A station registers its profile**: where it is and what it observes with
  (format `orbit-watch/station-profile` 1.0, migration 0005).
  - `PUT /v1/stations/{party}/profile` stores it. Its station ID must be the
    party's own name (`station:SIM-ESPOO` → `SIM-ESPOO`), the ID that its
    observation files carry.
  - Only the station and administrators read it, because the coordinates are
    personal data. They become public anyway in every observation file after
    settlement, which the page says.
  - The page starts from one of the built-in SIMULATED instruments
    (`GET /v1/public/station-templates`), with the station's own name and
    place.
- **SIMULATED observations on request**: `POST /v1/requests/{id}/simulate`.
  - Without a telescope, the station that reserved a request gets observations
    of its target in its window, simulated with its own profile. The
    simulator labels them SIMULATED.
  - Each call is a new draw, because the service refuses data delivered
    before. The call changes nothing; the station delivers the file like any
    other.
  - Two stations at one place simulate near-identical observations, which
    the duplicate check refuses as resubmitted data. That is why a profile
    keeps the station's own place.
  - This is how the plan's "registers a (simulated) station" works in the
    browser, and why everything still runs without a real telescope.
- **Reserve and deliver in the browser**:
  - **Reserving**: funded open requests get a Reserve button for stations.
  - **Delivering**: the page reads the chosen file and computes its SHA-256,
    sends it with `Content-SHA256` (the service checks it), and shows it.
  - **Checking the call data**: the transaction flow refuses a `deliver` call
    whose SHA-256 is not the file's, so the chain records exactly the file the
    station chose (extends D-28).
- **Why a delivery passed or failed**: the request's parties see the automated
  verification's checks with their reasons. An observer may challenge a
  failed result; a requester a passed one (D-29).
- **The request document is readable by more parties** than D-17 said: any
  party while the request is opened or funded (as D-26 lists it publicly), and
  the station that reserved it, which needs it to observe. Observations and
  reports still follow D-17.
- **A wallet without ETH** gets a plain message instead of the node's error:
  get some from a faucet. The end-to-end tests give new local wallets test
  ETH, as a faucet would.
- **The end-to-end tests now wait for the local stack's "Ready" line only.**
  Playwright takes whichever of a health URL and the line comes first, and
  the URL answers before the seeding is done. Since step 3.1 the first tests
  could therefore start too early; the slow seeding of step 3.4 made it show.

### D-31 The reviewer's view

Accepted · 2026-11-13 (with the pull request that implements step 3.6):

- **Pages**:
  - **Your review tasks** (`#/tasks`): the open tasks with their deadlines,
    automated results and challenge reasons, and the reviewer's record. The
    record shows calibration accuracy, votes in real rounds apart from all
    answers, agreement with decided outcomes, and the notes calibration raises
    (D-14).
  - **A task's page** (`#/tasks/<id>`): the request, why it was challenged,
    the three files to download, the automated verification check by check,
    and the answer: approve or reject, with reasons.
- **Real and calibration tasks look alike** until the answer, as since phase
  1. The answer then differs:
  - a vote in a real round is the reviewer's own EAS attestation, prepared
    by the service (`202`) and signed in the reviewer's wallet;
  - a calibration answer is recorded at once (`200`).

  So a reviewer can tell them apart after answering. This is the open point
  of D-23 and stays for a later phase.
- **The vote is read from its call data before the wallet sees it**:
  - the EAS schema is the vote schema;
  - the request ID in the attestation is the prepared request's;
  - the answer is the one chosen;
  - the reasons' SHA-256 is the one the page computes from the reasons sent;
  - the delivery's SHA-256 is the task's observation file.

  Anything else is refused (extends D-28).
- **The local stack seeds SIM-REQ-3006 in review**: SIM-ESPOO delivered
  fresh good observations, the requester challenged them, and the escrow
  chose three of the six SIMULATED reviewers. The end-to-end tests let two of
  them vote in the browser, and the round settles.

### D-32 The administrator view and the public pages

Accepted · 2026-11-13 (with the pull request that implements step 3.7):

- **Administration** (`#/admin`, administrators only):
  - every request with its status, observer, automated result, votes,
    outcome and payments;
  - errors: the chain conflicts and the failed transactions;
  - every watched transaction, and the escrow's events the service applied,
    newest first;
  - `tick`;
  - the reviewer registry and its governance (below);
  - the simulator and the six demo datasets, as SIMULATED files to download.
    Nothing is kept.
- **The view uses the API only**, and the API checks the role of every call,
  so the view can do nothing the API refuses. The end-to-end tests check this
  with a non-administrator's session. A page for someone else shows a note
  instead of controls.
- **Governance stays with the Safe.** As on Base Sepolia (step 2.7), a
  timelock owns the registry and a 2-of-3 Safe is its only proposer. The
  service never holds their keys and never sends their transactions. It
  prepares:
  - `schedule` and `execute` call data for adding or removing a reviewer,
    with the timelock operation's ID and a random salt;
  - a batch file for the Safe app's Transaction Builder, with the checksum the
    builder checks (its `serializeJSONObject`, Keccak-256, without the
    batch's name), tested against the builder's own test value;
  - links to the Safe app on Base Sepolia (`?safe=basesep:<address>`).

  The Safe's owners sign and execute in the Safe app. After the delay anyone
  may execute (`execute` with the operation's data, or the execute file in the
  Transaction Builder).
- **The timelock's operations are read from its events.** The service reads
  the timelock's logs in the same `eth_getLogs` calls as the escrow's, and
  keeps `CallScheduled`, `CallSalt`, `CallExecuted` and `Cancelled`
  (migration 0006). The timelock's `getOperationState` gives each operation's
  state. Operations scheduled before the service started following the chain
  do not show; the Safe app shows every Safe transaction. The escrow's and the
  timelock's `Cancelled(bytes32)` share a topic, so logs are told apart by
  their address. `serve --network` takes the Safe from the deployment record;
  `serve --safe` names it otherwise.
- **The local stack governs like Base Sepolia.** A Safe 1.4.1 of three LOCAL
  TEST signers (two must sign), a timelock that waits 60 seconds instead of 48
  hours, and the registry owned by the timelock. The administrator has a
  wallet and signs in like everyone else. The end-to-end test downloads the
  batch file, has the Safe execute it, waits out the delay on the chain's
  clock, executes with the downloaded execute file, sees the reviewer
  added, and removes it again.
- **Public pages, no sign-in**:
  - **Attestations** (`#/attestations`): every automated result and vote of
    the requests the service follows, with EAS Scan links on Base Sepolia
    (`base-sepolia.easscan.org/attestation/view/<uid>`). Each attestation is
    read from the chain once and kept (migration 0006). Attesters are shown
    by address, as on the chain; a reviewer's party name is not.
  - **Station quality meter** (`#/quality`): an observation file in, the
    quality report out (`POST /v1/public/quality`). The file is not kept,
    it is at most 2 MiB, and scoring does not hold the service's lock.


### D-33 The phase 3 demo and the accessibility review

Accepted · 2026-11-13 (with the pull request that implements step 3.8):

- **The demo is a recorded browser run on Base Sepolia**
  ([`web/demo`](../web/demo), `npm run demo:base-sepolia`). It is not part of
  CI, because it uses the maintainer's testnet keys (D-24) and spends testnet
  ETH. It writes [`examples/phase3`](../examples/phase3): a transcript with
  every transaction on the block explorer and every attestation on EAS Scan,
  a summary, screenshots and the Safe batch file. Videos of every role's
  browser stay in the run's directory, outside the repository, for their
  size.
- **Each role has its own wallet**: the end-to-end tests' EIP-6963 wallet,
  holding the role's testnet key. The test runner opens the key from its
  encrypted keystore. The page asks the wallet to sign and send, and the key
  reaches neither the page nor the service, as in criterion 2 of P3-11. A
  wallet extension such as MetaMask or Rabby works the same way through
  EIP-6963, but the recorded run does not use one.
- **Who comes how**:
  - The requester and the station sign up in the browser.
  - The administrator registers the reviewers' wallets with API keys (P3-05).
    It has a testnet wallet of its own, which needs no ETH to sign in.
- **The Safe's part is signed outside the Safe app.** Two of the Safe's three
  owners sign the downloaded batch file's transaction, and one executes it.
  Their keys sign in the test runner, as their wallets would in the Safe app;
  the Safe app's own pages are not part of the run. The recorded run's
  operation adds `reviewer:sim-dana` to the registry, and an earlier run's
  adds `reviewer:sim-bertil`, as phase 2 planned (D-24). Each is ready 48
  hours later, and then anyone may execute it.
- **The accessibility review is a test**
  ([`web/e2e/a11y.spec.ts`](../web/e2e/a11y.spec.ts),
  [accessibility.md](accessibility.md)). It opens every view as the role that
  uses it, and checks:
  - axe in light and dark colours;
  - the keyboard alone: every stop shown with a focus indicator, no trap, and
    the skip link to the heading;
  - reflow at 320 CSS pixels (WCAG 1.4.10).

  CI runs it on every pull request. Screen readers, other browsers and tests
  with users are open (P3-10).

## Phase 4 decisions

P4-01 to P4-16 were proposed for the
[roadmap](roadmap.md#phase-4-a-public-testnet-service-target-version-050)'s
phase 4, a public testnet service, in
[#67](https://github.com/Haiko-Innovations/orbit-watch/issues/67), and approved
by the maintainer on 2026-11-14. The service starts at Vercel's own address
(P4-03), and the Safe's keys stay with the maintainer until there is a
community to share them with (P4-11). They were discussed with the maintainer on
2026-11-14: hosting on Vercel and Neon, PostgreSQL everywhere the service keeps
state, a design that can move to other hosts, and a path that stays open to a
network run by the community
([decentralisation.md](decentralisation.md)). Facts were checked on
2026-11-14; the sources are listed under each decision. Versions are chosen,
and checked, when they are used.

### P4-01 A public sandbox on the testnet

Accepted · 2026-11-14. Phase 4 puts the service and the web application
online, so that people can try the whole chain with their own wallets without
installing anything. Everything else stays as it is:
- Base Sepolia only: no mainnet, no real money, no token of our own;
- everything SIMULATED: the built-in simulated objects, reference orbits,
  allow-list and stations.

Real reference orbits and real observations are not in phase 4. They need
decisions of their own: the data source's terms, licences, and the personal
data of real observers. They are left for a later phase.

### P4-02 Hosting on Vercel and Neon

Accepted · 2026-11-14. The service runs as a Python function on Haiko
Innovations' Vercel Pro team, and its database is a Neon PostgreSQL project
from the Vercel Marketplace. Pro is already paid for other projects, and its
monthly credit covers a sandbox's functions. Neon's Free plan is enough if
the scheduled follower runs every 15 minutes (P4-06). Launch is pay as you go
and is taken only when needed.

Why not as it is: the service was one long-running process with SQLite and
files on its own disk, its whole state in memory behind one lock, and a key in
a keystore file. Vercel functions are short-lived, run many instances at once
and have a read-only file system, so P4-04 to P4-06 change the service first.

Alternatives:
- **A small server of our own in Finland**: almost no code change, but a
  monthly fee and server upkeep (updates, firewall, TLS, disk). It stays
  possible at any time (P4-05).
- **Spark through Tailscale Funnel**: no cost, but the machine holds other
  projects' secrets, and Funnel serves only `*.ts.net` names and is in beta.

Sources:
- [Vercel Python runtime](https://vercel.com/docs/functions/runtimes/python)
  ("run ASGI … and WSGI"; Python 3.12 to 3.14);
- [Vercel runtimes](https://vercel.com/docs/functions/runtimes)
  ("read-only filesystem with writable `/tmp`");
- [Vercel function limits](https://vercel.com/docs/functions/limitations)
  (4.5 MB request and response bodies; 500 MB Python bundles; 300 s by
  default and 800 s at most on Pro);
- [Vercel Pro](https://vercel.com/docs/plans/pro-plan) ("$20 in monthly
  credit");
- [Neon plans](https://neon.com/docs/introduction/plans) (Free: 100 CU-hours
  per project per month, scale to zero after 5 minutes, 6 hours of restore)
  and [pricing](https://neon.com/pricing) (compute is suspended until the next
  billing period when the hours run out; Launch at $0.106 per CU-hour with no
  minimum).

The service's dependencies take 122 MB, measured on 2026-11-14.

### P4-03 Vercel's own address first

Accepted · 2026-11-14. The service starts at the address Vercel gives the
project (`<project>.vercel.app`), served over HTTPS. "Orbit Watch" is a working
name, and its trademark and domain checks are not done. So it gets no domain of
its own; a subdomain of `haikoinnovations.com` can follow when the maintainer
wants one. The web application and the API stay on
one origin: the static build at `/`, and the function at `/v1/`. So the
content security policy keeps `connect-src 'self'` (D-25).

### P4-04 PostgreSQL wherever the service keeps state

Accepted · 2026-11-14. Replaces
[P-02](#p-02-sqlite-with-plain-sql-migrations) once accepted. P-02 said that
"PostgreSQL is reconsidered when a public service is planned". This is that
plan.

The service keeps its state, its files included, in PostgreSQL, everywhere:
in production, in the local stack and in the tests. There is one backend and
no choice of two:
- the stateless service relies on PostgreSQL's locks and concurrent
  transactions, which SQLite cannot test;
- two backends would double every change.

What this means:
- **Files in the database.** Requests, observations and reports are a few
  kilobytes each.
- **The open core needs no database.** The command-line tools for the
  format, verification, the simulator, the quality meter and the demos work
  as now.
- **The local stack starts PostgreSQL itself** in a container, as it starts
  Anvil.
- **Tests that need a database are skipped without one.** CI always runs
  them (`ORBIT_WATCH_PG_TESTS=1`), as it does the chain tests.
- **No migration of old directories.** The testnet's earlier service
  directories are not moved: their state comes from the chain, and their
  demos are in `examples/`.

### P4-05 Portable by design

Accepted · 2026-11-14. Moving from Vercel and Neon to a server of our own, or
to a network of community nodes later
([decentralisation.md](decentralisation.md)), must not need code changes:
- **One plain ASGI application.** Its settings come from environment
  variables (`DATABASE_URL`, the RPC endpoint, the verifier key).
- **Vercel only in thin files:** `vercel.json` (routes, the schedule) and a
  few-line entry file that calls `create_app()`.
- **The follower is an authenticated HTTP call.** The Vercel schedule makes
  it, a timer can, and `orbit-watch serve --follow` runs the same loop in the
  process.
- **Limits per IP address and per party live in the database too**, so they
  hold without Vercel's firewall.
- **Standard PostgreSQL only**, through psycopg, with nothing specific to
  Neon. Locks are transaction-scoped advisory locks
  (`pg_advisory_xact_lock`), which work behind a connection pooler.
- **CI builds the container image on every pull request** and runs the
  end-to-end tests against it, so the server path stays tested.

### P4-06 The service runs on its own

Accepted · 2026-11-14. The service has no state outside PostgreSQL. Each call
works in a transaction, reads what it needs from the database and, to change
anything, takes the same advisory lock. So two instances never apply one
change twice.

A follower does the service's own work without anyone calling `tick`:
- it applies the escrow's events;
- it attests results;
- it settles decided requests;
- it applies passed deadlines.

The follower runs on a Vercel schedule every 15 minutes, which keeps Neon's
Free plan within its hours (about 61 of 100 CU-hours a month). It also runs
on every call, as now. It reads only up to a confirmation depth behind the
newest block, and a health endpoint tells monitoring whether it keeps up.
Source: [Vercel cron jobs](https://vercel.com/docs/cron-jobs/usage-and-pricing)
(Pro: "Once per minute", 100 jobs; marked as legacy and moving to Schedules,
which is used where available).

### P4-07 A dedicated RPC endpoint for the service

Accepted · 2026-11-14. Base's public endpoints "are free, rate limited, and
best effort", and "not suitable for production apps". The service reads the
chain through a dedicated RPC provider, with the public endpoint as a
fallback. Its key is a server secret that never reaches a response, a log or
the browser. Wallets in the browser use their own endpoints, as now.
Source: [Base network information](https://docs.base.org/chain/network-information).

### P4-08 Limits against abuse

Accepted · 2026-11-14:
- **Vercel's firewall** limits requests per IP address.
- **The service** limits, per IP address and per party and in the database,
  sign-in and sign-up attempts, new requests, uploads and quality meter runs.
  It answers `429 Too Many Requests` with `Retry-After`.
- **Bodies are at most 4 MB**, under Vercel's 4.5 MB.
- **No third-party CAPTCHA.** It would load another origin's scripts, which
  the content security policy forbids (D-25).

The limits are settings and are documented.
Source: [Vercel WAF rate limiting](https://vercel.com/docs/vercel-firewall/vercel-waf/rate-limiting)
("available on all plans").

### P4-09 Personal data, a privacy notice and terms of use

Accepted · 2026-11-14. Haiko Innovations Oy is the controller.

The data, kept to the minimum:
- wallet addresses and party names, which are public on the chain or in
  requests;
- station profiles;
- the sign-in session;
- IP addresses in logs, kept for at most 14 days.

No analytics, no trackers, no third-party content.

A station may be someone's home, so the public service keeps station
coordinates to two decimals, about a kilometre. Since 2026-11-21 the observer
chooses the exact place or about a kilometre instead
([P5-11](#p5-11-the-stations-place-the-observer-chooses)). A party can delete
its station profile and end its sessions. What is on the chain cannot be deleted, and the
notice says so.

A privacy notice and terms of use, in English and Finnish, are linked from
every page. The terms say: testnet only, no value, SIMULATED data, no
warranty, civilian objects only. Since [D-41](#d-41-english-only), in English
only.

The only cookie is the `HttpOnly` sign-in session. Whether it needs consent is
checked in step 4.4 against section 205 of the Act on Electronic
Communications Services (917/2014) and Traficom's guidance. The result is
recorded with its source. On 2026-11-14 the text could not be read from
Finlex, so it is not stated here. It was read in step 4.4: see
[D-37](#d-37-personal-data-in-the-service). Logs are kept for 30 days since
step 4.5 ([D-38](#d-38-the-service-on-vercel-and-neon)).

### P4-10 The database's protection

Accepted · 2026-11-14. A server of our own could keep its database closed to
the internet. Neon's endpoint is reachable from anywhere, behind TLS and a
password. Its protections are:
- **two roles**: the service's role can only read and write its own tables,
  and a separate role runs the migrations at deployment;
- **the connection string in one place only**: the production environment's
  secret on Vercel; never in the repository, a log, a preview, CI or a
  developer's machine, since development uses a local PostgreSQL;
- **`sslmode=verify-full`**, which Neon recommends;
- **a runbook** to change the password at once if it may have leaked.

Who gets the password can change the service's off-chain state: for example,
which wallet belongs to which party, or the stored files. They cannot do
three things:
- move money, since the escrow decides and every party signs itself;
- use the verifier key, which is not in the database;
- sign in as anyone, since API keys and sessions are stored only as their
  SHA-256.

For a testnet sandbox with SIMULATED data this level is accepted. Before real
data or real money, the choice is Neon's IP Allow or private networking (Scale
plan), or a server of our own with a closed database (P4-05).

Sources:
- [Neon secure connections](https://neon.com/docs/connect/connect-securely)
  ("Neon rejects connections that do not use SSL/TLS");
- [Neon IP Allow](https://neon.com/docs/introduction/ip-allow) ("available
  with the Neon Scale plan");
- [Vercel static IPs](https://vercel.com/docs/networking/static-ips) (a Pro
  add-on, "$100/month per project").

### P4-11 Keys

Accepted · 2026-11-14:
- **The verifier key** is the production environment's write-only secret on
  Vercel, and no preview or developer has it. After the move it leaves the
  maintainer's machine (D-24), except for one encrypted offline copy for
  recovery.
- **The escrow's verifier cannot be changed.** If the key leaks, the remedy
  is a new escrow and a new database, and a runbook describes it.
- **The Safe's three keys stay with the maintainer** (D-24): there is no
  community yet to share them with. Moving them to different people, by
  `swapOwner` in the Safe app, is the first step from one person's keys towards
  the community's, and it needs help from the community
  ([#77](https://github.com/Haiko-Innovations/orbit-watch/issues/77),
  [decentralisation.md](decentralisation.md)).

Source: [Vercel secrets](https://vercel.com/docs/environment-variables/sensitive-environment-variables)
("Secret values are write-only after saving").

### P4-12 Releases and deployment

Accepted · 2026-11-14:
- **Production follows a release.** Vercel's production branch is a branch
  named `production`, and the maintainer moves it to a release tag. A
  rollback moves it back.
- **No deployment credential in GitHub.**
- **Every pull request gets a preview** without secrets and without the
  production database.
- **CI builds the container image** (P4-05); it is published with the
  release.

Since step 4.5 production follows `main`, and a rollback is Vercel's instant
rollback ([D-38](#d-38-the-service-on-vercel-and-neon)).

### P4-13 Operations

Accepted · 2026-11-14:
- **Backups.** Neon's Free plan restores only 6 hours back. So every day a
  GitHub Actions job takes a `pg_dump`, encrypts it to the maintainer's public
  key and keeps it for 14 days. The repository is public, so encryption is
  required. A restore drill runs before the launch and after every schema
  migration.
- **Monitoring.** An external uptime check of the health endpoint, alerts to
  the maintainer, and a check of Neon's monthly hours.
- **Incidents.** A read-only mode refuses changes and keeps the public pages.
  Runbooks cover deployment, rollback, restore, a leaked key and a leaked
  database password.

Since step 4.6 the service takes the backup itself and GitHub Actions keeps it,
encrypted; the uptime check also runs in GitHub Actions
([D-39](#d-39-backups-monitoring-and-read-only-mode)).

### P4-14 A review before the launch

Accepted · 2026-11-14. Before the service is announced:
- a security review against a short checklist taken from OWASP ASVS level 1:
  authentication, sessions, input, headers, limits, secrets and logging;
- an accessibility test with a screen reader, done by a person
  ([accessibility.md](accessibility.md#not-covered));
- a run with a real wallet extension.

Each finding is fixed or recorded.

The screen reader test was moved to after the web application's redesign on
2026-11-18 by [D-42](#d-42-the-screen-reader-test-after-the-redesign).

### P4-15 Nothing that closes the way to a community network

Accepted · 2026-11-14. In the long run Orbit Watch should depend on no single
person, machine or company, and the community should decide how its network
is run ([decentralisation.md](decentralisation.md)). Phase 4 builds nothing
that would close that way:
- no state outside the database;
- truth on the chain;
- files by their SHA-256;
- deterministic verification;
- releases that anyone can run;
- no automatic updates pushed to other people's machines.

### P4-16 Phase 4 completion criteria

Accepted · 2026-11-14. Phase 4 is done when:

1. The service and the web application run publicly at their address over
   HTTPS, on Base Sepolia only, with the testnet label and the SIMULATED label
   on every page.
2. Requests are attested, settled and expired on time without anyone calling
   `tick`. The service keeps no state outside PostgreSQL, and two instances
   never apply one change twice, tested.
3. PostgreSQL is the service's only database, in production, in the local
   stack and in CI, and the local stack still starts in one command.
4. The same release also runs as a container against any PostgreSQL with
   documented commands, and CI tests the image end to end.
5. Every public and sign-in endpoint has documented limits, tested.
6. The privacy notice and the terms are linked from every page, and personal
   data, its retention and its deletion are documented and implemented.
7. Only the production environment holds the verifier key and the database
   password. No secret is in the repository, a preview, the image or the
   browser, tested. The runbooks for a leaked key and a leaked password are
   written.
8. A release is deployed by merging to `main`, and a rollback has been done
   ([D-38](#d-38-the-service-on-vercel-and-neon); first written as moving a
   production branch).
9. Encrypted backups run every day outside Vercel and Neon, a restore drill
   has passed, and monitoring has alerted the maintainer once.
10. The review before the launch is done, each finding fixed or recorded;
    every CI check still passes, including every role's end-to-end test;
    release 0.5.0.

### D-34 PostgreSQL storage

Accepted · 2026-11-14 (with the pull request that implements step 4.1,
[P4-04](#p4-04-postgresql-wherever-the-service-keeps-state)):

- **The driver is psycopg 3** (`psycopg[binary]`, in the `api` extra): 3.3.6,
  the newest release at least 14 days old. It is LGPL-3.0, used unmodified as
  a library, and its binary package brings libpq. Storage imports it only
  when a database is opened, so the open core's command-line tools need neither
  psycopg nor a database.
- **PostgreSQL 18, as on Neon**, which supports 14 to 18. The tests, CI, the
  local stack and the demo run the official image `postgres:18.6`, the newest
  minor release at least 14 days old, pinned by digest. A test keeps all four
  on the same image.
- **A database is a libpq URL or connection string**: `--database`, or
  `ORBIT_WATCH_DATABASE_URL`, or `DATABASE_URL`, the name that Vercel's Neon
  integration sets. Messages name the database and the schema, never the
  connection string, which may hold a password.
- **The schema:**
  - files go in `files.content` (`BYTEA`);
  - numbers that can grow (blocks, amounts, sizes) are `BIGINT`;
  - `chain_conflicts` keeps its order in an identity column instead of SQLite's
    `rowid`;
  - the code keeps writing `?` placeholders, which storage turns into
    psycopg's `%s`.
- **One process per schema until step 4.2.** The service still keeps its state
  in memory, so it holds a session advisory lock on its schema and a second
  process gets `in_use`, as with SQLite's exclusive mode. Replaced by
  [D-35](#d-35-the-stateless-service-the-follower-and-the-image).
- **Tests:**
  - every test gets schemas of its own, named also as the connections'
    application name, so that dropping a schema ends any connection a test left
    open;
  - the server is `ORBIT_WATCH_TEST_DATABASE_URL`, or a container the tests
    start when Docker is there;
  - without either, those tests are skipped unless `ORBIT_WATCH_PG_TESTS=1`;
  - CI runs one service container for the whole job.
- **Earlier SQLite directories are not migrated** (P4-04).

Sources: [psycopg on PyPI](https://pypi.org/project/psycopg/) (3.3.6 of
2026-09-18; LGPL-3.0-only),
[Neon's version policy](https://neon.com/docs/postgresql/postgres-version-policy)
("Neon currently supports Postgres 14, 15, 16, 17, and 18"), and the
[official PostgreSQL image](https://hub.docker.com/_/postgres) (tag 18.6).

### D-35 The stateless service, the follower and the image

Accepted · 2026-11-16 (with the pull request that implements step 4.2,
[P4-05](#p4-05-portable-by-design) and
[P4-06](#p4-06-the-service-runs-on-its-own)):

- **Transactions take turns.** Every transaction first takes the schema's
  transaction-scoped advisory lock (`pg_advisory_xact_lock`, keyed by the
  database and the schema). Changes on one schema happen one at a time, in
  every process. The lock ends with its transaction, so it works behind a
  connection pooler. A change outside a transaction gets one of its own.
- **A checked copy in memory, not a read per call.** P4-06 says that each call
  reads what it needs from the database. The service keeps its working state in
  memory instead, as before, and checks it at the start of every transaction:
  a transaction that changes anything raises the state's version
  (`service_state`, migration 0007), and a process whose copy is older reloads
  it, under the lock, before it reads anything. The effect is the same: every
  call works on the current state and nothing is made twice. It kept the
  service's code as it was. The cost is a full reload after another process
  changes something, and on every cold start. That is small on a testnet. If
  the state grows, reading per request from the database comes in its place.
- **Idempotency is checked under the lock**, in the change's own transaction,
  so two processes that get the same call make it once.
- **The follower** (`follow_once`) applies passed deadlines and, on a chain,
  the escrow's new events. It attests results and settles decided requests, all
  in one transaction, and records when it ran (`service_state.followed_at`).
  - `GET` or `POST /v1/internal/follow` runs it for a schedule, with
    `Authorization: Bearer` and the secret from `ORBIT_WATCH_FOLLOW_SECRET`, or
    from `CRON_SECRET`, which Vercel's cron jobs send. Vercel's cron jobs make
    `GET` requests. Without a secret, the route does not exist (`404`). The
    secret is compared in constant time.
  - `orbit-watch serve --follow SECONDS` runs it in a thread, for a server of
    our own; a failed run is logged and the next one tries again.
  - `GET /v1/health/follower` answers `503` when no follower has run for 30
    minutes (twice the planned 15-minute schedule) or ever.
- **Confirmations.** The service applies a block's events once 10 blocks
  follow it on Base Sepolia, which makes five blocks a second (measured on
  2026-11-16 from Base's public endpoint: 0.2 seconds per block over 1,000
  blocks), so about two seconds. A local Anvil chain needs none.
  `--confirmations` sets another depth. A party's reported transaction is
  answered once it is that deep, so the answer shows the change. The service's
  own transaction, mined but not yet followed, counts as on its way and is not
  sent again. Base's `safe` and `finalized` blocks wait for Ethereum: on
  2026-11-16 they were about 2 and 20 minutes behind the newest block, too slow
  for the views. A reorganisation deeper than 10 blocks is not handled (a
  testnet).
- **The image** is built from the `Dockerfile` at the root in three stages:
  - the web application with Node 26.12.1 (`npm ci --ignore-scripts`);
  - the package and its locked dependencies with uv 0.11.16 into a virtual
    environment, non-editable, with the `api` and `evm` extras;
  - Python 3.12.15 slim with only that environment and the built app.

  Base images are pinned by digest, and Dependabot proposes updates after 14
  days. The service runs as user 10001 and needs no writable file system but
  `/tmp`. It listens on `$PORT` (8000 by default). The build context is an
  allowlist (`.dockerignore`), so local state and keys never reach it.
- **CI tests the image end to end.** CI builds the image and runs the same
  Playwright tests against it. The local stack seeds the database with its
  own process, then hands it to a container of the image (`--image`), which
  runs read-only, as an ordinary user, with the verifier's LOCAL TEST keystore
  mounted read-only.

Sources: [Vercel cron jobs](https://vercel.com/docs/cron-jobs) ("Vercel makes
an HTTP GET request") and
[managing them](https://vercel.com/docs/cron-jobs/manage-cron-jobs)
(`CRON_SECRET` "will be automatically sent as an `Authorization` header", with
the `Bearer` prefix), uv's
[Docker guide](https://docs.astral.sh/uv/guides/integration/docker/)
(`--no-editable`, `UV_COMPILE_BYTECODE`, intermediate layers), and the
[PostgreSQL manual on advisory locks](https://www.postgresql.org/docs/18/explicit-locking.html#ADVISORY-LOCKS).

### D-36 Limits, the body limit and the dedicated RPC endpoint

Accepted · 2026-11-16 (with the pull request that implements step 4.3,
[P4-07](#p4-07-a-dedicated-rpc-endpoint-for-the-service) and
[P4-08](#p4-08-limits-against-abuse)):

- **Counts in the database, in fixed windows** (`rate_limits`, migration 0008).
  Any number of processes count alike, without anything but PostgreSQL
  ([P4-05](#p4-05-portable-by-design)). The limits and their defaults are in
  [api.md](api.md#limits-against-abuse). A test keeps that table equal to the
  code. Fixed windows let a caller make up to twice a limit across the end of a
  window. That is enough against scripts and simpler to explain than a sliding
  window.
- **The public pages are limited too.** Besides the calls that P4-08 lists, every
  page anyone may read without a key (`GET /v1/public/…`, `GET /v1/chain`) counts
  against one generous limit per IP address: 600 per 10 minutes. So the limits
  hold without a firewall in front ([P4-05](#p4-05-portable-by-design)). Health
  checks are not limited, so monitoring keeps working.
- **Counted first, in a transaction of their own.** A call is counted before it
  does anything, after its key or session is known. So a call that then fails
  still counts, and failed sign-ins are what the limit is for. A refused call is
  not counted, and the limits of one call (a sign-up is also a sign-in) are
  checked together.
- **No IP address is stored.** A count keeps a SHA-256 of the address, keyed
  with a random key that the migration makes once per database. Every count is
  deleted when its window is over, at most an hour later. With the key in the
  same database, the hash is pseudonymous, not anonymous; the privacy notice
  (step 4.4) lists it. IPv6 addresses count per /64.
- **The caller's address** is the connection's, unless a trusted proxy's header
  is named. On Vercel that header is `x-real-ip`: Vercel's documentation says it
  "is identical to the `x-forwarded-for` header", "the public IP address of the
  client", and that Vercel overwrites `X-Forwarded-For` "to prevent IP
  spoofing". Of a list, the last entry counts.
- **Counts, keys, sessions and the follower's time change no state.** They are
  written with `state=False`, so they do not raise the state's version
  ([D-35](#d-35-the-stateless-service-the-follower-and-the-image)), and other
  processes do not reload for them.
- **Bodies are at most 4,000,000 bytes**, under Vercel's 4.5 MB. A middleware
  refuses a larger body by its `Content-Length`, or while it arrives, before any
  route reads it.
- **Vercel's firewall** gets one rate-limiting rule in step 4.5, when the
  project exists: every path, 300 requests per 60 seconds per IP address,
  answered with 429. On Pro, rules use a fixed window of 10 seconds to 10
  minutes, counted per IP address or JA4 digest, with 40 rules per project.
  Rules are made in the dashboard.
- **The dedicated RPC endpoint** comes from `ORBIT_WATCH_CHAIN_RPC`, and with
  `--network` the public endpoint is its fallback. The fallback is tried after
  a connection error, a timeout, HTTP 429 or a 5xx. Any other HTTP error is the
  answer, with its status and redacted body, so that a log query over too many
  blocks is still made smaller.
- **The RPC key stays secret.** The service's provider (`chain/rpc.py`) sends
  requests itself, so web3's own debug lines, which name the URL, are never
  written. Errors name an endpoint by its role and the cause by its type and
  status, and are not chained to the exception that holds the URL. A filter on
  urllib3's loggers replaces the URL's path, query and password with
  `[RPC endpoint]`. The tests run a request's whole course through a stand-in
  endpoint with a made-up key, at debug level. They look for the key in every
  response and every log line, and fail without the filter.
- **Which provider** is chosen in step 4.5, with an account in Haiko
  Innovations' name; the key goes into a production secret only.

Sources: [Vercel request headers](https://vercel.com/docs/headers/request-headers)
and [Vercel WAF rate limiting](https://vercel.com/docs/vercel-firewall/vercel-waf/rate-limiting)
("available on all plans"; Pro: "40 per project", window "Minimum: 10s,
Maximum: 10mins", "Fixed window").


### D-37 Personal data in the service

Accepted · 2026-11-16 (with the pull request that implements step 4.4,
[P4-09](#p4-09-personal-data-a-privacy-notice-and-terms-of-use)). The inventory
is [personal-data.md](personal-data.md):

- **The privacy notice and the terms of use are Markdown files** in
  [`docs/legal`](legal), in English and Finnish. The web application reads them
  as they are: a small reader turns the part of Markdown they use into page
  elements, never into HTML, and refuses anything else, so the same text is read
  on GitHub and in the application. A unit test reads all four, and checks that
  each Finnish file has the English one's sections and lists. The pages are at
  `#/privacy` and `#/terms` (`/fi` for Finnish), need neither the service nor
  signing in, and every page's footer links to all four. Since
  [D-41](#d-41-english-only), only the English files and pages remain. The sign-up form names
  the terms and the notice before its button. Haiko Innovations Oy, the
  controller, reviews both before the service is announced (step 4.8).
- **The session cookie needs no consent.** Section 205 of the Act on Electronic
  Communications Services (917/2014) requires consent for storing data on a
  user's device, but its second subsection exempts storage "joka on välttämätöntä
  palvelun tarjoajalle sellaisen palvelun tarjoamiseksi, jota tilaaja tai
  palvelun käyttäjä on nimenomaisesti pyytänyt" ("necessary for the service
  provider to provide a service that the subscriber or user has specifically
  requested"), and its third allows it "ainoastaan palvelun vaatimassa
  laajuudessa" ("only to the extent required for the service"). Traficom's
  cookie guidance names "kirjautuminen sivuston suojattuihin osiin" (signing in
  to the protected parts of a site) as a strictly necessary cookie, for which
  consent is not needed. `ow_session` is set only when someone signs in, only
  for that, for at most 12 hours, `HttpOnly` and `SameSite=Strict`, and the
  application stores nothing else in the browser. So it needs no consent, and
  the notice still describes it, as Traficom recommends. A cookie that
  remembered a sign-in beyond the session would need this checked again.
  Sources: section 205 in Finnish from
  [Finlex's open data](https://opendata.finlex.fi/finlex/avoindata/v1/akn/fi/act/statute-consolidated/2014/917)
  (consolidated version `fin@20221211`, consolidated on 2026-06-16; Finlex's
  web pages show the text only with JavaScript), the
  [unofficial English translation](https://finlex.fi/en/legislation/translations/2014/eng/917)
  (amendments up to 1207/2020, "legally binding only in Finnish and Swedish"),
  and [Traficom: Evästeet](https://www.kyberturvallisuuskeskus.fi/fi/toimintamme/saantely-ja-valvonta/evasteet)
  (updated 2026-10-12; not legally binding as such). Read on 2026-11-16.
- **Station coordinates to about a kilometre.** `orbit-watch serve` rounds a
  profile's latitude and longitude to two decimals of a degree, and refuses a
  delivered Orbit Watch JSON file whose station coordinates are more precise
  (`422 too_precise`). The service does not round a file: the file is kept
  exactly as delivered, since its SHA-256 is what the chain and the attestations
  name, and moving a station by up to 600 m would make its observations fail
  verification. Observations simulated with a profile use the rounded place, so
  they pass. `--station-decimals` (or `ORBIT_WATCH_STATION_DECIMALS`) sets
  another precision, or `off`. `create_app` applies none unless asked, so the
  open core's tools and the tests keep data as given; the local stack seeds
  first, then applies two decimals, as `serve` does.
- **Deleting.** A station deletes its profile (`DELETE
  /v1/stations/{party}/profile`; the station or an administrator). The copies
  of its answers that the idempotency records keep go with it: the records now
  keep the call's path (migration 0009). Its deliveries stay, as the record of
  their requests. A party ends its session (`DELETE /v1/session`) or every one
  of its sessions, in every browser (`DELETE /v1/sessions`). An account is not
  deleted from the browser: its name and wallet are the record of what it did,
  and an administrator handles a request to delete one.
- **Retention.** Ending a session deletes its row. `api/privacy.py`'s `sweep`
  deletes expired sessions, sign-in messages an hour after they expire (so that
  a late answer is told "expired"), the limits' counts whose window has passed
  and idempotency records after 24 hours, about as long as payment APIs keep
  theirs. After 24 hours the same `Idempotency-Key` makes a new call; every
  change also refuses a repeat by its own rules (a request ID, a lifecycle
  status, a transaction hash). The follower runs the sweep, and so does every
  sign-in, so it runs even without a schedule.
- **No IP address in the service's own logs.** `orbit-watch serve` runs uvicorn
  without its access log; `--access-log` turns it on, for a host that keeps it
  at most 14 days.
- **Left for step 4.5, and recorded here so that it is not missed.** Vercel keeps
  runtime logs for 1 day on Pro, but for 30 days with Observability Plus, which is
  "enabled by default" for teams that became Pro on or after 2026-04-03. Step 4.5
  checks the team and keeps runtime logs to at most 14 days, or else changes the
  notice first; Vercel's documentation does not say whether runtime logs hold
  the client's IP address. The Neon project is created in AWS Frankfurt
  (`aws-eu-central-1`), since a project's region cannot be changed later. Step
  4.6 checks the transfer terms for the backups that GitHub keeps.
  Sources: [Vercel runtime logs](https://vercel.com/docs/logs/runtime),
  [Observability Plus](https://vercel.com/docs/observability/observability-plus),
  [Vercel DPA](https://vercel.com/legal/dpa) (2021 standard contractual clauses),
  [Vercel privacy notice](https://vercel.com/legal/privacy-policy) (EU–U.S. Data
  Privacy Framework),
  [Neon regions](https://neon.com/docs/introduction/regions),
  [Databricks privacy notice](https://www.databricks.com/legal/privacynotice)
  (the Data Privacy Framework covers "Databricks, Inc., Neon, LLC"). Read on
  2026-11-16.

### D-38 The service on Vercel and Neon

Accepted · 2026-11-16 (with the pull request that implements step 4.5,
[P4-02](#p4-02-hosting-on-vercel-and-neon) to
[P4-12](#p4-12-releases-and-deployment)). How it is run is in
[deployment.md](deployment.md):

- **Where.** The maintainer chose on 2026-11-16: Haiko Innovations' Vercel Pro
  team, and Neon's Free plan to begin with, both in Europe. The function runs
  in Frankfurt (`fra1`); the Neon project is in AWS Frankfurt (`fra1` in the
  Marketplace, `aws-eu-central-1`). The address is
  `orbit-watch-tan.vercel.app`, since `orbit-watch.vercel.app` was taken
  ([P4-03](#p4-03-vercels-own-address-first)).
- **Vercel Services, in beta.** One project, two services: the web
  application, which Vercel's network serves, and the API as a Python function
  at `/v1/`. They are built, deployed and rolled back together, on one origin
  (D-25). Services are "in Beta on all plans"; the only Vercel-specific files are
  `vercel.json` and `core/asgi.py`, so leaving them costs nothing
  ([P4-05](#p4-05-portable-by-design)).
- **One application for every host.** `orbit_watch.asgi` sets the service up
  from `serve`'s settings in the environment, through the same `serve_app` as
  `orbit-watch serve`. `ORBIT_WATCH_NETWORK` and `ORBIT_WATCH_ORIGINS` give what
  `serve` takes as options, and the verifier key can come from
  `$ORBIT_WATCH_VERIFIER_KEY` instead of a keystore file, which a function does
  not have. Vercel's Python build installs only the base dependencies, so the
  API service installs the extras itself (`uv sync --locked --no-dev
  --no-editable --extra api --extra evm`).
- **Without a database, `503 not_configured`.** A preview has no settings and
  no database ([P4-12](#p4-12-releases-and-deployment)); a service that cannot
  start answers the same and logs why, never a secret.
- **The database's two roles, with one password.** P4-10 asked for a role that
  only reads and writes the service's tables, and another that runs the
  migrations. The Neon integration gives the database's owner as
  `DATABASE_URL`. A second login role would need its password composed into a
  second connection string by hand, on someone's machine. So the owner runs the
  migrations, and the role `orbit_watch_app` has no login: the owner switches to
  it with `SET LOCAL ROLE` at the start of every transaction, which holds behind
  the pooler too. A mistake in the service cannot drop or alter a table. A
  leaked password is still the owner's; the runbook in step 4.6 says how to
  change it.
- **TLS checked against known roots.** `ORBIT_WATCH_DATABASE_SSLMODE=verify-full`
  sets libpq's mode, with `certifi`'s root certificates, since the function's
  system paths may not match the bundled OpenSSL's. libpq is 18.
- **A long-lived process, a database that sleeps.** Neon's Free plan suspends
  the database after five minutes, which closes connections, and Vercel keeps a
  function's instance for many calls. The storage layer opens a lost connection
  again before a transaction or a read on its own, never in the middle of one,
  and uses no server-side prepared statements, which the pooler in
  transaction mode does not keep. The first call after a sleep took 8.4 s on
  2026-11-16 (the database waking, and the first migrations); later calls take
  well under a second.
- **Neon's variables are Config, not Secret.** The integration writes its
  variables to the production environment only, as Config, readable by the
  team's members. Haiko's team has one member. Replacing them with Secret copies
  would cut them off from the integration's password changes.
- **Logs for 30 days.** The maintainer chose on 2026-11-16 to keep Vercel's
  default for the team, Observability Plus, which keeps runtime logs for 30 days.
  This replaces the 14 days of P4-09, and the privacy notice and
  [personal-data.md](personal-data.md) say 30.
- **Production follows `main`.** The maintainer chose on 2026-11-17 to deploy
  every merge to `main`, instead of P4-12's `production` branch moved to a
  release tag. The maintainer reviews and merges one pull request at a time, so
  a second step for each release would add work and no safety, and the service
  is not announced yet. `main` is Vercel's default, which the REST API could
  not have changed anyway (`PATCH /v9/projects` refuses `link`).
- **A rollback is Vercel's instant rollback.** It points the production domains
  at an earlier production deployment, with that deployment's build, its
  settings as they were then and its cron jobs, without building anything.
  Merges to `main` still build but do not go live until a deployment is
  promoted again (`vercel promote`). So a rollback also stops a broken `main`
  from going live while a fix is merged.
- **The first deployment.** The project's first deployment from the command
  line, made before the Git connection, became its production deployment; it
  had no settings and answered `503`.
- **The firewall rule** of D-36 is set with `vercel firewall`; publishing it
  needs a person's approval.
- **The RPC endpoint.** Until a dedicated provider is chosen, the service
  reads Base Sepolia through its public endpoint, which is enough while the
  service is not announced. A dedicated endpoint needs an account in Haiko
  Innovations' name, and is set as `ORBIT_WATCH_CHAIN_RPC` before the launch.

Sources, read on 2026-11-16: [Vercel Services](https://vercel.com/docs/services)
and its [configuration](https://vercel.com/docs/services/config-reference),
[Python runtime](https://vercel.com/docs/functions/runtimes/python),
[cron jobs](https://vercel.com/docs/cron-jobs),
[regions](https://vercel.com/docs/functions/configuring-functions/region),
[production branch](https://vercel.com/docs/git#production-branch),
[Config and Secret variables](https://vercel.com/docs/environment-variables/sensitive-environment-variables),
[runtime logs](https://vercel.com/docs/logs/runtime). On 2026-11-17:
[instant rollback](https://vercel.com/docs/instant-rollback) and
[promoting a deployment](https://vercel.com/docs/deployments/promoting-a-deployment).

### D-39 Backups, monitoring and read-only mode

Accepted · 2026-11-17 (with the pull request that implements step 4.6,
[P4-13](#p4-13-operations)). The maintainer asked on 2026-11-16 for light
backups, since Neon's Free plan restores only six hours back. How they are run is
in [operations.md](operations.md):

- **The service takes the backup, GitHub keeps it.** P4-13 planned a `pg_dump` by
  GitHub Actions, which would need the database's owner password in GitHub. The
  service instead takes the backup itself, in one transaction under the lock that
  every change takes, encrypts it with age to the maintainer's public key, and
  streams it to the `Backup` workflow, which calls `GET /v1/internal/backup` with a
  token every day. GitHub holds only that token, which can fetch nothing but
  ciphertext, and only `main` can use it (the environment `backup`). Plain data
  never leaves Vercel and Neon, the same code restores what it took, and a server
  of our own takes the same backup with `orbit-watch backup create`
  ([P4-05](#p4-05-portable-by-design)). The workflow keeps only an age file, as an
  artifact, for 14 days.
- **The format** is age (v1, X25519), then gzip and tar: a manifest with the
  schema's version and each table's columns, rows and SHA-256, and each table in
  PostgreSQL's `COPY` text format, so `age` and `tar` open it without Orbit Watch.
  pyrage 1.4.0 (MIT, the Rust age library's Python binding) encrypts and decrypts;
  it is in the `api` extra.
- **Left out of backups:** sessions, sign-in challenges, limit counts, the copies of
  answers kept for idempotency, and the migrations' record. They live for hours at
  most ([D-37](#d-37-personal-data-in-the-service)), and a restore runs the
  migrations itself.
- **A restore** goes into an empty database: the migrations up to the backup's
  version, the rows, a check of every table against the manifest, then the newer
  migrations. A backup from a newer version is refused. The tests restore a backup
  taken through the API on every pull request; a drill with a real backup runs
  before the launch and after every schema migration, and is logged in
  operations.md.
- **The backup key.** Claude made the age key pair on 2026-11-17 on the
  maintainer's machine, into `~/secrets/orbit-watch` beside the testnet keys
  ([D-24](#d-24-the-base-sepolia-deployment)), and printed only the public key,
  which is a Config variable. The private key goes offline with the verifier key in
  step 4.7 ([P4-11](#p4-11-keys)).
- **Monitoring from GitHub Actions.** The `Uptime` workflow checks the API, the
  follower and the web application every hour. No other account is needed. GitHub
  may run a schedule late at busy times, and turns schedules off after 60 days
  without activity in a public repository; both are acceptable for an unannounced
  testnet service.
- **An alert is an issue.** A failed run of `Uptime` or `Backup` opens an issue
  assigned to the maintainer (the repository variable `ALERT_ASSIGNEE`), labelled
  `alert: uptime` or `alert: backup`, unless one is already open, and the next
  passing run closes it; so the workflows may write issues and nothing else. At
  first a failed run was the alert, through GitHub's own notifications of failed
  runs, which go to whoever created the scheduled workflow or ran it by hand. In the
  first alert check on 2026-11-17 none arrived, with the maintainer's Actions
  notifications off and then on for GitHub Mobile. An assigned issue reaches the
  maintainer like everything else they follow.
- **Neon's hours.** The Free plan has 100 compute hours a month per project, sends
  no email before they run out, and has no usage API. So the check is indirect: a
  database stopped for the month makes the follower fall behind, which the uptime
  check reports, and the maintainer looks at the usage in Vercel once a month. The
  uptime check runs at 17 minutes past the hour, just after the follower's run at
  :15, while the database is still awake, so it adds no hours of its own. Each
  backup crosses the network, which the Free plan limits to 5 GB a month: the
  workflow warns over 50 MB.
- **Read-only mode** is a setting, `ORBIT_WATCH_READ_ONLY`, applied by a redeploy:
  every change is refused with `503 read_only`, the follower waits, and reads no
  longer follow the chain, since following it writes. Reading, the public pages,
  signing in and backups still work, and the web application says so on every page.
  A setting in the database would apply at once, but it would not help when the
  database is what is wrong, and a redeploy takes under a minute.

Sources, read on 2026-11-17: [pyrage](https://pypi.org/project/pyrage/) 1.4.0,
[age v1](https://age-encryption.org/v1),
[GitHub notifications for workflow runs](https://docs.github.com/en/actions/concepts/workflows-and-actions/notifications-for-workflow-runs),
[the schedule event](https://docs.github.com/en/actions/reference/workflows-and-actions/events-that-trigger-workflows#schedule),
[environments](https://docs.github.com/en/actions/reference/workflows-and-actions/deployments-and-environments),
[upload-artifact](https://github.com/actions/upload-artifact) v7.0.2 (retention
of 1 to 90 days), [Neon's plans](https://neon.com/docs/introduction/plans),
[monitoring Neon's usage](https://neon.com/docs/introduction/monitor-usage),
[Vercel-managed Neon](https://neon.com/docs/guides/vercel-managed-integration),
[Vercel's streaming functions](https://vercel.com/docs/functions/streaming-functions)
and [limits](https://vercel.com/docs/functions/limitations) ("The response body
limit doesn't apply to streamed responses").

### D-40 The review before the launch

Accepted · 2026-11-17 (with the pull request of the review, step 4.7,
[P4-14](#p4-14-a-review-before-the-launch)). The review is
[security-review.md](security-review.md):

- **Every level 1 requirement of OWASP ASVS 5.0.0**, 65 of them, not a short list
  chosen by hand: the full level is barely longer, and it leaves nothing to
  choose. ASVS 5.0 has no level 1 requirement on logging, which P4-14 names, so
  logging is reviewed beside it.
- **The session cookie is `__Host-ow_session` over HTTPS.** ASVS 3.3.1 asks for the
  prefix, which makes browsers keep the cookie only when it is `Secure`, set by
  this host and for the whole site. Plain http on a developer's machine cannot
  carry it, so there the cookie keeps its old name, and a session signed in over
  HTTPS counts only under the prefixed one. The privacy notice names the new
  cookie.
- **A sign-in ends the browser's earlier session** (ASVS 7.2.4).
- **The reasons people write are for the request's parties.** `GET
  /v1/requests/{id}` stays open to every signed-in party, who may follow any
  request, but it hides the challenge's and the votes' reasons from others until
  the request is published, as the data inventory always said.
- **Time frames for vulnerabilities** are in `SECURITY.md`: 2 days for anything
  exploitable in the public service or critical, 7 for high, 30 for medium, and
  the next update for low.
- **GitHub's secret scanning, push protection and Dependabot security updates**
  were turned on on 2026-11-17. They cost nothing in a public repository, and
  `dependabot.yml` already counted on security updates.
- **Accepted as they are:** the internal routes act on `GET`, because Vercel's
  cron jobs send `GET` and both need a token in a header; API keys are long-lived,
  for command-line tools; there is no command to disable an account, and an
  administrator who deletes one ends its sessions first.

Source: [OWASP ASVS 5.0.0](https://github.com/OWASP/ASVS/tree/v5.0.0_release/5.0/en),
released 2025-05-30, read on 2026-11-17.

### D-41 English only

Accepted · 2026-11-17, by the maintainer. Orbit Watch is in English only: the
code, the documentation, the web application, the privacy notice and the terms of
use. The Finnish translations are removed: the README, the contributing guide, the
plan, the roadmap, the phase summaries, the privacy notice and the terms of use,
and the web application's pages at `#/privacy/fi` and `#/terms/fi`, which are now
not found. This replaces [D-09](#d-09-english-first-finnish-translations-of-key-documents),
and the Finnish versions of [P4-09](#p4-09-personal-data-a-privacy-notice-and-terms-of-use) and
[D-37](#d-37-personal-data-in-the-service).

- One language is one version of every text to keep right. The translations
  lagged behind, and the English version applied whenever they differed.
- The service is for an international community of satellite operators and
  observers, whose common language is English.
- The legal texts still name Finnish law, the Finnish data protection authority
  and the Finnish company behind the service: those are facts, not translations.
  The history of the Finnish texts stays in the repository.

### D-42 The screen reader test after the redesign

Accepted · 2026-11-18, by the maintainer. The accessibility test with a screen
reader, done by a person ([P4-14](#p4-14-a-review-before-the-launch)), is not
done before the launch in step 4.8. The maintainer plans to redesign and restyle
the whole web application after release 0.5.0. The test is done then, against
the new pages, and step 4.7 is done without it.

- A test now would hear pages whose layout and styles are about to change, and
  it would have to be done again.
- Until then the automated review of every view keeps running in CI: axe in
  the light and dark themes, the keyboard, focus and reflow
  ([accessibility.md](accessibility.md)). It cannot tell how the pages sound.
- [accessibility.md](accessibility.md#not-covered) says that no screen reader
  test has been done, and so will the announcement in step 4.8.
- This replaces the screen reader part of P4-14, and of the review in phase 4's
  completion criterion 10 ([P4-16](#p4-16-phase-4-completion-criteria)).

### D-43 The dedicated RPC endpoint: Coinbase's CDP Node

Accepted · 2026-11-18, by the maintainer. The public service reads Base Sepolia
through Coinbase Developer Platform's Node service (CDP Node), as
[P4-07](#p4-07-a-dedicated-rpc-endpoint-for-the-service) and
[D-36](#d-36-limits-the-body-limit-and-the-dedicated-rpc-endpoint) planned.
Base's public endpoint stays the fallback. The endpoint's URL, which holds the
key, is the production secret `ORBIT_WATCH_CHAIN_RPC`, set from a prompt that
does not echo.

- **Why CDP Node.** Base Sepolia makes a block every 0.2 seconds, about 432,000
  a day, and the service reads the escrow's events from every one of them. The
  number of blocks that one `eth_getLogs` call may span decides how many calls
  that takes. On the free plans, read on 2026-11-18:

  | Provider | Blocks per call |
  |---|---|
  | CDP Node | 1,000 |
  | Chainstack | 100 |
  | Alchemy | 10 |
  | QuickNode | 5 |

  CDP Node's free tier is 10 million billing units a month, at about 50 calls a
  second. An `eth_getLogs` call costs 100 units, and other calls cost 30. The
  service needs an estimated 2 to 3 million units a month. Coinbase builds
  Base, and Base's documentation lists CDP among its node providers.
- **Cost.** Since January 2026, CDP Node needs a payment method on file. Use
  beyond the free tier costs $0.50 per million units.
- **The account is the maintainer's own for now**, not one in Haiko Innovations'
  name as D-38 planned. Moving it needs no code change: a new key in the
  company's account, set as the same secret, then a redeploy.
- **Checked on 2026-11-18.** The redeployed service followed the chain on
  schedule, within a few seconds of the latest block. None of its log records
  named the endpoint.

Sources, read on 2026-11-18:
- CDP Node's [overview](https://docs.cdp.coinbase.com/data/node/overview.md),
  [pricing](https://docs.cdp.coinbase.com/data/node/pricing.md) and
  [JSON-RPC limits](https://docs.cdp.coinbase.com/api-reference/json-rpc-api/core.md);
- [Alchemy](https://support.alchemy.com/articles/1883074130-why-do-i-see-a-free-tier-error-when-calling-eth-getlogs-with-a-large-block-range),
  [QuickNode](https://support.quicknode.com/hc/en-us/articles/10258449939473-Understanding-the-10-000-Block-Range-Limit-for-querying-Logs-and-Events)
  and [Chainstack](https://docs.chainstack.com/docs/limits) on their
  `eth_getLogs` limits;
- Base's [node providers](https://docs.base.org/base-chain/node-operators/node-providers.md).

## Phase 5 decisions

P5-01 to P5-15 were proposed for the
[roadmap](roadmap.md#phase-5-real-orbits-and-real-observations-on-the-testnet-target-version-060)'s
phase 5, real orbits and real observations on the testnet, in
[#103](https://github.com/Haiko-Innovations/orbit-watch/issues/103), and
approved by the maintainer on 2026-11-21. They follow a discussion with the
maintainer on 2026-11-20 and 2026-11-21:
- real data on the testnet, with test money only;
- real test data from public sources with open terms, instead of asking
  observers for it;
- the observer's own choice of how precisely a station's place is published;
- the method measured on real data before it changes;
- code without waiting: whatever needs the maintainer or someone outside the
  repository comes at the end of the phase, as a follow-up (P5-14).

Facts were checked on 2026-11-20; the sources are listed under each decision.
Versions are chosen, and checked, when they are used.

### P5-01 Real data, test money

Accepted · 2026-11-21. Phase 5 brings real data into Orbit Watch:
- **real reference orbits** of real civilian objects, beside the simulated
  ones;
- **real observations** that observers have published under an open licence,
  replayed through the service and used to measure the verification method.

Everything else stays as it is:
- Base Sepolia only: testnet USDC, no mainnet, no real money, no token of our
  own;
- the simulated objects, stations and deliveries, labelled SIMULATED.

Not in phase 5:
- real money;
- observations of our own;
- asking observers for data: it all comes from public sources with open terms
  (P5-06);
- the community network ([decentralisation.md](decentralisation.md)).

[P4-01](#p4-01-a-public-sandbox-on-the-testnet) left real data for a later
phase, because it needs decisions of its own: the data source's terms,
licences, and the personal data of real observers. P5-02 to P5-13 are those
decisions.

### P5-02 Current reference orbits from CelesTrak, one object at a time

Accepted · 2026-11-21. The service fetches a real object's current reference
orbit from CelesTrak's GP data, as CelesTrak's usage policy asks:
- **Only what is needed.** One object by its catalogue number, and only the
  objects of open requests. Never a large group such as `active`, which
  CelesTrak now limits.
- **Once per update.** At most once every two hours per object, since GP data
  is updated every two hours.
- **CSV, compressed.** `FORMAT=csv` with gzip, since JSON is about three times
  the size.
- **Stop at the first answer that is not 200, and tell a person.** The
  follower records why it stopped, and fetches nothing more until a person
  clears it. A health endpoint reports the stop, so the hourly uptime check
  opens an alert issue as for any other failure
  ([D-39](#d-39-backups-monitoring-and-read-only-mode)). No new secret is
  needed. After a 500 or a 503 the follower waits at least 15 minutes. An object without public data answers 404, which counts towards
  CelesTrak's error limit, so it is not asked for again.
- **A few objects per follower run**, so that a run stays short.

Each element set is kept in PostgreSQL with:
- its source;
- the time it was fetched;
- its epoch;
- its SHA-256.

An administrator can also upload an element set by hand, labelled as
uploaded, for example when CelesTrak cannot be reached.

**A risk.** Vercel's functions share their outgoing addresses with other
users, and CelesTrak blocks addresses, not users. If the service is blocked
for someone else's behaviour, it stops, alerts and waits for an upload by
hand. Step 5.8 records how often this happens.

`orbit-watch fetch-gp` also asks for CSV with gzip. Its other rules stay
(D-06): one request per call, no retries, no second download within two hours.

Source: [CelesTrak usage policy](https://celestrak.org/usage-policy.php),
updated 2026-11-16:
- "please use FORMAT=csv";
- "M2M (machine-to-machine) software should immediately stop querying when it
  receives any non-HTTP 200 responses and report the results to a human";
- after a 500 or a 503, "All requests should stop for at least 15 minutes";
- "we are starting to enforce some of those limits for larger data sets, like
  the Active list".

On 2026-11-20 a download of `GROUP=active` stopped at about 1.2 MB, and a query
for an object without public data answered `404 No GP data found`.

### P5-03 Past reference orbits from SatChecker

Accepted · 2026-11-21. CelesTrak gives only current element sets by URL. Its
history comes through a request form with a CAPTCHA, by email
([data-sources.md](data-sources.md)). Real observations are from the past, so
their reference orbits come from the IAU CPS's SatChecker. It keeps the
element sets of Space-Track and CelesTrak, and gives the one nearest a given
time without an account:
- `get-nearest-tle` for the past, since TLEs "remain the record for historical
  dates", and `get-nearest-omm` where OMM data exists;
- a TLE is read only from SatChecker's history, and only for catalogue numbers
  below 100,000, which a TLE can hold;
- one request at a time, at least two seconds apart, stopping at the first
  answer that is not 200;
- every answer kept with its source, its `date_collected`, its epoch and its
  SHA-256.

SatChecker serves the command line, the tests and replay requests (P5-10).
Current requests use CelesTrak (P5-02).

SatChecker's own notes say that "Public Space-Track TLEs for LEO satellites
are often off by several arcminutes", and that TLEs "are only good for a
maximum of two weeks". Step 5.3 measures what this means for verification.

Sources: SatChecker 1.9.0's
[orbital data access](https://satchecker.readthedocs.io/en/latest/tools_data_access.html)
and [notes](https://satchecker.readthedocs.io/en/latest/notes.html).

### P5-04 The element set nearest the observations

Accepted · 2026-11-21. Method 2.0.0 uses only the newest element set of each
object ([verification.md](verification.md#orbit-residuals)). With
history, a catalogue holds several sets of one object. The reference for a
delivery is then the set whose epoch is nearest the middle of its
observations, among the sets known when it is verified. The 7-day age limit
stays.

The report names the set by its source, epoch and SHA-256. Anyone can then
fetch the same set and run the same verification.

This is a new minor version of the method. With one set per object, as in
every committed example, every verdict and residual stays the same; only the
method's version and the new field change.

### P5-05 Orbit data stays out of the repository

Accepted · 2026-11-21. Confirms
[D-06](#d-06-no-real-orbit-data-in-the-repository) for phase 5. The element
sets come from the US Space Force through Space-Track, whose user agreement
governs their redistribution, and CelesTrak states no terms. We have not read
terms that allow us to republish them; reading them is a follow-up
([#114](https://github.com/Haiko-Innovations/orbit-watch/issues/114)). So:
- **Committed examples with real observations name their reference orbits**
  in a manifest: the object, the source, the epoch and the SHA-256.
- **One command fetches what a manifest names**, by its exact epoch and under
  P5-03's rules, into a cache outside the repository, and checks every
  SHA-256.
- **Tests that need the cache are skipped without it.** CI keeps the cache in
  GitHub Actions' cache, never in the repository or in an artifact, and fetches
  only what the cache lacks.
- **The public service keeps the sets it fetched in its database** and names
  them in its reports. It does not serve their content.

### P5-06 Real observations from SCORE

Accepted · 2026-11-21. The IAU CPS's Satellite Constellation Observation
Repository (SCORE) publishes observers' positional and brightness observations
of satellites under CC BY 4.0. On 2026-11-20 it held 42,669 observations of
3,344 satellites, from 2019-12-14 to 2026-11-19.

A positional observation holds:
- its time and the time's uncertainty;
- right ascension and declination in the ICRF, measured against Gaia DR3
  stars, with their variances;
- the observer's place and instrument;
- the observers' ORCID iDs.

That is everything Orbit Watch's format needs. So real observations no longer
need to be asked for.

- **Fetched politely.** A command fetches one satellite at a time through
  SCORE's API:
  - pages of at most 100 observations;
  - at most one request a second (the API allows ten);
  - it stops at the first answer that is not 200, and waits at least 15
    minutes after a 500 or a 503.

  The full download, which is behind a CAPTCHA, is never used. On 2026-11-20
  pages of 1,000 observations answered 500 and 503.
- **Converted** to Orbit Watch's format. Each file names its source, SCORE's
  observation IDs, the observers' ORCID iDs and the licence.
- **A selected set is committed** under `examples/real/`, with a credits file
  (P5-13): some tens of tracks from several instruments, good ones and bad
  ones.
- **Phase 0's last criterion is met with this set**
  ([#8](https://github.com/Haiko-Innovations/orbit-watch/issues/8)). The
  criterion asked for "one real public IOD example", because IOD was the only
  public source known then. SCORE's observers have no IOD station numbers, so
  the set is in Orbit Watch's format.
- **Personal data.** An ORCID iD and a station's place are personal data, even
  when the observer published them:
  - our use, measuring and showing a verification method, rests on legitimate
    interest;
  - the privacy notice says where the data comes from;
  - an observer can ask for their data to be removed from the service and from
    the repository's next version.

  Step 5.2 checks the duties of GDPR article 14, for data not obtained from
  the person, and records the result with its source. Anything they ask for
  outside the code becomes a follow-up (P5-14).

Alternatives, looked at on 2026-11-20:
- **SeeSat-L's archive.** In September to November 2026 it held 4,494 IOD
  lines of 295 objects from 8 stations, nearly all of them classified objects
  (D-05), and states no licence.
- **The VCM dataset on Zenodo** (CC BY 4.0, 2.9 GB, 2022 and 2023). Its precise
  orbits need the Space Force's own propagator.

Sources:
- [SCORE use policy](https://score.cps.iau.org/policy), last updated
  2024-12-02: "Data will be shared under the Creative Commons Attribution
  (CC-BY) 4.0 licence"; "If you use data from SCORE, you must follow the CC-BY
  licences and credit the observers appropriately";
- [SCORE data format](https://score.cps.iau.org/data-format);
- [SCORE API](https://score.cps.iau.org/api-access): "rate-limited to 10
  requests per second";
- [VCM dataset](https://zenodo.org/records/13892132).

### P5-07 Measure first

Accepted · 2026-11-21. The method's behaviour on real data is measured and
published before the method changes.

A first look on 2026-11-20 used 13 tracks, about 1,775 observations from SCORE,
against SatChecker's nearest TLEs:
- **A video camera** (WATEC 902H2): every observation within the limit. ACS
  3's median residual was 26″, against a median limit of 762″.
- **A phone** (iPhone 12 Mini): in five of its six tracks no observation was
  within the limit. Its tracks showed the same clock error, −1.5 to −1.7 s,
  which the quality meter is meant to find.
- **The limit is loose.** Its largest term is the reference orbit's assumed
  5 km error.

Step 5.3 measures, with method 2.0.0 and only P5-04's choice of set changed:
- residuals and pass rates per instrument and orbit;
- how the limit splits into its terms;
- the effect of the reference orbit's age;
- false rejections: tracks from good instruments that fail;
- false acceptances: real tracks with injected faults, such as a time shift,
  the wrong object, a moved station, or a track made from the reference orbit
  itself (which no automated check can catch, and the challenge period is
  for);
- what rounding a station's place to about a kilometre costs (P5-11).

The results go to `docs/real-data-validation.md`, reproducible with one command
from the committed set and the cache. Real tracks, good ones and ones with
injected faults, join the known-answer datasets of reviewer calibration
(step 1.4). Any change to the method's checks or parameters is proposed
afterwards, as a decision of its own, with the measurement behind it.

### P5-08 Real objects on the allow-list

Accepted · 2026-11-21. Requests may target only civilian objects (D-05). For
real objects the allow-list is built as now, with `orbit-watch allowlist
build`:
- from CelesTrak's small civilian groups, such as `science`, `education`,
  `amateur` and `cubesat`, downloaded at most once a day;
- minus the excluded groups and the name patterns.

Large groups, such as `starlink`, are not downloaded. Instead, an
administrator can add an object by its catalogue number, after checking its
owner in the satellite catalogue. The reason is shown publicly, and the name
patterns still apply. The simulated objects stay on the list.

### P5-09 Real and simulated side by side

Accepted · 2026-11-21. The service carries real and simulated data at once, and
every item says which it is:
- **objects**: real, or SIMULATED;
- **reference orbits**: CelesTrak, SatChecker or uploaded by hand, with the
  epoch;
- **observations**: SIMULATED, replayed (P5-10), or delivered by a station.

The SIMULATED label stays on everything simulated, and only there. The testnet
label stays on every page.

Simulated stations may observe real objects. The whole chain can then be shown
with real orbits without real observers, and their observations are SIMULATED.

The web application gets only the labels and views that phase 5 needs. Its
redesign stays separate
([#97](https://github.com/Haiko-Innovations/orbit-watch/issues/97)).

### P5-10 Replays name their observers

Accepted · 2026-11-21. A replay delivers observations that someone else
published, through the service, to show and test the whole chain with real
data:
- **Only an administrator creates a replay request.** Its window lies in the
  past, and the request is marked as a replay.
- **A replay station run by the maintainer delivers it.** It never appears as
  the observer.
- **Every page and file of a replay** names the source, the observers' ORCID
  iDs and the licence.
- **The testnet reward goes to the replay station's wallet.** Testnet USDC
  has no value ([P2-02](#p2-02-circles-testnet-usdc-no-token-of-our-own)), and
  nobody is paid for someone else's work.

A request for real observations of a coming pass is a normal request, open to
every station.

### P5-11 The station's place: the observer chooses

Accepted · 2026-11-21. Replaces the public service's fixed rounding of
station coordinates to two decimals
([P4-09](#p4-09-personal-data-a-privacy-notice-and-terms-of-use)).

Verification needs a precise place. Rounding to two decimals moves a station by
up to about 0.6 km. For a satellite 500 km away that is up to about 250″, ten
times the 26″ median residual of a good video camera (P5-07). But a station
may be someone's home.

- **The observer chooses when the station is created**: "publish the exact
  place" or "publish the place to about a kilometre". Neither is selected in
  advance, and the station cannot be saved without a choice. GDPR article
  25(2) asks that, by default, personal data is not made accessible "without
  the individual's intervention" to an indefinite number of people. An
  explicit choice is that intervention; "exact" chosen in advance would not
  be.
- **The choice can be changed at any time**, for later deliveries. Files
  already published keep the place they were delivered with, since their
  SHA-256 is on the chain. The station's page says so before the observer
  chooses "exact".
- **Existing stations stay at about a kilometre** until their owner chooses.
- **A station is verified with the place it publishes**, so that anyone can
  repeat the verification. A rounded place is verified as rounded; step 5.3
  measures what that costs.
- **The station profile is the place for every format.** IOD and CCSDS TDM
  deliveries take their station's place from the profile, and a JSON delivery
  whose place differs from the profile is refused.

Source: [GDPR article 25(2)](https://eur-lex.europa.eu/eli/reg/2016/679/oj):
"such measures shall ensure that by default personal data are not made
accessible without the individual's intervention to an indefinite number of
natural persons".

### P5-12 Visibility

Accepted · 2026-11-21. An optical observer sees a satellite only when the Sun
lights it and the observer's sky is dark. The simulator learns both
([#7](https://github.com/Haiko-Innovations/orbit-watch/issues/7)), and the
service lists a station's visible passes for a request:
- **The Sun's place from a short formula in the core**, without an ephemeris
  file. Skyfield's `is_sunlit()` needs a JPL ephemeris, and DE421 alone is
  17 MB. The US Naval Observatory's formula gives the Sun "to an accuracy of
  about 1 arcminute within two centuries of 2000", enough for the Earth's
  shadow and for twilight. Step 5.7 measures it once against a JPL ephemeris
  and records the result.
- **A dark sky**: by default the Sun at least 6° below the horizon, the end of
  civil twilight. This is a setting.
- **A pass list** for a station and a request's window, in the API and in the
  observer's view: rise, highest point and set above the request's elevation
  limit, and the part of the pass that is lit.

Sources: [Skyfield: JPL ephemeris files](https://rhodesmill.org/skyfield/planets.html)
(de421.bsp, 1900 to 2050, 17 MB), and the US Naval Observatory's
[approximate solar coordinates](https://aa.usno.navy.mil/faq/sun_approx).

### P5-13 Credits and statements

Accepted · 2026-11-21. The sources ask for credit. They get it in a credits
file beside the data, in the documentation, and on a public page of the
service that says where its real data comes from:
- **SCORE**:
  - the observers of each file, by ORCID iD (CC BY 4.0);
  - SCORE's acknowledgement;
  - the statement that SCORE requires on "any publication, presentation,
    website or web service that uses SCORE data".
- **SatChecker**: its acknowledgement.
- **CelesTrak**: named as the source of current element sets.

SCORE also asks its users to tell it that they use its data. That is for the
maintainer to decide, at the end of the phase: a follow-up (P5-14,
[#113](https://github.com/Haiko-Innovations/orbit-watch/issues/113)).

Sources: the [SCORE use policy](https://score.cps.iau.org/policy) and
[SatChecker's acknowledgements](https://satchecker.readthedocs.io/en/latest/acknowledgements.html).

### P5-14 Follow-ups at the end, not in the way

Accepted · 2026-11-21. Phase 5's steps need nothing from the maintainer but
reviews and merges, and nothing from anyone outside the repository. Work that
does becomes a follow-up issue in the phase's milestone, for example:
- a note to a data source;
- an account with a service;
- terms that can be read only after signing in;
- a change in a third-party service's settings.

A follow-up is done at the end of the phase, or later, and no step waits for
it. Until it is done, the plan's cautious choice holds. A step that finds such
work on the way records it as a follow-up and goes on. The follow-ups are not
completion criteria.

The follow-ups known now:
- telling SCORE that Orbit Watch uses its data, as its use policy asks, and
  perhaps starting a collaboration with the IAU CPS ([#113](https://github.com/Haiko-Innovations/orbit-watch/issues/113));
- reading Space-Track's user agreement, which may need an account, to decide
  whether real element sets may ever be committed. Until then D-06 and P5-05
  hold ([#114](https://github.com/Haiko-Innovations/orbit-watch/issues/114)).

The demonstrations on the public service (step 5.8) use the testnet keystores
of [D-24](#d-24-the-base-sepolia-deployment), so they need no person's own
wallet.

### P5-15 Phase 5 completion criteria

Accepted · 2026-11-21. Phase 5 is done when:

1. The service verifies deliveries for real objects against real reference
   orbits: CelesTrak's for current requests and SatChecker's for replays. It
   uses the element set nearest the observations, and the report names it.
2. Every fetch from CelesTrak, SatChecker and SCORE follows that source's
   rules, stops at the first answer that is not 200, and tells a person. This
   is tested against local stand-ins. No test in CI calls an outside service,
   except to fill its cache.
3. A set of real observations from SCORE is committed, credited under CC BY
   4.0 with the statements the sources ask for. No real element set is in the
   repository.
4. The method's behaviour on real data is measured and published (P5-07),
   reproducible with one command. Real tracks are in the known-answer
   datasets.
5. Real objects are on the allow-list under D-05's rules, and an
   administrator's additions show their reasons.
6. Every page labels objects, reference orbits and observations by their
   source. SIMULATED is on all simulated data and on nothing else, and the
   testnet label is on every page; tested end to end.
7. Replays name their observers and never appear as them.
8. The observer chooses how precisely the station's place is published, with
   nothing chosen in advance. The profile is the place for every format, and a
   delivery from another place is refused; tested. The privacy notice and the
   data inventory say so.
9. The simulator observes only objects the Sun lights under a dark sky, and an
   observer sees the station's visible passes for a request.
10. On the public service, a replay of real observations and a request for a
    real object with simulated observations have both settled on Base Sepolia.
    Every CI check passes; release 0.6.0.

### D-44 Reference orbits in the core

Accepted · 2026-11-21 (with the pull request that implements step 5.1).

- **A catalogue holds several element sets per object** (P5-04). The same set
  twice counts once.
  - `Catalog.nearest(object, time)` gives the set whose epoch is nearest the
    time; on a tie, the earlier one.
  - `records` and `satellite()` still give the newest set, for the simulator
    and the allow-list.
  - A wrapper's record may carry a `source` object. It is not an OMM field, it
    is not passed to SGP4, and a set's SHA-256 leaves it out.
- **Method 2.1.0, report format 1.1.** The reference for a delivery is the set
  nearest the middle of its observations, halfway between the first and the
  last. When no observations could be read, the report names the newest set.
  The report's `reference_orbit` gains three fields, and a fourth when the
  catalogue says where the set came from:
  - `element_set_sha256`;
  - `selection`;
  - `element_sets_in_catalogue`;
  - `source`.

  The `source` never includes the set itself, such as a TLE's lines: reports
  are published, and real element sets are not (D-06, P5-05). Every committed
  example keeps its verdict, checks and residuals; it was regenerated for the
  versions and the new fields. The terms' default method is
  `orbit-watch-automated-verification 2.1.0`, and a test keeps the two equal.
- **The quality meter 1.1.0** compares each observation file with the set
  nearest the middle of its observations.
- **`fetch-gp`** asks for `FORMAT=csv` with `Accept-Encoding: gzip`, and saves
  the answer decompressed, at most 50 MB before and after. An answer that is
  not 200 stops it with what CelesTrak's usage policy asks next:
  - after a 500 or a 503, wait at least 15 minutes;
  - after a 404, do not ask again;
  - after a 403, read the message;
  - after a 301, correct the URL.
- **`fetch-satchecker`** (`satchecker.py`) asks SatChecker's
  `get-nearest-tle` or `get-nearest-omm` for one object at one time: one
  request, no retries. It refuses an answer with no set, several sets, or
  another object's set.
  - A TLE is converted to OMM form with `sgp4.exporter.export_omm`, which
    sgp4's README documents. For the real sets of ACS 3 and PELICAN 3001 the
    two give the same orbit to 2 mm.
  - The record's `source` names SatChecker's version, the endpoint, its
    `data_source` and `date_collected`, the TLE, and the original set's
    SHA-256.
- **Manifests and the cache** (`orbit_cache.py`, format
  `orbit-watch/reference-orbits` 1.0).
  - An entry names a set by its object, kind, source, epoch and the SHA-256 of
    the original set: of the TLE's two lines, each ending in a newline, or of
    the OMM fields as compact canonical JSON.
  - `fetch-orbits` asks for the set nearest each epoch the cache lacks, one
    request at a time and two seconds apart. It stops at the first answer that
    is not 200, and at any set whose SHA-256 is not the manifest's.
  - The cache keeps SatChecker's answers as received, one file per set named
    by its SHA-256, in `$ORBIT_WATCH_CACHE` or `~/.cache/orbit-watch`.
- **Tests and CI.**
  - The stand-ins for CelesTrak's and SatChecker's answers are built from the
    SIMULATED catalogue: 339001 as an Alpha-5 TLE, `Z9001`. No real set is in
    the repository.
  - `core/tests/data/reference-orbits.json` names four real sets: three of
    PELICAN 3001 and one of ACS 3, objects of SCORE observations. The tests
    that use them are skipped without the cache.
  - CI restores the cache with `actions/cache` v6.1.0, keyed by the
    manifest's hash, and runs `fetch-orbits` before the tests. If SatChecker
    cannot be asked, a warning says so and those tests are skipped.
  - On 2026-11-21 SatChecker returned all four sets by their exact epochs,
    with matching SHA-256s, in 9.5 seconds.

Sources:
- [SatChecker's orbital data access](https://satchecker.readthedocs.io/en/latest/tools_data_access.html)
  (version 1.9.0);
- sgp4 2.27's README, "Export" (`exporter.export_omm`);
- [actions/cache](https://github.com/actions/cache) v6.1.0 (`path`, `key`).

### D-45 Real observations from SCORE

Accepted · 2026-11-21 (with the pull request that implements step 5.2).

- **Fetching** (`score.py`, `orbit-watch fetch-score`). One object and one window per
  command, through `GET /api/observations/search`: pages of 100, at least a second apart,
  at most 200 pages. It stops at the first answer that is not 200, and after a 429 or a
  5xx it says to wait at least 15 minutes. The fetched file keeps SCORE's items as
  received, with the query, the date and the licence.
- **Observation set format 1.1** adds `source.origin`: the source, its URL, the licence
  (SPDX), the observers' ORCID iDs, the source's ID of each observation (one per
  observation, checked), the date fetched, and any uncertainty the converter assumed.
  `converted_from` may be `score`. A set is written as 1.1 only when it has an origin,
  so every other file stays 1.0 byte for byte; the schema is picked by
  `format_version`.
- **Converting** (`orbit-watch convert-score`).
  - Brightness-only observations, and those without a place or a time, are left out
    and counted.
  - A track is one object, instrument and set of observers, with no gap over 15
    minutes. Observations more than 100 m from the track's first place start a new
    track.
  - A station is one instrument and set of observers at one site. Tracks within 100 m
    of a station's first place share it, across every file converted together. Its ID
    is `SCORE-` and the start of the SHA-256 of the place, the instrument and the
    observers. The place is kept as published: verification needs it (P5-06, P5-11).
  - The angle uncertainty is the square root of the larger of SCORE's two variances,
    which is conservative however SCORE measures the right ascension's. A variance of 0
    counts as none.
  - SCORE gives no angle uncertainty for most positional observations, and 0 for some
    tracks. `--assume-angle-uncertainty` and `--assume-time-uncertainty` say what to
    assume. Each file records the value and how many observations it applies to, and
    says it is the converter's assumption, not the observer's statement. Without them
    such observations are left out.
  - `--credits` writes a credits file: every file's observers by ORCID iD, SCORE's
    acknowledgement and the statement it requires, and SatChecker's acknowledgement
    (P5-13).
- **The committed set** (`examples/real/`), fetched on 2026-11-21.
  - 18 tracks from 7 stations and five kinds of instrument: a video camera, DECam on
    the Blanco 4 m, two eVscopes and two phones. 2,223 observations, 0.7 MB.
  - **60″ is assumed** for every angle uncertainty, since SCORE gives none for these.
    It is one arcminute, a round and cautious value. The reference orbit's term
    dominates today's limits anyway (P5-07), and step 5.3 measures what the
    assumption changes.
  - Only civilian objects (D-05), and a test checks the names against the allow-list's
    patterns. The track of a phone whose place moved 7 km in two minutes is left out:
    a set has one station place. `tracks.json` lists the windows and that track.
  - The 18 reference orbits, from SatChecker and nearest each track, are named in
    `examples/real/reference-orbits.json`, not committed (P5-05). CI fetches them into
    its cache.
  - The quality meter's report for each station is committed. A test regenerates them
    from the cache and requires them to match, so a release regenerates them as it
    does the simulated examples.
- **What the quality meter finds** (method 1.1.0).
  - **The video camera:** angle precision 9.6″, timing 0.017 s, no clock offset.
  - **The iPhone 12 Mini:** every object about 1.6 s behind its prediction, in
    September and in November, which the meter reads as the phone's clock.
  - **The iPhone 17 Pro:** tens to hundreds of seconds off, wrong times or wrong
    objects.
  - **DECam and the eVscopes:** two observations per object, too few for precision.
- **Phase 0's last criterion** ("one real public IOD example") is met with this set,
  in Orbit Watch's format, since SCORE's observers have no IOD station numbers (P5-06;
  #8 closed).
- **Personal data.** The [privacy notice](legal/privacy-notice.md#observations-that-others-have-published)
  has a section of its own, and the [data inventory](personal-data.md#observations-that-others-have-published)
  a table. GDPR article 14 was read, with these results:
  - articles 14(1) and (2): what a person is told, including the source;
  - article 14(3): within a month;
  - article 14(5)(b): where telling each person would be disproportionate, "making the
    information publicly available".

  We have only ORCID iDs, not contact details. The public notice is the measure taken
  here. Reaching the observers directly is a follow-up (#113). This is our reading,
  not legal advice.

Sources:
- [SCORE use policy](https://score.cps.iau.org/policy),
  [data format](https://score.cps.iau.org/data-format),
  [API](https://score.cps.iau.org/api-access), and the OpenAPI description (version
  2.0.0);
- [GDPR article 14](https://gdpr-info.eu/art-14-gdpr/). EUR-Lex's page asked for a
  browser check, which an automated client does not pass.

### D-46 The method measured on real data

Accepted · 2026-11-21 (with the pull request that implements step 5.3). The numbers are
in [real-data-validation.md](real-data-validation.md).

- **The measurement** (`validation.py`, `orbit-watch measure-method`). Method 2.1.0
  runs, as it is, over every real track: each one is verified from its file's bytes as a
  delivery for a request of its own object over its time. The request's requirements let
  every track through, so the residual check decides. Faults are put into copies in
  memory and never written: times shifted, the station moved or rounded, another object,
  positions made from the reference orbit, other angle uncertainties, older element
  sets. The command writes `validation/real/results.json`, `known-answers.json` and the
  tables of the page; with `--check` it writes nothing and fails on any difference.
  `results.json` names the method, orbit-watch's version and the SHA-256 of every
  input.
- **The validation set** (`validation/real/`). 38 more tracks from SCORE, from the
  instruments and observers of `examples/real/`: four more nights of the video camera,
  seven DECam tracks and 27 phone tracks, 13,713 observations. Together with the
  example, 56 tracks and some tens as P5-06 says, in two directories because they serve
  two purposes. It is credited, named in the privacy notice and the data inventory, and
  removable on request like the example. Six windows were not fetched, as not clearly
  civilian: two unidentified objects, a Shijian satellite, COSMO-SkyMed and a US Air
  Force satellite. `tracks.json` gives each reason.
- **The element sets** for the measurement are named in
  `validation/real/reference-orbits.json`: the nearest set of each new track, and for
  each track that passes the sets nearest 1, 3, 7 and 14 days before it. CI fetches them
  into its cache with the others, and restores a partial cache, so that only new sets
  are asked for.
- **What it found**, in short:
  - the video camera's 8 tracks and the eVscopes' 2 all pass;
  - all 35 phone tracks fail, rightly: their times are 1.3 to 1.9 s late. With the
    offset taken out, 25 of them pass;
  - 9 of DECam's 11 fail, for reasons not understood;
  - in low orbits the orbit term's 5 km is 82 to 97 % of the limit's square, so a time
    error of half a second passes and one second does not;
  - in low orbits an element set about 3 days old rejects good tracks, while the method
    accepts sets up to 7 days old;
  - no track passed for another object (397 tries), and every track made from the
    reference orbit passed;
  - rounding the station to about a kilometre, and any assumed angle uncertainty from
    10″ to 120″, changed no result.
- **The method is unchanged.** The page lists five candidates (the reference orbit's
  age, the orbit term, time uncertainties in high orbits, rounding, and the phones'
  timestamps). Each needs a decision of its own.
- **Known answers.** 39 real tracks with a settled answer join reviewer calibration: the
  video camera's 8 to approve and 31 phone tracks to reject. They are written by the
  measurement, by rules the page gives. DECam's tracks are left out, and so are the
  eVscopes': each is one observation that SCORE holds twice, so its delivery fails as a
  duplicate. `calibration.build_real_files` makes a task's
  request and report from one of them. The service uses them once it verifies real
  deliveries (steps 5.4 and 5.5): a round about real observations needs real
  calibration tasks, since a SIMULATED one gives itself away.
- **The converter leaves out a place that jumps.** A phone's place sometimes jumps by
  0.1 to 10 km for one observation and comes back for the next. The converter split the
  track there, and in one minute two pieces of a track could get the same file name,
  so that one overwrote the other. Now an observation is left out when no other
  observation of its track lies within 100 m of it while most of them share a place;
  the file says how many and how far, and the converter's summary counts them. A phone
  that truly moves keeps all its observations. `convert-score` also refuses to write two
  tracks to one file name. The files of `examples/real/` are unchanged.
- **Correction to D-45.** The track of 55945 was not "a phone whose place moved 7 km in
  two minutes". Six of its 57 observations had places 0.1 to 10 km away, and the other
  51 shared one. It is in the validation set now, with those six left out.
  `examples/real/tracks.json` and its README say so.
- **Questions for the observers**, added to the follow-up about telling SCORE
  ([#113](https://github.com/Haiko-Innovations/orbit-watch/issues/113)): how the phones'
  times are recorded, and what DECam's two observations of a track are.

### D-47 Reference orbits in the service

Accepted · 2026-11-21 (with the pull request that implements the first part of step
5.4). Step 5.4 comes in three pull requests: this one keeps element sets and verifies
against them; the next fetches them from CelesTrak and SatChecker (P5-02, P5-03); the
third brings real objects onto the allow-list (P5-08).

- **Kept in PostgreSQL** (migration 0010, table `element_sets`). Each set is kept with:
  - its source: `celestrak`, `satchecker` or `uploaded`;
  - the time it was fetched or uploaded;
  - its epoch;
  - the SHA-256 of its OMM fields, as reports name it;
  - for an upload, the administrator who made it;
  - the record itself. Its `source` field keeps what the fetcher recorded, and adds the
    service's name for the source, `kept_from` and `fetched_at`.

  The same set kept twice is kept once.
- **Verification uses the stored sets.** For a request's object the service builds a
  catalogue of every stored set of that object, and verification picks the one nearest
  the middle of the observations (P5-04). The report names it, its source included,
  never its TLE lines. An object without stored sets is verified against the service's
  own catalogue, as before. The SIMULATED objects keep their own orbits, and a set for
  one of them is refused, so that a real set never meets a SIMULATED label (P5-09). The
  quality meter uses the stored sets too.
- **Uploaded by hand.** `POST /v1/admin/element-sets` takes an `orbit-watch/gp-catalog`
  document, or CelesTrak's OMM JSON or CSV. The sets are labelled as uploaded; a
  SIMULATED catalogue is refused. The command line has `orbit-watch admin
  upload-orbits`, and [operations.md](operations.md#reference-orbits) says how.
- **Named, not served** (P5-05). `GET /v1/public/reference-orbits` lists the object, the
  epoch, the source, the time fetched and the SHA-256 of each set, never its elements.
  Anyone can fetch the same set from the same source and repeat a verification.
- **Backups.** The daily backups hold the stored sets, encrypted with age like the rest
  of the database (D-39). GitHub keeps only the ciphertext, so this publishes nothing,
  and a restore brings back the sets uploaded by hand.

### D-48 The follower fetches reference orbits

Accepted · 2026-11-21 (with the pull request that implements the second part of step
5.4). It carries out P5-02 and P5-03 in the service.

- **What is fetched.** After its other work, each run of the follower fetches what open
  requests need: requests that are open, funded or reserved, for real objects on the
  allow-list. Nothing is fetched for a SIMULATED object.
  - **CelesTrak:** an object's current GP data by its catalogue number, CSV with gzip,
    at most once every two hours. Only while its request's window has not ended and
    starts within a day: a set fetched earlier would be replaced by newer ones before
    verification needs it.
  - **SatChecker:** for a window that has ended, such as a replay's (P5-10, step 5.5),
    the set nearest the middle of the window. `get-nearest-tle` serves catalogue numbers
    below 100,000 and `get-nearest-omm` the rest. It is asked for once, and not at all
    when a kept set lies within a day of the middle. The middle of the window stands for
    the middle of the observations, which have not been delivered yet.
  - An object is asked for once, however many requests name it.
- **A few per run.** At most three requests per run, two seconds apart, the objects
  asked for least recently first. With the follower every 15 minutes, that keeps 24
  objects current per two-hour update; the testnet has far fewer. Each request times out
  after 30 seconds (CelesTrak) or 60 (SatChecker), so a run stays well inside a
  function's 300 seconds.
- **Outside the lock.** The requests are made outside the database's lock, so that
  other calls do not wait. Each is recorded as asked for just before it is made, in a
  transaction, so that another process does not make it too, and each answer is kept in
  a transaction of its own.
- **Stop, and tell a person.** These stop that source; the other source goes on:
  - the first answer that is not 200;
  - an answer of 200 without the object's element sets, since the source has changed
    something;
  - no answer at all. A timeout or a refused connection may be CelesTrak's firewall
    blocking the address that Vercel's functions share (P5-02's risk), and a person
    should know.

  The stop records the time, the object, the HTTP status and up to 500 characters of the
  reason. After a 500 or a 503, or no answer, the source also waits at least 15 minutes,
  even once resumed. An object that answered 404 is not asked for again until an
  administrator asks for it again.
- **The health endpoint.** `GET /v1/health/reference-orbits` answers `503` while a
  source is stopped. The hourly uptime check calls it, so a stop opens the alert issue
  like any other failure (D-39), with no new secret. It shows the stop, but not who
  resumed it.
- **Resumed by an administrator.** `POST /v1/admin/reference-orbits/resume`, or
  `orbit-watch admin resume-orbits`, clears a source's stop, and `ask_again` forgets
  what the source answered for the objects it names. The administrator is recorded.
  [operations.md](operations.md#fetching-reference-orbits-stopped) is the runbook.
- **Off by default.** The follower fetches only with `ORBIT_WATCH_FETCH_ORBITS=1` or
  `serve --fetch-orbits`, so local runs, CI and the end-to-end tests make no outside
  call. Production turns it on with step 5.4's third part, when real objects come onto
  the allow-list; until then there is nothing to fetch.
- **A replay delivered at once** would find no set yet. Its station waits for a run of
  the follower, or an administrator uploads the set; step 5.5 decides which.

CelesTrak's [usage policy](https://celestrak.org/usage-policy.php) was read again on
2026-11-21, still the version of 2026-11-16. It gives no number for its limits, and
does not say that a repeated download of unchanged data gets a 403, as
[data-sources.md](data-sources.md) said; that is corrected. A 403 is "usually sent in
response to abusive behavior".

### D-49 Real objects on the allow-list

Accepted · 2026-11-21 (with the pull request that implements the third part of step
5.4). It carries out P5-08 in the service.

- **The list.** Requests may target the objects of:
  - the service's own list, the SIMULATED objects, as before;
  - CelesTrak's groups `science`, `education`, `amateur` and `cubesat`;
  - an administrator's additions.

  It leaves out the objects of the groups `military` and `radar`, and those whose names
  match the patterns of `orbit-watch allowlist build`. The patterns apply to the name a
  group or an administrator gives, and to the names of the object's stored element sets.
  The group names are those of
  [CelesTrak's index of GP data](https://celestrak.org/NORAD/elements/), read on
  2026-11-21. `radar` is excluded because radar calibration objects are often run by
  armed forces; a civilian object wrongly left out is a small loss.
- **Fetched once a day.** The follower fetches each group at most once a day, CSV with
  gzip, with the requests that the objects of open requests leave in a run (D-48). The
  excluded groups come first, and the included groups count only once both excluded
  groups have been fetched, so that an object of both is never allowed in between. A
  group's answer stops CelesTrak like an object's, and after a stop the group may be
  asked for again two hours later, once a person has resumed. The service keeps each
  group's objects and names, with the time and the SHA-256 of the answer (migration
  0012), not its element sets.
- **An administrator's additions.** `POST /v1/admin/allowlist`, or `orbit-watch admin
  allow`, adds an object with its name and a reason, after the administrator has checked
  its owner in the satellite catalogue. The reason and the time are public; the
  administrator is recorded but not shown. An addition is refused for a name that
  matches a pattern, an object of an excluded group, a SIMULATED object, and one on the
  service's own list. `orbit-watch admin disallow` takes it back.
- **Labelled.** `GET /v1/public/targets` gives each object `simulated` and `source`:
  `service`, `celestrak` with its groups, or `administrator` with its reason. Its
  `simulated` is true only when every object is SIMULATED.
- **Refused when made.** A request for an object not on the list is refused when it is
  made (`target_not_allowed`), not only at delivery, so that the service never publishes
  a request for an object it does not allow.
- **Verified against the real list.** A delivery for a real object is verified against a
  target policy of the real objects only, which names the groups' answers by their
  SHA-256. Its report then does not say SIMULATED (P5-09). Every other delivery uses the
  service's own list, as before.
- **The web application** marks a request SIMULATED when its target is. Simulated
  stations observe only the objects of the service's own catalogue; observing real
  objects with them is step 5.5.
- **An object that leaves the groups** leaves the list at the group's next fetch, and a
  delivery for it then fails the target check. If that happens to an open request, an
  administrator can add it back with a reason. Keeping such objects by themselves would
  also keep an object that has moved to `military`.
- **Production turns fetching on** with `ORBIT_WATCH_FETCH_ORBITS=1`, once this is
  merged and deployed. The first two runs of the follower fetch the six groups.

### D-50 Simulated stations on real objects

Accepted · 2026-11-22 (with the pull request that implements the first part of step
5.5). It carries out P5-09's "Simulated stations may observe real objects".

- **Step 5.5 in three parts**, one pull request each:
  1. simulated stations on real objects (this decision);
  2. replays, created by an administrator and delivered by a replay station under the
     observers' names (P5-10);
  3. labels by source on every page, tested end to end, and in the local stack a
     request for a real object and a SIMULATED one side by side, and a replay settled.
- **A request for a real object may be SIMULATED.** The requester decides:
  - a real request asks for real observations;
  - a SIMULATED one lets simulated stations observe the real object, as a
    demonstration.

  The web application asks with a box that is not ticked in advance, so a request for a
  real object is SIMULATED only when the requester says so. A request for a SIMULATED
  object must be SIMULATED, and is refused otherwise when it is made
  (`simulated_target`): nobody can make real observations of an object that does not
  exist.
- **Along the stored set nearest the window.** A station's simulator
  (`POST /v1/requests/{id}/simulate`) and the administrator's
  (`POST /v1/admin/simulate`) observe a real object along one stored element set: the
  one whose epoch is nearest the middle of the window. Verification later picks the set
  nearest the middle of the observations (P5-04). With the follower's sets that is
  normally the same set.

  Without a stored set, or with none within the method's 7-day age limit, simulation is
  refused (`no_reference_orbit`, 409). The follower fetches the set from a day before
  the window starts (D-48), so the station tries again later. The service's own objects
  keep its own catalogue, as before.
- **A real request takes no SIMULATED observations.** A station's simulator refuses it
  (`real_request`, 409). On such a request's page, the web application shows no
  simulate button and says why. Verification already fails SIMULATED observations
  delivered for a real request (`simulation_label`).
- **Labelled.** The observations and the report of such a delivery say SIMULATED
  (`simulated_input`). The report names the real set by its source, epoch and SHA-256
  (P5-04), never the set itself (D-06). Labels by source on every page are the third
  part.

### D-51 Replays

Accepted · 2026-11-22 (with the pull request that implements the second part of step
5.5). It carries out P5-10 in the service.

- **The request names the replay.** A replay request is request format 1.1, whose
  `replay` block names:
  - the observation file it replays, by its SHA-256;
  - the replay station that delivers it;
  - the file's source, licence and observers' ORCID iDs.

  Every other request stays format 1.0, byte for byte. `orbit-watch admin replay` builds
  the document from a published file whose `source.origin` names where it comes from,
  such as one in `examples/real/` (D-45). The window runs from five minutes before the
  first observation to five minutes after the last, and the requirements are those that
  the file meets.
- **Only an administrator creates one** (`POST /v1/admin/replays`), for a requester, who
  then publishes and funds it as usual. A requester's own request with a `replay` block
  is refused (`replay_admin_only`). The window must have ended (`replay_window_not_past`)
  and the delivery deadline must be in the future. A replay is never SIMULATED, and its
  object must be a real object on the allow-list.
- **Only the replay station reserves and delivers it** (`replay_station_only`), and only
  the file it names (`not_the_replayed_file`). The service refuses both before it asks
  the chain. The contract does not know replays; the replay station is the maintainer's
  own.
- **The reference orbit comes first.** Once the request is open, the follower fetches
  SatChecker's set nearest the middle of its window (D-48). Until the service keeps a set
  within the method's 7-day age limit of that middle, a delivery is refused
  (`reference_orbit_pending`, 409), and the replay station tries again later. An
  administrator may upload the set by hand instead (D-47). Verification then uses the
  stored set nearest the observations (P5-04), and the report names it as SatChecker's.
- **The place as published.** A replay delivers its file as it is. The public service's
  rule against station places more precise than two decimals (P4-09) does not apply to
  it. The observer published the place with the observations, and verification needs it
  (P5-06). Every other delivery keeps the rule until step 5.6 replaces it (P5-11).
- **Never the observer.** The replay station is the request's observer in the lifecycle
  and on the chain, since the escrow pays it. The testnet reward goes to its wallet, and
  testnet USDC has no value (P2-02). The request names the observers, and the delivered
  file names them too. The pages show the replay station as the replay station, not as
  the observer: that is the third part, with the labels by source.
- **The report stays as it is.** It names the delivered file by its SHA-256, and that
  file and the request name the source, the observers and the licence. Adding them to
  the report would be a new method version, which every request's terms name. That is
  not worth it for a field that the two files already carry.

### D-52 Labels by source on every page

Accepted · 2026-11-22 (with the pull request that implements the first half of the third
part of step 5.5). It carries out P5-09's labels and P5-13's public page.

- **The third part in two pull requests.** This one adds the labels, in the API and on
  every page, the data sources page and the terms of use. The next one adds a real
  object and a replay to the local stack, and tests their labels end to end; then step
  5.5 is done.
- **The service says what each part is.** `labels` in a request's summary, and in
  `GET /v1/requests`, `GET /v1/public/open-requests` and the administrator's overview,
  gives:
  - whether the request is SIMULATED;
  - its object: SIMULATED or real, and why it is on the allow-list;
  - its reference orbit: CelesTrak, SatChecker, uploaded by hand or the service's own
    catalogue, with its epoch and SHA-256. Once a report names the set, the label is
    that set (`final`). Before that, it is the stored set nearest the window, which may
    still change;
  - its observations, once delivered: SIMULATED, replayed or a station's own, and the
    station that delivered them;
  - a replay's source, licence and observers.

  SIMULATED is said of what is simulated, and of nothing else. A real object observed by
  simulated stations is a real object with a real orbit and SIMULATED observations.
- **The web application shows them** on every page that shows objects, reference orbits
  or observations. A request's page and the open requests show all of them. The lists of
  requests (yours, a station's, the administrator's) tag each request: SIMULATED, a real
  object, a replay. The new-request page says what each object on the list is.
- **A review task labels its files, not its request.** A task names no request, so that
  real and calibration tasks look alike (D-23), and the service gives it no labels. The
  task's page reads them from the files it shows: the request document, the observation
  file and the report.
- **The station quality meter's page** already says SIMULATED of SIMULATED input, from the
  meter's report. It shows no request and no reference orbit of the service, so it gets
  no other label.
- **The testnet label** on every page now says that SIMULATED and real data run side by
  side, and that every object, reference orbit and observation says which it is. It no
  longer says that all data is SIMULATED, which stopped being true once production fetched
  real objects (D-49).
- **The terms of use** said the same, and are corrected, version of 22 November 2026:
  - the data is SIMULATED and real side by side;
  - the allow-list holds the service's SIMULATED objects and real objects from public
    catalogues.
- **A data sources page** (`#/data-sources`, the Markdown file `docs/legal/data-sources.md`)
  credits CelesTrak, SatChecker and SCORE. It gives the acknowledgements that SatChecker
  and SCORE ask for, and the statement that SCORE asks for on "any publication,
  presentation, website or web service that uses SCORE data" (P5-13). It is linked from
  every page and from the terms of use.

  The Markdown reader of `docs/legal` learns quotes for these statements, and still
  refuses anything else it does not read.
- **Before the first replay on the public service** (step 5.8), the privacy notice and the
  data inventory must name the observers' ORCID iDs that replays publish. Step 5.6
  changes both anyway.

### D-53 A stand-in for a real object in the local stack

Accepted · 2026-11-22 (with the pull request that finishes step 5.5). The local stack, and
the end-to-end tests on it, show a real object and a replay beside the SIMULATED requests.
There are no real data in them:
- No test in CI calls an outside service (P5-15), so the stack fetches nothing.
- No real element set is committed (D-06, P5-05).

So the stack uses made-up stand-ins (`core/tests/stand_ins.py`):
- **A stand-in for a real object**, 339990 "LOCAL STAND-IN 339990". An administrator adds it
  to the allow-list with the reason "LOCAL TEST: stands in for a real object in the local
  stack; its orbit is made up." Its element set is SIM-CUBESAT-A's elements under its
  number, uploaded by hand, so it is labelled as uploaded. The number comes after the
  SIMULATED objects', so that they stay first on the list. SGP4 reads numbers up to 339999,
  and no catalogue will reach this one for decades.
- **SIM-REQ-3010**, a SIMULATED request for the stand-in. SIM-ESPOO fulfils it with
  SIMULATED observations along the stand-in's orbit (D-50), and it waits in its challenge
  period.
- **REQ-3011**, a real request for the stand-in. It is funded and open beside the
  SIMULATED ones.
- **REPLAY-3020**, a replay of observations "published" by a made-up observer at a made-up
  source. It credits ORCID's documented example iD of a fictitious researcher,
  0000-0002-1825-0097. `station:LOCAL-REPLAY` delivers it, and it settles (D-51).

The labels call the stand-in a real object, which is what it stands in for. Its reason on
the list says that it is made up, and so do the stack's notice and the files. Real data run
end to end on the public service in step 5.8. The off-chain test `test_stand_ins.py` seeds
the same stand-ins without a chain, so a mistake in them shows up before the end-to-end
tests run.

With this, step 5.5 is done:
- in the local stack a request for a real object and a SIMULATED one run side by side;
- a replay settles;
- the labels are tested end to end on every page that shows objects, reference orbits or
  observations.

### D-54 The observer chooses how precisely the place is published

Accepted · 2026-11-22 (with the pull request that implements the first part of step
5.6). It carries out the choice of P5-11.

- **Step 5.6 in two parts:**
  1. the choice, its change, the privacy notice and the data inventory (this decision);
  2. the profile as the station's place for every format: IOD and CCSDS TDM deliveries
     take their station's place from it, and a JSON delivery from another place is
     refused.
- **The choice is part of saving a profile.** `PUT /v1/stations/{party}/profile` takes
  `"place": "exact"` or `"place": "kilometre"` beside the profile, and refuses a profile
  without one (`place_required`). The station's page asks with two choices, neither
  selected in advance. Before the observer chooses, the page says three things: that
  verification needs a precise place; that a station may be someone's home; and that
  files already delivered keep the place they were delivered with. With `kilometre` the
  coordinates are kept to two decimals of a degree. With `exact` they are kept as given.
  The choice is kept with the profile (migration 0013).
- **It can be changed at any time**, for later deliveries. Choosing `kilometre` again
  drops the exact place from the service. Choosing `exact` again needs the exact place
  given again, since the service no longer has it. Files already delivered are not
  touched: their SHA-256 is on the chain.
- **Existing profiles stay at about a kilometre** until their owner chooses. A profile
  saved before this step has no choice. `GET` reports it as `kilometre` with
  `place_chosen: false`, and the page selects nothing for it. The service rounds its
  SIMULATED observations as before.
- **Deliveries follow the choice.** The public service's refusal of station coordinates
  more precise than two decimals (P4-09) applies to a station that chose `kilometre`,
  that has not chosen, or that has no profile. A station that chose `exact` may deliver
  files that name its exact place. A replay delivers its file as published (D-51).
  Step 5.6's second part replaces this rule with the profile as the place.
- **The privacy notice** is version of 22 November 2026:
  - the station's profile and its files are kept exactly or to about a kilometre, as the
    observer chooses, and the choice can be changed;
  - replays publish their observers' ORCID iDs, source and licence on each replay's page
    and in its files (D-52).

  The data inventory lists the choice and the replays' tables.

### D-55 The profile is the station's place for every format

Accepted · 2026-11-22 (with the pull request that finishes step 5.6). It carries out
P5-11's last point: a station is verified with the place it publishes, and that place is
its profile's, as precisely as its observer chose (D-54).

- **A JSON delivery names its profile's place.** Its station's latitude, longitude and
  height must be the profile's, or the delivery is refused before anything is kept or
  asked of the chain (`wrong_place`, 422). The message names both places. With
  `kilometre` the profile is at two decimals, so a more precise file is from another
  place. This replaces the refusal of files more precise than two decimals (P4-09,
  `too_precise`). A profile saved before the choice is used at two decimals.
- **An IOD or CCSDS TDM delivery is placed at its profile.** Such a file names only a
  station number or a `PARTICIPANT_1`. The service writes a sites document that places
  that station at the profile's place, without the station's name, and verifies the
  delivery with it instead of the service's own sites file. The document is kept with
  the delivery and published with the request's files as `station_place` (migration
  0014), so that anyone can repeat the verification. On a chain it is kept with the
  upload until the chain's event arrives. A delivery names one station, its own. An IOD
  file whose number differs from the profile's IOD number is refused (`wrong_place`).
  So is a file that names several stations.
- **The public service needs a profile to deliver** (`profile_required`, 409). Without
  `--station-decimals`, as in the local tools and most tests, a station without a profile
  delivers as before, and a station with one follows these rules. The rules change no
  report and no method: the place is an input, as before.
- **A replay delivers its published file as it is** (D-51): its place was published with
  it, by its observer, and verification needs it. The rules do not apply to it.
- **The local stack** saves SIM-ESPOO's profile to about a kilometre, at the place of its
  datasets, after the seeded deliveries.
- **The privacy notice** says that the profile's place goes with every delivery: in the
  file, or for IOD and TDM files, in the station place published with them. It is still
  the version of 22 November 2026, the day it changed (D-54).

With this, step 5.6 is done:
- a station cannot be saved without the choice;
- a delivery from another place is refused;
- changing the choice is tested;
- the notice's version date is updated.

### D-56 The Sun's place from a short formula

Accepted · 2026-11-22 (with the pull request that implements the first part of step
5.7). It carries out P5-12's Sun and records its measurement.

- **Step 5.7 in three parts:**
  1. the Sun in the core, measured against a JPL ephemeris (this decision);
  2. the simulator observes only objects the Sun lights under a dark sky (#7), and the
     committed simulated examples are regenerated, with their changes explained;
  3. a station's visible passes for a request, in the API and the observer's view.
- **The US Naval Observatory's formula** (`orbit_watch.sun`), read on 2026-11-22 on its
  page, gives the Sun's right ascension and declination of date. Skyfield's precession
  and nutation matrix turns them into the ICRS axes of its positions. Its Earth rotation
  gives a station's geodetic zenith. No ephemeris file is needed.
- **A dark sky** is the Sun at least 6° below the horizon by default
  (`DARK_SKY_SUN_ELEVATION_DEG`). The value is a setting, used in the next parts.
- **Sunlight** is outside a cylinder of the Earth's equatorial radius behind the Earth.
  A cone would be more exact at the edges, but the measurement shows that the cylinder
  is enough here.
- **Measured once against DE421** with `orbit-watch measure-sun`, recorded in
  `validation/sun/results.json` and [visibility.md](visibility.md):
  - the Sun's direction is at most 55.9″ off over 1900–2049, median 13.0″;
  - the elevation at SIM-ESPOO is at most 37.4″ off through 2026;
  - the dark-sky decision at −6° differs in 3 of 52,560 samples;
  - sunlight differs from Skyfield's `is_sunlit` in 1 of 60,480 samples, for at most
    10 seconds.

  DE421 is fetched only with `--fetch`, into the cache outside the repository, and
  never in CI. A test repeats the measurement when the cache has it, as the real
  element sets' tests do (P5-05).

### D-57 The simulator observes only what a station can see

Accepted · 2026-11-22 (with the pull request that implements the second part of step
5.7). It carries out P5-12's simulator and closes issue
[#7](https://github.com/Haiko-Innovations/orbit-watch/issues/7).

- **Visible passes** (`orbit_watch.passes`). A pass runs from rise to set above an
  elevation limit. Its visible part is where the object is sunlit and the station's sky
  is dark (D-56), sampled every 10 seconds. Step 5.7's third part lists these passes for
  a request.
- **The simulator observes only there.** Its observations centre on the highest point of
  each pass's visible part, and those outside the visible part are left out. A pass
  without one gives none. The dark sky is a setting of the simulator, `dark_sky_deg`,
  −6° by default, and `None` keeps the old way. The command line has `--dark-sky-deg` and
  `--any-light`. It is not a field of the station profile: that would be a new profile
  format, and no observer needs it yet. Issue #7 asked for a profile field; this records
  why it is not one.
- **The SIMULATED orbits move to the evening.** The bundled catalogue's sun-synchronous
  objects crossed the equator northwards at about 22:40 local time. Over Finland in
  November, their passes fell at about 22:30, in the Earth's shadow, or at about 10:30,
  in daylight. No station could ever see them, and the simulator would have given no
  observations at all.

  Their right ascension of the ascending node is now 330° instead of 15° (SIM-ROCKET-BODY
  330.2° instead of 15.2°), so they cross the equator at about 19:30. Their two evening
  passes in the demo's window, at about 15:45 and 17:20 UTC, are lit under a dark sky at
  each of the four simulated stations. Nothing else in the orbits changed. The service's
  own catalogue changes with them; reports already published keep the catalogue they
  name by its SHA-256.
- **The committed simulated examples are regenerated**, with these changes:
  - `examples/simulated`: the observations moved from about 18:54 and 20:29 UTC to
    about 15:44 and 17:19 UTC. Each dataset has as many observations as before, except
    `too_imprecise`, which has 7 instead of 10: SIM-OULU's binoculars now see two of
    their three passes. All six datasets keep their verdicts and their failing checks.
  - `examples/phase1`: the five requests keep their outcomes: accepted, rejected twice,
    disputed and expired.
  - The quality meter's example is regenerated. The transcripts of phases 2 and 3 are
    records of runs on Base Sepolia, and stay as they were.
  - The Sun measurement's sunlight part follows SIM-CUBESAT-A's new orbit. It now
    differs from Skyfield's `is_sunlit` 7 times in 60,480 samples, each for at most
    10 seconds and all at the shadow's edge, instead of once.

### D-58 A station's visible passes for a request

Accepted · 2026-11-22 (with the pull request that finishes step 5.7). It carries out
P5-12's pass list.

- **`GET /v1/requests/{id}/passes`** lists the request's object's passes over the station
  in the request's window, with `orbit_watch.passes` (D-57). For each pass it gives the
  rise, the highest point and the set, and the visible part: its start, highest point
  and end, lit by the Sun under a dark sky, −6° by default. It also gives the elevation
  limit and dark sky it used, the place it used, and the reference orbit's label (D-52).
- **The station's own place and instrument.** The passes are over the station profile's
  place, rounded to about a kilometre unless the observer chose `exact` (D-54). They are
  above the instrument's elevation limit, `min_elevation_deg` in the profile. P5-12 spoke
  of the request's elevation limit, but a request has none: its requirements are about
  the observations, not the sky. A station without a profile is asked to register one
  (`no_profile`).
- **For the requests a station may observe:** a request that invites observers, open or
  funded, and one the station reserved. Anything else is `unknown_request`, as if it
  were not there. Only stations ask.
- **The orbit is the one a simulation of the request would use.** For the service's own
  objects it is the service's own catalogue. For a real object it is the stored set
  nearest the window, or `no_reference_orbit` without one within 7 days (D-50).
- **At most a week.** A longer window is listed for its first seven days, and
  `window_cut` says so, so that one call stays short.
- **The observer's view**: a request's page shows a station "Your visible passes" as a
  table while the request is open, funded or reserved by it. Each row has the rise, the
  highest point with its elevation, the set, and the visible part or why there is none.
  Each open request links to it for a station.

With this, step 5.7 is done:
- the Sun's error against JPL's DE421 is measured and recorded (D-56);
- the committed simulated examples are regenerated and their changes explained (D-57);
- the pass list is tested, in the API and end to end.

## Phase 6 decisions

P6-01 to P6-12 were proposed for the
[roadmap](roadmap.md#phase-6-more-precise-reference-orbits-and-identification-target-version-070)'s
phase 6, more precise reference orbits and identification, in
[#137](https://github.com/Haiko-Innovations/orbit-watch/issues/137), and approved by
the maintainer on 2026-11-23, after a look at the data the same day:
- **Public data for an orbit determination of our own is thin.** SCORE held 42,686
  observations of 3,353 objects. Dense positional data came from two observers: a
  video camera, with 24,463 observations of ACS 3 in September–December 2024, and a
  phone whose times run 1.3–1.9 s late. Its 100 most recent observations were all
  the phone's. Windows of a few days in which two or more stations saw the same
  object were a handful: two for SPACEMOBILE-002 within three days, two for
  SPACEMOBILE-006 within seven, none for the others looked at.
- **More precise orbits exist already.** CelesTrak's supplemental GP (SupGP) is
  fitted to operators' own orbits, to about 0.15–0.3 km for Starlink. For AST
  SpaceMobile's 13 satellites, CelesTrak's standard GP lay 0.15 to 31.6 km from
  SupGP over the next six hours.
- **Few of our objects have them.** Of the 204 real objects on the allow-list, 6 had
  SupGP: the ISS, CryoSat-2, Swarm A, B and C, and PELICAN-1.

So phase 6 first uses the precise orbits that exist, then measures and adds an
orbit determination of its own, and then identifies closely spaced objects. Code
waits for nothing outside the repository, as in phase 5 (P5-14).

Facts were checked on 2026-11-23; the sources are listed under each decision.
Versions are chosen, and checked, when they are used.

### P6-01 More precise reference orbits, and identification, with test money

Accepted · 2026-11-23. Phase 6 makes the reference orbit more precise, and uses it
to identify objects:
- **operators' own orbits**, through CelesTrak's SupGP, where an operator publishes
  them;
- **an orbit determination of our own**, from accepted deliveries;
- **identification** of an object among one launch's objects.

Everything else stays as it is: Base Sepolia only, testnet USDC, the simulated
objects and stations labelled SIMULATED, and real data from public sources.

Not in phase 6:
- real money, and bonds for reservations, challenges or reviewers;
- the community network ([decentralisation.md](decentralisation.md));
- the web application's redesign
  ([#97](https://github.com/Haiko-Innovations/orbit-watch/issues/97)): a step adds
  only the labels and views it needs;
- asking observers or anyone else for data (P6-10).

### P6-02 Measure first, again

Accepted · 2026-11-23. As P5-07, the method changes only after a measurement.
Step 6.1 measures how far CelesTrak's GP sets are from operators' orbits:
- **the truth** is a fresh SupGP set fitted to an operator's orbit (P6-03), for a
  sample of objects from the small SupGP sources;
- **the GP sets** are SatChecker's past sets of the same objects, of different ages,
  one request at a time (P5-03). SupGP keeps no history, and SatChecker keeps GP
  only ("celestrak" or "spacetrack" as its data source);
- **the comparison** propagates both over the six hours after the SupGP epoch, and
  reports the distance along track, cross track and radially, by orbit class,
  source and the GP set's age.

It also repeats the first look at SCORE's coverage for orbit determination. The
results go to a page in `docs/`, reproducible with one command from a cache outside
the repository. No element set is committed (P5-05).

Sources: CelesTrak's
[SupGP comparisons](https://celestrak.org/NORAD/elements/supplemental/) (the AST
SpaceMobile table of 2026-11-23 15:25 UTC);
[SatChecker's response fields](https://satchecker.readthedocs.io/en/latest/api_response.html).

### P6-03 Operators' orbits from CelesTrak's SupGP

Accepted · 2026-11-23. CelesTrak's supplemental GP is "derived directly from
owner/operator-supplied orbital data". Its sources include SpaceX's public
Starlink ephemerides; OneWeb's, Kuiper's and AST SpaceMobile's ephemerides on
Space-Track, "with permission" of each; Planet's; NASA's ISS ephemeris; and the
laser-ranging predictions (CPF). Each set has a `DATA_SOURCE`, such as `AST-E`
or `CPF`.
- **One object at a time**, by catalogue number, as CSV with gzip. CelesTrak's
  usage policy (updated 2026-11-16) asks for "a 2-hour minimum" for SupGP, as for
  GP. Only the objects of open requests are fetched, and the first answer that is
  not 200 stops fetching and tells a person, as D-48.
- **The set for a window.** "SupGP data is fitted from the current epoch forward,
  as opposed to GP data where that is fit to past observations." An object may
  have several sets, for example from several laser-ranging prediction centres or
  the ISS's 6-hour segments. Verification uses an operator-derived set whose epoch
  is the latest at or before the window, and otherwise GP as now.
- **Which sources count** as an operator's orbit is chosen in step 6.2 from the
  measurement: ephemerides and state vectors (`-E`, `-SV`, `CPF`), not almanacs or
  legacy TLEs.
- **Replays** keep SatChecker's GP, since SupGP keeps no history.
- **Nothing is committed** (D-06, P5-05). The report names the set's source,
  `DATA_SOURCE`, epoch and SHA-256, and the labels say "operator's orbit via
  CelesTrak".

Sources: [How to Perform SupGP Queries](https://celestrak.org/NORAD/documentation/sup-gp-queries.php)
(updated 2026-05-26); [SupGP data](https://celestrak.org/NORAD/elements/supplemental/);
[usage policy](https://celestrak.org/usage-policy.php).

### P6-04 Objects whose operators publish their orbits

Accepted · 2026-11-23. An operator that publishes its satellites' orbits for
everyone is open about them. So D-05's allow-list gains the objects of these
SupGP sources: **Starlink, OneWeb, Kuiper, AST SpaceMobile, Planet, the ISS and
the laser-ranging satellites**. GPS and GLONASS stay off: armed forces run them.
D-05's name patterns still apply to every object.
- **The small sources** are read once a day, as D-49's groups.
- **Starlink's list is large**, and CelesTrak limits large lists, so it is not
  downloaded. An administrator adds a Starlink object by its catalogue number after
  one SupGP query shows an operator's orbit for it, with a public reason, as D-49.

### P6-05 Method 3.0.0: the orbit term by source and age

Accepted · 2026-11-23. Today's limit assumes that every reference orbit is 5 km off
(D-08), and accepts sets up to 7 days old. Step 5.3 found both wrong for low orbits
([D-46](#d-46-the-method-measured-on-real-data)):
- the 5 km was 97 % of a good video camera's limit;
- a clock half a second wrong passed in 33 of 35 low-orbit tracks;
- sets about 3 days old already rejected good tracks.

Method 3.0.0 gives the orbit term by the orbit's source, its age and the orbit
class, with the values step 6.1 measures. An operator's orbit gets a small term, a
GP set's term grows with its age, and a fitted orbit's comes from its covariance
(P6-07). The 7-day limit is replaced by these terms. This is a major version,
since pass/fail parameters change (releasing.md). Reports name their method, and
earlier reports keep theirs.

Even 0.2 km is about 80″ seen from 500 km, so the check is still not one of
arcseconds. It becomes able to catch clock errors of a tenth of a second in low
orbits, which is what the quality meter needs to tell an observer.

### P6-06 Orbit determination in the core

Accepted · 2026-11-23. The core fits an orbit to observations: batch least squares
of SGP4's mean elements and B*, starting from a reference orbit.
- **No new dependency.** numpy, and the sgp4 library in use (2.27, whose `Satrec`
  is initialised from elements with `sgp4init`). Orekit (Apache 2.0, Java) and
  Find_Orb (GPL, C++) do this too, but would bring a JVM or a C++ build into a
  Python core. Orekit's TLE orbit determination improved a GNSS case from about a
  kilometre to about a hundred metres.
- **Deterministic**: fixed iteration and stopping rules and rounded output, so that
  a fit can be repeated byte for byte. It has a method version of its own.
- **Its result**: an element set in OMM form with its covariance and residuals,
  named by the SHA-256 of its inputs. `orbit-watch fit-orbit` makes one.
- **Measured** on simulated networks of stations, where the true orbit is known.
  Also on SCORE's real nights from the video camera, of ACS 3 and PELICAN 3001: a
  fit of the earlier nights predicts the next night, compared with the GP set
  available then.
- **Its limit, stated**: a short arc seen from one place leaves the range poorly
  known, and a fit to one station's tracks absorbs that station's constant clock
  error into the orbit. Only another station, or an operator's orbit, shows such
  an error.

Sources: [Orekit's TLE orbit determination, SDC8](https://conference.sdo.esoc.esa.int/proceedings/sdc8/paper/10/SDC8-paper10.pdf);
[Find_Orb](https://github.com/Bill-Gray/find_orb/);
[∂SGP4, arXiv 2402.04830](https://arxiv.org/pdf/2402.04830).

### P6-07 A fitted orbit as a reference, and Space-Track's terms first

Accepted · 2026-11-23. The service may verify a delivery against an orbit fitted
from **other** accepted deliveries of the same object:
- never from the delivery under verification;
- only when the fitted orbit's uncertainty at the window is smaller than the term
  of the operator's orbit or the GP set (P6-05);
- the report names the fitted orbit and its inputs by SHA-256, and the labels say
  "fitted by Orbit Watch";
- the follower refits when new deliveries are accepted.

A fit starts from a GP or SupGP set. So **Space-Track's user agreement is read
before any fitted orbit's elements are published**
([#114](https://github.com/Haiko-Innovations/orbit-watch/issues/114)); this
follow-up moves before step 6.5. If reading it needs an account, the maintainer
reads it. Until then fitted orbits are stored and named, and their elements are not
published.

### P6-08 Identification among one launch's objects

Accepted · 2026-11-23. Objects released together are hard to tell apart for weeks,
and some are never identified
([NASA](https://www.nasa.gov/smallsat-institute/sst-soa/identification-and-tracking-systems/)).
The core compares a track with each candidate:
- **the candidates** are the objects of one launch, by international designator,
  from GP and SupGP. While they exist, these include the deployment state vectors
  that SpaceX gives for its rideshares (`Transporter-SV`, `Bandwagon-SV`);
- **the comparison** is by residuals and by the along-track time offset;
- **the result** is "identified" only when the best candidate passes and the next
  fails by a margin that step 6.6 measures. It is "ambiguous" when more than one
  fits, and "none" when none does;
- **a launch with any object off the allow-list is refused**, so that a civilian
  object is never named in place of an excluded one (D-05).

The result is evidence, not the catalogue's identification, and the report says
so. Measured on simulated deployments, where the truth is known, and on real SCORE
tracks of known objects, treated as unknown among their launch mates.

### P6-09 Identification requests in the service

Accepted · 2026-11-23.
- **The request**: format 1.2 adds an optional `identify` block naming the launch.
- **The life cycle**: reservation, delivery, challenge and settlement are as now. A
  delivery passes when its track fits at least one candidate.
- **The report**: a new minor report format adds the ranking and the result.
- **Where it shows**: the API, the CLI, and only the labels and views that such a
  request needs in the current web application.

### P6-10 Public sources only, credited

Accepted · 2026-11-23. As in phase 5 (P5-06, P5-13), all real data comes from
public sources with open terms, and nobody is asked for data. SCORE's observers
are credited by ORCID iD. The data sources page names CelesTrak's SupGP and the
operators behind it. Talking with observers and CubeSat teams is the
maintainer's own decision, outside the code.

### P6-11 Follow-ups at the end

Accepted · 2026-11-23. As P5-14: no step waits for anything outside the
repository, and follow-ups are not completion criteria. The follow-ups known now:
- telling SCORE that Orbit Watch uses its data
  ([#113](https://github.com/Haiko-Innovations/orbit-watch/issues/113));
- a real rideshare identification, once a Transporter or Bandwagon flight gives
  deployment vectors and someone has published observations of it.
  [NextSpaceflight](https://nextspaceflight.com/launches/details/7612) listed
  Transporter-19 no earlier than February 2027 on 2026-11-23.

[#114](https://github.com/Haiko-Innovations/orbit-watch/issues/114) is no longer at
the end: it comes before fitted orbits are published (P6-07).

### P6-12 Phase 6 completion criteria

Accepted · 2026-11-23. Phase 6 is done when:

1. How far GP sets are from operators' orbits is measured and published by source,
   orbit class and age, reproducible with one command; no element set is committed.
2. The service verifies a delivery against an operator's orbit when the object has
   one, against CelesTrak's GP otherwise, and against SatChecker's GP for replays.
   The report names the source. Fetching follows CelesTrak's rules, tested against
   local stand-ins.
3. Objects whose operators publish their orbits are on the allow-list by P6-04's
   rule, and GPS and GLONASS are not; the name patterns still apply; tested.
4. Method 3.0.0 gives the orbit term by source and age from the measurement; the
   examples and known answers are regenerated and their changes explained;
   earlier reports keep their versions.
5. Orbit determination in the core is deterministic, measured on simulated
   networks against the truth and on real tracks by predicting the next night,
   and reproducible with one command.
6. A fitted orbit is a reference only when it is more precise, and never from the
   delivery under verification; tested. Fitted elements are published only after
   Space-Track's user agreement is read.
7. Identification ranks a launch's candidates and says "identified" only with a
   measured margin; a launch with an excluded object is refused; tested.
8. Identification requests run through the API, the CLI and the views they need,
   labelled; tested end to end.
9. On the public service, a request verified against an operator's orbit, one
   verified against a fitted orbit, and an identification request have each
   settled on Base Sepolia. Every CI check passes; release 0.7.0.

### D-59 Operators' orbits and past sets over a period

Accepted · 2026-11-23. Step 6.1 measures how far GP sets are from operators' orbits
(P6-02). Its first part gives the core what the measurement fetches. Fetching SupGP
comes here rather than in step 6.2, which puts it into the service.

- **`orbit-watch fetch-supgp`** (`orbit_watch.supgp`) asks CelesTrak for one object's
  SupGP sets, or one source's, as P6-03 says:
  - one request, CSV with gzip, never retried;
  - not again within two hours, which CelesTrak's usage policy asks for SupGP as for GP;
  - the first answer that is not 200 stops it, with what the policy asks next.

  The CelesTrak download and the two-hour rule are shared with `fetch-gp`.
- **Each set keeps its `RMS` and `DATA_SOURCE`.** They are columns of CelesTrak's CSV and
  stay in the record as fetched; SGP4 ignores them. An answer whose sets do not name a
  `DATA_SOURCE` is refused.
- **An operator's orbit** is a set whose `DATA_SOURCE` ends in `-E`, `-RE` or `-SV`, or
  is `CPF`: fitted to an ephemeris, state vectors or laser-ranging predictions. Almanacs
  (`-A`), 11-parameter data (`-11P`) and TLEs passed on as they came (`-TLE`) are not
  (`is_operator_orbit`). P6-03 left this choice to step 6.2. It is made here, from
  CelesTrak's list of sources, because the measurement needs it. Step 6.2 may revise it
  with the numbers.
- **`orbit-watch fetch-satchecker --start T --end T`** asks SatChecker's `get-omm-data`
  for every OMM of one object in a period:
  - one request, never retried, at most 31 days;
  - each set keeps its `data_source` and `date_collected`, so the measurement can take
    only the sets that were available at a time;
  - a set that CelesTrak and Space-Track both gave appears once, with the earlier
    collection time.

  `--near` works as before.

Tested against local stand-ins (`test_supgp.py`); no test calls CelesTrak or SatChecker.
The second part measures, and publishes the numbers.

### D-60 Reference orbits measured against operators' orbits

Accepted · 2026-11-23. Step 6.1's second part measures, as P6-02 asks, how far
CelesTrak's GP sets are from operators' own orbits
([reference-orbit-accuracy.md](reference-orbit-accuracy.md)).

- **`orbit-watch measure-reference-orbits`** (`orbit_watch.reference_accuracy`):
  - With `--fetch` it fetches one run into the cache. That is one SupGP download for
    each of `AST-E`, `CPF`, `ISS-E`, `Kuiper-E`, `OneWeb-E` and `Planet-E`, and one
    SatChecker request per chosen object, two seconds apart. It does not start within
    two hours of the last run. The first answer that is not 200 stops it, and an
    incomplete run is never used.
  - Without `--fetch` it measures the newest complete run again, byte for byte, and
    writes `validation/reference-orbits/results.json` and the page's tables.
  - SupGP keeps no history, so a later run measures with the sets current then.
- **The truth** for each object is its operator-derived set with the latest epoch at or
  before the run. Several prediction centres at one epoch give the best-fitted one.
  Up to six objects are taken per source and orbit class, evenly by catalogue number.
  The ISS gives its last eight segments that had begun. Starlink is left out, since
  its list is large.
- **The GP sets** are every OMM from SatChecker of the ten days up to the truth's epoch.
  Each is compared with the truth over the six hours after that epoch, every minute,
  radially, in track and across track.
  - SatChecker kept two OneWeb sets among CelesTrak's that are the SupGP sets
    themselves: the same epoch, and no difference. A GP set at the truth's epoch closer
    than a metre is counted apart and left out.
- **No element set leaves the cache.** The results name sets by epoch and SHA-256.
- **The first run**, fetched on 2026-11-23 at 21:05 UTC, gave 44 truth sets of 43
  objects and 2,158 comparisons. All 49 answers were 200.
  - **Fresh sets**: the newest GP set a service would have had, 0.2 to 0.6 days old,
    was a median 0.17 to 0.54 km off in low orbits, except AST SpaceMobile's at 1.83 km.
  - **Ageing in low orbits**: the median grew from 0.33 km under half a day to 1.4 km
    at one to two days, 3.2 km at two to three and 29 km at seven to ten. The 90th
    percentile grew from 1.9 to 212 km. Nearly all of it is in track.
  - **By object**: passive laser-ranging satellites stayed near 0.3 to 1 km for ten
    days. Satellites that manoeuvre were tens of kilometres off within three to five
    days.
- **`orbit-watch score-coverage`** counts what files from `fetch-score` hold for an
  orbit determination. It repeats the first look of 2026-11-23, which found windows
  with two or more stations rare.

The page lists five candidates for method 3.0.0, which step 6.3 decides:
- an orbit term that grows with a GP set's age;
- terms in track and across track kept apart;
- a small term for operators' orbits, once a few runs show how SupGP sets age;
- manoeuvres as the tail that no age model catches;
- the allow-list's own objects, which these numbers bracket rather than measure.

With this, step 6.1 is done.


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

Accepted · 2026-11-11. SQLite from the Python standard library, schema changes as numbered
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


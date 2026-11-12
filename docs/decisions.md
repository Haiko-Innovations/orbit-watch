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

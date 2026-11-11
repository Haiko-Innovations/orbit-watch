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

## Proposed decisions for phase 2

These need a maintainer's approval before step 2.1 of the
[roadmap](roadmap.md#phase-2-settlement-on-a-testnet-target-version-030)
starts. Approval is given in
[#27](https://github.com/Haiko-Innovations/orbit-watch/issues/27). Facts were checked on 2026-11-11; the sources are listed under each
proposal. Versions and addresses are settings, re-checked when they are used.

### P2-01 Base Sepolia as the testnet

Proposed. Base Sepolia (chain ID 84532) over Optimism Sepolia (11155420).
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

Proposed. Deposits and rewards are in Circle's testnet USDC on Base Sepolia
(`0x036CbD53842c5426634e7929541eC2318f3dCF7e` at the time of checking; a
setting, and the decimals are read from the contract). Circle states that
testnet USDC has no financial value. Anyone can get 20 USDC per address every
two hours from Circle's public faucet, without an account. Alternative: a
worthless test token deployed by Orbit Watch, which would be easier to hand out
but would look like a token of our own, which the plan rules out.
Sources: [USDC addresses](https://developers.circle.com/stablecoins/usdc-contract-addresses),
[Circle faucet](https://faucet.circle.com/).

### P2-03 EAS attestations with two schemas

Proposed. Use EAS at its Base Sepolia predeploy (`EAS`
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

Proposed. Contracts in `contracts/` as a Foundry project; Foundry pinned to
1.8.6 (the newest release older than 14 days; Apache-2.0 and MIT) and
OpenZeppelin Contracts 5.7.0 (MIT), pinned by commit. Custom money-handling
code is kept to the escrow's own rules; transfers go through OpenZeppelin's
`SafeERC20`. CI installs Foundry with the SHA-pinned `foundry-rs/foundry-toolchain`
action (v1.9.2) inside the `tarkistus` check.
Sources: [Foundry releases](https://github.com/foundry-rs/foundry/releases),
[OpenZeppelin releases](https://github.com/OpenZeppelin/openzeppelin-contracts/releases).

### P2-05 One non-upgradeable escrow contract

Proposed. One escrow contract holds all requests, each with its own deposit,
locked split, deadlines and state. No proxy and no upgrade path: a new version
is a new contract, and existing requests settle in the old one. No function
lets anyone, administrators included, take a deposit; money leaves only by the
settlement rules. Settlement can be triggered by anyone once its conditions
hold, and it happens once. Alternative: a separate contract per request (clean
isolation, more gas and more moving parts).

### P2-06 The phase 1 rules, on chain

Proposed. The escrow implements settlement rules 1.0 exactly
([D-12](#d-12-settlement-rules-10)): observer reward and platform fee (0 by
default, recipient a setting) only when accepted, every completed review paid,
the rest refunded, nothing locked. Challenge, review and delivery deadlines are
checked against block time with the request's terms. The phase 1 scenario
suite is the acceptance test.

### P2-07 Reviewer registry behind a Safe and a timelock

Proposed. An on-chain registry of reviewer addresses, owned by an OpenZeppelin
`TimelockController` with a public minimum delay of 48 hours, whose only
proposer is a Safe multisig (2 of 3 signers). Every change is visible for two
days before it takes effect. **Open:** who the three signers are.

### P2-08 Python adapter on web3.py

Proposed. The `evm-testnet` settlement adapter is Python, using web3.py 8.0
(MIT), so the request service stays one program. It passes the settlement
scenario suite against a local Anvil chain in CI. CI never talks to a public
testnet and holds no keys. Alternative: a TypeScript service with viem, which
phase 3's web application may use anyway, at the cost of a second runtime now.
Source: [web3.py on PyPI](https://pypi.org/project/web3/).

### P2-09 Keys and wallets

Proposed. Every party has its own address and signs its own transactions:
requesters fund, reviewers attest their votes. Orbit Watch never asks for seed
phrases or private keys. The command line signs with an encrypted keystore that
the user creates (for example with Foundry's `cast wallet import`), or prints an
unsigned transaction for an external wallet. The service holds one key, the
verifier key for automated attestations, read from a secret file outside the
repository. Keys for test automation are separate, used only on testnets and
funded only from faucets.

### P2-10 The chain decides payment status

Proposed. The chain, not the database, is the primary source of payment
status. The service mirrors it and shows pending, confirmed and failed
transactions apart, each with a block explorer link
(`https://sepolia.basescan.org`). Every chain-related output says "Base Sepolia
testnet, no real value".

### P2-11 Phase 2 has no public deployment

Proposed. As in phase 1 (P-03), the service runs locally; only the contracts
and attestations are public, on the testnet. A public demo service is decided
separately.

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

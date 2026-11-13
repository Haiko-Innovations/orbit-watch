# Changelog

All notable changes to Orbit Watch are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).
Formats and methods have their own versions; see [docs/releasing.md](docs/releasing.md).

## [Unreleased]

## [0.3.0] - 2026-11-13

Phase 2: settlement on a testnet. Testnet only: nothing here touches a
mainnet or real money.

### Added

- Contracts project (phase 2, step 2.1): `contracts/` is a Foundry project
  (Solidity 0.8.38, OpenZeppelin Contracts 5.7.0 and forge-std 1.17.0 as
  submodules pinned to release commits). `OrbitWatchEscrow` holds testnet USDC
  deposits per request: `fund` locks the split (observer reward, three review
  rewards, platform fee) and the hash of the request's terms. It refuses every
  chain except Base Sepolia and a local Anvil chain. Unit, fuzz and invariant
  tests run in the `tarkistus` check together with `forge fmt` and
  `forge lint`. See `docs/escrow.md` and `contracts/README.md`.
- Settlement rules on chain (phase 2, step 2.2): the escrow follows the phase 1
  lifecycle from funding to settlement (`cancel`, `reserve`, `deliver`,
  permissionless `settle`), applies deadlines at the current block time and
  pays by settlement rules 1.0. Payouts are credited and each party withdraws
  its own (`withdraw`). The automated result, challenges and votes are internal
  until step 2.3. The phase 1 settlement scenario suite is exported to
  `contracts/test/fixtures/settlement-scenarios.json`
  (`python -m orbit_watch.settlement.scenarios`) and replayed against the
  contract; invariant tests check every settlement against the rules.
- Attestations and reviewer rounds on chain (phase 2, step 2.3): the automated
  result and reviewer votes are EAS attestations with two schemas that the
  escrow registers and resolves itself, so an attestation the rules refuse is
  never created. Challenges are transactions by the requester or the observer.
  Each round's three reviewers are chosen on chain from the new
  `OrbitWatchReviewerRegistry` by the phase 1 rule, honouring affiliations.
  Tests run against the EAS bytecode of Base Sepolia's predeploys (checked by
  hash), with interfaces from eas-contracts v1.4.0. See `docs/attestations.md`.
- Governance of the reviewer registry (phase 2, step 2.4): the registry is
  owned from its deployment by an OpenZeppelin `TimelockController` with a
  48-hour minimum delay, whose only proposer and canceller is a Safe 2-of-3
  multisig; anyone may execute a change after its delay, and the timelock has
  no administrator. `script/OrbitWatchGovernance.sol` deploys the set-up and
  refuses any other Safe. Tests run against the canonical Safe 1.4.1 bytecode.
  The privileges are listed in `contracts/README.md`. The registry's
  constructor now takes the initial reviewers.
- The `evm-testnet` settlement adapter (phase 2, step 2.5), in the new
  optional `evm` extra (web3.py 8.0). It mirrors funding, reservations,
  deliveries, results, challenges, votes, settlements and refunds to the
  escrow and EAS, each signed by the party's own account, and checks every
  settlement against `settlement_plan` payout by payout. It passes the phase 1
  settlement scenario suite on a local Anvil chain, which now runs in CI.
  `orbit_watch.chain` holds the contract client and the ABIs, which a test
  keeps equal to the Foundry build. See `docs/evm-adapter.md`.
- The service, API and command line on a testnet chain (phase 2, step 2.6).
  `orbit-watch serve --chain-rpc … --escrow … --verifier-keystore …` settles
  funded requests on the escrow. Every party registers its own wallet with a
  signature and signs its own transactions: the API answers with unsigned
  transactions (`202`), and the command line signs them with the user's
  encrypted keystore (`--keystore`, for example from `cast wallet import`) or
  prints them for another wallet (`--unsigned`). The service holds only the
  verifier key. It follows the escrow's events, which decide reviewer rounds
  and payments, and shows pending, confirmed and failed transactions with
  explorer links. Events that do not fit a request are shown as conflicts.
  New endpoints `/v1/chain`, `/v1/wallet`, `/v1/wallet/withdraw` and
  `/v1/transactions`, and new commands `chain`, `wallet` and `tx`. Storage
  migration 0003 adds the chain's tables. Tests on a local chain include the
  whole chain from the command line and a check that no key, keystore or
  password ever reaches the server. See `docs/chain-service.md`.
- The Base Sepolia deployment (phase 2, step 2.7).
  `contracts/script/DeployOrbitWatch.s.sol` deploys a Safe 1.4.1 (2 of 3), the
  48-hour timelock and the reviewer registry, and the escrow; it writes a
  deployment record and checks a deployment against its record on chain. It
  refuses other chains, Safe code that is not the canonical code and, on Base
  Sepolia, any token but Circle's testnet USDC. The contracts run on Base
  Sepolia with verified sources; the addresses, faucet instructions for
  testnet ETH and USDC, and who holds which key are in
  `docs/base-sepolia.md`. `orbit-watch serve --network base-sepolia` takes the
  escrow from the record in the package, and the command line uses Base's
  public endpoint unless `--rpc` is given. On the testnet one maintainer holds
  every key, so the Safe separates keys, not people (D-24). The script runs in
  CI against a local chain with Base Sepolia's EAS and Safe code. A smoke test
  ran one SIMULATED request on Base Sepolia from funding to withdrawal.
- The phase 2 demo (phase 2, step 2.8): `orbit-watch demo --phase 2` runs the
  five requests of the phase 1 demo against a service on a chain, every party
  signing with its own keystore from the command line: accepted, rejected
  through a reviewer round, rejected, disputed and expired, with token
  transfers, EAS attestations and checks that unauthorised parties and retries
  are refused. The run on Base Sepolia is recorded in `examples/phase2/`; CI
  runs the same demo on a local chain. The phase 2 summary is in
  `docs/phase-2-summary.md`.
- Phase 2 decisions P2-01 to P2-11 accepted; D-18 on the contract project,
  D-19 on settlement on chain, D-20 on attestations, D-21 on governance,
  D-22 on the adapter interface, D-23 on the service on a chain and D-24 on
  the Base Sepolia deployment.

### Changed

- Settlement adapter interface 2: every mutating call may carry the
  lifecycle record (`record=`), and `deliver` and `challenge` are new calls.
  The points ledger ignores the record and journals nothing for the new calls,
  so phase 1 behaves and exports exactly as before.
- `request fund` on the command line takes token amounts such as `1.5` when
  the API runs on a chain; with points it still takes whole numbers.
- The escrow's version is 1.0.0, the version deployed on Base Sepolia.
  `orbit-watch chain` and `GET /v1/chain` also show the reviewer registry, and
  reporting a transaction on its own shows the testnet notice.
- The escrow's events are read in smaller block ranges when an endpoint
  refuses a range, taking the limit the endpoint names: Base's public endpoint
  answers at most 200 blocks per query. The chain client does this for every
  reader, the service and the demo alike.
- A new service directory follows the chain from the current block, since no
  earlier event can belong to its requests, and `serve` reads the chain up to
  date before it answers. Before, a new directory on Base Sepolia read the
  escrow's events from its deployment block, about a thousand queries after
  half a day at 5 blocks a second, and its first request timed out.
  `--from-block` no longer defaults to the deployment record's block.
- Creating an admin key says "an admin key".
- `admin tick` shows the transactions the service sent on chain, and
  `request show` no longer prints "until None" for a reservation that ended
  with a delivery.

## [0.2.0] - 2026-11-11

Phase 1: requests, optimistic verification and API. Still no money and no
blockchain: points are bookkeeping, and all bundled data is simulated.

### Added

- Request lifecycle (phase 1, step 1.1): a pure state machine from draft through
  open, funded, reserved, delivered, challenge period and reviewer round to
  accepted, rejected, disputed, expired or cancelled, and finally settled.
  Terms are frozen and hashed when a request opens, and funding locks a reward
  split (observer, per-review reward, platform fee); deadlines (reservation,
  delivery, verification, challenge, review) are applied at their exact time.
  See `docs/lifecycle.md`.
- Settlement (phase 1, step 1.2): shared settlement rules 1.0, the adapter
  interface (`fund`, `reserve`, `attest`, `settle`, `refund`) with idempotency
  keys, the points-only double-entry ledger adapter, and a scenario suite that
  every adapter must pass. See `docs/settlement.md`.
- Optimistic verification (phase 1, step 1.3): a request service that runs
  automated verification on delivery, publishes and attests the result, opens
  a challenge period, starts a reviewer round on a challenge or an inconclusive
  result, and settles every outcome. Pre-approved reviewer registry with
  affiliations (format 1.0) and a deterministic, recomputable reviewer
  selection; challenges and votes carry reasons. See
  `docs/optimistic-verification.md`.
- Reviewer accuracy (phase 1, step 1.4): known-answer calibration tasks built
  by the simulator are mixed into every reviewer's queue in the same shape as
  real tasks; reviewer profiles show accuracy, approval rate and missed tasks,
  with flags for rubber-stamping. See `docs/reviewer-accuracy.md`.
- Storage (phase 1, step 1.5): `open_service` keeps a service's state in SQLite
  (numbered plain-SQL migrations checked by hash) and its files by SHA-256
  (never deleted, checked on every read). One transaction per call, a refused
  call changes nothing, one process per directory, and a SQLite points ledger
  that passes the settlement scenario suite. See `docs/storage.md`.
- HTTP API (phase 1, step 1.6): Starlette application for the whole request
  chain, with role-scoped API keys stored as hashes, an `Idempotency-Key` on
  every change (replays return the stored response), stable JSON error codes,
  and `orbit-watch serve` / `orbit-watch keys create`. Optional `api` extra
  (Starlette, uvicorn). Migration 0002. See `docs/api.md`.
- Command-line client (phase 1, step 1.7): `request`, `reserve`, `challenge`,
  `review`, `admin` and `balance` commands, and `submit` now sends a delivery
  (manifest hash checked, sent as `Content-SHA256`). Standard library only;
  address and key from `--api`/`--key` or `ORBIT_WATCH_API`/`ORBIT_WATCH_KEY`;
  printed idempotency keys make retries safe.
- Data publication (phase 1, step 1.8): a request's request document,
  observations and report become public under CC BY 4.0 once it is settled and
  its embargo (0–30 days) has passed; until then only its parties and admins can
  read them; calibration files are never public. Public endpoints without a key
  (`/v1/public/…`) with permanent, content-addressed file URLs and a licence
  link header; `orbit-watch public list|get --download`. See
  `docs/data-publication.md`.
- Phase 1 demo: `orbit-watch demo --phase 1` runs five simulated requests
  through every outcome; the output is committed in `examples/phase1/` and
  checked byte for byte in CI. Phase 1 summary in `docs/phase-1-summary.md`.

## [0.1.0] - 2026-11-11

Phase 0: the open core. No money, no blockchain, no servers. All bundled data
is simulated and labelled as such.

### Added

- Orbit Watch JSON observation set format 1.0 with a JSON Schema, and request,
  delivery, target policy, station profile and sites formats 1.0.
- IOD reader and writer: angle formats 1–7, equinox codes 0 and 5, Alpha-5
  catalogue numbers, lenient handling of real-world files.
- CCSDS TDM (503.0-B-2) subset reader and writer for optical angle data.
- Station simulator with SGP4 (through Skyfield): angle and timing noise,
  station clock offset, missing observations; four simulated station profiles
  and a simulated catalogue of four objects.
- Verification method `orbit-watch-automated-verification` 1.0.0 with ten
  checks, including orbit residuals against the public reference orbit, and
  verification report format 1.0. Reports are byte-identical for identical
  input.
- Six simulated test datasets (acceptable, invalid, late, duplicate, wrong
  target, too imprecise) with committed reports in `examples/simulated/`.
- Station quality meter 1.0.0: angle and timing precision, clock offsets shared
  by several objects, development night by night.
- `fetch-gp` for public GP data from CelesTrak, following its usage policy.
- `allowlist build` for a civilian target allow-list.
- Command-line interface: `convert`, `simulate`, `validate`, `demo`,
  `score-station`, `fetch-gp`, `allowlist build`, and `submit` (a placeholder
  until the phase 1 API).
- CI check `tarkistus`: lint, tests on Python 3.12 and 3.15, plain pip install,
  byte-for-byte determinism of the demo output, gitleaks and pip-audit.
- Apache 2.0 licence, Contributor Covenant 3.0, contributing guide and README in
  English and Finnish, issue templates, roadmap, decision log and release process.

[unreleased]: https://github.com/Haiko-Innovations/orbit-watch/compare/v0.3.0...HEAD
[0.3.0]: https://github.com/Haiko-Innovations/orbit-watch/compare/v0.2.0...v0.3.0
[0.2.0]: https://github.com/Haiko-Innovations/orbit-watch/compare/v0.1.0...v0.2.0
[0.1.0]: https://github.com/Haiko-Innovations/orbit-watch/releases/tag/v0.1.0

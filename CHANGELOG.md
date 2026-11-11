# Changelog

All notable changes to Orbit Watch are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).
Formats and methods have their own versions; see [docs/releasing.md](docs/releasing.md).

## [Unreleased]

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

[unreleased]: https://github.com/Haiko-Innovations/orbit-watch/compare/v0.1.0...HEAD
[0.1.0]: https://github.com/Haiko-Innovations/orbit-watch/releases/tag/v0.1.0

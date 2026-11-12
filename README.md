# Orbit Watch (working name)

**English** · [Suomi](README.fi.md)

**An open protocol and reference implementation for requesting, delivering,
independently verifying and settling satellite observations.**

After a launch, dozens of small satellites are deployed at once, and CubeSat
teams often do not know which public orbit record is theirs. Orbit Watch lets a
team post a request ("identify and track object X in window Y"). Amateur
stations observe, and the delivery is verified automatically and reproducibly
against public orbit data. Observers get value from day one: a quality meter
that tells them how accurate their station is.

> **Status: phase 1 is done (version 0.2.0).** Requests, optimistic
> verification, a points ledger, an HTTP API and a command-line client all run
> locally, with **no money and no blockchain**. Requests target civilian objects
> only. **Simulated data is always labelled as simulated**, and automated
> verification is a prototype, not production-ready scientific validation.
> Phase 2, settlement on the Base Sepolia **testnet**, is under way: the escrow
> contract in [`contracts/`](contracts) follows the phase 1 settlement rules and
> refuses every chain but the testnet and a local one. See the [roadmap](docs/roadmap.md), the
> [phase 1 summary](docs/phase-1-summary.md) and the [changelog](CHANGELOG.md).

## Try it (three commands)

You need Python 3.12 or newer.

```sh
pip install "orbit-watch @ git+https://github.com/Haiko-Innovations/orbit-watch.git@v0.2.0#subdirectory=core"
orbit-watch demo
cat orbit-watch-demo/datasets/wrong_target/report.txt
```

`orbit-watch demo` simulates six deliveries for one request and verifies each:

| Dataset | What it is | Verdict |
|---|---|---|
| `acceptable` | a good CMOS station with GPS timing | pass |
| `invalid` | a broken file | fail: format |
| `late` | observed after the requested window | fail: time window, minimum observations |
| `duplicate` | the same observations delivered again | fail: duplicates |
| `wrong_target` | the neighbouring CubeSat, labelled as the requested one | fail: orbit residuals |
| `too_imprecise` | a visual observer with binoculars | fail: declared uncertainty |

Every report states the method and its version, the SHA-256 of every input and
the reason for every check. The same input gives a byte-identical report, on
any machine: CI checks this on two Python versions.

### The whole request chain (phase 1)

```sh
orbit-watch demo --phase 1
cat orbit-watch-demo-phase1/transcript.md
```

Five simulated requests on a simulated clock: accepted, rejected after a
challenge, rejected without one, disputed, and expired. The transcript shows
every step, the points and the reviewer profiles. To run the chain yourself
through the HTTP API (`pip install "orbit-watch[api] @ …"`, then
`orbit-watch serve`), see [docs/api.md](docs/api.md).

## Check your own station

```sh
orbit-watch fetch-gp --group cubesat -o cubesat.json     # public orbits from CelesTrak
orbit-watch score-station my-night.iod --sites my-site.json --catalog cubesat.json
```

The quality meter shows your angle and timing precision, finds clock errors
that several objects share, and shows how your station develops night by
night. See [docs/quality-meter.md](docs/quality-meter.md) and
[examples/real-iod/](examples/real-iod).

## What is in it

| Part | Command | Docs |
|---|---|---|
| Observation format (JSON Schema), IOD and CCSDS TDM converters | `convert` | [observation-format.md](docs/observation-format.md) |
| Station simulator (SGP4, noise, timing errors, dropouts) | `simulate` | [simulator.md](docs/simulator.md) |
| Deterministic, versioned verification engine | `validate` | [verification.md](docs/verification.md) |
| Station quality meter | `score-station` | [quality-meter.md](docs/quality-meter.md) |
| Public orbit data and the civilian allow-list | `fetch-gp`, `allowlist build` | [data-sources.md](docs/data-sources.md) |
| Request lifecycle, optimistic verification, reviewer rounds | | [lifecycle.md](docs/lifecycle.md), [optimistic-verification.md](docs/optimistic-verification.md) |
| Settlement rules and the points ledger | | [settlement.md](docs/settlement.md) |
| Reviewer accuracy with known-answer tasks | | [reviewer-accuracy.md](docs/reviewer-accuracy.md) |
| Storage (SQLite, files by hash) | | [storage.md](docs/storage.md) |
| HTTP API and command-line client | `serve`, `request`, `reserve`, `submit`, `challenge`, `review`, `admin` | [api.md](docs/api.md) |
| Open data (CC BY 4.0, embargo, permanent URLs) | `public` | [data-publication.md](docs/data-publication.md) |
| Escrow contract and EAS attestations for the Base Sepolia **testnet** (phase 2, in progress) | `forge test` | [escrow.md](docs/escrow.md), [attestations.md](docs/attestations.md) |

The Python code is in [`core/`](core) and the Solidity contracts in [`contracts/`](contracts). Simulated examples are in
[`examples/`](examples).

### What is simulated

- All stations, observations and test datasets in this repository, and the four
  objects in the built-in catalogue (numbers 339001–339009, marked
  `(SIMULATED)`).
- Simulated files say so themselves (`"simulated": true`, or a marker line in
  IOD and TDM), and a simulated delivery can never satisfy a real request.
- Real orbit data is never committed; `fetch-gp` downloads it when you need it.

### Allow-list: civilian objects only

Requests may only target objects on an allow-list. Build one from civilian
groups of the public catalogue, minus the military group:

```sh
orbit-watch fetch-gp --group cubesat -o cubesat.json
orbit-watch fetch-gp --group military -o military.json
orbit-watch allowlist build --include cubesat.json --exclude military.json -o allowlist.json
```

The builder also drops names that match conservative military and intelligence
patterns. Classified objects have no public orbit, so they can never be on the
list.

## Contribute

Amateur observers, astronomers and developers are all welcome. Issues
labelled [good first issue](https://github.com/Haiko-Innovations/orbit-watch/labels/good%20first%20issue)
are small and self-contained: a new verification check, a new observation
format or a new simulated station profile. Start with
[CONTRIBUTING.md](CONTRIBUTING.md) and follow the
[Code of Conduct](CODE_OF_CONDUCT.md).

## Roadmap

Current status and the next steps: [docs/roadmap.md](docs/roadmap.md).
Decisions and their reasons: [docs/decisions.md](docs/decisions.md).
The full starting plan: [docs/plan.md](docs/plan.md).

- **Phase 0 (done, 0.1.0):** open core: format, simulator, verification, quality meter, CLI.
- **Phase 1 (done, 0.2.0):** requests with a state machine, optimistic
  verification with a challenge period and a 2-of-3 reviewer round, an API, and
  a points-only "ledger" settlement adapter.
- **Phase 2 (in progress):** settlement on an EVM L2 **testnet** with EAS attestations.
  No mainnet, no token of our own.
- **Phase 3:** a web application with role views.

## Open questions

- **Name:** "Orbit Watch" is a working name; trademark and domain checks have
  not been done (close ones: "Orbital Watch" and DARPA OrbitOutlook).
- **A real IOD example:** recent public IOD posts are almost all of classified
  objects; we would like to ask an observer for a civilian example with
  permission to publish it (see [examples/real-iod/](examples/real-iod)).
- **Bonds** for reservations and reviewers against rubber-stamping and collusion.
- **Full dispute resolution.**
- **Collaboration:** IAU CPS (SatChecker and SCORE), Unistellar and SETI,
  SatNOGS and the SeeSat-L amateur community.
- **Regulation**, if real money is ever involved (MiCA, payment services). The
  contract will never hold funds on anyone's behalf.

## Licence

Code: [Apache License 2.0](LICENSE). Observation data published through Orbit
Watch defaults to CC BY 4.0. Orbit Watch is maintained by
[Haiko Innovations](https://haikoinnovations.com) and its contributors.

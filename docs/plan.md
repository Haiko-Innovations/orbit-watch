# Orbit Watch – Starting Plan

**English** · [Suomi](plan.fi.md)

> English is the primary language of this project. If the English and Finnish versions differ, the English version applies.

I want to build an open source project with the working name **Orbit Watch**: an open protocol and reference implementation for requesting, delivering, independently verifying and settling satellite observations.

Make sensible technical assumptions on your own and state them. Check the current official documentation (libraries, testnets, contract addresses) before using any of them. Do not write addresses or versions from memory.

## 1. Goal and background

The project is purely open source. The goal is to build a community of amateur observers, astronomers and developers, not a business. The repository is published in the Haiko Innovations GitHub organisation, and the project has its own clear identity. The code is licensed under **Apache 2.0**, and data defaults to **CC-BY 4.0**.

**The heart of the project is verification, not payment.** The chain is:

Request → (optional funding) → observation delivery → automated verification → challenge period → acceptance or rejection → (optional) rewards or refund.

Existing projects cover only parts of this chain:
- SatNOGS: an open radio network;
- IAU CPS SCORE: brightness observations;
- SkyMapper: a closed commercial DePIN;
- TruSat: stayed a prototype.

There is no open, vendor-neutral protocol for the whole chain. The lesson from TruSat is that a community does not grow around a registry alone. Participants must get value right away.

**The first target user is a CubeSat team.** After a launch, dozens of small satellites are deployed at once, and the teams do not know which public orbit record is theirs. A team posts a request ("identify and track object X in window Y"), amateur stations observe, and the result is verified. Other customer groups (operators, SSA companies, authorities) have not been validated and are not pursued at this stage.

The project does not control satellites and does not produce operational safety recommendations.

## 2. Key constraints

- **Targets:** civilian objects from a public GP catalogue (e.g. CelesTrak) only. The system rejects a request whose target is not on the allow-list. The list is configurable, and by default it excludes military, intelligence and classified objects.
- **The core works without a blockchain and without money.** Payment is a replaceable settlement adapter (section 6).
- **The first on-chain adapter runs on a testnet only.** Mainnet is not used. Payments use a worthless test token or testnet USDC. Either is fine, but the token address is a setting, not hard-coded.
- **No own investment or governance token**, exchange listing, liquidity pool or price mechanism.
- **Observation data and the simulator are clearly marked as simulations.** Verification is not presented as production-ready scientific validation.
- **Everything runs locally** without a real telescope and without paid services.

## 3. Phases

Each phase can be released and reviewed on its own. **Start with phase 0, and stop at its completion criteria before phase 1.**

### Phase 0: open core (Python)

This is the community core, and it contains no crypto.

1. **Observation format:**
   - a lightweight JSON schema of our own (versioned, JSON Schema);
   - converters from the amateur **IOD** format and a limited subset of **CCSDS TDM**;
   - format documentation and example files.
2. **Observation station simulator:**
   - produces positional observations (time, RA/Dec or az/el, uncertainty) from public orbit data with SGP4;
   - adds configurable noise, timing error and missing observations;
   - produces test datasets: acceptable, invalid, late, duplicate, wrong target and too imprecise.
3. **Verification engine (deterministic, versioned):**
   - required fields and format;
   - target matches the request;
   - time window and minimum number of observations;
   - declared uncertainty;
   - hash match;
   - duplicate or resubmission detection;
   - **orbit residuals against the public reference orbit**: residual statistics and thresholds.
   - The report states the method name and version, the input hashes, and the result of every check with its reasoning. Anyone can run the same verification and get the same result.
4. **Station quality meter (immediate value for participants):** an observer runs their own observations (IOD or JSON) through the meter. It shows how accurate the observations are against the public orbit, where systematic errors appear (for example clock offset), and how accuracy develops over time.
5. **CLI:** `simulate`, `validate`, `score-station`, `convert` and `submit` (sends to the API once the API exists).
6. **Tests and CI:**
   - pytest;
   - every test dataset produces the expected result;
   - determinism test: the same input produces a byte-identical report.

**Phase 0 completion criteria:**
- `pip install` and one command produce a simulated dataset and a verification report.
- All six test datasets get the correct result and an understandable explanation.
- The quality meter works with simulated data and with one real public IOD example.
- The README explains in three minutes what the project is, how to try it and how to contribute. CONTRIBUTING, a code of conduct, issue templates and tasks labelled "good first issue" are included, for example a new check, a new format or a new station profile.

### Phase 1: requests, optimistic verification and API (Python or TypeScript, lightweight database)

1. **Request state machine** (unambiguous, tested):
   draft → open → (funded) → reserved → delivered → automatically verified → **challenge period** → accepted / rejected / disputed → settled.
   Plus expired: reservation lapses, no delivery, or verification stuck.
2. **Optimistic verification:**
   - the automated verification result is published, followed by a challenge period (for example 24 h, fixed in the terms);
   - if nobody challenges, the result is final;
   - a challenge starts a reviewer round: three pre-approved reviewers, a 2-of-3 threshold, and no party may review its own delivery (in the prototype, enforced at key level through the allow-list);
   - reviewers are paid for a completed review regardless of the outcome.
3. **Reviewer accuracy measurement:** the system mixes in test datasets with a known correct result. Each reviewer's accuracy is shown on their profile. This discourages rubber-stamping.
4. **Dispute rule:** if no 2-of-3 result is reached by the deadline, reviewers are paid for completed reviews, the observer receives no reward, and the rest is refunded to the requester. A dispute never releases the observer's reward automatically and never locks funds forever.
5. **Reservation abuse:** reservations time out. A bond is a later-phase topic and is recorded as an open question.
6. **API and storage:**
   - requests, reservations, deliveries (file and hash), reports and challenges;
   - each station has its own API key that allows delivery only, never fund transfers;
   - all mutating calls are idempotent: the same delivery, approval or settlement request never has two effects.
7. **Settlement adapter interface and the default "ledger" adapter:** no money, only reputation and points bookkeeping that follows exactly the same rules as monetary settlement. The whole chain therefore works and can be tested without a blockchain.
8. **Data:** deliveries and reports are published under CC-BY by default. The requester may choose a short embargo in the terms (for example at most 30 days). Files are retained and given a permanent download URL. A hash does not replace retention.

**Phase 1 completion criteria:**
- The whole chain works with the ledger adapter from the CLI and the API: request, reservation, simulated delivery, automated verification, challenge period and outcome.
- Rejection, reservation expiry, challenge and reviewer round, dispute, and reviewer accuracy measurement with known-answer datasets are tested.
- Double delivery and double settlement have no double effect, and this is tested.

### Phase 2: monetary settlement on a testnet (EVM L2 + EAS)

**Chain choice: an EVM-compatible L2 testnet**, preferably Base Sepolia or Optimism Sepolia. Choose the one where EAS and test USDC are available according to current documentation.

**Rationale:**
- **Reviewer approvals** are stored as standard **Ethereum Attestation Service (EAS)** attestations. Anyone can read and reuse them without Orbit Watch code.
- **Escrow, multisig and timelock logic** is built from **OpenZeppelin's** audited components. Custom money-handling code is kept to a minimum.
- **Solidity and TypeScript have the largest developer pool**, which matters for a community project.
- **Costs are fractions of a cent to a few cents**, and USDC is natively available.

A Solana adapter remains possible later, because settlement sits behind an interface.

1. **Escrow contract:**
   - request ID and hash of the terms;
   - addresses of the parties;
   - deposit from the requester's pre-funded budget;
   - reward split locked at funding time: observer, reviewers, challenge-round reserve and platform fee (default 0 for an open source project, but the mechanism exists);
   - deadlines and refund rules.
2. **Approval and settlement:**
   - the automated verification result and reviewer votes are stored as EAS attestations;
   - the contract releases funds after the challenge period or on 2-of-3 approvals, strictly by the rules;
   - settlement is idempotent, and the same request cannot be settled twice.
3. **No hidden privileges:**
   - contracts are **not upgradeable** (no proxy pattern). A new version is a new contract, and existing requests settle in the old one;
   - administrators cannot withdraw customer deposits;
   - the reviewer list is managed through a multisig with a public timelock, and these privileges are documented in the README.
4. **Wallets and keys:**
   - each party has its own address;
   - users sign with their own wallets;
   - seed phrases or private keys are never requested and never stored in source code;
   - test automation keys are kept separate;
   - server secrets never reach the browser;
   - a testnet label is visible everywhere;
   - safe instructions for getting test funds: the testnet faucet and test token distribution.
5. **Transactions:** pending, confirmed and failed are shown separately. The chain, not the database, is the primary source of payment status. Every transaction has an explorer link.
6. **Tests:**
   - contract tests (Foundry or Hardhat) for fund flows, permissions, state transitions, timeouts and retries;
   - a fuzz test that no funds are created or lost: deposit = rewards + refunds.

**Phase 2 completion criteria:**
1. The system starts with the documented instructions.
2. Different parties act with different wallets.
3. A request can be created and funded.
4. An observer can reserve a request and deliver a simulated dataset with the CLI.
5. Automated verification, the challenge period and, through a challenge, the reviewer round work, and the results appear as EAS attestations.
6. Rewards of an accepted request move as real testnet token transfers.
7. Rejection, deadline expiry, dispute and refund work.
8. Explorer links are shown.
9. An unauthorised party cannot approve work or withdraw a deposit, and this is tested.
10. A retry never pays twice, and this is tested.

### Phase 3: web application (later)

One web application with separate role views:

- **Requester:** connects a wallet, sees balances, creates a request (target, time window, deadline, delivery requirements), sees the split of rewards and fees before funding, funds the request, follows delivery and verification, downloads the data and report, and sees payment transactions and refunds.
- **Observer:** connects a wallet, registers a (simulated) station, browses open requests, reserves a request, submits data, sees the reasons for acceptance or rejection, and follows their rewards.
- **Reviewer:** connects a wallet, sees challenges assigned to them, runs the checks, reviews the report, signs an approval or rejection with reasons, and sees their rewards and accuracy.
- **Administrator:** manages reviewers (multisig and timelock), sees the status of requests, deliveries and payments, errors and the event log, and starts simulators and demo datasets.

Also a station quality meter view and a public attestation browser. Administrators have no hidden privileges. A testnet label is visible everywhere.

## 4. What goes on-chain and what stays off-chain

**On-chain (phase 2):**
- request ID and hash of the terms;
- addresses of the parties;
- deposit;
- delivery hash;
- automated verification and reviewer attestations (EAS);
- final split and refunds.

**Off-chain:**
- observation files and their retention;
- reports;
- verification computation;
- search and request matching;
- user interface.

The contract checks authorised signatures and payment rules. It cannot see space and does not prove that measurements are physically correct.

## 5. Technical overview

- **One repository**, a monorepo:
  - `core/`: Python (format, simulator, verification, quality meter, CLI);
  - `api/`;
  - `contracts/`: Solidity, Foundry recommended;
  - `web/`: phase 3.
- **Languages:** Python in the core, because the astronomy community uses it (skyfield, sgp4, astropy). TypeScript and Solidity for the chain and the web.
- **Lightweight database**, for example SQLite in development, and file storage locally or S3-compatible.
- **CI** runs the core, API and contract tests. Also gitleaks, Dependabot and SHA-pinned actions (Haiko Innovations repository practice).

## 6. Settlement adapter interface

One interface through which the state machine applies monetary or points-based effects: `fund`, `reserve`, `attest`, `settle` and `refund`. Implementations:
1. `ledger` (default, phase 1): no money, reputation and points, same rules;
2. `evm-testnet` (phase 2): escrow contract and EAS;
3. later possibly `solana-devnet` or another.

The rules (split, timeouts, dispute rule) must be identical in every adapter. Run the same scenario suite against every adapter.

## 7. Open questions, recorded in the README

- Name: "Orbit Watch" is a working name. Trademark and domain checks have not been done (close ones: "Orbital Watch" and DARPA OrbitOutlook).
- Reservation bond and reviewer bond, i.e. incentives against rubber-stamping and collusion.
- Full dispute resolution.
- Collaboration: IAU CPS (SatChecker and SCORE), Unistellar and SETI, SatNOGS and the SeeSat-L amateur community.
- Regulation, if real money is ever involved (MiCA, payment services). The structure where the contract never holds funds on anyone's behalf is kept.

## 8. Deliverables

A short summary at the end of every phase:
- what actually works (and on which network);
- what is simulated;
- how to run the demo;
- what the next open problems are.

**Start with phase 0, and do not stop at a plan.** Stop at the phase 0 completion criteria and report before phase 1.

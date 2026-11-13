# Phase 3 summary

**English** · [Suomi](phase-3-summary.fi.md)

Phase 3, the web application, is complete as **version 0.4.0**. This is the
end-of-phase summary that the [plan](plan.md#8-deliverables) asks for.

> **Testnet only, no real value.** The web application runs locally
> ([P3-10](decisions.md#p3-10-no-public-deployment-in-phase-3)). On chain,
> everything runs on Base Sepolia with Circle's testnet USDC, which has no
> value. All stations, observations, requests and reviewers are SIMULATED.

## What works

- **One web application** ([web.md](web.md)): a TypeScript and React
  single-page app that the service serves on its own origin, under a strict
  content security policy. It uses only the documented API.
- **Each party signs in with its own wallet**, with Sign-In with Ethereum. The
  wallet is found through EIP-6963. The session is an `HttpOnly` cookie, and
  no key reaches the page or the service.
- **Transactions in the browser.** Before the wallet sees a transaction, the
  page reads its call data and says what it does: amounts, the file's SHA-256,
  the vote, the reasons. It refuses anything else. Transactions show as
  pending, confirmed or failed, with block explorer links.
- **The views:**
  - **the requester's**: create, publish, fund, follow, challenge, and
    download the data and the report;
  - **the observer's**: a SIMULATED station profile, reserving, delivering its
    own file or simulated observations, and why a delivery passed or failed;
  - **the reviewer's**: tasks, votes with reasons as its own EAS attestations,
    rewards and accuracy;
  - **the administrator's**: every request, payment, error and event, `tick`,
    the reviewer registry with the timelock's operations, data for the Safe,
    and the simulator.
- **Public pages without signing in**: the network, open requests, the
  attestation browser with EAS Scan links, and the station quality meter.
- **A local stack in one command** for development and tests. It runs a
  local chain with the contracts, a Safe, a timelock, the service and
  SIMULATED parties.
- **The phase 3 demo**: the whole chain in the browser on Base Sepolia, every
  role with its own wallet
  ([`examples/phase3/transcript.md`](../examples/phase3/transcript.md)).

### Completion criteria

From [P3-11](decisions.md#p3-11-phase-3-completion-criteria):

| Criterion | Status |
|---|---|
| 1. The web application starts with the documented instructions, on a local chain and on Base Sepolia | ✅ [web.md](web.md#run-it): the local stack in CI and in development; the demo's service on Base Sepolia started from the same instructions |
| 2. Each role signs in with its own wallet; no private key, seed phrase or server secret reaches the browser or the service, tested | ✅ every role's end-to-end test signs in with its own wallet. Tests check that the session cookie cannot be read by scripts and that the page keeps nothing secret. The demo's keys stay in the test runner (D-33) |
| 3. A requester creates, funds and follows a request, downloads its data and report, and sees payments and refunds in the browser | ✅ `requester.spec.ts`; the demo on Base Sepolia |
| 4. An observer registers a simulated station, reserves a request, delivers and follows rewards in the browser | ✅ `observer.spec.ts` and `transactions.spec.ts`; the demo |
| 5. A reviewer sees assigned tasks, signs votes with reasons as EAS attestations, and sees rewards and accuracy in the browser | ✅ `reviewer.spec.ts`; the demo's votes on EAS Scan |
| 6. An administrator sees requests, deliveries, payments, errors and the event log, prepares reviewer changes for the Safe and the timelock, and starts the simulator, with no privilege the API does not give, tested | ✅ `admin.spec.ts`, with a non-administrator's session refused; the demo's Safe schedules the prepared change on Base Sepolia |
| 7. Pending, confirmed and failed transactions are shown apart, with explorer links | ✅ `transactions.spec.ts` (a refused second withdrawal); BaseScan links in the demo |
| 8. The station quality meter and the public attestation browser work without signing in | ✅ `public.spec.ts`; the demo |
| 9. The testnet label is visible on every page, and simulated data is labelled | ✅ `public.spec.ts` and every role's test |
| 10. End-to-end tests of every role and accessibility checks of every view run in CI against a local chain | ✅ CI's `tarkistus` runs every end-to-end test and the review of all 17 views ([accessibility.md](accessibility.md)) |

## What is simulated, and what is a testnet

- All stations, observations, requests and reviewers. Every simulated
  document says so itself, and the pages label it.
- The money is Circle's testnet USDC on Base Sepolia, of no value.
- **One maintainer holds every key on the testnet**: the Safe's signers, the
  verifier and the simulated parties
  ([D-24](decisions.md#d-24-the-base-sepolia-deployment)).
- **In the demo, a test wallet signs for each role.** It holds the role's
  testnet key and is announced to the page like a real wallet. Wallet
  extensions such as MetaMask use the same EIP-6963 path, but no run with
  one is recorded.
- **The Safe app was not used.** The Safe's owners signed the prepared batch
  file's transaction with their keys outside it
  ([D-33](decisions.md#d-33-the-phase-3-demo-and-the-accessibility-review)).
- **The service runs locally.** Only the contracts and the attestations are
  public.

## How to run it

On a local chain, without any key of value, with Node 26, uv and Foundry
1.8.6 ([web.md](web.md#run-it)):

```sh
git clone --recurse-submodules --branch v0.4.0 https://github.com/Haiko-Innovations/orbit-watch.git
cd orbit-watch
cd contracts && forge build && cd ../web && npm ci && npm run build
cd ../core && uv run python tests/local_stack.py --web ../web/dist
```

Then open <http://127.0.0.1:8787/> and sign in with a wallet on the local
chain (port 8545). Its parties' test keys are in `local-stack.json`.

The demo on Base Sepolia needs the maintainer's testnet keystores
([web.md](web.md#the-phase-3-demo)).

## Open problems for the next phase

- **A public deployment** (P3-10): TLS, rate limits, key rotation,
  operations and a privacy notice. The service also needs a background worker,
  because today it settles when someone reports a transaction or calls
  `tick`.
- **Accessibility with people**: screen readers, other browsers, and tests
  with users ([accessibility.md](accessibility.md#not-covered)).
- **Separate people for the keys**: the Safe's three signers, and the
  verifier key away from the maintainer's machine.
- **Calibration on chain**: a reviewer can tell a calibration task from a
  real one after answering, because only a real vote is a public attestation
  (D-23, D-31).
- **The timelock's history**: the administrator view shows only the
  operations scheduled after the service started following the chain (D-32).
- **Bonds** for reservations, challenges and reviewers, and **personal data**:
  station coordinates in public data.
- **A real IOD example** of a civilian object, shared with permission
  ([#8](https://github.com/Haiko-Innovations/orbit-watch/issues/8)).

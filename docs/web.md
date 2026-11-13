# The web application

Phase 3, steps 3.1 to 3.6. Code: [`web/`](../web). Decisions:
[P3-01 to P3-11](decisions.md#phase-3-decisions),
[D-25](decisions.md#d-25-the-web-project),
[D-26](decisions.md#d-26-open-requests-are-public),
[D-27](decisions.md#d-27-signing-in-with-a-wallet),
[D-28](decisions.md#d-28-transactions-in-the-browser),
[D-29](decisions.md#d-29-the-requesters-view),
[D-30](decisions.md#d-30-the-observers-view) and
[D-31](decisions.md#d-31-the-reviewers-view).

> **Testnet only, no real value.** The web application runs locally
> ([P3-10](decisions.md#p3-10-no-public-deployment-in-phase-3)). Every page
> says which chain it is on and that all data is SIMULATED.

One single-page application in TypeScript and React, built with Vite. The
Python service serves its build on the API's own origin, so the browser talks
to one server, and the app uses the documented [API](api.md) and nothing else.

What it has so far:

| Page | Address | Shows |
|---|---|---|
| Network | `#/` | the service's version, the chain, the escrow, registry, token, EAS schemas, verifier and explorer, with explorer links on Base Sepolia |
| Open requests | `#/requests` | requests that invite observers: target, window, deadline, rewards and requirements ([`GET /v1/public/open-requests`](api.md)) |
| Sign in | `#/sign-in` | the wallets in this browser; signing in, or signing up as a requester or a station |
| Your account | `#/account` | the signed-in party, its role and wallet, when the session ends; signing out; the wallet's balance and the credit waiting in the escrow, with a withdrawal; the party's transactions with their status |

| Your requests | `#/my-requests` | a requester's requests |
| New request | `#/new-request` | a form for a draft request: target from the allow-list, window, deadline, requirements, time limits |
| A request | `#/requests/<id>` | its status and progress, terms, files, payments and chain events; for its requester: publish, fund (the deposit and its split first), cancel, challenge a passed result |

| Your station | `#/station` | a station's profile: a SIMULATED instrument with the station's own name and place; only the station sees it |
| Your observations | `#/my-observations` | the requests a station reserved or delivered |

On Open requests a signed-in station reserves a funded request. On the
request's page the station that reserved it delivers: it chooses a file, or
has the service simulate SIMULATED observations with its profile; the page
computes the file's SHA-256, and the transaction flow checks that the chain
records exactly that. The request's parties see why the automated
verification passed or failed, check by check; an observer may challenge a
failed result.

| Your review tasks | `#/tasks` | a reviewer's open tasks, real and calibration alike, and its record: calibration accuracy, votes, notes |
| A task | `#/tasks/<id>` | the request, the challenge's reason, the files, the automated verification check by check, and the answer: approve or reject with reasons. A vote in a real round is the reviewer's EAS attestation, signed in its wallet; the page checks the answer, the reasons' SHA-256 and the delivery in the call data first |

The administrator view follows in step 3.7
([roadmap](roadmap.md#phase-3-web-application-target-version-040)).

## Signing in

The page lists the wallets that announce themselves (EIP-6963; an older
wallet at `window.ethereum` if none does). Choosing one:

1. connects and asks the wallet to use the service's chain, adding it if the
   wallet lacks it;
2. asks the service for a sign-in message, and checks that it names this page
   and this account before the wallet shows it;
3. asks the wallet to sign. Signing sends no transaction and costs nothing;
4. hands the signature to the service, which sets a session cookie that
   scripts cannot read.

A wallet that is no party's yet signs up instead, as a requester or a station
with a name of its choosing. Reviewers and administrators are added by the
maintainers and sign in with a wallet registered from the command line
(`orbit-watch wallet register`). The details and the checks are in the
[API](api.md#signing-in-with-a-wallet) and
[D-27](decisions.md#d-27-signing-in-with-a-wallet).

## Transactions

Everything that moves money or records a vote is a transaction that the
party's own wallet signs ([D-28](decisions.md#d-28-transactions-in-the-browser)).
The service prepares it; the page then:

1. reads what the transaction does from its call data with the contracts'
   ABIs, shows it in words ("Withdraw your credit", "Deposit 1.3 TESTUSD for
   SIM-REQ-3001"), and refuses anything that is not a call this party makes to
   Orbit Watch's own contracts on the service's chain;
2. asks the wallet to send it, which shows the network fee;
3. reports the hash to the service, which waits for the chain, and shows the
   transaction as pending, confirmed or failed, with an explorer link on Base
   Sepolia.

A declined prompt, a wallet on another network, a wallet with another account
and a transaction the chain refuses are each explained, and nothing is sent.
Withdrawals come first (Your account); requests, deliveries and votes follow
in steps 3.4 to 3.6.

**With a real wallet on the local stack**: the local chain listens on
`http://127.0.0.1:8545` (chain 31337), where wallets and viem expect it; the
page asks the wallet to add it. `local-stack.json` lists every SIMULATED
party's test key, which you can import into a wallet used only for testing.
Never send real funds to these public keys. The stack seeds SIM-REQ-3000, a
request that ran its course: station:SIM-ESPOO can withdraw 1 TESTUSD and the
requester 0.3 TESTUSD.

## Run it

You need Node 26 (the version in `web/.nvmrc`) and npm 11, and for the local
stack Foundry 1.8.6 and uv ([contracts/README.md](../contracts/README.md)).

```sh
cd contracts && forge build                 # the contracts, for the local chain
cd ../web && npm ci && npm run build        # the app, in web/dist
cd ../core && uv run python tests/local_stack.py --web ../web/dist
```

Then open <http://127.0.0.1:8787/>. The local stack is a LOCAL Anvil chain
with Base Sepolia's EAS code and fresh Orbit Watch contracts, the service on
it, SIMULATED parties (a requester, four stations, the reviewers) with
registered wallets, and three SIMULATED requests, two of them funded. Its
clock starts at 2026-11-01 12:00 UTC. It writes `local-stack.json` with every
party's API key, address and keystore; the keys are public test keys that
anyone can recompute from the parties' names, so never use them anywhere but
a local chain. Stop it with Ctrl+C.

Against a service on Base Sepolia instead:

```sh
orbit-watch serve --dir ./ow-base-sepolia --network base-sepolia \
  --verifier-keystore … --web web/dist
```

## Develop

```sh
cd core && uv run python tests/local_stack.py   # the API on port 8787, the chain on 8545
cd web && npm run dev                            # http://127.0.0.1:5173/, /v1 forwarded to 8787
```

| Command (in `web/`) | Does |
|---|---|
| `npm run check` | Biome: lint and format check (`npm run format` fixes) |
| `npm run typecheck` | TypeScript 7, strict |
| `npm test` | unit tests (Vitest) |
| `npm run build` | the build, in `dist/` |
| `npm run e2e` | end-to-end tests (Playwright) against the local stack on port 8790, with axe accessibility checks in light and dark colours and a check for sideways scrolling on a phone; needs `npm run build` and `forge build` first, and once `npx playwright install chromium` |

The end-to-end tests sign in with a test wallet that announces itself to the
page like a real one; its key stays in the test runner, which signs when the
page asks ([`web/e2e/testWallet.ts`](../web/e2e/testWallet.ts)).

The interface's texts are in [`web/src/strings.ts`](../web/src/strings.ts),
in one place for a later translation. Colours are tokens in
[`web/src/styles.css`](../web/src/styles.css), for light and dark.

## Rules

- **Supply chain** ([P3-02](decisions.md#p3-02-the-npm-supply-chain)):
  `web/.npmrc` turns install scripts off, saves exact versions and sets npm's
  `min-release-age` to 14 days, so every package, dependencies of
  dependencies included, is at least 14 days old when the lock file is made.
  CI installs with `npm ci --ignore-scripts` and audits the runtime
  dependencies (`npm audit --omit=dev`); Dependabot proposes updates after the
  same 14 days. Only React, React DOM and scheduler reach the browser.
- **Security headers** ([D-25](decisions.md#d-25-the-web-project)): every
  response of the service carries a content security policy that lets the
  page run only its own scripts and styles and connect only to its own origin,
  and forbids framing; also `X-Content-Type-Options: nosniff`,
  `Referrer-Policy: no-referrer` and `Cross-Origin-Opener-Policy: same-origin`.
- **No privileges in the browser**
  ([P3-06](decisions.md#p3-06-the-browser-holds-no-privileges)): the app
  calls the documented API only; everything it may do, the command line may
  do too.
- **Accessibility** ([P3-09](decisions.md#p3-09-accessibility-language-and-labels)):
  WCAG 2.2 AA. Every page is checked with axe in CI in light and dark colours;
  pages have their own titles, the navigation marks the current page, and a
  page change moves focus to its heading.

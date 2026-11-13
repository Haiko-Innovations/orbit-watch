# The web application

Phase 3, step 3.1. Code: [`web/`](../web). Decisions:
[P3-01 to P3-11](decisions.md#phase-3-decisions),
[D-25](decisions.md#d-25-the-web-project) and
[D-26](decisions.md#d-26-open-requests-are-public).

> **Testnet only, no real value.** The web application runs locally
> ([P3-10](decisions.md#p3-10-no-public-deployment-in-phase-3)). Every page
> says which chain it is on and that all data is SIMULATED.

One single-page application in TypeScript and React, built with Vite. The
Python service serves its build on the API's own origin, so the browser talks
to one server, and the app uses the documented [API](api.md) and nothing else.

What it has so far (step 3.1), without signing in:

| Page | Address | Shows |
|---|---|---|
| Network | `#/` | the service's version, the chain, the escrow, registry, token, EAS schemas, verifier and explorer, with explorer links on Base Sepolia |
| Open requests | `#/requests` | requests that invite observers: target, window, deadline, rewards and requirements ([`GET /v1/public/open-requests`](api.md)) |

Signing in with a wallet and the role views follow in steps 3.2 to 3.7
([roadmap](roadmap.md#phase-3-web-application-target-version-040)).

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
cd core && uv run python tests/local_stack.py   # the API on port 8787
cd web && npm run dev                            # http://127.0.0.1:5173/, /v1 forwarded to 8787
```

| Command (in `web/`) | Does |
|---|---|
| `npm run check` | Biome: lint and format check (`npm run format` fixes) |
| `npm run typecheck` | TypeScript 7, strict |
| `npm test` | unit tests (Vitest) |
| `npm run build` | the build, in `dist/` |
| `npm run e2e` | end-to-end tests (Playwright) against the local stack on port 8790, with axe accessibility checks in light and dark colours; needs `npm run build` and `forge build` first, and once `npx playwright install chromium` |

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

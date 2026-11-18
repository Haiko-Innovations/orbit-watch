# Phase 4 summary

Phase 4, the public testnet service, is complete as **version 0.5.0**. This is
the end-of-phase summary that the [plan](plan.md#8-deliverables) asks for.

> **Testnet only, no real value.** The service runs at
> <https://orbit-watch-tan.vercel.app> on Base Sepolia, with Circle's testnet
> USDC, which has no value. All stations, observations, targets and reviewers
> are SIMULATED.

## What works

- **A public service** ([deployment.md](deployment.md)). The API and the web
  application run on Vercel in Frankfurt, and the database is on Neon in
  Frankfurt. Both use Haiko Innovations' existing plans. Production is
  deployed by merging to `main`, and Vercel's instant rollback has been tried
  ([D-38](decisions.md#d-38-the-service-on-vercel-and-neon)).
- **PostgreSQL everywhere** (4.1, [D-34](decisions.md#d-34-postgresql-storage)).
  PostgreSQL holds every piece of state, files included, in production, in
  the local stack and in CI. The local stack still starts in one command.
- **A stateless service that runs on its own** (4.2,
  [D-35](decisions.md#d-35-the-stateless-service-the-follower-and-the-image)):
  - A follower runs every 15 minutes. It applies the escrow's events once
    they are 10 blocks deep, attests results, and settles and expires
    requests without anyone calling `tick`.
  - A transaction lock means that two instances never apply one change twice.
  - The same release runs as a container against any PostgreSQL, and CI tests
    the image end to end.
- **Limits against abuse** (4.3,
  [D-36](decisions.md#d-36-limits-the-body-limit-and-the-dedicated-rpc-endpoint)):
  - Limits apply per IP address and per party, counted in the database with a
    keyed hash, never the address itself. Vercel's firewall sits in front.
  - Request bodies are at most 4 MB.
  - The chain is read through a dedicated RPC endpoint whose key never reaches
    a response, a log or the browser. Since 4.8 that endpoint is Coinbase's
    CDP Node, with Base's public endpoint as the fallback
    ([D-43](decisions.md#d-43-the-dedicated-rpc-endpoint-coinbases-cdp-node)).
- **A privacy notice and terms of use** (4.4,
  [D-37](decisions.md#d-37-personal-data-in-the-service)):
  - Every page links to both, and the
    [data inventory](personal-data.md) lists every table, file, log and
    cookie.
  - Station places are kept to about a kilometre.
  - A station can delete its profile and end its sessions everywhere.
  - Haiko Innovations Oy, the controller, reviewed both on 2026-11-18.
- **Backups, monitoring and runbooks** (4.6,
  [D-39](decisions.md#d-39-backups-monitoring-and-read-only-mode)):
  - Every day, GitHub Actions takes an age-encrypted backup and keeps it for
    14 days. The restore drill passed.
  - An hourly uptime check opens an issue when something fails, and the
    alert reached the maintainer by email.
  - A read-only mode keeps the service answering while nothing changes.
  - Runbooks cover a leaked key, a leaked database password and an outage
    ([operations.md](operations.md)).
- **The review before the launch** (4.7):
  - A security review against all 65 level 1 requirements of OWASP ASVS
    5.0.0, with its four findings fixed
    ([security-review.md](security-review.md),
    [D-40](decisions.md#d-40-the-review-before-the-launch)).
  - The project is in English only
    ([D-41](decisions.md#d-41-english-only)).
  - The verifier key and the backup key are offline, apart from the
    production secret.
  - A run with a real wallet, below.

## The first request with real wallets

On 2026-11-17 and 18 the maintainer ran request REQ-20261117-KJN3 through
the public service with MetaMask: two new wallets, one as the requester and
one as a station.

1. The requester funded the request with 1.4 testnet USDC.
2. The station reserved it, made a SIMULATED station profile and delivered
   12 simulated observations.
3. The automated verification came out inconclusive, so two SIMULATED
   reviewers approved the delivery on chain.
4. The follower settled the request as accepted:

   | Party | Amount |
   |---|---|
   | The station | 1 USDC |
   | Each of the two reviewers | 0.1 USDC |
   | The platform fee | 0.1 USDC |
   | Back to the requester, the unused review reward | 0.1 USDC |

The run found three faults, all fixed:
- **[#93](https://github.com/Haiko-Innovations/orbit-watch/pull/93):**
  MetaMask 13.55 and newer allowed a network the site added, but no account on
  it, so it refused to sign. The page now connects again by itself.
- **[#94](https://github.com/Haiko-Innovations/orbit-watch/pull/94):**
  MetaMask made both wallets EIP-7702 smart accounts, whose transactions a
  relayer sends. The service now accepts a transaction when the escrow's or
  the token's events name the wallet as the one who acted.
- **[#95](https://github.com/Haiko-Innovations/orbit-watch/pull/95):** the
  bundled SIMULATED orbits were more than a week from their epoch. Every
  delivery since 2026-11-08 was therefore inconclusive, although the simulator
  computes from the same elements. The verification method is now version
  2.0.0 and has no age limit for a SIMULATED catalogue.

### Completion criteria

From [P4-16](decisions.md#p4-16-phase-4-completion-criteria):

| Criterion | Status |
|---|---|
| 1. The service and the web application run publicly at their address over HTTPS, on Base Sepolia only, with the testnet label and the SIMULATED label on every page | ✅ <https://orbit-watch-tan.vercel.app>. `public.spec.ts` checks the labels on every public page, and every role's end-to-end test checks them on the role's own pages |
| 2. Requests are attested, settled and expired on time without anyone calling `tick`; no state outside PostgreSQL; two instances never apply one change twice, tested | ✅ The follower is a Vercel Cron job and settled the first real request. `test_two_followers_settle_and_expire_once_without_tick` and `test_two_services_never_apply_one_change_twice` test it |
| 3. PostgreSQL is the only database, in production, in the local stack and in CI; the local stack starts in one command | ✅ [D-34](decisions.md#d-34-postgresql-storage). `tests/local_stack.py` starts its own PostgreSQL container |
| 4. The same release runs as a container against any PostgreSQL, with documented commands, and CI tests the image end to end | ✅ [api.md](api.md#running-the-image) documents it. CI's `tarkistus` runs the end-to-end tests against the image (`ORBIT_WATCH_E2E_IMAGE`) |
| 5. Every public and sign-in endpoint has documented limits, tested | ✅ [api.md](api.md#limits-against-abuse) and `test_limits.py` |
| 6. The privacy notice and the terms are linked from every page; personal data, its retention and its deletion are documented and implemented | ✅ `legal.spec.ts`, `test_privacy.py` and [personal-data.md](personal-data.md). The controller reviewed both texts on 2026-11-18 |
| 7. Only production holds the verifier key and the database password; no secret in the repository, a preview, the image or the browser, tested; runbooks for a leaked key and a leaked password | ✅ The keys are offline since 2026-11-17. `test_rpc.py` checks that the RPC key never appears in a response or a log. A preview has no settings and answers `503 not_configured`, and a service that cannot start logs why, never a secret (`test_deployment.py`). gitleaks runs in CI. The runbooks are in [operations.md](operations.md) |
| 8. A release is deployed by merging to `main`, and a rollback has been done | ✅ Every merge since #85, and a rollback with Vercel's instant rollback on 2026-11-17 |
| 9. Encrypted backups run every day outside Vercel and Neon, a restore drill has passed, and monitoring has alerted the maintainer once | ✅ The `Backup` workflow runs daily. The drill passed on 2026-11-17 ([operations.md](operations.md#drills)), and the alert test reached the maintainer the same day |
| 10. The review before the launch is done, each finding fixed or recorded; every CI check passes, including every role's end-to-end test; release 0.5.0 | ✅ [security-review.md](security-review.md): every finding fixed. The screen reader test follows the redesign of the web application ([D-42](decisions.md#d-42-the-screen-reader-test-after-the-redesign)). CI passes: 862 Python tests, 58 web unit tests and 42 end-to-end tests. This release |

## What is simulated, and what is a testnet

- **Everything that comes with the service is SIMULATED:** all stations,
  observations, reference orbits, targets and reviewers. Every simulated
  document says so, and so do the pages.
- **The money** is Circle's testnet USDC on Base Sepolia, of no value.
- **One maintainer holds the network's keys** for now:
  - the Safe's three signers and the simulated reviewers' keys
    ([D-24](decisions.md#d-24-the-base-sepolia-deployment));
  - the verifier key, offline apart from the production secret;
  - the account behind the RPC endpoint.
  Making the network depend on no single person is the long-term direction
  ([decentralisation.md](decentralisation.md)).
- **The reviewers have no accounts on the public service.** Their votes go
  straight to the chain, so the service knows a vote's reason only by its
  SHA-256 and shows it that way.
- **The automated verification is a prototype**, not scientific validation
  ([verification.md](verification.md)).

## How to use it

Open <https://orbit-watch-tan.vercel.app> and sign in with a wallet such as
MetaMask on Base Sepolia. Sign up as a requester or a station. Testnet ETH
and USDC come from the faucets in
[base-sepolia.md](base-sepolia.md#testnet-eth-and-usdc-faucets).

To run it all locally instead, with Node 26, uv and Foundry 1.8.6
([web.md](web.md#run-it)):

```sh
git clone --recurse-submodules --branch v0.5.0 https://github.com/Haiko-Innovations/orbit-watch.git
cd orbit-watch
cd contracts && forge build && cd ../web && npm ci && npm run build
cd ../core && uv run python tests/local_stack.py --web ../web/dist
```

## Open problems for the next phase

- **The web application's redesign, then a screen reader test** by a person
  ([D-42](decisions.md#d-42-the-screen-reader-test-after-the-redesign),
  [#97](https://github.com/Haiko-Innovations/orbit-watch/issues/97)).
- **Separate people for the keys:** Safe signers from the community, and
  verifier nodes that agree k of n instead of one key
  ([#77](https://github.com/Haiko-Innovations/orbit-watch/issues/77)).
- **Reviewers on the service:** reviewers are added by the maintainers from
  the command line and cannot sign up. The simulated reviewers' votes carry
  no reason text.
- **The RPC account** moves from the maintainer to Haiko Innovations
  ([D-43](decisions.md#d-43-the-dedicated-rpc-endpoint-coinbases-cdp-node)).
- **Other wallets:** only MetaMask has been used for real. Contract wallets
  that sign in with ERC-1271, such as Coinbase Smart Wallet, are untested.
- **Carried over from phase 3:** calibration on chain, bonds for reservations,
  challenges and reviewers, and a real IOD example
  ([#8](https://github.com/Haiko-Innovations/orbit-watch/issues/8)).

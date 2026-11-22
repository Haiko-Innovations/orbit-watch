# Personal data

Phase 4, step 4.4 ([P4-09](decisions.md#p4-09-personal-data-a-privacy-notice-and-terms-of-use),
[D-37](decisions.md#d-37-personal-data-in-the-service)). This is the inventory of
the personal data that the public testnet service keeps: every table, file, log
and cookie, who sees it, how long it is kept and what deletes it. It is written
for the people who run and review the service. The people who use it read the
[privacy notice](legal/privacy-notice.md), which says the same in plain words,
and the [terms of use](legal/terms-of-use.md). The web application shows both at
`#/privacy` and `#/terms`, and links to them from every page.

The controller is Haiko Innovations Oy (info@haikoinnovations.com, subject
"Orbit Watch privacy"). A change to what the service keeps changes this file, the
notice and its version date in the same pull request.

## Principles

- **Keep as little as possible.** No analytics, trackers, advertising or
  third-party content: the web application loads everything from its own
  origin (the content security policy allows nothing else). It stores nothing
  in the browser but the sign-in cookie.
- **Public by design, said plainly.** Party names, wallet addresses and, once
  published, a request's files are public. What is on the chain cannot be
  deleted.
- **A station is not an address.** A station may be someone's home. Its observer
  chooses whether the public service keeps and publishes its place exactly or to
  two decimals of a degree, 1.1 km of latitude and 0.55 km of longitude at 60°
  north, with nothing chosen in advance (P5-11,
  [D-54](decisions.md#d-54-the-observer-chooses-how-precisely-the-place-is-published)).
  A profile saved before the choice existed stays at two decimals until its owner
  chooses.
- **Deleted when no longer needed.** `api/privacy.py`'s `sweep` deletes what has
  expired; the follower runs it (every 15 minutes on the public service,
  [P4-06](decisions.md#p4-06-the-service-runs-on-its-own)) and so does
  every sign-in.

## The inventory

Legal bases (GDPR article 6(1)): **b**, the contract, that is the terms of use;
**f**, our legitimate interest in a secure, available and verifiable service.

| Data | Where | Who sees it | Kept | Deleted by | Basis |
|---|---|---|---|---|---|
| Party name, such as `station:SIM-HELSINKI` | `wallets`, `api_keys`, and the tables that name parties (`requests`, `deliveries`, `review_tasks`, `transactions`, `element_sets.uploaded_by`, `orbit_sources.resumed_by`, `allowlist_additions.added_by`, …) | public | while the service runs | an administrator, on request | b |
| Wallet address | `wallets.address`, `sessions`, `signin_challenges`; on the chain | public on the chain | while the service runs | an administrator, on request; never on the chain | b |
| Message and signature that registered a wallet | `wallets.signature`, `wallets.signed_message` | administrators | while the service runs | with the wallet's row | b, f |
| Sign-in message: address, origin, nonce, times, the name to sign up | `signin_challenges` | the service only | an hour after it expires (it expires after 5 minutes) | `sweep` | b |
| Session: SHA-256 of the cookie, party, role, address, origin, times | `sessions` | the party (`GET /v1/session`) | until signed out, at most 12 hours | `DELETE /v1/session`, `DELETE /v1/sessions`, `sweep` | b |
| Session cookie `__Host-ow_session` over HTTPS (`Secure`, `HttpOnly`, `SameSite=Strict`, `Path=/`); `ow_session` over plain http on a developer's machine | the browser | that browser | at most 12 hours | signing out, its expiry | b; no consent needed ([D-37](decisions.md#d-37-personal-data-in-the-service)) |
| Station profile: name, place exactly or to two decimals as the station chooses (`place`, [D-54](decisions.md#d-54-the-observer-chooses-how-precisely-the-place-is-published)), height, SIMULATED instrument | `station_profiles` | the station, administrators | until deleted | `DELETE /v1/stations/{party}/profile` (the station or an administrator) | b |
| Request documents, with their titles | `files`, `requests` | the parties, administrators; anyone once published | while the service runs | an administrator, on request | b, f |
| Observation files, naming the station's place as precisely as it chose | `files`, `deliveries`, `chain_uploads` | the parties, administrators; anyone once published | while the service runs | an administrator, on request | b, f |
| Verification reports | `files`, `deliveries` | as above | while the service runs | as above | b, f |
| Reasons for challenges and reviews | `chain_texts`, `requests.record_json`; their SHA-256 on the chain | the parties, administrators; anyone once published (`GET /v1/requests/{id}` hides them from other parties since step 4.7) | while the service runs | an administrator, on request; never the hash on the chain | b, f |
| Reported transactions: hash, party, status, error | `transactions` | the party, administrators | while the service runs | an administrator, on request | b |
| Copies of answers to changes | `idempotency` (with the call's path) | the party, if it retries | 24 hours | `sweep`; a deleted profile takes its copies with it | b |
| Limit counts: a party, or an IP address as a keyed SHA-256 (IPv6 per /64) | `rate_limits`, keyed with `service_state.limit_key` | the service only | until the window ends, at most an hour | `Limits.hit`, `sweep` | f |
| API keys, for the command line: SHA-256 and party | `api_keys` | administrators | until revoked | an administrator | b |
| IP addresses in the service's own logs | nowhere: `orbit-watch serve` writes no access log unless `--access-log` is given | | | | |
| The hosting provider's request logs, which may hold IP addresses | Vercel | the maintainers | at most 30 days: Vercel's runtime logs with Observability Plus ([D-38](decisions.md#d-38-the-service-on-vercel-and-neon)) | Vercel | f |
| Backups of the database, without sessions, sign-in challenges, limit counts and copies of answers | encrypted with age by the service, kept as GitHub Actions artifacts ([D-39](decisions.md#d-39-backups-monitoring-and-read-only-mode)) | the maintainer's private key only | 14 days | expiry | f |
| Email to us | the maintainers' mailbox | the maintainers | while it is handled | the maintainers | b, f |
| Wallet address, transactions, attestations and votes naming request IDs, file and reason SHA-256s | Base Sepolia, EAS | public | permanently | cannot be deleted | |

The points ledger of phase 1 (`ledger_*`, `attestations`) names parties as well;
the public service runs on the chain and keeps no points.

## Observations that others have published

Phase 5, step 5.2 ([P5-06](decisions.md#p5-06-real-observations-from-score),
[D-45](decisions.md#d-45-real-observations-from-score)). The repository holds real
observations that observers published themselves in SCORE under CC BY 4.0, in
[`examples/real/`](../examples/real) and, since step 5.3
([D-46](decisions.md#d-46-the-method-measured-on-real-data)), in the validation set
[`validation/real/`](../validation/real). Replays through the service (step 5.5,
[D-51](decisions.md#d-51-replays)) hold the same kind of data.

| Data | Where | Who sees it | Kept | Deleted by | Basis |
|---|---|---|---|---|---|
| Observers' ORCID iDs, the observer's place as published in SCORE, instrument, observation times and positions, SCORE's observation IDs | `examples/real/observations/`, `examples/real/CREDITS.md`, the quality reports in `examples/real/quality/` | public, as in SCORE | as long as the example is in the repository | a maintainer, on request: removed from the next version; the repository's history and others' copies stay | f |
| The same, for the validation set | `validation/real/observations/`, `validation/real/CREDITS.md` | public, as in SCORE | as long as the set is in the repository | a maintainer, on request, as above | f |
| The same, replayed through the service: the observation file, and the replay request naming the source, the licence and the observers' ORCID iDs | `files`, `deliveries`, `requests` | the parties, administrators; anyone once the replay is settled | while the service runs | an administrator, on request | f |
| Station IDs (a hash of the place, instrument and observers) and file names, with each track's results | `validation/real/results.json`, `validation/real/known-answers.json`, the tables of [real-data-validation.md](real-data-validation.md) | public | as long as the set is in the repository | a maintainer, on request, as above | f |

**GDPR article 14**, for data not obtained from the person, was read on 2026-11-21
([text](https://gdpr-info.eu/art-14-gdpr/); EUR-Lex's own page asked for a browser
check, which an automated client does not pass):
- Article 14(1) and (2) list what the person is told, among it "from which source the
  personal data originate, and if applicable, whether it came from publicly accessible
  sources". The [privacy notice](legal/privacy-notice.md#observations-that-others-have-published)
  says all of it in a section of its own.
- Article 14(3) asks for this "within a reasonable period after obtaining the personal
  data, but at the latest within one month".
- Article 14(5)(b) lifts the duty where telling each person "proves impossible or would
  involve a disproportionate effort", and then asks for "appropriate measures …
  including making the information publicly available".

We have only the observers' ORCID iDs, not their contact details. The public notice is
the measure taken in the repository. Whether to reach the observers directly, for
example through SCORE's maintainers, is the maintainer's decision as the controller. It
needs someone outside the repository, so it is a follow-up at the end of the phase
([P5-14](decisions.md#p5-14-follow-ups-at-the-end-not-in-the-way),
[#113](https://github.com/Haiko-Innovations/orbit-watch/issues/113)). This is our reading,
not legal advice.

## Who else handles it

- **Vercel Inc.**, hosting: a processor under its DPA, which includes the 2021
  standard contractual clauses; Vercel is certified under the EU–U.S. Data
  Privacy Framework. The function runs in Frankfurt (`fra1`), and the static
  pages are served from Vercel's network ([D-38](decisions.md#d-38-the-service-on-vercel-and-neon)).
- **Neon** (Databricks, Inc.), the database: a processor. The project is in
  AWS Frankfurt (`aws-eu-central-1`, Vercel's `fra1`), on the Free plan; a Neon
  project's region cannot be changed later. Databricks names Neon, LLC in its
  Data Privacy Framework certification.
- **GitHub, Inc.**, the encrypted backups ([D-39](decisions.md#d-39-backups-monitoring-and-read-only-mode)),
  which it cannot read.
- **The RPC provider** answers the service's reads of the chain: Coinbase's
  CDP Node (Coinbase, Inc.) since 2026-11-18, with Base's public endpoint as
  the fallback ([D-43](decisions.md#d-43-the-dedicated-rpc-endpoint-coinbases-cdp-node)).
  The service sends it nothing about anyone that is not already public on the
  chain. The browser's wallet uses its own provider, which the user chooses.

## Requests from the people the data is about

They come by email. Before answering, an administrator checks that the account
is theirs, for example by a message signed with the wallet. Then:

- **A copy:** the rows above that name the party or its address, and its files.
- **Correction:** a station corrects its profile itself; anything else by an
  administrator.
- **Deletion:** a station deletes its profile and ends its sessions itself. An
  administrator deletes the rest unless it is needed to settle a request or to
  answer a challenge, and ends the party's sessions first
  (`DELETE FROM sessions WHERE party = …`), so that no browser stays signed in. Nothing on the chain, and no copy of published data that
  others have made, can be deleted; the notice says so.

Answers are due within a month (GDPR article 12(3)).

## Tests

- `core/tests/test_privacy.py`: no profile saved without the choice of exact or
  about a kilometre; profiles rounded to two decimals when the station chose so, and
  kept exactly when it chose so; changing the choice; a profile saved before the
  choice stays rounded; more precise deliveries refused unless the station chose
  exact, and nothing kept of them; observations simulated with a
  profile pass; deleting a profile (the station, an administrator, nobody else)
  and its idempotency copies; idempotency for 24 hours; the sweep and what it
  leaves; signing out everywhere; the follower and sign-ins sweeping; the
  command line's defaults.
- `core/tests/test_limits.py`: no IP address is stored (step 4.3).
- `core/tests/test_api.py`: `orbit-watch serve` writes no access log by default.
- `web/src/legal/markdown.test.ts`: the notice and the terms read, and link only
  to the service's pages, HTTPS and email.
- `web/e2e/legal.spec.ts`, `a11y.spec.ts`, `sign-in.spec.ts`,
  `observer.spec.ts`: the pages without signing in and without the service, the
  links on every page, signing out everywhere, the precision and deleting a
  profile in the browser.

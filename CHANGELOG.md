# Changelog

All notable changes to Orbit Watch are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).
Formats and methods have their own versions; see [docs/releasing.md](docs/releasing.md).

## [Unreleased]

## [0.6.0] - 2026-11-23

Phase 5: real orbits and real observations on the testnet, beside the simulated ones
([phase 5 summary](docs/phase-5-summary.md)).

### Added

- Real data end to end on Base Sepolia (step 5.8, #111). On the public service, a replay
  of 108 real observations of PELICAN-1 from SCORE and a request for the real object
  CUBESAT XI-IV (CO-57) with SIMULATED observations both settled, with the testnet
  keystores. The phase 5 summary records them and the completion criteria, and that
  CelesTrak and SatChecker answered every request.

- Phase 5 plan: real orbits and real observations on the testnet, in eight
  steps (5.1 to 5.8) with completion criteria in `docs/roadmap.md`, and the
  proposed decisions P5-01 to P5-15 in `docs/decisions.md`, approved on
  2026-11-21 (#103). Reference orbits from CelesTrak and SatChecker, real
  observations from SCORE under CC BY 4.0, the method measured on real data
  first, real and simulated data side by side, the observer's own choice of
  how precisely a station's place is published, and follow-ups at the end for
  whatever needs the maintainer or someone outside the repository.
- Past reference orbits from the IAU CPS's SatChecker: `orbit-watch
  fetch-satchecker` fetches the element set of one object nearest a time, in one
  request with no retries, and converts a TLE to OMM form (step 5.1, #104).
- Reference-orbit manifests (`orbit-watch/reference-orbits` 1.0): examples and
  tests name their real element sets instead of committing them, and
  `orbit-watch fetch-orbits` fetches what the local cache lacks, two seconds
  apart, checking every SHA-256. CI keeps the cache in GitHub Actions' cache
  only.

- Real observations from the IAU CPS's SCORE (CC BY 4.0): `orbit-watch fetch-score`
  fetches one object's observations in a window, politely, and `orbit-watch
  convert-score` writes each track as an observation set that names SCORE, the
  observers' ORCID iDs, SCORE's observation IDs and the licence, with a credits file
  (step 5.2, #105).
- `examples/real/`: 18 tracks of real observations from 7 stations and five kinds of
  instrument, with credits, a manifest of their reference orbits and the quality
  meter's report for each station. Phase 0's last criterion, a real public example, is
  met (#8).
- Observation set format 1.1: `source.origin` for observations that someone else
  published. Every other file stays 1.0.
- The privacy notice (version of 21 November 2026) and the data inventory say what
  Orbit Watch keeps of observations that others published in SCORE.
- The verification method measured on real data (step 5.3, #106): `orbit-watch
  measure-method` runs method 2.1.0, unchanged, over 56 real tracks and over copies
  with faults put into them, and writes `validation/real/results.json` and the tables
  of `docs/real-data-validation.md`. The page gives the numbers and five candidates
  for later decisions; the method is unchanged (D-46).
- `validation/real/`: a validation set of 38 more real tracks from SCORE, credited,
  with its reference orbits named in a manifest.
- Known answers from real tracks for reviewer calibration:
  `validation/real/known-answers.json` and `calibration.build_real_files`.
- Reference orbits in the service (step 5.4, first part, #107): real element sets are
  kept in PostgreSQL with their source, fetch time, epoch and SHA-256 (migration 0010),
  and a delivery for a real object is verified against the nearest stored set, which its
  report names. `POST /v1/admin/element-sets` and `orbit-watch admin upload-orbits`
  upload sets by hand, labelled as uploaded; `GET /v1/public/reference-orbits` names the
  sets without serving them (D-47).
- The follower fetches reference orbits (step 5.4, second part, #107), with
  `orbit-watch serve --fetch-orbits` or `ORBIT_WATCH_FETCH_ORBITS=1`: CelesTrak's current
  sets for open requests for real objects, once per update, and SatChecker's set nearest a
  window that has ended, at most three requests per run (migration 0011). The first
  answer that is not 200, or no answer, stops that source until an administrator resumes
  it (`POST /v1/admin/reference-orbits/resume`, `orbit-watch admin resume-orbits`), and
  `GET /v1/health/reference-orbits` answers `503` meanwhile, which the hourly uptime check
  reports (D-48).
- Real objects on the allow-list (step 5.4, third part, #107): the follower fetches
  CelesTrak's groups `science`, `education`, `amateur` and `cubesat`, and `military` and
  `radar` to exclude, each at most once a day, with the same stops (migration 0012). An
  administrator adds an object with a public reason (`POST /v1/admin/allowlist`,
  `orbit-watch admin allow`) and takes it back (`orbit-watch admin disallow`); the name
  patterns apply to both. `GET /v1/public/targets` says of each object whether it is
  SIMULATED and why it is on the list (D-49).
- Simulated stations on real objects (step 5.5, first part, #108): a request for a real
  object may be SIMULATED, and a station's simulator and the administrator's then
  observe the object along its stored element set nearest the window. Without one they
  answer `no_reference_orbit` until the follower has fetched it. The web application
  asks with a box that is not ticked in advance (D-50).
- Replays (step 5.5, second part, #108): request format 1.1 adds a `replay` block that
  names the published observation file by its SHA-256, the replay station, and the
  file's source, licence and observers. An administrator creates a replay for a
  requester (`POST /v1/admin/replays`, `orbit-watch admin replay`), with a window that
  has ended. Only its replay station reserves and delivers it, only that file, and only
  once the service keeps SatChecker's set near the window. The place is kept as
  published, and the testnet reward goes to the replay station (D-51).
- Labels by source (step 5.5, third part, first half, #108): `labels` in request summaries,
  request lists, open requests and the administrator's overview say whether the request is
  SIMULATED, what its object is and why it is on the list, where its reference orbit comes
  from with its epoch, and whose its observations are. The web application shows them on
  every page that shows requests, and a review task's page reads them from its files. A
  data sources page credits CelesTrak, SatChecker and SCORE with the statements they ask
  for (D-52).
- The local stack has a made-up stand-in for a real object beside its SIMULATED requests
  (step 5.5, third part, second half, #108). It is on the allow-list with an uploaded
  orbit, with a SIMULATED request for it that a simulated station fulfilled, a real request
  that is open, and a replay of made-up published observations that settled. The
  end-to-end tests check their labels on every page (D-53).
- The observer chooses how precisely the station's place is published (step 5.6, first
  part, #109): exactly, or to about a kilometre. Neither is selected in advance, a profile
  is not saved without the choice, and it can be changed for later deliveries. Profiles
  saved before stay at about a kilometre until their owner chooses (migration 0013).
  A station that chose exact may deliver files with its exact place (D-54).
- The profile is the station's place for every format (step 5.6, second part, #109): a
  JSON delivery from another place is refused (`wrong_place`), and an IOD or CCSDS TDM
  delivery is verified at the profile's place, which is kept and published with it as its
  `station_place` file (migration 0014). The public service needs a profile to deliver
  (`profile_required`); replays are exempt (D-55).
- The Sun's place for visibility (step 5.7, first part, #110): `orbit_watch.sun` computes
  the Sun's direction, its elevation at a station, a dark sky and whether a satellite is
  sunlit, from the US Naval Observatory's short formula and without an ephemeris file.
  `orbit-watch measure-sun` measured it against JPL's DE421: at most 55.9″ off over
  1900–2049 (`validation/sun/results.json`, docs/visibility.md, D-56).
- The simulator observes only what a station can see (step 5.7, second part, #110, #7):
  objects lit by the Sun under a dark sky, by default with the Sun at least 6° down
  (`dark_sky_deg`, `--dark-sky-deg`, `--any-light`). `orbit_watch.passes` finds each
  pass's visible part (D-57).
- A station's visible passes for a request (step 5.7, third part, #110): `GET
  /v1/requests/{id}/passes`, and "Your visible passes" on a request's page for a station.
  Each pass has its rise, highest point and set over the station's place, above its
  instrument's elevation limit, and the part lit by the Sun under a dark sky (D-58).

### Changed

- A request for an object not on the allow-list is refused when it is made
  (`target_not_allowed`), instead of failing the target check at delivery. A delivery
  for a real object is verified against the real objects of the list, so that its report
  does not say SIMULATED. The web application marks a request SIMULATED when its target
  is, and simulated stations observe only the service's own objects (D-49).
- A real request for a SIMULATED object is refused when it is made (`simulated_target`),
  and a station's simulator refuses a real request (`real_request`): SIMULATED
  observations cannot fulfil it. On a real request's page the web application shows no
  simulate button and says why (D-50).
- The testnet label and the terms of use (version of 22 November 2026) no longer say that
  all data is SIMULATED: SIMULATED and real data run side by side, and each says which it
  is (D-52).
- The privacy notice (version of 22 November 2026) says that the station's place is kept
  as precisely as its observer chooses, and that replays publish their observers' ORCID
  iDs; the data inventory lists both (D-54).
- `too_precise` is gone: a file more precise than its station's profile is from another
  place, `wrong_place` (D-55).
- The SIMULATED sun-synchronous objects cross the equator at about 19:30 local time
  instead of 22:40 (right ascension of the ascending node 330° instead of 15°), so that
  over Finland in November their evening passes are lit under a dark sky. The committed
  simulated examples and the phase 1 demo are regenerated; every verdict and outcome is
  the same (D-57).

- Verification method 2.1.0 and report format 1.1: when the catalogue holds
  several element sets of the object, the residuals use the set nearest the
  middle of the observations, and the report names it by its SHA-256, the
  choice and its source, never the set itself. With one set per object every
  verdict stays the same. The station quality meter (1.1.0) does the same per
  observation file.
- `orbit-watch fetch-gp` asks CelesTrak for CSV with gzip, as its usage policy
  of 2026-11-16 asks, and after an answer that is not 200 says what the policy
  asks next.
- `orbit-watch fetch-gp` and `fetch-satchecker` treat a broken or timed-out connection
  like an unreachable server: they say so and stop, instead of failing with a traceback.
- CI restores the older cache of real element sets when a manifest changes, so that
  SatChecker is asked only for the sets it lacks, and saves the cache right after
  fetching, before any later step can fail. It runs the tests with one BLAS thread, and
  the job may take 30 minutes, for a cache filled from scratch.

### Fixed

- A published replay's attribution named its replay station as the observer. It now names
  the observers by their ORCID iDs, the source and the licence, and the replay station as
  the one that replayed them (P5-10, D-51); found on the first replay on Base Sepolia.

- A request whose verification report is of format 1.0 (methods 1.0.0 and 2.0.0) broke
  its labels (D-52): the report names its reference orbit without the set's SHA-256. The
  public page of production's first settled request, and the administrator's overview,
  answered 500 since the labels came; the label now has no SHA-256 for such a report.

- `convert-score` no longer splits a track where a phone's place jumps for one
  observation: such an observation is left out, counted and noted in the file. Before,
  two pieces of a track could get the same file name, and one overwrote the other; the
  command now refuses to write two tracks to one file. The track left out of
  `examples/real/` in step 5.2 was described as a phone that moved 7 km; six of its
  observations had jumped (D-46).

## [0.5.0] - 2026-11-18

Phase 4: the public testnet service. The service and the web application run
on Vercel and Neon in Frankfurt, on the Base Sepolia testnet only, with
testnet USDC of no value and SIMULATED data
([docs/phase-4-summary.md](docs/phase-4-summary.md)).

### Added

- The phase 4 summary (`docs/phase-4-summary.md`), with the completion
  criteria and the first request run with real wallets.
- Phase 4 plan: a public testnet service in eight steps (4.1 to 4.8) with
  completion criteria in `docs/roadmap.md`, and the proposed decisions P4-01 to
  P4-16 in `docs/decisions.md`, approved on 2026-11-14 (#67): Vercel and Neon,
  PostgreSQL wherever the service keeps state, a stateless and portable
  service, and nothing that closes the way to a network the community runs.
  The long-term direction for that network is in `docs/decentralisation.md`.
- The service runs on its own (phase 4, step 4.2; P4-05, P4-06, D-35). A
  follower applies passed deadlines and the escrow's events, attests results
  and settles decided requests without anyone calling `tick`. It runs from a
  schedule (`GET` or `POST /v1/internal/follow` with the secret in
  `ORBIT_WATCH_FOLLOW_SECRET` or `CRON_SECRET`), from a timer, or in the server
  (`orbit-watch serve --follow SECONDS`). `GET /v1/health/follower` tells
  monitoring whether it keeps up.
- A container image of the service with the web application (`Dockerfile` at
  the root): base images pinned by digest, an ordinary user, no writable file
  system but `/tmp`, listening on `$PORT`. CI builds it and runs the end-to-end
  tests against it (`local_stack.py --image`, `ORBIT_WATCH_E2E_IMAGE`), and
  Dependabot proposes updates to its base images.
- `orbit-watch serve --confirmations BLOCKS`: on a chain, events are applied
  once their block is that deep, by default 10 blocks on Base Sepolia (about
  two seconds) and none on a local Anvil chain.
- Limits against abuse (phase 4, step 4.3; P4-08, D-36). The service counts in
  its database, per IP address and per party:
  - sign-in and sign-up attempts;
  - new requests;
  - uploads;
  - quality meter runs;
  - every call of the public pages.

  A call over a limit gets `429 rate_limited` with `Retry-After`. No IP address
  is stored, only a keyed hash, deleted when its window ends.
  `orbit-watch serve` applies the defaults. `--limits` (or
  `ORBIT_WATCH_LIMITS`) changes them or turns them off. `--client-ip-header`
  (or `ORBIT_WATCH_CLIENT_IP_HEADER`) names a trusted proxy's header,
  `x-real-ip` on Vercel.
- A dedicated RPC endpoint (step 4.3; P4-07, D-36): `ORBIT_WATCH_CHAIN_RPC`,
  with Base's public endpoint as its fallback when the dedicated one is down or
  busy. Its URL, which holds the provider's key, never reaches a response, a
  log or the browser, and tests look for it at debug level.
- A privacy notice and terms of use, in English and Finnish (phase 4, step 4.4;
  P4-09, D-37): `docs/legal`, shown by the web application at `#/privacy` and
  `#/terms` without signing in and linked from every page. `docs/personal-data.md`
  lists everything the service keeps about people, who sees it and for how long.
- The public testnet service on Vercel and Neon, in Frankfurt (phase 4, step
  4.5; D-38): `vercel.json` deploys the web application and the API together,
  a cron job runs the follower every 15 minutes, and a firewall rule limits
  each IP address. `docs/deployment.md` describes the settings, the database,
  deploying by merging to `main`, and rolling back with Vercel's instant
  rollback.
- Backups, monitoring and read-only mode (phase 4, step 4.6; D-39;
  `docs/operations.md`). The service takes a consistent backup of its database,
  encrypted with age to the maintainer's public key (`GET /v1/internal/backup`
  with `ORBIT_WATCH_BACKUP_TOKEN` and `ORBIT_WATCH_BACKUP_RECIPIENT`), and the
  `Backup` workflow keeps it for 14 days. `orbit-watch backup create` and
  `orbit-watch backup restore` take and restore one; a restore applies newer
  migrations after the backup's. The `Uptime` workflow checks the service every
  hour. A failed run of either workflow opens an issue assigned to the
  maintainer (`ALERT_ASSIGNEE`), and the next passing run closes it. `serve --read-only` (or
  `ORBIT_WATCH_READ_ONLY=1`) refuses every change with `503 read_only` and lets
  the follower wait; the web application says so on every page. Runbooks for
  failures, restores and leaked keys and passwords. pyrage joins the `api` extra.
- `orbit_watch.asgi`: the service as an ASGI application set up by the
  environment, for any ASGI server (`uvicorn orbit_watch.asgi:app`); without a
  database it answers `503 not_configured`. The verifier key may come from
  `ORBIT_WATCH_VERIFIER_KEY`.
- `ORBIT_WATCH_DATABASE_ROLE`: every transaction runs as a role that may only
  read and write the service's tables; the database's owner runs the
  migrations. `ORBIT_WATCH_DATABASE_SSLMODE` sets libpq's TLS mode, with
  `certifi`'s roots for `verify-full`.
- A station deletes its profile (`DELETE /v1/stations/{party}/profile`, a
  button on "Your station"), and a party signs out everywhere
  (`DELETE /v1/sessions`, a button on "Your account").
- `orbit-watch serve --station-decimals N` (default 2, about a kilometre, or
  `ORBIT_WATCH_STATION_DECIMALS`): station profiles are kept to that precision,
  and a delivered file with more precise station coordinates is refused with
  `422 too_precise`. `--access-log` logs requests with IP addresses, which
  `serve` no longer does by default.

### Changed

- The verification method is version 2.0.0, and new requests' terms name it:
  a SIMULATED catalogue has no reference age limit (see Fixed). A request
  published earlier keeps the method its terms name in its result
  attestation, while its report names the method that ran.
- The public service reads Base Sepolia through a dedicated RPC endpoint,
  Coinbase's CDP Node, with Base's public endpoint as the fallback (phase 4,
  step 4.8; D-43). Its URL is a production secret.
- `GET /v1/health` and `orbit-watch serve` no longer call the service a phase 1 or
  phase 2 prototype: the notice names the chain, such as "Base Sepolia testnet, no
  real value", and says that all bundled data is SIMULATED. `docs/api.md` no
  longer says the API has no public deployment.
- English only (D-41): the Finnish translations are removed, from the README
  and the contributing guide, the plan, the roadmap and the phase summaries to
  the privacy notice and the terms of use; the web application's `#/privacy/fi`
  and `#/terms/fi` are gone, and its footer links to the two English pages.
- The README and the package describe Orbit Watch as the service it is:
  ordering satellite observations, verifying every delivery independently and
  paying only for results that hold up, rather than "a protocol and reference
  implementation".

- Any number of service processes can share one database (step 4.2, D-35):
  transactions on a schema take turns under a transaction-scoped advisory lock,
  and a process reloads its copy of the state when another one changed it. The
  `in_use` refusal is gone, and `orbit-watch keys create` works while a server
  runs. Idempotency keys are checked in the change's own transaction, so a call
  sent to two processes at once is made once.
- Bodies are at most 4,000,000 bytes, under Vercel's 4.5 MB, instead of 10 MiB
  (step 4.3). A larger body is refused with `413` before any route reads it.
- The storage layer opens a lost database connection again, and uses no
  server-side prepared statements, so that it works behind a pooler and with a
  database that scales to zero (step 4.5).
- The hosting provider's logs are kept for 30 days instead of 14 (step 4.5,
  D-38); the privacy notice says so.
- What the service no longer needs is deleted (step 4.4, D-37): signing out
  deletes the session, and the follower and every sign-in delete expired
  sessions, sign-in messages an hour after they expire, past limit counts and
  idempotency records older than 24 hours. An `Idempotency-Key` is remembered
  for 24 hours (migration 0009).

- The service keeps its state, files included, in PostgreSQL instead of SQLite
  (phase 4, step 4.1; P4-04, D-34). `orbit-watch serve` and
  `orbit-watch keys create` take `--database` (a libpq URL), or
  `ORBIT_WATCH_DATABASE_URL` or `DATABASE_URL`, instead of `--dir`. psycopg is
  part of the `api` extra. The open core's command-line tools need no database.
  The local stack starts a PostgreSQL of its own in Docker. The tests that need a
  database start one too, or use `ORBIT_WATCH_TEST_DATABASE_URL`, and are
  skipped without either unless `ORBIT_WATCH_PG_TESTS=1`, as in CI. Earlier
  SQLite service directories are not migrated.

### Fixed

- The automated verification no longer applies the reference orbit's age
  limit (`max_reference_age_days`) to a SIMULATED catalogue. The simulator
  computes observations from the same elements, so their age does not matter,
  but every delivery on the public testnet more than seven days after the
  bundled catalogue's epoch (2026-11-01) came out inconclusive and went
  straight to reviewers. The first delivery with a real wallet in step 4.7
  found it. With real elements the limit stays. A change in pass or fail
  logic is a new major version of the method, so this is method 2.0.0
  (`docs/verification.md`); the release 0.5.0 sets it, after #95 had kept
  1.0.0 by mistake.
- A request with reviewers is shown as "Reviewers are checking it". It said
  "Challenged" even when nobody had challenged it and an inconclusive result
  had sent it to reviewers; the progress list says which it was.
- Transactions that a smart account's relayer sends for the wallet, such as
  MetaMask's EIP-7702 smart account, were refused as `not_your_transaction`,
  because their sender is the relayer. Once such a transaction is mined, the
  service now accepts it if the escrow's or the token's events name the
  party's wallet as the one who acted (`msg.sender`). While it is still
  pending, the answer is `transaction_pending` (`docs/api.md`). The run with a
  real wallet in step 4.7 found it.
- Signing in and sending with MetaMask 13.55.0 or newer on a network the site
  had just added. MetaMask permitted the network but no account on it, so it
  refused every signature and transaction there with error 4100 and showed no
  prompt (metamask-extension#47773). The page now disconnects the site, connects
  it again and tries once more, and otherwise tells the user what to do
  (`docs/web.md`). The run with a real wallet in step 4.7 found it.
- The review before the launch (phase 4, step 4.7; D-40;
  `docs/security-review.md`), against every OWASP ASVS 5.0.0 level 1
  requirement:
  - over HTTPS the session cookie is `__Host-ow_session`, and a session signed
    in over HTTPS counts only under that name;
  - a sign-in ends the browser's earlier session;
  - `GET /v1/requests/{id}` hides the reasons written for a challenge and its
    votes from parties other than the request's own, until it is published
    (`"reasons_hidden": true`);
  - `SECURITY.md` gives time frames for fixing vulnerabilities and the public
    service's scope.

- `orbit-watch serve --read-only` no longer follows the chain once at start,
  which wrote to the database; found in the first restore drill (phase 4,
  step 4.6).

- The phase 1 demo told another story after every release: its reviewer rounds
  are drawn from each delivery's SHA-256, and its observation files named the
  software's version. They now name the simulator without a version, so every
  release draws the same rounds. The rubber stamper's missed calibration task
  stays visible.

## [0.4.0] - 2026-11-13

Phase 3: the web application, with each party's own wallet in the browser.
Testnet only: nothing here touches a mainnet or real money, and the service
runs locally.

### Added

- Phase 3 plan: the web application in eight steps (3.1 to 3.8) with
  completion criteria in `docs/roadmap.md`, and decisions P3-01 to P3-11 in
  `docs/decisions.md`, approved on 2026-11-13.
- The web application's project (phase 3, step 3.1): `web/`, a TypeScript and
  React single-page app built with Vite, with the public pages Network and
  Open requests and a testnet label on every page. `orbit-watch serve --web
  web/dist` serves it on the API's own origin, and every response carries a
  strict content security policy (D-25). The `tarkistus` check runs Biome,
  the TypeScript 7 type check, Vitest, the build, Playwright end-to-end tests
  with axe accessibility checks in light and dark colours, and `npm audit`;
  npm installs run no scripts and take only releases at least 14 days old.
  Dependabot watches `web/`. See `docs/web.md`.
- `GET /v1/public/open-requests` lists, without a key, the requests that
  invite observers: opened or funded and not reserved, with their request
  document, terms and reward split (D-26).
- A local stack in one command for development and end-to-end tests
  (`core/tests/local_stack.py`): a local Anvil chain with the contracts, the
  service, SIMULATED parties with registered wallets and SIMULATED requests.
  Its chain listens on port 8545 by default, where wallets expect chain 31337.
- Signing in with a wallet (phase 3, step 3.2): Sign-In with Ethereum
  (ERC-4361) at `POST /v1/session/challenge` and `POST /v1/session`, a session
  cookie (`HttpOnly`, `SameSite=Strict`, 12 hours) that the rest of the API
  accepts like the party's key, `GET /v1/session` and `DELETE /v1/session`.
  Messages are written by the service for its configured web origins
  (`orbit-watch serve --origin`), work once and expire after five minutes;
  changes made with a session need its `Origin`. A new wallet signs up as a
  requester or a station, and its signed message is kept with the wallet
  (storage migration 0004). The web application gets Sign in and Your account
  pages; wallets are found with EIP-6963, and the page checks every message
  against its own address before the wallet signs (D-27).
- Transactions in the browser (phase 3, step 3.3): the page reads every
  prepared transaction from its call data with the contracts' own ABIs, shows
  what it does in words, and refuses anything but this party's calls to Orbit
  Watch's contracts on the service's chain. The party's wallet sends it, the
  service hears the hash, and the page shows it as pending, confirmed or
  failed with an explorer link. A declined prompt, a wallet on another network
  or account, and a transaction the chain refuses (named from the escrow's
  error) are explained. Your account shows the balance, the credit waiting in
  the escrow with a withdrawal, and the party's transactions (D-28). The local
  stack seeds a settled request, so that a station and the requester have
  credit to withdraw.
- The requester's view (phase 3, step 3.4): Your requests, a form for a new
  request (target from the allow-list, window and deadline in UTC,
  requirements, time limits), and a page per request with its status and
  progress, terms, files to download, payments and chain events. Its
  requester publishes, funds (seeing the deposit and its split first), cancels
  and challenges a passed result there, each signed with the requester's own
  wallet (D-29). `GET /v1/public/targets` gives the allow-list, and
  `GET /v1/requests` also gives each request's requester and title. The local
  stack writes fresh SIMULATED good observations for tests.
- The observer's view (phase 3, step 3.5): Your station, where a station
  registers its profile from a SIMULATED instrument with its own name and
  place (`GET /v1/public/station-templates`, `GET` and
  `PUT /v1/stations/{party}/profile`, storage migration 0005); Your
  observations; reserving funded open requests; and delivering on the
  request's page, with a file of the station's own or SIMULATED observations
  made with its profile (`POST /v1/requests/{id}/simulate`). The page computes
  the file's SHA-256 and the transaction flow checks that the chain records
  exactly that. The parties see why a delivery passed or failed, check by
  check, and an observer may challenge a failed result. A wallet without ETH
  is told to get some from a faucet (D-30).
- The reviewer's view (phase 3, step 3.6): Your review tasks, with the
  reviewer's record (calibration accuracy, votes in real rounds, notes), and a
  page per task with the request, the challenge's reason, the files, the
  automated verification check by check, and the answer. A vote in a real
  round is the reviewer's own EAS attestation, signed in its wallet after the
  page has checked the answer, the reasons' SHA-256 and the delivery in the
  call data; a calibration answer is recorded at once (D-31). The local stack
  seeds a request in review.
- The administrator view and the public pages (phase 3, step 3.7).
  Administration shows every request with its status, delivery, votes and
  payments, the conflicts and failed transactions, every watched transaction
  and the event log, and runs `tick`. It shows the reviewer registry with the
  timelock that owns it, its Safe and the timelock's operations. It prepares
  a reviewer's addition or removal as data for the Safe: a Transaction Builder
  batch file with the builder's checksum, and the data to execute after the
  delay; the service sends nothing and holds no governance key. It also makes
  SIMULATED files with the simulator and the six demo datasets. New
  endpoints: `GET /v1/admin/overview`, `GET /v1/admin/governance`,
  `POST /v1/admin/governance/proposals`, `GET /v1/admin/demo-datasets`,
  `POST /v1/admin/demo-datasets/{name}` and `POST /v1/admin/simulate`. The
  public pages need no sign-in: Attestations (`GET /v1/public/attestations`)
  lists every automated result and vote with EAS Scan links on Base Sepolia,
  and the Station quality meter (`POST /v1/public/quality`) scores an
  observation file without keeping it. The service follows the timelock's
  events with the escrow's and keeps the attestations it has read (storage
  migration 0006); `orbit-watch serve --safe` names the Safe, which
  `--network` takes from the deployment record. The local stack governs like
  Base Sepolia, with a Safe of LOCAL TEST signers and a 60-second timelock,
  and its administrator signs in with a wallet (D-32).
- The phase 3 demo (step 3.8): the whole chain in the browser on Base
  Sepolia, every role with its own wallet, recorded in
  `examples/phase3/transcript.md` with screenshots, every transaction on the
  block explorer and every attestation on EAS Scan. A requester and a
  station sign up, the request is funded, reserved, delivered, verified,
  challenged and settled after two reviewers vote, and the parties withdraw.
  The administrator prepares adding a reviewer, and the Safe schedules the
  downloaded batch file in the timelock. The demo is
  `npm run demo:base-sepolia` in `web/`; its wallet signs with testnet
  keystores in the test runner (D-33).
- An accessibility review of every view (`docs/accessibility.md`): axe in
  light and dark colours, the keyboard alone (every stop reachable and shown,
  no trap, the skip link) and reflow at 320 pixels, for all 17 views, in CI
  (`web/e2e/a11y.spec.ts`).
- The phase 3 summary (`docs/phase-3-summary.md`).

### Changed

- The request document is readable by any party while the request is opened
  or funded, and by the station that reserved it; observations and reports
  still only by the request's parties until publication (D-30).
- `GET /v1/requests` also gives each request's reserving station and observer.
- React 19.3.1 and Vitest 5.0.5 in the web application (Dependabot): the
  versions first picked were not the highest at least 14 days old (D-28).

### Fixed

- Date and time fields showed no focus indicator while one of their parts had
  focus; the whole field is now outlined.
- The end-to-end tests waited for the local stack's health URL or its "Ready"
  line, whichever came first, so they could start before the stack had seeded
  its requests; they now wait for the line (D-30).

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

[unreleased]: https://github.com/Haiko-Innovations/orbit-watch/compare/v0.6.0...HEAD
[0.6.0]: https://github.com/Haiko-Innovations/orbit-watch/compare/v0.5.0...v0.6.0
[0.5.0]: https://github.com/Haiko-Innovations/orbit-watch/compare/v0.4.0...v0.5.0
[0.4.0]: https://github.com/Haiko-Innovations/orbit-watch/compare/v0.3.0...v0.4.0
[0.3.0]: https://github.com/Haiko-Innovations/orbit-watch/compare/v0.2.0...v0.3.0
[0.2.0]: https://github.com/Haiko-Innovations/orbit-watch/compare/v0.1.0...v0.2.0
[0.1.0]: https://github.com/Haiko-Innovations/orbit-watch/releases/tag/v0.1.0

# HTTP API

Since phase 1, step 1.6. Code: [`core/src/orbit_watch/api/`](../core/src/orbit_watch/api).

> **Testnet only, no real value. All bundled data is SIMULATED.** The public
> service runs this API on Vercel, behind HTTPS
> ([deployment.md](deployment.md)). Run by hand, `orbit-watch serve` listens on
> `127.0.0.1` by default and has no TLS of its own.

## Run it

The API is an optional part of the package:

```sh
pip install "orbit-watch[api] @ git+https://github.com/Haiko-Innovations/orbit-watch.git#subdirectory=core"
export ORBIT_WATCH_DATABASE_URL=postgresql://user@localhost/orbit_watch   # a PostgreSQL database
orbit-watch keys create --role admin --party admin:me   # prints the key once
orbit-watch serve                                       # http://127.0.0.1:8000/v1/
```

`--catalog`, `--policy` and `--reviewers` default to the built-in SIMULATED
data. `--web web/dist` also serves the built web application at `/`, on the
API's own origin ([web.md](web.md)), and `--origin` names the addresses
browsers use for it, if not the service's own ([signing in](#signing-in-with-a-wallet)). Every response carries a strict content
security policy ([D-25](decisions.md#d-25-the-web-project)). The service keeps its state, files
included, in PostgreSQL: `--database`, or `ORBIT_WATCH_DATABASE_URL` or
`DATABASE_URL` ([storage.md](storage.md)). Any number of servers can share one
database (step 4.2): each call checks the state against the database first.
`orbit-watch keys create` works while a server runs, for the first admin key;
create the rest through the API.

The service also comes as a container image, built from the `Dockerfile` at
the repository's root, with the web application and no state of its own; see
[Running the image](#running-the-image).

## Keys and roles

Every call except `GET /v1/health` and the public ones needs
`Authorization: Bearer <key>`, or in a browser the session cookie of a party
that [signed in with its wallet](#signing-in-with-a-wallet). A key
belongs to one party and one role
([P-04](decisions.md#p-04-role-scoped-api-keys)); the party's name starts with
its role (`station:SIM-ESPOO`). Keys are stored only as SHA-256 hashes and are
shown once.

| Role | Can |
|---|---|
| `requester` | create, open, fund and cancel its requests; challenge a result |
| `station` | reserve, deliver observation files, challenge a result. **Never moves points.** |
| `reviewer` | list its review tasks and answer them |
| `admin` | grant points, create keys, apply deadlines (`tick`), read any profile or balance |

## Idempotency

Every change (a `POST`, and a `PUT` or `DELETE` of a station profile) needs an
`Idempotency-Key` header (1–128 characters), scoped to the caller's party. The
first successful response is stored in the same database transaction as the
change. Sending the same call again with the same key returns that response
with `Idempotent-Replayed: true` and changes nothing. Using the key for a
different call returns `409 key_reused`. Refused calls change nothing and are
not stored, so a key can be reused after a refusal. A key is remembered for
24 hours ([step 4.4](#personal-data)); after that, the same key makes a new
call.

## Endpoints

| Method and path | Role | Body | Does |
|---|---|---|---|
| `GET /v1/health` | none | | version and status; `read_only` is `true` in [read-only mode](#read-only-mode-and-backups) |
| `GET /v1/health/follower` | none | | when the follower last ran: `200` with `"status": "ok"`, or `503` with `"behind"` (longer ago than 30 minutes) or `"never"`; on a chain also the last block followed ([the follower](#the-follower)) |
| `GET /v1/health/reference-orbits` | none | | whether the follower fetches reference orbits: `503` with `"status": "stopped"` when it has stopped asking a source and waits for a person, `200` with `"ok"`, or `"off"` when the service does not fetch; per source the time, object, HTTP status and reason of a stop, and the objects without public data ([fetching reference orbits](#fetching-reference-orbits)) |
| `GET`, `POST /v1/internal/follow` | the follower's secret | | run the follower once: `{changed, sent, followed_at}`, on a chain also `synced_block`; `404` when the service has no follower secret |
| `GET /v1/internal/backup` | the backup token | | an encrypted backup of the database, streamed ([backups](#read-only-mode-and-backups)); `404` when the service has no backup token |
| `GET /v1/requests` | any | | all requests with requester, title, reserving station, observer, status, outcome and `labels` |
| `POST /v1/requests` | requester | `{"request": <request document>, "terms": {…}}` | create a request in draft; `terms` may set `delivery_deadline`, `reservation_hours`, `challenge_period_hours`, `review_hours`, `verification_timeout_hours`, `embargo_days`; a target not on the allow-list is refused with `target_not_allowed` ([D-49](decisions.md#d-49-real-objects-on-the-allow-list)), a real request for a SIMULATED object with `simulated_target`, and a replay request with `replay_admin_only` (403: an administrator creates replays); a request for a real object may be SIMULATED, for simulated stations to observe it ([D-50](decisions.md#d-50-simulated-stations-on-real-objects)) |
| `GET /v1/requests/{id}` | any | | summary, with its `labels`, and full lifecycle record; the reasons people wrote (`challenge_reason`, `vote_reasons`) only for the request's parties and administrators, or once it is published, and otherwise `"reasons_hidden": true` |
| `POST /v1/requests/{id}/open` | requester | | publish; freezes the terms |
| `POST /v1/requests/{id}/fund` | requester | `{"observer": 100, "reviewer": 10, "platform_fee": 0}` | lock the reward split and deposit the points |
| `POST /v1/requests/{id}/cancel` | requester | | cancel before a reservation |
| `POST /v1/requests/{id}/reserve` | station | | reserve the request |
| `POST /v1/requests/{id}/deliveries?format=json\|iod\|tdm` | station | the observation file as is | deliver and verify at once; an optional `Content-SHA256` header must match the body. The station's profile is its place: a JSON file must name it (`wrong_place`), and an IOD or TDM file is verified at it, with a sites document published as the request's `station_place` file; `serve` needs a profile (`profile_required`, 409); a replay is exempt ([D-55](decisions.md#d-55-the-profile-is-the-stations-place-for-every-format)) |
| `POST /v1/requests/{id}/challenge` | requester, station | `{"reason": "…"}` | challenge the automated result |
| `GET /v1/requests/{id}/report` | the request's parties, admin; anyone once published | | the automated verification report |
| `GET /v1/files/{sha256}` | the file's request parties (or calibration reviewer), admin; anyone once published | | a stored file |
| `GET /v1/tasks` | reviewer | | the reviewer's open tasks (real and calibration alike) |
| `POST /v1/tasks/{task_id}/review` | reviewer | `{"approve": true, "reason": "…"}` | answer a task |
| `GET /v1/reviewers/{party}/profile` | that reviewer, admin | | accuracy profile |
| `GET /v1/balances/{party}` | that party, admin | | points held |
| `POST /v1/admin/grants` | admin | `{"party": "…", "points": 1000}` | give points (phase 1 budgets) |
| `POST /v1/admin/keys` | admin | `{"party": "…", "role": "…"}` | create a key; shown once (a replay returns `"key": null`) |
| `POST /v1/admin/tick` | admin | | apply passed deadlines and settle finished requests |
| `POST /v1/admin/reference-orbits/resume` | admin | `{"source": "celestrak"}` or `"satchecker"`, optionally `"ask_again": [norad_id, …]` | let the follower ask the source again once a person has looked at why it stopped; a wait after a `500` or a `503` still holds; `ask_again` forgets what the source answered for these objects, a `404` included ([D-48](decisions.md#d-48-the-follower-fetches-reference-orbits)) |
| `POST /v1/admin/allowlist` | admin | `{"norad_id": 12345, "name": "…", "reason": "…", "operator_source": "SpaceX-E"}` | add a real object to the allow-list after checking its owner in the satellite catalogue; the reason is public; `operator_source`, optional and only `SpaceX-E`, says that one SupGP query showed its operator's orbit, for a Starlink object ([D-62](decisions.md#d-62-objects-whose-operators-publish-their-orbits-on-the-allow-list)), otherwise `invalid_operator_source`; refused for a name that matches the patterns, its own or one a group or source gives it (`excluded_name`), an object of an excluded group (`excluded_group`), a SIMULATED object, or one on the service's own list (`already_allowed`); answers the object as `GET /v1/public/targets` lists it ([D-49](decisions.md#d-49-real-objects-on-the-allow-list)) |
| `POST /v1/admin/replays` | admin | `{"requester": "requester:…", "request": <request document, format 1.1>, "terms": {…}}` | create a replay request in draft for a requester, who publishes and funds it as usual; its window must have ended and its delivery deadline must be in the future (`replay_window_not_past`, `invalid_request`); only its replay station reserves and delivers it, and only the file it names (`replay_station_only` 403, `not_the_replayed_file`), once the service keeps a reference orbit within 7 days of the window (`reference_orbit_pending` 409) ([D-51](decisions.md#d-51-replays)) |
| `POST /v1/admin/allowlist/remove` | admin | `{"norad_id": 12345}` | take back an addition: `{"norad_id", "allowed"}`, where `allowed` is true when CelesTrak's groups still hold the object |
| `POST /v1/admin/element-sets` | admin | an `orbit-watch/gp-catalog` document, or CelesTrak's OMM JSON or CSV | upload real element sets by hand; kept labelled as uploaded, a SIMULATED catalogue or object refused ([D-47](decisions.md#d-47-reference-orbits-in-the-service)) |
| `GET /v1/admin/overview` | admin | | every request with status, observer, automated result, votes, outcome and payments; counts by status; on a chain also the chain's state, conflicts, watched transactions and the latest 200 escrow events, newest first ([D-32](decisions.md#d-32-the-administrator-view-and-the-public-pages)) |
| `GET /v1/admin/governance` | admin | | on a chain: the reviewer registry and its reviewers, the timelock that owns it, the Safe that proposes, and the timelock's operations with their state and, while not done, the data to execute them |
| `POST /v1/admin/governance/proposals` | admin | `{"action": "add"\|"remove", "reviewer": "0x…" or a party}` | the data for the Safe to schedule the change through the timelock, a Safe Transaction Builder batch file, and the data to execute it after the delay; sends and keeps nothing |
| `GET /v1/admin/demo-datasets` | admin | | the six SIMULATED demo datasets with their expected results |
| `POST /v1/admin/demo-datasets/{name}` | admin | | one demo dataset, made afresh: `{file_name, format, observations, sha256, expected_verdict, expected_failures, simulated}` |
| `POST /v1/admin/simulate` | admin | `{"profile": "sim-cmos-gps", "norad_id": 339001, "start": "…", "end": "…", "max_passes": 2}` | SIMULATED observations by a built-in station profile of an allowed target, in a window of at most three days; a real object along its stored element set nearest the middle of the window, refused with `no_reference_orbit` (409) without one within 7 days ([D-50](decisions.md#d-50-simulated-stations-on-real-objects)); changes nothing |
| `GET /v1/public/station-templates` | none | | the built-in SIMULATED station profiles, as starting points ([D-30](decisions.md#d-30-the-observers-view)) |
| `GET /v1/stations/{party}/profile` | that station, admin | | the station's profile: `{party, profile, updated_at, place, place_chosen}`, where `place` is `exact` or `kilometre`, and `place_chosen` is false for a profile saved before the choice existed, kept to about a kilometre ([D-54](decisions.md#d-54-the-observer-chooses-how-precisely-the-place-is-published)) |
| `PUT /v1/stations/{party}/profile` | that station | `{"profile": <station profile>, "place": "exact" or "kilometre"}` | register or replace the profile; its station ID is the party's own name; `place` is the observer's choice of how precisely its place is kept and published, with nothing chosen in advance (`place_required` without it), and `kilometre` keeps the coordinates to two decimals ([personal data](#personal-data)) |
| `DELETE /v1/stations/{party}/profile` | that station, admin | | delete the profile: `{"party", "deleted": true}`, or `false` if there was none |
| `GET /v1/requests/{id}/passes` | a station with a profile, for a request that is open, funded or reserved by it | | the object's passes over the station's place in the window (at most its first week, `window_cut`), above the instrument's elevation limit: each with `rise`, `culmination`, `set`, `max_elevation_deg` and its visible part, `visible`, `visible_start`, `visible_peak`, `visible_end`, `visible_max_elevation_deg`, lit by the Sun under a dark sky (`dark_sky_deg`, −6°); `no_profile`, `no_reference_orbit` ([D-58](decisions.md#d-58-a-stations-visible-passes-for-a-request)) |
| `POST /v1/requests/{id}/simulate` | the station that reserved it, with a profile | | SIMULATED observations of the request's target in its window, made with the station's profile: `{file_name, format, observations, sha256, simulated}`; only for a SIMULATED request (`real_request`, 409, otherwise); a real object along its stored element set nearest the window, `no_reference_orbit` (409) until the follower has fetched one ([D-50](decisions.md#d-50-simulated-stations-on-real-objects)); changes nothing |
| `GET /v1/public/targets` | none | | the allow-list: the objects requests may target ([D-29](decisions.md#d-29-the-requesters-view), [D-49](decisions.md#d-49-real-objects-on-the-allow-list)). Each has `norad_id`, `name`, `simulated` and `source`: `service` (the service's own list), `celestrak` with its `groups`, or `administrator` with its `reason` and `added_at`; an object whose operator publishes its orbit also has `operator_orbits`, the SupGP sources with it ([D-62](decisions.md#d-62-objects-whose-operators-publish-their-orbits-on-the-allow-list)). `simulated` is true when every target is; `groups` says when each of CelesTrak's groups and SupGP sources was last fetched, how many objects it held, and its `data`, `gp` or `supgp` |
| `GET /v1/public/reference-orbits` | none | | the real element sets the service keeps, by name only: object, epoch, source and SHA-256, never the elements (`?norad_id=` for one object; [P5-05](decisions.md#p5-05-orbit-data-stays-out-of-the-repository)) |
| `GET /v1/public/open-requests` | none | | requests that invite observers: opened or funded, not reserved, with their request document, `labels`, terms and reward split ([D-26](decisions.md#d-26-open-requests-are-public)) |
| `GET /v1/public/requests` | none | | published requests ([data-publication.md](data-publication.md)) |
| `GET /v1/public/requests/{id}` | none | | one published request |
| `GET /v1/public/files/{sha256}` | none | | a published file, with its licence in a `Link` header |
| `POST /v1/public/quality?format=json\|iod\|tdm` | none | an observation file of one station, at most 2 MiB | the station quality report ([quality-meter.md](quality-meter.md)); the file is not kept |
| `GET /v1/public/attestations` | none | | on a chain: the EAS attestations of the requests the service follows (automated results and votes), newest first, with explorer and EAS Scan links on Base Sepolia |

Deadlines move on and finished requests are settled by [the
follower](#the-follower), or when an admin calls `tick`. Calls on a request
already take its passed deadlines into account: for example, a delivery after
the reservation lapsed is refused.


### Labels

A request's `labels` say what each of its parts is, by its source
([P5-09](decisions.md#p5-09-real-and-simulated-side-by-side),
[D-52](decisions.md#d-52-labels-by-source-on-every-page)):

```json
{
  "request_simulated": true,
  "object": {"norad_id": 99015, "name": "…", "simulated": false, "source": "celestrak", "groups": ["science"], "on_list": true},
  "reference_orbit": {"source": "celestrak", "source_name": "CelesTrak", "simulated": false, "epoch": "…", "element_set_sha256": "…", "final": true},
  "observations": {"kind": "simulated", "station": "station:…", "sha256": "…"},
  "replay": null
}
```

`object.source` is `service`, `celestrak` or `administrator` (with `reason` and
`added_at`), as in `GET /v1/public/targets`; `on_list` is false for an object that has
left the list. `reference_orbit.source` is `celestrak`, `satchecker`, `uploaded` or
`service` (the service's own catalogue). It is the set the report named once there is a
report (`final`), and before that the stored set nearest the window, or `null` if there is
none yet. `observations` is `null` until a delivery, and its `kind` is `simulated`,
`replayed` or `station`. `replay` is a replay's block from its request document (D-51).

## The follower

Step 4.2, [P4-06](decisions.md#p4-06-the-service-runs-on-its-own) and
[D-35](decisions.md#d-35-the-stateless-service-the-follower-and-the-image).
The follower does the service's own work, so that nobody has to call `tick`:
it applies passed deadlines and, on a chain, the escrow's new events; it
attests automated results and settles the requests whose outcome is reached.
Any number of followers can run against one database: they take turns, so a
change is made once.

- **A schedule** calls `GET` or `POST /v1/internal/follow` with
  `Authorization: Bearer <secret>`. The secret comes from
  `ORBIT_WATCH_FOLLOW_SECRET`, or from `CRON_SECRET`, which Vercel's cron jobs
  send. Without either, the route answers `404`.
- **A timer**, such as a systemd timer or cron with `curl`, calls the same
  route.
- **`orbit-watch serve --follow SECONDS`** runs it in a thread of the server,
  for a server of our own. A failed run is logged and the next one tries again.

`GET /v1/health/follower` is for monitoring: it answers `503` when no follower
has run in the last 30 minutes (twice the planned 15-minute schedule) or ever,
whichever process ran it.

### Fetching reference orbits

Step 5.4, [D-48](decisions.md#d-48-the-follower-fetches-reference-orbits). With
`orbit-watch serve --fetch-orbits`, or `ORBIT_WATCH_FETCH_ORBITS=1`, each run of the
follower also fetches the element sets that open requests for real objects need, after
its other work: CelesTrak's current sets while a request's window has not ended, and
SatChecker's set nearest the middle of a window that has ended. It makes at most three
requests per run, two seconds apart, outside the database's lock. Its answer lists them
under `reference_orbits`, each with the sets kept, or why it stopped. With the requests
left over, it fetches CelesTrak's groups and SupGP sources for the allow-list, each at
most once a day, the excluded groups first
([D-49](decisions.md#d-49-real-objects-on-the-allow-list),
[D-62](decisions.md#d-62-objects-whose-operators-publish-their-orbits-on-the-allow-list));
an entry for a group or source names it and says how many objects it held.

The first answer that is not 200 with the object's element sets, or no answer, stops that
source until an administrator resumes it (`POST /v1/admin/reference-orbits/resume`).
`GET /v1/health/reference-orbits` answers `503` meanwhile, for the uptime check.
[operations.md](operations.md#fetching-reference-orbits-stopped) says what to do.

## Read-only mode and backups

Step 4.6, [D-39](decisions.md#d-39-backups-monitoring-and-read-only-mode); how
they are used is in [operations.md](operations.md).

- **Read-only mode** (`orbit-watch serve --read-only`, or
  `ORBIT_WATCH_READ_ONLY=1`) refuses every change with `503 read_only`, and the
  follower waits. Reading, the public pages, the quality meter and signing in
  still work, and reads show the chain as it was last followed.
  `GET /v1/health` says `"read_only": true`, and the web application says so on
  every page.
- **Backups.** With `ORBIT_WATCH_BACKUP_TOKEN` and the age public key that
  backups are encrypted to (`--backup-recipient`, or
  `ORBIT_WATCH_BACKUP_RECIPIENT`), a schedule calls
  `GET /v1/internal/backup` with `Authorization: Bearer <token>`. The answer is
  the backup, encrypted before it leaves the service and streamed, so it may be
  larger than a function's response limit. `orbit-watch backup create` takes
  the same backup straight from the database, and `orbit-watch backup restore`
  restores one into an empty database.

## Running the image

The `Dockerfile` at the repository's root builds the service with the web
application, from base images pinned by digest. It runs as an ordinary user and
needs no writable file system but `/tmp`. Everything it keeps is in the
database, so any number of containers can share one. CI builds it on every pull
request and runs the end-to-end tests against it.

```sh
docker build --tag orbit-watch .
docker run --read-only --tmpfs /tmp --publish 127.0.0.1:8000:8000 \
  --env ORBIT_WATCH_DATABASE_URL --env ORBIT_WATCH_FOLLOW_SECRET \
  orbit-watch --follow 300
```

The image runs `orbit-watch serve --host 0.0.0.0 --port $PORT --web /app/web`
(`PORT` is 8000 unless the platform sets it), and adds the arguments given to
`docker run`; a later option wins. On Base Sepolia, mount the verifier's
keystore and its password file read-only and add
`--network base-sepolia --verifier-keystore … --verifier-password-file …`,
with the dedicated RPC endpoint in `ORBIT_WATCH_CHAIN_RPC`
([chain-service.md](chain-service.md#running-the-server-on-a-chain)). Behind a
proxy, name its client address header (`ORBIT_WATCH_CLIENT_IP_HEADER`) for
the [limits](#limits-against-abuse). Station coordinates are kept to two
decimals (`ORBIT_WATCH_STATION_DECIMALS`), and the service writes no access log
([personal data](#personal-data)).

Any ASGI server can run the service without the command line:
`uvicorn orbit_watch.asgi:app` sets it up from the environment, with
`ORBIT_WATCH_NETWORK` and `ORBIT_WATCH_ORIGINS` for `serve`'s `--network` and
`--origin`, the verifier key in `ORBIT_WATCH_VERIFIER_KEY`, the role that every
transaction runs as in `ORBIT_WATCH_DATABASE_ROLE`, and libpq's TLS mode in
`ORBIT_WATCH_DATABASE_SSLMODE`. Without a database it answers every call
`503 not_configured`. This is how the public service runs on Vercel
([deployment.md](deployment.md)).

## On a testnet chain

Phase 2, step 2.6. Started with `--network base-sepolia` and
`--verifier-keystore` (the deployment in [base-sepolia.md](base-sepolia.md),
step 2.7), or with `--chain-rpc`, `--escrow` and `--verifier-keystore` for
another escrow, the server settles funded requests on the escrow contract: see
[chain-service.md](chain-service.md). **The API never sees a party's key.** The calls above stay the same, with three differences:

- For a funded request (and for funding), `fund`, `cancel`, `reserve`,
  `deliveries`, `challenge` and the answer to a real review task return
  **`202 Accepted`** with the transactions the party signs and sends with its
  own wallet, in order:

  ```json
  {"request_id": "SIM-REQ-0001", "action": "fund",
   "sign": [{"action": "approve", "transaction": {"chainId": 84532, "from": "0x…", "to": "0x…", "data": "0x…", "value": 0}},
            {"action": "fund", "transaction": {"…": "…"}}],
   "notice": "Base Sepolia testnet, no real value", "next": "…"}
  ```

  Nothing changes until the chain confirms them; the party reports each hash.
- Every call first applies the escrow's new events, and a request's view has
  a `chain` part: whether it is on chain, its status there, the events applied
  with their explorer links, its pending and failed transactions, conflicts,
  the token and the notice. The clock is the latest block's time.
- Points are not used: `POST /v1/admin/grants` is refused
  (`points_not_used`), and `GET /v1/balances/{party}` gives the wallet's
  `address`, its token `balance` and what it can withdraw (`withdrawable`).
  `tick` also does the service's own part on chain and lists what it `sent`.

| Method and path | Role | Body | Does |
|---|---|---|---|
| `GET /v1/chain` | none | | the network, escrow, reviewer registry, token (symbol, decimals), EAS schemas, verifier, explorer, notice and the last block read |
| `POST /v1/session/challenge` | none, from a web origin | `{"address": "0x…"}`, or with `"sign_up": {"party": "station:NAME"}` | a Sign-In with Ethereum message to sign ([signing in](#signing-in-with-a-wallet)) |
| `POST /v1/session` | none, from a web origin | `{"message": "…", "signature": "0x…"}` | sign in: sets the session cookie |
| `GET /v1/session` | the session cookie | | the signed-in party, or `null` |
| `DELETE /v1/session` | the session cookie, from its origin | | sign out |
| `DELETE /v1/sessions` | the session cookie, from its origin | | sign out everywhere: ends every session of the signed-in party, `{"party", "ended": n}` |
| `GET /v1/wallet` | any | | your party, its wallet and the message to sign to register one |
| `POST /v1/wallet` | any | `{"address": "0x…", "signature": "0x…"}` | register your wallet (EIP-191 signature of the message) |
| `POST /v1/wallet/withdraw` | any | | `202`: the `withdraw` transaction to sign |
| `POST /v1/transactions` | any | `{"tx_hash": "0x…"}` | report a transaction you sent; the service waits for it, applies it and does its own part; returns the transaction and the request |
| `GET /v1/transactions?request=ID` | any (admin: all) | | your transactions: `pending`, `confirmed` or `failed`, with explorer links |

### Transactions someone else sent for your wallet

A smart account sends its transactions through a relayer, which pays the
fee. Examples are MetaMask's EIP-7702 smart account and ERC-4337 wallets.
The transaction's `from` is then the relayer, and its `to` is the relayer's
contract or the wallet itself, not Orbit Watch's contracts.

The service accepts such a transaction once it is mined, if what the escrow
or the token recorded names your wallet as the one who acted. Each of these
fields is the contract call's `msg.sender`, or for a vote, the attester:

| Event | Field | Action |
|---|---|---|
| escrow `Funded` | `requester` | `fund` |
| escrow `Reserved` | `station` | `reserve` |
| escrow `Delivered` | `station` | `deliver` |
| escrow `Challenged` | `challenger` | `challenge` |
| escrow `Voted` | `reviewer` | `attest_vote` |
| escrow `Withdrawn` | `party` | `withdraw` |
| escrow `Cancelled` | the request's `requester` | `cancel` |
| token `Approval` of the escrow | `owner` | `approve` |

Anything else is `not_your_transaction`, as is a failed transaction, which
changes nothing for anyone. A transaction that carries the actions of several
parties, such as an ERC-4337 bundle, is listed under the party that reports it
first. The service applies the escrow's events for every party either way. If the transaction is still pending after the
service has waited, the answer is `transaction_pending`; report it again once
it is mined.

## Signing in with a wallet

Phase 3, step 3.2 ([D-27](decisions.md#d-27-signing-in-with-a-wallet)). A
browser signs in instead of holding an API key:

1. `POST /v1/session/challenge` with the wallet's address, from one of the
   service's web origins (`orbit-watch serve --origin`, by default the
   service's own address). The service writes a Sign-In with Ethereum message
   (ERC-4361) for that origin and address, valid for five minutes and usable
   once. A wallet that is no party's yet gets `unknown_wallet`; it can sign up
   as `requester:<name>` or `station:<name>` with `sign_up`.
2. The wallet signs the message (`personal_sign`).
3. `POST /v1/session` with the message and signature sets the cookie
   `__Host-ow_session` over HTTPS, or `ow_session` over plain http
   (`HttpOnly`, `SameSite=Strict`), for 12 hours, and ends the session the
   browser had before. A session signed in over HTTPS counts only under the
   prefixed name ([security-review.md](security-review.md)). With it, the
   rest of the API works as with the party's own key. A change also needs the
   `Origin` it was signed in on.

Signing out deletes the session; `DELETE /v1/sessions` deletes every session of
the party, in every browser. Ended and expired sessions, and sign-in messages an
hour after they expire, are deleted by the follower and by every new sign-in
([personal data](#personal-data)).

Refusals: `forbidden_origin` and `wrong_origin` (403), `unknown_message`,
`message_used`, `message_expired` and `bad_signature` (422), `unknown_wallet`
(404), `party_taken` and `address_taken` (409), `invalid_party` (422). Only a
service on a chain has wallets (`not_on_chain` otherwise).

## Limits against abuse

Step 4.3, [P4-08](decisions.md#p4-08-limits-against-abuse) and
[D-36](decisions.md#d-36-limits-the-body-limit-and-the-dedicated-rpc-endpoint).
The service counts, in its database, the calls that cost the most, and every
call of the public pages, per IP address and, with a key or a session, per
party. So the limits hold without a firewall in front
([P4-05](decisions.md#p4-05-portable-by-design)); health checks are not
limited. A call over a limit gets
`429 rate_limited` with `Retry-After` (seconds) before it does anything. A
refused call is not counted. Any other call is counted even if it then fails:
failed sign-ins are what the limit is for.

| Limit | Calls | Per IP address | Per party |
|---|---|---|---|
| `sign_in` | `POST /v1/session/challenge`, `POST /v1/session` | 30 per 600 s | |
| `sign_up` | a challenge that signs up a new party | 10 per 3600 s | |
| `new_request` | `POST /v1/requests` | 60 per 3600 s | 20 per 3600 s |
| `upload` | `POST /v1/requests/{id}/deliveries` | 60 per 3600 s | 20 per 3600 s |
| `quality` | `POST /v1/public/quality` | 30 per 3600 s | |
| `public` | every `GET /v1/public/…` and `GET /v1/chain`: the pages anyone may read without a key | 600 per 600 s | |

- **Windows are fixed** and start at whole multiples of their length (an hour
  starts on the hour). Across the end of one window and the start of the next,
  a caller can make up to twice the limit.
- **An IP address is never stored.** The service keeps a SHA-256 of it, keyed
  with a random key of the database, and deletes every count when its window
  is over. IPv6 addresses count per /64 network, which one host or home usually
  has to itself.
- **Which address is the caller's:** the connection's own, or behind a proxy
  you trust, the header it sets (`--client-ip-header`, or
  `ORBIT_WATCH_CLIENT_IP_HEADER`; `x-real-ip` on Vercel). Of a list, the last
  entry counts, the one the nearest proxy added. Never name a header that
  callers can set themselves.
- **The limits are settings:** `orbit-watch serve` applies the defaults above.
  `--limits` (or `ORBIT_WATCH_LIMITS`) takes `off`, or a JSON object that
  changes some of them: `{"quality": {"ip": [60, 3600]}, "upload": {"party":
  null}}` (`[calls, seconds]`, or `null` for none). The local stack runs
  without limits, since every test calls from 127.0.0.1.
- **Every body is at most 4,000,000 bytes**, under Vercel's 4.5 MB: refused
  with `413 too_large` by its `Content-Length`, or while it arrives. The quality
  meter takes at most 2 MiB, and sign-in calls at most 64 KiB.
- **In front of the service**, Vercel's firewall limits requests per IP
  address on every path (step 4.5).

## Personal data

Phase 4, step 4.4 ([D-37](decisions.md#d-37-personal-data-in-the-service)). The
inventory of every table and log is [personal-data.md](personal-data.md), and
the web application shows the [privacy notice](legal/privacy-notice.md) and the
[terms of use](legal/terms-of-use.md).

- **Station coordinates exactly or to about a kilometre.** The observer chooses
  when saving the profile ([D-54](decisions.md#d-54-the-observer-chooses-how-precisely-the-place-is-published)).
  With `kilometre`, the profile's latitude and longitude are kept to two decimals of
  a degree; with `exact`, as given. The profile is then the station's place for every
  delivery ([D-55](decisions.md#d-55-the-profile-is-the-stations-place-for-every-format)):
  an Orbit Watch JSON file from another place is refused with `422 wrong_place`, and an
  IOD or CCSDS TDM file is verified at the profile's place, which is published with it.
  A file is kept as delivered, since its SHA-256 is what the chain names. `--station-decimals N` (or
  `ORBIT_WATCH_STATION_DECIMALS`) sets another precision of "about a kilometre",
  and `off` lets a station without a profile deliver, its IOD and TDM files placed
  by the service's own sites file. `create_app` does the same unless
  `station_decimals` is given.
- **Deleting.** A station deletes its profile with
  `DELETE /v1/stations/{party}/profile`, which also deletes the copies of its
  answers that the idempotency records keep. A party ends its sessions with
  `DELETE /v1/session`, or all of them with `DELETE /v1/sessions`.
- **Retention.** The follower, and every sign-in, delete ended and expired
  sessions, sign-in messages an hour after they expire, the limits' counts
  whose window has passed, and idempotency records older than 24 hours.
- **No IP address in the service's logs.** `orbit-watch serve` writes no access
  log unless `--access-log` is given.

## Errors

Errors are JSON: `{"error": {"code": "…", "message": "…"}}`. The codes are
stable; the HTTP status follows from the code:

| Status | Codes (examples) |
|---|---|
| 401 | `unauthorized` |
| 403 | `forbidden_role`, `not_requester`, `not_a_party`, `not_your_task`, `not_yourself`, `not_your_transaction` |
| 404 | `unknown_request`, `unknown_task`, `no_report`, `unknown_file`, `unknown_transaction`, `not_on_chain` |
| 409 | `forbidden_in_status`, `already_voted`, `duplicate_request`, `key_reused`; on a chain `no_wallet`, `wallet_already_set`, `address_taken`, `already_on_chain`, `insufficient_balance`, `nothing_to_withdraw`, `points_not_used`, `sign_on_chain`, `transaction_pending` |
| 413 | `too_large` (bodies over 4,000,000 bytes, [step 4.3](#limits-against-abuse)) |
| 422 | everything else, for example `invalid_body`, `idempotency_key_required`, `hash_mismatch`, `reason_required`, `insufficient_points`, `not_enough_reviewers`, `wrong_place` ([personal data](#personal-data)) |
| 429 | `rate_limited`, with `Retry-After` in seconds ([limits](#limits-against-abuse)) |
| 503 | `verification_unavailable`, `chain_unavailable`, `read_only` ([read-only mode](#read-only-mode-and-backups)) |

## Command-line client

Phase 1, step 1.7. The `orbit-watch` command is also a client for the API
(standard library only, no extra dependencies). The address and key come from
`--api` and `--key`, or better from the environment, which keeps keys out of
the shell history:

```sh
export ORBIT_WATCH_API=http://127.0.0.1:8000
export ORBIT_WATCH_KEY=$(cat requester.key)
```

| Role | Commands |
|---|---|
| requester | `request create FILE [--delivery-deadline …] [--embargo-days N]`, `request open ID`, `request fund ID --observer N --reviewer N [--platform-fee N]`, `request cancel ID` |
| station | `reserve ID`, `submit MANIFEST` (or `submit FILE --request ID`) |
| requester, station | `challenge ID --reason TEXT` |
| reviewer | `review list`, `review answer TASK --approve\|--reject --reason TEXT`, `review profile REVIEWER` |
| admin | `admin grant PARTY POINTS`, `admin key PARTY ROLE [-o FILE]`, `admin tick` |
| anyone with a key | `request list`, `request show ID`, `request report ID [-o FILE]`, `balance PARTY` |
| anyone, no key | `public list`, `public get ID [--download DIR]` |
| on a testnet chain | `chain`, `wallet register [--print-message \| --address A --signature S]`, `wallet withdraw`, `tx list [--request ID]`, `tx report HASH` |

On a testnet chain, the commands sign with your own encrypted keystore
(`--keystore`, `--password-file`, `--rpc`; on Base Sepolia `--rpc` defaults
to Base's public endpoint) or print the transactions for another wallet
(`--unsigned`); see
[chain-service.md](chain-service.md#the-command-line).

Every command takes `--json` to print the API's answer as is. Changes print
their idempotency key; running the same command again with
`--idempotency-key KEY` is safe and reports that nothing changed. `submit`
checks the delivery manifest's hash before sending and sends it as
`Content-SHA256`. `admin key -o FILE` writes the new key to a file readable
only by you. The client warns when it would send a key over plain HTTP to a
host other than this machine.

A whole request from the command line (all data SIMULATED):

```sh
orbit-watch request create examples/simulated/request.json         # requester
orbit-watch request open SIM-REQ-0001
orbit-watch request fund SIM-REQ-0001 --observer 100 --reviewer 10
orbit-watch reserve SIM-REQ-0001                                    # station
orbit-watch submit examples/simulated/datasets/acceptable/delivery.json
orbit-watch request show SIM-REQ-0001                               # anyone
orbit-watch admin tick                                              # after the challenge period
```

## Example with curl

```sh
H="Authorization: Bearer $REQUESTER_KEY"
curl -s -X POST -H "$H" -H "Idempotency-Key: create-1" \
  -d "{\"request\": $(cat request.json)}" http://127.0.0.1:8000/v1/requests
curl -s -X POST -H "Authorization: Bearer $STATION_KEY" -H "Idempotency-Key: deliver-1" \
  --data-binary @observations.json \
  "http://127.0.0.1:8000/v1/requests/SIM-REQ-0001/deliveries?format=json"
```


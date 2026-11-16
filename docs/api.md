# HTTP API (phase 1 prototype)

Phase 1, step 1.6. Code: [`core/src/orbit_watch/api/`](../core/src/orbit_watch/api).

> **Local use only.** Phase 1 has no public deployment
> ([P-03](decisions.md#p-03-no-public-deployment-in-phase-1)): the server
> listens on `127.0.0.1` by default and has no TLS. All bundled data is
> SIMULATED.

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
| `GET /v1/health` | none | | version and status |
| `GET /v1/health/follower` | none | | when the follower last ran: `200` with `"status": "ok"`, or `503` with `"behind"` (longer ago than 30 minutes) or `"never"`; on a chain also the last block followed ([the follower](#the-follower)) |
| `GET`, `POST /v1/internal/follow` | the follower's secret | | run the follower once: `{changed, sent, followed_at}`, on a chain also `synced_block`; `404` when the service has no follower secret |
| `GET /v1/requests` | any | | all requests with requester, title, reserving station, observer, status and outcome |
| `POST /v1/requests` | requester | `{"request": <request document>, "terms": {…}}` | create a request in draft; `terms` may set `delivery_deadline`, `reservation_hours`, `challenge_period_hours`, `review_hours`, `verification_timeout_hours`, `embargo_days` |
| `GET /v1/requests/{id}` | any | | summary and full lifecycle record |
| `POST /v1/requests/{id}/open` | requester | | publish; freezes the terms |
| `POST /v1/requests/{id}/fund` | requester | `{"observer": 100, "reviewer": 10, "platform_fee": 0}` | lock the reward split and deposit the points |
| `POST /v1/requests/{id}/cancel` | requester | | cancel before a reservation |
| `POST /v1/requests/{id}/reserve` | station | | reserve the request |
| `POST /v1/requests/{id}/deliveries?format=json\|iod\|tdm` | station | the observation file as is | deliver and verify at once; an optional `Content-SHA256` header must match the body |
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
| `GET /v1/admin/overview` | admin | | every request with status, observer, automated result, votes, outcome and payments; counts by status; on a chain also the chain's state, conflicts, watched transactions and the latest 200 escrow events, newest first ([D-32](decisions.md#d-32-the-administrator-view-and-the-public-pages)) |
| `GET /v1/admin/governance` | admin | | on a chain: the reviewer registry and its reviewers, the timelock that owns it, the Safe that proposes, and the timelock's operations with their state and, while not done, the data to execute them |
| `POST /v1/admin/governance/proposals` | admin | `{"action": "add"\|"remove", "reviewer": "0x…" or a party}` | the data for the Safe to schedule the change through the timelock, a Safe Transaction Builder batch file, and the data to execute it after the delay; sends and keeps nothing |
| `GET /v1/admin/demo-datasets` | admin | | the six SIMULATED demo datasets with their expected results |
| `POST /v1/admin/demo-datasets/{name}` | admin | | one demo dataset, made afresh: `{file_name, format, observations, sha256, expected_verdict, expected_failures, simulated}` |
| `POST /v1/admin/simulate` | admin | `{"profile": "sim-cmos-gps", "norad_id": 339001, "start": "…", "end": "…", "max_passes": 2}` | SIMULATED observations by a built-in station profile of an allowed target, in a window of at most three days; changes nothing |
| `GET /v1/public/station-templates` | none | | the built-in SIMULATED station profiles, as starting points ([D-30](decisions.md#d-30-the-observers-view)) |
| `GET /v1/stations/{party}/profile` | that station, admin | | the station's profile |
| `PUT /v1/stations/{party}/profile` | that station | `{"profile": <station profile>}` | register or replace the profile; its station ID is the party's own name; `serve` keeps its coordinates to two decimals ([personal data](#personal-data)) |
| `DELETE /v1/stations/{party}/profile` | that station, admin | | delete the profile: `{"party", "deleted": true}`, or `false` if there was none |
| `POST /v1/requests/{id}/simulate` | the station that reserved it, with a profile | | SIMULATED observations of the request's target in its window, made with the station's profile: `{file_name, format, observations, sha256, simulated}`; changes nothing |
| `GET /v1/public/targets` | none | | the allow-list: the objects requests may target, with names ([D-29](decisions.md#d-29-the-requesters-view)) |
| `GET /v1/public/open-requests` | none | | requests that invite observers: opened or funded, not reserved, with their request document, terms and reward split ([D-26](decisions.md#d-26-open-requests-are-public)) |
| `GET /v1/public/requests` | none | | published requests ([data-publication.md](data-publication.md)) |
| `GET /v1/public/requests/{id}` | none | | one published request |
| `GET /v1/public/files/{sha256}` | none | | a published file, with its licence in a `Link` header |
| `POST /v1/public/quality?format=json\|iod\|tdm` | none | an observation file of one station, at most 2 MiB | the station quality report ([quality-meter.md](quality-meter.md)); the file is not kept |
| `GET /v1/public/attestations` | none | | on a chain: the EAS attestations of the requests the service follows (automated results and votes), newest first, with explorer and EAS Scan links on Base Sepolia |

Deadlines move on and finished requests are settled by [the
follower](#the-follower), or when an admin calls `tick`. Calls on a request
already take its passed deadlines into account: for example, a delivery after
the reservation lapsed is refused.

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
   `ow_session` (`HttpOnly`, `SameSite=Strict`) for 12 hours. With it, the
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
[terms of use](legal/terms-of-use.md), in English and Finnish.

- **Station coordinates to about a kilometre.** `orbit-watch serve` rounds a
  station profile's latitude and longitude to two decimals of a degree, and
  refuses a delivered Orbit Watch JSON file whose station coordinates are more
  precise, with `422 too_precise`; the file is kept as delivered, since its
  SHA-256 is what the chain names. `--station-decimals N` (or
  `ORBIT_WATCH_STATION_DECIMALS`) sets another precision, `off` none. IOD and
  CCSDS TDM files name a station that the service's own sites file places.
  `create_app` applies no precision unless `station_decimals` is given.
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
| 409 | `forbidden_in_status`, `already_voted`, `duplicate_request`, `key_reused`; on a chain `no_wallet`, `wallet_already_set`, `address_taken`, `already_on_chain`, `insufficient_balance`, `nothing_to_withdraw`, `points_not_used`, `sign_on_chain` |
| 413 | `too_large` (bodies over 4,000,000 bytes, [step 4.3](#limits-against-abuse)) |
| 422 | everything else, for example `invalid_body`, `idempotency_key_required`, `hash_mismatch`, `reason_required`, `insufficient_points`, `not_enough_reviewers`, `too_precise` ([personal data](#personal-data)) |
| 429 | `rate_limited`, with `Retry-After` in seconds ([limits](#limits-against-abuse)) |
| 503 | `verification_unavailable`, `chain_unavailable` |

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

## Not yet

- TLS, key rotation and a public deployment (phase 4, step 4.5).

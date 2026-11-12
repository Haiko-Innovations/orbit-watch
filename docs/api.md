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
orbit-watch keys create --dir ./ow-service --role admin --party admin:me   # prints the key once
orbit-watch serve --dir ./ow-service                                        # http://127.0.0.1:8000/v1/
```

`--catalog`, `--policy` and `--reviewers` default to the built-in SIMULATED
data. The service directory holds the database and the files
([storage.md](storage.md)); a running server holds it exclusively, so create
the first admin key before starting it and the rest through the API.

## Keys and roles

Every call except `GET /v1/health` needs `Authorization: Bearer <key>`. A key
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

Every `POST` needs an `Idempotency-Key` header (1–128 characters), scoped to
the caller's party. The first successful response is stored in the same
database transaction as the change. Sending the same call again with the same
key returns that response with `Idempotent-Replayed: true` and changes
nothing. Using the key for a different call returns `409 key_reused`. Refused
calls change nothing and are not stored, so a key can be reused after a
refusal.

## Endpoints

| Method and path | Role | Body | Does |
|---|---|---|---|
| `GET /v1/health` | none | | version and status |
| `GET /v1/requests` | any | | all requests with status and outcome |
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
| `GET /v1/public/requests` | none | | published requests ([data-publication.md](data-publication.md)) |
| `GET /v1/public/requests/{id}` | none | | one published request |
| `GET /v1/public/files/{sha256}` | none | | a published file, with its licence in a `Link` header |

Deadlines move on and finished requests are settled when an admin (or a
scheduler with an admin key) calls `tick`. Calls on a request already take its
passed deadlines into account: for example, a delivery after the reservation
lapsed is refused.

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
| `GET /v1/wallet` | any | | your party, its wallet and the message to sign to register one |
| `POST /v1/wallet` | any | `{"address": "0x…", "signature": "0x…"}` | register your wallet (EIP-191 signature of the message) |
| `POST /v1/wallet/withdraw` | any | | `202`: the `withdraw` transaction to sign |
| `POST /v1/transactions` | any | `{"tx_hash": "0x…"}` | report a transaction you sent; the service waits for it, applies it and does its own part; returns the transaction and the request |
| `GET /v1/transactions?request=ID` | any (admin: all) | | your transactions: `pending`, `confirmed` or `failed`, with explorer links |

## Errors

Errors are JSON: `{"error": {"code": "…", "message": "…"}}`. The codes are
stable; the HTTP status follows from the code:

| Status | Codes (examples) |
|---|---|
| 401 | `unauthorized` |
| 403 | `forbidden_role`, `not_requester`, `not_a_party`, `not_your_task`, `not_yourself`, `not_your_transaction` |
| 404 | `unknown_request`, `unknown_task`, `no_report`, `unknown_file`, `unknown_transaction`, `not_on_chain` |
| 409 | `forbidden_in_status`, `already_voted`, `duplicate_request`, `key_reused`; on a chain `no_wallet`, `wallet_already_set`, `address_taken`, `already_on_chain`, `insufficient_balance`, `nothing_to_withdraw`, `points_not_used`, `sign_on_chain` |
| 413 | `too_large` (bodies over 10 MB) |
| 422 | everything else, for example `invalid_body`, `idempotency_key_required`, `hash_mismatch`, `reason_required`, `insufficient_points`, `not_enough_reviewers` |
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

- TLS, rate limits, key rotation and a public deployment (later, see P-03).

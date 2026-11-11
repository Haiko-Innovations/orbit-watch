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
| `GET /v1/requests/{id}/report` | any | | the automated verification report |
| `GET /v1/files/{sha256}` | any | | a stored file |
| `GET /v1/tasks` | reviewer | | the reviewer's open tasks (real and calibration alike) |
| `POST /v1/tasks/{task_id}/review` | reviewer | `{"approve": true, "reason": "…"}` | answer a task |
| `GET /v1/reviewers/{party}/profile` | that reviewer, admin | | accuracy profile |
| `GET /v1/balances/{party}` | that party, admin | | points held |
| `POST /v1/admin/grants` | admin | `{"party": "…", "points": 1000}` | give points (phase 1 budgets) |
| `POST /v1/admin/keys` | admin | `{"party": "…", "role": "…"}` | create a key; shown once (a replay returns `"key": null`) |
| `POST /v1/admin/tick` | admin | | apply passed deadlines and settle finished requests |

Deadlines move on and finished requests are settled when an admin (or a
scheduler with an admin key) calls `tick`. Calls on a request already take its
passed deadlines into account: for example, a delivery after the reservation
lapsed is refused.

## Errors

Errors are JSON: `{"error": {"code": "…", "message": "…"}}`. The codes are
stable; the HTTP status follows from the code:

| Status | Codes (examples) |
|---|---|
| 401 | `unauthorized` |
| 403 | `forbidden_role`, `not_requester`, `not_a_party`, `not_your_task`, `not_yourself` |
| 404 | `unknown_request`, `unknown_task`, `no_report`, `unknown_file` |
| 409 | `forbidden_in_status`, `already_voted`, `duplicate_request`, `key_reused` |
| 413 | `too_large` (bodies over 10 MB) |
| 422 | everything else, for example `invalid_body`, `idempotency_key_required`, `hash_mismatch`, `reason_required`, `insufficient_points`, `not_enough_reviewers` |
| 503 | `verification_unavailable` |

## Example

```sh
H="Authorization: Bearer $REQUESTER_KEY"
curl -s -X POST -H "$H" -H "Idempotency-Key: create-1" \
  -d "{\"request\": $(cat request.json)}" http://127.0.0.1:8000/v1/requests
curl -s -X POST -H "Authorization: Bearer $STATION_KEY" -H "Idempotency-Key: deliver-1" \
  --data-binary @observations.json \
  "http://127.0.0.1:8000/v1/requests/SIM-REQ-0001/deliveries?format=json"
```

## Not yet

- Public reads, licence and embargo rules for files and reports (step 1.8).
- A command-line client for the whole chain (step 1.7).
- TLS, rate limits, key rotation and a public deployment (later, see P-03).

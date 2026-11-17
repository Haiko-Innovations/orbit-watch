# Storage

Phase 1, step 1.5; PostgreSQL since phase 4, step 4.1. Code:
[`core/src/orbit_watch/storage/`](../core/src/orbit_watch/storage),
[`settlement/stored_ledger.py`](../core/src/orbit_watch/settlement/stored_ledger.py)
and `open_service` in [`service.py`](../core/src/orbit_watch/service.py).
Decisions: [P4-04](decisions.md#p4-04-postgresql-wherever-the-service-keeps-state)
(which replaced P-02's SQLite),
[D-34](decisions.md#d-34-postgresql-storage) and, for many processes on one
database, [D-35](decisions.md#d-35-the-stateless-service-the-follower-and-the-image).

A service opened with `open_service(database, reviewers, context)` keeps its
whole state, files included, in one PostgreSQL database and survives restarts.
`database` is a libpq URL or connection string, such as
`postgresql://user@host/dbname`. A `search_path` in its `options` selects a
schema, so several services can share one database, one schema each; the tests
give every test a schema of its own. Any number of processes can run one
service on one schema (step 4.2, see [Consistency](#consistency)).

`orbit-watch serve` and `orbit-watch keys create` take the database from
`--database`, or else from `ORBIT_WATCH_DATABASE_URL` or `DATABASE_URL`. A URL
with a password on the command line ends up in the shell history, so prefer the
environment. Messages name the database and the schema, never the connection
string.

The open core's command-line tools (validate, convert, verify, simulate, the
quality meter and the demos) keep no state and need no database. psycopg, the
PostgreSQL driver, is part of the `api` extra.

## Database

PostgreSQL through [psycopg](https://www.psycopg.org/) 3, with the schema in
numbered plain-SQL migrations:
[`storage/migrations/`](../core/src/orbit_watch/storage/migrations).

- `migrate()` applies missing migrations in one transaction and records each
  one with the SHA-256 of its SQL. A migration that was changed after it was
  applied, or a database with migrations this version does not know, is
  refused (`migration_changed`, `newer_schema`).
- The SQL is standard PostgreSQL with nothing specific to one provider
  ([P4-05](decisions.md#p4-05-portable-by-design)). Numbers that can grow
  (blocks, amounts, sizes) are `BIGINT`. The code writes `?` placeholders, which
  the storage layer turns into psycopg's `%s`.

| Table | Holds |
|---|---|
| `requests` | each request's full lifecycle record as JSON, plus its status for queries |
| `files` | every kept file: its SHA-256, size and content |
| `deliveries` | station, observation file, report and automated verdict per request |
| `settlements` | the settlement plan and the ledger reference per request |
| `review_tasks` | real and calibration review tasks |
| `ledger_entries`, `ledger_postings` | the double-entry points journal |
| `ledger_settled`, `attestations` | settled requests and recorded attestations |
| `chain_settings`, `wallets`, `transactions`, `chain_events`, `chain_texts`, `chain_uploads`, `chain_conflicts` | on a testnet chain only (migration 0003, step 2.6): the chain followed, each party's wallet, watched transactions, the escrow events applied, reasons by SHA-256, uploaded files and conflicts ([chain-service.md](chain-service.md)) |
| `station_profiles` | each station's profile (migration 0005, step 3.5); only the station and administrators read it ([D-30](decisions.md#d-30-the-observers-view)) |
| `governance_operations`, `chain_attestations` | on a testnet chain only (migration 0006, step 3.7): the operations of the timelock that owns the reviewer registry, from its events, and the EAS attestations behind the escrow's results and votes, read once ([D-32](decisions.md#d-32-the-administrator-view-and-the-public-pages)) |
| `service_state` | one row (migration 0007, step 4.2): the state's version, which every change raises, and when the follower last ran ([D-35](decisions.md#d-35-the-stateless-service-the-follower-and-the-image)) |
| `signin_challenges`, `sessions` | signing in with a wallet (migration 0004, step 3.2): the sign-in messages the service wrote, each usable once, and browser sessions by the SHA-256 of their cookie; `wallets.signed_message` keeps the message a party signed when it signed up in the browser ([D-27](decisions.md#d-27-signing-in-with-a-wallet)) |
| `api_keys`, `idempotency` | API keys by their SHA-256 (migration 0002, step 1.6), and a copy of each change's answer by party and `Idempotency-Key`, kept for 24 hours (its path and expiry: migration 0009, step 4.4) |
| `rate_limits` | the limits' counts per fixed window (migration 0008, step 4.3): a party, or an IP address as a keyed SHA-256 only, deleted when the window has passed ([D-36](decisions.md#d-36-limits-the-body-limit-and-the-dedicated-rpc-endpoint)) |

With `database_role` (`ORBIT_WATCH_DATABASE_ROLE`, step 4.5), the database's
own user runs the migrations, then makes sure the role exists without a login
and may only read and write the schema's tables and sequences; every
transaction begins with `SET LOCAL ROLE`. A lost connection is opened again
before a transaction or a read on its own, never in the middle of a transaction,
and no server-side prepared statements are used, so a pooler in transaction mode
works ([D-38](decisions.md#d-38-the-service-on-vercel-and-neon)).

What these tables keep about people, who sees it and for how long is in
[personal-data.md](personal-data.md) (step 4.4). `api/privacy.py`'s `sweep`
deletes what is no longer needed; the follower and every sign-in run it.

## Files

Observation files, reports and request documents are kept in the `files`
table by their SHA-256 (`content`, `BYTEA`) and are **never deleted**: a hash
identifies a file, it does not replace keeping it. Every read checks the hash
(`corrupt_file`). A file is written in the caller's transaction, so a rolled
back call leaves no file behind.

## Consistency

- **One transaction per call.** Every service call that changes something runs
  in one database transaction, so the lifecycle, the deliveries, the review
  tasks and the points journal always change together.
- **A refused call changes nothing.** If a call fails, for any reason, the
  transaction is rolled back and the working state is reloaded from the
  database. Business refusals (`ServiceError`) have no side effects; for
  example, a challenge that comes too late is refused and the request is settled
  by the next `tick`.
- **Many processes per schema, one transaction at a time** (step 4.2,
  [P4-06](decisions.md#p4-06-the-service-runs-on-its-own)). Every transaction
  first takes the schema's transaction-scoped advisory lock
  (`pg_advisory_xact_lock`, keyed by the database and the schema), so
  transactions on one schema take turns, across processes too; the lock ends
  with the transaction and works behind a connection pooler. A change made
  outside a transaction gets one of its own.
- **A copy in memory, checked on every transaction.** A process keeps a copy of
  the working state in memory for speed. A transaction that changes anything
  raises the state's version in `service_state`. When a transaction begins,
  under the lock, the process compares that version with the one it last saw
  and reloads its copy if another process changed the state, or if one of its
  own transactions was rolled back. So every call works on the current state,
  and a change that another process already made is refused, never made twice:
  of two stations that reserve one request at the same moment, one gets it and
  the other is told that it is reserved.
- **Rebuilt on start.** The service rebuilds its working state from the
  database, and the points ledger rebuilds its balances from the journal; an
  unbalanced or out-of-order journal is refused (`broken_journal`).

## Tests

- Migrations from an empty database, changed and unknown migrations.
- The stored ledger passes the same settlement scenario suite as the memory
  ledger and gives the same journal.
- A full request history run with a restart after every step ends in exactly
  the same state as the same history in memory.
- Two services on one database, taking the steps of a history in turns, end in
  the same state as the service in memory; two that reserve one request at the
  same moment reserve it once; transactions on one schema take turns.
- A refused call and a crash in the middle of a call leave the stored state
  unchanged.

The tests that need a database run against the server named by
`ORBIT_WATCH_TEST_DATABASE_URL`, or else against a PostgreSQL they start in
Docker ([`core/tests/postgres.py`](../core/tests/postgres.py)): PostgreSQL 18
as on Neon, the official image pinned by digest, on `127.0.0.1` only, with
trust authentication and its data in memory. Every test gets schemas of its
own, dropped afterwards. Without Docker or a server those tests are skipped,
unless `ORBIT_WATCH_PG_TESTS=1`, as in CI, where a service container runs the
same image. The local stack takes its database the same way.

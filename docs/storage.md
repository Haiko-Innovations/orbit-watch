# Storage

Phase 1, step 1.5. Code: [`core/src/orbit_watch/storage/`](../core/src/orbit_watch/storage),
[`settlement/sqlite_ledger.py`](../core/src/orbit_watch/settlement/sqlite_ledger.py)
and `open_service` in [`service.py`](../core/src/orbit_watch/service.py).

A service opened with `open_service(directory, reviewers, context)` keeps its
whole state in one directory and survives restarts:

```
directory/
  orbit-watch.sqlite3   requests, deliveries, settlements, review tasks, the points journal
  files/ab/abcdef…      observation files, reports and request documents, by SHA-256
```

## Database

SQLite from the Python standard library, with the schema in numbered plain-SQL
migrations ([decision P-02](decisions.md#p-02-sqlite-with-plain-sql-migrations)):
[`storage/migrations/`](../core/src/orbit_watch/storage/migrations).

- `migrate()` applies missing migrations in one transaction and records each
  one with the SHA-256 of its SQL. A migration that was changed after it was
  applied, or a database with migrations this version does not know, is
  refused (`migration_changed`, `newer_schema`).
- The SQL avoids SQLite-only features (it uses standard types and
  `ON CONFLICT` upserts), so a later move to PostgreSQL stays small.

| Table | Holds |
|---|---|
| `requests` | each request's full lifecycle record as JSON, plus its status for queries |
| `files` | the SHA-256 and size of every kept file |
| `deliveries` | station, observation file, report and automated verdict per request |
| `settlements` | the settlement plan and the ledger reference per request |
| `review_tasks` | real and calibration review tasks |
| `ledger_entries`, `ledger_postings` | the double-entry points journal |
| `ledger_settled`, `attestations` | settled requests and recorded attestations |

## Files

Observation files, reports and request documents are kept under `files/` by
their SHA-256 and are **never deleted**: a hash identifies a file, it does not
replace keeping it. Every read checks the hash (`corrupt_file`). Writing is
atomic (a temporary file, then a rename). A transaction that is rolled back can
leave a file on disk that no table lists, which is harmless.

## Consistency

- **One transaction per call.** Every service call that changes something runs
  in one database transaction, so the lifecycle, the deliveries, the review
  tasks and the points journal always change together.
- **A refused call changes nothing.** If a call fails, for any reason, the
  transaction is rolled back and the working state is reloaded from the
  database. Business refusals (`ServiceError`) have no side effects; for
  example, a challenge that comes too late is refused and the request is settled
  by the next `tick`.
- **One process at a time.** The database is opened in SQLite's exclusive
  locking mode. A second process that opens the same directory gets
  `StorageError("in_use")`. This is enough for phase 1, which has no public
  service ([P-03](decisions.md#p-03-no-public-deployment-in-phase-1)).
- **Rebuilt on start.** The service rebuilds its working state from the
  database, and the points ledger rebuilds its balances from the journal; an
  unbalanced or out-of-order journal is refused (`broken_journal`).

## Tests

- Migrations from an empty database, changed and unknown migrations.
- The SQLite ledger passes the same settlement scenario suite as the memory
  ledger and gives the same journal.
- A full request history run with a restart after every step ends in exactly
  the same state as the same history in memory.
- A refused call and a crash in the middle of a call leave the stored state
  unchanged.

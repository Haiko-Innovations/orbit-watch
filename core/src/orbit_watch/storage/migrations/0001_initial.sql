-- Orbit Watch storage, migration 0001 (phase 1). PostgreSQL since phase 4 (decision P4-04,
-- which replaced P-02's SQLite); plain SQL, standard types.

-- Every kept file, by its SHA-256: requests, observations and reports. Never deleted.
CREATE TABLE files (
    sha256 TEXT PRIMARY KEY CHECK (length(sha256) = 64),
    size BIGINT NOT NULL CHECK (size >= 0),
    content BYTEA NOT NULL
);

CREATE TABLE requests (
    request_id TEXT PRIMARY KEY,
    requester TEXT NOT NULL,
    status TEXT NOT NULL,
    request_sha256 TEXT NOT NULL REFERENCES files (sha256),
    record_json TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE deliveries (
    request_id TEXT PRIMARY KEY REFERENCES requests (request_id),
    station TEXT NOT NULL,
    observations_sha256 TEXT NOT NULL REFERENCES files (sha256),
    observations_format TEXT,
    report_sha256 TEXT NOT NULL REFERENCES files (sha256),
    verdict TEXT NOT NULL
);

CREATE TABLE settlements (
    request_id TEXT PRIMARY KEY REFERENCES requests (request_id),
    plan_json TEXT NOT NULL,
    reference TEXT NOT NULL
);

CREATE TABLE review_tasks (
    task_id TEXT PRIMARY KEY,
    reviewer TEXT NOT NULL,
    kind TEXT NOT NULL CHECK (kind IN ('real', 'calibration')),
    request_id TEXT REFERENCES requests (request_id),
    calibration_json TEXT,
    CHECK ((kind = 'real' AND request_id IS NOT NULL AND calibration_json IS NULL)
        OR (kind = 'calibration' AND request_id IS NULL AND calibration_json IS NOT NULL))
);

CREATE INDEX review_tasks_by_reviewer ON review_tasks (reviewer);

CREATE TABLE ledger_entries (
    seq BIGINT PRIMARY KEY,
    idempotency_key TEXT NOT NULL UNIQUE,
    fingerprint TEXT NOT NULL,
    operation TEXT NOT NULL,
    request_id TEXT,
    memo TEXT NOT NULL
);

CREATE TABLE ledger_postings (
    seq BIGINT NOT NULL REFERENCES ledger_entries (seq),
    position INTEGER NOT NULL,
    account TEXT NOT NULL,
    amount BIGINT NOT NULL,
    PRIMARY KEY (seq, position)
);

CREATE TABLE ledger_settled (
    request_id TEXT PRIMARY KEY,
    idempotency_key TEXT NOT NULL REFERENCES ledger_entries (idempotency_key)
);

CREATE TABLE attestations (
    seq BIGINT PRIMARY KEY REFERENCES ledger_entries (seq),
    request_id TEXT NOT NULL,
    attester TEXT NOT NULL,
    kind TEXT NOT NULL,
    subject_sha256 TEXT NOT NULL,
    value TEXT NOT NULL
);

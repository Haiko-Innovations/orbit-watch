-- Orbit Watch phase 1 storage, migration 0002: the HTTP API (step 1.6).

CREATE TABLE api_keys (
    key_hash TEXT PRIMARY KEY CHECK (length(key_hash) = 64),
    party TEXT NOT NULL,
    role TEXT NOT NULL CHECK (role IN ('requester', 'station', 'reviewer', 'admin')),
    created_at TEXT NOT NULL,
    revoked INTEGER NOT NULL DEFAULT 0 CHECK (revoked IN (0, 1))
);

CREATE INDEX api_keys_by_party ON api_keys (party);

CREATE TABLE idempotency (
    party TEXT NOT NULL,
    idempotency_key TEXT NOT NULL,
    request_hash TEXT NOT NULL,
    status_code INTEGER NOT NULL,
    response_json TEXT NOT NULL,
    PRIMARY KEY (party, idempotency_key)
);

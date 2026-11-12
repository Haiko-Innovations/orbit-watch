-- Orbit Watch storage, migration 0003: the service on a testnet chain (phase 2, step 2.6).
-- Every table stays empty for a service that does not run on a chain.

-- The chain and escrow this service follows, and how far it has read the chain.
CREATE TABLE chain_settings (
    name TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

-- One wallet address per party and one party per address, proven by a signature.
CREATE TABLE wallets (
    party TEXT PRIMARY KEY,
    address TEXT NOT NULL UNIQUE,
    signature TEXT NOT NULL,
    registered_at TEXT NOT NULL
);

-- Transactions that parties reported and that the service sent itself. The chain decides
-- their status; this table only remembers which ones to watch.
CREATE TABLE transactions (
    tx_hash TEXT PRIMARY KEY,
    party TEXT NOT NULL,
    action TEXT NOT NULL,
    request_id TEXT,
    status TEXT NOT NULL CHECK (status IN ('pending', 'confirmed', 'failed')),
    block INTEGER,
    error TEXT,
    reported_at TEXT NOT NULL
);

CREATE INDEX transactions_by_party ON transactions (party);
CREATE INDEX transactions_by_request ON transactions (request_id);

-- The escrow's events the service has applied to its requests, in chain order.
CREATE TABLE chain_events (
    tx_hash TEXT NOT NULL,
    log_index INTEGER NOT NULL,
    block INTEGER NOT NULL,
    request_id TEXT NOT NULL,
    event TEXT NOT NULL,
    at TEXT NOT NULL,
    PRIMARY KEY (tx_hash, log_index)
);

CREATE INDEX chain_events_by_request ON chain_events (request_id);

-- Challenge and vote reasons, kept by the SHA-256 that goes on chain.
CREATE TABLE chain_texts (
    sha256 TEXT PRIMARY KEY CHECK (length(sha256) = 64),
    text TEXT NOT NULL
);

-- Observation files a station uploaded before (or after) delivering their SHA-256 on chain.
CREATE TABLE chain_uploads (
    request_id TEXT NOT NULL,
    sha256 TEXT NOT NULL CHECK (length(sha256) = 64),
    station TEXT NOT NULL,
    format TEXT,
    PRIMARY KEY (request_id, sha256)
);

-- Escrow events that do not fit a request's record, for example someone else funding the
-- same request ID with other terms. They are shown, never applied.
CREATE TABLE chain_conflicts (
    tx_hash TEXT NOT NULL,
    log_index INTEGER NOT NULL,
    request_id TEXT NOT NULL,
    code TEXT NOT NULL,
    message TEXT NOT NULL,
    PRIMARY KEY (tx_hash, log_index)
);

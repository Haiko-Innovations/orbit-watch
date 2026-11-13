-- Orbit Watch storage, migration 0006: the administrator view and the public attestation
-- browser (phase 3, step 3.7). Both tables stay empty for a service that does not run on a
-- chain.

-- The operations of the timelock that owns the reviewer registry, as its events tell them:
-- one row per call (a batch has several). The timelock itself decides whether an operation
-- is waiting, ready or done; this table only remembers what was scheduled.
CREATE TABLE governance_operations (
    operation_id TEXT NOT NULL,
    call_index INTEGER NOT NULL,
    target TEXT NOT NULL,
    value TEXT NOT NULL,
    data TEXT NOT NULL,
    predecessor TEXT NOT NULL,
    delay_seconds INTEGER NOT NULL,
    salt TEXT,
    scheduled_tx TEXT NOT NULL,
    scheduled_block INTEGER NOT NULL,
    scheduled_at TEXT NOT NULL,
    executed_tx TEXT,
    executed_at TEXT,
    cancelled_tx TEXT,
    cancelled_at TEXT,
    PRIMARY KEY (operation_id, call_index)
);

-- The EAS attestations behind the escrow's VerificationRecorded and Voted events, read once
-- from the chain: they never change, and the public attestation browser lists them.
CREATE TABLE chain_attestations (
    tx_hash TEXT NOT NULL,
    log_index INTEGER NOT NULL,
    uid TEXT NOT NULL UNIQUE,
    kind TEXT NOT NULL CHECK (kind IN ('result', 'vote')),
    request_id TEXT NOT NULL,
    attester TEXT NOT NULL,
    fields_json TEXT NOT NULL,
    PRIMARY KEY (tx_hash, log_index)
);

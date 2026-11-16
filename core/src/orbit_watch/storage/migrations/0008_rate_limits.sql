-- Limits against abuse (phase 4, step 4.3; decision P4-08). One row per limit, subject and
-- fixed time window, deleted once the window is over. A subject is a party, or an IP
-- address as a keyed SHA-256 (never the address itself) with the key below.
CREATE TABLE rate_limits (
    name TEXT NOT NULL,
    subject TEXT NOT NULL,
    window_start BIGINT NOT NULL,
    hits INTEGER NOT NULL,
    expires_at BIGINT NOT NULL,
    PRIMARY KEY (name, subject, window_start)
);

CREATE INDEX rate_limits_by_expiry ON rate_limits (expires_at);

-- The key for IP addresses: random, made once per database (gen_random_uuid is built into
-- PostgreSQL 13 and later), so that every process of the service counts alike.
ALTER TABLE service_state
    ADD COLUMN limit_key TEXT NOT NULL DEFAULT (gen_random_uuid()::text || gen_random_uuid()::text);

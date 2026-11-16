-- Orbit Watch storage, migration 0009: retention (phase 4, step 4.4; decision D-37).

-- An idempotency record keeps a copy of a change's answer, so that a retry gets the same
-- answer instead of a second change. It is kept for a day (api/privacy.py), and the path
-- lets a deleted station profile take its records with it. Records from before this
-- migration have no expiry and are deleted at the next sweep.
ALTER TABLE idempotency ADD COLUMN path TEXT;
ALTER TABLE idempotency ADD COLUMN expires_at BIGINT;
CREATE INDEX idempotency_by_expiry ON idempotency (expires_at);

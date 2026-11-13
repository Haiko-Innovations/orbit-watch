-- Orbit Watch storage, migration 0004: signing in with a wallet (phase 3, step 3.2).

-- Sign-In with Ethereum messages (ERC-4361) that the service wrote. Each is usable once,
-- before it expires, from the origin it was written for.
CREATE TABLE signin_challenges (
    nonce TEXT PRIMARY KEY,
    address TEXT NOT NULL,
    origin TEXT NOT NULL,
    message TEXT NOT NULL,
    sign_up_party TEXT,
    issued_at TEXT NOT NULL,
    expires_at TEXT NOT NULL,
    used_at TEXT
);

-- Browser sessions, by the SHA-256 of their cookie; the cookie itself is never stored.
CREATE TABLE sessions (
    token_hash TEXT PRIMARY KEY CHECK (length(token_hash) = 64),
    party TEXT NOT NULL,
    role TEXT NOT NULL CHECK (role IN ('requester', 'station', 'reviewer', 'admin')),
    address TEXT NOT NULL,
    origin TEXT NOT NULL,
    created_at TEXT NOT NULL,
    expires_at TEXT NOT NULL,
    ended_at TEXT
);

CREATE INDEX sessions_by_party ON sessions (party);

-- A wallet registered by signing up in the browser keeps the message it signed, so the
-- registration stays verifiable like one signed from the command line.
ALTER TABLE wallets ADD COLUMN signed_message TEXT;

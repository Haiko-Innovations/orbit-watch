-- Orbit Watch storage, migration 0007: a stateless service (phase 4, step 4.2; P4-06).

-- The version of the service's state. Every transaction that changes something adds one.
-- A service instance keeps a copy of the state in memory and reloads it when the version
-- is not the one it last saw, so any number of instances can share one database.
-- followed_at: when the follower last did the service's own work (UTC).
CREATE TABLE service_state (
    id INTEGER PRIMARY KEY CHECK (id = 1),
    version BIGINT NOT NULL,
    followed_at TEXT
);

INSERT INTO service_state (id, version) VALUES (1, 0);

-- Orbit Watch storage, migration 0012: real objects on the allow-list (phase 5, step 5.4;
-- decisions P5-08 and D-49). CelesTrak's groups as the follower last fetched them, and the
-- objects an administrator added, each with a public reason.

-- One row per group the follower has asked for. ``status`` is the HTTP status of the last
-- answer, NULL while it is asked or when no answer came; ``members_json`` holds the
-- objects of the last answer of 200, as [catalogue number, name] pairs.
CREATE TABLE allowlist_groups (
    group_name TEXT PRIMARY KEY,
    asked_at TEXT NOT NULL,
    status INTEGER,
    fetched_at TEXT,
    sha256 TEXT,
    members_json TEXT
);

CREATE TABLE allowlist_additions (
    norad_id BIGINT PRIMARY KEY,
    name TEXT NOT NULL,
    reason TEXT NOT NULL,
    added_at TEXT NOT NULL,
    added_by TEXT NOT NULL
);

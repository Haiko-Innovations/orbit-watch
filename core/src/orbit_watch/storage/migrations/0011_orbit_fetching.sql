-- Orbit Watch storage, migration 0011: the follower fetches reference orbits (phase 5,
-- step 5.4; decisions P5-02, P5-03 and D-48). For each source, whether fetching is
-- stopped and why, which a person clears; for each object, when it was last asked for and
-- what the source answered.
CREATE TABLE orbit_sources (
    source TEXT PRIMARY KEY CHECK (source IN ('celestrak', 'satchecker')),
    stopped_at TEXT,
    stop_status INTEGER,
    stop_norad_id BIGINT,
    stop_reason TEXT,
    not_before TEXT,
    last_answer_at TEXT,
    resumed_at TEXT,
    resumed_by TEXT
);

INSERT INTO orbit_sources (source) VALUES ('celestrak'), ('satchecker');

-- ``target`` is '' for an object's current element sets, and for a past set the time it
-- is to be nearest. ``status`` is the HTTP status of the answer, NULL while it is asked or
-- when no answer came.
CREATE TABLE orbit_asks (
    source TEXT NOT NULL CHECK (source IN ('celestrak', 'satchecker')),
    norad_id BIGINT NOT NULL,
    target TEXT NOT NULL,
    asked_at TEXT NOT NULL,
    status INTEGER,
    PRIMARY KEY (source, norad_id, target)
);

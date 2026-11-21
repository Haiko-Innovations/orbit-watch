-- Orbit Watch storage, migration 0010: reference orbits (phase 5, step 5.4; decisions P5-02,
-- P5-05 and D-47). The real element sets the service verifies deliveries against: fetched
-- from CelesTrak or SatChecker, or uploaded by an administrator. They are kept, not served:
-- reports name a set by the SHA-256 of its OMM fields, its epoch and its source.
CREATE TABLE element_sets (
    sha256 TEXT PRIMARY KEY,
    norad_id BIGINT NOT NULL,
    epoch TEXT NOT NULL,
    source TEXT NOT NULL CHECK (source IN ('celestrak', 'satchecker', 'uploaded')),
    fetched_at TEXT NOT NULL,
    uploaded_by TEXT,
    record_json TEXT NOT NULL
);

CREATE INDEX element_sets_by_object ON element_sets (norad_id, epoch);

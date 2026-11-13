-- Orbit Watch storage, migration 0005: station profiles (phase 3, step 3.5).

-- Each station's profile: where it is and what it observes with. Only the station itself
-- and administrators read it (its coordinates are personal data); the service uses it to
-- simulate observations for the station on request.
CREATE TABLE station_profiles (
    party TEXT PRIMARY KEY,
    profile_json TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

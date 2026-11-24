-- Orbit Watch storage, migration 0015: objects whose operators publish their orbits (phase 6,
-- step 6.2; decisions P6-04 and D-62). An administrator's addition may name the CelesTrak
-- SupGP source with its operator's orbit, such as ``SpaceX-E`` for a Starlink object, after
-- one SupGP query has shown it. NULL for an addition without one. The SupGP sources read
-- once a day are kept in ``allowlist_groups`` beside CelesTrak's groups.
ALTER TABLE allowlist_additions ADD COLUMN operator_source TEXT;

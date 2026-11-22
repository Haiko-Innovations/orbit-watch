-- Orbit Watch storage, migration 0014: the place an IOD or CCSDS TDM delivery was verified at
-- (phase 5, step 5.6; decisions P5-11 and D-55). Such a file names only a station number or
-- name; its station's profile is its place, written as a sites document that is kept in
-- ``files`` and published with the delivery. NULL for a JSON delivery, which names its own
-- place, and for one verified with the service's own sites file.
ALTER TABLE deliveries ADD COLUMN sites_sha256 TEXT;
ALTER TABLE chain_uploads ADD COLUMN sites_sha256 TEXT;

-- Orbit Watch storage, migration 0016: one more try after a request that got no answer
-- (phase 6, step 6.2; decision D-64). ``no_answer_at`` is when a source last left a request
-- unanswered while it was not stopped. The follower then waits two hours and tries once
-- more; a second request without an answer stops the source, as D-48 did at the first. An
-- answer clears it, and so does a person who resumes the source.
ALTER TABLE orbit_sources ADD COLUMN no_answer_at TEXT;

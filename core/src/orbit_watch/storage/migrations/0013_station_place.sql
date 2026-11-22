-- Orbit Watch storage, migration 0013: how precisely a station's place is published (phase
-- 5, step 5.6; decisions P5-11 and D-54). The observer chooses "exact" or "kilometre" (to
-- about a kilometre) when saving the profile, with nothing chosen in advance. NULL: a
-- profile saved before the choice existed, kept to about a kilometre until its owner
-- chooses.
ALTER TABLE station_profiles ADD COLUMN place TEXT;

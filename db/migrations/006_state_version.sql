-- 006: canonical schema registry — state_version on memory_states.
--
-- state_version 1 = state_json holds raw extractor keys, where two aliases
-- for one concept could coexist (`budget_inr` alongside `budget_inr_max`).
-- state_version 2 = every key is a canonical path from app/schema/canonical.py
-- and money/date values are normalized objects.
--
-- Existing rows are NOT rewritten. A handle is the content address of the
-- bytes that produced it, so editing state_json in place would leave every
-- stored handle pointing at content it no longer describes, and audit replay
-- would stop verifying. Old rows keep version 1 and are read forward.

ALTER TABLE memory_states
    ADD COLUMN state_version INT NOT NULL DEFAULT 1;

-- Rows created from here on are written by the canonical pipeline.
-- (No UPDATE: see above. New writes set the column explicitly.)

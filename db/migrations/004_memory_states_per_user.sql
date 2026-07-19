-- 004: scope memory_states dedup to (handle, user_id, session_tag).
-- The old PRIMARY KEY (handle) deduped globally: when a second user (or a
-- second session) ingested content that produced the same deterministic
-- handle, INSERT IGNORE silently dropped their row and they were left with
-- no state at all — this broke the instant demo for every fresh account.
-- Applied automatically at app startup (app/main.py _ensure_tables); kept
-- here for reference / manual runs.

ALTER TABLE memory_states
  DROP PRIMARY KEY,
  ADD COLUMN id INT NOT NULL AUTO_INCREMENT PRIMARY KEY FIRST,
  ADD UNIQUE KEY uq_memory_states_scope (handle, user_id, session_tag);

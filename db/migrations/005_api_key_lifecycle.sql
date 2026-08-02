-- 005: developer API key lifecycle.
--
-- Keys were mint-and-forget: no expiry, no label, no way to tell a key that
-- is still in use from one issued months ago and abandoned. All three columns
-- are nullable so existing rows stay valid — a NULL expires_at means "never
-- expires", which is what every key issued before this migration was.
--
-- app/main.py applies the same three ALTERs at boot for a deployed database
-- that cannot be migrated by hand.

ALTER TABLE api_keys ADD COLUMN label VARCHAR(100) NULL;
ALTER TABLE api_keys ADD COLUMN expires_at DATETIME NULL;
ALTER TABLE api_keys ADD COLUMN last_used_at DATETIME NULL;

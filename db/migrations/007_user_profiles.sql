-- 007: user profiles.
--
-- A side table rather than columns on `users`. `users` holds the credential,
-- so every read of it is on an auth path; putting display data there would
-- mean an ordinary profile edit touches the row that decides who you are.
-- One-to-one keeps the credential surface exactly as small as it already was.
--
-- Every field is nullable and there is no backfill. An account without a
-- profile row is a normal state -- "not filled in" -- not a broken one, and
-- the read endpoint returns an empty profile rather than a 404 for it. That
-- means this migration cannot break an existing account: nothing is required
-- and nothing is rewritten.
--
-- Widths match app/profile.py::LIMITS. They are declared in one place in the
-- application so the validator rejects a long value with a readable reason
-- instead of letting the database raise a truncation error.

CREATE TABLE IF NOT EXISTS user_profiles (
    id            INT AUTO_INCREMENT PRIMARY KEY,
    user_id       INT          NOT NULL,
    display_name  VARCHAR(80)  NULL,
    organization  VARCHAR(120) NULL,
    role          VARCHAR(80)  NULL,
    use_case      VARCHAR(400) NULL,
    created_at    DATETIME     NOT NULL,
    updated_at    DATETIME     NOT NULL,
    -- one profile per account, enforced by the schema rather than by whichever
    -- code path happens to write it
    UNIQUE KEY uq_user_profiles_user (user_id)
);

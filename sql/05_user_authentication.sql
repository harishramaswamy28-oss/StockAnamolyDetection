-- Authentication support for the dashboard and ownership-scoped user data.
-- Existing app_user rows keep a NULL password_hash and cannot sign in until
-- their owner registers a new account or an administrator provisions a hash.

ALTER TABLE app_user
    ADD COLUMN IF NOT EXISTS password_hash TEXT;

CREATE TABLE IF NOT EXISTS app_session (
    token_hash CHAR(64) PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES app_user(user_id) ON DELETE CASCADE,
    expires_at TIMESTAMPTZ NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_app_session_user_expiry
    ON app_session (user_id, expires_at);

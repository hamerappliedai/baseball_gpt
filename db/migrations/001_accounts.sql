-- Accounts, server-side sessions, login attempts and Ask AI usage.
-- Applied once by `make migrate`; never edit after it has been applied
-- anywhere, add 002_... instead.

CREATE TABLE app.users (
    id                 bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    email              text NOT NULL CHECK (email = lower(email) AND email LIKE '%_@_%'),
    password_hash      text NOT NULL,
    display_name       text NOT NULL,
    role               text NOT NULL DEFAULT 'user' CHECK (role IN ('user', 'admin')),
    is_active          boolean NOT NULL DEFAULT true,
    daily_token_limit  integer CHECK (daily_token_limit >= 0),  -- NULL: the server default
    created_at         timestamptz NOT NULL DEFAULT now(),
    last_login_at      timestamptz
);
CREATE UNIQUE INDEX users_email_key ON app.users (email);

-- The cookie holds a random token; only its SHA-256 is stored, so a leaked
-- table can't be replayed as sessions.
CREATE TABLE app.sessions (
    token_hash    bytea PRIMARY KEY,
    user_id       bigint NOT NULL REFERENCES app.users ON DELETE CASCADE,
    created_at    timestamptz NOT NULL DEFAULT now(),
    expires_at    timestamptz NOT NULL,
    last_seen_at  timestamptz NOT NULL DEFAULT now(),
    user_agent    text
);
CREATE INDEX sessions_user_id_idx ON app.sessions (user_id);
CREATE INDEX sessions_expires_at_idx ON app.sessions (expires_at);

-- Failed logins, for rate limiting by email and by client address. Kept in
-- the database so the limit holds across several backend instances.
CREATE TABLE app.login_failures (
    id         bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    email      text NOT NULL,
    client_ip  text NOT NULL,
    at         timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX login_failures_email_at_idx ON app.login_failures (email, at);
CREATE INDEX login_failures_ip_at_idx ON app.login_failures (client_ip, at);

-- One row per Ask AI question, from the API's reported usage (summed over the
-- tool-use rounds). Feeds the per-user hourly and daily limits.
CREATE TABLE app.chat_usage (
    id                     bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    user_id                bigint NOT NULL REFERENCES app.users ON DELETE CASCADE,
    created_at             timestamptz NOT NULL DEFAULT now(),
    model                  text NOT NULL,
    input_tokens           integer NOT NULL DEFAULT 0,
    output_tokens          integer NOT NULL DEFAULT 0,
    cache_creation_tokens  integer NOT NULL DEFAULT 0,
    cache_read_tokens      integer NOT NULL DEFAULT 0,
    tool_rounds            integer NOT NULL DEFAULT 0,
    stop_reason            text
);
CREATE INDEX chat_usage_user_created_idx ON app.chat_usage (user_id, created_at);

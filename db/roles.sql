-- Read-only role the chat backend uses to run Claude's SQL. Idempotent: `make
-- db-up` applies it on every start. Run with psql, passing the password:
--   psql -v reader_password=... -f db/roles.sql
--
-- Security rests on privileges, not on session settings (a session can change
-- its own settings): the role can SELECT the marts tables and the search
-- aliases in vectors, and nothing else.
-- The backend also runs every query in a READ ONLY transaction with a
-- statement timeout and always rolls it back.

SELECT 'CREATE ROLE bgpt_reader'
WHERE NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'bgpt_reader') \gexec

ALTER ROLE bgpt_reader WITH LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT
    CONNECTION LIMIT 20 PASSWORD :'reader_password';

-- Defaults for the role's sessions (defence in depth, not the boundary).
ALTER ROLE bgpt_reader SET default_transaction_read_only = on;
ALTER ROLE bgpt_reader SET statement_timeout = '5s';
ALTER ROLE bgpt_reader SET idle_in_transaction_session_timeout = '10s';
ALTER ROLE bgpt_reader SET search_path = marts;

-- No temp tables for anyone but the owner (PUBLIC has TEMP by default).
-- :"DBNAME" is psql's name for the database it's connected to.
REVOKE TEMPORARY ON DATABASE :"DBNAME" FROM PUBLIC;
GRANT CONNECT ON DATABASE :"DBNAME" TO bgpt_reader;

-- marts and vectors only: raw and staging stay invisible.
REVOKE ALL ON SCHEMA raw, staging FROM bgpt_reader;
GRANT USAGE ON SCHEMA marts TO bgpt_reader;
GRANT SELECT ON ALL TABLES IN SCHEMA marts TO bgpt_reader;
-- dbt drops and recreates mart tables on every build; new tables it creates
-- (as the owner role) get SELECT for the reader automatically.
ALTER DEFAULT PRIVILEGES FOR ROLE CURRENT_USER IN SCHEMA marts
    GRANT SELECT ON TABLES TO bgpt_reader;

-- Player search reads the alias embeddings (phase 4). `bgpt-pipeline embed`
-- recreates these tables, so the same default-privileges rule applies.
GRANT USAGE ON SCHEMA vectors TO bgpt_reader;
GRANT SELECT ON ALL TABLES IN SCHEMA vectors TO bgpt_reader;
ALTER DEFAULT PRIVILEGES FOR ROLE CURRENT_USER IN SCHEMA vectors
    GRANT SELECT ON TABLES TO bgpt_reader;

-- ---------------------------------------------------------------------------
-- Accounts (milestone 5). User data lives in the `app` schema, which the
-- pipeline and dbt never touch. Its tables come from db/migrations (applied by
-- `make migrate` as the owner). bgpt_app reads and writes them and nothing
-- else; bgpt_reader, which runs Claude's SQL, can't see the schema at all.

SELECT 'CREATE ROLE bgpt_app'
WHERE NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'bgpt_app') \gexec

ALTER ROLE bgpt_app WITH LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT
    CONNECTION LIMIT 20 PASSWORD :'app_password';
ALTER ROLE bgpt_app SET statement_timeout = '5s';
ALTER ROLE bgpt_app SET idle_in_transaction_session_timeout = '10s';
ALTER ROLE bgpt_app SET search_path = app;
GRANT CONNECT ON DATABASE :"DBNAME" TO bgpt_app;

CREATE SCHEMA IF NOT EXISTS app;
REVOKE ALL ON SCHEMA app FROM PUBLIC, bgpt_reader;
REVOKE ALL ON SCHEMA raw, staging, marts, vectors FROM bgpt_app;
GRANT USAGE ON SCHEMA app TO bgpt_app;
GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA app TO bgpt_app;
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA app TO bgpt_app;
ALTER DEFAULT PRIVILEGES FOR ROLE CURRENT_USER IN SCHEMA app
    GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO bgpt_app;
ALTER DEFAULT PRIVILEGES FOR ROLE CURRENT_USER IN SCHEMA app
    GRANT USAGE, SELECT ON SEQUENCES TO bgpt_app;
-- The migration ledger is the owner's business.
SELECT 'REVOKE ALL ON app.schema_migrations FROM bgpt_app'
WHERE to_regclass('app.schema_migrations') IS NOT NULL \gexec

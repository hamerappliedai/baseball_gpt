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
REVOKE TEMPORARY ON DATABASE baseball FROM PUBLIC;
GRANT CONNECT ON DATABASE baseball TO bgpt_reader;

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

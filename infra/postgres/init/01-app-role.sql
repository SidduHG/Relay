-- Runs once, automatically, on first container init (official Postgres
-- images execute every script in /docker-entrypoint-initdb.d in order).
--
-- Creates the role every application connection (API, worker) uses day
-- to day. It deliberately gets neither SUPERUSER nor BYPASSRLS: Postgres
-- unconditionally skips row-level security for both, regardless of
-- ENABLE/FORCE ROW LEVEL SECURITY on the table. POSTGRES_USER — the
-- bootstrap role initdb creates, "relay" in this project — always gets
-- both, which was verified directly: every RLS policy in 0001_initial_schema
-- was silently inert when connected as that role, FORCE included.
CREATE ROLE relay_app LOGIN PASSWORD 'relay_app' NOSUPERUSER NOBYPASSRLS;
GRANT CONNECT ON DATABASE relay TO relay_app;
GRANT USAGE ON SCHEMA public TO relay_app;

-- Migrations run as the bootstrap/owner role, so tables they create
-- don't automatically grant anything to relay_app. This makes every
-- future CREATE TABLE grant it DML rights automatically, so this script
-- never needs editing again as the schema grows.
ALTER DEFAULT PRIVILEGES FOR ROLE relay IN SCHEMA public
    GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO relay_app;

-- =============================================================================
-- create_worker_db_role.sql — Least-privilege PostgreSQL role for Workers
-- =============================================================================
-- Run this on the CENTRAL server's PostgreSQL instance ONCE.
--
-- Usage:
--   docker exec -i barpro-postgres psql -U postgres -d barpro \
--     -v WORKER_DB_PASSWORD="<strong-random-password>" \
--     -f scripts/create_worker_db_role.sql
--
-- Or interactively:
--   docker exec -it barpro-postgres psql -U postgres -d barpro
--   \i /path/to/create_worker_db_role.sql
-- =============================================================================

-- 1. Create the role (idempotent)
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'barpro_worker') THEN
        CREATE ROLE barpro_worker LOGIN PASSWORD :'WORKER_DB_PASSWORD';
        RAISE NOTICE 'Role barpro_worker created.';
    ELSE
        -- Update password if role already exists
        ALTER ROLE barpro_worker PASSWORD :'WORKER_DB_PASSWORD';
        RAISE NOTICE 'Role barpro_worker already exists — password updated.';
    END IF;
END
$$;

-- 2. Allow connection to the database
GRANT CONNECT ON DATABASE barpro TO barpro_worker;

-- 3. Allow usage of the public schema
GRANT USAGE ON SCHEMA public TO barpro_worker;

-- 4. Allow SELECT, INSERT, UPDATE on all current tables
GRANT SELECT, INSERT, UPDATE ON ALL TABLES IN SCHEMA public TO barpro_worker;

-- 5. Allow sequence usage (needed for auto-increment PKs)
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO barpro_worker;

-- 6. Set defaults for future tables (when migrations add new tables)
ALTER DEFAULT PRIVILEGES IN SCHEMA public
    GRANT SELECT, INSERT, UPDATE ON TABLES TO barpro_worker;

ALTER DEFAULT PRIVILEGES IN SCHEMA public
    GRANT USAGE, SELECT ON SEQUENCES TO barpro_worker;

-- 7. Explicitly revoke dangerous permissions
REVOKE CREATE ON SCHEMA public FROM barpro_worker;
REVOKE DELETE ON ALL TABLES IN SCHEMA public FROM barpro_worker;
-- Note: TRUNCATE and DROP TABLE are not granted above, so no need to revoke.

-- 8. Verify
SELECT
    rolname,
    rolcanlogin,
    rolcreatedb,
    rolcreaterole,
    rolsuper
FROM pg_roles
WHERE rolname = 'barpro_worker';

\echo ''
\echo '✅ barpro_worker role configured with least-privilege access.'
\echo '   Workers can SELECT/INSERT/UPDATE but NOT DELETE/CREATE/DROP/TRUNCATE.'
\echo ''
\echo 'Next step: add the password to the Worker .env file:'
\echo '   DATABASE_URL=postgresql+asyncpg://barpro_worker:<password>@<CENTRAL_IP>:5432/barpro'

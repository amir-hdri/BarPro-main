🔒 Fix Hardcoded Default Postgres Password in Configuration

🎯 **What:**
The codebase contained a hardcoded default Postgres password ('postgres') and Redis password ('change_me') in the `.env` file, as well as hardcoded fallback passwords in multiple config files (`docker-compose.node-backend.yml`, `apps/backend/.env.example`, `alembic.ini`, and `scripts/fix_migration_version.py`).

⚠️ **Risk:**
Using default hardcoded passwords like 'postgres' poses a severe security risk. If a database using this default password gets exposed, it allows unauthorized attackers root access to all data, leading to data breaches and potential compromise of the entire system.

🛡️ **Solution:**
- Replaced the hardcoded passwords in `.env` with securely generated random cryptographic strings.
- Replaced the hardcoded 'postgres' password in configuration templates (`apps/backend/.env.example`, `alembic.ini`, `scripts/fix_migration_version.py`) with a placeholder (`<your_secure_password>`).
- Updated `docker-compose.node-backend.yml` to use environment variable interpolation (`${POSTGRES_PASSWORD}`) instead of the hardcoded default password.

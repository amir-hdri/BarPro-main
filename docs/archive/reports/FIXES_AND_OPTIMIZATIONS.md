 # Database Migration Fixes and System Optimizations
 
 ## Critical Issues Fixed
 
 ### 1. Database Migration Failure (DuplicateTableError)
 
 **Root Cause:**
 - Migration `001_initial.py` creates table `waybilltask` with constraint `uq_waybill_task_task_id`
 - Model `app/models_multitenant.py` has `WaybillTask` with table `waybill_tasks_legacy` but **same constraint name**
 - When `app/core/database.py` fallback runs `SQLModel.metadata.create_all()`, it tries to create both tables
 - PostgreSQL rejects duplicate constraint names → **DuplicateTableError**
 
 **Solution:**
 1. **Removed dangerous fallback** in `app/core/database.py`:
    - Fallback `create_all()` only runs on SQLite (safe for fresh DB)
    - On PostgreSQL, fail fast with clear error message
    - Prevents partial schema corruption
 
 2. **Fixed constraint name conflicts**:
    - `app/models_multitenant.py`: Renamed constraints to `uq_waybill_tasks_legacy_*`
    - `app/models.py`: Explicitly set `__tablename__ = "waybilltask"`
    - Created migration `005_fix_constraint_conflicts.py` for existing databases
 
 3. **Added idempotent migration script**:
    - `scripts/init_database.py`: Safe initialization with version checking
    - `scripts/reset_database.sh`: Clean database reset for development
 
 ### 2. Startup Script Issues
 
 **Problems:**
 - No database initialization before backend starts
 - Poor error visibility when backend fails
 - No migration status checking
 
 **Solution:**
 - Updated `scripts/start_system.sh` to run `init_database.py` before backend
 - Added detailed error logging with tail output
 - Better health check logic
 
 ## File Changes Summary
 
 ### Modified Files
 
 1. **app/core/database.py**
    - Removed dangerous `create_all()` fallback on PostgreSQL
    - Added SQLite-only fallback for development
    - Improved error messages with actionable solutions
 
 2. **app/models_multitenant.py**
    - Renamed `WaybillTask` constraints to avoid conflicts:
      - `uq_waybill_task_task_id` → `uq_waybill_tasks_legacy_task_id`
      - `uq_waybill_task_idempotency_key` → `uq_waybill_tasks_legacy_idempotency_key`
 
 3. **app/models.py**
    - Added explicit `__tablename__ = "waybilltask"` to `WaybillTask`
 
 4. **alembic/versions/001_initial.py**
    - Added clarifying comment about legacy table
 
 5. **alembic/versions/002_phase1_rpa_backend.py**
    - Added section comments for better readability
 
 6. **scripts/start_system.sh**
    - Added database initialization step
    - Improved error reporting with log tails
 
 ### New Files
 
 1. **scripts/init_database.py**
    - Idempotent database initialization
    - Checks existing schema before migrations
    - Reports current and final migration versions
    - Safe for both fresh and existing databases
 
 2. **scripts/reset_database.sh**
    - Drops and recreates PostgreSQL database
    - Runs fresh migrations
    - Useful for development/testing
 
 3. **alembic/versions/005_fix_constraint_conflicts.py**
    - Idempotent migration to fix existing databases
    - Renames conflicting constraints safely
    - Checks table/constraint existence before modifying
 
 ## Usage Instructions
 
 ### Fresh Setup
 
 ```bash
 # Start infrastructure
 docker compose up -d postgres redis prometheus
 
 # Initialize database (automatic in start_system.sh)
 python scripts/init_database.py
 
 # Start full system
 ./scripts/start_system.sh
 ```
 
 ### Existing Database with Issues
 
 ```bash
 # Option 1: Reset database (DESTRUCTIVE - loses data)
 ./scripts/reset_database.sh
 
 # Option 2: Run fix migration
 alembic upgrade head
 ```
 
 ### Manual Migration Management
 
 ```bash
 # Check current version
 alembic current
 
 # Upgrade to latest
 alembic upgrade head
 
 # Downgrade one version
 alembic downgrade -1
 
 # Reset to base
 alembic downgrade base
 ```
 
 ## Additional Optimizations
 
 ### Performance Improvements
 
 1. **Database Connection Pooling**
    - Already configured in `create_async_engine`
    - Consider tuning pool size for production
 
 2. **Migration Performance**
    - Migrations now run in worker thread (no event loop blocking)
    - Idempotent checks prevent redundant operations
 
 ### Code Quality
 
 1. **Better Error Handling**
    - Clear error messages with actionable solutions
    - Proper exception chaining with `from exc`
 
 2. **Logging Improvements**
    - Structured logging with extra fields
    - Clear migration status reporting
 
 3. **Documentation**
    - Added inline comments explaining critical logic
    - Documented constraint naming conventions
 
 ## Testing Checklist
 
 - [ ] Fresh database initialization works
 - [ ] Existing database migration works
 - [ ] Backend starts successfully after migration
 - [ ] Frontend connects to backend
 - [ ] No duplicate constraint errors
 - [ ] Rollback migrations work correctly
 - [ ] Reset script works for development
 
 ## Future Improvements
 
 1. **Migration Testing**
    - Add automated tests for migrations
    - Test upgrade/downgrade cycles
 
 2. **Database Backup**
    - Add pre-migration backup script
    - Automated backup before destructive operations
 
 3. **Health Checks**
    - Add database health endpoint
    - Migration version reporting in API
 
 4. **Monitoring**
    - Track migration execution time
    - Alert on migration failures
 
 ## Troubleshooting
 
 ### Backend won't start
 
 1. Check database is running:
    ```bash
    docker compose ps postgres
    ```
 
 2. Check migration status:
    ```bash
    python scripts/init_database.py
    ```
 
 3. Check backend logs:
    ```bash
    tail -f output/backend.log
    ```
 
 ### Migration fails
 
 1. Check PostgreSQL connection:
    ```bash
    psql -h localhost -U postgres -d utcms_rpa
    ```
 
 2. Check alembic version table:
    ```sql
    SELECT * FROM alembic_version;
    ```
 
 3. Reset if needed:
    ```bash
    ./scripts/reset_database.sh
    ```
 
 ### Constraint conflicts
 
 If you still see constraint conflicts:
 
 1. Check for duplicate constraint names:
    ```sql
    SELECT conname, conrelid::regclass 
    FROM pg_constraint 
    WHERE conname LIKE 'uq_waybill%';
    ```
 
 2. Run fix migration:
    ```bash
    alembic upgrade 005_fix_constraint_conflicts
    ```
 
 ## Contact & Support
 
 For issues or questions:
 - Check logs in `output/backend.log` and `output/frontend.log`
 - Review migration history: `alembic history`
 - Check database schema: `\d+ tablename` in psql

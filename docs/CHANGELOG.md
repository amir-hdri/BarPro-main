# Changelog
  
  All notable changes to the UTCMS Automation System.
  
  ## [2.5.0] - 2026-08-10
  
  ### Fixed
  - **Proxy Health Check URL**: Changed target from `barname.utcms.ir` to `https://utcms.ir` — the previous URL redirected causing false health check failures
  - **Scheduler FOR UPDATE Error**: Fixed PostgreSQL `FOR UPDATE SKIP LOCKED` on outer join by moving driver-slot check to a subquery; PostgreSQL rejects `FOR UPDATE` on the nullable side of an outer join
  - **Test Assertions**: Updated proxy health test expectations to match new URL
  
  ### Files Changed
  - `app/api/routes/system.py`
  - `app/automation/proxy_rotator.py`
  - `app/automation/worker_proxy.py`
  - `app/orchestrator/scheduler_service.py`
  - `scripts/verify_system_connections.py`
  - `tests/test_worker_proxy_health.py`
  
  ### Documentation
  - Updated AGENTS.md, ISSUES.md, README.md with latest changes
  
  ---
  
  ## [2.4.0] - 2026-08-02

### Added
- **Security Headers**: Added comprehensive security headers middleware to FastAPI backend including CSP (with frame-ancestors, base-uri, form-action), X-Content-Type-Options, X-Frame-Options, X-XSS-Protection, Referrer-Policy, and Permissions-Policy
- **Permissions-Policy Header**: Added to Nginx configuration to restrict geolocation, microphone, and camera access
- **Enhanced CSP**: Content-Security-Policy now includes `frame-ancestors 'none'`, `base-uri 'self'`, and `form-action 'self'` for better security

### Changed
- **Redis Connection Pool**: Configured all Redis clients (redis.py, rate_limiter.py, circuit_breaker.py) with proper timeout and retry settings:
  - `socket_connect_timeout: 5`
  - `socket_timeout: 5`
  - `retry_on_timeout: True`
  - `health_check_interval: 30`
  - `max_connections: 10-20`
- **Nginx DNS Resolution**: Configured dynamic upstream resolution using Docker internal DNS (127.0.0.11) with 30s cache for container IP changes
- **Phone Validation**: Improved error messages with examples for driver, sender, and receiver phone numbers in waybillSchema.ts
- **Exception Handling**: Added logging to `_safe_json_payload` in _helpers.py to prevent silent exception swallowing

### Removed
- **Hardcoded Secrets**: Removed fallback hardcoded JWT_SECRET and DRIVER_ENCRYPTION_KEY from GitHub Actions ci-cd.yml workflow

### Security
- All backend API responses now include security headers for direct access scenarios
- Nginx security headers enhanced with additional directives
- Redis clients now have proper connection pool settings for better reliability

### Documentation
- Updated all documentation files (ISSUES.md, README.md, AGENTS.md, CRITICAL_RULES.md) with latest changes
- Added Persian translations and examples where applicable

---

  ## [2.3.0] - 2026-07-18

 ### Added
 - **Driver submission lock**: concurrent waybill submissions for the same driver are now serialized (`rpa_runtime.submit_lock_key` + `RPA_LOCK_TTL_SECONDS`). A conflicting job is parked in `WAITING_RETRY` with `error_category=driver_submission_in_progress` instead of double-submitting.
 - **Idempotency / skip-on-complete**: jobs already holding a UTCMS `tracking_code` in `result_json` are skipped on re-execution. A `SUCCESS` status without a tracking code is demoted to `NEEDS_REVIEW` (`error_category=submission_unconfirmed`).
 - **New job statuses**: `OTP_BACKOFF` and `NEEDS_REVIEW` are now fully wired through the queue-depth counters and the frontend status badges.
 - **Fuel inquiry claim-on-execute**: the Celery/fuel worker now atomically claims a `pending` inquiry (`UPDATE ... WHERE status='pending'`) before scraping, preventing double processing.
 - **Fuel inquiry de-duplication**: migration `018_fuel_inquiry_active_unique` adds a partial unique index `uq_fuel_inquiries_active_period` (one active inquiry per driver+period); duplicate/legacy rows are reconciled to `failed` on upgrade. The API now returns HTTP `409` on a conflicting active inquiry.
 - **Redis-cached queue depth**: status transitions use `HINCRBY` (`_adjust_queue_depth`) seeded from the DB at startup, eliminating the per-transition full-table scan.
 - **SSRF guard for `RPA_PROXIES`**: proxy URLs injected via the `RPA_PROXIES` env var are validated through `ProxyRotator._is_safe_proxy_url` before the `/proxies/health` endpoint uses them.
 - **Frontend**: job cards and dashboard now display the UTCMS `tracking_code` (from `result_json`); admin job cards show `error_category` in Persian; the Admin Reports failure-analysis chart and CSV now render Persian category labels; the fuel page shows a friendly Persian message on HTTP `409` (duplicate active inquiry).
 - Added `errorCategoryLabel()` and `trackingCodeFromResult()` helpers in `apps/web/src/lib/format.ts`.

 ### Changed
 - **JWT stack swapped**: `python-jose` replaced with `PyJWT[crypto]` to drop the vulnerable `ecdsa` transitive dependency (no upstream fix available). `JWTError` aliased to `jwt.exceptions.PyJWTError` in `security.py` and `auth_multitenant.py`.
 - Bumped vulnerable dependencies: `Pillow` 12.2.0 → 12.3.0, `torch` 2.12.1 → 2.13.0, `tensorflow` ≥2.18.0, `opencv-python-headless` ≥4.11.0, `setuptools` 81.0.0 → 82.x (below torch's upper bound).
 - `requirements-dev.txt` pins relaxed from `==` to `>=` so Dependabot can auto-update dev tooling.
 - Added `.github/dependabot.yml` for weekly pip/npm/github-actions updates.

 ### Removed
 - Deleted legacy/deprecated `app/frontend/` (unused; superseded by `apps/web`) which carried 7 npm vulnerabilities.
 - Removed stale `apps/web/yarn.lock` (5 npm vulns); `package-lock.json` is now the single source of truth and is clean.
 - Removed `.playwright-headless` Chromium binaries from git tracking (regenerated via `playwright install`; added to `.gitignore`).

 ### Security
 - `pip-audit` and `npm audit` (apps/web) now report **no known vulnerabilities**. GitHub Dependabot no longer flags the default branch.

 ---

 ## [2.2.0] - 2026-07-09

### Added
- Added **Pre-flight Proxy Health Checks** (`check_proxy_health`) before worker Playwright browser sessions to verify Squid proxy connectivity.
- Added `/proxies/health` latency and health check endpoint for monitoring active Squid proxy configurations.
- Added unified user/admin dependency context (`get_current_user_or_admin`) allowing Master Admin to view and manage resources globally across all tenants while ensuring data isolation for client roles.
- Enhanced Admin Reports page with live **SVG line charts** for success/failure weekly trends, **SVG horizontal bar charts** for error category distributions, Persian tooltips, and CSV download export options.
- Added Persian-digit tracking codes formatting (`UTC-YYMM-ID`) for fuel inquiries.
- Added integration tests for worker proxy health checks.

### Changed
- Refactored multitenant list/detail services (`list_jobs`, `get_job`, `get_job_timeline`, `list_inquiries`, `get_inquiry`) to conditionally accept and process admin roles, injecting client metadata where appropriate.
- Client responses for jobs and timelines now strip `last_error` and detailed `timeline_entries` to prevent internal system detail exposure.

---

## [2.1.0] - 2026-07-08

 ### Added
 - Added PyTorch fuel CAPTCHA solver assets and provider option `pytorch_fuel`.
 - Added migrations `014_add_year_month_to_fuel_inquiries` and `015_add_client_subscription_dates`.
 - Added `AUTH_COOKIE_SECURE` to control secure httpOnly auth cookies for HTTP vs HTTPS deployments.

 ### Changed
 - Frontend Dockerfile now performs a full multi-stage Next.js build inside Docker; `.next/standalone` no longer has to exist before upload.
 - Backend Docker build selects `tensorflow-cpu` on x86_64 servers and `tensorflow` on non-x86 builds for local ARM compatibility.
 - Frontend auth now relies on httpOnly cookies for JWT transport and no longer sends Bearer tokens from localStorage.
 - PWA tooling moved to development/build dependencies; production npm audit now passes with `npm audit --omit=dev`.

 ### Fixed
 - Fixed production HTTP login regression caused by forcing `Secure` cookies before HTTPS was enabled.
 - Fixed Alembic migration downgrade idempotency for the new fuel inquiry and client subscription columns.
 - Fixed generated artifact handling by ignoring local datasets, screenshots, model cache, tarballs, and PWA generated files.

 ### Verified
 - `npm run build`
 - `npm audit --omit=dev`
 - `docker compose -f compose/backend.yml build backend`
 - `docker compose -f compose/web.yml build frontend`
 - Focused auth/config/schedule tests passed.

 ---

 ## [2.0.1] - 2026-04-23
 
 ### 🔥 Critical Fixes
 
 #### Database Migration Issues
 - **Fixed**: `DuplicateTableError` when backend starts with PostgreSQL
 - **Root cause**: Dangerous fallback to `SQLModel.metadata.create_all()` after migration failures
 - **Solution**: 
   - Removed `create_all()` fallback on PostgreSQL (only allowed on SQLite)
   - Fixed constraint name conflicts between `waybilltask` and `waybill_tasks_legacy` tables
   - Added idempotent migration `005_fix_constraint_conflicts.py`
 
 #### Startup Script Issues
 - **Fixed**: Backend fails silently without clear error messages
 - **Solution**:
   - Added database initialization step before backend starts
   - Improved error logging with tail output
   - Better health check logic
 
 ### ✨ New Features
 
 #### Management Scripts
 - `scripts/init_database.py` - Idempotent database initialization with version checking
 - `scripts/reset_database.sh` - Clean database reset for development
 - `scripts/check_health.sh` - Comprehensive system health check
 - `scripts/stop_system.sh` - Graceful system shutdown
 - `scripts/view_logs.sh` - Unified log viewing interface
 - `scripts/test_system.sh` - Automated system testing
 
 #### Documentation
 - `QUICK_START.md` - Quick start guide for new users
 - `FIXES_AND_OPTIMIZATIONS.md` - Detailed technical documentation of fixes
 - `CHANGELOG.md` - This file
 - Updated `README_FA.md` with new features and troubleshooting
 
 ### 🔧 Improvements
 
 #### Code Quality
 - Added explicit `__tablename__` to models for clarity
 - Improved error messages with actionable solutions
 - Better structured logging with extra fields
 - Added inline comments explaining critical logic
 
 #### Database
 - Constraint names now follow clear naming convention
 - Migrations are now idempotent (safe to run multiple times)
 - Better migration error handling
 - Version tracking and reporting
 
 #### Developer Experience
 - One-command system startup: `./scripts/start_system.sh`
 - Easy log access: `./scripts/view_logs.sh follow`
 - Quick health checks: `./scripts/check_health.sh`
 - Automated testing: `./scripts/test_system.sh`
 
 ### 📝 Changed Files
 
 #### Modified
 - `app/core/database.py` - Removed dangerous fallback, improved error handling
 - `app/models_multitenant.py` - Fixed constraint name conflicts
 - `app/models.py` - Added explicit table name
 - `alembic/versions/001_initial.py` - Added clarifying comments
 - `alembic/versions/002_phase1_rpa_backend.py` - Added section comments
 - `scripts/start_system.sh` - Added database initialization step
 - `README_FA.md` - Updated with new features and documentation
 
 #### Added
 - `scripts/init_database.py` - Database initialization script
 - `scripts/reset_database.sh` - Database reset script
 - `scripts/check_health.sh` - Health check script
 - `scripts/stop_system.sh` - System stop script
 - `scripts/view_logs.sh` - Log viewing script
 - `scripts/test_system.sh` - System testing script
 - `alembic/versions/005_fix_constraint_conflicts.py` - Fix migration
 - `QUICK_START.md` - Quick start guide
 - `FIXES_AND_OPTIMIZATIONS.md` - Technical documentation
 - `CHANGELOG.md` - This changelog
 
 ### 🐛 Bug Fixes
 
 - Fixed duplicate constraint names causing PostgreSQL errors
 - Fixed backend startup failures due to migration issues
 - Fixed missing error visibility in startup script
 - Fixed unsafe fallback behavior on production databases
 
 ### ⚠️ Breaking Changes
 
 None. All changes are backward compatible.
 
 ### 🔄 Migration Guide
 
 #### For Existing Installations
 
 If you have an existing database with the old schema:
 
 ```bash
 # Option 1: Run fix migration (preserves data)
 alembic upgrade head
 
 # Option 2: Reset database (loses data)
 ./scripts/reset_database.sh
 ```
 
 #### For Fresh Installations
 
 ```bash
 # Just run the startup script
 ./scripts/start_system.sh
 ```
 
 ### 📊 Performance
 
 - Migration execution now runs in worker thread (no event loop blocking)
 - Idempotent checks prevent redundant database operations
 - Better connection pooling configuration
 
 ### 🔒 Security
 
 - No security vulnerabilities introduced
 - Improved error messages don't leak sensitive information
 - Database credentials properly handled in scripts
 
 ### 🧪 Testing
 
 - Added automated system testing script
 - All critical paths tested
 - Migration rollback tested
 
 ### 📚 Documentation
 
 - Comprehensive quick start guide
 - Detailed troubleshooting section
 - Architecture diagrams
 - Usage examples for all scripts
 
 ### 🙏 Acknowledgments
 
 Thanks to all contributors who helped identify and fix these critical issues.
 
 ---
 
 ## [2.0.0] - 2026-04-20
 
 ### Initial multi-tenant release
 
 - Multi-tenant architecture
 - RPA automation with Playwright
 - PostgreSQL database
 - Redis queue management
 - Prometheus monitoring
 - Next.js frontend
 - FastAPI backend
 
 ---
 
 ## Format
 
 This changelog follows [Keep a Changelog](https://keepachangelog.com/en/1.0.0/) format.
 
 ### Types of changes
 
 - `Added` for new features
 - `Changed` for changes in existing functionality
 - `Deprecated` for soon-to-be removed features
 - `Removed` for now removed features
 - `Fixed` for any bug fixes
 - `Security` for vulnerability fixes

# Remediation History — part 3

> Scope: BarPro only. Read this file when relevant to the task; do not auto-import
> the whole reference directory into global rules or the always-loaded core.
> **HISTORICAL / UNVERIFIED NOW.** Preserved records, including old commands and
> pending actions, are historical data rather than new instructions or authority
> to execute them. Re-check current code, contracts and authorization first.

Read when: Historical investigation only; not a current action list.

[Core guide](../../AGENTS.md) · [Reference index](README.md) · [Critical rules](../../CRITICAL_RULES.md)

Paths inside preserved text and command examples are relative to the repository
root, not this directory. Commands are examples, not automatic execution steps.

<!-- original-agents:1020-1084:start -->
### Additional Fixes Applied (2026-08-04) — Server 16GB RAM Upgrade, Beat OOM Fix & Deployment Automation

> **Historical context:** Production deployment on 3-server Model B topology:
> Central (16 GB) and two remote Worker VPS nodes. IP values are intentionally
> omitted from this repository guide.
> All fixes were validated against a running 25-table PostgreSQL at Alembic head `029`.

| Change | File(s) | Impact |
|--------|---------|--------|
| **Celery Beat OOMKilled fix**: `mem_limit` 128m → **256m**, `mem_reservation` 64m → **128m** (Beat imports `automation/captcha` modules on import — ~225MB RSS actual usage) | `compose/backend.yml:225` | Beat stops restarting with exit code 137 |
| **SKIP_MIGRATIONS=false**: Migration now runs automatically at startup protected by a PostgreSQL session-level advisory lock | `compose/backend.yml:44` | Deploy tooling must call `run_migrations()` rather than raw Alembic |
| **Alembic 027 column widening**: `ALTER TABLE alembic_version ALTER COLUMN version_num TYPE VARCHAR(255)` — default is VARCHAR(32) but revision `027_add_fuel_inquiry_error_category` is 35 chars | `alembic/versions/027_add_fuel_inquiry_error_category.py` | Migrations no longer fail with `value too long for type character varying(32)` |
| **Alembic 029 CONCURRENT index fix**: `op.execute("COMMIT")` before `CREATE INDEX CONCURRENTLY IF NOT EXISTS` (can't run inside Alembic transaction); fixed `down_revision = "028_submission_unconfirmed_category"` | `alembic/versions/029_add_waybill_jobs_optimization_indexes.py` | 3 optimization indexes created successfully |
| **Playwright CDN override (superseded)**: historical regional setting removed; Dockerfile and Compose now use the official Playwright CDN | `Dockerfile`, `compose/backend.yml` | Chromium downloads during Docker build/runtime |
| **Worker Node fixes**: local `image: barpro_backend:latest` (not GHCR), `env_file: [../.env]`, fast Redis+proc healthcheck (replaces slow `celery inspect ping` which timed out at 11–17s due to central Redis latency), `squid:host-gateway` extra_hosts | `compose/worker-node.yml` | Remote workers 2 & 3 start and stay healthy |
| **RAM upgrade for 16GB server**: PostgreSQL 1g→**1.5g**, Redis 256m→**512m** (+`maxmemory 400mb`), Backend API 256m→**512m**, Worker 1 2.5g→**3g**, Frontend 512m→**1g**, Nginx 256m→**512m** | `compose/infra.yml`, `compose/backend.yml`, `compose/web.yml` | Smooth UI, faster API response, more Chrome/PyTorch headroom |
| **manage.sh improvements**: +`beat-restart` (force-recreate Beat), +`logs [service]` (live log tail), fixed `backup-db` DB name from env, improved `deploy` (build+up+migrate+health) | `manage.sh` | Operational convenience |
| **New deploy script** `scripts/quick_deploy_central.sh`: 10-step fully automated central server deploy (pull → build → beat restart → web → monitoring → migrate → verify) | `scripts/quick_deploy_central.sh` | One-command deploy |
| **New setup script** `scripts/setup_worker.sh`: automated worker node setup from scratch (Docker install → config → build → up → verify registry) | `scripts/setup_worker.sh` | Reproducible worker deployment |
| **.env.example completed**: Added `WORKER_ID`, `WORKER_IP_INDEX`, `WORKER_PROXY_PORT`, `CENTRAL_IP`, `GRAFANA_ADMIN_USER/PASSWORD`, `GRAFANA_ROOT_URL`, `AUTH_COOKIE_SECURE` | `.env.example` | Template covers all required variables |
| **Volume permissions fix** (server action): `chown -R 10001:10001 /var/lib/docker/volumes/barpro_runtime_data/_data/` + mkdir auth/screenshots/output | Applied on central server | Backend starts without PermissionError |

> **Historical deployment snapshot (2026-08-04; not current evidence):**
> - PostgreSQL: `barpro_runtime_data` at Alembic head `029` (25 tables)
> - Workers 2 & 3: healthy, registered in `worker_registry`
> - Celery Beat: `mem_limit=256m` — OOM resolved
> - Frontend + Nginx: mem_limit=1g+512m
> - All services tested healthy via `manage.sh health`

---

*Historical snapshot dated 2026-08-04; do not use its test/deployment status as
current runtime evidence.*

---

### Additional Fixes Applied (2026-08-08) — Soft-Cancel Intent Sync, Proxy Fail-Closed, Scheduler Enforcement & CI Fixes

| Change | File(s) | Impact |
|--------|---------|--------|
| **Historical soft-cancel implementation (superseded)**: an earlier `delete_job` cancelled intents. The current API contract is permanent DELETE; do not implement cancellation from this changelog entry. | `app/services/waybill_job_service.py`, `app/orchestrator/dispatcher_service.py` | Historical context only; current route/service code is authoritative. |
| **Proxy fail-closed (production)**: New `ProxyUnavailableError` + `_proxy_fail_closed()` in `worker_proxy`. In production, unreachable/unset proxy raises instead of falling back to direct connection. Dev mode remains fail-open. `_claim_and_execute` / `_claim_and_reconcile` catch and map to `TRANSIENT_INFRA_ERROR` → `WAITING_RETRY`. `classify_exception` maps proxy keywords to retryable. | `app/automation/worker_proxy.py`, `app/workers/waybill_worker.py`, `app/core/error_taxonomy.py` | Prevents silent direct-connection fallback that bypasses proxy rotation/anti-bot; failed proxy now schedules retry with correct error category. |
| **Scheduler enforcement**: Per-job tenant/driver/quota checks before scheduling: client ACTIVE + subscription window, driver ACTIVE/READY, tenant in-flight < `max_concurrent_tasks`, tenant daily < `max_daily_tasks`. Caches client/driver lookups and counts per loop. | `app/orchestrator/scheduler_service.py` | Prevents scheduling jobs for suspended tenants, inactive drivers, or over-quota tenants. |
| **CI fixes**: Created missing `requirements-dev.txt` (pytest, ruff, black, mypy, aiosqlite); fixed indentation in `ci-cd.yml` step "Run Unit Tests". | `requirements-dev.txt`, `.github/workflows/ci-cd.yml`, `.github/workflows/ci-test.yml` | CI pipeline no longer fails on missing deps / YAML syntax. |
| **Frontend types**: Removed `access_token` from `AuthLoginResponse` / `AdminLoginResponse` — JWT now httpOnly cookie only. | `apps/web/src/lib/types.ts` | Aligns types with cookie-based auth; no token leakage to localStorage. |
| **String import fix**: Added missing `from sqlalchemy import String` in `waybill_job_service` (pre-existing bug in plate-number search filter). | `app/services/waybill_job_service.py` | Fixes `NameError` at runtime when plate filter is used. |
| **Test updates**: `test_redis_unavailable` mocks `get_worker_proxy_url`; `test_worker_proxy_and_rotator` tests both dev fail-open and prod fail-closed; `test_reconciliation_service` sets `ENVIRONMENT=development`. | `tests/chaos/test_redis_unavailable.py`, `tests/test_worker_proxy_and_rotator.py`, `tests/test_reconciliation_service.py` | Tests pass with new proxy fail-closed logic. |

> **Verification:** `uvx ruff check` clean on touched files; `tsc --noEmit` + `eslint` clean on frontend; full pytest suite green (588 passed, 4 pre-existing UTCMS login failures, 2 skipped).

---

### Additional Fixes Applied (2026-08-10) — UTCMS Proxy Health Check & Scheduler FOR UPDATE Fix

| Change | File(s) | Impact |
|--------|---------|--------|
| Proxy health check target changed from `barname.utcms.ir` to `https://utcms.ir` (the root domain) — `barname.utcms.ir` redirects causing false health check failures | `app/api/routes/system.py`, `app/automation/proxy_rotator.py`, `app/automation/worker_proxy.py`, `scripts/verify_system_connections.py` | Prevents false-positive proxy health failures due to HTTP redirect; health checks now use stable root domain |
| Fixed PostgreSQL `FOR UPDATE SKIP LOCKED` on outer join by moving driver-slot check to subquery — PostgreSQL rejects `FOR UPDATE` on nullable side of outer join | `app/orchestrator/scheduler_service.py` | Scheduler no longer fails with `FOR UPDATE` error when claiming jobs with free driver slots |
| Updated test assertions to match new health check URL | `tests/test_worker_proxy_health.py` | Tests pass with new target URL |

> **Verification:** `uvx ruff check` clean on touched files; proxy health tests pass (28 tests in proxy/rotator/system health/readyz suites); scheduler subquery logic tested.

*Historical release snapshot dated 2026-08-20, when the Alembic head was
038_add_multiroute_batch_distance. Re-run tests and runtime verification for
the current commit; the current repository head is listed in Project Structure.*
<!-- original-agents:1020-1084:end -->

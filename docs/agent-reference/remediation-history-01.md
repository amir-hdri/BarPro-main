# Remediation History — part 1

> Scope: BarPro only. Read this file when relevant to the task; do not auto-import
> the whole reference directory into global rules or the always-loaded core.
> **HISTORICAL / UNVERIFIED NOW.** Preserved records, including old commands and
> pending actions, are historical data rather than new instructions or authority
> to execute them. Re-check current code, contracts and authorization first.

Read when: Historical investigation only; not a current action list.

[Core guide](../../AGENTS.md) · [Reference index](README.md) · [Critical rules](../../CRITICAL_RULES.md)

Paths inside preserved text and command examples are relative to the repository
root, not this directory. Commands are examples, not automatic execution steps.

<!-- original-agents:0778-0932:start -->
## Historical Remediation Log (see ISSUES.md for current work)

> Status marks below describe repository changes at the time recorded. They do
> not prove that a production server has deployed them; server state always
> requires a timestamped runtime check.

### Repository fixes and follow-ups

| # | Fix | Status |
|---|-----|--------|
| 1 | Rotate leaked credentials (`PLACEHOLDER_SSH_PASSWORD` in code) | ✅ Previous leaked password → `PLACEHOLDER_SSH_PASSWORD` (rotate actual server password yourself) |
| 2 | Purge `.env` from git history | ✅ `git filter-repo` done — `.env` and `celerybeat-schedule.db` removed from all commits |
| 3 | Fix `zod/v4` import → `zod` | ✅ `apps/web/src/schemas/waybillSchema.ts:1` |
| 4 | Fix `ArrowLeftOnRectangleIcon` | ✅ `apps/web/src/components/layout/Header.tsx:3` |
| 5 | Add HTTPS to Nginx | ⬜ Config ready (`infra/nginx/nginx.conf` + `http-server.conf` + compose volume) — uncomment `listen 443` and `ssl` volume after cert install |
| 6 | Remove `privileged: true` | ✅ `cap_add: [SYS_ADMIN, NET_ADMIN]` + `security_opt: [no-new-privileges:true]` on all containers |
| 7 | Fix rate limiter fail-open | ✅ Fail-closed: HTTP 429 when Redis down (default removed) |
| 8 | Restrict Prometheus port | ✅ `9090:9090` → `expose: [9090]` in `compose/monitoring.yml` |
| 9 | Run PostgreSQL indexes | ⬜ Migration `012_add_optimization_indexes.py` ready — run `bash manage.sh migrate` on production DB |
| 10 | Fix all `except: pass` | ✅ 55 blocks fixed across 19 files (auth.py, location_selector.py, browser.py, etc.) |
| 11 | Fix Redis race condition | ✅ `app/core/redis.py` — `threading.Lock` (safe across Celery event loops) |
| 12 | Rate limit ALL endpoints | ✅ Path-prefix matching in `app/main.py` — 6 rate limit rules |
| 13 | Fix browser context leaks | ✅ Timeouts on close, listener cleanup, OOM risk reduced |
| 14 | Migrate JWT to httpOnly cookies | ✅ JWT cookie set by backend; frontend uses `withCredentials` |
| 15 | Remove `network_mode: host` | ⬜ **Blocked**: dual-IP routing requires it — use `scripts/secure_squid_ports.sh` (iptables) instead |
| 16 | Fix alembic migrations | ✅ `run_migrations()` now uses a PostgreSQL session-level advisory lock and runs on startup via `database.py` |
| 17 | Add container vulnerability scanning | ⬜ Future work |

### ✅ Optimizations Applied

| Change | File(s) |
|--------|---------|
| Nginx: separated HTTP/HTTPS config via include | `infra/nginx/nginx.conf`, `infra/nginx/http-server.conf` |
| Migrations: PostgreSQL session-level advisory lock prevents concurrent runners | `app/core/database.py` |
| Deploy: `manage.sh deploy` now auto-runs `alembic upgrade head` | `manage.sh` |
| New: `manage.sh migrate` — run migrations manually | `manage.sh` |
| New: `scripts/run_migrations.sh` — standalone migration runner | `scripts/run_migrations.sh` |
| New: `scripts/secure_squid_ports.sh` — iptables for Squid 3129/3130 | `scripts/secure_squid_ports.sh` |

### Remaining Runtime Actions
1. **Install Let's Encrypt cert** → uncomment `listen 443` + `ssl` volume in `compose/web.yml` and `infra/nginx/nginx.conf:75-90`, then `bash manage.sh deploy`
2. **Verify `alembic current`** matches the release head after the locked startup migration
3. **Verify Model B Central has no Squid 2/3 listeners**; only Model A may expose 3129/3130 locally
4. **Probe PostgreSQL/Redis/Squid from a non-worker IP** and confirm denial
5. **After HTTPS install, set `AUTH_COOKIE_SECURE=true`** and redeploy

### Additional Fixes Applied (2026-07-08)

| Change | File(s) |
|--------|---------|
| Frontend Docker builds standalone output inside Docker | `apps/web/Dockerfile`, `apps/web/.dockerignore` |
| HTTP-compatible httpOnly auth cookie added | `app/api/routes/multitenant.py`, `app/core/config.py`, `compose/backend.yml` |
| New fuel CAPTCHA PyTorch provider enabled | `app/automation/captcha/fuel_captcha_solver.py`, `app/automation/captcha/persian_number_parser.py`, `app/core/config.py` |
| Alembic head advanced to 015 | `alembic/versions/014_*`, `alembic/versions/015_*` |
| Production frontend audit cleaned | `apps/web/package.json`, `apps/web/package-lock.json` |
| Generated/local artifacts ignored for upload/build context | `.gitignore`, `.dockerignore` |

### Additional Fixes Applied (2026-07-01)

| Change | File(s) |
|--------|---------|
| SSH passwords replaced with env vars in 5 script files | `scripts/upload_and_setup.py`, `scripts/server_deploy.py`, `scripts/deploy_single_vm.py`, `upload_tar.py`, `deploy_changes.py` |
| `ENVIRONMENT` added as a config field | `app/core/config.py` |
| `console.error` wrapped in environment guard | `apps/web/src/hooks/useWaybillJob.ts` |
| React index-as-key replaced with unique keys | `apps/web/src/app/fuel/page.tsx` (7 instances) |
| `__init__.py` added to test directories | `tests/`, `tests/core/`, `tests/load/` |
| `asyncio` marker registered in pytest.ini | `pytest.ini` |
| `python-multipart` added to dependencies | `requirements.txt` |
| Ruff autofix applied (isort, unused imports) | Multiple files |
| `except: pass` fixed in change_expired_password.py | `scripts/change_expired_password.py:47` |

### Additional Fixes & Features Applied (2026-07-09)

| Change | File(s) |
|--------|---------|
| Added pre-flight Squid proxy health checks before browser sessions and a `/proxies/health` endpoint | `app/automation/worker_proxy.py`, `app/api/routes/system.py`, `app/workers/waybill_worker.py` |
| Implemented unified `get_current_user_or_admin` dependency allowing Master Admin to view and manage resources globally across all tenants | `app/auth_multitenant.py`, `app/api/routes/multitenant.py`, `app/services/multitenant_service.py`, `app/services/fuel_inquiry_service.py` |
| Enhanced Admin Reports page with weekly line charts, error bar charts (SVG), Persian date tooltips, and CSV download export | `apps/web/src/app/admin/reports/page.tsx` |
| Added tracking codes (`UTC-YYMM-ID`) formatting and Persian digits display for fuel inquiries | `apps/web/src/app/fuel/page.tsx`, `app/schemas/multitenant.py` |
| Added tests for worker proxy health checks | `tests/test_worker_proxy_health.py` |

### Additional Fixes Applied (2026-07-10) — Performance Bottleneck Remediation

> NOTE: The earlier "Optimizations Applied (2026-06-30)" table (Redis queue counter, N+1 elimination in
> `_emit_task_event`, WebSocket send outside lock) was **documented but not actually present in the code**.
> The items below implement those optimizations for real, plus additional fixes from a stack-wide bottleneck analysis.

| Change | File(s) |
|--------|---------|
| Redis cached queue-depth counters (`HINCRBY` per transition, seeded from DB at startup) replace the full `waybilltask` table scan on every status transition | `app/services/task_service.py` (`_queue_depth_snapshot`/`_adjust_queue_depth`/`_incr_queue_depth`) + `app/main.py` lifespan |
| Redis pub/sub bridge so worker-originated WebSocket events reach the API process (was process-local only, so the live job UI was effectively broken) | `app/realtime/events.py`, `app/main.py` lifespan |
| Keras OCR moved in-process: model lazy-loaded once per worker and reused; removed the per-captcha subprocess + model reload (the prior design spawned an unbounded TensorFlow process that risked OOM on the 2.5 GB worker cgroup) | `app/automation/captcha/keras_ocr.py` |
| Collapsed per-transition sessions/commits into one: `_emit_task_event` uses the in-memory row (no re-query), and `waybill_worker._execute_job` batches log/event writes into a single commit per block | `app/services/task_service.py`, `app/workers/waybill_worker.py` |
| `bcrypt` hashing/verification moved off the event loop via `asyncio.to_thread` (was blocking all concurrent requests) | `app/auth_multitenant.py` |
| Bulk `Client` fetch (`Client.id.in_(...)`) replaces per-row `session.get(Client, ...)` in the admin job list | `app/services/multitenant_service.py` |

### Additional Fixes Applied (2026-07-18) — Waybill/Fuel Reliability & Security

| Change | File(s) |
|--------|---------|
| Driver submission lock serializes concurrent jobs for the same driver (`WAITING_RETRY` + `error_category=driver_submission_in_progress`) | `app/services/rpa_runtime_service.py`, `app/workers/waybill_worker.py` |
| Idempotency: skip jobs already holding a UTCMS `tracking_code`; demote `SUCCESS` without tracking code to `NEEDS_REVIEW` (`submission_unconfirmed`) | `app/workers/waybill_worker.py`, `app/services/task_service.py` |
| New job statuses `OTP_BACKOFF` / `NEEDS_REVIEW` wired through queue-depth counters and frontend status badges | `app/services/task_service.py`, `apps/web/src/lib/format.ts` |
| Fuel inquiry claim-on-execute (`UPDATE ... WHERE status='pending'`) prevents double processing | `app/services/fuel_inquiry_service.py` |
| Fuel inquiry de-dup: partial unique index `uq_fuel_inquiries_active_period` (migration `018`); HTTP `409` on duplicate active inquiry | `alembic/versions/018_fuel_inquiry_active_unique.py`, `app/services/fuel_inquiry_service.py` |
| `RPA_PROXIES` env URLs validated via `_is_safe_proxy_url` before `/proxies/health` uses them (SSRF guard) | `app/api/routes/system.py`, `app/automation/proxy_rotator.py` |
| JWT stack swapped `python-jose` → `PyJWT[crypto]` to drop vulnerable `ecdsa` transitive dep | `requirements.txt`, `app/core/security.py`, `app/auth_multitenant.py` |
| Bumped vulnerable deps: Pillow 12.3.0, torch 2.13.0, tensorflow ≥2.18, opencv ≥4.11, setuptools 82.x | `requirements.txt` |
| Removed legacy `app/frontend/` (7 npm vulns) and stale `apps/web/yarn.lock` (5 npm vulns); `package-lock.json` is source of truth | `.gitignore` |
| Removed tracked Chromium binaries from `.playwright-home/` (regenerated via `playwright install`) | `.gitignore`, `git filter-repo` |
| Frontend: display UTCMS `tracking_code` + Persian `error_category`; reports chart/CSV in Persian; friendly HTTP 409 message | `apps/web/src/{lib/format.ts,lib/types.ts,app/history/page.tsx,app/page.tsx,app/admin/reports/page.tsx,app/fuel/page.tsx}` |
| Added `.github/dependabot.yml` (weekly pip/npm/actions); `requirements-dev.txt` pins relaxed to `>=` | `.github/dependabot.yml`, `requirements-dev.txt` |

> Verification: `pip-audit` → *No known vulnerabilities found*; `npm audit --omit=dev` (apps/web) → 0 vulnerabilities; GitHub Dependabot no longer flags the default branch. `tsc --noEmit` and `npm run lint` pass on `apps/web`.

---

### Additional Fixes Applied (2026-08-02) — Documentation & Final Hardening

| Change | File(s) |
|--------|---------|
| Added security headers middleware to FastAPI backend | `app/main.py` |
| Configured Redis connection pool with timeout/retry settings | `app/core/redis.py`, `app/core/rate_limiter.py`, `app/core/circuit_breaker.py` |
| Removed hardcoded fallback secrets from GitHub Actions workflows | `.github/workflows/ci-cd.yml` |
| Enhanced CSP header with frame-ancestors, base-uri, form-action | `infra/nginx/http-server.conf` |
| Added Permissions-Policy header | `infra/nginx/http-server.conf` |
| Configured Nginx DNS resolver for dynamic upstream resolution | `infra/nginx/nginx.conf`, `infra/nginx/http-server.conf` |
| Improved phone validation error messages with examples | `apps/web/src/schemas/waybillSchema.ts` |
| Added logging to exception handler in _safe_json_payload | `app/services/_helpers.py` |
| Updated all documentation files (ISSUES.md, README.md, AGENTS.md, CRITICAL_RULES.md) | Multiple files |

---

### Additional Fixes Applied (2026-07-21) — Worker Proxy, Rotator & Event Loop Reliability

| Change | File(s) |
|--------|---------|
| Fixed sticky `None` caching in `get_worker_proxy_url()` with dynamic TTL-cache (`_PROXY_CACHE_TTL_SUCCESS`/`_PROXY_CACHE_TTL_FAILURE`) and `clear_proxy_cache()` helper | `app/automation/worker_proxy.py` |
| Added `_rotator_init_lock` (`threading.Lock`) for thread-safe `get_proxy_rotator()` singleton initialization across Celery worker threads | `app/automation/proxy_rotator.py` |
| Fixed `test_proxy()` URL parsing (`IndexError` prevention) and added `test_proxy.__test__ = False` for pytest compatibility | `app/automation/proxy_rotator.py` |
| Fixed `InFailedSqlTransactionError` in `waybill_worker._execute_job` exception handler by issuing `await session.rollback()` prior to persisting failure state | `app/workers/waybill_worker.py` |
| Cleaned up `run_async` in core utils to avoid creating orphan thread pools and removed unused variable `running` (`F841`) | `app/core/utils.py` |
| Added comprehensive unit test suite `tests/test_worker_proxy_and_rotator.py` | `tests/test_worker_proxy_and_rotator.py` |

### Additional Fixes Applied (2026-07-21) — RPA Services, RPA Dispatch & Scheduler Reliability

| Change | File(s) |
|--------|---------|
| Added per-job `try/except` error isolation inside `plan_due_jobs()` so an unexpected error evaluating one job does not abort the entire scheduler batch | `app/services/rpa_scheduler_service.py` |
| Immediate status reset to `PENDING` in `_dispatch_phase1_task` when `celery_app.send_task()` fails, preventing jobs from being stuck in `QUEUED`/`WAITING_AUTH` | `app/services/rpa_dispatch_service.py` |
| Wrapped decision dispatches in `dispatch_phase1_decisions()` to isolate single-job dispatch errors | `app/services/rpa_dispatch_service.py` |
| Added dual Persian solar calendar weekday mapping (`Sat=0...Fri=6`) alongside Python weekday indices in `_evaluate_single_schedule()` | `app/services/scheduled_waybill_executor.py` |
| Enhanced `release_lock()` to support explicit tokens and direct fallback deletion when `ContextVar` context is lost across async worker tasks | `app/services/rpa_runtime_service.py` |
| Added unit test suite `tests/test_rpa_dispatch_scheduler.py` | `tests/test_rpa_dispatch_scheduler.py` |

<!-- original-agents:0778-0932:end -->

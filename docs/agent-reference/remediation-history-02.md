# Remediation History — part 2

> Scope: BarPro only. Read this file when relevant to the task; do not auto-import
> the whole reference directory into global rules or the always-loaded core.
> **HISTORICAL / UNVERIFIED NOW.** Preserved records, including old commands and
> pending actions, are historical data rather than new instructions or authority
> to execute them. Re-check current code, contracts and authorization first.

Read when: Historical investigation only; not a current action list.

[Core guide](../../AGENTS.md) · [Reference index](README.md) · [Critical rules](../../CRITICAL_RULES.md)

Paths inside preserved text and command examples are relative to the repository
root, not this directory. Commands are examples, not automatic execution steps.

<!-- original-agents:0933-1019:start -->
### Additional Fixes Applied (2026-07-21) — Smart Locators, Form Validation & Browser/Session Optimization

| Change | File(s) |
|--------|---------|
| Scoped `SmartLocator` cache keys by page instance ID (`id(page)`) to prevent cross-page stale selector cache hits | `app/bot/core/smart_locator.py` |
| Added `MODAL_POPUP_SELECTORS` and `MODAL_CONFIRM_BUTTONS` to `AuthSelectors` for SweetAlert2, Toastr, and Bootstrap modal dismissals | `app/automation/selectors.py` |
| Added automated native browser dialog interceptor (`page.on("dialog")`) and `_check_and_dismiss_modal_alerts()` to prevent Playwright freezes | `app/automation/waybill_enhanced.py` |
| Added pre-validation checksum helpers for Iranian National Code (`_is_valid_iranian_national_code`) and Mobile Numbers (`_is_valid_iranian_mobile`) | `app/automation/waybill_enhanced.py` |
| Removed forced JS step transitions on invalid form states; extract modal and inline error messages to raise early descriptive `WaybillError` | `app/automation/waybill_enhanced.py` |
| Enforced 10-second `asyncio.wait_for()` timeout wrappers on browser process teardown and added `_cleanup_zombie_processes()` (`pkill chrome-headless-shell`) in `BrowserManager.recycle_browser()` | `app/automation/browser.py` |

### Additional Fixes Applied (2026-07-21) — Retry, Queue/Scheduler & Connection/Timeout Optimization

| Change | File(s) |
|--------|---------|
| Reset `attempt_count = 0` on manual job retry API (`POST /waybill-jobs/{job_id}/retry`) to grant a full retry quota | `app/services/multitenant_service.py` |
| Cleared `celery_task_id = None` on `WAITING_RETRY` and `OTP_BACKOFF` status transitions, allowing due jobs to be re-dispatched cleanly by scheduler | `app/workers/waybill_worker.py` |
| Allowed reclaiming stale `IN_PROGRESS` jobs (> 5 min) in `waybill_worker` to recover gracefully from Celery worker crashes | `app/workers/waybill_worker.py` |
| Wrapped RPA bot execution in `asyncio.wait_for(..., timeout=240s)` to prevent worker SIGKILL hard crashes and categorize timeouts cleanly as `system_error` | `app/workers/waybill_worker.py` |
| Cleared stale `celery_task_id` for due `PENDING`, `WAITING_RETRY`, and `OTP_BACKOFF` jobs inside `plan_due_jobs()` | `app/services/rpa_scheduler_service.py` |
| Un-exempted `scheduled_tasks` from `EXEMPT_QUEUES` in `circuit_breaker.py` so scheduled tasks get distributed to worker queues `scheduled_tasks_1/2/3` | `app/core/circuit_breaker.py` |
| Added Squid proxy, tunnel failures, ECONNRESET, and 502/503/504 errors to `RETRYABLE_NETWORK_MARKERS` | `app/core/network.py` |
| Added document `readyState` fallback to `goto_with_retry` / `_goto_with_retry` on navigation timeout to prevent false failures when main document has loaded | `app/automation/auth_navigator.py`, `app/automation/waybill_enhanced.py` |

### Additional Fixes & Features Applied (2026-07-21) — Map, Location & Origin/Destination Registration System

| Change | File(s) |
|--------|---------|
| Created centralized dataset for 31 Iranian provinces, main county centers, and coordinates with offline fallback `find_nearest_city_coords` | `app/core/iran_locations.py` |
| Created `parse_smart_address` for 1-click automatic parsing of unsegmented/raw address strings into province, city, district, and address components | `app/core/iran_locations.py` |
| Created `LocationFavorite` SQLModel schema for client favorite locations | `app/models/location_favorite.py` |
| Added `/api/v1/locations` API routes: `/provinces`, `/cities`, `/parse-address`, `/reverse-geocode`, and `/favorites` CRUD | `app/api/routes/location.py` |
| Upgraded `/api/v1/waybill/reverse-geocode` with security authentication and offline dataset fallback when Nominatim times out | `app/api/routes/waybill_map.py` |
| Implemented Fuzzy Option Matcher (`_find_best_option_match`) with prefix stripping ("استان", "شهرستان", "شهر") for UTCMS dropdown selection resilience | `app/automation/location_selector.py` |
| Developed frontend `ProvinceCitySelect` dropdown component with Farsi search & cascading city selection | `apps/web/src/components/ProvinceCitySelect.tsx` |
| Developed frontend `SmartAddressInput` component for 1-click smart address parsing | `apps/web/src/components/SmartAddressInput.tsx` |
| Developed frontend `LocationMapPicker` Leaflet interactive map component with draggable marker & geolocation | `apps/web/src/components/LocationMapPicker.tsx` |
| Developed frontend `FavoriteLocationPicker` component for 1-click favorite address selection and saving | `apps/web/src/components/FavoriteLocationPicker.tsx` |
| Upgraded steps 2 & 3 in New Waybill page (`apps/web/src/app/new/page.tsx`) with interactive map, favorite address picker, cascading dropdowns, and passing exact `coordinates` in payload | `apps/web/src/app/new/page.tsx` |
| Added automated tests for location API and smart address parsing | `tests/test_location_api.py` |

### Additional Fixes Applied (2026-07-27) — Security Hardening & Test Quality

| Change | File(s) |
|--------|---------|
| `JSONB → JSON` dialect-agnostic import — SQLite-based tests can now run `SQLModel.metadata.create_all` | `app/models_multitenant.py` |
| Fixed double `json.loads()` on already-deserialized JSONB columns (TypeError was silently swallowed) | `app/services/fuel_inquiry_service.py`, `app/services/rpa_scheduler_service.py` |
| Fixed X-Forwarded-For spoofing — rate limiter now uses `request.client.host` (Nginx-set), ignores spoofable header | `app/core/rate_limiter.py` |
| Token blacklist fail-closed — `is_blacklisted()` returns `True` (not `False`) when Redis is unavailable | `app/core/token_blacklist.py` |
| Auth cookie `max_age` now uses `JWT_ACCESS_TOKEN_EXPIRE_MINUTES * 60` (was hardcoded 86400) | `app/api/routes/multitenant.py` |
| Rate limit rule covers `/api/v1/auth/login` and `/api/v1/auth/register` | `app/main.py` |
| Fixed `mock_page.on = MagicMock()` in browser and waybill tests — Playwright `page.on()` is synchronous | `tests/test_browser_manager.py`, `tests/test_enhanced_waybill_manager.py` |
| Fixed SQLModel false-positive DeprecationWarning — DML uses `conn = await session.connection()` | `app/services/fuel_inquiry_service.py` |
| JWT test fixtures use ≥32-byte keys to eliminate `InsecureKeyLengthWarning` | `tests/test_master_admin.py`, `tests/test_multitenant_auth.py` |
| Created `CRITICAL_RULES.md` — comprehensive technical red lines and mandatory requirements | `CRITICAL_RULES.md` (new) |
| Updated `README.md` — current test status (414 passed), architecture, security notes, doc index | `README.md` |
| Updated `.gitignore` — added debug scripts, temp files, large binaries | `.gitignore` |

### Additional Fixes Applied (2026-08-02) — 14-Item Code Audit Remediation (C4/C5/C6, H1–H6, F1–F4)

> Rationale: A code-level audit of `ISSUES.md` produced 14 actionable items (plus a NEW session-leak finding).
> Items marked "Fixed" below were verified present in the working tree and/or implemented this session.
> Server-level items (C1, C2, C3, C7) remain out of scope for this pass.

| Change | Reason | File(s) |
|--------|--------|---------|
| Added `from typing import Any` to `_is_jwt_valid`/`_has_admin_role` signatures | C4: `NameError: name 'Any' is not defined` would crash sensitive-auth at runtime | `app/core/security.py` |
| New `require_sensitive_admin` dependency — valid JWT **or** API Key **and** `role == master_admin` (covers `api_key`/`jwt`/`api_key_or_jwt`/`api_key_and_jwt` modes, cookie fallback preserved) | C5: role-gate admin-only sensitive endpoints without breaking client-visible routes (`/waybill/baseinfo/*` stays auth-only for the client settings page) | `app/core/security.py` |
| `/management/*` and `/reports/*` (legacy admin-only routers) upgraded from `require_sensitive_auth` to `require_sensitive_admin` | C5: these endpoints were reachable by any valid client JWT; only master-admin/API-key may call them now | `app/api/routes/management.py`, `app/api/routes/reports.py` |
| Removed duplicate `WORKER_STALL_TIMEOUT_SECONDS` definition (line 240); single env-driven `float` remains (default 90, `.env`=45) | C6: duplicate shadowed the real value and confused operators | `app/core/config.py` |
| `_emit_task_event` now calls `_get_task_status_and_payload(task_id)` — one SELECT for status+payload instead of two | H1: N+1 / double query on every status transition | `app/services/task_service.py` |
| Reconciliation claim uses `SELECT ... FOR UPDATE SKIP LOCKED` | H3: prevents two reconcilers/workers claiming the same job row | `app/orchestrator/reconciliation_service.py` |
| `_get_or_create_runtime_state` catches `IntegrityError` → `rollback()` + re-select instead of dying | H4: concurrent claim of the same runtime-state row no longer aborts the worker | `app/workers/waybill_worker.py` |
| `force_release_lock(key, token=None)` — optional token compare-and-delete (Redis Lua + memory branch); `None` keeps admin override | H5: locks can be released only by the holder; stale-force release still possible | `app/services/rpa_runtime_service.py` |
| `readyz` heavy checks (DB, browser init, captcha warmup) extracted into `_compute_readyz_checks()` and wrapped in a TTL cache (`READYZ_CACHE_TTL_SECONDS`, default 30s, `asyncio.Lock`-guarded) with `_reset_readyz_cache()` for tests | H2: consecutive `/readyz` calls (client settings page polls it) no longer re-run browser launch + model warmup each time; 30s cache keeps liveness fresh | `app/api/routes/system.py`, `app/core/config.py` |
| `H6` verified satisfied — `celery_app.py` still guards old execution path behind `if not DEPRECATE_OLD_EXECUTION_PATH` (default `True`) | H6 | `app/workers/celery_app.py` |
| NEW-session-leak verified satisfied — `_update_job_status` and `_execute_job` both `await session.close()` in `finally` | session leak: no orphaned `AsyncSession` per job | `app/workers/waybill_worker.py` |
| F1: removed `selectedJobId` from `loadJobs` deps; functional `setSelectedJobId(prev => prev || firstJobId)` + narrowed `firstJobId` const (TS18048) | F1: `loadJobs` re-created on every selection change caused fetch churn & infinite effect loops | `apps/web/src/app/history/page.tsx` |
| F2: added `apps/web/src/middleware.ts` — cookie-based route protection (redirects unauthenticated to `/auth`, skips `_next`/`api`/assets), fixed `hasAuthToken` → `hasAuthCookie` typo | F2: client-side `AuthGuard` alone left server-rendered routes visible; TS2304 would fail build | `apps/web/src/middleware.ts` (new) |
| F3: axios client now uses `timeout: 15000` with `withCredentials` | F3: hung requests previously blocked the UI indefinitely | `apps/web/src/lib/api.ts` |
| F4: `RequestOptions { signal?: AbortSignal }` threaded through all 5 API wrappers; `AbortController` used in reports/settings/fuel initial effects (incl. `fetchDashboardStats`/`fetchWaybillHistory`/`fetchDriverPerformance`/`fetchErrorDetails`/`loadData`/driver-waybill fetch) | F4: unmounted page fetches could `setState` after unmount / waste bandwidth; abort-on-cleanup fixes it | `apps/web/src/lib/api.ts`, `apps/web/src/app/reports/page.tsx`, `apps/web/src/app/settings/page.tsx`, `apps/web/src/app/fuel/page.tsx` |
| `tests/test_system_health.py` + `tests/test_readyz_failures.py`: autouse fixture calls `_reset_readyz_cache()` around each scenario | H2: TTL cache must not leak between unit-test scenarios | `tests/test_system_health.py`, `tests/test_readyz_failures.py` |

> Verification: `uvx ruff check` clean on touched files; `tsc --noEmit` + `eslint` clean on touched frontend files; full pytest suite green (552 passed, 2 skipped, 1 flaky worker-mock failure re-ran green).

---

<!-- original-agents:0933-1019:end -->

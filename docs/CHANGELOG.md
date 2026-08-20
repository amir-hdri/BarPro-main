# Changelog
  
  All notable changes to the UTCMS Automation System.

  ## [2.9.1] - 2026-08-20

  ### Fixed & Security — Validation, Multi-Tenancy & Hardening
  - **Union Validation Bypass Fix**: Eliminated `dict[str, Any]` fallback from `WaybillJobCreateRequest.payload: WaybillPayload | WaybillNestedPayload`, ensuring invalid payloads (malformed plates, negative weights, missing fields) immediately raise HTTP 422 `ValidationError`.
  - **Payload Pre-Validators**: Added normalization and aliasing pre-validators to `CargoModel`, `VehicleModel`, `FinancialModel`, `SenderModel`, and `ReceiverModel` (`cargo_title` -> `type`, `cargo_weight` -> `weight`, `fare_amount` -> `cost`, `plate_number` -> `plate`).
  - **Multi-Tenant Queue Isolation**: Enforced `client_id` resolution from JWT auth / API key in legacy routes (`waybill_entry.py`, `waybill_map.py`) and eliminated unsafe `client_id=1` default in production.
  - **Fail-Closed Dispatcher Routing**: Ensured `circuit_breaker.py` raises `NoHealthyWorkerError` on Redis or registry outages in production instead of blindly falling open.
  - **Container Least Privilege**: Removed `cap_add: [SYS_ADMIN, NET_ADMIN]` from backend common compose configuration, restricting `SYS_ADMIN` solely to browser worker containers.
  - **Production Security Check**: Added startup enforcement in `app/main.py` requiring `AUTH_COOKIE_SECURE=True` when HTTPS is configured.
  - **Frontend Middleware Security**: Replaced broad `pathname.includes('.')` in `apps/web/src/middleware.ts` with strict static asset extension regex.
  - **Fuel Polling UX**: Stabilized fuel inquiry polling in `apps/web/src/app/fuel/page.tsx` with `useCallback`, added user toasts on network errors and polling timeout, and fixed React hook dependencies.
  - **Frontend Unit Testing**: Added native Node.js test runner in `apps/web/package.json` (`npm test`) with unit tests covering plate normalization and canonicalization.

  ## [2.9.0] - 2026-08-19

  ### Added — Clean Iranian Proxy Pool (Zero IP Restriction)
  - **Live Iranian Proxy Aggregator**: Integrated multi-source aggregator (`app/automation/clean_ip_pool.py`) collecting from 11+ sources and actively validating live proxies against `https://utcms.ir`.
  - **Dynamic Hybrid Routing Engine**: Updated `app/automation/proxy_rotator.py` and `app/automation/worker_proxy.py` to seamlessly fail over between worker local Squids and dynamic clean Iranian proxies, removing egress IP bottlenecks.
  - **Single-Tab In-Place Fuel Scraper**: Eliminated ASP.NET session collision on `ShowFuelQuota.aspx`, reducing inquiry runtime to < 15 seconds.
  - **Multi-Server Screenshot Persistence**: Converted screenshots to Base64 Data URIs in PostgreSQL, resolving Model B cross-server 404 missing-file errors.

  ## [2.8.0] - 2026-08-13

  ### Changed — UTCMS live form contract
  - UI، Zod، Pydantic و payload adapter بر اساس فیلدهای واقعاً اجباری فرم
    HagigiHogugi همگام شدند: راننده/پلاک، استان/شهر/آدرس مبدأ و مقصد، نام کامل
    فرستنده/گیرنده، نوع کالا، بسته‌بندی، وزن و ارزش بار.
  - فیلدهای غیرضروری از فرم اصلی حذف و fallbackهای ساختگی برای نام، آدرس، تلفن،
    کالا و راننده/پلاک حذف شدند.
  - payload ناقص قبل از proxy، Chromium، lease و retry با
    `payload_validation_failed` به `needs_review` منتقل می‌شود.

  ### Fixed — Routing and worker isolation
  - routing در نبود Worker تازه/فعال/unblocked به‌صورت fail-closed عمل می‌کند؛
    دیگر dispatch به IP blocked یا queue بدون consumer انجام نمی‌شود.
  - مسیرهای failure پیش از Execution، driver slot را با ownership guard آزاد
    می‌کنند و retryهای Celery برای intent از قبل failed تکرار جانبی ایجاد نمی‌کنند.
  - JSON object، JSON string و payload دوبار encodeشده به‌صورت ایمن normalize می‌شوند.

  ### Fixed — UTCMS transport
  - bridge جدید `http_browser_bridge.py` فقط document/xhr/fetch را با fingerprint
    کروم `curl_cffi` عبور می‌دهد؛ JS/CSS/font/image توسط Chromium/Squid بارگیری
    می‌شوند تا serialization و reset انبوه assetها رخ ندهد.
  - proxy pre-flight بین خطای Squid و reset لحظه‌ای upstream تفاوت می‌گذارد و با
    retry کوتاه از drain اشتباه Worker جلوگیری می‌کند.
  - آزمون کنترل‌شده ورود را موفق کرد، ولی `DocumentList/Index` همچنان reset TLS
    داد؛ ثبت نهایی و tracking code اثبات نشد.

  ### Changed — CAPTCHA and fuel inquiry
  - امضای غیرحساس CAPTCHA شامل نوع/مسیر/ابعاد/digest برای تشخیص drift ثبت می‌شود؛
    پاسخ CAPTCHA از log و debug metadata حذف شد.
  - در نمونه‌های موجود تغییر ساعت‌محور نوع CAPTCHA مشاهده نشد: login همچنان DNT
    ریاضی `CapType=1` و fuel همچنان CAPTCHA فارسی `#imgCapchaEdit1` است.
  - Fuel CRNN initialization با `threading.Lock` بین loopهای Celery ایمن شد و
    دوره جلالی با `ZoneInfo("Asia/Tehran")` محاسبه می‌شود.

  ### Documentation
  - `docs/UTCMS_CONSTRAINTS.md` به‌عنوان مرجع واحد محدودیت‌های فرم، IP/WAF،
    CAPTCHA، زمان‌بندی، صف‌ها، سوخت و معیار اثبات ثبت اضافه شد.
  
  ## [2.7.0] - 2026-08-13
  
  ### Fixed — Authentication / Login Flow
  - **WAF fast-fail in Playwright fallback** (`app/automation/auth.py`): After an HTTP login
    failure, the Playwright path previously navigated to `/Account/Login` and waited
    ~3 minutes for login-form fields that never appeared (UTCMS WAF returns HTTP 444
    and the text «درخواست مجاز نمی‌باشد» for headless Chromium). Now detected within
    500 ms → `return False` immediately → job enters `waiting_retry` and retries the
    faster HTTP path on the next cycle.
  - **Post-HTTP-login Playwright navigation** (`app/automation/auth.py`): After a successful
    HTTP login the auth cookies were injected into the Playwright context but the browser
    remained on `about:blank`. The first waybill navigation therefore always started from
    a cold, unauthenticated state. Fixed: `_try_http_login_first` now calls
    `page.goto(WAYBILL_URL, wait_until="domcontentloaded")` immediately after cookie
    injection so the session is warm before the form-filling phase begins.
  - **HTTP 503/502/504 transient retry** (`app/automation/utcms_http_login.py`): A single
    upstream 503 from the Squid egress proxy used to abort the entire HTTP login attempt
    and fall back to the WAF-blocked Playwright path. Now `TRANSIENT_STATUS_CODES =
    (408, 500, 502, 503, 504)` are retried up to `TRANSIENT_MAX_RETRIES = 3` times with
    `TRANSIENT_BACKOFF_SECONDS = 6.0` delay each using a fresh `curl_cffi` session.
    The captcha-attempt counter is not decremented for transient errors so a 503 does
    not consume a captcha solve budget.
  - **Silent session expiry detection** (`app/automation/utcms_http_login.py`): UTCMS
    sometimes redirects to `/Account/Login` (or renders it inline) on authenticated
    page fetches without returning a 401. `_looks_unauthenticated()` now checks both
    the `Location` header and the final URL so expired sessions are caught and the
    fetch is retried with a fresh login rather than handing a login-page HTML back
    to the waybill form parser.
  - **Rate-limit counter fix** (`app/automation/utcms_http_login.py`): HTTP 429 and
    transient 5xx responses no longer decrement the captcha-attempt counter
    (`captcha_attempts_left += 1` to compensate). This prevents a network hiccup
    from exhausting the captcha retry budget.

  ### Added
  - **`_response_diagnostics()` helper** (`app/automation/utcms_http_login.py`): Extracts
    `Server`, `Via`, `X-Squid-Error`, `X-Cache`, `Content-Type`, and `Retry-After`
    from every error response. Squid-originated 503s carry `X-Squid-Error` and
    `Server: squid`; UTCMS/WAF 503s do not — enabling attribution without a live
    re-run.
  - **`auth_playwright_waf_blocked` log event** (`app/automation/auth.py`): Emitted
    whenever the WAF-block page is detected, including the current URL and a 200-char
    snippet of page text for forensics.
  - **`auth_http_login_post_nav_failed` log event** (`app/automation/auth.py`): Emitted
    (warning, non-fatal) if `page.goto(WAYBILL_URL)` throws after cookie injection.
  - **`utcms_http_login_transient_status_retry` log event** (`app/automation/utcms_http_login.py`):
    Emitted before each transient-error backoff sleep; includes HTTP status, attempt
    number, backoff seconds, retries remaining, and a 160-char error snippet.
  - **`utcms_http_login_fetch_unauthenticated` log event** (`app/automation/utcms_http_login.py`):
    Emitted when a fetch returns a login-page response instead of the requested page.
  - **`utcms_http_login_get_bad_status` / `utcms_http_login_post_bad_status` log events**:
    Emitted when GET (login page fetch) or POST (credential submission) returns an
    unexpected HTTP status so proxy vs. upstream failures are distinguishable.

  ### Refactored
  - **`app/core/network.py`** — completely rewritten around three composable marker
    tables: `EGRESS_FAILURE_MARKERS` (transport is broken → remove IP from pool),
    `BROWSER_LIFECYCLE_MARKERS` (process-local crash → do not evict IP), and
    `GENERIC_NETWORK_MARKERS`. `RETRYABLE_NETWORK_MARKERS` is now the union, enforced
    by `tests/test_error_taxonomy.py` so EGRESS⊆RETRYABLE can never silently drift.
    Previously five of six real egress failure patterns were retried forever without
    ever removing the broken IP index from the routing pool.
  - **`app/core/redis.py`** — `RedisConnectionManager` now caches one client per
    *(thread × event-loop)* pair instead of per-thread alone. A single thread can
    legitimately run multiple loops over its lifetime (Celery worker lifecycle); the
    previous per-thread cache returned a client whose transports belonged to a closed
    loop, causing `RuntimeError: Event loop is closed`. `_force_close_sockets()` and
    `_detach_transport()` helpers safely release file descriptors on abandoned
    transports without awaiting, eliminating `ResourceWarning: unclosed socket` and
    `ResourceWarning: unclosed transport` in the test suite under
    `filterwarnings = error`.

  ### Tests
  - `tests/test_error_taxonomy.py` — extended to **114 tests** asserting that every
    entry in `EGRESS_FAILURE_MARKERS` is also present in `RETRYABLE_NETWORK_MARKERS`
    (containment invariant), and that browser-lifecycle markers are *not* in
    `EGRESS_FAILURE_MARKERS` (no false IP eviction).
  - `tests/test_circuit_breaker.py` — **82 new tests** for `CircuitBreaker` state
    machine, EGRESS vs BROWSER error routing, and IP-index eviction logic.
  - `tests/test_event_loop_affinity.py` — **272 new tests** for `RedisConnectionManager`
    per-loop caching and socket-close behaviour across event loop boundaries.
  - `tests/test_typecheck_requirements.py` — validates `requirements-typecheck.txt`
    pin consistency.

  ### Files Changed
  - `app/automation/auth.py`, `app/automation/utcms_http_login.py`
  - `app/automation/auth_navigator.py`, `app/automation/browser.py`
  - `app/automation/waybill_bot_multitenant.py`, `app/automation/waybill_enhanced.py`
  - `app/automation/worker_proxy.py`
  - `app/core/network.py`, `app/core/redis.py`, `app/core/circuit_breaker.py`
  - `app/core/config.py`, `app/core/error_taxonomy.py`, `app/core/utils.py`
  - `app/bot/captcha/interceptor.py`, `app/bot/core/smart_locator.py`
  - `app/workers/waybill_worker.py`, `app/main.py`
  - `.github/workflows/cd-deploy.yml`, `.github/workflows/ci-cd.yml`,
    `.github/workflows/ci-test.yml`
  - `infra/squid/squid_1.conf`, `infra/squid/squid_worker.conf`
  - `compose/worker-node.yml`, `pyproject.toml`, `pytest.ini`
  - `tests/conftest.py` (new fixtures), `tests/test_circuit_breaker.py` (new),
    `tests/test_error_taxonomy.py` (extended), `tests/test_event_loop_affinity.py` (new),
    `tests/test_typecheck_requirements.py` (new), `requirements-typecheck.txt` (new)

  ## [2.6.0] - 2026-08-11
  
  ### Fixed
  - **R1 — Proxy interpolation in compose/backend.yml**: per-worker proxy values
    (`WORKER_1_PROXY`/`RPA_PROXIES`, `WORKER_2_PROXY`, `WORKER_3_PROXY`) are now
    `${WORKER_N_PROXY:-<fallback>}` instead of hardcoded, so deploy-time `.env`
    values (two-node topology) are no longer neutralized by the `environment:`
    block
  - **R2 — Remote render escaping in deploy_all_servers.sh**: `\${WORKER_EGRESS_IP}`
    / `\${CENTRAL_IP}` now expand on the WORKER NODE (its own `.env`), not on the
    launcher machine
  - **R3 — Operator runbooks**: `add_worker_firewall.sh` + all worker docs render
    `squid_worker.conf -> squid_worker.runtime.conf` (no `sed -i` on git
    templates) and pass `--env-file .env`; runbooks no longer point
    `CELERY_BROKER_URL` at Redis DB 1 / result backend DB 2 (central publishes
    on DB 0) and use the correct `utcms_rpa` database name
  - **Central squid configs (X4 central)**: new `scripts/render_squid_configs.sh`
    renders `squid_1/2/3.conf -> squid_*.runtime.conf` (mounted by
    compose/proxy.yml); deploy scripts no longer `sed -i` the tracked templates,
    so `git pull` on the central server no longer breaks
  - **X12 — CD pipeline**: `.github/workflows/cd-deploy.yml` migrated from
    `docker-compose` V1 (cannot parse the root `include:`) to `docker compose`
    V2 with `exec -T`, renders squid configs before deploy, and applies
    `deploy/registry-images.yml` so `pull`/`up` use the CD-published GHCR
    images instead of non-existent Docker Hub names
  - **Single backend image**: removed per-service image names from
    compose/backend.yml (fresh central servers could not start workers because
    only the anchor image was built); worker-node.yml now references the
    CD-published `ghcr.io/amir-hdri/barpro-main/barpro-backend:latest` and all
    worker build scripts tag the same name
  - **Worker env**: `WORKER_EGRESS_IP` / `SECONDARY_EGRESS_IP` added to
    `.env.example`; runbooks define `WORKER_EGRESS_IP` and guard the squid
    render with `:?` so a missing value fails loudly instead of rendering an
    empty `tcp_outgoing_address`
  - **celery_scheduler**: explicit `WORKER_IP_INDEX: ""` (no `.env` leakage);
    worker-node squid gets a `squid -k check` healthcheck (unrendered config
    shows `unhealthy` instead of silently restart-looping)
  
  ### Tests
  - `tests/test_queue_routing_contract.py` extended to **26 tests** covering:
    beat-queue profile-less consumers (both execution-path branches), solo
    control-queue consumer, proxy interpolation, `--env-file`, worker template
    rendering, runbook DB/egress contracts, central squid render-not-edit,
    compose-up render ordering, CD Compose V2 + registry images, and single
    backend image — all validated with mutation testing (18/18 mutants caught)
  
  ### Files Changed
  - `compose/backend.yml`, `compose/proxy.yml`, `compose/worker-node.yml`
  - `scripts/deploy_all_servers.sh`, `scripts/add_worker_firewall.sh`,
    `scripts/setup_worker.sh`, `scripts/render_squid_configs.sh` (new),
    `scripts/deploy_single_vm.py`, `scripts/deploy_remote.sh`,
    `scripts/deploy_remote.py`, `scripts/server_deploy.py`,
    `scripts/quick_deploy_central.sh`, `scripts/fix_stuck_jobs.sh`, `manage.sh`
  - `deploy/registry-images.yml` (new), `.github/workflows/cd-deploy.yml`
  - `docs/adding_new_worker.md`, `docs/runbook_worker_registration.md`,
    `docs/runbook_scale_out.md`, `.env.example`, `.gitignore`
  - `tests/test_queue_routing_contract.py`
  
  ---
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

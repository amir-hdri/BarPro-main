# Changelog
  
  All notable changes to the UTCMS Automation System.

  ## [Unreleased] - 2026-09-02

### Operations and CAPTCHA provider cleanup
- Removed the external vision provider, API key fallbacks, Compose/config injection, and related helper scripts. CAPTCHA routing now uses only the project-owned CNN, DNT CRNN, Keras, Enhanced OCR, and Local OCR providers.
- Synced the deployed DNT CRNN model and vocabulary assets into the repository.
- Rebuilt stale Central Scheduler and Beat containers from the current backend image and verified the Central image inventory.
- Corrected `manage.sh health` to test the live Backend container directly when Compose project labels do not match the fixed `container_name`.
- Set the Playwright browser download default to the Iranian TestEng mirror (`mirror.testeng.ir/playwright`) with a build-argument override; the mirror returned `502` during the live check, so no unverified download is treated as successful.
- Added the timestamped live operations report at `docs/OPERATIONS_STATUS_2026-09-02.md`, including the three-witness success rule, current job causes, Worker outage, OTP gate state, and IP pool policy.

  ## [Unreleased] - 2026-08-30

### Fixed — the final-registration CAPTCHA image was being blanked by our own asset policy
- `/DNTCaptchaImage/Show?data=...` is an `image` resource, and the bridge stubbed every image with an empty body to keep the asset flood off the curl transport. The issuance form therefore rendered a broken image, the submit-stage solver read no challenge at all, and it filled a one-character junk value into `#DNTCaptchaInputText` — a live submit with that value would have been rejected by UTCMS. Login was unaffected because the login CAPTCHA is solved over the HTTP path, not inside the browser, which is why this stayed hidden until the final stage (`app/automation/http_browser_bridge.py`).
- Captcha images now bypass both the stub and the on-disk asset cache: each challenge is single-use and bound to a server-side token, so a cached copy would be replayed against a token it no longer matches.
- Live verification (run 21, read-only, submit never clicked): the real image loaded, the `math` strategy correctly declined (the challenge is a handwritten-font image, not DOM text), the provider chain OCR'd it and `_normalize_captcha_solution` evaluated the expression — the result matched the challenge. One verified solve, not a success-rate measurement.

### Documented — the real final-stage, CAPTCHA and OTP contract
- Added `docs/UTCMS_SITE_BEHAVIOR_AND_BOT_RESPONSE.md`: the single reference for what the site does and how the bot answers — access/transport layer, asset-stubbing policy and the three behavioural regressions that shaped it, the pill-pane map, the two upstream location-dropdown defects, the three `#CapType` captcha/submit paths, the OTP contract, the mutation-boundary rules, the upstream-defect table and the live-run log.
- Corrected `UTCMS_SUBMIT_CONTRACT.md`: the final save is **not** `/Barname/PrintReport/printbarnameNew` (that is the print path). It is `UpdateRegisterNewNewOld` / `UpdateRegisterNewOld` / `UpdateRegisterNewNew`, selected by `#CapType` (live value: `1`, DNTCaptcha). Added `IssueDocumentByOtpNew` and `ResendOtpForIssueDocumen`.
- Corrected the OTP modal id across the docs: it is `#GetOptCodeModal`, not `#FormSendOtpCode`, it exists in the DOM from page load, and only the `.show` class is meaningful. Recorded the captcha-placeholder false positive ("کد امنیتی" matches `input[placeholder*='کد']`).
- Recorded that `#GoFinalStep` is UTCMS's own post-save navigation, hidden before submission; the readiness signal is `#btnRegisterFinished` visibility.
- Corrected the predicted OTP window to 17:30–08:00 Tehran in `UTCMS_GATE_RUNBOOK.md` and `UTCMS_OTP_DETECTION.md`, matching `PREDICTED_OTP_REQUIRED_*` defaults in the gate.
- `scripts/probe_waybill_final_stage.py` now emits a read-only final-stage DOM inventory and has an opt-in `--attempt-captcha` / `--captcha-artifact-dir` mode. It never clicks a submit control, never requests an OTP, and writes the solver output only to disk for operator review.

  ## [Unreleased] - 2026-08-29

### Frontend multi-route hardening and release verification
- Added real sender/receiver mobile fields to the batch wizard and validate Iranian `09xxxxxxxxx` numbers before creating a batch.
- Corrected cargo value labeling to ریال and kept the value in the canonical batch payload.
- Added abort-safe province/city, driver, plate, schedule, distance, reverse-geocode and batch-progress requests so stale responses cannot overwrite current UI state.
- Shared location favorites through React Query, added keyboard/ARIA support, and cleared stale coordinates whenever text/location selectors change.
- Verified route-chain semantics: each selected leg creates an independent waybill, `route_chain=true` preserves the requested order, releases the next leg only after reconciled success plus estimated duration and configured spacing, and does not require geographic continuity.
- Release commit: `5d583a1` (`fix(ui): harden multi-route form flows`).
- Verification: frontend typecheck/lint/build and 5 frontend tests passed; backend suite `1149 passed, 3 skipped`.
- Runtime verification reached all three servers and found expected containers/images healthy, but the fleet still required deployment of commit `5d583a1` at the time of this entry. No live waybill submission was performed without operator-supplied payload data and an `OTP_FREE` gate observation.

  ## [2.9.9] - 2026-08-27

### Fixed — Issuance form transport (asset session) and JavaScript-liveness gate
- The exact curl session that completes HTTP login is now reserved for issuance documents; landing-page AJAX runs on a separate session because live testing showed shared use burns the TLS connection for the following form navigation. Form XHR/fetch is promoted onto the authenticated session once the prefetched form document is consumed (`app/automation/http_browser_bridge.py`).
- The issuance form's critical scripts (jquery, jquery-ui, jquery.validate, formvalidation.popular, formhelper, hagigihogugitemplate, hagigihogugi) are prefetched in HTML order on that same authenticated session and served to Chromium from cache. Chromium's own TLS handshake resets these files, and a fresh cold curl session gets the identical reset. Prefetching *every* script on the page was rejected: the connection wore out before reaching `hagigihogugi*.js`. A single failed script no longer aborts the document handoff.
- Asset/document transport failures never reset the authenticated session; POST submission is still attempted exactly once with no retry or fallback path.
- New JavaScript-liveness gate before any field is filled (`_probe_form_javascript`/`_require_live_form_javascript` in `app/automation/waybill_enhanced.py`): jQuery, jQuery UI autocomplete, jQuery validator and the step-2 inline handler must all be initialised. Live testing produced a DOM-complete form (all markers present, ~258 KB) whose scripts had been reset — the person-type selector never revealed the name fields and `KalaSearch` returned nothing. DOM markers alone are no longer treated as readiness.
- `build_enhanced_waybill_payload` normalizes mixed-shape historical payloads (nested parties with compact origin/destination strings) instead of raising `ValueError` before the browser opens (`app/automation/multitenant_payload_adapter.py`).
- Documentation: new single reference `docs/UTCMS_BOT_BEHAVIOR_CONTRACT.md` (red lines, session/transport contract, navigation order, liveness gate, field read-back rules, dry-run protocol, deploy checklist); `docs/UTCMS_CONSTRAINTS.md` and `docs/INDEX.md` updated.
- No live waybill was submitted in this change: three-witness registration remains unproven for the new transport and requires an isolated dry-run followed by operator-supervised live submission.
- Verification: `ruff` clean on touched modules; `tests/test_http_browser_bridge.py` (17), `tests/test_waybill_enhanced_fast.py` (26) and the UTCMS/waybill suites (`119 + 54 passed`) pass locally.

  ## [2.9.8] - 2026-08-27

### Fixed — Authenticated issuance navigation, Clean IP truth and route read-back
- Clean IP screening no longer probes the session-protected `HagigiHogugi` deep-link anonymously. It probes the stable login surface with the production Chrome fingerprint and classifies 408/5xx as target-unavailable rather than IP rejection.
- Only proxies with measured Iranian egress (`egress_verified=true`, `observed_country=IR`) are selectable. Remote Workers load the shared fresh Redis pool; stale/zero-result Redis and fallback files are invalidated.
- Circuit Breaker infers the current egress source, isolates clean-pool failures to the exact third-party proxy, and no longer drains a Worker from a generic 408.
- Origin/destination province, city and address read-back now uses the exact selector that accepted the value, preventing hidden/fallback DOM mismatches.
- Added canonical Worker registration and scale-out runbooks; updated UTCMS, outage, route and critical-rule documentation.
- Verification: `1061 passed, 3 skipped`; codebase, RPA network, proxy, memory, topology and full-stack contract audits passed.

  ## [2.9.6] - 2026-08-24

### Fixed & Hardened — Full Audit Remediation: Duplicate-Registration Class, Firewall, Nginx, URL-Classification Sweep
- **C1 — Orphan sweep live-lease guard**: the stale-job sweep skips any RUNNING/IN_PROGRESS job whose `Execution.lease_expires_at` is still alive (`app/orchestrator/orphan_detector.py`); killing an in-flight job previously released the driver slot mid-mutation (duplicate-submission risk). Claim-path transitions now bump `updated_at`.
- **C2 — Real client IP behind nginx**: uvicorn runs with `--proxy-headers --forwarded-allow-ips=127.0.0.1,172.16.0.0/12,10.0.0.0/8` (`compose/backend.yml`, `Dockerfile`). Previously every request shared the nginx container IP, so the 5/min auth bucket was ONE global bucket (systemic login lockout).
- **C3 — Renewable driver locks**: new `renew_lock()` (Lua compare-and-expire) plus a lease-renewal thread extending registered submit/auth locks every ~30s (`app/services/rpa_runtime_service.py`); `RPA_LOCK_TTL` can no longer expire mid-bot-window.
- **C4 — Admin retry guards**: retry from UNKNOWN/CANCELLED returns descriptive HTTP 409 instead of a guaranteed 500; jobs categorized `submission_unconfirmed`/`ambiguous_mutation`/`duplicate_submission` are refused resubmission (`app/api/routes/admin_alerts.py`).
- **H1 — Derived Celery limits**: `CELERY_TASK_SOFT_TIME_LIMIT` defaults to `JOB_TIMEOUT_SECONDS+15`, hard limit to soft+45, with auto-correction of env misconfiguration (`app/core/config.py`).
- **H2 — `retrying` state node**: source set added and `retrying` accepted as an inbound target from 11 statuses in `ALLOWED_TRANSITIONS` (`app/orchestrator/state_machine.py`).
- **H3 — Stale celery_task_id recovery**: QUEUED (>15m) / WAITING_AUTH (>1h) jobs with provably dead Celery ids are cleared inside `plan_due_jobs` (`app/services/rpa_scheduler_service.py`).
- **H5 — Blacklist on sensitive deps**: `require_sensitive_auth/admin` reject JWTs whose jti is blacklisted (`app/core/security.py`).
- **H6/H7 — Nginx header inheritance + missing routes**: shared `infra/nginx/security-headers.conf` include attached to every location declaring local `add_header`; `proxies|circuit-breaker` added to the backend regex.
- **H8 — DOCKER-USER firewall guard** (`5441776`): UFW alone cannot block Docker-published ports; firewall scripts install comment-managed `DOCKER-USER` rules for 5432/6379 per Worker IP, enumerate all Docker subnets, and fix the UFW-enable self-DoS for host-network Squid 1.
- **NEW-1 — Waybill navigation resilience**: live `/Barname/RegisterWaybill/Index` is 404; canonical candidates + generic sidebar-link sweep with path-only partitioning (`app/automation/waybill_enhanced.py`).
- **NEW-2 — Wrong-captcha retry**: AJAX "لطفا کد امنیتی صحیح…" response confirmed flowing into `_is_captcha_error`; locked with regression tests.
- **Bug-class fix — structural URL classification**: login/session classifiers are path-parsed instead of substring-on-full-URL in `auth_utils.py`, `utcms_http_login.py`, `utcms_reconciliation_scraper.py`, `waybill_bot_multitenant.py` (`?ReturnUrl=/Login` no longer flips session detection; duplicate-submission hazard removed).
- **Chore — Dependabot version updates disabled** (`35bb5d2`): `.github/dependabot.yml` deleted (~24 stale branches cleaned). Dependabot alerts/security-updates remain governed by repo Settings.
- **Regression suite**: `tests/test_audit_fixes.py` (28 tests); suite collects 1026 tests at this commit.

  ## [2.9.5] - 2026-08-24

### Security Hardening, Lock-Token Durability & Full-Stack Consistency Remediation
- **Alert webhook fail-closed** without `ALERT_WEBHOOK_SECRET` for edge-proxied requests; nginx allow/deny defence-in-depth on the webhook location.
- **Metrics access guard**: `GET /metrics` restricted to loopback/RFC1918 peers or `METRICS_SCRAPE_TOKEN` holders.
- **Tenant isolation on legacy routes**: global `API_KEY` no longer silently attributes jobs to tenant 1.
- **Durable driver-lock tokens**: `acquire_lock` persists tokens in a `locktok:{key}` registry so `release_lock` can prove ownership across task/thread boundaries (fixes the 360s `driver_submission_in_progress` stall); registry cleanup moved outside the non-reentrant `_get_lock()` (deadlock fix).
- **Migration-038 response fields**: `WaybillJobResponse` exposes `batch_id`, `route_template_id`, `sequence_index`, `distance_km`, `duration_min`, `submission_fingerprint`.
- **Cookie name single source of truth**: `AUTH_COOKIE_NAME` (backend) + `NEXT_PUBLIC_AUTH_COOKIE_NAME` (frontend) — no hardcoded drift.
- **Rate-limit bucket accuracy**: `/reports`, `/api/system/*` → admin bucket; `/api/v1/batches`, `/api/v1/route-templates` → waybill bucket.
- **Priority schema alignment**: `BatchCreate.priority` clamped to `le=9`; client-side Iranian national-code checksum mirrors the backend validator; `SQLModel.metadata` registers `LocationFavorite` + `AdminAlert`; config dedup and docs sync.

  ## [2.9.4] - 2026-08-23

### Added & Fixed — Error Taxonomy Sync, State Machine Auto-Heal & Full-Stack UI Batch Integration
- **Unified Worker Retry Classification**: `_is_retryable()` in `app/workers/waybill_worker.py` is now bound directly to `is_retryable_terminal_category(classify_error_string(...))` and exponential backoff calculations in `get_retry_delay()`. This ensures transient site timeouts (`target_site_timeout`), infra resets (`transient_infra_error`), and authentication hiccups (`auth_failure`) are automatically retried with exponential backoff instead of failing permanently.
- **State Machine Resilient Recovery**: Expanded `ALLOWED_TRANSITIONS` in `app/orchestrator/state_machine.py` so jobs in `FAILED` or `NEEDS_REVIEW` can transition cleanly to `WAITING_SUBMISSION_WINDOW` or `WAITING_RETRY` during automated auto-heal cycles and admin retries.
- **Model Metadata Auto-Registration**: Explicitly imported `WaybillBatch` and `WaybillRouteTemplate` into `app/models_multitenant.py`, ensuring all foreign key constraints (`waybill_jobs.batch_id`, `waybill_jobs.route_template_id`) resolve cleanly without `NoReferencedTableError` when models are loaded in isolation.
- **Frontend Dashboard & Sidebar Integration**:
  - Added direct quick action button for **«ثبت دسته‌ای (چندمسیره)»** on the main Dashboard hero banner (`apps/web/src/app/page.tsx`).
  - Added **«ثبت دسته‌ای»** (`/batches`) and **«قالب‌های مسیر»** (`/route-templates`) to both Client and Admin navigation menus in `apps/web/src/components/layout/Sidebar.tsx`.
- **Test Suite Verification**: Updated `test_get_retry_delay` in `tests/test_auto_heal.py` to assert exponential backoff for retryable errors. Full test suite passing at 100% (996 automated tests: 988 passed, 3 skipped, 0 failed).

## [2.9.3] - 2026-08-23

### Added — Multi-Route Waybill Registration (Route Templates, Batches & Distance/Time)
- **Route templates** (`waybill_route_template`): save reusable origin→destination routes with precomputed road distance and duration; CRUD + favorite endpoints under `/api/v1/route-templates`.
- **Multi-route batches** (`waybill_batch`): expand N route templates × target count into concrete `waybill_jobs` with round-robin / random / sequential repeat modes; endpoints under `/api/v1/batches`.
- **Distance/time service**: `POST /api/v1/locations/distance` resolves road distance and duration via Neshan routing API with Redis cache and a local haversine fallback (no external call when `NESHAN_API_KEY` is unset).
- **Migration `038_add_multiroute_batch_distance`**: creates the two tables, adds `batch_id`, `route_template_id`, `sequence_index`, `distance_km`, `duration_min` to `waybill_jobs`, with matching foreign keys and indexes.
- **100% registration accuracy gate**: batch creation validates every route's province/city/address and the base payload against the live worker contract (`validate_enhanced_waybill_payload`), returning a 422 with the exact missing fields instead of silently failing to `NEEDS_REVIEW` at runtime.
- **Interval enforcement**: jobs are staggered via `submit_after` (not `next_retry_at`) so `plan_due_jobs` respects `interval_minutes` (anti-spam).

### Changed
- `JOB_TIMEOUT_SECONDS` default 480 → 330 (stays below `CELERY_TASK_TIME_LIMIT` 360).
- `driver_id` is now required on batch creation with tenant-ownership validation.
- OpenAPI `version` metadata 2.0.0 → 2.9.3.
- Worker timeout fallback 480 → 330.

### Fixed
- Multi-route payloads now produce the full `WaybillMapRequest`-compatible structure (sender/receiver/cargo/vehicle + nested origin/destination), fixing silent `payload_validation_failed`.
- Route-template `update` no longer nulls non-nullable fields.
- Batch "today" progress uses Asia/Tehran timezone.
- Haversine fallback is no longer cached (no cache poisoning).

### Docs
- README / CRITICAL_RULES / AGENTS / INDEX / DEPLOYMENT_GUIDE / QUICK_START / KNOWLEDGE_GRAPH: migration head 036/037 → 038, test count → 989, version → 2.9.3.
- New `docs/MULTI_ROUTE_FEATURE.md`.

## [2.9.2] - 2026-08-20

  ### Added & Optimized — Universal Mobile Anti-Zoom, UI/UX Polish & Full-Stack Hardening
  - **Universal Mobile Viewport & Anti-Zoom (iOS & Android)**:
    - Enforced `width: device-width`, `initialScale: 1`, `maximumScale: 1`, `userScalable: false`, and `viewportFit: cover` in `apps/web/src/app/layout.tsx`.
    - Applied universal minimum font size `font-size: 16px !important` across all `input`, `select`, `textarea`, and `.field` elements on screens `< 768px` in `apps/web/src/app/globals.css`, eliminating auto-zoom behavior across iOS Safari, Chrome Android, Samsung Internet, and Firefox Mobile.
    - Set `touch-action: manipulation` across all interactive elements (`button`, `a`, `input`, `select`, `textarea`) and added text scaling protections (`text-size-adjust: 100%`).
  - **Full-Stack Status Filter Normalization & Resilience**:
    - Fixed status filter dropdown in `apps/web/src/app/reports/page.tsx` by replacing uppercase values with canonical lowercase keys (`success`, `failed`, `in_progress`, `pending`, `queued`, `needs_review`, `submission_unconfirmed`).
    - Hardened database query filters in `app/services/user_reporting_service.py` and `app/services/admin_reporting_service.py` with `.strip().lower()` for case-insensitive filtering.
  - **Comprehensive Persian RPA Error Taxonomy**:
    - Extended `errorCategoryLabel` in `apps/web/src/lib/format.ts` with case normalization and Persian translations for all RPA engine and bot error categories (`CAPTCHA_SOLVE_FAILED`, `WAF_BLOCKED`, `SESSION_TIMEOUT`, `CONCURRENT_LOCK_HELD`, `TARGET_SITE_TIMEOUT`, `USER_DATA_ERROR`, `AUTH_FAILURE`, `SELECTOR_CHANGED`, `BOT_DETECTED`, `WORKER_RESOURCE_ERROR`, `WORKER_DRAINED`, `OTP_REQUIRED`, `SYSTEM_ERROR`).
  - **RTL Admin Layout & Accessibility**:
    - Corrected admin sidebar layout in `apps/web/src/app/admin/layout.tsx` to adhere to RTL standards (`right-0`, `border-l`, `md:mr-[280px]`, `translate-x-full` mobile slide).
    - Added missing `aria-label` and `aria-expanded` attributes across all modal close buttons and letter selectors (`CreateClientModal.tsx`, `PlateInput.tsx`, `drivers/page.tsx`, `new/page.tsx`, `fuel/page.tsx`).
    - Added live screen-reader regions (`role="status"`, `aria-live="polite"`) to dashboard and alert summary cards.
    - Implemented automatic input focus recovery upon failed authentication in `apps/web/src/app/auth/page.tsx`.

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

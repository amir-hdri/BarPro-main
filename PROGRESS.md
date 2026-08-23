# BarPro Unified Master Roadmap v2.0 Progress Status

This file tracks the completion status of the phases defined in [BarPro_Unified_Master_Roadmap.md](file:///Users/amirheidari/GitHub/BarPro-main/BarPro_Unified_Master_Roadmap.md).

## Phase Checklist

- Phase 0: Open Decisions & Staging Readiness [x]
- Phase 1: Core Database & Dispatch Intents [x]
- Phase 2: Central & Worker Scaling [x]
- Phase 3: Driver FIFO Serialization [x]
- Phase 4: Redis Session Vault & Fail-Closed Safety [x]
- Phase 5: UTCMS Health Probe [x]
- Phase 6: Reconciliation Engine & Admin Alerts [x]
- Phase 7: Scale-Out (Dynamic Worker List + UFW+TLS Infrastructure) [x]
- Phase 8: Auto-Heal [x]
- Phase 9: Beat High Availability (celery-redbeat) [x]
- Phase 10: Observability [x]
- Phase 11: Test Suite [x]
- Phase 12: Documentation & Runbook [x]
- Phase 13: Production Deployment & Go-Live [x]

---

## Detailed Notes & Timestamps

### Phase 5 — UTCMS Health Probe (Completed: 2026-07-31)
- **Investigation Output**: Created [utcms_list_search_investigation.md](file:///Users/amirheidari/GitHub/BarPro-main/docs/utcms_list_search_investigation.md) addressing questions H.1 to H.4.
- **Verification Status**: Verified successfully using the upgrade CLI tool.

### Phase 6 — Reconciliation Engine & Admin Alerts (Completed: 2026-07-31)
- **Reconciliation**: `app/orchestrator/reconciliation_service.py` + `utcms_reconciliation_scraper.py`
- **Admin Alerts**: `app/orchestrator/alert_manager.py` + migration `024_admin_alerts.py`
- **Tests**: `tests/test_reconciliation_service.py`, `tests/test_admin_alerts.py` — 6 passed

### Phase 7 — Scale-Out: Dynamic Worker List + UFW+TLS Infrastructure (Completed: 2026-07-31)
- **Architecture Decision**: UFW Firewall + fixed IPs (instead of WireGuard) — simpler, no extra software
- **proxy_rotator.py**: Replaced `squid_1/2/3` hardcode with `re.match(r"^squid[_-]?\d+$")` regex
- **system.py `/proxies/health`**: Reads active workers from `worker_registry` DB (was `for i in (1,2,3)`)
- **worker_dashboard_service.py**: New service for dynamic worker proxy mapping
- **compose/worker-node.yml**: Docker Compose template for remote Worker nodes
- **scripts/setup_firewall_central.sh**: UFW setup for Central server
- **scripts/add_worker_firewall.sh**: Add new Worker IP to firewall (with setup instructions)
- **scripts/create_worker_db_role.sql**: PostgreSQL least-privilege role for Workers
- **infra/squid/squid_worker.conf**: Squid config template for Worker nodes
- **docs/adding_new_worker.md**: Step-by-step guide (also documents Headscale migration path)
- **Tests**: 21 passed in `tests/test_dynamic_worker_list.py`

### Phase 8 — Auto-Heal (Completed: 2026-08-01)
- **Features**: Implement worker proxy health checks, worker failure tracking in Redis, automatic consumer cancellation (draining mode) and Playwright browser recycling.
- **Tests**: verified in `tests/test_auto_heal.py`.

### Phase 9 — Beat High Availability (Completed: 2026-08-01)
- **Features**: Integrate `celery-redbeat` scheduler with Redis backend lock, build container watchdog check `beat_watchdog.sh`.
- **Tests**: verified in `tests/test_beat_ha.py`.

### Phase 10 — Observability (Completed: 2026-08-01)
- **Features**: Live SLO exporter gauges, Prometheus `alerts.yml` rule thresholds, Alertmanager HMAC signed webhook route, and Admin Worker dashboard.
- **Tests**: verified webhook HMAC signature & event routing in `tests/test_admin_alerts.py`.

### Phase 11 — Test Suite (Completed: 2026-08-01 | Remediated: 2026-08-01)
- **Features**: Created a comprehensive testing suite verifying tenant isolation security, database failover retry, and load/performance throughput.
- **Files**: `tests/test_state_machine.py` (26 tests), `test_driver_fifo.py`, `test_execution_lease.py`, `test_fencing_token.py`, `test_dispatch_intents.py`, `test_reconciliation_service.py`, `test_admin_alerts.py`, `test_session_vault_redis.py`, `test_wireguard_security.py` (deprecated — renamed), `load/test_500_jobs_per_hour.py`, `chaos/test_redis_unavailable.py`, `chaos/test_db_failover.py`, `integration/test_worker_lifecycle.py`, `smoke/test_smoke.py`.
- **Gaps Fixed (2026-08-01)**: Replaced hardcoded `188.121.123.16` IPs in all test fixtures with placeholders. Clarified that `test_wireguard_security.py` references legacy architecture (UFW is current). Load test is simulation-based (mocked) not full end-to-end.
- **Results**: 100% green under simulated conditions. Full end-to-end requires production-like environment.

### Phase 12 — Documentation & Runbook (Completed: 2026-08-01 | Remediated: 2026-08-01)
- **Features**: Created production-ready runbooks for worker registration, UTCMS outage handling, failed reconciliation recovery, scaling out, and pre-deployment security audits.
- **Files**: `docs/runbook_worker_registration.md`, `docs/runbook_utcms_outage.md`, `docs/runbook_failed_reconciliation.md`, `docs/runbook_scale_out.md`, `docs/security_audit_checklist.md`, `docs/utcms_list_search_investigation.md`, `docs/architecture.md`, `docs/adding_new_worker.md`.
- **Gaps Fixed (2026-08-01)**: Removed all hardcoded `188.121.123.16` IP addresses from runbooks and replaced with `<YOUR_CENTRAL_SERVER_IP>` placeholders. Updated `architecture.md` to reflect UFW-based networking instead of WireGuard. All curl commands in runbooks now use placeholders.

### Phase 13 — Production Deployment & Go-Live (Completed: 2026-08-01 | Remediated: 2026-08-01)
- **Features**: Created server management script `manage.sh` covering start, stop, status, health, migrate, backup, and deploy. Added automated smoke tests under `tests/smoke/`.
- **Files**: `manage.sh`, `tests/smoke/test_smoke.py`, deploy scripts (`server_deploy.py`, `deploy_remote.sh`, `deploy_single_vm.py`, `upload_and_setup.py`, etc.).
- **Gaps Fixed (2026-08-01)**: Removed hardcoded IPs from all deploy scripts (`server_deploy.py`, `deploy_remote.sh`, `deploy_single_vm.py`, `deploy_remote.py`, `upload_and_setup.py`). All scripts now use `CENTRAL_IP` / `SECONDARY_IP` environment variables or `<YOUR_CENTRAL_SERVER_IP>` placeholders. Enhanced `manage.sh health` to check proxy health (Squid 1/2/3) and worker registry DB connectivity. Updated `.env.example` and `infra/squid/squid_1.conf` comments. Updated `app/automation/worker_proxy.py` to use generic public IP detection instead of hardcoded addresses.

### UI/UX, Typography, and Motion Upgrades (Completed: 2026-08-02)
- **Features**: Comprehensive visual, responsiveness, typography, and motion upgrade across the Next.js 15 web panel. Set up the Vazirmatn variable font, resolved iOS Safari auto-zoom issues, set notch-compatible viewport parameters, built an interactive mobile navigation drawer with spring transitions and Drag-to-dismiss via Framer Motion, transition templates on route navigation, and converted grids/nested sub-tables to flexible cards on mobile.
- **Verification & Audit**: Successfully passed the pre-flight frontend UI/UX audit (`ui_ux_cli.py audit-ui --output ui_audit.json`) with 0 violations.
- **Font File Fix**: Remedied a critical issue where the Vazirmatn variable font file was corrupted (HTML 404 placeholder) by downloading and extracting the official TrueType variable font (`Vazirmatn[wght].ttf`) from Saber Rastikerdar's repository releases.
  - **Build Status**: Verified successfully with `npm run build` compiling the production bundle in 6.9s without warnings.

### Documentation & Security Hardening (Completed: 2026-08-02)
- **Features**: Complete review, update, and completion of all documentation files according to latest changes
- **Files Updated**:
  - `ISSUES.md`: Added new fixes for 2026-08-02 session (security headers, Redis pool, CSP, Permissions-Policy, DNS resolution)
  - `README.md`: Updated test count (552 passed), migration head (029), security notes, documentation index
  - `AGENTS.md`: Updated architecture overview, network flow, common pitfalls, testing status, new fixes table
  - `CRITICAL_RULES.md`: Added new rules for security headers and Redis configuration, updated migration info
  - `CHANGELOG.md`: Added release 2.4.0 with all latest changes
- **Security Improvements**:
  - Added security headers middleware to FastAPI backend
  - Configured Redis connection pool with timeout/retry settings
  - Enhanced CSP header with frame-ancestors, base-uri, form-action
  - Added Permissions-Policy header to Nginx
  - Removed hardcoded secrets from GitHub Actions workflows
  - Improved phone validation error messages
  - Added logging to exception handlers

### Fuel Inquiry Performance & Screenshot Multi-Server Persistence (Completed: 2026-08-19 — v2.8.2)
- **Single-Tab In-Place Fuel Scraper**:
  - Eliminated parallel-tab ASP.NET session collision on `ShowFuelQuota.aspx` (`Session["LoginShowFuelQuota"]`).
  - Switched from concurrent multi-tab scraping to single-tab in-place sequential scraping: form loaded and filled once, Base Quota queried and captured, QuotaType switched to Performance in-place, and Performance Quota queried and captured.
  - Reduced fuel inquiry runtime from 167s (3 minutes) to **< 15 seconds** and achieved 100% reliable extraction of both Base & Performance quotas.
- **Modal Screenshot Capture & Base64 Data URI Persistence**:
  - Captured screenshot of modal element (`.modal-content`) before dismissing dialogs, preventing blank/empty screenshot artifacts.
  - Converted screenshot bytes to Base64 Data URI and persisted directly in PostgreSQL `FuelInquiry.screenshot_url`.
  - Added Base64 data fallback to `/api/v1/fuel-inquiries/{id}/screenshot` endpoint in `multitenant.py`, fixing Model B 404 missing-file errors on Central API when tasks run on remote Worker VPS nodes.
- **Frontend Quota Table & High-Res Preview**:
  - Enhanced Fuel Inquiry details modal in `apps/web/src/app/fuel/page.tsx` with structured breakdown tables for Base & Performance quotas and high-res screenshot view with external link.

### Waybill Registration Validation & Vehicle Type Integration (Completed: 2026-08-19 — v2.8.3)
- **Vehicle Type Integration (`vehicle_type`)**:
  - Integrated dedicated `vehicle_type` selector and customizable field into Step 1 of the Waybill Form (`apps/web/src/app/new/page.tsx`) with 12 preset chips (کامیون، تریلی کشنده، کامیونت خاور، وانت بار، تک ۱۰ تن، جفت ۱۵ تن، تریلی کفی، کمپرسی و...).
  - Auto-prefills `vehicle_type` from driver's registered plate upon driver/plate selection.
  - Added `vehicle_type` to the Quick Add Driver modal.
  - Added `vehicle_type` to Zod schema (`apps/web/src/schemas/waybillSchema.ts`) and TypeScript types (`apps/web/src/lib/types.ts`).
- **Pydantic Validation Resilience**:
  - Made `vehicle_type` (defaulting to `"کامیون"`) and `driver_phone` (optional with Persian 09xx digit normalization) flexible in backend `WaybillPayload` (`app/schemas/multitenant.py`), resolving the Union 422 validation failure on `POST /api/v1/waybill-jobs`.
  - Added `cargo_packaging` to `WaybillPayload` and flexible weight parsing.
  - Handled flat, nested, and hybrid dictionary payloads in `WaybillJobCreateRequest` and `WaybillJobService.create_job`.
  - Auto-registers and updates `DriverPlate.vehicle_type` in database upon waybill creation.
- **Verification**:
  - 875 passed tests in pytest suite.
  - 2 new E2E tests in `tests/test_e2e_fullstack_flows.py` verifying fullstack payload flexibility and plate sync.
  - Clean TypeScript typecheck (`tsc --noEmit` with 0 errors) and `fullstack_cli.py check-schemas` passed.

### Full-Stack Hardening & Zero IP Restriction (Completed: 2026-08-20 — v2.9.1)
- **Strict Payload & Schema Validation (A1)**:
  - Eliminated `dict[str, Any]` bypass from `WaybillJobCreateRequest.payload: WaybillPayload | WaybillNestedPayload`, ensuring invalid payloads (bad plates, negative weights, missing fields) immediately raise 422 `ValidationError`.
  - Added smart field aliasing pre-validators to `CargoModel`, `VehicleModel`, `FinancialModel`, `SenderModel`, and `ReceiverModel` in `app/schemas/waybill.py`.
- **Multi-Tenant Queue Isolation & client_id Enforcement (A2)**:
  - Enforced `client_id` resolution from JWT auth in legacy routes (`waybill_entry.py`, `waybill_map.py`) and removed unsafe `client_id=1` default in production.
- **Fail-Closed Dispatcher Routing (A3)**:
  - Ensured `circuit_breaker.py` raises `NoHealthyWorkerError` on Redis or registry outages in production instead of blindly falling open to index 1.
- **Container Least Privilege (A4)**:
  - Removed `cap_add` from backend API, beat, and scheduler services in `compose/backend.yml`, applying `SYS_ADMIN` exclusively to browser workers.
- **Security & Dependency Alignment (A5, A6)**:
  - Added production startup check enforcing `AUTH_COOKIE_SECURE=True` when HTTPS frontend is configured.
  - Aligned Dockerfile PyTorch and TensorFlow dependencies directly with `requirements.txt`.
- **Frontend Security & Polling UX**:
  - Replaced broad `pathname.includes('.')` in `middleware.ts` with strict static asset extension regex.
  - Stabilized fuel inquiry polling in `apps/web/src/app/fuel/page.tsx` with `useCallback` and added user toasts on network errors and polling timeout.
- **Clean Iranian Proxy Pool & Zero IP Restriction (v2.9.0/v2.9.1)**:
  - Maintained dynamic hybrid routing engine with third-party clean Iranian proxy fallback, eliminating egress IP bottlenecks.
- **Verification**:
  - 889 passed tests, 3 skipped (892 collected).
  - Clean TypeScript typecheck (`tsc --noEmit`) and zero ESLint warnings.

### Universal Mobile Anti-Zoom, UI/UX Hardening & Full-Stack Taxonomy Sync (Completed: 2026-08-20 — v2.9.3)
- **Universal Mobile Ergonomics & Anti-Zoom (iOS & Android)**:
  - Locked viewport scale in `apps/web/src/app/layout.tsx` (`width: device-width`, `initialScale: 1`, `maximumScale: 1`, `userScalable: false`, `viewportFit: cover`).
  - Enforced minimum font size `font-size: 16px !important` on all inputs/selects/textareas for screens `< 768px` in `apps/web/src/app/globals.css` to prevent automatic zoom on focus across iOS Safari, Chrome Android, Samsung Internet, and Firefox Mobile.
  - Configured `touch-action: manipulation` across all interactive elements (`button`, `a`, `input`, `select`, `textarea`) and added text scaling protections (`text-size-adjust: 100%`).
  - Prevented horizontal layout shifts with `overflow-x: hidden; width: 100%; max-width: 100vw;` on `html`, `body`, and outer container components.
- **Full-Stack Status Filter Normalization & Resilience**:
  - Synced frontend dropdown values in `apps/web/src/app/reports/page.tsx` with canonical lowercase backend keys (`success`, `failed`, `in_progress`, `pending`, `queued`, `needs_review`, `submission_unconfirmed`).
  - Hardened backend database queries in `app/services/user_reporting_service.py` and `app/services/admin_reporting_service.py` with `.strip().lower()` for case-insensitive filtering.
- **Comprehensive Persian RPA Error Taxonomy**:
  - Extended `errorCategoryLabel` in `apps/web/src/lib/format.ts` with case normalization and Persian translations for all RPA engine and bot error categories (`CAPTCHA_SOLVE_FAILED`, `WAF_BLOCKED`, `SESSION_TIMEOUT`, `CONCURRENT_LOCK_HELD`, `TARGET_SITE_TIMEOUT`, `USER_DATA_ERROR`, `AUTH_FAILURE`, `SELECTOR_CHANGED`, `BOT_DETECTED`, `WORKER_RESOURCE_ERROR`, `WORKER_DRAINED`, `OTP_REQUIRED`, `SYSTEM_ERROR`).
- **RTL Admin Layout & Accessibility (a11y)**:
  - Corrected admin sidebar layout in `apps/web/src/app/admin/layout.tsx` to RTL standards (`right-0`, `border-l`, `md:mr-[280px]`, `translate-x-full` mobile slide).
  - Added missing `aria-label` and `aria-expanded` attributes across all modal close buttons and letter selectors (`CreateClientModal.tsx`, `PlateInput.tsx`, `drivers/page.tsx`, `new/page.tsx`, `fuel/page.tsx`).
  - Added live screen-reader regions (`role="status"`, `aria-live="polite"`) to dashboard and alert summary cards.
  - Implemented automatic input focus recovery upon failed authentication in `apps/web/src/app/auth/page.tsx`.
- **Verification**:
  - Full-stack CLI audits (`check-schemas`, `check-auth-flow`, `check-websocket-events`, `audit-ui`) all passed with 0 warnings.
  - Clean TypeScript typecheck (`tsc --noEmit`) and 0 ESLint errors.
  - Frontend unit tests and backend pytest suites fully verified.

### Multi-Route Waybill Registration, Route Templates & Distance Service (Completed: 2026-08-23 — v2.9.3)
- **Route Templates (`WaybillRouteTemplate`)**: Save reusable origin→destination routes with precomputed road distance/duration; CRUD + favorite endpoints under `/api/v1/route-templates`.
- **Multi-Route Batches (`WaybillBatch`)**: Expand N routes × target count into jobs with round-robin, random, or sequential repeat modes; endpoints under `/api/v1/batches`.
- **Distance & Travel Time Engine**: `POST /api/v1/locations/distance` resolves road distance via Neshan Direction API + Redis cache + local Haversine fallback ($1.35$ factor).
- **100% Accuracy Gate**: Batch creation validates every payload against `validate_enhanced_waybill_payload` (422 with exact missing fields) and enriches driver data from database.
- **Migration 038**: `038_add_multiroute_batch_distance` adds batch tables and 5 foreign key columns to `waybill_jobs` (`ondelete SET NULL`).
- **Interval Staggering**: Staggers `submit_after` to enforce `interval_minutes` anti-spam pacing.

### Error Taxonomy Sync, State Machine Auto-Heal & Full-Stack UI Batch Integration (Completed: 2026-08-23 — v2.9.4)
- **Unified Retry Classification**: `_is_retryable()` in `app/workers/waybill_worker.py` binds to `is_retryable_terminal_category` and exponential delay calculations in `get_retry_delay()`.
- **State Machine Resilient Recovery**: Expanded `ALLOWED_TRANSITIONS` in `app/orchestrator/state_machine.py` for `FAILED` and `NEEDS_REVIEW` to transition cleanly to `WAITING_SUBMISSION_WINDOW` and `WAITING_RETRY`.
- **Model Metadata Auto-Registration**: Explicitly imported `WaybillBatch` and `WaybillRouteTemplate` into `app/models_multitenant.py` so SQLModel metadata registers all foreign keys.
- **Frontend Dashboard & Sidebar Integration**:
  - Added direct quick action button for **«ثبت دسته‌ای (چندمسیره)»** on the main Dashboard hero banner (`apps/web/src/app/page.tsx`).
  - Added **«ثبت دسته‌ای»** (`/batches`) and **«قالب‌های مسیر»** (`/route-templates`) to both Client and Admin navigation menus in `apps/web/src/components/layout/Sidebar.tsx`.
- **Verification**:
  - All 996 automated pytest tests passed (988 passed, 3 skipped, 0 failed).
  - Next.js production build (`npm run build`) completed in 4.4s with 21/21 static pages generated.
  - Multi-server cluster deployment verified across Central, Worker 2, and Worker 3 nodes.

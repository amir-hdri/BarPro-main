# Changelog

All notable changes to the UTCMS Automation System.

## [2.9.17] - unreleased

### 2026-10-11 — Jalali Calendar Everywhere, Route Templates Interactive Map, Unfiltered CartoDB Tiles & UI Hardening

- **Full Jalali (Shamsi) Calendar Adoption**:
  - Implemented standalone, zero-dependency Jalali calendar conversion utilities in frontend (`apps/web/src/lib/jalali.ts`) adhering to the Birashk/Kazemi mathematical algorithm, backed by 58 automated unit tests in `apps/web/test/jalali.test.mjs`.
  - Built reusable, accessible popover `JalaliDatePicker` component (`apps/web/src/components/JalaliDatePicker.tsx`) supporting year/month dropdown navigation, today selection, clearing, keyboard triggers, and outside-click dismissal.
  - Replaced native Gregorian `<input type="date">` inputs in `RecordFilters.tsx`, `reports/page.tsx`, and `admin/reports/page.tsx` with `JalaliDatePicker`, while emitting standard ISO `YYYY-MM-DD` strings for backend compatibility.
  - Replaced Gregorian dates in admin client onboarding modal (`CreateClientModal.tsx`) for `subscription_start_date` and `subscription_end_date`, and formatted client subscription dates with `formatJalaliDisplay` in `admin/clients/page.tsx`.
  - Added `parse_jalali_date` and `format_date_jalali` utilities in `app/core/jalali.py` with full unit test coverage in `tests/test_driver_tracking.py`.
- **Interactive Route Templates Map & Reverse Geocoding**:
  - Integrated `LocationMapPicker` dynamically (`ssr: false`) inside `apps/web/src/app/route-templates/page.tsx` to prevent Leaflet SSR errors.
  - Enabled interactive map toggles for both Origin (مبدأ) and Destination (مقصد), syncing pin drag/click coordinates with `origin_lat`/`origin_lng` and `dest_lat`/`dest_lng`, while automatically resolving province, city, and address via `/api/v1/locations/reverse-geocode`.
- **Unfiltered, High-Speed Map Tiles in Iran**:
  - Updated `apps/web/src/lib/map-tiles.ts` to use CartoDB Voyager and Light raster tiles (`https://{s}.basemaps.cartocdn.com/...`) with distributed `abcd` subdomains, accessible without VPN or WAF filtering in Iran. Maintained fallbacks to OSM Germany and OSM Standard. Verified full conformance with Nginx Content-Security-Policy headers.
- **Account Settings & Profile UI Hardening**:
  - Removed obsolete description banner under "حساب کاربری مشتری" in `apps/web/src/app/settings/page.tsx`.
  - Hardened `InfoCard` against value overflow by adding `min-w-0`, `overflow-hidden`, `truncate block w-full`, and LTR text direction (`dir="ltr" text-left font-mono`) for email/username values.
- **Fuel Inquiries Cleanup**:
  - Removed outdated subtitle, manual "بروزرسانی اطلاعات" button, and informational callout card in `apps/web/src/app/fuel/page.tsx`.
- **Verification Evidence**:
  - Frontend Jalali tests: 3 suites, 58 assertions passed (`node apps/web/test/jalali.test.mjs`).
  - Frontend typecheck: `npm --prefix apps/web run typecheck` passed (exit code 0).
  - Frontend lint: `npm --prefix apps/web run lint` passed (exit code 0).
  - Backend tests: `uv run pytest tests/test_driver_tracking.py` passed (13 passed in 1.59s).
  - Backend lint: `uvx ruff check app/core/jalali.py tests/test_driver_tracking.py` passed (exit code 0).
  - Production build & container: `barpro-frontend:latest` rebuilt and started (`healthy`).

### 2026-10-10 — Two-Flavor Driver-Hub SMS Relay Topology

- Architecture alignment for low-connectivity fleet operations: introduced a two-tier SMS relay that
  decouples driver phones from direct server connectivity.
- `SMS-Forwarder-Pro` product flavors (dimension `role`, `app/build.gradle.kts:39-63`). Both flavors
  build from the single `app/src/main` source set — only `applicationId`, `versionNameSuffix` and
  three `BuildConfig` fields differ; there is no role-specific UI.
  - `driver` (`ir.barpro.fleet.smsforwarder.driver`): catches UTCMS OTP SMS, signs it with
    HMAC-SHA256 truncated to 16 bytes into the ASCII envelope
    `BP1#phone#timestamp#code#signature`, and dispatches it over GSM SMS to the Hub phone without
    internet. Requires three settings to function: webhook token (signing key), Hub SIM number, and
    `driverPhone`.
  - `hub` (`ir.barpro.fleet.smsforwarder.hub`): listens for `BP1#...` envelopes, verifies the HMAC
    locally in constant time and discards forgeries before they consume an outbox slot, queues the
    rest in the Room outbox, and delivers to `/api/v1/otp/sms-gateway` with `X-OTP-Webhook-Token`.
    The server re-verifies with `hmac.compare_digest`.
- Dual-SIM carrier matching is now reachable from configuration. `ForwardConfig` gained
  `hubIrancellPhoneNumber` (Room migration 9→10) with a UI field, remote-config support, and a pure
  `CarrierDetector.resolveHubNumbers` precedence helper. Previously the Irancell leg was read from a
  `BuildConfig` field that no normal build defines, so every APK collapsed to single-number delivery
  and the SIM failover branch was unreachable.
- Hub-side `SmsFallbackEnvelope.verify` now compares via `MessageDigest.isEqual` instead of
  `String.equals`, and is wired into the intake path rather than being test-only code.
- Distribution APK names are produced by the build: `assembleDriverDebug` / `assembleHubDebug`
  finalize with `copy<Variant>DistributionApk`, writing
  `app/build/outputs/distribution/Forward-BarPro-{Driver,Hub}-<variant>.apk`. No manual copy step.
- Transport reality: this deployment serves **HTTP on port 80 by design**
  (`infra/nginx/nginx.conf:70`; the `listen 443 ssl` block is commented out), so the Hub must have
  `allowCleartextTransport` enabled. The envelope is HMAC-authenticated, but the webhook token and
  OTP are not encrypted in transit — network-level restriction of the gateway is part of the design.
  Health heartbeat interval is `healthCheckIntervalMinutes` — default **5 minutes**, clamped to
  **1-60 minutes**; there is no 60-second heartbeat.
- **Not implemented:** the 4G cellular / Tailscale exit-node proxy. No code or configuration exists
  in either repository; UTCMS egress remains the Squid chain with Iranian-egress proxy admission.
  Previously documented here as delivered — corrected after source verification.
- Verification (2026-10-10): `tests/test_otp_delivery_contract.py` + `tests/test_otp_forwarder.py` + `tests/test_full_relay_and_bot_simulation.py` →
  `52 passed in 23.89s`; `ruff` → `All checks passed!`; `black --check` → `428 files would be left unchanged`;
  `mypy app/` → `Success: no issues found in 217 source files`; Android
  `testDriverDebugUnitTest` / `testHubDebugUnitTest` → `tests=86 failures=0 errors=0` each (172 total, including
  complete end-to-end Driver-to-Hub relay simulations and boundary forge rejection).
- Added `POST /api/v1/otp/sms-gateway/{path_driver_phone}` to FastAPI router with path-to-origin driver phone consistency checks, fully matching `BarProContract.isPathValid`.
- Codified GSM Relay Sanitization & Route Parity rules in `CRITICAL_RULES.md` (§11.5), `runtime-contracts.md`, and `pitfalls-and-captcha.md`.
- Implemented full three-way end-to-end simulation (`tests/test_full_relay_and_bot_simulation.py`) verifying Driver SMS extraction, carrier route resolution, GSM HMAC envelope encoding, Hub boundary verification, FastAPI Gateway ingestion, Redis Lua transactions, Bot OTP consumption, and two-witness waybill confirmation.



### 2026-10-09 — UTCMS 6-Digit OTP & 7777000982 Shortcode Alignment

- Grounded real-world evidence from live Hagigi waybill issuance and SMS intake: identified official shortcode `7777000982` (range 7777), template `کد ورود: XXXXXX`, and 6-digit OTP modal on `com.baarnameshahri`.
- `SMS-Forwarder-Pro`: whitelisted `7777000982`, `+987777000982`, `7777`, `+987777` in `SmsParser.kt` (`UTCMS_NUMBERS`) and added default Room database prefix rules in `AppDatabase.kt`.
- `SMS-Forwarder-Pro/backend`: updated `otp_vault.py` to extract and validate 5 and 6-digit OTPs (`len(clean) in (5, 6)`), added non-digit gap resilience `[^\d]{0,40}` for phrases like `کد تایید شما` / `کد اول`, added `صادر گردید` / `بارنامه شماره` to waybill confirmation guards, and fixed `FallbackLimiter` decorator signature wrapping with `@functools.wraps`. Verified all 95 backend unit tests passing (100%).
- `BarPro-main`: added `7777000982` and `7777` to recommended rules and Iranian instructions in `otp_forwarder.py` and driver setup UI modal (`apps/web/src/app/drivers/page.tsx`). Added real production SMS tests in `tests/test_otp_forwarder.py` (79/79 passing across OTP and mobile contract test suites).

### 2026-10-09 — Security Secret Rotation, Loopback Binding & Fail-Closed Startup Validation

- Rotated historical leaked secrets in `.env`: `JWT_SECRET` (64-char), `POSTGRES_PASSWORD` (32-char), `REDIS_PASSWORD` (32-char), and `API_KEY` (47-char) with cryptographically random tokens, breaking the git-history exposure chain (`match_leaked = False`).
- Enforced local loopback binds in `.env`: `POSTGRES_BIND=127.0.0.1` and `REDIS_BIND=127.0.0.1`, closing external network exposure of database and cache ports.
- Reduced JWT cookie TTL: set `JWT_ACCESS_TOKEN_EXPIRE_MINUTES=240` (4 hours) down from 24 hours, shrinking the replay attack window on plaintext HTTP.
- Provisioned OTP and alert webhook tokens: generated 64-char `OTP_WEBHOOK_SECRET` and `ALERT_WEBHOOK_SECRET` in `.env`, and updated `scripts/generate_secrets.py` to produce them.
- Wired fail-closed environment validation to application boot: connected `validate_environment()` directly to FastAPI `lifespan` in `app/main.py:117`, halting the server with `RuntimeError` if critical production configuration is missing.
- Replaced state machine bypass: eliminated manual status assignment in `scheduled_waybill_executor.py:276` with validated `JobStateMachine.transition(session, job, TaskStatus.NEEDS_REVIEW.value, ...)`.
- Replaced silent pass with logging: replaced `except Exception: pass` in `app/services/otp_delivery.py:141` with `logger.warning(...)`.
- Resolved Mypy type-narrowing in `app/services/forwarder_health.py:124` (`if receipt and probe_timestamp is not None:`).
- Added comprehensive unit tests in `tests/test_config_validation.py` covering dual production environment indicators (`NODE_ENV` / `ENVIRONMENT`) and lifespan `RuntimeError` fail-closed behavior (16/16 passing).
- Formatted entire repository with `black` (427 files clean) and verified 0 Ruff linter errors, 0 Mypy type errors across 217 files, 55 frontend tests, and 2,342 backend tests passing.

### 2026-10-09 — Primary SMS Relay & Driver Heartbeat Persistence Subsystem

- Added Primary SMS Relay (`BP1#...`) support with instantaneous modem handover and multi-channel dual-dispatch (SMS + parallel HTTP) to `SMS-Forwarder-Pro`.
- Added persistent 90-day driver connection tracking in Redis (`rpa:forwarder:connected:{phone}`) on `HEALTH_CHECK` pings and gateway SMS reception, removing premature 30-minute disconnection alarms for mobile drivers on the road.
- Disentangled "Provisioned" (`provisioned: true`) from "Permissions Complete" (`permissions_complete: true`) and added `permissions_revoked` check so that revoked permissions immediately prevent false green verification (`forwarder_connection_verified: false`).
- Implemented atomic merge preservation in `forwarder_health.py` (`record_observation`) with Lua `MERGE_OBSERVATION` and robust Python `get`/`set` fallback, preventing SMS packets or mock harnesses from wiping driver permissions or connection timestamps.
- Added strict timestamp validation in test probe handling (`BP1#...#TEST`) and fail-closed HTTP 503 handling on storage outages.
- Updated test suites with 4 automated test cases across OTP test contracts: `tests/test_otp_forwarder_hardening.py` (10/10 passing) and `tests/test_otp_delivery_contract.py` (36/36 passing), plus 4/4 passing in independent review suite `graphify-out/sms-review/test_health_review.py`.

### 2026-10-09 — Systemic audit remediation and 32GB Compose alignment

- Applied verified 32 GB RAM Central Server cgroup limits directly to Compose files:
  `compose/infra.yml` (Postgres 4.0 GB / shared_buffers 1GB / max_connections 150, Redis 1.0 GB / maxmemory 800mb),
  `compose/backend.yml` (Backend API 1.5 GB / 4 workers, Celery Worker 1 4.5 GB / shm_size 1.5 GB, Beat 512 MB, Scheduler 1.0 GB),
  `compose/web.yml` (Frontend 1.5 GB), `compose/proxy.yml` (Squid 1 256 MB), and `compose/android.yml` (Redroid 4.0 GB / 2.0 CPUs).
- Staged all 13 reference files under `docs/agent-reference/` into Git, restoring full link resolution from `AGENTS.md`.
- Corrected active OTP mobile endpoint in `CRITICAL_RULES.md` to `IssueDocumentByOtp` (fixing legacy web name `IssueDocumentByOtpNew`).
- Added loud runtime deprecation warning in `app/core/config.py` when legacy web transport (`UTCMS_TRANSPORT="web"`) is chosen.
- Clarified Redroid live runtime switch status in `docs/ANDROID_CLIENT_IMPLEMENTATION_PLAN.md` to eliminate contradictory deployment assertions.
- Added untracked testing/IDE artifacts (`.coverage`, `.gemini/`, `.playwright-mcp/`) to `.gitignore` and tracked `.graphifyignore`.
- Added connection reuse and context manager lifecycle (`__aenter__`, `__aexit__`, `close`) to `UtcmsMobileClient` and guaranteed safe session termination via `finally` block in `WaybillAutomationBot.run_mobile_waybill` to eliminate socket leaks.
- Added 3-attempt polling loop with 1.5s backoff for `client.get_tracking_code` in `WaybillAutomationBot` to handle asynchronous UTCMS tracking code assignment without premature drops to `unknown`.
- Fixed dry-run captcha validation bug in `WaybillAutomationBot` to evaluate resolved `issue_cap_token` variable.
- Enforced Tehran timezone (`TEHRAN_TZ`) for default shipping start/end timestamps in `mobile_payload_adapter.py` to prevent Rule 4006 rejections.
- Added Persian/Arabic digit normalization and resilient integer parsing with comma stripping (`_to_int`) for cargo and financial fields in `mobile_payload_adapter.py`.
- Added unit tests in `tests/test_utcms_mobile_contract.py` covering session lifecycle, Persian digit normalization, Tehran timezone defaults, and numeric resilience. Verified 31 passed tests.

### 2026-10-07 — Complete interrupted audit and verify current contracts

- Formulated and documented the hardware profile upgrade for the Central Server (32 GB RAM / 8 vCPU cores).
  Redistributed the container memory budget to ~20.0 GB in Model B (preserving ~12.0 GB OS headroom),
  specified container memory limits for PostgreSQL (4.0 GB), Redis (1.0 GB), Redroid (4.0 GB / 2.0 CPUs to mitigate
  server-side OOM risks), Celery Worker 1 (4.5 GB, shm_size 1.5 GB), Backend API (1.5 GB with 4 Uvicorn workers),
  and Celery Scheduler (1.0 GB).
- Explicitly aligned repository authority documents (`CRITICAL_RULES.md`, `AGENTS.md`, and `docs/INDEX.md`)
  with the active production architecture: direct Mobile API Transport (`UtcmsMobileClient`) for waybill issuance,
  server-side virtual Android (`Redroid` + `FakeTraveler`) for GPS/shipping lifecycle, and universal Android
  SMS forwarder (`SMS-Forwarder-Pro`) for event-driven OTP intake. Retired legacy web browser form submission
  (`Playwright UI` / `HagigiHogugi`) from all active guidelines and added `.graphifyignore` to prevent legacy
  browser automation modules from skewing knowledge graph hub centrality.
- Closed two ambiguous shipping-start paths: transport failure preserves an
  unknown trip and does not create a registered-origin witness; tracking remains
  intact, and automatic completion/replay are blocked pending reconciliation.
- Isolated background proxy screening in the test harness so singleton refresh
  locks and external requests cannot outlive tests. Removed two tests for an
  unused legacy OTP writer; verified recipient isolation through actual HTTP,
  Lua and Redis intake instead.
- Replaced CARTO tiles that returned an API-key placeholder with two public
  OpenStreetMap providers and updated the provider picker and PWA cache rule.

- Recovered the interrupted session and independently reviewed OTP/security,
  frontend, shipping, map and historical reporting changes. Added executable
  tenant cleanup and structured-log privacy regressions.
- Removed CAPTCHA solutions/expressions from diagnostic metadata and logs.
  Kept private rejection images with digest/size and bounded operational context.
- Scoped Android mock attribution to the matching provider, honored explicit
  non-mock markers, and rejected invalid uptime or implausible future timestamps.
  Validated persisted route geometry and preserved canonical user-coordinate
  authority without silently substituting city centroids.
- Fixed stale timeline/account UI state and rejected shipping responses being
  presented as success. History search follows displayed historical identities.
- Changed dispatcher Redis routing to asynchronous selection and made the common
  delay helper awaitable. Per-intent worker selection and fail-closed behavior
  are covered by regression checks.
- Ran a full PostgreSQL 16.15 migration upgrade, fuel migration downgrade and
  re-upgrade in an isolated local cluster. Production migration remains separate.
- Corrected unsupported Android capacity/RAM claims in the supplied report.
  Final checks and deployment limits are recorded in the
  [continuation report](audits/2026-10-07/REPORT.fa.md). The full frontend dependency
  audit still reports unpatched `braces` development dependencies; its CI gate
  remains enabled.


### 2026-10-06 — Verified audit remediation and driver-specific workflows

- Bound OTP intake to durable driver/document challenges and the owning worker.
  Removed API-side/inline issuance, added token-owned renewable leases, database
  mutation fences, pending-stream recovery and fail-closed handling of ambiguous
  outcomes. Pending OTP documents prevent new submissions for the same driver.
- Removed query-string webhook credentials. Added tenant-owned forwarder setup
  without exposing secrets, truthful readiness, asynchronous acceptance messages
  and session-scoped frontend caches. HTTP clipboard failures are handled.
- Added driver/day filters and individual fuel-history records with pagination;
  removed sums of repeated quota snapshots. Historical inquiry identity and UTC
  timestamps are captured independently of the driver's later profile changes.
- Fixed shipping recovery starvation after 50 rows, reporting validation and
  Tehran-day boundaries. Hardened private diagnostic/cache files and tensor-only
  model loading while preserving the upstream UTCMS MD5 wire contract.
- Reworked map loading/fallback and address autofill. Old addresses clear on pin
  change; street-level geocoding and distinct nearby cache keys replace city-level
  results. Approximate results require manual exact address. Map popups use DOM
  text rather than untrusted HTML. Road snapping preserves requested and effective
  anchors with visible provenance and conservative travel time.
- Made browser smoke tests hermetic and live UTCMS tests explicit opt-in. Added
  genuine Redis and PostgreSQL integration coverage and Node20 frontend test steps.
  CI requires configured services; absent local PostgreSQL is reported as skipped.
- Evidence, final gate results and remaining limitations are recorded in
  [the audit report](audits/2026-10-06/REPORT.fa.md). Runtime dependency audit is
  clean in the recorded frontend run; the full dev audit retains an unpatched
  `braces` advisory and remains a blocking signal in ci-cd. No force-upgrade or
  audit bypass was added.
- Rollout requires the new additive fuel-history migration and coordinated API,
  scheduler and worker versions. Drain legacy inline OTP workers; legacy pending
  documents without a verified challenge require read-only reconciliation.
  This task does not provide production or live UTCMS verification.

### 2026-10-06 — Split oversized agent guide into local references

- Reduced the always-loaded `AGENTS.md` from 113,437 to 11,802 UTF-8 bytes.
  Retained mandatory conduct, project identity, conventions, critical warnings,
  testing guidance and a task-to-reference reading map in the core.
- Moved the remaining text into 11 project-local topic/history files under
  `docs/agent-reference/`, plus a navigation index. Every resulting Markdown
  file is below 24,000 bytes (largest: 14,719 bytes). Ordinary links load content
  on demand; no recursive imports or global BarPro rules were introduced.
- Preserved all 1,084 original lines exactly once in 21 marked blocks.
  `docs/agent-reference/migration-manifest.json` records source spans and hashes;
  reassembly matched the original backup byte-for-byte. Historical commands,
  dated success claims and old runtime statements are explicitly labelled as
  reference snapshots requiring current evidence, not new execution authority.
- Validation: 59 local Markdown links resolve; exact content preservation, byte
  limits and absence of automatic imports passed. Gemini CLI 0.61.0 native
  loader read the new core and unchanged global rules without import errors.
  The global settings and project context setting were also unchanged. Evidence:
  `~/Downloads/antigravity-review-2026-10-06/evidence/barpro-agents-split-verification.json`
  and `barpro-gemini-context-after-split.json` in that directory.
- Live Antigravity verification remains unverified: a completion-mode probe
  failed at the eligibility check with HTTP 403 on `/v1internal:loadCodeAssist`,
  before a model response. The user will perform in-app checks; loading success
  is not evidence of model compliance. No application code or production state
  was changed by this documentation split.

### 2026-10-06 — BarPro-only agent context and migration guidance

- On the audited workstation, removed the BarPro-specific Vercel hybrid recipe
  and RPA Worker rewrite checklist item from the global `vercel-nextjs-expert`
  skill. Preserved the exact excerpts in the repository-local
  `.agents/skills/barpro-deploy-ops/references/historical-vercel-hybrid-migration.md`
  and linked them only from the local deployment skill. They are explicitly
  historical/unverified proposals, not current deployment requirements.
- Added project-local `.gemini/settings.json` with
  `context.fileName: ["GEMINI.md", "AGENTS.md"]`, so Gemini CLI can combine the
  existing global conduct rules with this repository's agent instructions.
  Generic v3 evidence, documentation-first, planning, and workflow improvements
  remain global; no BarPro content is imported by the global policy.
- Verification: original files were backed up and hash-checked; the migration
  preserves all non-BarPro global skill text and both archived excerpts exactly.
  Gemini CLI 0.61.0 native schema/context-loader helpers read the global and
  project instructions under the project setting. This checks native loading,
  not an existing interactive session refresh or model compliance. Evidence is
  recorded on the audited workstation in
  `~/Downloads/antigravity-review-2026-10-06/evidence/barpro-scope-migration.json`
  and `barpro-gemini-context.json` in the same directory.
- This change updates agent context/documentation only; no application code,
  production deployment, or live UTCMS operation was changed. The existing
  `.gitignore` excludes `.agents/`; the local skill/reference remain local files.

### 2026-10-06 — Universal Android forwarder compatibility, resilient JSON decoding & driver national code fallback

#### Added
- **Resilient JSON parsing helper** (`app/services/otp_wakeup_consumer.py`: `_safe_json_dict`):
  safely handles both Python dicts and JSON strings in `result_json` and `payload_json`, preventing
  empty-dict fallback when database drivers or older jobs return stringified payloads.
- **Direct job completion by ID** (`app/services/otp_wakeup_consumer.py`: `resolve_and_complete_pending_job_for_otp`):
  accepts an explicit `job_id` parameter to complete pending jobs directly without relying solely on phone matching.
- **Driver national code fallback** (`app/services/waybill_job_service.py`: `submit_otp`):
  when `job.driver_id` is null, automatically resolves and sets the tenant's driver via `driver_national_code`
  or `phone` from `payload_json`, eliminating false 400 errors.
- **Universal Android forwarder field & auth mapping** (`app/api/routes/otp_forwarder.py`):
  accepts webhook authentication via `Authorization: Bearer <token>`, `X-Webhook-Token`, `X-Webhook-Secret`,
  or query parameter `?token=<secret>`. Broadened payload mapping to recognize `smsBody`, `messageBody`,
  `address_from`, `phoneNumber`, `receiver`, `receiver_phone`, `time`, `date`, and «کد ثبت بارنامه».
- **Forwarder connectivity probes** (`app/api/routes/otp_forwarder.py`):
  added lightweight `GET /api/v1/otp/ping` and `GET /api/v1/otp/health` endpoints for Android forwarder apps
  to verify network routing and service readiness.
- **Waybill OTP route alias** (`app/api/routes/multitenant.py`):
  added `@router.post("/waybill-jobs/{job_id}/otp")` as an alias to `/submit-otp`.
- **Manual OTP auto-completion** (`app/api/routes/otp_forwarder.py`: `submit_manual_otp`):
  triggers background job auto-completion when manual OTP is submitted with `job_id` or `phone`.

#### Changed
- **Registration proof reduced to two witnesses** (`AGENTS.md` §2, `CRITICAL_RULES.md` §0,
  `docs/UTCMS_CONSTRAINTS.md`, `docs/UTCMS_RECONCILIATION.md`,
  `docs/UTCMS_BOT_BEHAVIOR_CONTRACT.md` §6, `docs/INDEX.md`, `DEPLOYMENT_GUIDE.md`,
  `docs/operations/DEPLOYMENT_GUIDE.md`, `docs/operations/runbook_tracking_first_acknowledgement.md`,
  `docs/BARPRO_KNOWLEDGE_GRAPH.md` §7.3): the per-waybill third witness (a matching
  UTCMS History/Search record) is removed from the proof contract. Proof is now
  (1) a non-empty tracking code in the RPA response and (2) the same code persisted
  in `waybill_jobs.result_json`. Final confirmation is batched rather than
  per-waybill: `orchestrator.reconciliation.audit_tracking_received`
  (`reconcile_tracking_received_jobs`) sweeps every tracking-received job in one
  pass with `audit_only=True`, setting `reconciled_at` and
  `mutation_status='confirmed'`; no per-waybill History check is needed during the
  day. The `JobStateMachine` success gate (`mutation_status='confirmed'`
  + `reconciled_at` + persisted tracking code) is unchanged in code.
- **Domain skills scoped to the repository**: all BarPro agent skills moved from
  global installs (`~/.claude/skills`, `~/.config/opencode/skills`, `~/.gemini/skills`,
  `~/.agents/skills`) into `~/GitHub/BarPro-main/.agents/skills/` (21 skills);
  global copies and symlinks removed. The temporary `barpro-leak` stub (which
  dumped `git status/log/diff` into a failing-test message) was then deleted
  outright, leaving 20 skills.
- **BarPro skills aligned with the two-witness rule**:
  `barpro-waybill-submission-safety` (SKILL.md + `references/call-site-map.md`),
  `barpro-rpa-ops`, and `barpro-master-upgrade` now state the two-witness proof
  plus batched `audit_tracking_received` confirmation; stale
  `038_add_multiroute_batch_distance` head reference updated to the current
  `041_driver_plate_tracking_fields`.

### 2026-10-05 — Event-driven OTP wake-up, lease locking, Iranian DST tolerance & single-flight attribution

#### Added
- **Event-driven OTP wake-up consumer** (`app/services/otp_wakeup_consumer.py`): background
  stream processor listening on `rpa:otp:stream` with consumer group `barpro_otp_group` and
  atomic `XACK`. When an OTP arrives, `resolve_and_complete_pending_job_for_otp` immediately
  locates waybill jobs waiting for OTP (`WAITING_OTP` or `UNKNOWN` with `otp_required`) and executes
  immediate document completion via `submit_otp`. Resolves the late SMS race condition where an
  SMS arrives at second 125 after the 120-second worker loop expired.
- **Distributed lease locking** (`app/automation/otp_keys.py`: `reserve_otp_issue_lease`,
  `release_otp_issue_lease`): atomic 30-second TTL distributed lease with token ownership
  verification (`lock:otp:issue:{job_id}`). Prevents concurrent issuance and race conditions
  between the active Celery worker and the webhook background issuer.
- **Single-flight phone attribution fallback** (`app/services/otp_wakeup_consumer.py`:
  `resolve_single_flight_pending_phone`): solves the Iranian SIM card limitation where Irancell
  and MCI SIMs lack MSISDN on the chip. When incoming SMS arrives via a shared GSM gateway without
  a driver phone, the system checks whether exactly one waybill is pending OTP; if so, the SMS is
  safely attributed to that job.
- **Multi-channel driver phone attribution** (`app/api/routes/otp_forwarder.py`): incoming SMS
  can attribute the driver phone via path parameter (`/sms-forwarder/{driver_phone}`), query
  parameter (`?driver_phone=...`), custom header (`X-Driver-Phone`), or JSON body field,
  simplifying setup for third-party Android forwarding apps. Form-data parsing preserves path-based
  driver phone even when form data lacks phone fields.
- **Client clock drift recovery** (`app/api/routes/otp_forwarder.py`): webhook intake catches
  future timestamp errors caused by fast Android client clocks and automatically falls back to
  authoritative server `now`, ensuring valid OTP codes are never rejected due to phone clock skew.
- **Broadened Iranian and UTCMS OTP regexes** (`app/api/routes/otp_forwarder.py`: `extract_otp_code`):
  expanded keyword detection to capture `کد صدور`, `کد یکبار مصرف`, `کد امنیتی`, `رمز تایید`, and
  `کد مجوز` while strictly maintaining security blocks against banking and promo SMS.
- **Stale pending job self-pruning** (`app/services/otp_wakeup_consumer.py`:
  `resolve_single_flight_pending_phone`): automatically cleans up dead/expired members from Redis set
  `rpa:otp:active_pending_jobs` when only one valid job retains a live `rpa:job:pending_doc` cache,
  preventing phantom ambiguity false positives.
- **Resilient state machine transition on OTP issue** (`app/services/waybill_job_service.py`):
  `submit_otp` safely transitions jobs from `unknown` / `needs_review` through `reconciling` to
  `success`, and `waiting_retry` / `retrying` through `in_progress` to `success`, preventing
  `StateTransitionError` when completing jobs parked in review or retry states.
- **Automated start-of-shipping lifecycle initiation on OTP issue** (`app/services/waybill_job_service.py`):
  immediately upon issuing document via OTP, `submit_otp` invokes `init_shipping` and calls
  `register_start_of_shipping` with origin coordinates and 2-point trace witness, queuing the trip
  for automated destination arrival completion by Celery Beat.
- **Celery periodic stream consumer task** (`app/workers/tasks.py`: `sweep_otp_stream`,
  `app/workers/celery_app.py`): scheduled every 5 seconds (`schedule(5.0)`) on `rpa_scheduler`
  (`RPA_SCHEDULER_QUEUE`) with 4-second expiry to drain and acknowledge Redis Stream events
  reliably without introducing worker queue delays.
- **Client opt-in OTP flow flag** (`app/schemas/multitenant.py`): added `allow_otp_flow: bool = True`
  to `WaybillJobCreate` and `WaybillBatchItemCreate`, enabling automated OTP flow by default for all jobs.
- **Standalone SMS Forwarder simulator** (`scripts/sms_forwarder_simulator.py`): CLI utility
  supporting direct webhook POSTs, HMAC-signed gateway envelopes, and health probes for offline
  and operator testing without a physical Android device.

#### Fixed
- **Squid proxy injection for OTP submission** (`app/services/waybill_job_service.py`): `submit_otp`
  now instantiates `UtcmsMobileClient` using `get_worker_proxy_url()`, routing mobile requests
  through the designated Iranian Squid proxy and safeguarding the central server IP.
- **Atomic consumed OTP invalidation** (`app/automation/otp_keys.py`: `consume_scoped_otp`):
  called immediately upon successful waybill issuance across `waybill_job_service.py`,
  `waybill_enhanced.py`, and `waybill_bot_multitenant.py`. Atomically deletes `rpa:otp:job:{job_id}`,
  `rpa:otp:phone:{phone}`, `rpa:job:pending_doc:{job_id}`, and cleans up pending sets so a stale
  OTP cannot be reused for a subsequent waybill.
- **Iranian DST clock skew tolerance** (`app/services/otp_delivery.py`: `sms_received_at`):
  handles unpatched Android devices affected by the Iranian government's 1402 cancellation of
  daylight saving time. Automatically normalizes 1-hour (3600s +/- 90s) clock shifts back to UTC/server
  time, avoiding false 410 or 422 rejections.
- **Ambiguous OTP protection guard** (`app/api/routes/otp_forwarder.py`, `otp_wakeup_consumer.py`):
  when more than one waybill is pending OTP and an incoming SMS lacks a `driver_phone`, the system
  fails closed with HTTP 422 (`AMBIGUOUS_OTP`) rather than guessing, requiring driver phone attribution.
- **Server `ingested_at` anchoring** (`app/automation/waybill_enhanced.py`): evaluates OTP freshness
  against server-side ingestion timestamp rather than client device clock, preventing premature timeouts.
- **Zero-latency worker loop exit** (`app/automation/waybill_bot_multitenant.py`): Celery worker wait
  loop polls `completed_otp:{job_id}`, allowing instant exit with `SUCCESS` as soon as the webhook
  completes the document.

#### Tests
- New comprehensive test suite: `tests/test_otp_wakeup_and_lifecycle.py` (13 tests verifying late
  SMS auto-completion, lease locking concurrency, atomic key cleanup, device clock skew, single-flight
  attribution, Redis streams processing, Iranian DST tolerance, ambiguous OTP rejection, and full
  HTTP E2E webhook-to-job database completion). All 84 OTP, forwarder, and contract tests passing.

### 2026-10-04 — GPS shipping fences, durable OTP intake & operator-endpoint hardening

#### Added
- **Durable, ordered OTP intake** (`app/services/otp_delivery.py`: `accept_forwarded_otp`,
  `sms_received_at`, `recipient_phone`). A single Lua transaction performs dedup + ordering +
  the durable write + pub/sub, so a retry never refreshes an OTP's TTL nor resurrects a
  consumed code, and an older SMS can never overwrite a newer one (409). 300 s TTL, 30 s
  clock-skew gate, fail-closed on Redis loss (503 — delivery is never acknowledged before the
  durable write succeeds). Raw SMS text is never stored nor echoed. Backed by a real-Redis /
  real-Lua contract test (`tests/test_otp_delivery_contract.py`).
- **Signed inbound SMS gateway** `POST /api/v1/otp/sms-gateway`: a GSM-relay path
  authenticated by an HMAC-SHA256 envelope `BP1#phone#timestamp#code#signature`
  (`sig = hmac(OTP_WEBHOOK_SECRET, "#".join(parts[:4])).hexdigest()[:32]`), sender-matched to
  the recipient phone. Shares one delivery identity with the direct `sms-forwarder`, so the
  two paths dedupe against each other.

#### Fixed
- **OTP forwarder hardening** (`app/api/routes/otp_forwarder.py`): 16 KB body cap (413); a
  `HEALTH_CHECK` probe returning `{"status":"ready","protocol":"barpro-otp-v1"}`; encrypted
  envelopes rejected (422); `driver_phone` (`09xxxxxxxxx`) now **required** for recipient
  routing; fail-closed on Redis loss; and `extract_otp_code` rewritten keyword-anchored so a
  tracking code, phone number, or bank/discount SMS is never mistaken for an OTP.
  `submit-manual` no longer attaches a caller phone when `job_id` is set (tenant isolation).
- **Shipping lifecycle fences** (`app/automation/gps_shipping_manager.py`,
  `app/api/routes/shipping_gps.py`): durable `starting`/`finishing` fences with a dual-key
  completion claim and a reaper (`reclaim_stuck_shipping_fences`) that reclaims only abandoned
  fences (older than the claim TTL, no claim held) and never steals a live mutation; Redis-down
  fails closed. The Beat end-of-shipping path no longer stamps an explicit UTCMS refusal as
  `self_declared_auto_complete` — an explicitly-rejected `4011` now routes to `needs_review`,
  matching the `/finish` endpoint. The ETA gate (`shipping_wait_reason`) is fail-closed on a
  missing or future `estimated_end_at`.
- **Mobile bot finish fallback** (`app/automation/utcms_mobile_client.py`): a 404 from
  `finish_shipping_with_gps` no longer fabricates a `resultCode 200`; it falls back to
  `RegisterEndOfShipping`, whose trace validator rejects a single-point finish — an
  unregistered finish is never reported as success.
- **Issuance auto-start state** (`app/automation/waybill_bot_multitenant.py`): a post-issuance
  `RegisterStartOfShipping` now honors the UTCMS result (acknowledged → `in_transit`; explicit
  reject → `unknown`; raised/ambiguous → `in_transit`, still sweepable) and records the origin
  witness, instead of hard-setting `in_transit` and swallowing exceptions.
- **History date filters are now strict** (`app/api/routes/multitenant.py`):
  `_parse_history_date_bounds` rejects any value outside `YYYY-MM-DD` with HTTP 400 (previously
  `datetime.fromisoformat` silently accepted compact / ISO-week / datetime / tz-aware forms and
  discarded the time or offset), and rejects a reversed range (`date_from` after `date_to`)
  instead of returning a silently-empty page.
- **Manual `/shipping/finish` escalates the Rule-4012 distance target** the same way the Beat
  auto-complete path does, so an operator finishing a short / intra-city route whose first
  attempt was rejected for `<2 km` no longer re-sends an identical trace and loops until
  `needs_review`.
- **Clean-IP pool**: per-provider harvest caching + HTML/proxy-list payload detection and
  stricter schema validation; targeted Iranian harvesters tag source country explicitly.

#### Tests
- New contract suites: `tests/test_otp_delivery_contract.py`,
  `tests/test_mobile_shipping_start_contract.py`, `tests/test_gps_shipping_batch_g.py`,
  `tests/test_shipping_backoff_and_contract.py`. The real-Redis OTP contract test and the
  Android bridge socket tests skip gracefully where the environment forbids binding a local
  socket (they run fully in CI). Run the suite on the current commit and report its exact
  result; dated runs are snapshots, not timeless facts.

### Fixed — Offline audit follow-up

- Replaced the enterprise example's removed exception and workflow helpers with
  `UTCMSException`, `ErrorCode`, `WorkflowState`, and `resilient_step`. Its executable
  demo now uses `httpx.MockTransport` for a read-only job lookup; it never submits
  a waybill or treats an observed status as independent registration evidence.
- Aligned OpenAPI with the existing `2.9.17-unreleased` development label and
  refreshed current migration references to `041_driver_plate_tracking_fields`.
  Removed fixed current-suite count assertions; dated historical runs remain
  snapshots, and deployment status still requires separate runtime verification.

### Added

- **Driver tracking — پیگیری راننده‌ها**: new `GET /api/v1/driver-tracking` endpoint and a
  dedicated tab on the drivers page. Each plate shows ثبت امروز (today's registrations),
  تعداد هدف ثبت (per-period target), and کل ثبت (period total). Totals are computed over
  repeating 15-day Jalali periods anchored at ۹ مهر (phase 1: ۹–۲۳ مهر، phase 2: ۲۴ مهر–۸ آبان، …),
  so کل ثبت returns to zero automatically when a period ends — no scheduled reset needed.
  Plate controls under each plate: فعال/غیرفعال (status), رفت و برگشت, حمل, plus an editable
  target count (all via `PUT /api/v1/plates/{id}`). «ثبت» counts jobs with status
  `success`/`issued`/`in_transit`/`delivered`. New columns on `driver_plates`
  (`target_count`, `round_trip`, `in_transport`) via Alembic `041_driver_plate_tracking_fields`.
  Evidence: `tests/test_driver_tracking.py` (12 tests: conversion references, phase boundaries,
  exact Tehran-midnight edges, Jalali new-year crossover, automatic rollover,
  today counts, tenant isolation, toggle persistence).

### Fixed

- **History date filters excluded the selected end day**: `date_from`/`date_to`
  were parsed to UTC midnights and `created_at <= date_to` was applied, so
  filtering a single day (`from=X to=X`) returned virtually nothing. Both
  `GET /api/v1/waybill-jobs` and `GET /api/v1/fuel-inquiries` now convert the
  `YYYY-MM-DD` pickers to Tehran-calendar-day UTC bounds
  (`app/core/jalali.py::tehran_day_bounds_utc`) and treat `date_to` as an
  exclusive end bound — the entire selected end day is included. Invalid
  dates now return HTTP 400 with a Persian message instead of 500.
  Evidence: `tests/test_history_date_filters.py` (10 tests: Tehran bounds,
  single-day waybill + fuel inclusion, open ranges, invalid-date 400,
  route-level end-to-end regression, «ثبت‌شده» aggregate; 8/9 date tests
  fail on the old code).
- **New «ثبت‌شده» status filter in history**: the status dropdown filtered only
  exact `success` as «موفق», while the tracking panel counts a registration
  as `success`/`issued`/`in_transit`/`delivered`. Passing
  `status=registered` now matches that same set (reuses
  `driver_tracking_service.REGISTERED_STATUSES`), so per-driver/per-plate
  daily registrations are viewable in one click. Exact statuses still work.
- **C1 verification follow-up**: retired the last residual write to the legacy
  global `rpa:otp:latest` key (`submit_otp` in `app/services/waybill_job_service.py`);
  OTPs are now stored under the job-scoped key only (`rpa:otp:job:{job_id}`).
- **History plate filter missed Persian digits**: the plate input accepts
  Persian digits (example shows them) but the backend only stored/normalized
  Latin digits, so a Persian-digit search missed matching jobs. The frontend
  now normalizes with `normalizeDigits` before sending.
  Evidence: code-verified in `apps/web/src/app/history/page.tsx`.

### Changed

- **Map tiles default to CARTO (commit `13bab19`)**: Google tile endpoints are
  blocked in Iran, so the shipping/map views now default to CARTO basemaps
  instead of failing on Google tiles. (Clarification: the 2.9.15 entry's "CARTO
  voyager stays the default" referred to the tile-fallback layer's default; the
  map picker's provider default was still Google until this commit.)
- **FakeTraveler apply wired into the shipping workflow (commit `13bab19`)**:
  the FakeTraveler mock-location apply step is now part of the automated
  shipping lifecycle instead of a manual side action.

### Fixed

- **A1 — tenant-scoped idempotency keys (critical)**: `WaybillTaskService.build_idempotency_key`
  now requires the caller's `client_id` and delegates to the canonical builder in
  `app/core/submission_identity` (same as the scheduler path); both idempotency lookups in
  `create_or_get_task` are additionally filtered by `client_id`. A second tenant submitting a
  colliding raw key now gets its own task row instead of hijacking the first tenant's job.
  Evidence: `tests/test_global_idempotency.py::test_two_tenants_same_raw_idempotency_key_each_get_own_task_row`.
- **A2 — fail-open 4011 recovery is now fail-closed (`app/automation/gps_shipping_manager.py`)**:
  the business-rule code is extracted structurally (structured `result_code`, else the strict
  `(code: NNNN)` pattern); free-text "4011" mentions no longer count as the rule. A failed
  4011-recovery marks the trip `unknown` and routes the job through `JobStateMachine` into
  `reconciling` — never `success`; `reconciled_at`/`mutation_status="confirmed"` are never
  fabricated. Evidence: `tests/test_gps_shipping_batch_g.py` (A2 ×5).
- **B1 — `/start` no longer bricks the job on transient apply failure
  (`app/api/routes/shipping_gps.py`)**: transient FakeTraveler/ADB apply and readback failures
  still 503, but the persisted state stays retryable — no more 409-bricked paid waybills.
  Evidence: `tests/test_faketraveler_waybill_coords.py::test_start_apply_failure_keeps_job_retryable`.
- **B2 — readback verifies stored waybill coords (`app/api/routes/shipping_gps.py`)**: the
  Android anchor readback now compares against `state.origin_*`/`dest_*` (what `apply_location`
  wrote) instead of the operator's request anchor, aligning the 5 m readback tolerance with the
  0.0002° (~22 m) route gate. Evidence: 10 m-offset regression tests in
  `tests/test_faketraveler_waybill_coords.py`.
- **B3 — device-wide lock for `apply_location` (`app/android_bridge/`)**: every FakeTraveler
  apply is serialized through the Redis lock `lock:android-device:mutation` in addition to the
  per-job lock; lock unavailable/busy → `BridgeError` (503), never proceeds unlocked.
  Evidence: `tests/test_android_bridge_controller.py::test_concurrent_apply_location_serializes_on_shared_device`.
- **B4 — `/shipping/*` reachable through production nginx**: added `shipping` to the
  backend-proxy regex in `infra/nginx/http-server.conf` (was 404ing into the Next.js fallback).
- **B5 — latent `/api/v1` doubling fixed (`apps/web/src/lib/api.ts`)**: `API_BASE_URL` now
  strips trailing `/api/v1` as well as `/api`; `npm run typecheck` + `npm run lint` clean.
- **C1 — unscoped global OTP key retired**: `store_otp_in_redis` no longer writes
  `rpa:otp:latest`; automation readers use job-scoped → phone-scoped keys via
  `app/automation/otp_keys.py` (never the global key). Evidence:
  `tests/test_tenant_isolation_batch_c.py::test_c1_two_tenants_consume_only_own_otp`.
- **C2 — legacy `/waybill/create-with-map` auth-state scoping**: Playwright auth-state path +
  Redis session-vault key are now scoped per tenant (`client-{id}` for JWT, `infra` for
  API-key-only), including the queue inline path (`queue_manager._execute_inline` threads
  the task tenant's scope). Evidence:
  `tests/test_tenant_isolation_batch_c.py::test_c2_queue_inline_path_scopes_auth_state_to_task_tenant`.
- **C3 — session-vault `client_id` threading**: driver vault keys are
  `utcms:driver:{token,refresh,auth-lock}:{client_id}:{national_code}` with no cross-tenant
  fallback; all call sites (`shipping_gps.py`, `waybill_bot_multitenant.py`,
  `reconciliation_service.py`, `waybill_job_service.py`) pass the caller's tenant.
  Evidence: `tests/test_gps_session_vault.py::test_c3_vault_uses_scoped_key_when_client_id_provided`.
- **C4 — shipping mutation lock ordering**: `_get_job_and_driver` ownership check now runs
  before `lock:shipping:{job_id}` acquisition — foreign/unknown jobs get 404 without
  squatting the lock. Evidence:
  `tests/test_tenant_isolation_batch_c.py::test_c4_other_tenant_cannot_squat_shipping_lock`.
- **C5 — admin driver creation requires explicit `client_id`**: master_admin without
  `client_id` gets 400 (unknown tenant → 404); the first-active-client silent fallback is
  removed. Evidence:
  `tests/test_tenant_isolation_batch_c.py::test_c5_master_admin_without_client_id_rejected`.
- **D1 — `JWT_SECRET` ≥ 32 chars enforced at startup** (CRITICAL_RULES §1): `UTCMSConfig()`
  raises and `validate_environment()` reports an error for short secrets (deny-list kept).
  Evidence: `tests/test_config_validation.py::test_validate_short_jwt_secret_rejected`.
- **D2 — `.env.example` completeness**: all env vars read by production code are now
  documented (6 were genuinely missing; 15 were already present as appendix entries).
  `SECONDARY_EGRESS_IP` is the canonical name; `SECONDARY_IP` kept as legacy alias in both
  deploy scripts.
- **E1 — tracking-received jobs now get their History witness**: `POST
  /api/v1/admin/alerts/reconcile/{job_id}` passes `audit_only=True` (no more early-return
  skip); new `ReconciliationService.reconcile_tracking_received_jobs()` audit sweep attaches
  the UTCMS History/Search witness to acknowledged-but-unwitnessed jobs; the dispatcher
  recognizes the `reconciliation_audit` intent; new periodic task
  `orchestrator.reconciliation.audit_tracking_received` on Beat every 10 min. SUCCESS is still
  only declared on a History witness match; the sweep never resubmits. Evidence:
  `tests/test_reconciliation_service.py:408,484`, `tests/test_admin_alerts.py:290`.
- **F1 — loop-aware bounded auth locks (`app/automation/gps_shipping_manager.py`)**: per
  `(loop, tenant, driver)` locks, FIFO-evicted at 512 entries (was: one global
  `asyncio.Lock` dict shared across event loops).
- **F3 — dead-code sweep round 2**: removed provably-unused symbols in `app/schemas/admin.py`
  (13 classes), `app/schemas/panel.py` (13 classes), `app/auth_multitenant.py`
  (`TokenPayload`, `TokenResponse`), `app/core/exceptions.py` (4 exception classes),
  `app/core/resilience.py` (`retry_with_backoff`, `ExplicitWaits`, `ResilientWorkflow`,
  `GracefulDegradation`), `app/core/error_handler.py` (3 helpers), `app/core/business_time.py`
  (2 helpers), `app/core/startup_validation.py` (`validate_or_exit`); `docs/guides/QUICK_REFERENCE.md`
  updated to the live `resilient_step` pattern.
- **F4 — silent `except: pass` → structured logging**: 15 sites across routes/services/workers
  now log with context (OTP webhook parsers, shipping state decodes, scheduler kicks, gate
  state parses); the 2 `redis.py` finalizer sites are deliberately kept with rationale.
- **F5 — per-trip completion claim**: `auto_complete_shipping` takes a Redis `SET NX` claim
  (`utcms:shipping:claim:{job_id}`, 600 s TTL); overlapping Beat runs skip instead of
  double-calling `RegisterEndOfShipping`.
- **F6 — UTC fix for the legacy StartShipping 404-fallback
  (`app/automation/utcms_mobile_client.py`)**: the fallback `StartDate` is now strict UTC ISO
  (`YYYY-MM-DDTHH:mm:ss.000Z`); Tehran-local-naive would have shifted it 3.5 h and risked
  Rule 4013.
- **F7 — `API_AUTH_MODE=off` now warns loudly at startup** (log only, no behavior change;
  default `api_key_or_jwt` unchanged).

## [2.9.16] - 2026-10-01

  ### Fixed — mypy strict pay-down (540 errors → 0), tenant-isolation gaps, Android bridge verification

  - **mypy pay-down to strict-clean (`pyproject.toml`, `jdatetime.pyi`, 60+ files)**:
    Baseline was 540 unique errors across 83 files (measured after the typecheck
    venv was completed — the earlier 0-error figure was a broken-venv artifact).
    Removed all broad `ignore_errors` overrides; optional dependencies (Playwright,
    Celery, Redis, SQLModel, Alembic, torch, keras, tensorflow) are now centrally
    declared, and `jdatetime` is covered by a minimal `jdatetime.pyi` stub instead
    of an import ignore. Strict mypy: **206 files, 0 issues**.
  - **Real runtime bugs found by the pay-down**: Playwright 1.63 `add_init_script`
    arity (WebGL spoof never applied), `timeout=` kwarg on `_goto_with_retry`
    (cookie probe never navigated), dead branches in `waybill_enhanced.py`,
    `WaybillJob`/`task_id` AttributeError in `task_service._extract_correlation_id`.
  - **Tenant isolation — GAP-1 (`app/api/routes/otp_forwarder.py`)**:
    `GET /api/v1/otp/latest` is now admin-only (`get_current_admin`); the global
    Redis key `rpa:otp:latest` carries every tenant's live OTP codes.
  - **Tenant isolation — GAP-2 (`app/api/routes/otp_forwarder.py`)**:
    `POST /api/v1/otp/submit-manual` now requires `job_id` for clients and
    verifies `(WaybillJob.client_id == client.id) AND job_id` before writing the
    job OTP key; foreign/missing jobs → 404, missing job_id → 403. Admins keep
    the global submission path.
  - **Tenant isolation — GAP-3 (`app/api/routes/waybill_map.py`, `app/services/task_service.py`)**:
    `GET /waybill/tasks/{task_id}` moved from `require_sensitive_auth` (no tenant
    identity) to `get_current_user_or_admin`; `get_task_status()` takes
    `client_id` and scopes the `WaybillJob` query; legacy non-`job_*` IDs return
    404 for clients.
  - **10 new regression tests** in `tests/test_tenant_isolation_gaps.py` covering
    cross-tenant negatives, owner positives, and admin positives — all passing.
  - **Android bridge verification (`app/android_bridge/`)**: feature flag
    (`ANDROID_BRIDGE_ENABLED`, default False, fail-closed), import independence
    (stdlib only), and `_require_enabled` gating on all public methods verified;
    113 bridge unit tests pass. Live Redroid dry-run remains blocked on
    infrastructure + user approval.
  - **Verification**: pytest **1841 passed / 0 failed**; ruff clean; black clean;
    strict mypy 206 files 0 issues.

  ## [2.9.15] - 2026-09-27

  ### Fixed — Map Grey-Tile Race, Real Tile Fallback & Frontend Performance Plan

  - **Real tile fallback (was warn-only) (`LocationMapPicker.tsx`, `ShippingRouteMap.tsx`)**:
    CARTO voyager stays the default (unfiltered); after 4 sustained `tileerror` events the
    layer now actually switches voyager → dark → OSM instead of only logging.
  - **Debounced `ResizeObserver` + unified staged invalidate (`[50, 200, 500]ms`)**:
    eliminates 0x0 grey-tile races on conditional modal mounts without layout thrash;
    timers/observer aborted on unmount.
  - **Abort-safe shipping status polling (`ShippingRouteMap.tsx`)**:
    `fetchStatus` now uses `AbortController` — no setState after unmount, no overlapping polls.
  - **Code-split Leaflet on `/new` (`apps/web/src/app/new/page.tsx`)**:
    `LocationMapPicker` is `next/dynamic(ssr:false)` with a skeleton, matching `/history`;
    Leaflet leaves the initial bundle.
  - **Tile + shell caching (`next.config.mjs`, `layout.tsx`, nginx unchanged)**:
    Workbox SWR for CARTO/OSM tiles (7d/200 entries), `/api/*` stays `NetworkOnly`;
    `preconnect`/`dns-prefetch` for `*.basemaps.cartocdn.com`; `/_next/static/` keeps
    nginx `immutable` (see `infra/nginx/http-server.conf:118-127`).
  - **Above-fold images**: `priority` + `sizes` on logos
    (`Header`, `Sidebar`, `auth/page`, `admin/layout`).
  - **Report corrections (see `docs/archive/PERFORMANCE_VERIFICATION_2026-09-27.md`)**:
    real paths are `app/workers/shipping_worker.py` and `app/travel/providers.py`
    (report paths did not exist); marker truth is cyan `#06b6d4` `pulse-marker`
    (not `#3b82f6`); quoted `146 passed` / `Next 15.0.0` / `/dashboard` logs are not
    reproducible — fresh evidence here: targeted **50 passed**, `typecheck`/`lint` clean,
    `next build` 19 routes (`/new` 18.1kB/240kB, `/history` 16.3kB/213kB).

  ## [2.9.14] - 2026-09-15

### Added — Virtual Android Observation Bridge & Verified Dual-Host Mobile Architecture

- **Dual-Host Mobile Architecture Alignment (`app/core/config.py`, `docs/UTCMS_MOBILE_AND_WAF_AUDIT_REPORT.md`)**:
  Separated CapJS PoW challenge endpoint (`https://cptch.utcms.ir/`) from live business API endpoint (`https://mobservices-barname.utcms.ir/baarnameh_sd/API`). Live wire inspection and server testing confirmed that `cptch.utcms.ir` serves exclusively the CapJS PoW mathematical challenge/redeem service (returning HTTP 404 for ASP.NET endpoints like `UserLoginV2`), while `mobservices-barname.utcms.ir` is the active host for mobile login, documents, and fleet queries.
- **Live-Fire End-to-End Verification on Central Production Server (`<CENTRAL_IP>`)**:
  Executed real driver authentication flow (driver national code redacted) through Iranian Squid proxy (`http://172.20.0.1:3128`) without WAF blocks (0% HTTP 444 / 408):
  1. Solved CapJS PoW on `cptch.utcms.ir`.
  2. Authenticated on `mobservices-barname.utcms.ir/baarnameh_sd/API/Account/UserLoginV2` with HTTP 200 OK.
  3. Cached driver bearer token in Redis Session Vault (short TTL, 240s default; refresh token 7000s default), reducing redundant login and CAPTCHA overhead and lowering HTTP 429 login rate-limit risk — not eradicating it (see `docs/archive/ANTIGRAVITY_GPS_VERIFICATION_2026-09-15.md`).
  4. Successfully retrieved driver fleet (`vin=IRGC761H07Y582039`).
- **Virtual Android Client Bridge Phase 1 (`app/android_bridge/`)**:
  Added an opt-in, lightweight observation bridge for server-side virtual Android (Redroid) running on Linux (no physical phones required). Features zero heavy dependencies (no DB, SQLModel, or ML imports), explicit ADB serial requirement (`ANDROID_BRIDGE_SERIAL`), package verification for official APK (`com.baarnameshahri`) and FakeTraveler (`cl.coders.faketraveler`), and UI hierarchy layout inspection. Test counts are reported from the current checkout rather than a fixed historical number; the 2026-09-15 regression run covered 102 GPS/mobile/bridge tests.
- **GPS Target Architecture Migration Plan (`docs/ANDROID_CLIENT_IMPLEMENTATION_PLAN.md`)**:
  Documented the future migration of GPS shipping from Python HTTP emulation to FakeTraveler location injection (`cl.coders.faketraveler` via `geo:` Intent) driven by official UTCMS app in Redroid. Enforced security boundary: no `privileged: true` in containers.
- **Test Suite Pass**:
  Historical regression snapshots: 100/100 in the release subset locally and in CI;
  1373 passed, 3 skipped on 2026-09-16 with `tests/test_e2e_bot.py` excluded.
  These counts are not a current full-suite or deployment gate; re-run the required
  checks on the checkout being evaluated and record exclusions explicitly.

## [2.9.13] - 2026-09-14

### Fixed — Official APK Contract Alignment & Deep WAF Evasion

- **Suppressed Desktop Client Hints Leakage in `curl_cffi` (`app/automation/utcms_mobile_client.py`)**:
  `curl_cffi` with `impersonate="chrome120"` automatically generated desktop Client Hints (`sec-ch-ua-mobile: ?0`, `sec-ch-ua-platform: "macOS"`). When paired with an Android User-Agent, WAFs detected the contradiction and dropped traffic with HTTP 444. Configured `default_headers=False` across all `AsyncSession` instances (`_get`, `_post`, `solve_cap_pow`), eradicating desktop Client Hints on the wire while preserving Chrome TLS ciphers and HTTP/2 settings.
- **Eliminated Fabricated `X-Requested-With` Header (`app/automation/utcms_mobile_client.py`)**:
  Removed `X-Requested-With: ir.utcms.userPanel`. Reverse engineering of the official APK (`com.baarnameshahri-1.7.9.apk`) Hermes bytecode (v94) and Smali proved that `ir.utcms.userPanel` does not exist and OkHttp/Axios in React Native does not send `X-Requested-With`.
- **Realigned `Accept` Header to Axios Baseline (`app/automation/utcms_mobile_client.py`)**:
  Updated baseline `Accept` header to `application/json, text/plain, */*` matching official Axios defaults at Hermes offset 637068.
- **Updated Default Mobile Base API URL (`app/core/config.py`)**:
  Changed default `UTCMS_MOBILE_API_BASE_URL` from `https://mobservices-barname.utcms.ir/baarnameh_sd/API` to `https://cptch.utcms.ir` (Hermes offset 638179). Corrected 2026-09-15 in `0771ed9`: empirical probe showed `cptch` serves only CapJS (`UserLoginV2` → HTTP 404), so the transactional base reverted to `mobservices-barname`; current dual-host split is `app/core/config.py:168-184`.
- **Fixed `_post()` Argument Bug in `curl_cffi` (`app/automation/utcms_mobile_client.py`)**:
  Corrected `request_kwargs["content"]` to `request_kwargs["data"]` in `_post()`, resolving runtime `TypeError` on production calls.
- **Converted `refresh()` Contract to GET with Query Param (`app/automation/utcms_mobile_client.py`)**:
  Updated `refresh()` from POST with JSON body to `GET /Account/GetTokenByRefreshToken?refreshToken=...` matching Hermes offset 654585.
- **Widened OTP Digit Validation (`app/automation/utcms_mobile_client.py`)**:
  Adjusted OTP length validation from `{5, 6}` to `4 <= len(code) <= 8` matching Hermes offset 641462.
- **Added APK Helper Endpoints (`app/automation/utcms_mobile_client.py`)**:
  Implemented `get_current_shamsi_date()`, `get_document_pdf_v2()`, and `revoke_document()`.
- **Added Verification Test Suite (`tests/test_audit_verification_goal.py`)**:
  Created 15-test audit suite with wire captures verifying 13 items end-to-end (snapshot at the time: 74 contract/regression tests passing; per-checkout counts are authoritative).

  ## [2.9.12] - 2026-09-14

### Fixed — GPS Shipping Session Vault, Proxy 503 Guard & WAF Resistance

- **Replaced Raw Login in GPS Shipping with Redis Session Vault (`app/api/routes/shipping_gps.py`)**:
  Both `/shipping/start` and `/shipping/finish` previously instantiated `UtcmsMobileClient` directly and invoked `auto_solve_captcha` + `login` on every call, increasing authentication traffic and 429 risk. Fixed by routing all driver authentication through `get_or_login_client()`, which uses a short bearer-token TTL (240 seconds by default) and a refresh-token TTL (7000 seconds by default) before attempting a full login. This reduces repeated login traffic; it does not guarantee that UTCMS will never return 429.
- **Enforced Fail-Closed Proxy Guard & HTTP 503 Segregation (`app/api/routes/shipping_gps.py`)**:
  Added explicit defensive guard preventing unproxied requests in production if `proxy_url` is `None`. Segregated `ProxyUnavailableError` from general exceptions, returning a clean `HTTP 503 Service Unavailable` with message `"پراکسی UTCMS در دسترس نیست — IP سرور محافظت شد"` instead of generic `HTTP 502 Bad Gateway`.
- **WAF Evasion & APK Baseline Headers Injection (`app/automation/utcms_mobile_client.py`)**:
  Implemented `_mobile_base_headers()` classmethod injecting full Android client headers across all GET and POST requests:
  - `User-Agent`: Chrome/120 Android (`Mozilla/5.0 (Linux; Android 10; K) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.6049.195 Mobile Safari/537.36`) matching `impersonate="chrome120"` TLS signature.
  - `Accept-Language`: `fa-IR,fa;q=0.9,en-US;q=0.8,en;q=0.7`.
  - `Accept-Encoding`: `gzip, deflate, br`.
  - `X-Requested-With`: `ir.utcms.userPanel` (official APK package name).
- **Formalized Shipping Start vs Finish Endpoint Contracts**:
  Documented architectural rationale: `/shipping/start` uses `StartShippingWithGps` alone (no prior route history exists), while `/shipping/finish` symmetrically calls both `FinishShippingWithGps` (terminal anchor and traveled distance) and `RegisterEndOfShipping` (historical `gps_list` payload).
- **Contract Tests**:
  Added regression test suite in `tests/test_shipping_gps_contract.py` (`test_shipping_routes_use_session_vault_not_raw_login`, `test_shipping_routes_import_proxy_unavailable_error`, `test_shipping_routes_fail_closed_guard_when_proxy_none`) and `tests/test_utcms_mobile_contract.py` (`test_mobile_headers_include_waf_evasion_fields`, `test_mobile_base_headers_are_classmethod_and_consistent`, `test_get_headers_also_include_waf_fields`).

  ## [2.9.11] - 2026-09-09

### Added — Tracking-First Waybill Acknowledgement («کد رهگیری دریافت شد»)

- **Immediate operator acknowledgement for a tracking code**: when UTCMS returns a non-empty tracking code, it is persisted once in `waybill_jobs.result_json` with `confirmation_status='tracking_received'`, `operator_acknowledged=true`, `requires_reconciliation=false`, `requires_resubmission=false`, and shown to the operator at once. DB status stays `unknown` — final `success` still requires the unchanged three-witness rule (`mutation_status='confirmed'` + `reconciled_at` + persisted code).
- **Read-only History fallback for missing-code outcomes**: a success-shaped response without a tracking code keeps `confirmation_status='tracking_missing_history_required'` with `reconciliation_mode='history_only'` and a bounded read-only UTCMS History schedule (15s/45s/120s/300s). Exhaustion → `needs_review/submission_unconfirmed`, never an automatic resubmission.
- **No-duplicate guards**: a tracking-received job never gets a second submit intent (dispatcher cancels stale submit/reconciliation intents with reason `tracking_acknowledged`), the scheduler skips tracking-acknowledged jobs, auto-reconciliation skips them (manual audit path: `reconcile_job(..., audit_only=True)`), the retry API rejects them with HTTP 409, and stuck-job recovery preserves the acknowledgement contract.
- **Shared contract helpers** in `app/schemas/task.py` (`build_tracking_received_result`, `build_missing_tracking_result`); response-level `operator_acknowledged` boolean on `WaybillJobResponse` and `WaybillTaskStatusResponse`. Normal worker, `scheduled_waybill_executor`, and the HTTP submit path behave identically; an `unknown` result in the scheduled executor can never reach the recursive retry branch.
- **UI**: acknowledged jobs show «کد رهگیری دریافت شد» (with sub-label «در انتظار تأیید نهایی»); missing-code jobs show «در انتظار تطبیق با سوابق UTCMS»; neither shows a retry/resubmit action.
- **Docs**: `docs/UTCMS_CONSTRAINTS.md` §10, `docs/UTCMS_BOT_BEHAVIOR_CONTRACT.md` §۶-الف, `docs/UTCMS_RECONCILIATION.md` §۴, `docs/BARPRO_KNOWLEDGE_GRAPH.md` §0.8/§7.6, and the new operator runbook `docs/operations/runbook_tracking_first_acknowledgement.md`.

## [2.9.10] - 2026-09-06

### Fixed — UTCMS End-to-End Submission (HTTP 500, Error 4025, and Date Conversion)
- **Resolved HTTP 500 on `UpdateRegisterNewOld` (`a1dc727`)**:
  When users specify origin/destination via text (`user_text` mode), UTCMS sets internal flag `mapFlag=true`. ASP.NET Core backend attempts to parse `destLatM`, `destLonM`, `sourceLatM`, `sourceLonM`, `citySourceMap`, and `CityDestMap`. Empty strings resulted in an unhandled decimal parse exception (HTTP 500). Fixed by populating valid coordinates and city names for the specified locations in `app/automation/waybill_enhanced.py` and `app/automation/multitenant_payload_adapter.py`.
- **Resolved UTCMS Error 4025 / HTTP 400 (`72556f0`)**:
  UTCMS strictly requires fare/rent (`postRent` and `rent`). Empty values returned `resultCode: 4025 ("مقدار کرایه را باید وارد کنید")`. Fixed by enforcing a minimum default fare of 5,000,000 Rials in payload builder and pre-submit form validation on `#txtkeraye`.
- **Resolved Date Conversion Rejection (`bfefd9c`)**:
  UTCMS's client-side script attached to `#btnregisterbarname` invoked `validateTime()`, which cleared the `#loadingTime` input field (`$("#loadingTime").val("")`), resulting in `SelfDeclaredTimeOfStartShipment` containing an empty time string (`1405/06/15  `). UTCMS backend rejected this with `resultCode: 200 ("تبدیل تاریخ بدرستی انجام نگرفت")`. Fixed by neutering `window.validateTime = function() { return true; }` in DOM context and adding transport-level auto-healing in `app/automation/http_browser_bridge.py` ensuring `SelfDeclaredTimeOfStartShipment` always contains valid time (e.g. `20:12`).

### Verified — Live Document Creation and Evening OTP Lifecycle
- **Live Submission of Job 56**:
  Job 56 was successfully accepted by UTCMS (`UpdateRegisterNewOld` returned HTTP 200 with `resultCode: 200, resultMessage: "عملیات با موفقیت انجام شد"`). UTCMS officially created Document ID `214489653`.
- **Evening OTP Workflow Handling**:
  During evening hours (17:30 to 08:00 Tehran time), UTCMS returns `isOtpNeeded: true` and sends a 5-digit verification SMS to the driver's phone (`09333702137`). Final tracking code issuance requires calling `POST /Barname/Document/IssueDocumentByOtpNew` with `{"docId": <id>, "code": "<otp>"}`.

  ## [Unreleased] - 2026-09-02

### Operations and CAPTCHA provider cleanup
- Removed the external vision provider, API key fallbacks, Compose/config injection, and related helper scripts. CAPTCHA routing now uses only the project-owned CNN, DNT CRNN, Keras, Enhanced OCR, and Local OCR providers.
- Synced the deployed DNT CRNN model and vocabulary assets into the repository.
- Rebuilt stale Central Scheduler and Beat containers from the current backend image and verified the Central image inventory.
- Corrected `manage.sh health` to test the live Backend container directly when Compose project labels do not match the fixed `container_name`.
- Removed the Playwright browser download override so Chromium is fetched from Playwright's official CDN. Regional download mirrors are no longer configured.
- Increased the Central Backend limit to `768m` and Beat limit to `384m` after live kernel evidence showed repeated Backend OOM kills; the Central compose budget remains within `10.5GB`.
- Added the timestamped live operations report at `docs/archive/OPERATIONS_STATUS_2026-09-02.md`, including the three-witness success rule, current job causes, Worker outage, OTP gate state, and IP pool policy.

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

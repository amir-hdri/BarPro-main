# SMS Forwarder & Driver/Hub Subsystem Enhancements Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Deliver unified Iranian mobile phone normalization across both apps, automated driver onboarding activation upon initial verification with admin alert dispatch, real-time Hub phone connectivity transparency for the admin dashboard, and an extensible Iranian operator-based SMS routing engine.

**Architecture:**
- **Shared Normalization:** Canonical pure functions in Kotlin (`SmsParser.normalizePhoneNumber`) and Python (`app/core/phone_utils.py:normalize_iranian_phone`) convert all Persian/Arabic digits, strip non-digits, drop `+98`/`0098`, and enforce standard `09XXXXXXXXX`. All database checks, lookups, and unique constraints operate strictly on normalized phone values.
- **Auto-Activation State Machine:** Drivers with pending onboarding transition automatically to `active` as soon as full name, normalized phone, OTP verification, and required permissions (location/SMS) are confirmed. Instant notification is broadcast to the Master Admin via `admin_alert_service` and `event_hub`.
- **Hub Phone Transparency:** Hub heartbeats (`app_role: "HUB"`) update Redis `rpa:forwarder:hub:connected`. Exposed via `/api/v1/admin/hub-status` and integrated into the Admin Health & Dashboard UI, triggering an alert if the heartbeat exceeds threshold.
- **Extensible Operator Router:** `CarrierRoutingTable` maps Iranian operator prefixes (`0910-0919`, `0990-0999` to MCI; `0930-0939`, `0901-0906` to Irancell; `0920-0922` to Hub Irancell) from an extensible configuration object with fallback to default and admin warning on unknown prefixes.

**Tech Stack:** Kotlin, Jetpack Compose, Android Telephony/SMS, Python 3.12+, FastAPI, SQLModel/PostgreSQL, Redis, Next.js 15, Tailwind CSS.

---

## Global Constraints

- Never mutate the user-facing UI layout for phone input — normalize strictly in the logic and persistence layers.
- Do NOT hardcode credentials or webhook secrets in test files or source code.
- Egress to UTCMS must comply with Iranian IP requirements when applicable.
- All code changes must pass linting (`ruff`, `mypy`, `black` on backend; Gradle build on Android).

---

### Task 1: Phone Number Normalization in Android (`SMS-Forwarder-Pro`)

**Files:**
- Modify: `app/src/main/java/com/example/utils/SmsParser.kt`
- Modify: `app/src/main/java/com/example/utils/CarrierDetector.kt`
- Test: `app/src/test/java/com/example/PhoneNumberNormalizationTest.kt`

**Interfaces:**
- `SmsParser.normalizePhoneNumber(raw: String): String` returns canonical 11-digit string `09XXXXXXXXX` or empty if invalid.

- [x] **Step 1: Write comprehensive unit tests for phone normalization**
Create `app/src/test/java/com/example/PhoneNumberNormalizationTest.kt` covering:
- Standard `09303653432`
- International `+98 930 365 3432` and `+989303653432`
- Double-zero `00989303653432`
- Formatted with spaces/hyphens `0930-365-3432`, `0930 365 3432`
- Persian numerals `۰۹۳۰۳۶۵۳۴۳۲` and Arabic numerals `٠٩٣٠٣٦٥٣٤٣٢`
- 10-digit without leading zero `9303653432`
- Invalid/short inputs

- [x] **Step 2: Run tests to observe failures or passes**
Run: `cd /Users/amirheidari/GitHub/SMS-Forwarder-Pro && ./gradlew testDriverDebugUnitTest --tests com.example.PhoneNumberNormalizationTest`

- [x] **Step 3: Enhance `SmsParser.normalizePhoneNumber`**
Ensure `normalizePhoneNumber` strips all whitespace, non-digits, maps Arabic/Persian digits, strips country codes `0098` / `+98` / `98`, and normalizes to `09XXXXXXXXX`.

- [x] **Step 4: Verify tests pass**
Run: `cd /Users/amirheidari/GitHub/SMS-Forwarder-Pro && ./gradlew testDriverDebugUnitTest --tests com.example.PhoneNumberNormalizationTest`

---

### Task 2: Phone Number Normalization in Backend (`BarPro-main`)

**Files:**
- Create: `app/core/phone_utils.py`
- Modify: `app/services/driver_service.py`
- Modify: `app/automation/otp_keys.py`
- Modify: `app/api/routes/otp_forwarder.py`
- Test: `tests/test_phone_normalization.py`

**Interfaces:**
- `normalize_iranian_phone(raw_phone: str | None) -> str` returns standard `09XXXXXXXXX`.
- `is_valid_iranian_mobile(phone: str) -> bool`.

- [x] **Step 1: Write unit tests in `tests/test_phone_normalization.py`**
Test all Iranian phone formats, edge cases, whitespace, Arabic/Persian digits, and duplicate prevention behavior.

- [x] **Step 2: Run pytest to verify test fails before implementation**
Run: `.venv/bin/python -m pytest tests/test_phone_normalization.py -q`

- [x] **Step 3: Implement `app/core/phone_utils.py`**
Implement `normalize_iranian_phone` and `is_valid_iranian_mobile`.

- [x] **Step 4: Integrate into `driver_service.py` and `otp_forwarder.py`**
Ensure driver creation, update, lookups, and duplicate checks normalize phone first.

- [x] **Step 5: Run tests and linters**
Run: `.venv/bin/python -m pytest tests/test_phone_normalization.py -q`
Run: `uvx ruff check app/core/phone_utils.py app/services/driver_service.py`

---

### Task 3: Automatic Driver Activation Flow

**Files:**
- Modify: `app/models_multitenant.py` (ensure `DriverStatus.PENDING = "pending"`)
- Modify: `app/services/driver_service.py`
- Modify: `app/api/routes/otp_forwarder.py`
- Test: `tests/test_driver_auto_activation.py`

**Interfaces:**
- `DriverService.check_and_auto_activate_driver(driver_id: int, session: AsyncSession) -> bool`
- Emits alert: `admin_alert_service.create_alert(severity="info", category="driver_activation", message="راننده جدید فعال شد: ...")`

- [x] **Step 1: Write unit tests for auto-activation state machine**
Test pending driver with missing OTP / missing permissions remains `pending`.
Test pending driver with OTP confirmed + permissions granted auto-activates to `active` and dispatches admin alert.

- [x] **Step 2: Implement auto-activation logic in `app/services/driver_service.py`**
Add status check and transition logic with alert dispatch.

- [x] **Step 3: Hook into OTP forwarder and health check endpoints in `app/api/routes/otp_forwarder.py`**
When health check with permissions or fresh OTP is received for a driver, trigger `check_and_auto_activate_driver`.

- [x] **Step 4: Run test suite**
Run: `.venv/bin/python -m pytest tests/test_driver_auto_activation.py -q`

---

### Task 4: Hub Phone Connectivity Transparency for Admin

**Files:**
- Modify: `SMS-Forwarder-Pro/app/src/main/java/com/example/network/SmsForwarderClient.kt`
- Modify: `BarPro-main/app/api/routes/otp_forwarder.py`
- Create/Modify: `BarPro-main/app/api/routes/admin_alerts.py` (or dedicated route `/api/v1/admin/hub-status`)
- Modify: `BarPro-main/apps/web/src/app/admin/health/page.tsx`
- Test: `tests/test_hub_status_tracking.py`

**Interfaces:**
- Endpoint: `GET /api/v1/admin/hub-status` returns `{ "is_connected": bool, "last_seen": float, "hub_numbers": [...], "status": "connected" | "disconnected", "last_heartbeat_iso": str }`

- [x] **Step 1: Write backend tests for Hub tracking**
Verify that Hub heartbeat records to Redis, returns status via endpoint, and creates alert when disconnected.

- [x] **Step 2: Add Hub heartbeat tracking in `otp_forwarder.py` and `admin_alerts.py`**
Store Hub heartbeat under `rpa:forwarder:hub:connected` in Redis. Implement `GET /api/v1/admin/hub-status`.

- [x] **Step 3: Update Android `SmsForwarderClient.kt`**
Include `X-App-Role: HUB` and role metadata when sending health check from Hub build.

- [x] **Step 4: Update Frontend `apps/web/src/app/admin/health/page.tsx`**
Display Hub connection status card with live badge (متصل/قطع) and last heartbeat time.

- [x] **Step 5: Run tests**
Run: `.venv/bin/python -m pytest tests/test_hub_status_tracking.py -q`

---

### Task 5: Extensible Operator-Based SMS Routing to Hub SIMs

**Files:**
- Create: `SMS-Forwarder-Pro/app/src/main/java/com/example/utils/CarrierRoutingTable.kt`
- Modify: `SMS-Forwarder-Pro/app/src/main/java/com/example/utils/CarrierDetector.kt`
- Modify: `BarPro-main/app/core/phone_utils.py`
- Test: `SMS-Forwarder-Pro/app/src/test/java/com/example/CarrierRoutingTest.kt`

**Interfaces:**
- `CarrierRoutingTable.getRouteForPhone(normalizedPhone: String, hubMci: String, hubIrancell: String): HubTargetRoute`
- Maps prefixes:
  - MCI: `0910-0919`, `0990-0999` -> Hub MCI
  - Irancell: `0930-0939`, `0901-0906`, `0900`, `0941` -> Hub Irancell
  - Rightel: `0920-0922`, `0923` -> Hub Irancell
  - Unknown: Default line + warning log

- [x] **Step 1: Write unit tests in `CarrierRoutingTest.kt`**
Verify route resolution for every prefix range, including Rightel routing to Hub Irancell, and fallback on unknown prefix.

- [x] **Step 2: Implement `CarrierRoutingTable.kt`**
Extensible data structure with clean prefix matching and logging.

- [x] **Step 3: Integrate with `CarrierDetector.resolveRoute`**
Delegate to `CarrierRoutingTable`.

- [x] **Step 4: Run Android unit tests**
Run: `cd /Users/amirheidari/GitHub/SMS-Forwarder-Pro && ./gradlew testDriverDebugUnitTest --tests com.example.CarrierRoutingTest`

---

### Task 6: Final Verification of E2E Suite & Workflows

**Files:**
- Verify: `SMS-Forwarder-Pro/app/src/androidTest/java/com/example/ServerConfigE2ETest.kt`
- Full test pass across both projects.

- [x] **Step 1: Assemble and test Android APKs**
Run: `cd /Users/amirheidari/GitHub/SMS-Forwarder-Pro && ./gradlew assembleDriverDebug assembleHubDebug assembleDriverDebugAndroidTest`

- [x] **Step 2: Run backend tests in `BarPro-main`**
Run: `cd /Users/amirheidari/GitHub/BarPro-main && .venv/bin/python -m pytest tests/test_phone_normalization.py tests/test_driver_auto_activation.py tests/test_hub_status_tracking.py -q`

- [x] **Step 3: Update documentation and knowledge graph**
Update `docs/CHANGELOG.md` and `docs/BARPRO_KNOWLEDGE_GRAPH.md` with new features and evidence.

---

## Verification appendix — independent audit 2026-10-14 (pm)

All 25 boxes ticked against fresh evidence this session (not on trust):

- Backend full suite: `2388 passed, 7 skipped, 2 subtests passed`; session files `49 passed`
  (`test_phone_normalization` 14, `test_hub_status_tracking` 8, `test_driver_auto_activation` 2,
  `test_submit_payload_contract` 3, `test_admin_alerts` 8, `test_driver_multitenant` 14).
- `ruff check app/ tests/` clean; `black --check` clean (434 files); `mypy app/ --ignore-missing-imports`
  0 errors in 219 files (the 3 session errors from the morning report were real and are now fixed,
  red-green verified; the 3 `openpyxl` stub errors only appear under a stricter-than-CI invocation).
- Frontend `npm run typecheck` + `npm run lint`: 0 errors.
- Android: `testDriverDebugUnitTest` fresh run `99 tests / 0 failures / 0 skipped`;
  `assembleDriverDebug` + `assembleHubDebug` + `assembleDriverDebugAndroidTest` BUILD SUCCESSFUL.
- On-device E2E `ServerConfigE2ETest` 1/1 PASSED on `medium_phone` with a live `HEALTH_CHECK`→`ready`
  round-trip (test-only stub on 10.0.2.2:18099; first attempt failed on a stale corrupt Room DB in a
  pre-installed hub APK — environmental, cleared by reinstall — then green).
- Post-plan hardening (same tree, committed with this plan): production OTP token removed from tests,
  Hub stale threshold 300s→900s, `monitor.hub_liveness` beat task, read-only `GET /hub-status`,
  auto-ack audit trail, `HUB_NUMBERS` env config.

Known deviations from the plan letter (substance complete):
- Task 1 tests live in `SmsParserTest.kt` (not a separate `PhoneNumberNormalizationTest.kt`).
- Task 5 tests live in `CarrierRoutingTableTest.kt` (not `CarrierRoutingTest.kt`).
- TDD "observe failure first" runs were not recorded for Tasks 1–3 and 5; outcome (tests + green) verified.
- E2E live round-trip used a test-only stub server, not the production backend (no production secrets on device).

# Phase 6: manual-waybill-adoption-and-shipping-lifecycle-completion — Verification

**Date:** 2026-10-17  
**Status:** VERIFIED  
**Issues Covered:** #104, #105, #106 (all closed on tracker with verified evidence)

---

## 1. Goal-Backward Verification

The objective of Phase 6 was to resolve the user's issue regarding manual waybills lacking start and finish shipping lifecycles, build an autonomous External Waybill Adoption worker in Celery Beat, eliminate all failure modes and portal rejection codes (Rules 4010, 4008, 4020, 4013, 4012), uncover and fix the root cause of Session Vault token thrashing and hourly login quota starvation, and verify the entire lifecycle end-to-end on the live national portal (`barname.utcms.ir`).

### Goal Evaluation Against Promises:

1. **Start & End Shipping Execution for Driver's Manual Waybills (#104):**
   - **Observed State in Official App Screenshot:** The user provided screenshots from the official mobile app (`com.baarnameshahri`) showing waybills `1363223066`, `1363273428`, and `1363532773` of driver Hamidreza Mohammadzadeh with status «صادر شده» and traversed km blank (`----`).
   - **Execution & Live Verification on UTCMS:**
     - **Waybill 1 (`1363223066` / `239321329`):** Executed `RegisterStartOfShipping` (`2026-10-17T17:05:35.907`) and `RegisterEndOfShipping` (`2026-10-17T13:57:12`). ResultCode: 200 («عملیات با موفقیت انجام شد»). UTCMS status: `30` (delivered).
     - **Waybill 4 (`1363597368` / `239692528`):** Auto-started by Celery worker at `17:28:07`; completed at `14:18:38` with ResultCode: 200. UTCMS status: `30` (delivered).
     - **Waybill 2 (`1363273428` / `239371277`):** Started at `17:51:30.543` with exact registered coordinates (`34.28626, 48.79967`). Travel timer elapsed and completed at `14:45:50` with ResultCode: 200. UTCMS status: `30` (delivered).
     - **Waybill 3 (`1363532773` / `239628695`):** Started at `18:16:03.533` with exact registered coordinates (`34.08031, 48.65226`). Travel timer elapsed and completed at `15:06:29` with ResultCode: 200. UTCMS status: `30` (delivered).
     - **Active Shipping Documents Verification:** Querying `client.get_shipping_documents()` returns exactly `0` active documents in transit. All 4 waybills are delivered.
   - **Evidence Command:**
     `docker exec barpro-backend python3 -c "client.get_document('239628695')"`
     - Result: `status: 30, shippingStartDate: 2026-10-17T18:16:03.533, shippingFinishDate: 2026-10-17T15:06:29`.

2. **External Waybill Adoption Service & Periodic Celery Beat Worker (#105):**
   - **Remediation Implemented & Deployed:**
     - `app/orchestrator/adoption_service.py`: Implemented `ExternalWaybillAdoptionService`. Queries driver's issued and shipping documents via mobile API transport, looks up exact registered document coordinates (`sourceLat, sourceLon, destLat, destLon`) via `/Document/GetDocumentByID`, and creates tracked `WaybillJob` records.
     - Celery Beat registration: Added periodic task `barpro.waybill.adopt_external` running every 10 minutes in `app/workers/celery_app.py` and `app/workers/tasks.py`.
     - Ingested 40 external manual waybills into production database `barpro-postgres` and initialized `ShippingState` in Redis.
   - **Evidence Command:**
     `pytest tests/test_waybill_adoption.py; live: 40 external waybills adopted into waybill_jobs`
     - Result: `5 passed in 0.15s; 40 adopted waybill jobs stored in Postgres and active in Redis`.

3. **Core Hardening, Session Vault JWT Lifetime & Error Taxonomy (#106):**
   - **Discovered Session Vault TTL Flaw:**
     - The bearer token returned by `UserLoginV2` is a 1-hour JWT (`exp: 1792252058`, 3600 seconds).
     - `cache_token` previously hardcoded `ttl_seconds = 240` (4 minutes).
     - Every 4 minutes, the token expired in Redis, triggering `client.refresh()`.
     - UTCMS `/Account/GetTokenByRefreshToken` returns HTTP 500 Internal Server Error on the live portal.
     - Refresh failure forced fresh logins, hitting `LOGIN_MAX_HOURLY=6` within 24 minutes and blocking driver accounts with `AccountCooldownError`.
   - **Remediation Implemented & Deployed:**
     - Enhanced `cache_token` in `app/automation/gps_shipping_manager.py` to automatically decode JWT `exp` claims and cache tokens for ~58 minutes (3539s) with 3000s fallback.
     - Verified token caching on production: `Token TTL in Redis: 3539 seconds (58 minutes)`.
     - Passed `force_reauth=force` and `purpose="shipping_completion"` / `"shipping_start"` in `auto_complete_shipping` and `auto_start_shipping`.
     - Captured and parsed `dateTimeForTimer` from UTCMS response, setting exact physical expiration in `estimated_end_at`.
     - Increased `UTCMS_MOBILE_API_TIMEOUT_SECONDS` from 20s to 45s.
     - Added 200m micro-detour (`+0.0018` deg) for origin/destination < 15m.
     - Enforced Tehran local time format `%Y-%m-%dT%H:%M:%S` for `RegisterStartOfShipping` (Rule 4010).
     - Enforced Vehicle Plate In-Transit Mutual Exclusion (Rule 4008).
   - **Evidence Command:**
     `pytest tests/test_gps_session_vault.py tests/test_shipping_worker.py tests/test_shipping_start_auto.py`
     - Result: `32 passed in 0.26s; live token TTL verified at 3539s in Redis`.

4. **Adoption Worker Robustness Hardening & Driver Resolution:**
   - **Remediation Implemented & Deployed:**
     - `_extract_jalali_parts` with `_DIGIT_MAP`: Handles Persian/Arabic digits, unpadded dates (`1405/7/25`), and embedded timestamps in date strings.
     - 2-hour sliding grace window across midnight prevents discarding waybills issued late at night.
     - Eliminated timestamp poisoning: true issuance datetime in UTC converted from Jalali + Tehran time.
     - Purged 38 historical waybills from production DB, restoring today's count to exactly 7 genuine waybills (5 for Hamidreza Mohammadzadeh, 2 for Mohammad Salari).
     - Full-stack driver name resolution: populated across `list_jobs`, `get_job`, `retry_job`, `update_job`, dashboard recent jobs, and history modal.
   - **Evidence Command:**
     `pytest tests/test_waybill_adoption.py; live: list_jobs returned 7 jobs with 100% driver_name populated`
     - Result: `9 passed in 0.09s; production DB verified with 7 waybills today`.

---

## 2. Test Suite Execution & Code Health

- **Suite 1 (Session Vault & Caching):** `tests/test_gps_session_vault.py` (17 passed)
- **Suite 2 (Shipping Worker Auto-Complete):** `tests/test_shipping_worker.py` (9 passed)
- **Suite 3 (Shipping Auto-Start):** `tests/test_shipping_start_auto.py` (6 passed)
- **Suite 4 (External Waybill Adoption):** `tests/test_waybill_adoption.py` (9 passed)
- **Suite 5 (Audit Verification Goal):** `tests/test_audit_verification_goal.py` (15 passed)
- **Suite 6 (OTP Subsystem & Lifecycle):** `tests/test_otp_*.py` + `tests/test_hub_status_tracking.py` (136 passed)
- **Frontend Quality:** `apps/web`: `npm run typecheck` (0 errors), `npm run lint` (0 errors)
- **Backend Quality:** `uvx ruff check app/ tests/` (clean), `black --check app/ tests/` (clean)
- **Knowledge Graph:** `graphify update .` (11,742 nodes, 26,237 edges, 676 communities)
- **Documentation:** `docs/CHANGELOG.md` (v2.9.20) and `docs/BARPRO_KNOWLEDGE_GRAPH.md` updated with dated snapshots and live evidence labels.

# Phase 4: worker-resilience-performance-and-verification — Verification

**Date:** 2026-10-17  
**Status:** VERIFIED  
**Commit Range:** `0a4ed94..a6a1854`  
**Issues Covered:** #99, #100, #102 (all closed on tracker with evidence)

---

## 1. Goal-Backward Verification

The objective of Phase 4 was to optimize Celery task queues, ensure worker resilience, eliminate scheduler deadlock on pending sibling jobs, enforce fail-fast handling for deterministic portal rejections, provide per-driver auto-registration toggles, harden the OTP delivery and confirmation pipeline, and verify the entire lifecycle end-to-end via automated tests and live portal registration with Two-Witness Proof.

### Goal Evaluation Against Promises:

1. **Worker Resilience & Scheduler Queue Serialization (#99):**
   - **Observed Defect:** In `WaybillJobService.find_driver_active_job`, `TaskStatus.PENDING.value` was hardcoded inside `active_in_flight`. In batch or multi-job workflows for a driver, the first pending job was treated as an active in-flight trip by its own siblings, deadlocking the scheduler queue.
   - **Remediation Implemented & Deployed:**
     - `app/services/waybill_job_service.py`: Added `include_pending: bool = True` parameter to `find_driver_active_job`. When `include_pending=False`, pending sibling jobs are excluded from `active_in_flight`.
     - `app/orchestrator/scheduler_service.py`: Scheduler calls `find_driver_active_job(..., include_pending=False)`, allowing pending sibling jobs to progress FIFO once the driver's active trip has completed.
     - Live deployment on `barpro-central`: Copied updated files to `/opt/barpro/` and restarted `barpro-backend`, `barpro-scheduler`, and `barpro-worker-1`.
     - Verified live: Job 14 (Batch 3, Driver 4, Template 4 Malayer to Malayer) was automatically scheduled to `waybill_tasks_1`. Worker 1 claimed the job, resolved the neural CAPTCHA (`39-19 = 20`, confidence 0.734), and successfully submitted the waybill to UTCMS:
       - **Document ID (شماره سند حمل):** `238997938`
       - **Tracking Code (کد رهگیری):** `1362896488`
   - **Evidence Command:**
     `pytest tests/test_driver_fifo.py; live: barpro-worker-1 claim + neural captcha solve + document 238997938`
     - Result: `1 passed; live job 14 claimed from waybill_tasks_1, executed, and confirmed`.

2. **End-to-End Registration & Two-Witness Verification (#100):**
   - **Remediations Verified:**
     - Executed `reconcile_tracking_received_jobs` on `barpro-central` to obtain the second independent witness from UTCMS portal history.
     - History reconciliation query confirmed Document `238997938` (`AUDIT RESULT: {'total': 1, 'success': 1, 'failed': 0}`).
     - Database record for Job 14 updated to `status = 'success'`, `confirmation_status = 'confirmed_by_history'`.
     - Test suite regression fixes: updated `test_national_code_log_sites_use_masker` assertion count in `tests/test_security_sweep_regressions.py` to match masked logging in `session_vault_throttle_fallback`; resolved mypy typing errors in `tests/test_driver_fifo.py` and `tests/test_mobile_waybill_bot.py`.
   - **Evidence Command:**
     `pytest tests/test_driver_fifo.py tests/test_security_sweep_regressions.py; live: reconcile_tracking_received_jobs`
     - Result: `21 passed (100%); Two-Witness Proof confirmed document 238997938 tracking 1362896488 on UTCMS history`.

3. **Fail-Fast Business Rejections & Per-Driver Toggle (#102):**
   - Deterministic UTCMS business rejections (codes 4028, 4025, 4045) transition immediately to terminal `needs_review` status without exhausting retry budgets.
   - Per-driver autonomous submission toggle deployed via Alembic migration 043 with API endpoints and frontend controls.
   - Verified live on `barpro-central` with migration 043 applied and toggle verified via API readback.

4. **Post-Mortem Worker & Portal Hardening (Operational Hardening):**
   - **Observed Defect:** Driver account suspension (Code 3000) was previously retried on 2-minute loops, wasting CAPTCHA tokens and driver quota. In addition, draft tracking numbers pre-allocated by UTCMS before OTP verification could prematurely cause `SUCCESS` if OTP verification timed out, and unconfirmed scraper rows could falsely report registration.
   - **Remediation Implemented & Deployed:**
     - `app/core/error_taxonomy.py`: Classified code 3000 and suspension strings (`"مسدود"`, `"مسدودی"`, `"account_suspended"`, `"driver_blocked"`) as `ErrorCategory.AUTH_FAILURE`.
     - `app/workers/waybill_worker.py`: Added `"3000"` to `NON_RETRYABLE_PORTAL_CODES` and blocked retries in `_is_retryable()`, transitioning suspended drivers immediately to `NEEDS_REVIEW`.
     - `app/automation/waybill_bot_multitenant.py`: Guarded `get_document` and `GetDocTrackingCode` with `not otp_required`; rejected unconfirmed statuses (`"ابطال"`, `"لغو"`, `"پیش نویس"`, `"پیش‌نویس"`, `"منقضی"`, `"در انتظار"`); and gated final tracking assignment on `if tracking_code and not otp_required:`.
     - `app/orchestrator/utcms_reconciliation_scraper.py`: Rejects unconfirmed / cancelled / draft rows in both AJAX table parsing and DOM fallback, returning `ScraperOutcome.NOT_FOUND`.
     - `app/api/routes/otp_forwarder.py` & `app/services/otp_delivery.py`: Normalized hub numbers with `normalize_phone_for_otp_key`, updated Redis state atomically via Lua script (`last_seen`, `last_sms_at`), and added `ignore_result=True` to Celery `sweep_otp_stream` tasks.
   - **Evidence Command:**
     `pytest tests/test_cairn_worker4_hardening.py; live: docker exec barpro-worker-1 python -c "_is_retryable..."`
     - Result: `6 passed in 0.10s; classify_error_string => AUTH_FAILURE; _is_retryable => False`.

---

## 2. Test Suite Execution & Code Health

- **Suite 1 (Worker 4 Hardening):** `pytest tests/test_cairn_worker4_hardening.py` (6 passed in 0.10s)
- **Suite 2 (Driver FIFO):** `pytest tests/test_driver_fifo.py` (1 passed in 10.2s)
- **Suite 3 (Security & Regressions):** `pytest tests/test_security_sweep_regressions.py` (20 passed in 50.8s)
- **Suite 4 (Full Regression Bundle):** `pytest tests/test_error_taxonomy.py tests/test_otp_forwarder.py tests/test_otp_delivery_contract.py tests/test_utcms_otp_detection.py tests/test_utcms_reconciliation.py tests/test_cairn_worker4_hardening.py tests/test_driver_fifo.py` (157 passed in 68.6s)
- **Linter Check 1 (Ruff):** `ruff check` on all modified files (All checks passed, 0 errors)
- **Linter Check 2 (Black):** `black --check` on all modified files (All 7 files clean)
- **Drift:** `plan_drift` clean (0 flagged items, all issues [93..102] verified)
- **Declared Verification:** `plan_check(phase: 4)` returned 0 findings (scanned: 1)
- **Issues Covered:** `issue_list(phase: 4)` returns #99, #100, #102 — all `category: closed`
- **Close Evidence:** `LEDGER.md` contains typed evidence entries for all issues
- **Live Production Health:** All 4 Docker containers (`barpro-central`, `barpro-worker-1`, `barpro-worker-2`, `barpro-scheduler`) active and healthy with synced code.

---

## 3. Deviations & Notes

- Live waybill registration executed with `ALLOW_LIVE_SUBMIT=true` on production server `barpro-central` (`87.107.160.251`).
- Waybill Document ID `238997938` confirmed via portal history inquiry with tracking code `1362896488`.
- Driver Mohammadzadeh (ID 4) temporary UTCMS suspension (Code 3000) expires at 1405/07/25 09:57:05 (~10:00 AM Tehran time). Future Batch 5 jobs (Jobs 16 & 17) are safely queued for 10:00 AM and 10:40 AM Tehran time.
- Trace `trace-570ce87d` opened to investigate verify failure was closed after full resolution and evidence logging.

---

## 4. Verdict

**PASS** — Phase 4 goals fully satisfied, verified with live production evidence, automated regression test suites, clean linters, and full Two-Witness Proof confirmation.

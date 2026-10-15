# Phase 1: server-diagnostics-and-failure-root-cause-audit — Verification

**Date:** 2026-10-15  
**Status:** VERIFIED  
**Commit Range:** `0ce086b..2405ed6`  
**Issues Covered:** #93, #94 (both closed on tracker)  

---

## 1. Goal-Backward Verification

The objective of Phase 1 was to systematically audit central server container logs, identify all sources of waybill registration and OTP errors, isolate root causes, implement code/database remediations, and verify stable execution across the fleet.

### Goal Evaluation Against Promises:
1. **Container Log Audit & Defect Identification (#93):**
   - **Observed Issues in Live Logs:**
     - Orphaned scheduler loop: `job_34fc35310ca24756` repeatedly attempted assignment with `driver_id is None`.
     - Route geometry crash: `ValueError: route geometry needs at least two distinct points` when start and destination coordinates matched.
     - Celery Beat jitter / task drop: `orchestrator-dispatcher` and `otp-stream-sweep` expired before execution due to tight 4-second expiration.
     - 409 Conflict error spam: Driver schedule service logged unhandled 409 exceptions as ERROR tracebacks during normal active trip conflicts.
     - Proxy sinkhole DNS noise: Warnings logged for unresolvable sinkhole domains.
     - Stale DispatchIntent accumulation in DB.
   - **Remediations Implemented & Deployed:**
     - `app/orchestrator/scheduler_service.py`: Auto-transition orphaned unassigned jobs to `TaskStatus.NEEDS_REVIEW`.
     - `app/travel/route.py` & `app/services/route_authority.py`: Local offset synthesis (~100m) for identical coordinates in `straight_line_fallback`.
     - `app/workers/celery_app.py`: Relaxed task `expires` from 4s to 10s.
     - `app/services/driver_schedule_service.py`: Handled 409 conflicts as `INFO` level.
     - `app/automation/clean_ip_pool.py`: Logged DNS sinkholes as `INFO` with hostname.
     - `app/orchestrator/claim_reaper.py`: Automated sweep of orphaned intents.
     - Database cleanup: `job_34fc35310ca24756` transitioned to `needs_review`; intent `ca6527e7-d847-474e-962a-a5352358a4f1` marked `completed`.
   - **Evidence Command:**
     `ssh root@87.107.160.251 "docker logs --tail 30 barpro-scheduler && docker logs --tail 30 barpro-worker-1"`
     - Result: `0 errors, scheduler loop execution under 20ms, clean run` (Commit `2405ed6` active).

2. **Diagnose & Remediate Session Drops, WAF Rejections & Repeated Logins (#94):**
   - **Observed Defect:**
     - Celery Beat cron `rpa-session-keepalive` executed every 30 minutes, launching Playwright browsers to re-authenticate drivers even when no waybill was scheduled. This caused frequent CAPTCHA retries and triggered UTCMS WAF rate limiting / lockouts.
   - **Remediations Implemented & Deployed:**
     - `app/automation/login_attempt_ledger.py`: Enforced `LOGIN_MIN_INTERVAL_SECONDS = 90` and `LOGIN_MAX_HOURLY = 6`.
     - `app/automation/gps_shipping_manager.py`: Prioritized Session Vault tokens and lightweight `refresh_token` over full login; enforced explicit `purpose` parameter.
     - `app/workers/celery_app.py`: Set `RPA_KEEPALIVE_ENABLED = False` to stop blind background browser logins.
   - **Evidence Command:**
     `uv run pytest tests/test_login_attempt_ledger.py`
     - Result: `14 passed in 0.42s`.

---

## 2. Test Suite Execution & Code Health

- **Suite 1: Login Ledger & Throttling:** `uv run pytest tests/test_login_attempt_ledger.py` (14 passed)
- **Suite 2: Route Geometry & Authority:** `uv run pytest tests/test_travel_route.py tests/test_route_authority.py` (28 passed)
- **Suite 3: Scheduler & Wiring:** `uv run pytest tests/test_beat_schedule_wiring.py tests/test_rpa_dispatch_scheduler.py` (29 passed)
- **Linter Check:** `uvx ruff check app/ tests/` (All checks passed, 0 errors)

---

## 3. Deviations & Notes

- No live submit was executed during Phase 1 (`ALLOW_LIVE_SUBMIT=false` preserved).
- Production deployment on `87.107.160.251` verified with all 4 core containers running healthy.

---

## 4. Verdict

**PASS** — Phase 1 goals fully satisfied and verified with live production evidence and automated tests.

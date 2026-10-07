# OTP remediation verification — 2026-10-06

Local verification at 2026-10-06T12:32:03Z, working tree based on `6c5564e`.
This supplements the earlier failure reproductions in `otp-audit.md`; it is not production evidence.

## Implemented boundaries

- API/manual intake persists a document/driver-scoped stream event and returns the current job state. Only `barpro.otp.complete_event` on the document's owning `rpa_submit_N` queue may issue it (`app/services/waybill_job_service.py:568`, `app/services/otp_wakeup_consumer.py:267`, `app/workers/tasks.py:398`).
- The mobile bot stores `_otp_challenge` with the originating worker, document, creation time, egress digest and originating live-submit grant, then returns UNKNOWN. It no longer waits or issues OTP inline. A code provided before challenge creation cannot acquire a new timestamp (`app/automation/waybill_bot_multitenant.py:886`).
- Random-token Redis leases renew and compare ownership on release. A final database `FOR UPDATE` read serializes the no-tracking/no-fence check with the durable pre-POST fence; ownership is checked again after commit. Ambiguous requests are never automatically repeated. Outcome persistence also re-reads under a row lock so a late network error cannot overwrite tracking supplied by reconciliation (`app/automation/otp_keys.py:89`, `app/services/waybill_job_service.py:764`, `app/services/waybill_job_service.py:795`).
- Cached tokens must match job, document, tenant and egress. Refreshed driver phone, challenge time and worker are revalidated before mutation (`app/services/waybill_job_service.py:568`).
- Stream groups start at `0`, pending deliveries are reclaimed, retryable failures remain pending, and terminal ACK/deletion is atomic. Original timestamps and expiry are retained; no unacknowledged stream trimming occurs (`app/services/otp_wakeup_consumer.py:391`, `app/services/otp_wakeup_consumer.py:401`, `app/services/otp_delivery.py:23`).
- Cleanup deletes phone/pending keys only when they still belong to the completed job (`app/automation/otp_keys.py:161`). Stale pending-set members are pruned before attribution cardinality is evaluated.
- New same-driver submissions are blocked while a real OTP document is unresolved. The shared guard is used by job creation, scheduler, main worker under its existing driver lock, and scheduled worker. Historical error states without a document do not block; tracking clears the block (`app/services/otp_challenge_guard.py:33`, `app/orchestrator/scheduler_service.py:150`, `app/workers/waybill_worker.py:1376`, `app/services/scheduled_waybill_executor.py:172`).

## Executed checks

1. `pytest tests/test_mobile_waybill_bot.py tests/test_otp_wakeup_and_lifecycle.py tests/test_otp_reliability_regressions.py tests/test_otp_delivery_contract.py tests/test_otp_forwarder.py tests/test_otp_forwarder_hardening.py tests/test_tenant_isolation_gaps.py -q --tb=short --show-capture=no`: **129 passed in 50.36s**, before the final outcome-read refinement. Log: `otp-api-worker-tests.log`.
2. After that refinement and its new race regression, `pytest tests/test_otp_wakeup_and_lifecycle.py -q --tb=short --show-capture=no`: **54 passed in 15.08s**. Log: `otp-final-lifecycle-tests.log`.
3. `pytest tests/test_rpa_dispatch_scheduler.py tests/test_rpa_scheduler_gate_integration.py tests/test_rpa_scheduler_cooldown.py tests/test_scheduled_waybill_executor.py tests/test_dispatch_intents.py tests/test_scheduler_policy.py -q --tb=short --show-capture=no`: **33 passed in 94.27s**. Log: `otp-scheduler-tests.log`.
4. Ruff on the 10 changed source files and five related test files: **All checks passed**. Black `--check`: **15 files would be left unchanged**. Scoped `git diff --check`: exit **0**.
5. Mypy on the 10 changed source files with `--ignore-missing-imports --follow-imports=silent`: **Success: no issues found in 10 source files**. The normal-follow run additionally reports optional Torch typing errors outside these changed files in CAPTCHA dependencies; this scoped check is not a substitute for the full CI type check.

The integrated lifecycle test uses actual isolated Redis Lua/Stream commands and SQLite sessions, with the broker dispatch and UTCMS transport mocked. It exercises HTTP intake, dispatch to `rpa_submit_2`, the actual Celery task body, committed pre-POST fence visibility, tracking persistence, terminal ACK, and duplicate-delivery suppression. Other regressions cover lease loss during login/commit, stale ORM state, driver/worker/document changes, wrong cached-token scope, expired delivery, stream failures, late SMS, and all-stale attribution (`tests/test_otp_wakeup_and_lifecycle.py:180`).

## Limits and rollout requirements

- No live UTCMS request, registration, deployment, or global live-submit enablement was performed by this subtask. The existing accepted mobile SUCCESS exception remains unchanged.
- SQLite does not enforce PostgreSQL row locks. The `FOR UPDATE` boundary was inspected and its surrounding behavior tested, but concurrent PostgreSQL lock behavior and real broker routing remain unverified locally.
- Legacy pending documents without the new durable challenge fail closed with HTTP 409. They require reconciliation or explicit revalidation of their original authorization; no automatic grant migration is supplied. Stream entries without original timing evidence are discarded rather than refreshed.
- Drain old workers before a mixed-version rollout: old inline issuance and unconditional lease deletion do not implement the new ownership/fence protocol.
- The scheduler fixture used the generic SQLAlchemy `AsyncSession` and an unawaited `flush`; it now uses the production SQLModel session and awaits `flush`. The initial 5 fixture failures were resolved and all 33 scheduler tests were rerun.

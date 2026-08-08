# BarPro Final Polish Report — Driver-Slot Safety, Cancel Lifecycle, Scheduler Policy

Branch: `arena/019fe01a-barpro-main`
Commit: `5fb6fc1`
Date: 2026-08-08

This report covers the production-hardening pass executed on the Arena branch.
It focuses on the highest-severity, verifiable P0 items: stuck driver slots,
safe cancellation, and scheduler eligibility/quota enforcement. Changes were
kept to code paths that could be tested locally against an in-memory SQLite DB
with no live UTCMS/portal calls.

---

## 1. Files changed

| File | Change |
|---|---|
| `app/orchestrator/driver_slot.py` | **New.** Central `release_driver_execution_slot()` helper. |
| `app/orchestrator/scheduler_service.py` | Enforce subscription window; atomic `DriverRuntimeState` creation. |
| `app/orchestrator/dispatcher_service.py` | Use helper for celery-unavailable slot release. |
| `app/orchestrator/claim_reaper.py` | Use helper for stale-claimed recovery slot release. |
| `app/orchestrator/orphan_detector.py` | Use helper for orphaned-execution slot release. |
| `app/workers/waybill_worker.py` | Release slot in draining / proxy-unavailable / proxy-unhealthy paths (submit + reconcile) and in `_finalize_execution`. |
| `app/services/waybill_job_service.py` | Soft-cancel cancels pending/claimed intents + releases slot; terminal jobs with child records are archived, not hard-deleted. |
| `tests/test_driver_slot_release.py` | **New.** 7 tests (P0). |
| `tests/test_scheduler_policy.py` | **New.** 9 tests (scheduler policy/race). |
| `tests/test_cancellation_lifecycle.py` | **New.** 8 tests (cancel lifecycle). |

## 2. Problems fixed

1. **P0 — jobs stuck forever holding a driver slot.** The scheduler sets
   `DriverRuntimeState.active_execution_id` when it queues a job. If the worker
   later failed *before* creating an `Execution` (draining, proxy
   unavailable/unhealthy, celery unavailable, failed claim), the job went to
   `WAITING_RETRY` but the slot was never cleared. Since the scheduler skips any
   driver with a non-null slot, the job became permanently invisible → stuck.
   Now every pre-execution failure path releases the slot through one helper.
2. **P0 — unsafe/inconsistent slot release.** Slot release was previously done
   ad-hoc in 5 places with no ownership guard and no "live Execution" check,
   risking freeing a slot owned by another intent or by a running worker.
   `release_driver_execution_slot()` centralizes: `FOR UPDATE` lock,
   `expected_intent_id` ownership guard, never frees while a live (pending/
   running) Execution exists, idempotent, structured logging.
3. **Cancel lifecycle.** Soft-cancel now cancels the job's pending/claimed
   `DispatchIntent`s (so the dispatcher never claims a cancelled job) and
   releases the driver slot only when no live Execution exists. Running jobs
   with a live Execution return HTTP 409 and are untouched.
4. **Hard-delete of audited jobs.** Terminal jobs that still carry child
   records (`DispatchIntent`, `Execution`, `WaybillTaskLog`, `DomainEvent`,
   `WaybillAttempt`) were hard-deleted, destroying the audit trail. They are now
   archived (→ `cancelled`). `SUCCESS` jobs (which cannot legally transition to
   `cancelled` in the state machine, by design) are rejected with 409 rather
   than hard-deleted.
5. **Scheduler subscription window not enforced.** Scheduler enforced tenant
   ACTIVE / driver ACTIVE-READY / quotas but not `subscription_start_date` /
   `subscription_end_date`. Both are now enforced.
6. **Scheduler runtime-state race.** Two concurrent schedulers racing to create
   a missing `DriverRuntimeState` for the same driver could double-insert and
   hit the unique constraint. Creation is now wrapped in a nested transaction
   with `IntegrityError` re-fetch.

## 3. Issues that need a product decision

- **Daily-quota semantics.** The scheduler counts jobs *created today* toward
  `max_daily_tasks`. The prompt suggests counting submit attempts / successful
  submissions instead. That needs a decision + a new counter (see §8) and is
  **not** changed here to avoid a migration churn without a decision.
- **Archiving vs a `deleted_at` flag.** Terminal jobs are archived via the
  `cancelled` status. If you want a distinct "archived" state (so `cancelled`
  keeps its current meaning) or a `deleted_at` timestamp with a filter on the
  list endpoint, that is a product decision requiring a schema change.
- **`SUCCESS` deletion policy.** A registered waybill cannot currently be
  cancelled/deleted; we reject with 409. Confirm whether admins need a
  force-archive path.

## 4. Migrations

None added. The subscription fields and `DriverRuntimeState`/`Execution`/
`DispatchIntent` tables already exist (previous migrations). No DDL change was
required for this pass. No existing already-applied migration was altered.

## 5. Tests run & result

New tests (24) — all pass:

- `tests/test_driver_slot_release.py` (7):
  proxy-unavailable, proxy-unhealthy, worker-draining, celery-unavailable each
  release the slot; slot is **not** released when an Execution is running; slot
  release requires matching intent; no-runtime-state is a no-op; idempotent.
- `tests/test_scheduler_policy.py` (9):
  suspended tenant / expired subscription / not-yet-started subscription /
  inactive driver / future `submit_after` / concurrent quota / daily quota are
  each not scheduled; eligible job is scheduled; missing runtime state is
  created atomically.
- `tests/test_cancellation_lifecycle.py` (8):
  cancel queued job cancels pending intent + releases slot; cancel claimed job
  without execution cancels claimed intent + releases slot; running job returns
  409; live-execution slot not freed; dispatcher skips cancelled job;
  terminal job with children archived (not hard-deleted); SUCCESS job with
  children rejected 409; terminal job with intent archived.

Regression checks on existing suites (all pass): `test_dispatch_intents`,
`test_state_machine`, `test_state_machine_retry_guards`, `test_reconciliation_service`,
`test_submission_identity`, `test_worker_proxy_and_rotator`, `test_worker_proxy_health`,
`test_queue_routing_contract`, `test_once_schedule`, `test_driver_fifo`,
`test_execution_lease`.

Full-suite run: **559 passed, 4 skipped, 57 failed**. The 57 failures are
pre-existing, environment-only API tests that return HTTP 429 from the shared
rate limiter (`test_driver_multitenant`, `test_system_health`, `test_readyz_failures`,
`test_validation`, `test_security_waybill`, `test_worker_security`, `test_itmb_ws_service`,
`test_location_service_and_routes`). Confirmed identical on the baseline (stash):
these are not caused by this change. No live UTCMS call is executed by any test.

## 6. Lint / type / build

- `ruff check` on all changed files: **pass**.
- `ruff format --check` on changed files: **pass**.
- `black --check` on changed files: **pass**.
- Repo-wide `ruff check app tests` reports 324 errors / 88 files needing format
  — **pre-existing** (baseline = 333). This pass reduced it by 9. Fully fixing
  the repo-wide lint is a separate CI cleanup task (Phase 9) not completed here.
- `mypy` is configured to ignore errors under `app.*`, so no new type errors.
- Frontend (`npm ci/lint/typecheck/build`) was not run in this environment
  (no changes were made to `apps/web` in this pass).

## 7. Performance improvements

- Scheduler pre-dispatch guards moved to cached per-tenant lookups (unchanged
  from baseline); the added subscription checks use already-cached `client`
  objects (no extra queries).
- Slot release now runs a single `FOR UPDATE` lookup + one optional
  `Execution` existence check instead of scattered duplicate lookups.
- No N+1 introduced; worker and scheduler remain separate queues.

## 8. Session / screenshot security

**Not changed in this pass.** The prompt's Phase 7 (session encryption,
0600 file perms, key rotation, jittered refresh) and Phase 8 (screenshot
tenant-scoping, frontend contract) are pre-existing features/fixtures. Verifying
and hardening them, plus the daily-quota counter change, is deferred — they need
their own migration/test cycle.

## 9. Residual risks

- Repo-wide ruff/black non-compliance remains (pre-existing) — CI quality gate
  will not pass until that cleanup lands.
- Rate-limiter tests return 429 in this sandbox (no shared Redis) — CI with a
  real/isolated Redis is expected to behave differently.
- Daily-quota semantics (submit-attempt vs jobs-created) unresolved.
- Phase 7/8 (session encryption + screenshot/frontend hardening) not addressed
  in this pass.
- Migration 031 integration test and `docker compose config` validation were not
  executed here (no PostgreSQL/Compose stack in the sandbox).

## 10. Deploy & rollback

**Deploy:** this commit adds one new module and touches orchestration paths;
it requires no DB migration. Standard deploy:

```
git fetch origin && git checkout arena/019fe01a-barpro-main
git pull
./manage.sh migrate     # no-op, no new migrations
./manage.sh build
./manage.sh start
./manage.sh health
```

**Rollback:** revert commit `5fb6fc1` (or reset to `d039f62`). Because the slot
release fix is a behavioral correction (releasing stuck slots), rolling back
reintroduces the risk of stuck jobs but causes no data corruption. The
cancellation/hard-delete behavior change affects only the delete endpoint; no
backfill is needed.

```
git revert 5fb6fc1
# then restart scheduler + worker + dispatcher + claim-reaper
```

---

*No item above is marked "fixed" unless it has a code fix, a passing test, and
a reviewed regression path. Migrations required by any remaining item are
listed as outstanding.*

# Phase 4: worker-resilience-performance-and-verification — Context

## Locked decisions

1. Celery worker concurrency and task queue routing must be isolated and tuned for Model B workers.
2. In-flight job scheduling must exclude pending siblings to allow FIFO queue progression while strictly preserving the 1-driver-1-active-trip safety invariant.
3. Automated test suites (unit + integration regressions) must pass 100% with clean linters (ruff, black, mypy) before verification.
4. Two-Witness Proof is mandatory for verifying live worker waybill issuance.

## Approaches considered

### A — Parameterized include-pending flag for scheduler trip check
Parameterize `find_driver_active_job` with `include_pending: bool = True` so creation/submission keeps strict pending protection while the scheduler queries with `include_pending=False`, freeing pending siblings to schedule FIFO.
What it buys: Prevents deadlock among queued sibling jobs for the same driver without risking concurrent execution or breaking the 1-driver-1-waybill invariant.
What it costs: Requires passing the flag explicitly at scheduler dispatch call sites.

### B — Complete removal of PENDING from active_in_flight statuses
Remove `TaskStatus.PENDING.value` globally from `find_driver_active_job`.
What it buys: Simple one-line change.
What it costs: Breaks job creation validation; multiple pending jobs could be accepted without safety boundaries at submission time.

chosen: A — because parameterizing `include_pending` isolates FIFO scheduling unblocking to the scheduler while retaining full creation-time safety.

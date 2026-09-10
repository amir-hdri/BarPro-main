# Runbook: Tracking-First Waybill Acknowledgement

**Last reviewed: 2026-09-09**

This runbook covers the operator side of the tracking-first acknowledgement
contract: what a UTCMS tracking code proves, what it does **not** prove, and how
to inspect, verify and (where allowed) manually drive one job through the
contract.

Scope:

- A non-empty UTCMS tracking code is an **immediate operator acknowledgement**:
  it is persisted exactly once in `waybill_jobs.result_json` with
  `confirmation_status='tracking_received'`, `operator_acknowledged=true`,
  `requires_reconciliation=false`, `requires_resubmission=false`.
- The database job status stays `unknown` — it is **not** `success`. Final
  `success` still requires the unchanged three-witness rule
  (`mutation_status='confirmed'` + `reconciled_at` + persisted tracking code).
- A tracking-received job never receives a second submit intent, never retries
  the final POST, and never auto-reconciles. A manual audit-only path exists
  (see §3).
- A success-shaped response without a tracking code stays `unknown` with
  `confirmation_status='tracking_missing_history_required'` and
  `reconciliation_mode='history_only'`, and goes through a bounded read-only
  UTCMS History reconciliation schedule (15s / 45s / 120s / 300s) — never a
  resubmit.

Related contracts: [UTCMS_CONSTRAINTS.md](../UTCMS_CONSTRAINTS.md),
[UTCMS_RECONCILIATION.md](../UTCMS_RECONCILIATION.md),
[UTCMS_BOT_BEHAVIOR_CONTRACT.md](../UTCMS_BOT_BEHAVIOR_CONTRACT.md).

---

## 1. Inspect one job's acknowledgement state

Run against the waybill job table (placeholder identifiers only):

```sql
SELECT
    status,
    result_json->>'tracking_code'      AS tracking_code,
    result_json->>'confirmation_status' AS confirmation_status,
    result_json->>'operator_acknowledged' AS operator_acknowledged,
    result_json->>'reconciliation_mode' AS reconciliation_mode,
    mutation_status,
    reconciled_at
FROM waybill_jobs
WHERE job_id = '<JOB_ID>';
```

What each combination means:

| status | confirmation_status | meaning |
|---|---|---|
| `unknown` | `tracking_received` | Tracking code captured; operator acknowledgement recorded. Waiting for the (manual/audit-only) History confirmation. Not final success. |
| `unknown` | `tracking_missing_history_required` | Success-shaped response but no code; bounded read-only History reconciliation is scheduled. |
| `success` | `confirmed_by_history` | History found the document; three-witness rule satisfied; final. |
| `needs_review` | `submission_unconfirmed` (error category) | History window exhausted without a match; requires a human decision. |

The response-level `operator_acknowledged` boolean (on `WaybillJobResponse` and
`WaybillTaskStatusResponse`) mirrors the persisted result field. The UI shows
«کد رهگیری دریافت شد» (with sub-label «در انتظار تأیید نهایی») for
acknowledged jobs and «در انتظار تطبیق با سوابق UTCMS» for missing-code jobs; neither
shows a retry/resubmit action.

## 2. Confirm no submit intent was created after acknowledgement

A tracking-received job must never be dispatched again. To verify that no
submit or reconciliation intent survived the acknowledgement, query the
dispatch intent table for the job after the acknowledgement timestamp
(placeholder identifiers only):

```sql
SELECT intent_id, operation, status, created_at
FROM dispatch_intents
WHERE job_id = '<JOB_ID>'
  AND created_at > '<ACKNOWLEDGE_TIMESTAMP>'
  AND status IN ('pending', 'claimed');
```

Expected result: **zero rows.** The dispatcher cancels stale
submit/reconciliation intents for tracking-received jobs, and the scheduler
skips tracking-acknowledged jobs. If any `pending`/`claimed` intent appears
after the acknowledgement timestamp, treat it as a contract violation and
escalate — do not let it run.

## 3. Manually start read-only History reconciliation (missing-code outcome)

For a `tracking_missing_history_required` job, automatic reconciliation is
read-only UTCMS History polling on the bounded schedule (15s / 45s / 120s /
300s). To start it manually, use the admin reconciliation route
(`app/api/routes/admin_alerts.py`, ~line 123) which calls
`reconciliation_service.reconcile_job`:

```
POST /api/v1/admin/...   # admin reconciliation trigger for <JOB_ID>
```

Alternatively, from a backend shell, invoke the service directly:

```python
# app/orchestrator/reconciliation_service.py
await reconciliation_service.reconcile_job(job_id="<JOB_ID>")
```

Outcomes:

- **History REGISTERED → tracking code recovered**: the job may transition to
  final `success` (`mutation_status='confirmed'`, `reconciled_at` set,
  `confirmation_status='confirmed_by_history'`).
- **History NOT_FOUND after the bounded window**: the job becomes
  `needs_review` / `submission_unconfirmed`. Automatic resubmission never
  happens; a human decides.

For a **tracking-received** job, automatic reconciliation is skipped. The only
manual path is the audit-only service call:

```python
await reconciliation_service.reconcile_job(job_id="<JOB_ID>", audit_only=True)
```

`audit_only=True` forces a manual audit: it never mutates the job towards a
resubmit and exists solely to attach History evidence for the three-witness
confirmation.

## 4. Decision table

| RPA result | Persisted state | Operator result | History | Resubmit |
|---|---|---|---|---|
| Non-empty tracking code | `unknown` + `tracking_received` acknowledgement | Immediate code shown («کد رهگیری دریافت شد») | Not on the critical path (audit-only manual path available) | Never |
| Success-shaped response, no code | `unknown` + `tracking_missing_history_required` | Pending verification («در انتظار تطبیق با سوابق UTCMS») | Read-only, bounded (15s/45s/120s/300s) | Never |
| History finds the code | `success` + `confirmed` + `reconciled_at` | Confirmed | Completed | Never |
| History not found after window | `needs_review` / `submission_unconfirmed` | Manual review required | Exhausted | Never automatic |
| Clear pre-submit failure (before the mutation boundary) | Existing retryable-failure policy | Retryable | Not required | Existing guarded retry only |

## 5. Invariant — a tracking code is not final success

A tracking code alone **never proves final UTCMS History registration**. It
must not be counted as final success in monitoring or accounting reports.
Final success requires the full three-witness rule: the tracking code in the
RPA response, the same code persisted in `waybill_jobs.result_json`, and
`mutation_status='confirmed'` with `reconciled_at` set (matching record in
UTCMS History). Any dashboard, report or alert that counts
`confirmation_status='tracking_received'` jobs as successful submissions is
wrong by contract.

Guards that enforce the contract (all `CODE-VERIFIED` per the knowledge
graph):

- Dispatcher cancels stale submit/reconciliation intents for tracking-received jobs.
- Scheduler skips tracking-acknowledged jobs.
- Reconciliation skips code-present jobs (manual path is `audit_only=True` only).
- The retry API endpoint rejects tracking-received jobs with HTTP 409.
- `rpa_scheduler` recovery of stuck jobs preserves the tracking-received contract.

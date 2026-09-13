# Tracking-First Waybill Acknowledgement Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make BarPro return a prompt operator acknowledgement as soon as UTCMS returns a non-empty tracking code, and use read-only UTCMS History reconciliation only when a supposedly successful submission returns no tracking code.

**Architecture:** Keep the existing single-submit and idempotency protections. A tracking code becomes an immediate operator acknowledgement persisted in `result_json`; it must never enqueue a second submit. A success-shaped response without a tracking code crosses the mutation boundary into the existing read-only reconciliation flow. Do not weaken the project invariant that database `success` is reserved for a confirmed mutation with a persisted tracking code and a reconciliation timestamp.

**Tech Stack:** Python 3.11, FastAPI, SQLModel, Celery, Playwright, pytest, Next.js 15, TypeScript.

**Spec:** This plan implements the operator requirement: «اگر کد رهگیری دریافت شد، نتیجه فوری نمایش داده شود؛ اگر کد دریافت نشد، پس از پاسخ موفق فقط History همان بارنامه بررسی شود.» The authoritative safety contracts remain `docs/UTCMS_CONSTRAINTS.md`, `docs/UTCMS_BOT_BEHAVIOR_CONTRACT.md`, and `CRITICAL_RULES.md`.

## Global Constraints

- The final POST to UTCMS is exactly once; never retry, fallback, or duplicate the mutation request.
- A Job with a non-empty persisted tracking code is never submitted again.
- A response without a tracking code is not evidence that no waybill exists; reconcile read-only before any operator-approved new idempotency key.
- Never print or persist UTCMS passwords, CAPTCHA answers, cookies, authorization headers, or SSH credentials.
- Preserve `ALLOW_LIVE_SUBMIT=false` as the default and require the existing live-submit gates.
- Do not create a new Job for the same canonical waybill merely to obtain a tracking code.
- Keep the existing three-witness rule for database `status=success`; expose the tracking code immediately through an acknowledgement field/status instead of falsely marking final success.
- Keep all behavior identical between the normal Worker path and `scheduled_waybill_executor`.

---

### Task 1: Define the tracking-first result contract

**Files:**
- Modify: `app/schemas/task.py`
- Modify: `app/schemas/multitenant.py`
- Modify: `app/services/waybill_job_service.py`
- Test: `tests/test_tracking_first_contract.py`

**Interfaces:**
- Add a stable result-level value `confirmation_status="tracking_received"`.
- Add a response-level boolean `operator_acknowledged: bool = False` where the existing job/task response models expose result data.
- Do not add a new database status unless a full repository-wide status audit proves it is necessary. Prefer the existing `unknown` status plus the explicit confirmation status so queue/reporting behavior does not silently change.

- [ ] **Step 1: Write failing contract tests**

```python
def test_tracking_received_is_an_operator_ack_not_final_success():
    result = build_tracking_received_result("UTC-123")
    assert result["operator_acknowledged"] is True
    assert result["confirmation_status"] == "tracking_received"
    assert result["tracking_code"] == "UTC-123"
    assert result["requires_resubmission"] is False


def test_missing_tracking_code_requires_read_only_reconciliation():
    result = build_missing_tracking_result(document_id="214000001")
    assert result["requires_reconciliation"] is True
    assert result["reconciliation_mode"] == "history_only"
    assert result["requires_resubmission"] is False
```

- [ ] **Step 2: Run the focused tests and verify failure**

Run: `pytest tests/test_tracking_first_contract.py -q`

Expected: FAIL because the explicit acknowledgement contract does not yet exist.

- [ ] **Step 3: Implement the smallest contract helpers**

Create one dependency-free helper in the existing service/module chosen by the repository conventions. It must normalize whitespace and return exactly these fields:

```python
def build_tracking_received_result(tracking_code: str, **details: object) -> dict[str, object]:
    code = str(tracking_code or "").strip()
    if not code:
        raise ValueError("tracking_code must be non-empty")
    return {
        **details,
        "tracking_code": code,
        "confirmation_status": "tracking_received",
        "operator_acknowledged": True,
        "requires_reconciliation": False,
        "requires_resubmission": False,
    }


def build_missing_tracking_result(*, document_id: str | None) -> dict[str, object]:
    return {
        "document_id": document_id,
        "confirmation_status": "tracking_missing_history_required",
        "operator_acknowledged": False,
        "requires_reconciliation": True,
        "reconciliation_mode": "history_only",
        "requires_resubmission": False,
    }
```

Keep the final `JobStateMachine` success guard unchanged.

- [ ] **Step 4: Run the focused tests**

Run: `pytest tests/test_tracking_first_contract.py -q`

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add app/schemas/task.py app/schemas/multitenant.py app/services/waybill_job_service.py tests/test_tracking_first_contract.py
git commit -m "feat: define tracking-first waybill acknowledgement contract"
```

---

### Task 2: Change the normal RPA Worker result handling

**Files:**
- Modify: `app/automation/waybill_bot_multitenant.py:241-290`
- Modify: `app/workers/waybill_worker.py:1343-1435`
- Test: `tests/test_waybill_submission_reliability.py`
- Test: `tests/test_mutation_safety.py`

**Interfaces:**
- The bot returns a non-empty tracking code as `status="success"` plus `confirmation_status="tracking_received"` and `operator_acknowledged=true`.
- The Worker persists the code in `WaybillJob.result_json` in the same transaction that records the mutation boundary.
- The Worker must not enqueue reconciliation or create another submit intent when a tracking code is present.

- [ ] **Step 1: Add failing tests for code-present behavior**

Add tests that invoke the Worker result path with a manager result containing `tracking_code="UTC-123"` and assert:

```python
assert result["status"] == "success"
assert result["result"]["tracking_code"] == "UTC-123"
assert result["result"]["confirmation_status"] == "tracking_received"
assert result["result"]["operator_acknowledged"] is True
assert result["result"]["requires_resubmission"] is False
assert reconciliation_dispatch.call_count == 0
```

Also assert that a second invocation of the same Job returns the persisted result and does not call `create_waybill_with_map`.

- [ ] **Step 2: Add failing tests for code-missing behavior**

For a result with `success=true`, `document_id` present, and no tracking code, assert:

```python
assert result["status"] == "unknown"
assert result["error_category"] == "submission_unconfirmed"
assert result["needs_reconciliation"] is True
assert result["reconciliation_mode"] == "history_only"
assert result["requires_resubmission"] is False
```

Assert that only a reconciliation intent is created and no UTCMS submit method is called again.

- [ ] **Step 3: Run the focused tests and verify failure**

Run: `pytest tests/test_waybill_submission_reliability.py tests/test_mutation_safety.py -q`

Expected: the new tracking-first assertions fail against the current mandatory-History behavior.

- [ ] **Step 4: Implement the normal Worker path**

In `waybill_bot_multitenant.py`, replace the block that converts every non-empty tracking code to `unknown/pending_history_reconciliation` with the tracking acknowledgement contract. Preserve all existing fields such as screenshot, route, origin/destination methods, and document ID. Do not remove the mutation boundary flags.

In `waybill_worker.py`, when `result_status == success` and the normalized tracking code is non-empty:

1. Build the acknowledgement result.
2. Set `job.result_json` to that result, preserving `document_id`.
3. Set `job.mutation_status = "dispatched"` unless the existing adapter has an independently confirmed mutation value.
4. Set `job.mutation_at` if the existing path does so.
5. Do not set `reconciled_at` merely because a code exists.
6. Do not dispatch a reconciliation intent for this code-present path.
7. Return `status="success"` to the API caller with `operator_acknowledged=true`.
8. Keep the existing idempotency check before any browser/session creation.

When the result is success-shaped but has no tracking code, retain `unknown`, set `confirmation_status="tracking_missing_history_required"`, and schedule only the existing read-only reconciliation path.

- [ ] **Step 5: Run the focused tests**

Run: `pytest tests/test_waybill_submission_reliability.py tests/test_mutation_safety.py -q`

Expected: PASS, with all pre-existing mutation-safety tests still green.

- [ ] **Step 6: Commit**

```bash
git add app/automation/waybill_bot_multitenant.py app/workers/waybill_worker.py tests/test_waybill_submission_reliability.py tests/test_mutation_safety.py
git commit -m "feat: acknowledge tracking code without blocking on history"
```

---

### Task 3: Make the scheduled executor behavior identical

**Files:**
- Modify: `app/services/scheduled_waybill_executor.py:242-292`
- Test: `tests/test_scheduled_waybill_executor.py`

**Interfaces:**
- The scheduled executor must use the same helper and result keys as the normal Worker path.
- There must be no second implementation of the tracking-first decision tree.

- [ ] **Step 1: Write failing parity tests**

Mock the bot response twice, once through the normal worker adapter and once through the scheduled executor. Assert that both produce the same values for `status`, `tracking_code`, `confirmation_status`, `operator_acknowledged`, `requires_reconciliation`, and `requires_resubmission`.

- [ ] **Step 2: Run the parity test and verify failure**

Run: `pytest tests/test_scheduled_waybill_executor.py -q`

Expected: FAIL because the executor currently converts a tracking code into `unknown` and schedules History.

- [ ] **Step 3: Implement parity**

For a non-empty code, persist the result immediately, return `success` with the acknowledgement fields, and do not set `next_retry_at` or `submit_after` for reconciliation. For a missing code, retain the existing `unknown` plus `history_only` reconciliation schedule. Reuse the shared helper; do not duplicate normalization logic.

- [ ] **Step 4: Run tests**

Run: `pytest tests/test_scheduled_waybill_executor.py tests/test_waybill_submission_reliability.py -q`

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add app/services/scheduled_waybill_executor.py tests/test_scheduled_waybill_executor.py
git commit -m "fix: align scheduled executor with tracking-first acknowledgement"
```

---

### Task 4: Keep History reconciliation read-only and code-missing only

**Files:**
- Modify: `app/orchestrator/reconciliation_service.py`
- Modify: `app/orchestrator/dispatcher_service.py`
- Modify: `app/services/rpa_scheduler_service.py`
- Test: `tests/test_reconciliation_service.py`
- Test: `tests/test_state_machine_retry_guards.py`

**Interfaces:**
- History reconciliation may be scheduled for `tracking_missing_history_required`, `unknown`, or existing ambiguous mutation states.
- A Job with a persisted tracking code is never eligible for submit dispatch, even if an old reconciliation intent exists.
- History lookup remains GET/read-only and must never call the final submit endpoint.

- [ ] **Step 1: Add failing guard tests**

Cover these exact cases:

```python
def test_tracking_received_job_is_not_reconcilable_for_submit(async_db):
    # A tracking code must block any submit dispatch.
    assert can_dispatch_submit(job_with_tracking_code) is False


def test_missing_code_reconciliation_can_recover_code(async_db):
    # History REGISTERED result persists the code and reaches final success.
    assert reconciled_job.status == JobStatus.SUCCESS
    assert reconciled_job.result_json["tracking_code"] == "UTC-HISTORY-1"


def test_history_not_found_never_resubmits(async_db):
    # Exhausted History lookup becomes needs_review; submit count stays zero.
    assert reconciled_job.status == JobStatus.NEEDS_REVIEW
    assert submit_mock.call_count == 0
```

- [ ] **Step 2: Run tests and verify failure or missing coverage**

Run: `pytest tests/test_reconciliation_service.py tests/test_state_machine_retry_guards.py -q`

- [ ] **Step 3: Implement guards**

Update reconciliation scheduling predicates so code-present Jobs are skipped for reconciliation unless the operation is an explicitly named audit-only operation. Update submit dispatch predicates so `result_json.tracking_code` is an unconditional no-submit guard. Keep existing fencing, lease, tenant, driver, and idempotency checks.

For a missing-code result, keep the existing bounded delays `15, 45, 120, 300` seconds. On exhaustion transition to `needs_review/submission_unconfirmed`; never auto-submit.

- [ ] **Step 4: Run tests**

Run: `pytest tests/test_reconciliation_service.py tests/test_state_machine_retry_guards.py -q`

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add app/orchestrator/reconciliation_service.py app/orchestrator/dispatcher_service.py app/services/rpa_scheduler_service.py tests/test_reconciliation_service.py tests/test_state_machine_retry_guards.py
git commit -m "fix: restrict history reconciliation to code-missing outcomes"
```

---

### Task 5: Expose the immediate acknowledgement clearly in API and frontend

**Files:**
- Modify: `app/schemas/multitenant.py`
- Modify: `app/services/waybill_job_service.py`
- Modify: `apps/web/src/lib/api.ts`
- Modify: frontend waybill status/timeline components found by `rg -n "needs_review|unknown|tracking_code|TaskStatus" apps/web/src`
- Test: `tests/test_waybill_service.py`
- Test: frontend test file following the existing test setup

**Interfaces:**
- API result must include `tracking_code`, `confirmation_status`, `operator_acknowledged`, and `requires_resubmission`.
- The UI must show the received code immediately as «کد رهگیری دریافت شد» and must not show a retry/resubmit action for that Job.
- A missing-code Job must show «نیازمند بررسی History» and must not show a live submit button.

- [ ] **Step 1: Add failing API/UI assertions**

Assert that the serialized response preserves the four fields and that a tracking-received Job is not grouped with retryable failures.

- [ ] **Step 2: Implement serialization and presentation**

Do not infer confirmation from a raw string in the frontend. Use the explicit response fields. Preserve the existing httpOnly-cookie authentication and 401 handling. Do not expose credentials or raw UTCMS responses.

- [ ] **Step 3: Run tests and type checks**

Run: `pytest tests/test_waybill_service.py -q`

Run: `npm --prefix apps/web run lint`

Run the repository's existing frontend test command from `apps/web/package.json`.

Expected: PASS.

- [ ] **Step 4: Commit**

```bash
git add app/schemas/multitenant.py app/services/waybill_job_service.py apps/web/src tests/test_waybill_service.py
git commit -m "feat: expose immediate tracking acknowledgement"
```

---

### Task 6: Update contracts, knowledge graph, and operational documentation

**Files:**
- Modify: `docs/UTCMS_CONSTRAINTS.md`
- Modify: `docs/UTCMS_BOT_BEHAVIOR_CONTRACT.md`
- Modify: `docs/UTCMS_RECONCILIATION.md`
- Modify: `docs/BARPRO_KNOWLEDGE_GRAPH.md`
- Modify: `docs/CHANGELOG.md`
- Create: `docs/operations/runbook_tracking_first_acknowledgement.md`

- [ ] **Step 1: Document the exact state machine**

Document this decision table:

| RPA result | Persisted state | Operator result | History | Resubmit |
|---|---|---|---|---|
| Non-empty tracking code | `unknown` + `tracking_received` acknowledgement | Immediate code shown | Not on critical path | Never |
| Success-shaped response, no code, mutation/document boundary crossed | `unknown` + `tracking_missing_history_required` | Pending verification | Read-only, bounded | Never |
| History finds matching waybill/code | `success` + `mutation_status=confirmed` + `reconciled_at` | Confirmed | Completed | Never |
| History not found after bounded window | `needs_review/submission_unconfirmed` | Manual review | Exhausted | Never automatic |
| Clear pre-submit/network failure before mutation boundary | Existing retryable failure policy | Retryable | Not required | Existing guarded retry only |

- [ ] **Step 2: State the invariant explicitly**

The documentation must say that a tracking code is sufficient for immediate operator acknowledgement but not, by itself, sufficient to label the database mutation as final `success`. This prevents monitoring and accounting reports from overstating certainty.

- [ ] **Step 3: Add the runbook**

Include commands for inspecting one Job, confirming its persisted tracking code, checking that no submit intent was created after acknowledgement, and manually starting read-only History reconciliation for missing-code outcomes. Redact secrets in every example.

- [ ] **Step 4: Run documentation and contract tests**

Run: `pytest tests/test_utcms_submission_gate.py tests/test_utcms_reconciliation.py tests/test_mutation_safety.py -q`

- [ ] **Step 5: Commit**

```bash
git add docs/UTCMS_CONSTRAINTS.md docs/UTCMS_BOT_BEHAVIOR_CONTRACT.md docs/UTCMS_RECONCILIATION.md docs/BARPRO_KNOWLEDGE_GRAPH.md docs/CHANGELOG.md docs/operations/runbook_tracking_first_acknowledgement.md
git commit -m "docs: specify tracking-first acknowledgement and history fallback"
```

---

### Task 7: Full verification and deployment gate

**Files:**
- Modify only files justified by failing verification; do not alter `.env` or commit secrets.

- [ ] **Step 1: Run focused backend tests**

```bash
pytest tests/test_tracking_first_contract.py tests/test_waybill_submission_reliability.py tests/test_mutation_safety.py tests/test_reconciliation_service.py tests/test_state_machine_retry_guards.py -q
```

- [ ] **Step 2: Run the complete backend suite**

```bash
pytest -q
```

Record the exact result from the current commit; do not reuse historical test counts.

- [ ] **Step 3: Run static and frontend checks**

```bash
ruff check app tests
mypy app --ignore-missing-imports
npm --prefix apps/web run lint
```

Run the existing frontend test command from `apps/web/package.json`.

- [ ] **Step 4: Verify the no-duplicate invariant with a database fixture**

For one canonical Job, execute the result handler twice. Assert exactly one Job, one mutation attempt record, one persisted tracking code, and zero additional submit calls on the second execution. Include a pre-existing duplicate intent fixture and assert it is not dispatched.

- [ ] **Step 5: Perform deployment only after all gates pass**

Use the repository's `manage.sh`/Compose V2 deployment path. Verify migration status, API readiness, Worker 1 queue consumption, Redis, PostgreSQL, Nginx, Squid, and memory headroom. Do not run live UTCMS submission as part of automated verification.

- [ ] **Step 6: Perform one operator-controlled live smoke test only when explicitly authorized**

Use one prevalidated canonical Job, one Worker, one IP, and `ALLOW_LIVE_SUBMIT=true` only for that controlled run. Capture only non-sensitive evidence: Job ID, UTCMS tracking code, timestamps, Worker/IP index, and persisted result fields. Never log passwords, cookies, CAPTCHA answers, or full request bodies.

- [ ] **Step 7: Commit the verification record**

Add a dated operational report with exact commit, test results, deployment health, and whether a live smoke test was run. Do not claim final UTCMS registration for a tracking-only acknowledgement unless the repository's final-success witnesses are present.

## Acceptance Criteria

1. A non-empty tracking code is persisted once and shown immediately to the operator.
2. A tracking-received Job never creates a second submit Job or retries the final POST.
3. A success-shaped response without a tracking code enters read-only History reconciliation only.
4. A matching History result recovers and persists the tracking code and may transition the Job to final `success`.
5. Missing History after the bounded window becomes `needs_review/submission_unconfirmed` without automatic resubmission.
6. Normal Worker and scheduled executor return identical result semantics.
7. Existing OTP, CAPTCHA, lease, proxy, tenant-isolation, idempotency, and `ALLOW_LIVE_SUBMIT` gates remain intact.
8. Focused tests, full tests, lint, type checks, and frontend checks pass, with exact results recorded.
9. No secret, CAPTCHA answer, session cookie, or raw credential appears in source, test fixtures, logs, documentation, or the resulting Git diff.

## Self-Review Checklist

- [ ] Search for every existing conversion of a non-empty tracking code to `unknown`, `pending_history_reconciliation`, or `needs_reconciliation`, and decide it against this plan.
- [ ] Search for every submit dispatch path and confirm a persisted `result_json.tracking_code` blocks it.
- [ ] Search for every status/reporting aggregation and confirm tracking acknowledgement is not counted as final success.
- [ ] Confirm no test changes disable live-submit, security, or mutation-safety guards.
- [ ] Confirm no documentation claims that tracking code alone proves final UTCMS History registration.

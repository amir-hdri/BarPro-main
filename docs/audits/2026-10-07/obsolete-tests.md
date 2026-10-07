# Obsolete OTP test cleanup — 2026-10-07

Request: remove tests tied to obsolete architecture. Review was constrained to source-proven inactive behavior; active HTTP/Playwright migration coverage and security rejection regressions remain.

## Removed tests and proof

Removed from `tests/test_tenant_isolation_batch_c.py`:

1. `test_c1_store_otp_never_writes_global_key`.
2. `test_c1_two_tenants_consume_only_own_otp`.

Both invoked `app.api.routes.otp_forwarder.store_otp_in_redis` directly and described it as the active webhook/manual intake. The second also wrote hypothetical manual job keys directly into a dict, bypassing the current durable challenge/Stream path. `rg -n 'store_otp_in_redis' app tests --glob '*.py'` establishes no production callers: after this cleanup the symbol occurs only at its definition (`app/api/routes/otp_forwarder.py:125`), an outdated module docstring (`app/automation/otp_keys.py:4`), and an explanatory test comment. The unused application helper itself remains, per the parent's scope instruction.

Current source proof:

- Signed gateway → `accept_forwarded_otp` at `app/api/routes/otp_forwarder.py:194`.
- Normal/attributed phone intake → `accept_forwarded_otp` at lines 434 and 447.
- Manual job intake → `WaybillJobService.submit_otp` at line 488.
- Admin phone-only intake → `accept_forwarded_otp` at line 502.
- Job-owned manual persistence → `store_job_otp_event` at `app/services/waybill_job_service.py:631`.

Removed the old tests' now-unused route import and FakeRedis writer/publish scaffolding. No application behavior changed.

## Security coverage preserved through active intake

Extended existing `tests/test_otp_delivery_contract.py:90` (`test_android_payload_reaches_only_recipient_and_worker`) using actual local HTTP handlers, the actual Lua transaction and isolated Redis. It now submits messages for two distinct recipient phones and verifies:

- Each scoped browser reader obtains only its own recipient's code/key.
- The first phone's payload is unchanged by the second message.
- Neither the retired global key nor the shared sender shortcode receives a code.
- Exactly two distinct recipient/code messages exist in the durable Stream.
- Raw SMS text is absent from stored events and neither response echoes the code.

These are two synthetic recipients, not a claim of a live two-tenant deployment. Actual authenticated tenant/job rejection and cross-tenant cleanup remain covered by `tests/test_otp_wakeup_and_lifecycle.py`, `tests/test_tenant_isolation_gaps.py` and `tests/test_otp_forwarder_hardening.py`.

Also corrected `test_submit_manual_otp_delegates_to_authorized_service` to mock the current `unknown` state. The old `waiting_otp` value does not exist in `TaskStatus` (`app/models_multitenant.py:38–56`). The test's active delegation/privacy coverage is retained. Its old global-key auth docstring was corrected to explain the remaining admin diagnostic route.

The two manual-intake hardening tests now assert that the active phone writer `accept_forwarded_otp` is not used for job submission, replacing assertions against the uncalled legacy helper. They retain authenticated-job delegation and foreign-job rejection coverage.

## Explicitly retained

- No-global lookup, stale-entry rejection, job-key priority and empty-context fail-closed tests in `test_tenant_isolation_batch_c.py`.
- Query-token rejection, legacy challenge rejection, tracking guards, fence/lease/retry restrictions and tenant isolation tests.
- Browser OTP polling and `fetch_scoped_otp` tests. Source still calls `_handle_otp_if_required` at `app/automation/waybill_enhanced.py:5871`, and its active implementation begins at line 5278. The removed inline wait applies to the mobile branch, not all browser code.
- HTTP/Playwright and Android migration tests. `docs/ANDROID_CLIENT_IMPLEMENTATION_PLAN.md` identifies current HTTP behavior as the migration baseline, not an already-retired subsystem.
- Keras provider tests. The optional sample test has stale separate-environment commentary, but invokes the current in-process `KerasOcrCaptchaProvider`; that wording does not justify deleting working-provider coverage. No Keras file was changed.

## Verification and files

Edited only:

- `tests/test_tenant_isolation_batch_c.py`
- `tests/test_otp_delivery_contract.py`
- `tests/test_otp_forwarder.py`
- `tests/test_otp_forwarder_hardening.py`

Command: `.venv/bin/pytest tests/test_tenant_isolation_batch_c.py tests/test_otp_delivery_contract.py tests/test_otp_forwarder.py tests/test_otp_forwarder_hardening.py tests/test_otp_reliability_regressions.py tests/test_otp_wakeup_and_lifecycle.py tests/test_tenant_isolation_gaps.py tests/test_mobile_waybill_bot.py -q --tb=short --show-capture=no`

Result: **169 passed in 27.01s**, exit 0. Log: `/tmp/barpro-resume-20261007-obsolete-tests.log`.

Ruff on all four changed test files: **All checks passed!**, exit 0. Black `--check`: **4 files would be left unchanged**, exit 0. Scoped `git diff --check`: exit 0. After these checks the only subsequent edit was wording `Live intake` → `HTTP/Lua intake` in a module docstring.

No live UTCMS access, production operations, commit, push, shared-doc changes, or app/source changes were performed for this cleanup. Full-suite integration and documentation are owned by the parent.

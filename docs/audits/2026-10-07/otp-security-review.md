# OTP, security and CAPTCHA continuation verification — 2026-10-07

Workspace: `/Users/amirheidari/GitHub/BarPro-main`, dirty checkout based on `6c5564ea7483f127f2e23e785148009114bae49b`.

## Scope and recovered evidence

Read the repository critical rules, knowledge graph OTP/CAPTCHA and current continuation snapshots, runtime/UTCMS contracts, `docs/SMS_FORWARDER_AND_OTP_LIFECYCLE.md`, the `barpro-waybill-submission-safety` and `barpro-rpa-ops` skills, the prior `/Users/amirheidari/Documents/Codex/2026-10-07/sa/work/otp-security-note.md`, and the current continuation report. Reviewed the outstanding OTP intake/authentication/lease/stream/job-fence code and private CAPTCHA storage/diagnostic changes.

No source or test files were changed by this continuation. The previously fixed `tests/test_mobile_waybill_bot.py::test_mobile_bot_auto_solves_login_captcha` already mocks token/refresh reads and cache writes, asserts the cache miss and returned proof token, and passes in the combined current focused suite. The reported older full-suite failure does not reproduce on current source.

Reviewed invariants include tenant-owned phone resolution and cleanup, header-only webhook auth, retained original event timestamps, durable Stream before acknowledgement, immutable event/challenge binding, owning-worker dispatch and egress match, lease-token checks and renewal, re-read under row lock, persisted pre-POST fence, tracking guards, and removal of solved CAPTCHA answers from diagnostics. This is a focused review, not a fresh whole-repository security scan.

## Fresh verification

1. `.venv/bin/pytest tests/test_mobile_waybill_bot.py tests/test_otp_wakeup_and_lifecycle.py tests/test_otp_reliability_regressions.py tests/test_otp_delivery_contract.py tests/test_otp_forwarder.py tests/test_otp_forwarder_hardening.py tests/test_tenant_isolation_gaps.py tests/test_security_audit_gates.py tests/test_captcha_rejection_and_success_gate.py tests/test_security_sweep_regressions.py tests/test_captcha_no_torch.py tests/test_barname_ml_solver_no_torch.py tests/test_captcha_optional_typing.py tests/test_captcha_provider_factory.py tests/test_captcha_cnn_only.py tests/test_captcha_fallback.py tests/test_barname_ml_solver.py tests/test_utcms_mobile_contract.py -q --tb=short --show-capture=no` → **257 passed in 29.33s**, exit 0. Complete log: `/tmp/barpro-resume-20261007-otp-tests.log`.
2. Ruff on the fourteen application files and ten test files listed below → **All checks passed!**, exit 0.
3. Black `--check` on those same files → **24 files would be left unchanged**, exit 0.
4. Mypy on the fourteen application files with `--ignore-missing-imports` → **Success: no issues found in 14 source files**, exit 0. Log: `/tmp/barpro-resume-20261007-otp-mypy.log`.
5. `git diff --check -- <same twenty-four files>` → exit 0, no output.
6. `.venv/bin/python .agents/skills/barpro-rpa-ops/scripts/rpa_cli.py audit-network --output /tmp/barpro-resume-20261007-network-audit.json` → **Network audit passed**, exit 0. JSON reports no violations and explicitly notes that Playwright close-timeout enforcement still needs source review. This scanner result alone does not establish every browser lifecycle invariant.

Application files: `app/api/routes/otp_forwarder.py`, `app/automation/otp_keys.py`, `app/services/otp_delivery.py`, `app/services/otp_wakeup_consumer.py`, `app/services/otp_challenge_guard.py`, `app/services/waybill_job_service.py`, `app/core/private_storage.py`, `app/automation/captcha/debug_artifacts.py`, `app/automation/captcha/barname_ml_solver.py`, `app/automation/captcha/dnt_captcha_solver.py`, `app/automation/captcha/fuel_captcha_solver.py`, `app/automation/captcha/math_crnn_solver.py`, `app/automation/captcha/neural_net.py`, `app/automation/utcms_mobile_client.py`.

Static-check test files: `tests/test_mobile_waybill_bot.py`, `tests/test_otp_wakeup_and_lifecycle.py`, `tests/test_otp_reliability_regressions.py`, `tests/test_otp_delivery_contract.py`, `tests/test_otp_forwarder.py`, `tests/test_otp_forwarder_hardening.py`, `tests/test_security_audit_gates.py`, `tests/test_captcha_rejection_and_success_gate.py`, `tests/test_security_sweep_regressions.py`, `tests/test_captcha_optional_typing.py`.

## Follow-up passed to the parent

At review time, `app/services/waybill_job_service.py:967` set shipping status `in_transit` and assigned an origin witness after an exception from `register_start_of_shipping`, while an explicit unacknowledged response used `unknown`. This was reported to the parent for the shipping reviewer to assess against the accepted shipping contract. The OTP/security continuation did not edit that shipping section. Its disposition belongs in the final integrated report.

## Limits

- Local Redis delivery/lease fixtures use an isolated actual Redis Unix socket; job lifecycle fixtures use SQLite, synthetic broker dispatch and mocked UTCMS. These results do not independently prove PostgreSQL row locking, live Celery topology, production egress, actual issuance or mobile-app behavior.
- No production access, UTCMS request, deployment, credential change, commit or push was performed by this subagent. No access or changes to SMS-Forwarder-Pro.
- Shared documentation, full backend/frontend CI checks, dependency audits, final integration and GitHub are owned by the parent. This note does not claim the full suite is green.
- Existing rollout constraints remain: legacy pending jobs without a valid durable challenge fail closed; old workers require coordinated draining; `ALLOW_LIVE_SUBMIT` remains disabled by default.

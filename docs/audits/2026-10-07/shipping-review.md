# Shipping / GPS / Android / reporting continuation — 2026-10-07

Scope: shared `/Users/amirheidari/GitHub/BarPro-main` checkout. No production, UTCMS or Android runtime access; no commit/push; no shared documentation edits. Root owns consolidated docs and full verification.

Read CRITICAL_RULES, canonical knowledge graph, runtime/UTCMS behavior constraints, Android implementation plan, prior shipping note, and the local `barpro-fuel-inquiry` skill. Historical claims were treated as leads, not fresh proof.

## New change in this continuation

- `app/services/waybill_job_service.py:960-967` and `app/automation/waybill_bot_multitenant.py:758-768`: an exception from the post-issuance shipping-start call now leaves shipping `unknown`, records the error, and does not fabricate a GPS point with `Provenance=registered_start_of_shipping`. The already-issued waybill and tracking code remain intact. Prior code stored `in_transit` and an alleged registered origin after timeout/reset, inviting the completion sweep to act without an acknowledged start.
- `tests/test_mobile_shipping_start_contract.py:274-301`: removed the obsolete assertions that an ambiguous start must be automatically swept; replaced them with checks for `unknown`, no registered-origin point, and rejection by the actual `auto_complete_shipping(..., force=True)` entry point before login.
- `tests/test_otp_wakeup_and_lifecycle.py:256-315`: added four outcome cases (ACK 200, self-declared 4006, refusal 4025, lost response). They verify preserved issuance/tracking, origin evidence only on ACK, no completion claim for unknown starts, and no duplicate issue/start on replay.

## Previous interrupted work checked

- The old full-suite `KeyError: source` failure was already corrected in the current `tests/test_automated_shipping_and_payload_repair.py`; it now inspects the normalized `origin` passed to `insert_document`. The complete file passed twice in this continuation.
- Future Android elapsed timestamps and invalid uptime were already fixed before this continuation. Current tests cover 2.000s accepted versus 2.001s rejected, nonfinite/negative uptime, malformed durations, false mock markers and provider attribution. No Android source edit was necessary.
- The broader route/map/history/fuel regression suite passed fresh; this supports the existing requested/road endpoint distinction, date filtering, historical identity and frozen plate changes. It does not verify live Neshan, Android, fuel or UTCMS behavior.

## Executed verification

1. `.venv/bin/pytest tests/test_android_observer_identity.py tests/test_android_bridge_controller.py tests/test_android_anchor_gate.py tests/test_route_authority.py tests/test_gps_map_anchor_audit.py tests/test_faketraveler_waybill_coords.py tests/test_map_address_regressions.py tests/test_location_service_and_routes.py tests/test_audit_shipping_reporting_regressions.py tests/test_history_identity_contracts.py tests/test_history_date_filters.py tests/test_fuel_inquiry_reliability.py tests/test_automated_shipping_and_payload_repair.py -q --no-cov`
   - **253 passed in 14.17s**. Log: `/tmp/barpro-resume-20261007-shipping-tests.log`.
2. After the ambiguous-start fix: `.venv/bin/pytest tests/test_mobile_shipping_start_contract.py tests/test_otp_wakeup_and_lifecycle.py tests/test_automated_shipping_and_payload_repair.py -q --no-cov`
   - **72 passed in 17.89s**. Log: `/tmp/barpro-resume-20261007-shipping-start.log`.
3. Black on the four newly edited source/test files: **4 files left unchanged**. Ruff on the same files: **All checks passed!** `git diff --check`: exit 0.
4. `.venv/bin/mypy app/services/waybill_job_service.py app/automation/waybill_bot_multitenant.py --ignore-missing-imports`: **Success: no issues found in 2 source files**, exit 0.

## Remaining constraints and docs for root

- An ambiguous start now requires upstream reconciliation/operator review before further shipping mutation. This patch does not introduce a new automated shipping reconciliation workflow or claim successful live recovery. That is the safety tradeoff replacing fabricated ACK/sweepability.
- `docs/agent-reference/runtime-contracts.md` and older knowledge-graph snapshots describe the historical exception-to-`in_transit` policy. Root should add a dated current correction without rewriting historical claims. The current code path is `unknown` after ambiguity; manual shipping already used that boundary.
- Current HTTP shipping remains an active migration/operator path in the repository; no tests for active paths were blindly deleted. The obsolete positive behavior assertions were replaced while retaining ACK/refusal/migration safety coverage.
- Full backend suite, repository-wide mypy, security audit and release actions are root-owned. No blanket all-checks-pass or production-readiness claim is made here.

All four source/test files are stable for root verification.

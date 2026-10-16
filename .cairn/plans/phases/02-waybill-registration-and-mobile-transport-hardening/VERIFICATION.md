# Phase 2: waybill-registration-and-mobile-transport-hardening — Verification

**Date:** 2026-10-16
**Status:** VERIFIED
**Commit Range:** `ae52dab..0932c8e`
**Issues Covered:** #95, #96 (both closed on tracker with evidence)

---

## 1. Goal-Backward Verification

The objective of Phase 2 was to fix UtcmsMobileClient defects (pre-flight payload validation, session recovery, robust error handling) and waybill_jobs state-machine defects (stuck jobs, strict Two-Witness Proof).

### Goal Evaluation Against Promises:
1. **Mobile Transport Hardening (#95):**
   - **Observed defect:** batch-created jobs bypassed the mobile preflight the single-job path enforces — 4 live jobs (9–12, batch_id=1) passed creation and died at worker runtime (`USER_DATA_ERROR`, permanent NEEDS_REVIEW).
   - **Root causes found:** `build_job_payload` hardcoded `coordinates: None` and overwrote origin/destination (dropping base postal codes); `create_batch` ran only the browser-shape gate; the batch UI had no inputs for party codes/postals/fare (proven via git history: those inputs never existed).
   - **Remediations Implemented & Deployed:**
     - `app/services/batch_service.py`: GPS merge (`_route_coordinates` + `_merge_route_location`) + mobile gate in `create_batch` (422 fail-fast).
     - `apps/web/src/app/batches/page.tsx` + `apps/web/src/schemas/waybillSchema.ts`: 7 missing inputs with single-form-identical validation (shared checksum helper).
     - Deployed to barpro-central: volume-mounted backend files + frontend image rebuild; `readyz=200` all checks ok; gate introspected live (`gate_live=True`).
2. **State Transitions & Two-Witness Proof (#96):**
   - **Remediations verified live:** jobs 9–12 moved `needs_review → cancelled` exclusively through the audited `delete_job` path (4× HTTP 204, archived with reason, child audit rows preserved, intents settled, driver-4 slot `ready`, worker logs clean).
   - Guards holding in deployed code: 1-driver-1-waybill (`find_driver_active_job`), reconciliation self-healing, orphan→needs_review, `allow_live_submit` PermissionError gate.

## 2. Checks

- **Tests:** unit suite 250/250 green; related bundles (multiroute, mobile-contract, batch isolation, mobile bot) 94/94 green; `ruff`/`black`/`mypy` clean; frontend `tsc --noEmit` + `eslint` clean (exit 0).
- **Drift:** `plan_drift` clean — no `stale-audit`. Pre-run flags on 95/96 were `closed-unverified`, resolved by this verification.
- **Declared verification:** `plan_check(phase 2)` reports no `missing-verify`. One `missing-approaches` finding on the CONTEXT.md skeleton (plan-quality note, not a verify-failer).
- **Issues:** `issue_list(phase 2)` returns only #95 + #96, both `category: closed`.
- **TDD:** PLAN.md carries no `tdd:` frontmatter — vacuous pass.
- **Close evidence:** LEDGER.md holds one close line per issue, each with an `evidence <command> => <result>` segment; no evidence-only lines.

## 3. Deviations (judged, not auto-failed)

- PLAN.md is an 8-line skeleton (no tasks, no `verify:` declarations — predates the work). Ledger evidence cites concrete runs instead: live API cancels, readyz/gate introspection, pytest bundles with counts. Accepted: evidence is real and specific.
- CONTEXT.md `approaches-considered` block is empty (plan_check finding). Noted for plan hygiene; does not fail verification.
- Roadmap row for phase 2 read `not started`; repaired to `verified` per verb step 6b.
- Docs debt (report-only): `docs_drift` flags phase 1 (CHANGELOG predates its ledger) — for `/cairn:distill`, not this verification.

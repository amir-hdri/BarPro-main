---
status: resolved
issue: 101
created: 2026-10-16
resolved: 2026-10-16
---
# Trace: Waybills marked SUCCESS by the bot but never registered in the UTCMS portal (no tracking code) — suspected Two-Witness Proof bypass: success declared without tracking code in RPA response + DB

## evidence — 2026-10-16
DB screen (live, 2026-10-16): every SUCCESS row carries tracking + confirmed_by_history (jobs 5,6,7 in backup; job 8 live with reconciled_at). Zero success-without-proof rows. One tracking_received-without-confirmation case: job 2 (doc 236027523 / tracking 1359790419), reconciled_at NULL, last_error 'Reconciliation result ambiguous; marked for manual review', parked since Oct-11. Related live portal-truth gap found same day: job 13 got mobile_login+mobile_fleet_match success but portal business rejection code 4028 (origin-scope rule) — response-vs-truth divergence is real as a class. Job 13 cancelled via audited API (204, archived).

## hypothesis — 2026-10-16
No systemic false-success: every SUCCESS row in live + backup tables carries tracking_code + confirmed_by_history (verified by full-table screen). The real gap class is tracking_received-never-confirmed: job 2 got doc 236027523/tracking 1359790419 in the RPA response but portal History cannot confirm it (ambiguous Oct-11 and again today) — correctly parked in needs_review, never marked success. User-visible 'success' = document/tracking displayed while portal truth unconfirmed. Same family as live 4028 business rejection on job 13 (portal refuses with explicit codes).

## test — 2026-10-16
Repro/verification runs (all live, 2026-10-16): (1) SELECT status/count/has-tracking GROUP BY status + DISTINCT confirmation_status over live and backup tables => zero success-without-proof rows; sole tracking_received case is job 2. (2) POST /api/v1/admin/reconcile/2 (read-only History audit, twice incl. one wrong-path 404 first) => endpoint success:true but job 2 unchanged: needs_review/tracking_received/reconciled_at NULL, last_error still 'Reconciliation result ambiguous'. Observed failing output = unchanged ambiguous state.

## verdict — 2026-10-16
No code defect in success declaration — the Two-Witness rule holds everywhere verifiable; job 2 is correctly held (not falsely succeeded). Portal truth for doc 236027523/tracking 1359790419 is genuinely unconfirmable from our side (History ambiguous twice); only the operator looking directly in the portal UI can resolve it, then mark job 2 confirmed or dead per what the portal shows. Recommendation: operator checks the portal for that tracking code; meanwhile the re-issue path for current work (template 4, ملایر origin) is unaffected.

## resolution — 2026-10-16
No false-success bug exists: all SUCCESS rows carry tracking + History confirmation; the one unconfirmed case (job 2, doc 236027523) is correctly parked in needs_review per Two-Witness rules after two ambiguous History audits. Operator action: check tracking 1359790419 directly in the portal UI and mark job 2 accordingly. Separately fixed this session: scheduler self-match bypass (exclude_job_id) that let job 13 dispatch during job 8's unresolved trip; live 4028 origin-scope rule documented for future batches (use ملایر-origin templates for this driver).

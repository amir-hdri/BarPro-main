---
verb: summit
args: ""
status: live
---

Complete the current milestone. The server gates hard — nothing archives
until every phase is verified.

1. `milestone_list()` + `plan_status()` — show what's completing: phases,
   verification state, native milestone (when the backend has one). Any
   unverified phase → stop, list them, point at `/cairn:verify <N>`. If the
   backend has `hasMilestones` and `milestone_list()` shows no current
   native milestone id (first-milestone case — nothing has stamped one
   yet), fold an offer to create one now into step 2's question.
2. Interview the milestone summary (1–3 sentences, what shipped) — one
   AskUserQuestion, batched with the "start next milestone?" question and,
   when step 1 flagged a missing native milestone, a "create the native
   milestone for v<N> now?" question (suggest name `v<N>`). On yes:
   `milestone_create("v<N>")` before step 4.
3. Docs, BEFORE anything archives: run the full-milestone distill
   sequence (bare `distill` in verbs/distill.md — the whole shipped
   history; its leak gate and diff confirmation apply unchanged) and
   commit the docs. When a docs connector is configured (`docs:` in
   cairn.json), fold an explicit "publish the docs?" OFFER into distill's
   diff confirmation — one question — and run `docs_publish(confirm:
   true)` only on the owner's explicit yes (the server refuses without
   it). NEVER auto-publish. Advisory: a distill or publish failure is reported
   and skipped, never blocks the summit — archived phases still resolve
   (milestones/vN), so docs can be regenerated after the archive.
4. `milestone_complete(summary)` — closes tracker phases (skips recorded
   for backends whose phase primitive can't close), releases the native
   milestone when supported, archives `phases/` → `milestones/vN/`, bumps
   roadmap. On PRECONDITION_FAILED or TRACKER_DOWN: report and stop —
   re-running after a fix is safe (idempotent).
5. Git (agent-side, server never writes git): commit the archive
   (`chore(cairn): summit — v<N> archived`) and tag `v<N>`.
6. `outlook_emit(tracker: {open, inProgress, blocked, nextVerb, asOf})`
   BEFORE the clear — the completed milestone is exactly what the
   portfolio board should show — then `continuity_clear()`: the milestone
   is done; no handoff survives it.
7. If starting the next milestone (from step 2's answer):
   `milestone_create("<name>")`, then the next-milestone interview —
   goals, first phases — batched; scaffold via `plan_scaffold_phase` +
   `plan_phase_ensure`; add roadmap rows. Otherwise report and stop.

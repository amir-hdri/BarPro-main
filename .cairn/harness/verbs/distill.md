---
verb: distill
args: "[<N>]"
status: live
---

Ship-time knowledge synthesis (#3519) — run at/after `ship` or `summit`.
The output must read as if the repo never had planning scaffolding.
Bare `distill` synthesizes the whole shipped history; `distill <N>`
is incremental — scoped to what phase N alone changed.

1. Inputs:
   - Bare: shipped phases' CONTEXT.md locked decisions, PLAN.md
     outcomes, LEDGER.md summaries, decision/constraint cards in scope
     (`mem_card_list`).
   - Per-phase (`distill <N>`): call `distill_manifest` with the phase
     number (live or archived under milestones/vN). The manifest IS the
     scope: the phase's PLAN.md issues, its parsed ledger entries
     (taskRef, summary, per-task commit range, closed date), and the
     union commit range those entries span. Synthesize from ONLY those
     entries plus that phase's CONTEXT.md locked decisions and cards —
     read `git diff <base>..<head>` over the union range for what
     structurally changed; nothing outside it. Surface any `skipped`
     malformed-line notes to the user instead of guessing at them.
2. Generate into `docs/`:
   - ARCHITECTURE.md — per-section merge for what structurally changed.
     Write through the marked-section writer
     (`server/dist/docs/sections.js`, API `writeSectionFile(path,
     heading, body)` → `{path, changed}`; `createSection` via
     `createMissing: true` for new sections): it rewrites ONLY the
     region under a section's `<!-- docs: -->` marker and is a zero-diff
     no-op on identical bodies. An unmarked section fails with
     PRECONDITION_FAILED — that is hand-written prose; surface the
     conflict to the user, NEVER clobber it.
   - docs/adr/NNNN-<slug>.md — one ADR per locked decision that shaped
     code (next free NNNN; context/decision/consequences; reference
     commits, not phase dirs). Per-phase mode: only THAT phase's locked
     decisions — existing ADRs stay untouched. Every new ADR carries a
     `removeWhen:` line under its status line: the capability or
     platform condition that would make the decision unnecessary, or
     `never — <why>`. ARCHITECTURE.md carries each ADR's `removeWhen:`
     beside the component it describes, so the sunset condition survives
     into the public picture.
   - CHANGELOG.md — prepend-only, no markers. Entries from ledger
     summaries grouped by milestone or phase, newest first; per-phase
     mode prepends one block covering just that phase's ledger entries.
3. Sanitize BEFORE writing: run
   `node <plugin>/hooks/scripts/leak-patterns.mjs <each generated file>`
   (write to a temp path first). Any hit → rewrite that line to
   public-safe form: tracker ids → plain prose ("the issue tracker"),
   phase/dir refs → the milestone or version name, `.cairn/` paths →
   remove. Re-scan until clean — the scanner exiting 0 is the gate.
4. Show the diff summary (files, sections touched, ADR titles) — ONE
   confirmation — then write and offer a `docs(distill): …` commit.
5. When a docs connector is configured (`docs:` in cairn.json), offer
   `/cairn:docs publish` as the follow-up — distill synthesizes into
   `docs/`; docs publish mirrors it (plus the README) into the connector
   as a landing page + page tree.

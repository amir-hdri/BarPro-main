# BarPro agent reference index

Scope: **this repository only**. The always-loaded entry point is
[AGENTS.md](../../AGENTS.md); the general agent policy remains global.
Read a reference only when it matches the current task. These ordinary links do
not inline the directory into the core rule. Do not install these files globally.

## Topic references

- [Architecture, stack and repository layout](architecture.md) — Architecture, dependency or file-layout work.
- [Deployment, configuration and resources](deployment-and-resources.md) — Deployment, infrastructure, environment configuration, Android hosting or resource work.
- [Runtime contracts recorded in the original guide](runtime-contracts.md) — API, submission, reconciliation, queues, schema, OTP, CAPTCHA or shipping changes.
- [Known pitfalls and CAPTCHA chain](pitfalls-and-captcha.md) — Related debugging, dependency compatibility or CAPTCHA work.

## Historical records

Old operational commands, “remaining actions” and dated success claims are
historical data. They require current evidence and authorization before use.
The original ordering and wording are retained, including any old conflicts.

- [optimization-history-01.md](optimization-history-01.md) — original lines 495–555.
  Covers: 2026-09-14 — GPS Shipping Session Vault & WAF Evasion Hardening (v2.9.12); 2026-09-13 — Deep WAF Evasion & Mobile TLS Hardening (v2.9.11); 2026-09-06 — UTCMS End-to-End Submission & OTP Lifecycle Hardening (v2.9.10); 2026-08-27 — Session-Aware 408 and Shared Clean Pool Hardening (v2.9.8); 2026-08-26 — Clean IP Pool Pipeline Overhaul (v2.9.7); 2026-08-24 — Dependabot Version Updates Disabled.
- [optimization-history-02.md](optimization-history-02.md) — original lines 556–615.
  Covers: 2026-08-24 — v2.9.6 Full Audit Remediation (Duplicate-Registration Class, Firewall, Nginx, URL-Classification Bug Sweep); 2026-08-24 — v2.9.5 Security Hardening, Lock-Token Durability & Full-Stack Consistency Remediation; 2026-08-23 — v2.9.4 Error Taxonomy Sync, State Machine Auto-Heal & Full-Stack UI Batch Integration; 2026-08-23 — v2.9.3 Multi-Route Waybill Registration (Route Templates, Batches & Distance/Time).
- [optimization-history-03.md](optimization-history-03.md) — original lines 616–706.
  Covers: 2026-08-22 — v2.9.3 Auth Session Cookie Synchronization, Fast 408 Outage Detection & Taxonomy Resilience; 2026-08-20 — v2.9.2 Universal Mobile Anti-Zoom, UI/UX Hardening & Full-Stack Taxonomy Sync; 2026-08-20 — v2.9.1 Driver Fleet Vehicle Type Sync & Multi-Tenant Plate Safeguards; 2026-08-19 — v2.9.0 Clean Iranian Proxy Pool (Zero IP Restriction); 2026-08-19 — v2.8.3 Waybill Payload Validation & Vehicle Type Integration; 2026-08-19 — v2.8.2 Fuel Quota Performance & Modal Screenshot Persistence; 2026-08-19 — v2.8.1 Fuel Inquiry Tracking & Waybill UX Polish; 2026-08-16 — v2.8.0 UTCMS RPA Hardening & Mutation Safety; 2026-08-13 — v2.7.0 Authentication & Network Layer.
- [optimization-history-04.md](optimization-history-04.md) — original lines 707–752.
  Covers: 2026-06-30 — Performance; Memory / Stability; Database; Index Recommendations (run on PostgreSQL).
- [remediation-history-01.md](remediation-history-01.md) — original lines 778–932.
  Covers: Repository fixes and follow-ups; ✅ Optimizations Applied; Remaining Runtime Actions; Additional Fixes Applied (2026-07-08); Additional Fixes Applied (2026-07-01); Additional Fixes & Features Applied (2026-07-09); Additional Fixes Applied (2026-07-10) — Performance Bottleneck Remediation; Additional Fixes Applied (2026-07-18) — Waybill/Fuel Reliability & Security; Additional Fixes Applied (2026-08-02) — Documentation & Final Hardening; Additional Fixes Applied (2026-07-21) — Worker Proxy, Rotator & Event Loop Reliability; Additional Fixes Applied (2026-07-21) — RPA Services, RPA Dispatch & Scheduler Reliability.
- [remediation-history-02.md](remediation-history-02.md) — original lines 933–1019.
  Covers: Additional Fixes Applied (2026-07-21) — Smart Locators, Form Validation & Browser/Session Optimization; Additional Fixes Applied (2026-07-21) — Retry, Queue/Scheduler & Connection/Timeout Optimization; Additional Fixes & Features Applied (2026-07-21) — Map, Location & Origin/Destination Registration System; Additional Fixes Applied (2026-07-27) — Security Hardening & Test Quality; Additional Fixes Applied (2026-08-02) — 14-Item Code Audit Remediation (C4/C5/C6, H1–H6, F1–F4).
- [remediation-history-03.md](remediation-history-03.md) — original lines 1020–1084.
  Covers: Additional Fixes Applied (2026-08-04) — Server 16GB RAM Upgrade, Beat OOM Fix & Deployment Automation; Additional Fixes Applied (2026-08-08) — Soft-Cancel Intent Sync, Proxy Fail-Closed, Scheduler Enforcement & CI Fixes; Additional Fixes Applied (2026-08-10) — UTCMS Proxy Health Check & Scheduler FOR UPDATE Fix.

## Preservation and maintenance

Split on 2026-10-06 from the 113,437-byte, 1,084-line root guide. No original
source block was omitted or rewritten. [migration-manifest.json](migration-manifest.json)
maps every original line exactly once to marked blocks and records SHA-256 hashes.
Reordering those blocks by their original line span reconstructs the original file
byte-for-byte. The manifest is a migration snapshot, not a ban on future edits;
intentional later changes must be recorded in the changelog and knowledge document.

All Markdown files in this directory and the core are below 24,000 bytes at
migration time. Keep the core concise and split growing references at topic
boundaries. Preserve the global/project scope boundary and avoid automatic imports.

The canonical current knowledge document remains
[BARPRO_KNOWLEDGE_GRAPH.md](../BARPRO_KNOWLEDGE_GRAPH.md), read by relevant section
with its evidence labels. [CRITICAL_RULES.md](../../CRITICAL_RULES.md) and the
linked UTCMS contracts retain their original authority; no runtime safety gate
was changed by this documentation move.

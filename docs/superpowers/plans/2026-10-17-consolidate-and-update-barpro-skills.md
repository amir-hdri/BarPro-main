# Consolidate and Modernize BarPro Domain Skills Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Consolidate BarPro's 20 fragmented, overlapping domain skills in `.agents/skills/` into 7 authoritative, modern, and precise skills, incorporating the latest production architectural contracts (Mobile API transport primacy, external waybill adoption Jalali invariants, Next.js standalone container build protocol, and two-witness proof).

**Architecture:** Merge redundant and fragmented skill directories into cohesive functional domains: (1) Infrastructure & Deployment (`barpro-deploy-ops`), (2) RPA, Automation & Shipping Lifecycle (`barpro-rpa-ops`), (3) Full-Stack & UI/UX (`barpro-fullstack-sync`), (4) Database & Disaster Recovery (`barpro-database-ops`), (5) Background Queues (`barpro-celery-ops`), (6) Observability & Load Testing (`barpro-monitoring-alerting`), and (7) Multi-Tenancy (`barpro-tenant-onboard`). Archive obsolete historical roadmaps (`barpro-master-upgrade`) to docs references. Consolidate Python helper CLI scripts within each merged skill and update project documentation (`AGENTS.md`, `docs/BARPRO_KNOWLEDGE_GRAPH.md`).

**Tech Stack:** Markdown (`SKILL.md`), Python 3.12 (CLI scripts in `scripts/`), Docker Compose, PostgreSQL 16, Redis 7, Next.js 15, FastAPI, Celery 5.

**Spec:** Direct user request to merge related skills and update/sharpen them with verified production lessons learned.

## Global Constraints

- Preserve all verified CLI functionality and validation logic from merged scripts.
- Every merged skill MUST have valid YAML frontmatter (`name`, `description`).
- Eliminate retired/obsolete claims (e.g. browser form submission for waybill issuance is retired; cellular 4G/Tailscale proxy does not exist).
- Codify latest production contracts: Mobile API transport primacy, Two-Witness Proof, Jalali multi-format parsing, 2-hour cross-midnight adoption window, zero timestamp poisoning, and Next.js standalone build requirements.
- Maintain atomic git commits per task and keep test coverage clean.

---

### Task 1: Consolidate Infrastructure, Networking, Security & Deployment (`barpro-deploy-ops`)

**Files:**
- Modify: `.agents/skills/barpro-deploy-ops/SKILL.md`
- Modify: `.agents/skills/barpro-deploy-ops/scripts/deploy_cli.py`
- Delete: `.agents/skills/barpro-server-setup/`
- Delete: `.agents/skills/security-firewall/`
- Delete: `.agents/skills/proxy-ops/`
- Delete: `.agents/skills/ssl-https/`
- Delete: `.agents/skills/docker-build/`

**Interfaces:**
- Produces: Unified `barpro-deploy-ops` covering Model B topology, container memory budgets (~20 GB / 12 GB OS headroom), UFW firewall rules, Squid proxy egress (port 3128, IR IP validation), Docker multi-stage builds, Next.js standalone rebuild protocol, safe server git sync, and deployment verification.

- [ ] **Step 1: Expand `deploy_cli.py` to absorb merged CLI commands**
Integrate checks from `setup_cli.py`, `security_cli.py`, `proxy_cli.py`, `ssl_cli.py`, and `docker_cli.py` into `.agents/skills/barpro-deploy-ops/scripts/deploy_cli.py`:
  - `check-firewall`: verify UFW rules for PostgreSQL, Redis, SSH, and Squid.
  - `check-proxy`: test Squid port 3128 and egress IP nationality (`IR`).
  - `check-ssl`: verify Let's Encrypt certificate expiry or HTTP port 80 status.
  - `check-docker`: inspect multi-stage Dockerfile and container memory limits.

- [ ] **Step 2: Test `deploy_cli.py` commands**
Run: `python3 .agents/skills/barpro-deploy-ops/scripts/deploy_cli.py --help`
Verify all subcommands are available and executable.

- [ ] **Step 3: Update `.agents/skills/barpro-deploy-ops/SKILL.md`**
Rewrite `SKILL.md` to unify:
  - Model B Topology (Central Server + 2 Remote Worker VPS nodes).
  - Container RAM allocation & audit (~20 GB budget with 12 GB host headroom).
  - Network & Firewall Security (UFW allowlists, Squid 3128 port binding, IR egress verification).
  - Docker Multi-Stage Builds & Next.js Standalone Container Rebuild Protocol.
  - Safe Production Git Sync Protocol (tarball backup + temporary branch isolation before `git pull`).
  - Pre-deploy and post-deploy verification commands (`manage.sh`).

- [ ] **Step 4: Remove redundant skill directories**
Delete:
  - `.agents/skills/barpro-server-setup/`
  - `.agents/skills/security-firewall/`
  - `.agents/skills/proxy-ops/`
  - `.agents/skills/ssl-https/`
  - `.agents/skills/docker-build/`

- [ ] **Step 5: Verify and Commit**
Run: `python3 .agents/skills/barpro-deploy-ops/scripts/deploy_cli.py audit-codebase`
Commit: `git commit -m "refactor(skills): consolidate infrastructure, security, proxy, and deployment into barpro-deploy-ops"`

---

### Task 2: Consolidate RPA, Automation, Shipping Lifecycle & OCR (`barpro-rpa-ops`)

**Files:**
- Modify: `.agents/skills/barpro-rpa-ops/SKILL.md`
- Modify: `.agents/skills/barpro-rpa-ops/scripts/rpa_cli.py`
- Delete: `.agents/skills/barpro-waybill-submission-safety/`
- Delete: `.agents/skills/browser-lifecycle/`
- Delete: `.agents/skills/captcha-retrain/`
- Delete: `.agents/skills/barpro-fuel-inquiry/`

**Interfaces:**
- Produces: Authoritative `barpro-rpa-ops` covering Mobile API transport (`UtcmsMobileClient`), Two-Witness Proof, Virtual Android GPS shipping lifecycle (`Redroid` + `FakeTraveler`), External Waybill Adoption & Jalali date invariants, PyTorch CNN/CRNN CAPTCHA engines, Fuel Quota inquiry OCR, and legacy browser fallback.

- [ ] **Step 1: Expand `rpa_cli.py` to absorb merged CLI commands**
Integrate checks from `browser_cli.py`, `captcha_cli.py`, and `fuel_cli.py` into `.agents/skills/barpro-rpa-ops/scripts/rpa_cli.py`:
  - `check-captcha-models`: verify presence and integrity of PyTorch CNN (login) and CRNN (fuel) models.
  - `verify-two-witness`: validate that a waybill meets Two-Witness proof (RPA tracking code + DB record).
  - `check-adoption-date`: validate Jalali date parsing and cross-midnight window logic.
  - `check-fuel-ocr`: verify fuel quota parser fallback chain.

- [ ] **Step 2: Test `rpa_cli.py` commands**
Run: `python3 .agents/skills/barpro-rpa-ops/scripts/rpa_cli.py --help`
Verify all subcommands execute cleanly.

- [ ] **Step 3: Update `.agents/skills/barpro-rpa-ops/SKILL.md`**
Rewrite `SKILL.md` with:
  - Mobile API Transport Primacy: Explicit declaration that browser form submission is RETIRED for issuance.
  - Two-Witness Proof: Strict rule that waybill registration requires (1) non-empty tracking code in RPA response and (2) identical tracking code in `waybill_jobs.result_json`.
  - Virtual Android GPS Lifecycle: Server-side Redroid container + FakeTraveler + AndroidShippingController.
  - External Waybill Adoption & Jalali Invariants: Tehran Jalali date filter, 2-hour sliding grace window across midnight, multi-format parsing (Persian/Arabic digits, unpadded dates, embedded timestamps), zero timestamp poisoning, and full-stack driver name resolution.
  - CAPTCHA Solver Hierarchy: PyTorch CNN login solver, PyTorch CRNN fuel solver, Keras OCR, and local OCR fallback.
  - Legacy Browser Lifecycle: Playwright browser recycling strictly labeled as fallback/test fixture.

- [ ] **Step 4: Remove redundant skill directories**
Delete:
  - `.agents/skills/barpro-waybill-submission-safety/`
  - `.agents/skills/browser-lifecycle/`
  - `.agents/skills/captcha-retrain/`
  - `.agents/skills/barpro-fuel-inquiry/`

- [ ] **Step 5: Verify and Commit**
Run: `python3 .agents/skills/barpro-rpa-ops/scripts/rpa_cli.py check-captcha-models`
Commit: `git commit -m "refactor(skills): consolidate rpa, shipping lifecycle, adoption, and captcha into barpro-rpa-ops"`

---

### Task 3: Consolidate Full-Stack & UI/UX Guard (`barpro-fullstack-sync`)

**Files:**
- Modify: `.agents/skills/barpro-fullstack-sync/SKILL.md`
- Modify: `.agents/skills/barpro-fullstack-sync/scripts/fullstack_cli.py`
- Delete: `.agents/skills/barpro-ui-ux-guard/`

**Interfaces:**
- Produces: Unified `barpro-fullstack-sync` covering Next.js 15 App Router ↔ FastAPI alignment, Zod v3 ↔ Pydantic v2 schemas, httpOnly cookie JWT auth, strict Persian RTL typography, Tailwind CSS design system, Heroicons v2, friendly Persian validation errors, and AbortController unmount safety.

- [ ] **Step 1: Expand `fullstack_cli.py` to absorb UI/UX guard checks**
Integrate checks from `ui_ux_cli.py` into `.agents/skills/barpro-fullstack-sync/scripts/fullstack_cli.py`:
  - `check-typography`: scan for hardcoded English digits in user-facing Persian text or missing RTL containers.
  - `check-zod-imports`: verify strict `zod@3` imports (flag any `zod/v4`).
  - `check-auth-cookies`: verify `AUTH_COOKIE_SECURE=false` alignment and httpOnly cookie transport.

- [ ] **Step 2: Test `fullstack_cli.py` commands**
Run: `python3 .agents/skills/barpro-fullstack-sync/scripts/fullstack_cli.py --help`
Verify all subcommands execute cleanly.

- [ ] **Step 3: Update `.agents/skills/barpro-fullstack-sync/SKILL.md`**
Rewrite `SKILL.md` to incorporate:
  - Zod v3 ↔ Pydantic v2 Schema Alignment and Persian validation messages.
  - JWT Authentication: httpOnly cookie `utcms_auth_token`, `withCredentials: true`, edge middleware redirect.
  - Strict Persian RTL Typography & Formatting: IRANSans font stack, circular badges for numbers, ASCII digits (`0-9`), and LTR-isolated code/badge tokens.
  - Next.js 15 App Router Best Practices: AbortController pattern for unmount-safe data fetching, Tailwind CSS logical properties, Heroicons v2.
  - Frontend Driver Name Fallback Hierarchy: `job.driver_name` → `راننده #X` → `عملیات ثبت بارنامه`.

- [ ] **Step 4: Remove redundant skill directory**
Delete:
  - `.agents/skills/barpro-ui-ux-guard/`

- [ ] **Step 5: Verify and Commit**
Run: `python3 .agents/skills/barpro-fullstack-sync/scripts/fullstack_cli.py check-zod-imports`
Commit: `git commit -m "refactor(skills): consolidate fullstack sync and ui-ux guard into barpro-fullstack-sync"`

---

### Task 4: Consolidate Database & Disaster Recovery (`barpro-database-ops`)

**Files:**
- Modify: `.agents/skills/database-ops/SKILL.md`
- Modify: `.agents/skills/database-ops/scripts/db_cli.py`
- Delete: `.agents/skills/disaster-recovery/`

**Interfaces:**
- Produces: Comprehensive `barpro-database-ops` covering PostgreSQL 16 schema integrity, Alembic migrations with PostgreSQL advisory locks, sequence repair, automated pg_dump snapshot verification, restore testing, and Redis persistence (RDB/AOF).

- [ ] **Step 1: Expand `db_cli.py` to absorb disaster recovery checks**
Integrate checks from `dr_cli.py` into `.agents/skills/database-ops/scripts/db_cli.py`:
  - `verify-backup`: test validity and schema integrity of recent `.dump` files.
  - `check-redis-persistence`: verify Redis RDB and AOF configuration.
  - `check-advisory-lock`: ensure Alembic migrations acquire PostgreSQL advisory lock (`SELECT pg_advisory_lock(847291)`).

- [ ] **Step 2: Test `db_cli.py` commands**
Run: `python3 .agents/skills/database-ops/scripts/db_cli.py --help`
Verify all subcommands execute cleanly.

- [ ] **Step 3: Update `.agents/skills/database-ops/SKILL.md`**
Rewrite `SKILL.md` to include:
  - PostgreSQL 16 Operations: async session factory, connection pooling, and sequence repair.
  - Safe Alembic Migrations: advisory locks, non-blocking DDL, and zero downtime patterns.
  - Snapshot & Backup Automation: pg_dump scripts, snapshot retention, and offsite sync.
  - Disaster Recovery Runbook: step-by-step restoration drill and Redis cache rebuild.

- [ ] **Step 4: Remove redundant skill directory**
Delete:
  - `.agents/skills/disaster-recovery/`

- [ ] **Step 5: Verify and Commit**
Run: `python3 .agents/skills/database-ops/scripts/db_cli.py check-advisory-lock`
Commit: `git commit -m "refactor(skills): consolidate database operations and disaster recovery into barpro-database-ops"`

---

### Task 5: Consolidate Observability, Alerting & Load Profiling (`barpro-monitoring-alerting`)

**Files:**
- Modify: `.agents/skills/monitoring-alerting/SKILL.md`
- Modify: `.agents/skills/monitoring-alerting/scripts/monitor_cli.py`
- Delete: `.agents/skills/load-testing/`

**Interfaces:**
- Produces: Unified `barpro-monitoring-alerting` covering Prometheus, Grafana, Alertmanager, Nginx / Redis / Postgres exporters, alert rule tuning, and Locust load testing / stress profiling.

- [ ] **Step 1: Expand `monitor_cli.py` to absorb load testing helpers**
Integrate helpers from `load_cli.py` into `.agents/skills/monitoring-alerting/scripts/monitor_cli.py`:
  - `check-exporters`: probe `/metrics` endpoints across node, nginx, postgres, and redis exporters.
  - `run-load-baseline`: run headless Locust benchmark scenario against target API.

- [ ] **Step 2: Test `monitor_cli.py` commands**
Run: `python3 .agents/skills/monitoring-alerting/scripts/monitor_cli.py --help`
Verify all subcommands execute cleanly.

- [ ] **Step 3: Update `.agents/skills/monitoring-alerting/SKILL.md`**
Rewrite `SKILL.md` to include:
  - Prometheus + Grafana stack setup, port isolation, and retention policies.
  - Exporter fleet verification (node, redis, postgres, nginx).
  - Alertmanager routing rules and notification channels.
  - Performance baselines, Locust stress test profiles, and resource threshold monitoring.

- [ ] **Step 4: Remove redundant skill directory**
Delete:
  - `.agents/skills/load-testing/`

- [ ] **Step 5: Verify and Commit**
Run: `python3 .agents/skills/monitoring-alerting/scripts/monitor_cli.py check-exporters`
Commit: `git commit -m "refactor(skills): consolidate monitoring, alerting, and load testing into barpro-monitoring-alerting"`

---

### Task 6: Streamline Tenant Lifecycle & Archive Master Upgrade (`barpro-tenant-onboard`)

**Files:**
- Modify: `.agents/skills/tenant-onboard/SKILL.md`
- Move/Archive: `.agents/skills/barpro-master-upgrade/` → `docs/agent-reference/historical-master-upgrade.md`

**Interfaces:**
- Produces: Sharp `barpro-tenant-onboard` focusing on multi-tenant onboarding, driver setup, encryption, and forwarder pairing.
- Archives historical upgrade log to prevent outdated rules from cluttering active agent skills.

- [ ] **Step 1: Update `.agents/skills/tenant-onboard/SKILL.md`**
Update `SKILL.md` with:
  - Multi-tenant client onboarding flow.
  - Driver account provisioning and AES password encryption (`decrypt_driver_password`).
  - SMS Forwarder Android app binding and webhook token assignment.
  - Tenant quota enforcement and daily reset lifecycle.

- [ ] **Step 2: Archive `barpro-master-upgrade`**
Move historical content from `.agents/skills/barpro-master-upgrade/SKILL.md` into `docs/agent-reference/historical-master-upgrade.md`.
Delete `.agents/skills/barpro-master-upgrade/`.

- [ ] **Step 3: Verify and Commit**
Run: `python3 .agents/skills/tenant-onboard/scripts/tenant_cli.py --help`
Commit: `git commit -m "refactor(skills): streamline tenant-onboard and archive historical master upgrade"`

---

### Task 7: Update Documentation, Repository Guides & Verify All Skills

**Files:**
- Modify: `AGENTS.md`
- Modify: `docs/BARPRO_KNOWLEDGE_GRAPH.md`
- Modify: `.context/STATE.md`

**Interfaces:**
- Produces: Updated documentation referencing the streamlined 7 BarPro domain skills.

- [ ] **Step 1: Update `AGENTS.md` skill roster**
Update the skills list in `AGENTS.md` section 3 to reflect the 7 consolidated skills:
  - `barpro-deploy-ops`
  - `barpro-rpa-ops`
  - `barpro-fullstack-sync`
  - `barpro-database-ops`
  - `barpro-celery-ops`
  - `barpro-monitoring-alerting`
  - `barpro-tenant-onboard`

- [ ] **Step 2: Update `docs/BARPRO_KNOWLEDGE_GRAPH.md`**
Update the skills inventory and node links in the canonical knowledge graph.

- [ ] **Step 3: Run comprehensive verification across all 7 skills**
Execute a verification script testing that all 7 skills:
  1. Have valid frontmatter in `SKILL.md`.
  2. Have executable CLI scripts in `scripts/` with 0 syntax or import errors.
  3. Comply with project code conventions (Ruff clean).
Run: `uvx ruff check .agents/skills/`

- [ ] **Step 4: Update `.context/STATE.md` and commit**
Update `.context/STATE.md` with the 5-point session status.
Commit: `git commit -m "docs: update AGENTS.md and knowledge graph for consolidated 7 domain skills"`

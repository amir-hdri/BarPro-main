# Historical Master Roadmap Upgrade (Archived Reference)

> **Status**: Historical Reference / Archived Snapshot.
> **Original Location**: `.agents/skills/barpro-master-upgrade/SKILL.md`
> **Replaced By**: Consolidated domain skills in `.agents/skills/` (`barpro-deploy-ops`, `barpro-rpa-ops`, `barpro-database-ops`, `barpro-celery-ops`, `barpro-monitoring-alerting`, `barpro-fullstack-sync`, `barpro-tenant-onboard`).

## Overview
This document preserves the historical architectural upgrade record (the "Unified Master Roadmap") for BarPro. It tracked linear milestones across orchestrator, dispatcher, state machine, worker registry, error taxonomy, reconciliation, submission gate, CAPTCHA hardening, Model B scale-out, RAM upgrades, and multi-server deployment.

The production topology is **Model B scale-out**:
- Central server: 32 GB RAM, 8 vCPUs, single public IP `<CENTRAL_IP>`.
- 2 Remote Worker VPS nodes: each ~6 GB RAM, dedicated static Iranian IP, running a local Squid proxy on port 3128.

---

## 🚨 Historical Core Technical Standards

### 1. State Machine & Dispatcher
- All `waybilljob` status transitions MUST go through `JobStateMachine.transition(...)` in `app/orchestrator/state_machine.py`.
- Fuel inquiries use `set_fuel_inquiry_status(...)`; atomic claim performs `pending` to `processing` in one guarded SQL UPDATE.
- Direct waybill status string writes are banned — dispatcher and worker apply canonical transitions.

### 2. Shared Session Vault (Redis)
- Driver login session state is shared across Workers via Redis (`barpro:auth_state:*`).
- Local file fallback is banned across workers.

### 3. Worker Registry & Networking (Model B)
- Worker registry persistence in `app/models_rpa.py` (`WorkerRegistry`) with lifecycle logic in `app/orchestrator/worker_lifecycle.py`.
- Hooked into Celery initialization (`worker_process_init` in `app/workers/celery_app.py`) ONCE per startup.
- Scale-out networking uses **UFW Firewall + Fixed IPs**.
- `scripts/setup_firewall_central.sh` — allowlist 5432/6379 on Central from registered Worker IPs only.
- `scripts/add_worker_firewall.sh` — register a new Worker VPS IP.
- Remote Squid on port 3128 with Iranian egress validation.

### 4. Database Migrations & Session-Level Advisory Lock
- Migrations run sequentially under a PostgreSQL session-level advisory lock in `app/core/database.py:run_migrations` (`MIGRATION_ADVISORY_LOCK_ID = 0x42415250524F`).
- Migration `027`: widened `alembic_version.version_num` to `VARCHAR(255)`.
- Migration `029`: executes `COMMIT` before `CREATE INDEX CONCURRENTLY IF NOT EXISTS`.

### 5. Submit Idempotency & Mutation Safety
- Global canonical idempotency (`app/core/submission_identity.py`): deterministic digest without volatile correlation IDs.
- Two-Witness Proof: non-empty tracking code in RPA response + identical code in `waybill_jobs.result_json`.
- Batched History confirmation via `orchestrator.reconciliation.audit_tracking_received`.

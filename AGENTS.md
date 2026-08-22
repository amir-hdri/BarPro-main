# BarPro — Agent Guide

> **📋 See also: [CRITICAL_RULES.md](./CRITICAL_RULES.md)** — خطوط قرمز و الزامات فنی حیاتی پروژه
>
> **UTCMS live contract:** [docs/UTCMS_CONSTRAINTS.md](./docs/UTCMS_CONSTRAINTS.md) — فیلدهای اجباری، WAF/IP، CAPTCHA، زمان‌بندی و معیار اثبات ثبت
>
> **Canonical tracked knowledge graph:** [docs/BARPRO_KNOWLEDGE_GRAPH.md](./docs/BARPRO_KNOWLEDGE_GRAPH.md) — API, schema, queues, RPA, deployment, evidence labels

## Project Identity

**BarPro** is a multi-tenant RPA (Robotic Process Automation) framework for automated waybill (بارنامه) registration on Iran's national transportation portal (barname.utcms.ir). It uses Playwright-driven browser automation with CAPTCHA solving (CNN/PyTorch fuel CRNN/Keras OCR), smart proxy rotation (Squid), and human-behavior simulation.

## Architecture Overview

```
Client Browser → Nginx (port 80; 443 only after TLS activation) → FastAPI Backend (port 8000)
                                                    ├── PostgreSQL 16 (SQLModel/AsyncPG)
                                                    ├── Redis 7 (cache/queue/pub-sub)
                                                    ├── Celery Workers ×3 (via Squid proxies)
                                                    │   ├── Worker 1 (central, always-on)
                                                    │   ├── Worker 2 (remote node, profile scale-out)
                                                    │   └── Worker 3 (remote node, profile scale-out)
                                                    ├── Celery Scheduler (profile-less, rpa_scheduler queue)
                                                    └── Monitoring (Prometheus, Alertmanager, Grafana, exporters)
Frontend: Next.js 15 (TypeScript, Tailwind, React 19)
```

- **Single-server deployment (Model A)**: All containers run on one server with 2 public IPs + 3 local Squid proxies
- **Multi-server deployment (Model B — production target/current documented topology)**:
  Central runs API + Worker 1 + Scheduler + Beat + Squid 1; Workers 2/3 run on
  remote VPS nodes. Live state still requires timestamped verification.
- **Layered Docker services** managed via docker-compose files (`compose/`); the exact
  live container count is topology-dependent and must be verified with full `docker ps`
- **Root `docker-compose.yml`** uses `include:` (Compose >= 2.20) to assemble all layers — CI/CD and deploy scripts MUST use `docker compose` V2 (not `docker-compose` V1)
- **Nginx**: Configured with security headers (CSP, X-Frame-Options, X-Content-Type-Options, Permissions-Policy)

## Server Specifications

| Role | vCPU | RAM |
|------|------|-----|
| Central Server — UFW Firewall + Nginx (port 80), Backend, Frontend, Squid 1 egress | 4 | 16 GB |
| Worker Nodes — Remote VPS with static Iranian IP + local Squid proxy | — | ~6 GB each |

Core platform containers run on the **central server**. In Model B, Workers 2/3 and
their local Squids run on remote VPS nodes and are not part of the central host's
resource budget.

### Resource Constraints & Implications
- **16 GB RAM** on central server — Workers 2/3 are on remote nodes (Model B), not counted in central budget
- Celery Worker 1 limited to 3 GB; celery_scheduler 768 MB; Beat 256 MB
- Current Model B Central Compose limits total approximately 9 GB, leaving about
  7 GB for host overhead and headroom; live RSS still requires `docker stats`
- **4 vCPUs** means CPU contention under load — Worker 1 + DB can saturate cores
- Disk: ensure <90% utilization

## Tech Stack

| Layer | Technology | Version |
|-------|-----------|---------|
| Backend | Python / FastAPI | 3.11 / latest |
| Frontend | Next.js / TypeScript | 15 / 5.x |
| Database | PostgreSQL + SQLModel | 16 |
| Queue | Celery + Redis | latest |
| RPA | Playwright (Chromium) | latest |
| Proxy | Squid | latest (ubuntu/squid:latest) |
| Monitoring | Prometheus + Alertmanager + Grafana + exporters | pinned in `compose/monitoring.yml` |
| Reverse Proxy | Nginx | 1.27-alpine |

## Code Conventions

### Python
- **Formatter**: Black (line-length 120)
- **Imports**: isort with black profile
- **Linting**: Ruff (select: E, W, F, I, B, C4, UP)
- **Type checking**: mypy (strict mode, partial)
- **Testing**: pytest with async mode auto, coverage (HTML/XML/term)
- **Patterns**: Async/Await throughout, SQLModel for ORM, Pydantic v2 for schemas

### TypeScript / React
- **Framework**: Next.js 15 (App Router, React 19)
- **Forms**: React Hook Form + Zod
- **Data fetching**: React Query + Axios
- **Styling**: Tailwind CSS + Heroicons
- **State**: JWT is transported by httpOnly cookie; localStorage stores only non-sensitive client/session metadata
- **Cookie security**: keep `AUTH_COOKIE_SECURE=false` on current HTTP deployment; set `true` after HTTPS is enabled

## Critical Warnings

1. **NEVER hardcode credentials** — the repo already has leaked production SSH passwords (`PLACEHOLDER_SSH_PASSWORD`) committed in multiple files
2. **NEVER commit `.env`** — currently tracked in git history; use `.env.example` as template
3. **`.env` IS in `.gitignore`** but was committed before being added — do NOT commit new secrets
4. **Frontend Docker no longer requires prebuilt `.next/standalone`** — `apps/web/Dockerfile` builds inside Docker
5. **Do not re-add `privileged: true`** — containers use `cap_add` + `no-new-privileges`
6. **No HTTPS** — Nginx listens on port 80 only; all traffic is plaintext
7. **Rate limiter is fail-closed** — preserve HTTP 429 behavior if Redis is unavailable
8. **Proxy URL validation exists** — do not weaken `_is_safe_proxy_url`
9. **Health responses must not expose credentials** — public `/readyz` is sanitized;
   detailed readiness is admin-only at `/api/v1/admin/readyz`
10. **Compose is not firewall evidence** — verify UFW/provider firewall and
    `DOCKER-USER` from a non-worker IP after every deployment

## Deployment Topology

> **Deployment target (Model B — scale-out):** the central server has a **single public IP**.
> Multi-IP egress is provided by **remote Worker VPSes**, each with its own
> static Iranian IP and a local Squid proxy. Postgres/Redis bind `0.0.0.0` on the central
> server (`POSTGRES_BIND`/`REDIS_BIND` in `.env`) and **must be protected** by UFW,
> provider firewall, and `DOCKER-USER`
> (`scripts/setup_firewall_central.sh`, `scripts/add_worker_firewall.sh`).
> Workers 2/3 run on the remote nodes via `compose/worker-node.yml`; on the central server
> they are disabled by default (compose profile `scale-out`).
> This is a configuration target; live IPs, listeners and firewall denial require runtime verification.

```
Central Server (single IP: <CENTRAL_IP>, 16 GB RAM)
├── PostgreSQL (port 5432, bind 0.0.0.0, firewall target: workers only)
├── Redis (port 6379, bind 0.0.0.0, firewall target: workers only)
├── Squid 1 (port 3128, egress via <CENTRAL_IP>)    ← Worker 1 (local)
├── FastAPI Backend (port 8000, internal)
├── Celery Worker 1 → Squid 1 → UTCMS               ← -Q waybill_tasks_1,...
├── Celery Beat (periodics scheduler)
├── Celery Scheduler → rpa_scheduler                 ← profile-less, always-on control queue consumer
├── Next.js Frontend (port 3000, internal)
├── Nginx (port 80, public) → reverse proxy
└── Monitoring stack (Prometheus/Alertmanager/Grafana/exporters; internal or loopback only)

Remote Worker Nodes (each: 2 vCPU / ~6 GB / own static Iranian IP)
├── Squid (port 3128, egress via the Worker's own IP)   ← Workers 2/3
└── Celery Worker 2/3 → local Squid → UTCMS
    (via compose/worker-node.yml; DB/Redis at <CENTRAL_IP>)
```

### Squid Proxy Ports
| Proxy | Port | Egress IP | Used By | Topology |
|-------|------|-----------|---------|----------|
| Squid 1 | 3128 | <CENTRAL_IP> | Worker 1 | Both Model A & B |
| Squid 2 | 3129 | <CENTRAL_IP> (Model A) / N/A (Model B) | Worker 2 | Model A only (central) |
| Squid 3 | 3130 | <CENTRAL_IP> (Model A) / N/A (Model B) | Worker 3 | Model A only (central) |
| Remote Worker Squid | 3128 | Worker's own IP | Worker 2/3 | Model B only (remote nodes) |

> **Note:** In Model B, Squid 2 and 3 must not run on Central. They are guarded by
> the explicit `model-a` Compose profile; Workers 2/3 use their own remote Squid
> on port 3128. Confirm the live host has no unexpected Model A containers/listeners.

### Network Flow
- **Public entry**: port 80 (HTTP). Port 443 is only a disabled template until a
  certificate, active listener, redirect, TLS handshake, and secure cookie are verified.
- **Internal**: Docker bridge network `barpro_platform`
- **UTCMS egress**: via Squid proxies using different IPs (anti-bot bypass)
- **Inter-node security target**: UFW/provider firewall must restrict database
  (5432) and Redis (6379) to registered Worker IPs only; verify this at runtime
  because bind addresses and Compose files do not prove packet filtering
- **Squid 2/3 ports (3129, 3130)**: should be firewall-restricted to localhost only (`scripts/secure_squid_ports.sh`)
- **DNS resolution**: Nginx uses Docker internal DNS (127.0.0.11) with 30s cache for dynamic container IP resolution

## Current Runtime Contracts

### Canonical API Paths

| Area | Current path |
|---|---|
| Liveness / public sanitized readiness | `GET /healthz`, `GET /readyz` |
| Detailed readiness | `GET /api/v1/admin/readyz` (admin only) |
| Authentication | `/api/v1/auth/*`, `/api/v1/admin/login` |
| Waybill jobs | `/api/v1/waybill-jobs` and its retry/requeue/timeline/log/screenshot subpaths |
| Fuel inquiries | `/api/v1/fuel-inquiries` |
| Clean IP operations | `/api/system/clean-ips`, `/api/system/clean-ips/refresh` (admin only) |
| Realtime | `WS /ws/waybill` with cookie auth and optional task/batch/correlation filters |

Do not use stale paths such as `/api/system/health`, `/ws/jobs/{client_id}` or
`/ws/admin/stream`. There is no distinct POST cancel contract:
`DELETE /api/v1/waybill-jobs/{job_id}` permanently deletes a job.

### Submission State and Reconciliation

A successful browser response is not immediate proof of registration. The safe flow is:

`running → unknown → reconciling → success | needs_review`

`success` requires all three witnesses defined in `docs/UTCMS_CONSTRAINTS.md`:
an RPA tracking code, the same code persisted in `result_json`, and a matching
UTCMS History/Search record. `JobStateMachine` also requires
`mutation_status=confirmed` and `reconciled_at`. Unknown outcomes are reconciled
with delays `15,45,120,300` seconds and are never automatically resubmitted after
the bounded window.

### Queue Topology

- Every RPA Worker runs with effective concurrency `1`.
- Worker 1 consumes base queues plus `waybill_tasks_1`, `rpa_auth_1`,
  `rpa_submit_1`, `reconciliation_tasks_1`, `scheduled_tasks_1`, and
  `barpro.fuel.inquiry`.
- Remote Workers consume the corresponding `*_2` or `*_3` queues and the fuel queue.
- `celery_scheduler` consumes **only** `rpa_scheduler`.
- Beat publishes periodic messages; it does not consume gate, proxy, cleanup, or
  orchestrator tasks.
- Active bindings, backlog, and registered IP indices are runtime facts. Verify with
  Celery inspection, Worker Registry, and metrics rather than inferring them from env examples.

### Data Model

SQLModel primary keys are integer IDs. Public identifiers such as `job_id`,
`batch_id`, `intent_id`, and `execution_id` are strings, not UUID primary keys.
`WaybillJob` stores `payload_json`, `result_json`, retry, mutation, and
reconciliation fields. Operational aggregates include `DispatchIntent`,
`Execution`, `WorkerRegistry`, `ProxyEndpoint`, `UploadBatch`, and
`UTCMSSystemObservation`. `FuelInquiry` stores quota JSON and a screenshot
URL/Data URI and has no direct tracking-code column.

### OTP and CAPTCHA

- The `18:00–08:00` window is a configurable **prediction** of
  `OTP_REQUIRED`, not a guaranteed UTCMS schedule. Only a current
  `OTP_FREE` observation permits submission; unknown/degraded states fail closed.
- `CAPTCHA_PROVIDER=auto` uses CNN → PyTorch Fuel CRNN → Keras → Enhanced OCR →
  Local OCR.
- Keras lazy-loads and runs in-process in each Worker. `KERAS_PYTHON_PATH` is a
  legacy compatibility setting and is not consumed by the current solver.
- Accuracy and latency numbers require a versioned benchmark artifact; do not copy
  unsupported percentages into operational documentation.

## Common Pitfalls

| Pitfall | Details | Status |
|---------|---------|--------|
| `except: pass` | Used extensively (~55+ locations); never catch silently — log at minimum | ✅ Fixed |
| `engine.dispose()` per Celery task | Destroys connection pool, causing connection storms | ✅ Fixed |
| `asyncio.Lock` on class instances | Race condition when event loop changes; use `threading.Lock` for init | ✅ Fixed |
| `autoretry_for = (Exception,)` | Retries programming bugs indefinitely; use specific exceptions | ✅ Fixed |
| Migration startup | `run_migrations()` is active with a PostgreSQL session-level advisory lock; avoid raw Alembic startup runners | ✅ Fixed |
| Event loop per Celery task | `asyncio.new_event_loop()` per task is extremely expensive | ✅ Fixed |
| Session not injected | Services create `AsyncSession` directly instead of using `get_session()` dependency | ✅ Fixed |
| Race condition in Redis manager | Double-checked locking pattern is broken for async (redis.py:36-53) | ✅ Fixed |
| Zod v3 ↔ v4 mismatch | Keep imports from `zod`, not `zod/v4`, because package is `zod@3.24.1` | ✅ Fixed |
| Heroicons rename | Use current Heroicons v2 names such as `ArrowRightStartOnRectangleIcon` | ✅ Fixed |
| Hardcoded secrets in workflows | CI/CD workflows had fallback hardcoded credentials | ✅ Fixed |
| Missing security headers | Backend responses lacked security headers | ✅ Fixed |
| Missing Redis connection pool settings | No timeout/retry configuration | ✅ Fixed |
| Docker Compose V1 (`docker-compose`) usage | CI/CD and deploy scripts must use `docker compose` V2 — root `docker-compose.yml` uses `include:` (Compose >= 2.20) which V1 does not support | ✅ Fixed (.github/workflows/cd-deploy.yml) |
| Multi-IP proxy routing — topology mismatch | `AVAILABLE_IP_INDICES` is topology-specific and must match fresh Worker Registry entries. The intended 3-worker Model B fleet uses indices `1,2,3`; smaller deployments must narrow the set. | ✅ Runtime filtering prevents unregistered indices, but effective values still require deployment verification |

## Testing

```bash
pytest                    # Run all tests with coverage
pytest -m unit            # Unit tests only
pytest -m integration     # Integration tests only
pytest -m "not slow"      # Skip slow tests
```

- Tests use `asyncio_mode = "auto"` — async test functions are auto-detected
- Database tests require PostgreSQL running (check `compose/infra.yml`)
- Playwright tests require Chromium (install via `playwright install chromium`)
- Test counts are release snapshots, not timeless facts. Run the requested suite
  on the current commit and report its exact result instead of copying an old count.

## Project Structure

```
BarPro/
├── app/                    # Backend (FastAPI)
│   ├── api/                # Route handlers (waybill, management, admin, system)
│   ├── automation/         # RPA engine (browser, auth, captcha, proxy_rotator)
│   ├── core/               # Config, database, redis, security, rate_limiter
│   ├── models/             # SQLModel database models
│   ├── bot/                # Bot automation (captcha interception, smart locators)
│   │   ├── captcha/        # CAPTCHA interception & solving (interceptor, provider registry)
│   │   └── core/           # Smart element locators with fallback strategies
│   ├── services/           # Business logic layer
│   ├── workers/            # Celery tasks (waybill_worker, phase1_tasks, tasks)
│   ├── realtime/           # WebSocket event hub
│   └── rpa/                # RPA services (auth, submit, scheduler)
├── apps/web/               # Frontend (Next.js 15)
│   └── src/
│       ├── app/            # App Router pages
│       ├── components/     # Shared React components
│       ├── hooks/          # Custom hooks
│       ├── lib/            # Utilities (api, auth, plate)
│       └── schemas/        # Zod validation schemas
├── compose/                # Docker Compose layered files
│   ├── docker-compose.yml  # Root file using `include:` (requires Compose >= 2.20 / docker compose V2)
│   ├── infra.yml           # PostgreSQL, Redis
│   ├── proxy.yml           # Squid 1 by default; Squid 2/3 under model-a profile
│   ├── backend.yml         # FastAPI + Celery workers + celery_scheduler + Beat
│   ├── web.yml             # Nginx + Frontend
│   └── monitoring.yml      # Prometheus, Alertmanager, Grafana, exporters
├── infra/                  # Config files
│   ├── nginx/nginx.conf
│   ├── squid/squid_*.conf
│   ├── prometheus/prometheus.yml
│   └── logging/logrotate.conf
├── alembic/                # Database migrations; current head 036_management_tables_and_activity_logs_fix
├── tests/                  # Pytest test suite
├── scripts/                # Utility and deploy scripts
└── deploy/                 # Deployment configs
```

## Deployment

```bash
bash manage.sh start        # Full system bootstrap (respects layer order)
bash manage.sh stop         # Graceful shutdown
bash manage.sh status       # CPU/RAM/disk/container status
bash manage.sh health       # Verify DB/Redis/API/Frontend health
bash manage.sh deploy       # Pull from GitHub and redeploy
bash manage.sh backup-db    # PostgreSQL snapshot
```

### Docker Compose Layers (in order)
```bash
docker compose -f compose/infra.yml up       # PostgreSQL + Redis only
docker compose -f compose/proxy.yml up       # Model B: Squid 1 only
docker compose -f compose/proxy.yml --profile model-a up  # Model A: Squid 1/2/3
docker compose -f compose/backend.yml up     # Backend + workers
docker compose -f compose/web.yml up         # Nginx + Frontend
docker compose -f compose/monitoring.yml up  # Full monitoring stack
```

## Environment Variables (`.env`)

**Critical**: `.env` must NEVER contain real production secrets. Use `.env.example` as template.

| Variable | Purpose |
|----------|---------|
| `API_KEY` | Backend API key authentication |
| `JWT_SECRET` | JWT signing key (min 32 chars) |
| `DRIVER_ENCRYPTION_KEY` | Fernet key for driver password encryption |
| `MASTER_ADMIN_PASSWORD` | Master admin login password |
| `POSTGRES_PASSWORD` | Database password |
| `REDIS_PASSWORD` | Redis password |
| `HEADLESS` | Browser headless mode (true/false) |
| `CAPTCHA_PROVIDER` | Solver: auto/composite/cnn/pytorch_fuel/keras_ocr/enhanced_ocr/local_ocr/off |
| `AUTH_COOKIE_SECURE` | Secure flag for httpOnly JWT cookie; false on HTTP, true after HTTPS |
| `CAPTCHA_MODE` | Validated mode: local_only / provider_only / provider_first / manual_only |
| `CAPTCHA_TIMEOUT_SECONDS` | Max time to solve captcha (default 120) |
| `CAPTCHA_MAX_RETRIES` | Max auto retries (default 2) |
| `KERAS_PYTHON_PATH` | Legacy compatibility setting; current Keras provider does not execute a subprocess |
| `KERAS_MODEL_PATH` | Keras .keras model file for fuel inquiry captchas |
| `CAPTCHA_LOCAL_FALLBACK_ENABLED` | Enable Tesseract/local OCR fallback |
| `AVAILABLE_IP_INDICES` | Comma-separated routing indices; topology-specific and filtered against fresh Worker Registry entries. The intended 3-worker Model B fleet uses `"1,2,3"`; smaller fleets must narrow it. |
| `RPA_PROXIES` | Comma-separated proxy URLs for workers (SSRF risk — see ISSUES.md) |

## CAPTCHA Model Chain

| Page | Solver | Model | Provider Name |
|------|--------|-------|---------------|
| **Login** (math: "2+3") | PyTorch CNN | `app/automation/captcha/assets/captcha_cnn.pth` | `cnn` |
| **Fuel Inquiry** (Persian words) | PyTorch CRNN | `app/automation/captcha/assets/fuel_captcha_crnn.pth` + vocab | `pytorch_fuel` |
| **Fuel Inquiry fallback** | Keras OCR | `persian_number_ocr.keras` (project root) | `keras_ocr` |

Default `CAPTCHA_PROVIDER=auto` tries CNN → PyTorch fuel → Keras → Enhanced → Local in sequence.
All current providers execute within the Worker process; Keras is lazy-loaded once and reused.

## Optimization Applied (2026-06-30 → 2026-08-22)

### 2026-08-22 — v2.9.3 Auth Session Cookie Synchronization, Fast 408 Outage Detection & Taxonomy Resilience
| Change | File | Impact |
|--------|------|--------|
| ASP.NET Auth Cookie Synchronization | `app/automation/auth_session.py` | Adds `Barname`, `ApplicationToken`, `cookiesession1` to `AUTH_KEYWORDS`, ensuring `SessionManager.has_auth_cookie()` instantly validates fast HTTP logins without falling back to WAF-blocked Chromium sessions |
| Operator Direct Retry Unblocking | `app/core/error_taxonomy.py` + `app/services/waybill_job_service.py` | Moves `UNKNOWN_AUTOMATION_ERROR`, `AUTH_FAILURE`, `SELECTOR_CHANGED`, `BOT_DETECTED` to `RETRYABLE_TERMINAL_CATEGORIES`, resolving the 409 UI retry blockage while strictly preserving `SUBMISSION_UNCONFIRMED` safeguards |
| Sub-Second Fast 408 Outage Detection | `app/automation/waybill_enhanced.py` + `app/core/error_taxonomy.py` | Detects upstream UTCMS portal downtime (`HTTP 408` / `قادر به پاسخگویی نمی باشد`) in <0.3s instead of 480s timeout, automatically classifying as `TARGET_SITE_TIMEOUT` and queuing exponential backoff retry |
| Next.js History Page Build Fix | `apps/web/src/app/history/page.tsx` | Resolves `loadTimeline` hook declaration order that broke the Next.js production build and page rendering |
| Multi-Server Fleet Deployment | Central + Worker 2 + Worker 3 | Synchronizes and restarts all backend, scheduler, and worker containers across the entire Model B cluster |

### 2026-08-20 — v2.9.2 Universal Mobile Anti-Zoom, UI/UX Hardening & Full-Stack Taxonomy Sync
| Change | File | Impact |
|--------|------|--------|
| Universal Mobile Anti-Zoom & Viewport Lock | `apps/web/src/app/layout.tsx` + `apps/web/src/app/globals.css` | Enforces `width: device-width`, `maximumScale: 1`, `userScalable: false`, `16px` minimum input font size, and `touch-action: manipulation` across all iOS and Android mobile browsers |
| Full-Stack Case-Insensitive Status Filtering | `apps/web/src/app/reports/page.tsx` + `app/services/user_reporting_service.py` + `app/services/admin_reporting_service.py` | Eliminates empty query results by syncing dropdown values with backend lowercase keys and applying `.strip().lower()` on database query filters |
| Comprehensive Persian RPA Error Taxonomy | `apps/web/src/lib/format.ts` | Extends `errorCategoryLabel` with case normalization and friendly Persian translations for all RPA engine and bot error categories |
| RTL Admin Sidebar Layout Fix | `apps/web/src/app/admin/layout.tsx` | Standardizes admin layout to RTL (`right-0`, `border-l`, `md:mr-[280px]`, `translate-x-full` mobile transition) |
| Form Digit Normalization & Mobile Spacing | `apps/web/src/app/new/page.tsx` | Implements real-time Persian/Arabic to English digit conversion on `onChange` and prevents mobile navigation bar occlusion with `pb-32 sm:pb-0` |
| Web Accessibility (a11y) & Focus Management | `CreateClientModal.tsx` + `PlateInput.tsx` + `alerts/page.tsx` + `auth/page.tsx` | Adds missing `aria-label` / `aria-expanded` attributes, live screen-reader regions (`aria-live="polite"`), and automatic focus recovery on login errors |

### 2026-08-20 — v2.9.1 Driver Fleet Vehicle Type Sync & Multi-Tenant Plate Safeguards
| Change | File | Impact |
|--------|------|--------|
| Multi-Tenant Plate Limit Enforcement | `app/services/driver_service.py` + `app/services/waybill_job_service.py` | Enforces `client.max_plates` check before adding new `DriverPlate` dynamically upon driver creation and waybill submission |
| Independent `vehicle_type` Plate Sync | `app/services/driver_service.py` | Allows updating `vehicle_type` on the driver's active plate without requiring `plate_number` in `DriverUpdateRequest` |
| Driver Fleet Vehicle Type Chips & UI Integration | `apps/web/src/app/drivers/page.tsx` | Adds 12 vehicle type preset chips and custom input to create/edit modals; renders vehicle type badges on driver cards |
| Fuel Quota Parsing Standardization & Canonical Tracking Code | `apps/web/src/app/fuel/page.tsx` | Eliminates raw `quota_data` property access by adopting canonical `parseQuotaData` and `formatFuelTrackingCode` across all cards, tables, and modal views |
| Alembic Migration Documentation Sync | `AGENTS.md` + `.agents/skills/barpro-fullstack-sync/SKILL.md` | Standardizes current Alembic head reference to `036_management_tables_and_activity_logs_fix` |

### 2026-08-19 — v2.9.0 Clean Iranian Proxy Pool (Zero IP Restriction)
| Change | File | Impact |
|--------|------|--------|
| Multi-Source Iranian Proxy Aggregator & Benchmarking Engine | `app/automation/clean_ip_pool.py` | Aggregates from 11+ global sources, probes live against `https://utcms.ir` via HTTPS CONNECT, verifies status 200, ranks by latency |
| Egress Fallback & Dynamic Hybrid Routing | `app/automation/worker_proxy.py` + `app/automation/proxy_rotator.py` | `get_best_egress_proxy()` seamlessly fails over from blocked/unreachable worker Squids to the Clean IP Pool (modes: worker_first, clean_pool_only, hybrid) |
| Per-IP Circuit Breaker & Isolation | `app/core/circuit_breaker.py` | Errors on third-party clean proxies mark only that specific proxy blocked via `mark_blocked()`, leaving worker nodes and `WORKER_IP_INDEX` healthy |
| Periodic Background Probe & Redis Distributed Sync | `app/workers/tasks.py` + `app/workers/celery_app.py` | `barpro.clean_ip.probe` RedBeat task refreshes the pool every 5 minutes under distributed Redis lock |
| Management Endpoints & Operational CLI | `app/api/routes/system.py` + `scripts/refresh_iran_proxies.py` | Exposes admin-protected `GET /api/system/clean-ips`, `POST /api/system/clean-ips/refresh`, and standalone benchmark CLI |

### 2026-08-19 — v2.8.3 Waybill Payload Validation & Vehicle Type Integration
| Change | File | Impact |
|--------|------|--------|
| Vehicle Type Preset Chips & Custom Input | `apps/web/src/app/new/page.tsx` | Adds 12 vehicle type presets (کامیون، تریلی کشنده، خاور، وانت، تک، جفت و...) with auto-population from driver's plate |
| Quick Add Driver Vehicle Type Support | `apps/web/src/app/new/page.tsx` | Allows registering vehicle type directly in the quick driver creation modal |
| Full-Stack Schema Alignment & Normalization | `apps/web/src/schemas/waybillSchema.ts` + `app/schemas/multitenant.py` | Eliminates 422 Union validation error on `POST /api/v1/waybill-jobs`; supports flat/nested/hybrid payloads |
| Driver Plate Auto-Sync & Storage | `app/services/waybill_job_service.py` | Auto-registers and updates `DriverPlate.vehicle_type` in PostgreSQL upon job creation |

### 2026-08-19 — v2.8.2 Fuel Quota Performance & Modal Screenshot Persistence
| Change | File | Impact |
|--------|------|--------|
| Single-Tab In-Place Sequential Fuel Scraper | `app/automation/fuel_scraper.py` | Eliminates ASP.NET session clobbering (`Session["LoginShowFuelQuota"]`); reduces inquiry time from 167s to <15s and guarantees 100% extraction of BOTH Base and Performance quotas |
| Modal-Content Screenshot Capture Before Close | `app/automation/fuel_scraper.py` | Captures modal element screenshot while results and numbers are visible before dismissing the dialog |
| Multi-Server Base64 Data URI Persistence | `app/automation/fuel_scraper.py` + `app/api/routes/multitenant.py` | Stores screenshots directly in PostgreSQL as Data URIs; fixes Model B 404 missing-file error between remote workers and central API |
| Quota Data Tables & Full-Res Preview Modal | `apps/web/src/app/fuel/page.tsx` | Displays structured Base/Performance data breakdown tables and full-resolution screenshot links in details modal |

### 2026-08-19 — v2.8.1 Fuel Inquiry Tracking & Waybill UX Polish
| Change | File | Impact |
|--------|------|--------|
| Resilient Quota Data Parser & Persian Digits | `apps/web/src/lib/format.ts` | Eliminates `[object Object]` bug on `/history` and `/fuel`; safely renders Base Quota, Performance Quota, Card Number |
| Full Details Modal for Fuel Inquiries | `apps/web/src/app/history/page.tsx` + `fuel/page.tsx` | Adds comprehensive modal with quota metrics, structured breakdown tables, and high-res screenshot view |
| Rich Waybill Payload Metadata in Job Cards | `apps/web/src/app/history/page.tsx` + `lib/format.ts` | Displays fleet plate, origin←destination route, cargo weight/type badges and confirmed UTCMS tracking codes |
| Vehicle Type Quick Selector & Payload Alignment | `apps/web/src/app/new/page.tsx` + `schemas/waybillSchema.ts` | Integrates `vehicle_type` chips and canonical multi-tenant payload serialization on waybill creation |
| Driver Plate Validation & Schema Resilience | `app/schemas/multitenant.py` + `app/services/driver_service.py` | Enforces truck plate validation while maintaining test and endpoint backward compatibility |

### 2026-08-16 — v2.8.0 UTCMS RPA Hardening & Mutation Safety
| Change | File | Impact |
|--------|------|--------|
| `_click_once_no_retry` At-Most-Once submit click | `automation/waybill_enhanced.py` | Eliminates double-click duplicate waybill submissions on target closed/navigation errors |
| Adaptive OTP Gate & Predicted Window | `services/utcms_submission_gate.py` | 18:00-08:00 defined as predicted OTP_REQUIRED; only confirmed OTP_FREE allows submission |
| Beat periodic gate probe task `barpro.gate.probe` | `workers/tasks.py` + `workers/celery_app.py` | Low-rate background probe maintains live gate status under Redis distributed lock |
| Global canonical idempotency & plate inclusion | `core/submission_identity.py` + `services/task_service.py` | Deterministic digest without random/volatile correlation IDs; duplicate dispatch returns existing job |
| Strict exact/unique cargo & packaging match | `automation/waybill_enhanced.py` | Eliminates guessing first option (`items[0]`, `search_results[0]`); invalid inputs fail fast |
| Pure text route validation (GPS independence) | `services/management_service.py` + `automation/location_selector.py` | Location readiness verified by city and address strings without GPS coordinates dependency |
| Three-Witness Reconciliation & Eventual Consistency | `orchestrator/utcms_reconciliation_scraper.py` + `orchestrator/reconciliation_service.py` | Full DataTables payload on `/barname/History/History`; composite multi-attribute match |
| Frontend unconfirmed status clarity | `apps/web/src/lib/format.ts` | `submission_unconfirmed` displayed as unconfirmed/reconciling, never falsely as success |
| OpenTelemetry shutdown debug logging | `core/tracing.py` | Replaced `except: pass` with debug logging |

### 2026-08-13 — v2.7.0 Authentication & Network Layer
| Change | File | Impact |
|--------|------|--------|
| WAF fast-fail in Playwright fallback | `automation/auth.py` | 3-minute wait on HTTP 444 → 500ms fast-fail |
| Post-HTTP-login Playwright navigation to WAYBILL_URL | `automation/auth.py` | Session warm before form-fill; eliminates cold-start navigation |
| Transient 5xx retry (503/502/504/500/408, 3×, 6s) | `automation/utcms_http_login.py` | Single 503 no longer aborts HTTP login and forces WAF-blocked Playwright |
| `_looks_unauthenticated()` silent session expiry detection | `automation/utcms_http_login.py` | Expired session detected via Location header + final URL (not just HTTP status) |
| Rate-limit / transient counter not decrementing captcha budget | `automation/utcms_http_login.py` | 503 or 429 no longer wastes a captcha-solve attempt |
| `_response_diagnostics()` (Server/Via/X-Squid-Error) | `automation/utcms_http_login.py` | Squid 503 vs UTCMS 503 distinguishable without re-run |
| `network.py` composable marker tables (EGRESS+BROWSER+GENERIC) | `core/network.py` | EGRESS⊆RETRYABLE invariant enforced by tests; 5/6 egress failures previously not evicting IP |
| `RedisConnectionManager` per-thread×loop cache | `core/redis.py` | `RuntimeError: Event loop is closed` in Celery eliminated |
| `_force_close_sockets()` + `_detach_transport()` | `core/redis.py` | `ResourceWarning: unclosed socket/transport` eliminated |
| 82 new `test_circuit_breaker.py` tests | `tests/` | EGRESS vs BROWSER routing, IP-index eviction |
| 272 new `test_event_loop_affinity.py` tests | `tests/` | Redis per-loop cache and socket-close across loop boundaries |
| 114 extended `test_error_taxonomy.py` tests | `tests/` | containment invariant EGRESS⊆RETRYABLE |

### 2026-06-30 — Performance
| Change | File | Impact |
|--------|------|--------|
| Removed `engine.dispose()` per Celery task | `workers/waybill_worker.py:91`, `phase1_tasks.py:23` | +500ms saved per task, connection storm eliminated |
| `autoretry_for` changed to specific exceptions | `workers/waybill_worker.py:61` | No retry on programming bugs |
| Browser recycle removed from task `finally` block | `workers/waybill_worker.py:105`, `phase1_tasks.py:28` | 90% fewer Chrome launches |
| Recycle threshold increased to 20 | `automation/browser.py:181` | Chrome restarts only after 20 successes |
| Event loop per worker process (not per task) | `workers/tasks.py:4-15` | No event loop churn on 4 vCPU |
| `_run_async` no longer creates ThreadPoolExecutor per call | `workers/tasks.py:16-27` | No thread churn |
| `NullPool` replaced with `AsyncAdaptedQueuePool(2,2)` | `core/database.py` | Connection reuse across tasks |
| `React.memo` on table rows/cards | `fuel/page.tsx` | No full re-render on every state tick |
| WebSocket event buffer capped at 100 | `useWaybillJob.ts:65` | No linear memory growth on long-lived connections |
| Aggressive 3s polling → MAX_POLLS=60 | `fuel/page.tsx:151` | Stuck jobs stop after 3 min, not forever |
| `client_max_body_size` 50m → 10m | `http-server.conf:9` | 40 MB nginx memory saved per upload |
| Rate-limit zones 20m → 10m (×3) | `nginx.conf:48-50` | 30 MB nginx shared memory saved |
| Chromium V8 heap capped at 1 GB | `browser.py:251` | No unbounded JS heap growth |
| WebSocket events bridged via Redis pub/sub | `realtime/events.py` + `main.py` lifespan | Worker-originated events now reach API WebSockets cross-process (was process-local only) |

### Memory / Stability
| Change | File | Impact |
|--------|------|--------|
| Page listeners removed on page close | `automation/browser.py:463-465` | No listener leak over 1000+ pages |
| Timeouts added to all browser close operations | `automation/browser.py:139-176` | No hang on context/browser close |
| `except: pass` replaced with logging in recycle_browser | `automation/browser.py:139-176` | Errors visible in logs |
| Model B Central resource limits retuned for 16 GB | `compose/*.yml` | Current documented limits total about 9 GB; verify live RSS separately |
| Dedicated celery_scheduler service for rpa_scheduler queue | `compose/backend.yml:246-277` | Profile-less, always-on consumer — no starvation on central/dual-node deployments |

### Database
| Change | File | Impact |
|--------|------|--------|
| Queue depth cached in Redis (HINCRBY per transition, seeded from DB at startup) | `services/task_service.py` (`_queue_depth_snapshot`/`_adjust_queue_depth`) | No full-table scan on every status transition; DB scan only as fallback/seed |
| N+1 re-fetch eliminated in `_emit_task_event` | `services/task_service.py` | Status/payload passed from the in-memory row; no extra SELECT per transition |
| Per-transition commits collapsed into one | `services/task_service.py` + `workers/waybill_worker.py` | 3 commits/block → 1; helpers `add`+`flush`, caller commits once |

### Index Recommendations (run on PostgreSQL)
```sql
CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_wj_status_priority_created
ON waybill_jobs (status, priority DESC, created_at ASC);

CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_wj_status_next_retry
ON waybill_jobs (status, next_retry_at);

CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_wj_status_covering
ON waybill_jobs (status) INCLUDE (id);
```

## Memory Budget (16 GB RAM — Central Server)

> **سرور مرکزی 16 GB RAM** — Workers 2/3 روی Remote Worker VPSها اجرا می‌شوند (Model B Scale-out)

| Container | Limit | Reservation | shm_size | تغییر |
|-----------|-------|-------------|----------|-------|
| PostgreSQL | **1.5 GB** | 768 MB | — | ↑ از 1 GB |
| Redis | **512 MB** | 256 MB | — | ↑ از 256 MB |
| Backend API | **512 MB** | 256 MB | 256 MB | ↑ از 256 MB |
| Celery Worker 1 | **3 GB** | 2.5 GB | 512 MB | ↑ از 2.5 GB |
| Celery Scheduler | **768 MB** | 384 MB | 128 MB | Dedicated rpa_scheduler consumer (FIX-A1) |
| Celery Beat | **256 MB** | 128 MB | — | ↑ از 128 MB (OOM fix) |
| Frontend (Next.js) | **1 GB** | 512 MB | — | ↑ از 512 MB |
| Nginx | **512 MB** | 256 MB | — | ↑ از 256 MB |
| Squid 1 (Model B Central) | 128 MB | 64 MB | — | Squid 2/3 are Model A only |
| Prometheus | 256 MB | 128 MB | — | — |
| Alertmanager | 128 MB | 64 MB | — | — |
| Grafana | 256 MB | 128 MB | — | — |
| Exporters ×4 | 64 MB each | 32 MB each | — | node/Redis/Postgres/Nginx |
| **Model B Central total limits** | **~9.0 GB** ← based on current Compose limits | | | |

> Workers 2/3 روی Remote Worker VPS اجرا می‌شوند و در بودجه سرور مرکزی نیستند.
> عدد بالا budget کد است، نه مصرف زنده؛ `docker stats` و host memory باید جداگانه
> بررسی شوند. Squid 2/3 فقط در استقرار تک‌سروره Model A وجود دارند.

## Historical Remediation Log (see ISSUES.md for current work)

> Status marks below describe repository changes at the time recorded. They do
> not prove that a production server has deployed them; server state always
> requires a timestamped runtime check.

### Repository fixes and follow-ups

| # | Fix | Status |
|---|-----|--------|
| 1 | Rotate leaked credentials (`PLACEHOLDER_SSH_PASSWORD` in code) | ✅ Previous leaked password → `PLACEHOLDER_SSH_PASSWORD` (rotate actual server password yourself) |
| 2 | Purge `.env` from git history | ✅ `git filter-repo` done — `.env` and `celerybeat-schedule.db` removed from all commits |
| 3 | Fix `zod/v4` import → `zod` | ✅ `apps/web/src/schemas/waybillSchema.ts:1` |
| 4 | Fix `ArrowLeftOnRectangleIcon` | ✅ `apps/web/src/components/layout/Header.tsx:3` |
| 5 | Add HTTPS to Nginx | ⬜ Config ready (`infra/nginx/nginx.conf` + `http-server.conf` + compose volume) — uncomment `listen 443` and `ssl` volume after cert install |
| 6 | Remove `privileged: true` | ✅ `cap_add: [SYS_ADMIN, NET_ADMIN]` + `security_opt: [no-new-privileges:true]` on all containers |
| 7 | Fix rate limiter fail-open | ✅ Fail-closed: HTTP 429 when Redis down (default removed) |
| 8 | Restrict Prometheus port | ✅ `9090:9090` → `expose: [9090]` in `compose/monitoring.yml` |
| 9 | Run PostgreSQL indexes | ⬜ Migration `012_add_optimization_indexes.py` ready — run `bash manage.sh migrate` on production DB |
| 10 | Fix all `except: pass` | ✅ 55 blocks fixed across 19 files (auth.py, location_selector.py, browser.py, etc.) |
| 11 | Fix Redis race condition | ✅ `app/core/redis.py` — `threading.Lock` (safe across Celery event loops) |
| 12 | Rate limit ALL endpoints | ✅ Path-prefix matching in `app/main.py` — 6 rate limit rules |
| 13 | Fix browser context leaks | ✅ Timeouts on close, listener cleanup, OOM risk reduced |
| 14 | Migrate JWT to httpOnly cookies | ✅ JWT cookie set by backend; frontend uses `withCredentials` |
| 15 | Remove `network_mode: host` | ⬜ **Blocked**: dual-IP routing requires it — use `scripts/secure_squid_ports.sh` (iptables) instead |
| 16 | Fix alembic migrations | ✅ `run_migrations()` now uses a PostgreSQL session-level advisory lock and runs on startup via `database.py` |
| 17 | Add container vulnerability scanning | ⬜ Future work |

### ✅ Optimizations Applied

| Change | File(s) |
|--------|---------|
| Nginx: separated HTTP/HTTPS config via include | `infra/nginx/nginx.conf`, `infra/nginx/http-server.conf` |
| Migrations: PostgreSQL session-level advisory lock prevents concurrent runners | `app/core/database.py` |
| Deploy: `manage.sh deploy` now auto-runs `alembic upgrade head` | `manage.sh` |
| New: `manage.sh migrate` — run migrations manually | `manage.sh` |
| New: `scripts/run_migrations.sh` — standalone migration runner | `scripts/run_migrations.sh` |
| New: `scripts/secure_squid_ports.sh` — iptables for Squid 3129/3130 | `scripts/secure_squid_ports.sh` |

### Remaining Runtime Actions
1. **Install Let's Encrypt cert** → uncomment `listen 443` + `ssl` volume in `compose/web.yml` and `infra/nginx/nginx.conf:75-90`, then `bash manage.sh deploy`
2. **Verify `alembic current`** matches the release head after the locked startup migration
3. **Verify Model B Central has no Squid 2/3 listeners**; only Model A may expose 3129/3130 locally
4. **Probe PostgreSQL/Redis/Squid from a non-worker IP** and confirm denial
5. **After HTTPS install, set `AUTH_COOKIE_SECURE=true`** and redeploy

### Additional Fixes Applied (2026-07-08)

| Change | File(s) |
|--------|---------|
| Frontend Docker builds standalone output inside Docker | `apps/web/Dockerfile`, `apps/web/.dockerignore` |
| HTTP-compatible httpOnly auth cookie added | `app/api/routes/multitenant.py`, `app/core/config.py`, `compose/backend.yml` |
| New fuel CAPTCHA PyTorch provider enabled | `app/automation/captcha/fuel_captcha_solver.py`, `app/automation/captcha/persian_number_parser.py`, `app/core/config.py` |
| Alembic head advanced to 015 | `alembic/versions/014_*`, `alembic/versions/015_*` |
| Production frontend audit cleaned | `apps/web/package.json`, `apps/web/package-lock.json` |
| Generated/local artifacts ignored for upload/build context | `.gitignore`, `.dockerignore` |

### Additional Fixes Applied (2026-07-01)

| Change | File(s) |
|--------|---------|
| SSH passwords replaced with env vars in 5 script files | `scripts/upload_and_setup.py`, `scripts/server_deploy.py`, `scripts/deploy_single_vm.py`, `upload_tar.py`, `deploy_changes.py` |
| `ENVIRONMENT` added as a config field | `app/core/config.py` |
| `console.error` wrapped in environment guard | `apps/web/src/hooks/useWaybillJob.ts` |
| React index-as-key replaced with unique keys | `apps/web/src/app/fuel/page.tsx` (7 instances) |
| `__init__.py` added to test directories | `tests/`, `tests/core/`, `tests/load/` |
| `asyncio` marker registered in pytest.ini | `pytest.ini` |
| `python-multipart` added to dependencies | `requirements.txt` |
| Ruff autofix applied (isort, unused imports) | Multiple files |
| `except: pass` fixed in change_expired_password.py | `scripts/change_expired_password.py:47` |

### Additional Fixes & Features Applied (2026-07-09)

| Change | File(s) |
|--------|---------|
| Added pre-flight Squid proxy health checks before browser sessions and a `/proxies/health` endpoint | `app/automation/worker_proxy.py`, `app/api/routes/system.py`, `app/workers/waybill_worker.py` |
| Implemented unified `get_current_user_or_admin` dependency allowing Master Admin to view and manage resources globally across all tenants | `app/auth_multitenant.py`, `app/api/routes/multitenant.py`, `app/services/multitenant_service.py`, `app/services/fuel_inquiry_service.py` |
| Enhanced Admin Reports page with weekly line charts, error bar charts (SVG), Persian date tooltips, and CSV download export | `apps/web/src/app/admin/reports/page.tsx` |
| Added tracking codes (`UTC-YYMM-ID`) formatting and Persian digits display for fuel inquiries | `apps/web/src/app/fuel/page.tsx`, `app/schemas/multitenant.py` |
| Added tests for worker proxy health checks | `tests/test_worker_proxy_health.py` |

### Additional Fixes Applied (2026-07-10) — Performance Bottleneck Remediation

> NOTE: The earlier "Optimizations Applied (2026-06-30)" table (Redis queue counter, N+1 elimination in
> `_emit_task_event`, WebSocket send outside lock) was **documented but not actually present in the code**.
> The items below implement those optimizations for real, plus additional fixes from a stack-wide bottleneck analysis.

| Change | File(s) |
|--------|---------|
| Redis cached queue-depth counters (`HINCRBY` per transition, seeded from DB at startup) replace the full `waybilltask` table scan on every status transition | `app/services/task_service.py` (`_queue_depth_snapshot`/`_adjust_queue_depth`/`_incr_queue_depth`) + `app/main.py` lifespan |
| Redis pub/sub bridge so worker-originated WebSocket events reach the API process (was process-local only, so the live job UI was effectively broken) | `app/realtime/events.py`, `app/main.py` lifespan |
| Keras OCR moved in-process: model lazy-loaded once per worker and reused; removed the per-captcha subprocess + model reload (the prior design spawned an unbounded TensorFlow process that risked OOM on the 2.5 GB worker cgroup) | `app/automation/captcha/keras_ocr.py` |
| Collapsed per-transition sessions/commits into one: `_emit_task_event` uses the in-memory row (no re-query), and `waybill_worker._execute_job` batches log/event writes into a single commit per block | `app/services/task_service.py`, `app/workers/waybill_worker.py` |
| `bcrypt` hashing/verification moved off the event loop via `asyncio.to_thread` (was blocking all concurrent requests) | `app/auth_multitenant.py` |
| Bulk `Client` fetch (`Client.id.in_(...)`) replaces per-row `session.get(Client, ...)` in the admin job list | `app/services/multitenant_service.py` |

### Additional Fixes Applied (2026-07-18) — Waybill/Fuel Reliability & Security

| Change | File(s) |
|--------|---------|
| Driver submission lock serializes concurrent jobs for the same driver (`WAITING_RETRY` + `error_category=driver_submission_in_progress`) | `app/services/rpa_runtime_service.py`, `app/workers/waybill_worker.py` |
| Idempotency: skip jobs already holding a UTCMS `tracking_code`; demote `SUCCESS` without tracking code to `NEEDS_REVIEW` (`submission_unconfirmed`) | `app/workers/waybill_worker.py`, `app/services/task_service.py` |
| New job statuses `OTP_BACKOFF` / `NEEDS_REVIEW` wired through queue-depth counters and frontend status badges | `app/services/task_service.py`, `apps/web/src/lib/format.ts` |
| Fuel inquiry claim-on-execute (`UPDATE ... WHERE status='pending'`) prevents double processing | `app/services/fuel_inquiry_service.py` |
| Fuel inquiry de-dup: partial unique index `uq_fuel_inquiries_active_period` (migration `018`); HTTP `409` on duplicate active inquiry | `alembic/versions/018_fuel_inquiry_active_unique.py`, `app/services/fuel_inquiry_service.py` |
| `RPA_PROXIES` env URLs validated via `_is_safe_proxy_url` before `/proxies/health` uses them (SSRF guard) | `app/api/routes/system.py`, `app/automation/proxy_rotator.py` |
| JWT stack swapped `python-jose` → `PyJWT[crypto]` to drop vulnerable `ecdsa` transitive dep | `requirements.txt`, `app/core/security.py`, `app/auth_multitenant.py` |
| Bumped vulnerable deps: Pillow 12.3.0, torch 2.13.0, tensorflow ≥2.18, opencv ≥4.11, setuptools 82.x | `requirements.txt` |
| Removed legacy `app/frontend/` (7 npm vulns) and stale `apps/web/yarn.lock` (5 npm vulns); `package-lock.json` is source of truth | `.gitignore` |
| Removed tracked Chromium binaries from `.playwright-home/` (regenerated via `playwright install`) | `.gitignore`, `git filter-repo` |
| Frontend: display UTCMS `tracking_code` + Persian `error_category`; reports chart/CSV in Persian; friendly HTTP 409 message | `apps/web/src/{lib/format.ts,lib/types.ts,app/history/page.tsx,app/page.tsx,app/admin/reports/page.tsx,app/fuel/page.tsx}` |
| Added `.github/dependabot.yml` (weekly pip/npm/actions); `requirements-dev.txt` pins relaxed to `>=` | `.github/dependabot.yml`, `requirements-dev.txt` |

> Verification: `pip-audit` → *No known vulnerabilities found*; `npm audit --omit=dev` (apps/web) → 0 vulnerabilities; GitHub Dependabot no longer flags the default branch. `tsc --noEmit` and `npm run lint` pass on `apps/web`.

---

### Additional Fixes Applied (2026-08-02) — Documentation & Final Hardening

| Change | File(s) |
|--------|---------|
| Added security headers middleware to FastAPI backend | `app/main.py` |
| Configured Redis connection pool with timeout/retry settings | `app/core/redis.py`, `app/core/rate_limiter.py`, `app/core/circuit_breaker.py` |
| Removed hardcoded fallback secrets from GitHub Actions workflows | `.github/workflows/ci-cd.yml` |
| Enhanced CSP header with frame-ancestors, base-uri, form-action | `infra/nginx/http-server.conf` |
| Added Permissions-Policy header | `infra/nginx/http-server.conf` |
| Configured Nginx DNS resolver for dynamic upstream resolution | `infra/nginx/nginx.conf`, `infra/nginx/http-server.conf` |
| Improved phone validation error messages with examples | `apps/web/src/schemas/waybillSchema.ts` |
| Added logging to exception handler in _safe_json_payload | `app/services/_helpers.py` |
| Updated all documentation files (ISSUES.md, README.md, AGENTS.md, CRITICAL_RULES.md) | Multiple files |

---

### Additional Fixes Applied (2026-07-21) — Worker Proxy, Rotator & Event Loop Reliability

| Change | File(s) |
|--------|---------|
| Fixed sticky `None` caching in `get_worker_proxy_url()` with dynamic TTL-cache (`_PROXY_CACHE_TTL_SUCCESS`/`_PROXY_CACHE_TTL_FAILURE`) and `clear_proxy_cache()` helper | `app/automation/worker_proxy.py` |
| Added `_rotator_init_lock` (`threading.Lock`) for thread-safe `get_proxy_rotator()` singleton initialization across Celery worker threads | `app/automation/proxy_rotator.py` |
| Fixed `test_proxy()` URL parsing (`IndexError` prevention) and added `test_proxy.__test__ = False` for pytest compatibility | `app/automation/proxy_rotator.py` |
| Fixed `InFailedSqlTransactionError` in `waybill_worker._execute_job` exception handler by issuing `await session.rollback()` prior to persisting failure state | `app/workers/waybill_worker.py` |
| Cleaned up `run_async` in core utils to avoid creating orphan thread pools and removed unused variable `running` (`F841`) | `app/core/utils.py` |
| Added comprehensive unit test suite `tests/test_worker_proxy_and_rotator.py` | `tests/test_worker_proxy_and_rotator.py` |

### Additional Fixes Applied (2026-07-21) — RPA Services, RPA Dispatch & Scheduler Reliability

| Change | File(s) |
|--------|---------|
| Added per-job `try/except` error isolation inside `plan_due_jobs()` so an unexpected error evaluating one job does not abort the entire scheduler batch | `app/services/rpa_scheduler_service.py` |
| Immediate status reset to `PENDING` in `_dispatch_phase1_task` when `celery_app.send_task()` fails, preventing jobs from being stuck in `QUEUED`/`WAITING_AUTH` | `app/services/rpa_dispatch_service.py` |
| Wrapped decision dispatches in `dispatch_phase1_decisions()` to isolate single-job dispatch errors | `app/services/rpa_dispatch_service.py` |
| Added dual Persian solar calendar weekday mapping (`Sat=0...Fri=6`) alongside Python weekday indices in `_evaluate_single_schedule()` | `app/services/scheduled_waybill_executor.py` |
| Enhanced `release_lock()` to support explicit tokens and direct fallback deletion when `ContextVar` context is lost across async worker tasks | `app/services/rpa_runtime_service.py` |
| Added unit test suite `tests/test_rpa_dispatch_scheduler.py` | `tests/test_rpa_dispatch_scheduler.py` |

### Additional Fixes Applied (2026-07-21) — Smart Locators, Form Validation & Browser/Session Optimization

| Change | File(s) |
|--------|---------|
| Scoped `SmartLocator` cache keys by page instance ID (`id(page)`) to prevent cross-page stale selector cache hits | `app/bot/core/smart_locator.py` |
| Added `MODAL_POPUP_SELECTORS` and `MODAL_CONFIRM_BUTTONS` to `AuthSelectors` for SweetAlert2, Toastr, and Bootstrap modal dismissals | `app/automation/selectors.py` |
| Added automated native browser dialog interceptor (`page.on("dialog")`) and `_check_and_dismiss_modal_alerts()` to prevent Playwright freezes | `app/automation/waybill_enhanced.py` |
| Added pre-validation checksum helpers for Iranian National Code (`_is_valid_iranian_national_code`) and Mobile Numbers (`_is_valid_iranian_mobile`) | `app/automation/waybill_enhanced.py` |
| Removed forced JS step transitions on invalid form states; extract modal and inline error messages to raise early descriptive `WaybillError` | `app/automation/waybill_enhanced.py` |
| Enforced 10-second `asyncio.wait_for()` timeout wrappers on browser process teardown and added `_cleanup_zombie_processes()` (`pkill chrome-headless-shell`) in `BrowserManager.recycle_browser()` | `app/automation/browser.py` |

### Additional Fixes Applied (2026-07-21) — Retry, Queue/Scheduler & Connection/Timeout Optimization

| Change | File(s) |
|--------|---------|
| Reset `attempt_count = 0` on manual job retry API (`POST /waybill-jobs/{job_id}/retry`) to grant a full retry quota | `app/services/multitenant_service.py` |
| Cleared `celery_task_id = None` on `WAITING_RETRY` and `OTP_BACKOFF` status transitions, allowing due jobs to be re-dispatched cleanly by scheduler | `app/workers/waybill_worker.py` |
| Allowed reclaiming stale `IN_PROGRESS` jobs (> 5 min) in `waybill_worker` to recover gracefully from Celery worker crashes | `app/workers/waybill_worker.py` |
| Wrapped RPA bot execution in `asyncio.wait_for(..., timeout=240s)` to prevent worker SIGKILL hard crashes and categorize timeouts cleanly as `system_error` | `app/workers/waybill_worker.py` |
| Cleared stale `celery_task_id` for due `PENDING`, `WAITING_RETRY`, and `OTP_BACKOFF` jobs inside `plan_due_jobs()` | `app/services/rpa_scheduler_service.py` |
| Un-exempted `scheduled_tasks` from `EXEMPT_QUEUES` in `circuit_breaker.py` so scheduled tasks get distributed to worker queues `scheduled_tasks_1/2/3` | `app/core/circuit_breaker.py` |
| Added Squid proxy, tunnel failures, ECONNRESET, and 502/503/504 errors to `RETRYABLE_NETWORK_MARKERS` | `app/core/network.py` |
| Added document `readyState` fallback to `goto_with_retry` / `_goto_with_retry` on navigation timeout to prevent false failures when main document has loaded | `app/automation/auth_navigator.py`, `app/automation/waybill_enhanced.py` |

### Additional Fixes & Features Applied (2026-07-21) — Map, Location & Origin/Destination Registration System

| Change | File(s) |
|--------|---------|
| Created centralized dataset for 31 Iranian provinces, main county centers, and coordinates with offline fallback `find_nearest_city_coords` | `app/core/iran_locations.py` |
| Created `parse_smart_address` for 1-click automatic parsing of unsegmented/raw address strings into province, city, district, and address components | `app/core/iran_locations.py` |
| Created `LocationFavorite` SQLModel schema for client favorite locations | `app/models/location_favorite.py` |
| Added `/api/v1/locations` API routes: `/provinces`, `/cities`, `/parse-address`, `/reverse-geocode`, and `/favorites` CRUD | `app/api/routes/location.py` |
| Upgraded `/api/v1/waybill/reverse-geocode` with security authentication and offline dataset fallback when Nominatim times out | `app/api/routes/waybill_map.py` |
| Implemented Fuzzy Option Matcher (`_find_best_option_match`) with prefix stripping ("استان", "شهرستان", "شهر") for UTCMS dropdown selection resilience | `app/automation/location_selector.py` |
| Developed frontend `ProvinceCitySelect` dropdown component with Farsi search & cascading city selection | `apps/web/src/components/ProvinceCitySelect.tsx` |
| Developed frontend `SmartAddressInput` component for 1-click smart address parsing | `apps/web/src/components/SmartAddressInput.tsx` |
| Developed frontend `LocationMapPicker` Leaflet interactive map component with draggable marker & geolocation | `apps/web/src/components/LocationMapPicker.tsx` |
| Developed frontend `FavoriteLocationPicker` component for 1-click favorite address selection and saving | `apps/web/src/components/FavoriteLocationPicker.tsx` |
| Upgraded steps 2 & 3 in New Waybill page (`apps/web/src/app/new/page.tsx`) with interactive map, favorite address picker, cascading dropdowns, and passing exact `coordinates` in payload | `apps/web/src/app/new/page.tsx` |
| Added automated tests for location API and smart address parsing | `tests/test_location_api.py` |

### Additional Fixes Applied (2026-07-27) — Security Hardening & Test Quality

| Change | File(s) |
|--------|---------|
| `JSONB → JSON` dialect-agnostic import — SQLite-based tests can now run `SQLModel.metadata.create_all` | `app/models_multitenant.py` |
| Fixed double `json.loads()` on already-deserialized JSONB columns (TypeError was silently swallowed) | `app/services/fuel_inquiry_service.py`, `app/services/rpa_scheduler_service.py` |
| Fixed X-Forwarded-For spoofing — rate limiter now uses `request.client.host` (Nginx-set), ignores spoofable header | `app/core/rate_limiter.py` |
| Token blacklist fail-closed — `is_blacklisted()` returns `True` (not `False`) when Redis is unavailable | `app/core/token_blacklist.py` |
| Auth cookie `max_age` now uses `JWT_ACCESS_TOKEN_EXPIRE_MINUTES * 60` (was hardcoded 86400) | `app/api/routes/multitenant.py` |
| Rate limit rule covers `/api/v1/auth/login` and `/api/v1/auth/register` | `app/main.py` |
| Fixed `mock_page.on = MagicMock()` in browser and waybill tests — Playwright `page.on()` is synchronous | `tests/test_browser_manager.py`, `tests/test_enhanced_waybill_manager.py` |
| Fixed SQLModel false-positive DeprecationWarning — DML uses `conn = await session.connection()` | `app/services/fuel_inquiry_service.py` |
| JWT test fixtures use ≥32-byte keys to eliminate `InsecureKeyLengthWarning` | `tests/test_master_admin.py`, `tests/test_multitenant_auth.py` |
| Created `CRITICAL_RULES.md` — comprehensive technical red lines and mandatory requirements | `CRITICAL_RULES.md` (new) |
| Updated `README.md` — current test status (414 passed), architecture, security notes, doc index | `README.md` |
| Updated `.gitignore` — added debug scripts, temp files, large binaries | `.gitignore` |

### Additional Fixes Applied (2026-08-02) — 14-Item Code Audit Remediation (C4/C5/C6, H1–H6, F1–F4)

> Rationale: A code-level audit of `ISSUES.md` produced 14 actionable items (plus a NEW session-leak finding).
> Items marked "Fixed" below were verified present in the working tree and/or implemented this session.
> Server-level items (C1, C2, C3, C7) remain out of scope for this pass.

| Change | Reason | File(s) |
|--------|--------|---------|
| Added `from typing import Any` to `_is_jwt_valid`/`_has_admin_role` signatures | C4: `NameError: name 'Any' is not defined` would crash sensitive-auth at runtime | `app/core/security.py` |
| New `require_sensitive_admin` dependency — valid JWT **or** API Key **and** `role == master_admin` (covers `api_key`/`jwt`/`api_key_or_jwt`/`api_key_and_jwt` modes, cookie fallback preserved) | C5: role-gate admin-only sensitive endpoints without breaking client-visible routes (`/waybill/baseinfo/*` stays auth-only for the client settings page) | `app/core/security.py` |
| `/management/*` and `/reports/*` (legacy admin-only routers) upgraded from `require_sensitive_auth` to `require_sensitive_admin` | C5: these endpoints were reachable by any valid client JWT; only master-admin/API-key may call them now | `app/api/routes/management.py`, `app/api/routes/reports.py` |
| Removed duplicate `WORKER_STALL_TIMEOUT_SECONDS` definition (line 240); single env-driven `float` remains (default 90, `.env`=45) | C6: duplicate shadowed the real value and confused operators | `app/core/config.py` |
| `_emit_task_event` now calls `_get_task_status_and_payload(task_id)` — one SELECT for status+payload instead of two | H1: N+1 / double query on every status transition | `app/services/task_service.py` |
| Reconciliation claim uses `SELECT ... FOR UPDATE SKIP LOCKED` | H3: prevents two reconcilers/workers claiming the same job row | `app/orchestrator/reconciliation_service.py` |
| `_get_or_create_runtime_state` catches `IntegrityError` → `rollback()` + re-select instead of dying | H4: concurrent claim of the same runtime-state row no longer aborts the worker | `app/workers/waybill_worker.py` |
| `force_release_lock(key, token=None)` — optional token compare-and-delete (Redis Lua + memory branch); `None` keeps admin override | H5: locks can be released only by the holder; stale-force release still possible | `app/services/rpa_runtime_service.py` |
| `readyz` heavy checks (DB, browser init, captcha warmup) extracted into `_compute_readyz_checks()` and wrapped in a TTL cache (`READYZ_CACHE_TTL_SECONDS`, default 30s, `asyncio.Lock`-guarded) with `_reset_readyz_cache()` for tests | H2: consecutive `/readyz` calls (client settings page polls it) no longer re-run browser launch + model warmup each time; 30s cache keeps liveness fresh | `app/api/routes/system.py`, `app/core/config.py` |
| `H6` verified satisfied — `celery_app.py` still guards old execution path behind `if not DEPRECATE_OLD_EXECUTION_PATH` (default `True`) | H6 | `app/workers/celery_app.py` |
| NEW-session-leak verified satisfied — `_update_job_status` and `_execute_job` both `await session.close()` in `finally` | session leak: no orphaned `AsyncSession` per job | `app/workers/waybill_worker.py` |
| F1: removed `selectedJobId` from `loadJobs` deps; functional `setSelectedJobId(prev => prev || firstJobId)` + narrowed `firstJobId` const (TS18048) | F1: `loadJobs` re-created on every selection change caused fetch churn & infinite effect loops | `apps/web/src/app/history/page.tsx` |
| F2: added `apps/web/src/middleware.ts` — cookie-based route protection (redirects unauthenticated to `/auth`, skips `_next`/`api`/assets), fixed `hasAuthToken` → `hasAuthCookie` typo | F2: client-side `AuthGuard` alone left server-rendered routes visible; TS2304 would fail build | `apps/web/src/middleware.ts` (new) |
| F3: axios client now uses `timeout: 15000` with `withCredentials` | F3: hung requests previously blocked the UI indefinitely | `apps/web/src/lib/api.ts` |
| F4: `RequestOptions { signal?: AbortSignal }` threaded through all 5 API wrappers; `AbortController` used in reports/settings/fuel initial effects (incl. `fetchDashboardStats`/`fetchWaybillHistory`/`fetchDriverPerformance`/`fetchErrorDetails`/`loadData`/driver-waybill fetch) | F4: unmounted page fetches could `setState` after unmount / waste bandwidth; abort-on-cleanup fixes it | `apps/web/src/lib/api.ts`, `apps/web/src/app/reports/page.tsx`, `apps/web/src/app/settings/page.tsx`, `apps/web/src/app/fuel/page.tsx` |
| `tests/test_system_health.py` + `tests/test_readyz_failures.py`: autouse fixture calls `_reset_readyz_cache()` around each scenario | H2: TTL cache must not leak between unit-test scenarios | `tests/test_system_health.py`, `tests/test_readyz_failures.py` |

> Verification: `uvx ruff check` clean on touched files; `tsc --noEmit` + `eslint` clean on touched frontend files; full pytest suite green (552 passed, 2 skipped, 1 flaky worker-mock failure re-ran green).

---

### Additional Fixes Applied (2026-08-04) — Server 16GB RAM Upgrade, Beat OOM Fix & Deployment Automation

> **Historical context:** Production deployment on 3-server Model B topology:
> Central (16 GB) and two remote Worker VPS nodes. IP values are intentionally
> omitted from this repository guide.
> All fixes were validated against a running 25-table PostgreSQL at Alembic head `029`.

| Change | File(s) | Impact |
|--------|---------|--------|
| **Celery Beat OOMKilled fix**: `mem_limit` 128m → **256m**, `mem_reservation` 64m → **128m** (Beat imports `automation/captcha` modules on import — ~225MB RSS actual usage) | `compose/backend.yml:225` | Beat stops restarting with exit code 137 |
| **SKIP_MIGRATIONS=false**: Migration now runs automatically at startup protected by a PostgreSQL session-level advisory lock | `compose/backend.yml:44` | Deploy tooling must call `run_migrations()` rather than raw Alembic |
| **Alembic 027 column widening**: `ALTER TABLE alembic_version ALTER COLUMN version_num TYPE VARCHAR(255)` — default is VARCHAR(32) but revision `027_add_fuel_inquiry_error_category` is 35 chars | `alembic/versions/027_add_fuel_inquiry_error_category.py` | Migrations no longer fail with `value too long for type character varying(32)` |
| **Alembic 029 CONCURRENT index fix**: `op.execute("COMMIT")` before `CREATE INDEX CONCURRENTLY IF NOT EXISTS` (can't run inside Alembic transaction); fixed `down_revision = "028_submission_unconfirmed_category"` | `alembic/versions/029_add_waybill_jobs_optimization_indexes.py` | 3 optimization indexes created successfully |
| **Playwright CDN fix**: `ENV PLAYWRIGHT_DOWNLOAD_HOST=https://npmmirror.com/mirrors/playwright` (cdn.playwright.dev blocked from Iran) | `Dockerfile:83` | Chromium downloads during Docker build |
| **Worker Node fixes**: local `image: barpro_backend:latest` (not GHCR), `env_file: [../.env]`, fast Redis+proc healthcheck (replaces slow `celery inspect ping` which timed out at 11–17s due to central Redis latency), `squid:host-gateway` extra_hosts | `compose/worker-node.yml` | Remote workers 2 & 3 start and stay healthy |
| **RAM upgrade for 16GB server**: PostgreSQL 1g→**1.5g**, Redis 256m→**512m** (+`maxmemory 400mb`), Backend API 256m→**512m**, Worker 1 2.5g→**3g**, Frontend 512m→**1g**, Nginx 256m→**512m** | `compose/infra.yml`, `compose/backend.yml`, `compose/web.yml` | Smooth UI, faster API response, more Chrome/PyTorch headroom |
| **manage.sh improvements**: +`beat-restart` (force-recreate Beat), +`logs [service]` (live log tail), fixed `backup-db` DB name from env, improved `deploy` (build+up+migrate+health) | `manage.sh` | Operational convenience |
| **New deploy script** `scripts/quick_deploy_central.sh`: 10-step fully automated central server deploy (pull → build → beat restart → web → monitoring → migrate → verify) | `scripts/quick_deploy_central.sh` | One-command deploy |
| **New setup script** `scripts/setup_worker.sh`: automated worker node setup from scratch (Docker install → config → build → up → verify registry) | `scripts/setup_worker.sh` | Reproducible worker deployment |
| **.env.example completed**: Added `WORKER_ID`, `WORKER_IP_INDEX`, `WORKER_PROXY_PORT`, `CENTRAL_IP`, `GRAFANA_ADMIN_USER/PASSWORD`, `GRAFANA_ROOT_URL`, `AUTH_COOKIE_SECURE` | `.env.example` | Template covers all required variables |
| **Volume permissions fix** (server action): `chown -R 10001:10001 /var/lib/docker/volumes/barpro_runtime_data/_data/` + mkdir auth/screenshots/output | Applied on central server | Backend starts without PermissionError |

> **Historical deployment snapshot (2026-08-04; not current evidence):**
> - PostgreSQL: `barpro_runtime_data` at Alembic head `029` (25 tables)
> - Workers 2 & 3: healthy, registered in `worker_registry`
> - Celery Beat: `mem_limit=256m` — OOM resolved
> - Frontend + Nginx: mem_limit=1g+512m
> - All services tested healthy via `manage.sh health`

---

*Historical snapshot dated 2026-08-04; do not use its test/deployment status as
current runtime evidence.*

---

### Additional Fixes Applied (2026-08-08) — Soft-Cancel Intent Sync, Proxy Fail-Closed, Scheduler Enforcement & CI Fixes

| Change | File(s) | Impact |
|--------|---------|--------|
| **Historical soft-cancel implementation (superseded)**: an earlier `delete_job` cancelled intents. The current API contract is permanent DELETE; do not implement cancellation from this changelog entry. | `app/services/waybill_job_service.py`, `app/orchestrator/dispatcher_service.py` | Historical context only; current route/service code is authoritative. |
| **Proxy fail-closed (production)**: New `ProxyUnavailableError` + `_proxy_fail_closed()` in `worker_proxy`. In production, unreachable/unset proxy raises instead of falling back to direct connection. Dev mode remains fail-open. `_claim_and_execute` / `_claim_and_reconcile` catch and map to `TRANSIENT_INFRA_ERROR` → `WAITING_RETRY`. `classify_exception` maps proxy keywords to retryable. | `app/automation/worker_proxy.py`, `app/workers/waybill_worker.py`, `app/core/error_taxonomy.py` | Prevents silent direct-connection fallback that bypasses proxy rotation/anti-bot; failed proxy now schedules retry with correct error category. |
| **Scheduler enforcement**: Per-job tenant/driver/quota checks before scheduling: client ACTIVE + subscription window, driver ACTIVE/READY, tenant in-flight < `max_concurrent_tasks`, tenant daily < `max_daily_tasks`. Caches client/driver lookups and counts per loop. | `app/orchestrator/scheduler_service.py` | Prevents scheduling jobs for suspended tenants, inactive drivers, or over-quota tenants. |
| **CI fixes**: Created missing `requirements-dev.txt` (pytest, ruff, black, mypy, aiosqlite); fixed indentation in `ci-cd.yml` step "Run Unit Tests". | `requirements-dev.txt`, `.github/workflows/ci-cd.yml`, `.github/workflows/ci-test.yml` | CI pipeline no longer fails on missing deps / YAML syntax. |
| **Frontend types**: Removed `access_token` from `AuthLoginResponse` / `AdminLoginResponse` — JWT now httpOnly cookie only. | `apps/web/src/lib/types.ts` | Aligns types with cookie-based auth; no token leakage to localStorage. |
| **String import fix**: Added missing `from sqlalchemy import String` in `waybill_job_service` (pre-existing bug in plate-number search filter). | `app/services/waybill_job_service.py` | Fixes `NameError` at runtime when plate filter is used. |
| **Test updates**: `test_redis_unavailable` mocks `get_worker_proxy_url`; `test_worker_proxy_and_rotator` tests both dev fail-open and prod fail-closed; `test_reconciliation_service` sets `ENVIRONMENT=development`. | `tests/chaos/test_redis_unavailable.py`, `tests/test_worker_proxy_and_rotator.py`, `tests/test_reconciliation_service.py` | Tests pass with new proxy fail-closed logic. |

> **Verification:** `uvx ruff check` clean on touched files; `tsc --noEmit` + `eslint` clean on frontend; full pytest suite green (588 passed, 4 pre-existing UTCMS login failures, 2 skipped).

---

### Additional Fixes Applied (2026-08-10) — UTCMS Proxy Health Check & Scheduler FOR UPDATE Fix

| Change | File(s) | Impact |
|--------|---------|--------|
| Proxy health check target changed from `barname.utcms.ir` to `https://utcms.ir` (the root domain) — `barname.utcms.ir` redirects causing false health check failures | `app/api/routes/system.py`, `app/automation/proxy_rotator.py`, `app/automation/worker_proxy.py`, `scripts/verify_system_connections.py` | Prevents false-positive proxy health failures due to HTTP redirect; health checks now use stable root domain |
| Fixed PostgreSQL `FOR UPDATE SKIP LOCKED` on outer join by moving driver-slot check to subquery — PostgreSQL rejects `FOR UPDATE` on nullable side of outer join | `app/orchestrator/scheduler_service.py` | Scheduler no longer fails with `FOR UPDATE` error when claiming jobs with free driver slots |
| Updated test assertions to match new health check URL | `tests/test_worker_proxy_health.py` | Tests pass with new target URL |

> **Verification:** `uvx ruff check` clean on touched files; proxy health tests pass (28 tests in proxy/rotator/system health/readyz suites); scheduler subquery logic tested.

*Historical release snapshot dated 2026-08-20. Re-run tests and runtime
verification for the current commit; Alembic head documented for this checkout:
036_management_tables_and_activity_logs_fix.*

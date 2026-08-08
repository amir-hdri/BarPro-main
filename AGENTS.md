# BarPro — Agent Guide

> **📋 See also: [CRITICAL_RULES.md](./CRITICAL_RULES.md)** — خطوط قرمز و الزامات فنی حیاتی پروژه

## Project Identity

**BarPro** is a multi-tenant RPA (Robotic Process Automation) framework for automated waybill (بارنامه) registration on Iran's national transportation portal (barname.utcms.ir). It uses Playwright-driven browser automation with CAPTCHA solving (CNN/PyTorch fuel CRNN/Keras OCR), smart proxy rotation (Squid), and human-behavior simulation.

## Architecture Overview

```
Client Browser → Nginx (port 80/443) → FastAPI Backend (port 8000)
                                                    ├── PostgreSQL 16 (SQLModel/AsyncPG)
                                                    ├── Redis 7 (cache/queue/pub-sub)
                                                    ├── Celery Workers ×3 (via Squid proxies)
                                                    └── Prometheus (monitoring)
Frontend: Next.js 15 (TypeScript, Tailwind, React 19)
```

- **Single-server deployment**: All 13 Docker containers run on one server with 2 public IPs
- **13 Docker containers** managed via docker-compose layered files (`compose/`)
- **Nginx**: Configured with security headers (CSP, X-Frame-Options, X-Content-Type-Options, Permissions-Policy)

## Server Specifications

| Role | vCPU | RAM |
|------|------|-----|
| Central Server — UFW Firewall + Nginx (port 80), Backend, Frontend, Squid 1 egress | 4 | 12 GB |
| Worker Nodes — Remote VPS with static Iranian IP + local Squid proxy | — | — |

All containers run on the **central server** (single host, dual networking for egress IPs).

### Resource Constraints & Implications
- **12 GB RAM** must be shared across 13 containers — tight budget
- Celery Workers are already limited to 3 GB memory each → 9 GB for 3 workers
- Remaining: ~3 GB for PostgreSQL, Redis, Nginx, Frontend, Prometheus, Beat
- **4 vCPUs** means CPU contention under load — 3 workers + DB can saturate all cores
- Disk: ensure <90% utilization (Milestone 1 requirement)

## Tech Stack

| Layer | Technology | Version |
|-------|-----------|---------|
| Backend | Python / FastAPI | 3.11 / latest |
| Frontend | Next.js / TypeScript | 15 / 5.x |
| Database | PostgreSQL + SQLModel | 16 |
| Queue | Celery + Redis | latest |
| RPA | Playwright (Chromium) | latest |
| Proxy | Squid | latest (ubuntu/squid:latest) |
| Monitoring | Prometheus | latest |
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

## Deployment Topology

> **Current deployment (Model B — scale-out):** the central server has a **single public IP**
> (87.107.5.238). Multi-IP egress is provided by **remote Worker VPSes**, each with its own
> static Iranian IP and a local Squid proxy. Postgres/Redis bind `0.0.0.0` on the central
> server (`POSTGRES_BIND`/`REDIS_BIND` in `.env`) and are protected by the UFW allowlist
> (`scripts/setup_firewall_central.sh`, `scripts/add_worker_firewall.sh`).
> Workers 2/3 run on the remote nodes via `compose/worker-node.yml`; on the central server
> they are disabled by default (compose profile `scale-out`).

```
Central Server (single IP: <CENTRAL_IP> = 87.107.5.238)
├── PostgreSQL (port 5432, bind 0.0.0.0, UFW: workers only)
├── Redis (port 6379, bind 0.0.0.0, UFW: workers only)
├── Squid 1 (port 3128, egress via <CENTRAL_IP>)    ← Worker 1 (local)
├── FastAPI Backend (port 8000, internal)
├── Celery Worker 1 → Squid 1 → UTCMS
├── Celery Beat (scheduler)
├── Next.js Frontend (port 3000, internal)
├── Nginx (port 80, public) → reverse proxy
└── Prometheus (port 9090, exposed internally)

Remote Worker Nodes (each: 2 vCPU / ~6 GB / own static Iranian IP)
├── Squid (port 3128, egress via the Worker's own IP)   ← Workers 2/3
└── Celery Worker 2/3 → local Squid → UTCMS
    (via compose/worker-node.yml; DB/Redis at <CENTRAL_IP>)
```

### Squid Proxy Ports
| Proxy | Port | Egress IP | Used By |
|-------|------|-----------|---------|
| Squid 1 | 3128 | <CENTRAL_IP>    | Worker 1 |
| Squid 2 | 3129 | <SECONDARY_IP>  | Worker 2 |
| Squid 3 | 3130 | <SECONDARY_IP>  | Worker 3 |

### Network Flow
- **Public entry**: port 80 (HTTP) and 443 (HTTPS - ready for Let's Encrypt)
- **Internal**: Docker bridge network `barpro_platform`
- **UTCMS egress**: via Squid proxies using different IPs (anti-bot bypass)
- **Inter-node security**: UFW Firewall restricts database (5432) and Redis (6379) to registered Worker IPs only
- **Squid 2/3 ports (3129, 3130)**: should be firewall-restricted to localhost only (`scripts/secure_squid_ports.sh`)
- **DNS resolution**: Nginx uses Docker internal DNS (127.0.0.11) with 30s cache for dynamic container IP resolution

## Common Pitfalls

| Pitfall | Details | Status |
|---------|---------|--------|
| `except: pass` | Used extensively (~55+ locations); never catch silently — log at minimum | ✅ Fixed |
| `engine.dispose()` per Celery task | Destroys connection pool, causing connection storms | ✅ Fixed |
| `asyncio.Lock` on class instances | Race condition when event loop changes; use `threading.Lock` for init | ✅ Fixed |
| `autoretry_for = (Exception,)` | Retries programming bugs indefinitely; use specific exceptions | ✅ Fixed |
| Migration startup | `run_migrations()` is active with Redis distributed lock; avoid duplicate startup runners | ✅ Fixed |
| Event loop per Celery task | `asyncio.new_event_loop()` per task is extremely expensive | ✅ Fixed |
| Session not injected | Services create `AsyncSession` directly instead of using `get_session()` dependency | ✅ Fixed |
| Race condition in Redis manager | Double-checked locking pattern is broken for async (redis.py:36-53) | ✅ Fixed |
| Zod v3 ↔ v4 mismatch | Keep imports from `zod`, not `zod/v4`, because package is `zod@3.24.1` | ✅ Fixed |
| Heroicons rename | Use current Heroicons v2 names such as `ArrowRightStartOnRectangleIcon` | ✅ Fixed |
| Hardcoded secrets in workflows | CI/CD workflows had fallback hardcoded credentials | ✅ Fixed |
| Missing security headers | Backend responses lacked security headers | ✅ Fixed |
| Missing Redis connection pool settings | No timeout/retry configuration | ✅ Fixed |

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
- **Current status**: 552 passed, 2 skipped, 0 failed

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
│   ├── infra.yml           # PostgreSQL, Redis
│   ├── proxy.yml           # Squid ×3
│   ├── backend.yml         # FastAPI + Celery workers + Beat
│   ├── web.yml             # Nginx + Frontend
│   └── monitoring.yml      # Prometheus
├── infra/                  # Config files
│   ├── nginx/nginx.conf
│   ├── squid/squid_*.conf
│   ├── prometheus/prometheus.yml
│   └── logging/logrotate.conf
├── alembic/                # Database migrations; current head 029_add_waybill_jobs_optimization_indexes
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
docker compose -f compose/proxy.yml up       # Squid proxies only
docker compose -f compose/backend.yml up     # Backend + workers
docker compose -f compose/web.yml up         # Nginx + Frontend
docker compose -f compose/monitoring.yml up  # Prometheus only
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
| `CAPTCHA_MODE` | provider_only / manual_fallback |
| `CAPTCHA_TIMEOUT_SECONDS` | Max time to solve captcha (default 120) |
| `CAPTCHA_MAX_RETRIES` | Max auto retries (default 2) |
| `KERAS_PYTHON_PATH` | Python 3.12 path for Keras OCR (e.g. /opt/barpro/venv/bin/python) |
| `KERAS_MODEL_PATH` | Keras .keras model file for fuel inquiry captchas |
| `CAPTCHA_LOCAL_FALLBACK_ENABLED` | Enable Tesseract/local OCR fallback |
| `AVAILABLE_IP_INDICES` | Comma-separated IP indices for proxy routing (e.g., "1,2") |
| `RPA_PROXIES` | Comma-separated proxy URLs for workers (SSRF risk — see ISSUES.md) |

## Two Captcha Models

| Page | Solver | Model | Provider Name |
|------|--------|-------|---------------|
| **Login** (math: "2+3") | PyTorch CNN | `app/automation/captcha/assets/captcha_cnn.pth` | `cnn` |
| **Fuel Inquiry** (Persian words) | PyTorch CRNN | `app/automation/captcha/assets/fuel_captcha_crnn.pth` + vocab | `pytorch_fuel` |
| **Fuel Inquiry fallback** | Keras OCR | `persian_number_ocr.keras` (project root) | `keras_ocr` |

Default `CAPTCHA_PROVIDER=auto` tries CNN → PyTorch fuel → Keras → Enhanced → Local in sequence.

## Optimization Applied (2026-06-30)

The following optimizations have been implemented in this codebase:

### Performance
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
| Container resource limits tuned for 12 GB | `compose/*.yml` | Total 10.5 GB limits, 1.5 GB headroom |
| Queue routing: scheduler moved to Worker 3 | `compose/backend.yml:107,173` | Worker 1 not blocked by scheduler |

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
| Celery Beat | **256 MB** | 128 MB | — | ↑ از 128 MB (OOM fix) |
| Frontend (Next.js) | **1 GB** | 512 MB | — | ↑ از 512 MB |
| Nginx | **512 MB** | 256 MB | — | ↑ از 256 MB |
| Squid ×3 | 128 MB each | 64 MB each | — | — |
| Prometheus | 256 MB | 128 MB | — | — |
| Alertmanager | 128 MB | 64 MB | — | — |
| Grafana | 256 MB | 128 MB | — | — |
| **Total limits** | **~8.9 GB** ← fits in 16 GB with ~7 GB headroom | | | |

> Workers 2/3 (هر کدام 3 GB) روی Remote Worker VPS اجرا می‌شوند و در بودجه سرور مرکزی نیستند.

## Priority Fixes for Server Deployment (see ISSUES.md for full list)

### ✅ Fixed (all applied and pushed)

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
| 16 | Fix alembic migrations | ✅ `run_migrations()` now functional with Redis distributed lock — runs on startup via `database.py` |
| 17 | Add container vulnerability scanning | ⬜ Future work |

### ✅ Optimizations Applied

| Change | File(s) |
|--------|---------|
| Nginx: separated HTTP/HTTPS config via include | `infra/nginx/nginx.conf`, `infra/nginx/http-server.conf` |
| Migrations: Redis distributed lock prevents multi-worker deadlock | `app/core/database.py` |
| Deploy: `manage.sh deploy` now auto-runs `alembic upgrade head` | `manage.sh` |
| New: `manage.sh migrate` — run migrations manually | `manage.sh` |
| New: `scripts/run_migrations.sh` — standalone migration runner | `scripts/run_migrations.sh` |
| New: `scripts/secure_squid_ports.sh` — iptables for Squid 3129/3130 | `scripts/secure_squid_ports.sh` |

### Remaining User Actions (server-level, cannot automate)
1. **Install Let's Encrypt cert** → uncomment `listen 443` + `ssl` volume in `compose/web.yml` and `infra/nginx/nginx.conf:75-90`, then `bash manage.sh deploy`
2. **Run `bash manage.sh migrate`** on production DB (or just `bash manage.sh deploy` which auto-runs it)
3. **Run `sudo bash scripts/secure_squid_ports.sh`** to lock down Squid 3129/3130
4. **Add to crontab**: `@reboot sudo bash /opt/barpro/scripts/secure_squid_ports.sh`
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

> **Context:** Production deployment on 3-server Model B topology:
> Central (`87.107.5.238`, 16 GB), Worker 2 (`5.56.132.26`), Worker 3 (`87.107.5.219`).
> All fixes were validated against a running 25-table PostgreSQL at Alembic head `029`.

| Change | File(s) | Impact |
|--------|---------|--------|
| **Celery Beat OOMKilled fix**: `mem_limit` 128m → **256m**, `mem_reservation` 64m → **128m** (Beat imports `automation/captcha` modules on import — ~225MB RSS actual usage) | `compose/backend.yml:225` | Beat stops restarting with exit code 137 |
| **SKIP_MIGRATIONS=false**: Migration now runs automatically at startup protected by Redis distributed lock (prevents parallel execution across workers) | `compose/backend.yml:44` | No manual `alembic upgrade head` needed on deploy |
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

> **Deployment Status (2026-08-04):**
> - PostgreSQL: `barpro_runtime_data` at Alembic head `029` (25 tables)
> - Workers 2 & 3: healthy, registered in `worker_registry`
> - Celery Beat: `mem_limit=256m` — OOM resolved
> - Frontend + Nginx: mem_limit=1g+512m
> - All services tested healthy via `manage.sh health`

---

*Last updated: 2026-08-04 · Tests: 552 passed, 2 skipped · Deployment: 3-server Model B (Central 16GB + 2× remote Worker VPS)*

---

### Additional Fixes Applied (2026-08-08) — Soft-Cancel Intent Sync, Proxy Fail-Closed, Scheduler Enforcement & CI Fixes

| Change | File(s) | Impact |
|--------|---------|--------|
| **Soft-cancel sync**: `delete_job` now atomically cancels pending/claimed `DispatchIntent` rows when a job is soft-cancelled (CANCELLED status), preventing dispatcher from attempting invalid transitions. Dispatcher already had guard for CANCELLED jobs. | `app/services/waybill_job_service.py`, `app/orchestrator/dispatcher_service.py` | Eliminates race where cancelled jobs left stale intents that dispatcher would try to claim. |
| **Proxy fail-closed (production)**: New `ProxyUnavailableError` + `_proxy_fail_closed()` in `worker_proxy`. In production, unreachable/unset proxy raises instead of falling back to direct connection. Dev mode remains fail-open. `_claim_and_execute` / `_claim_and_reconcile` catch and map to `TRANSIENT_INFRA_ERROR` → `WAITING_RETRY`. `classify_exception` maps proxy keywords to retryable. | `app/automation/worker_proxy.py`, `app/workers/waybill_worker.py`, `app/core/error_taxonomy.py` | Prevents silent direct-connection fallback that bypasses proxy rotation/anti-bot; failed proxy now schedules retry with correct error category. |
| **Scheduler enforcement**: Per-job tenant/driver/quota checks before scheduling: client ACTIVE + subscription window, driver ACTIVE/READY, tenant in-flight < `max_concurrent_tasks`, tenant daily < `max_daily_tasks`. Caches client/driver lookups and counts per loop. | `app/orchestrator/scheduler_service.py` | Prevents scheduling jobs for suspended tenants, inactive drivers, or over-quota tenants. |
| **CI fixes**: Created missing `requirements-dev.txt` (pytest, ruff, black, mypy, aiosqlite); fixed indentation in `ci-cd.yml` step "Run Unit Tests". | `requirements-dev.txt`, `.github/workflows/ci-cd.yml`, `.github/workflows/ci-test.yml` | CI pipeline no longer fails on missing deps / YAML syntax. |
| **Frontend types**: Removed `access_token` from `AuthLoginResponse` / `AdminLoginResponse` — JWT now httpOnly cookie only. | `apps/web/src/lib/types.ts` | Aligns types with cookie-based auth; no token leakage to localStorage. |
| **String import fix**: Added missing `from sqlalchemy import String` in `waybill_job_service` (pre-existing bug in plate-number search filter). | `app/services/waybill_job_service.py` | Fixes `NameError` at runtime when plate filter is used. |
| **Test updates**: `test_redis_unavailable` mocks `get_worker_proxy_url`; `test_worker_proxy_and_rotator` tests both dev fail-open and prod fail-closed; `test_reconciliation_service` sets `ENVIRONMENT=development`. | `tests/chaos/test_redis_unavailable.py`, `tests/test_worker_proxy_and_rotator.py`, `tests/test_reconciliation_service.py` | Tests pass with new proxy fail-closed logic. |

> **Verification:** `uvx ruff check` clean on touched files; `tsc --noEmit` + `eslint` clean on frontend; full pytest suite green (588 passed, 4 pre-existing UTCMS login failures, 2 skipped).

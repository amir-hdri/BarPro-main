# BarPro — Agent Guide

## Project Identity

**BarPro** is a multi-tenant RPA (Robotic Process Automation) framework for automated waybill (بارنامه) registration on Iran's national transportation portal (barname.utcms.ir). It uses Playwright-driven browser automation with CAPTCHA solving (CNN/PyTorch fuel CRNN/Keras OCR), smart proxy rotation (Squid), and human-behavior simulation.

## Architecture Overview

```
Client Browser → Nginx (port 80, no HTTPS) → FastAPI Backend (port 8000)
                                                   ├── PostgreSQL 16 (SQLModel/AsyncPG)
                                                   ├── Redis 7 (cache/queue)
                                                   ├── Celery Workers ×3 (via Squid proxies)
                                                   └── Prometheus (monitoring)
Frontend: Next.js 15 (TypeScript, Tailwind, React 19)
```

- **Single-server deployment**: All 13 Docker containers run on one server with 2 public IPs
- **13 Docker containers** managed via docker-compose layered files (`compose/`)

## Server Specifications

| IP | Role | vCPU | RAM |
|----|------|------|-----|
| 188.121.123.16 | Primary IP — Nginx (port 80), Backend, Frontend, Squid 1 egress | 4 | 12 GB |
| 95.38.233.90 | Secondary IP — Squid 2 (port 3129) and Squid 3 (port 3130) egress | — | — |

Both IPs point to the **same physical server** (single host, dual networking).

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

```
Single Server (188.121.123.16 + 95.38.233.90)
├── PostgreSQL (port 5432, internal only)
├── Redis (port 6379, internal only)
├── Squid 1 (port 3128, egress via 188.121.123.16) ← Worker 1
├── Squid 2 (port 3129, egress via 95.38.233.90)   ← Worker 2
├── Squid 3 (port 3130, egress via 95.38.233.90)   ← Worker 3
├── FastAPI Backend (port 8000, internal)
├── Celery Worker 1 → Squid 1 → UTCMS (egress via 188.121.123.16)
├── Celery Worker 2 → Squid 2 → UTCMS (egress via 95.38.233.90)
├── Celery Worker 3 → Squid 3 → UTCMS (egress via 95.38.233.90)
├── Celery Beat (scheduler)
├── Next.js Frontend (port 3000, internal)
├── Nginx (port 80, public) → reverse proxy
└── Prometheus (port 9090, public — INSECURE)
```

### Squid Proxy Ports
| Proxy | Port | Egress IP | Used By |
|-------|------|-----------|---------|
| Squid 1 | 3128 | 188.121.123.16 | Worker 1 |
| Squid 2 | 3129 | 95.38.233.90 | Worker 2 |
| Squid 3 | 3130 | 95.38.233.90 | Worker 3 |

### Network Flow
- **Public entry**: only port 80 (Nginx)
- **Internal**: Docker bridge network `barpro_platform`
- **UTCMS egress**: via Squid proxies using different IPs (anti-bot bypass)
- **Squid 2/3 ports (3129, 3130)**: should be firewall-restricted to localhost only

## Common Pitfalls

| Pitfall | Details |
|---------|---------|
| `except: pass` | Used extensively (~30+ locations); never catch silently — log at minimum |
| `engine.dispose()` per Celery task | Destroys connection pool, causing connection storms |
| `asyncio.Lock` on class instances | Race condition when event loop changes; use `threading.Lock` for init |
| `autoretry_for = (Exception,)` | Retries programming bugs indefinitely; use specific exceptions |
| Migration startup | `run_migrations()` is active with Redis distributed lock; avoid duplicate startup runners |
| Event loop per Celery task | `asyncio.new_event_loop()` per task is extremely expensive |
| Session not injected | Services create `AsyncSession` directly instead of using `get_session()` dependency |
| Race condition in Redis manager | Double-checked locking pattern is broken for async (redis.py:36-53) |
| Zod v3 ↔ v4 mismatch | Keep imports from `zod`, not `zod/v4`, because package is `zod@3.24.1` |
| Heroicons rename | Use current Heroicons v2 names such as `ArrowRightStartOnRectangleIcon` |

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
├── alembic/                # Database migrations; current head 015_add_client_subscription_dates
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

## Memory Budget (12 GB RAM)

| Container | Limit | Reservation | shm_size |
|-----------|-------|-------------|----------|
| PostgreSQL | 1 GB | 512 MB | — |
| Redis | 256 MB | 128 MB | — |
| Backend API | 256 MB | 128 MB | 256 MB |
| Celery Worker 1 | 2.5 GB | 2 GB | 512 MB |
| Celery Worker 2 | 2.5 GB | 2 GB | 512 MB |
| Celery Worker 3 | 2.5 GB | 2 GB | 512 MB |
| Celery Beat | 128 MB | 64 MB | — |
| Frontend (Next.js) | 512 MB | 256 MB | — |
| Nginx | 256 MB | 128 MB | — |
| Squid ×3 | 128 MB each | 64 MB each | — |
| Prometheus | 256 MB | 128 MB | — |
| **Total limits** | **~10.5 GB** ← fits in 12 GB with ~1.5 GB headroom | | |

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

> Verification: `pip-audit` → *No known vulnerabilities found*; `npm audit --omit=dev` (apps/web) → 0 vulnerabilities; GitHub Dependabot no longer flags the default branch. `tsc --noEmit` and `next lint` pass on `apps/web`.

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

---

*Last updated: 2026-07-21 · Deployment: single server, dual IP (4 vCPU, 12 GB RAM)*



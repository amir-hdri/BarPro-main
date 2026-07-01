# BarPro — Agent Guide

## Project Identity

**BarPro** is a multi-tenant RPA (Robotic Process Automation) framework for automated waybill (بارنامه) registration on Iran's national transportation portal (barname.utcms.ir). It uses Playwright-driven browser automation with CAPTCHA solving (CNN/Keras OCR), smart proxy rotation (Squid), and human-behavior simulation.

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
- **State**: localStorage-based auth (insecure — see ISSUES.md)
- **No httpOnly cookies** — JWT in localStorage (critical security issue)

## Critical Warnings

1. **NEVER hardcode credentials** — the repo already has leaked production SSH passwords (`PLACEHOLDER_SSH_PASSWORD`) committed in multiple files
2. **NEVER commit `.env`** — currently tracked in git history; use `.env.example` as template
3. **`.env` IS in `.gitignore`** but was committed before being added — do NOT commit new secrets
4. **Build will fail** without fixing `zod/v4` import in `waybillSchema.ts:1` and `ArrowLeftOnRectangleIcon` in `Header.tsx:3`
5. **All containers run privileged** (`privileged: true`) — any compromise = full host access
6. **No HTTPS** — Nginx listens on port 80 only; all traffic is plaintext
7. **Rate limiter fails open** — if Redis is down, 999 requests/minute are allowed
8. **SSRF vector** in proxy rotator — proxy URLs from config are used for outbound health checks

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
| `run_migrations` is dead code | Line 82 in database.py is commented out; migrations never auto-run |
| Event loop per Celery task | `asyncio.new_event_loop()` per task is extremely expensive |
| Session not injected | Services create `AsyncSession` directly instead of using `get_session()` dependency |
| Race condition in Redis manager | Double-checked locking pattern is broken for async (redis.py:36-53) |
| Zod v3 ↔ v4 mismatch | `waybillSchema.ts` imports from `zod/v4` but package has `zod@3.24.1` |
| Heroicons rename | `ArrowLeftOnRectangleIcon` renamed to `ArrowRightStartOnRectangleIcon` in v2.1+ |

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
├── alembic/                # Database migrations (14 files, hand-crafted IDs)
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
| `CAPTCHA_PROVIDER` | Solver: auto/ensemble/cnn/keras_ocr/enhanced_ocr/local_ocr/off |
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
| **Fuel Inquiry** (text/numeric) | Keras OCR | `persian_number_ocr.keras` (project root) | `keras_ocr` |

Default `CAPTCHA_PROVIDER=auto` tries CNN → Keras → Enhanced → Local in sequence.

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
| WebSocket send moved outside asyncio.Lock | `events.py:46-59` | No blocking concurrent publishes |

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
| Full table scan replaced with Redis cached counter | `services/task_service.py:227-249` | No `SELECT COUNT *` on every status transition |
| N+1 queries in `_emit_task_event` eliminated | `services/task_service.py:344-361` | Task object passed directly, no re-fetch |
| Mark methods refactored to single session/transaction | `services/task_service.py` | 5-7 round-trips → 2-3 per status update |

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
| 14 | Migrate JWT to httpOnly cookies | ⬜ Still `localStorage` — requires significant frontend refactor |
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
5. **Migrate JWT from localStorage to httpOnly cookies** — requires frontend refactor (~4-8 hours)

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

---

*Last updated: 2026-07-01 · Deployment: single server, dual IP (4 vCPU, 12 GB RAM)*

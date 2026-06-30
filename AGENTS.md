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
| `CAPTCHA_PROVIDER` | OCR engine: keras_ocr / cnn / local_ocr / enhanced_ocr / ensemble |
| `AVAILABLE_IP_INDICES` | Comma-separated IP indices for proxy routing (e.g., "1,2") |
| `RPA_PROXIES` | Comma-separated proxy URLs for workers (SSRF risk — see ISSUES.md) |

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

### Memory / Stability
| Change | File | Impact |
|--------|------|--------|
| Page listeners removed on page close | `automation/browser.py:463-465` | No listener leak over 1000+ pages |
| Timeouts added to all browser close operations | `automation/browser.py:139-176` | No hang on context/browser close |
| `except: pass` replaced with logging in recycle_browser | `automation/browser.py:139-176` | Errors visible in logs |
| Container resource limits added (all services) | `compose/*.yml` | No OOM risk on 12 GB |
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

| Container | Limit | Reservation |
|-----------|-------|-------------|
| PostgreSQL | 1 GB | 512 MB |
| Redis | 512 MB | 256 MB |
| Backend API | 512 MB | 256 MB |
| Celery Worker 1 | 3 GB | 2 GB |
| Celery Worker 2 | 3 GB | 2 GB |
| Celery Worker 3 | 3 GB | 2 GB |
| Celery Beat | 256 MB | 128 MB |
| Frontend (Next.js) | 512 MB | 256 MB |
| Nginx | 256 MB | 128 MB |
| Squid ×3 | 256 MB each | 128 MB each |
| Prometheus | 512 MB | 256 MB |
| **Total** | **~12.8 GB** | **~8.9 GB** |

## Priority Fixes for Server Deployment (see ISSUES.md for full list)

### Tier 1 — Security (fix before exposing to internet)
1. Rotate all leaked credentials (`PLACEHOLDER_SSH_PASSWORD`, API keys in `.agents/`)
2. Purge `.env` from git history
3. Fix `zod/v4` import → `zod` (build break)
4. Fix `ArrowLeftOnRectangleIcon` → `ArrowRightStartOnRectangleIcon` (build break)
5. Add HTTPS to Nginx (currently plain HTTP)
6. Remove `privileged: true` from all containers
7. Fix rate limiter fail-open (default: 999 req/min)
8. Restrict Prometheus port 9090 (no auth)

### Tier 2 — Stability (fix for production reliability)
9. Run PostgreSQL indexes from optimization section above
10. Fix all remaining `except: pass` blocks (~30+ locations)
11. Fix Redis connection manager race condition
12. Apply rate limiting to ALL API endpoints
13. Fix browser context leaks (OOM risk on 12 GB)

### Tier 3 — Maintenance
14. Migrate JWT from localStorage to httpOnly cookies
15. Remove `network_mode: host` from Squid containers
16. Fix alembic migrations (dead code)
17. Add container image vulnerability scanning

---

*Last updated: 2026-06-30 · Deployment: single server, dual IP (4 vCPU, 12 GB RAM)*

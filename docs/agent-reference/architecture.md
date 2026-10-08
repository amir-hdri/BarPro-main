# Architecture, stack and repository layout

> Scope: BarPro only. Read this file when relevant to the task; do not auto-import
> the whole reference directory into global rules or the always-loaded core.
> **REFERENCE SNAPSHOT, NOT LIVE EVIDENCE.** Original claims and dates are preserved.
> Even headings such as “Current” and statuses such as “Fixed” reflect the source
> guide, not a fresh verification. Resolve drift against current code and contracts
> before acting; deployment state requires timestamped runtime evidence.

Read when: Architecture, dependency or file-layout work.

[Core guide](../../AGENTS.md) · [Reference index](README.md) · [Critical rules](../../CRITICAL_RULES.md)

Paths inside preserved text and command examples are relative to the repository
root, not this directory. Commands are examples, not automatic execution steps.

<!-- original-agents:0056-0079:start -->
## Architecture Overview

```
Client Browser → Nginx (port 80; 443 only after TLS activation) → FastAPI Backend (port 8000)
                                                    ├── PostgreSQL 16 (SQLModel/AsyncPG)
                                                    ├── Redis 7 (cache/queue/pub-sub)
                                                    ├── Redroid (Android 11, virtual server-side GPS via FakeTraveler)
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
  Central runs API + Worker 1 + Scheduler + Beat + Redroid + Squid 1 on 32 GB RAM / 8 vCPU; Workers 2/3 run on
  remote VPS nodes. Live state still requires timestamped verification.
- **Layered Docker services** managed via docker-compose files (`compose/`); the exact
  live container count is topology-dependent and must be verified with full `docker ps`
- **Root `docker-compose.yml`** uses `include:` (Compose >= 2.20) to assemble all layers — CI/CD and deploy scripts MUST use `docker compose` V2 (not `docker-compose` V1)
- **Nginx**: Configured with security headers (CSP, X-Frame-Options, X-Content-Type-Options, Permissions-Policy)

<!-- original-agents:0056-0079:end -->

<!-- original-agents:0119-0131:start -->
## Tech Stack

| Layer | Technology | Version |
|-------|-----------|---------|
| Backend | Python / FastAPI | 3.11 / latest |
| Frontend | Next.js / TypeScript | 15 / 5.x |
| Database | PostgreSQL + SQLModel | 16 |
| Queue | Celery + Redis | latest |
| RPA | Playwright (Chromium) | latest |
| Virtual Android | Redroid (Android 11, server-side via binderfs) | 11.0.0-latest |
| Proxy | Squid | latest (ubuntu/squid:latest) |
| Monitoring | Prometheus + Alertmanager + Grafana + exporters | pinned in `compose/monitoring.yml` |
| Reverse Proxy | Nginx | 1.27-alpine |

<!-- original-agents:0119-0131:end -->

<!-- original-agents:0390-0438:start -->
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
│   ├── rpa/                # RPA services (auth, submit, scheduler)
│   └── travel/             # Travel simulation engine (GPS, route, speed, clock)
│       ├── geometry.py     # Spherical geometry (haversine, polyline, PathIndex)
│       ├── route.py        # RouteGeometry, RouteSegment
│       ├── speed.py        # SpeedProfile, SpeedSolution (kinematic solver)
│       ├── clock.py        # TravelClock (monotonic, pause-aware)
│       ├── state.py        # TravelStatus state machine
│       ├── engine.py       # TravelEngine → TravelSample (drift-free)
│       └── providers.py    # FakeGpsProvider → Android/Redroid
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
├── alembic/                # Database migrations; current head 041_driver_plate_tracking_fields
├── tests/                  # Pytest test suite
├── scripts/                # Utility and deploy scripts
└── deploy/                 # Deployment configs
```

<!-- original-agents:0390-0438:end -->

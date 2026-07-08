# BarPro

BarPro is a multi-tenant RPA system for automated waybill registration on Iran's UTCMS transportation portal. It combines a FastAPI backend, Playwright browser automation, CAPTCHA solving, Celery workers, Redis, PostgreSQL, and a Next.js web interface.

## Architecture

```text
Client Browser -> Nginx :80 -> Next.js frontend :3000
                              -> FastAPI backend :8000
                                   -> PostgreSQL 16
                                   -> Redis 7
                                   -> Celery workers
                                   -> Squid proxies
```

The production target is a single server with two public IPs. All services run through layered Docker Compose files under `compose/`.

## Main Components

- `app/` - FastAPI backend, RPA automation, services, workers, models
- `apps/web/` - Next.js 15 frontend
- `compose/` - Docker Compose layers
- `infra/` - Nginx, Squid, Prometheus, logging config
- `alembic/` - database migrations; current head is `015_add_client_subscription_dates`
- `tests/` - pytest suite

## Quick Start

```bash
cp .env.example .env
# edit .env and set all secrets
bash manage.sh start
bash manage.sh health
```

For production updates:

```bash
git pull
bash manage.sh deploy
```

## Authentication

- JWT is transported by the backend through the `httpOnly` cookie `utcms_auth_token`
- The frontend sends requests with credentials enabled
- localStorage is limited to non-sensitive UI/session metadata
- Keep `AUTH_COOKIE_SECURE=false` on HTTP deployments
- Set `AUTH_COOKIE_SECURE=true` after HTTPS is enabled

## Frontend

- Framework: Next.js 15, React 19, TypeScript
- Package manager: npm lockfile is present for Docker builds
- Docker build: `apps/web/Dockerfile` performs a full multi-stage build
- No prebuilt `.next/standalone` directory is required before deployment

## CAPTCHA Providers

Supported `CAPTCHA_PROVIDER` values:

- `auto`
- `composite`
- `cnn`
- `pytorch_fuel`
- `keras_ocr`
- `enhanced_ocr`
- `local_ocr`
- `off`

Required runtime assets:

- `app/automation/captcha/assets/captcha_cnn.pth`
- `app/automation/captcha/assets/fuel_captcha_crnn.pth`
- `app/automation/captcha/assets/fuel_captcha_vocab.json`
- `persian_number_ocr.keras`

## Useful Commands

```bash
bash manage.sh status
bash manage.sh health
bash manage.sh logs backend
bash manage.sh migrate
bash manage.sh backup
```

## Verification

The latest local verification included:

- Backend Docker image build
- Frontend Docker image build
- Frontend production build
- Production npm audit with zero vulnerabilities
- Focused backend tests for config, auth, admin, and scheduling
- Alembic head check

Last updated: 2026-07-08

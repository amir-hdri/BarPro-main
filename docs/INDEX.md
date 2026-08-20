# BarPro Documentation Index

## مراجع عملیاتی اصلی

- [قرارداد و محدودیت‌های UTCMS](UTCMS_CONSTRAINTS.md) — فیلدهای اجباری، CAPTCHA، IP/WAF، زمان‌بندی، صف‌ها و معیار اثبات ثبت
- [Runbook قطعی/اختلال UTCMS](runbook_utcms_outage.md)
- [Runbook استقرار Scale-out](runbook_scale_out.md)
- [Runbook ثبت Worker](runbook_worker_registration.md)

Use this index for current operational documentation. Older historical reports remain under `docs/archive/` and should not be treated as deployment instructions.

## Start Here

| Document | Purpose |
|---|---|
| `README.md` | Current project overview and verified readiness state |
| `DEPLOYMENT_GUIDE.md` | Production deployment checklist |
| `SERVER_STATUS.md` | Current server/runtime status summary |
| `docs/guides/QUICK_START.md` | Local and Docker quick start |
| `docs/guides/START_SYSTEM.md` | Day-to-day startup commands |
| `docs/operations/DEPLOYMENT_GUIDE.md` | Operations deployment checklist |
| `docs/operations/production_deployment.md` | Production runtime notes |
| `docs/CHANGELOG.md` | Release history |

## Current Architecture

- Backend: FastAPI under `app/`
- Frontend: Next.js 15 under `apps/web/`
- Database: PostgreSQL 16
- Queue/cache: Redis 7 and Celery
- Browser automation: Playwright Chromium
- Reverse proxy: Nginx on port `80`
- Deployment: Docker Compose layers in `compose/`

## Core Commands

```bash
bash manage.sh start
bash manage.sh status
bash manage.sh health
bash manage.sh deploy
bash manage.sh migrate
bash manage.sh backup
bash manage.sh stop
```

## Important Current State

- Alembic head is `036_management_tables_and_activity_logs_fix`
- Frontend Docker builds inside `apps/web/Dockerfile`
- No prebuilt `.next/standalone` upload is required
- JWT transport uses the `httpOnly` cookie `utcms_auth_token`
- Keep `AUTH_COOKIE_SECURE=false` on HTTP; switch to `true` after HTTPS
- Required captcha assets include CNN, PyTorch fuel CRNN, fuel vocab, and Keras fallback model
- Universal mobile anti-zoom enforced across iOS and Android

## Active Guides

| Category | Documents |
|---|---|
| Deployment | `DEPLOYMENT_GUIDE.md`, `docs/operations/DEPLOYMENT_GUIDE.md` |
| Server status | `SERVER_STATUS.md` |
| Development startup | `docs/guides/QUICK_START.md`, `docs/guides/START_SYSTEM.md` |
| Security and issues | `ISSUES.md`, `FIXES_SUMMARY.md` |
| Architecture | `AGENTS.md`, `AI_AGENT_GUIDE.md`, `ARCHITECTURE.md` |

## Verification Commands

```bash
python -m ruff check app tests
pytest
cd apps/web && npm run build && npm audit --omit=dev
docker compose -f compose/backend.yml build backend
docker compose -f compose/web.yml build frontend
alembic heads
```

## Archive Policy

Files in `docs/archive/` are historical records. They may mention old local paths, old auth storage, or previous frontend versions. Do not use them for current deployment decisions.

Last updated: 2026-08-20 (v2.9.2)

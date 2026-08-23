# BarPro Documentation Index

## مراجع عملیاتی اصلی

- [قرارداد و محدودیت‌های UTCMS](UTCMS_CONSTRAINTS.md) — فیلدهای اجباری، CAPTCHA، IP/WAF، زمان‌بندی، صف‌ها و معیار اثبات ثبت
- [قابلیت چندمسیره + فاصله/زمان](MULTI_ROUTE_FEATURE.md) — قالب مسیر، دستهٔ چندمسیره و محاسبهٔ فاصله/زمان جاده‌ای
- [Runbook قطعی/اختلال UTCMS](runbook_utcms_outage.md)
- [Runbook استقرار Scale-out](runbook_scale_out.md)
- [Runbook ثبت Worker](runbook_worker_registration.md)

Use this index for current operational documentation. Older historical reports remain under `docs/archive/` and should not be treated as deployment instructions.

## Start Here

| Document | Purpose |
|---|---|
| `README.md` | Project overview; runtime readiness claims require timestamped evidence |
| `ARCHITECTURE.md` | Canonical code-level architecture, API/state/schema/queue contracts, and runtime verification boundaries |
| `docs/BARPRO_KNOWLEDGE_GRAPH.md` | Tracked full-system knowledge graph with CODE-VERIFIED / CONFIG-TARGET / RUNTIME-VERIFICATION labels |
| `DEPLOYMENT_GUIDE.md` | Production deployment checklist |
| `docs/guides/QUICK_START.md` | Local and Docker quick start |
| `scripts/start_system.sh` | Day-to-day startup commands |
| `docs/operations/DEPLOYMENT_GUIDE.md` | Operations deployment checklist |
| `docs/CHANGELOG.md` | Release history |

## Current Architecture

- Backend: FastAPI under `app/`
- Frontend: Next.js 15 under `apps/web/`
- Database: PostgreSQL 16
- Queue/cache: Redis 7 and Celery
- Browser automation: Playwright Chromium
- Reverse proxy: Nginx on port `80`; HTTPS remains inactive until TLS is explicitly enabled and verified
- Deployment: Docker Compose layers in `compose/`
- Monitoring: Prometheus, Alertmanager, Grafana, and node/Redis/Postgres/Nginx exporters

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

- Alembic head is `038_add_multiroute_batch_distance`
- Frontend Docker builds inside `apps/web/Dockerfile`
- No prebuilt `.next/standalone` upload is required
- JWT transport uses the `httpOnly` cookie `utcms_auth_token`
- Keep `AUTH_COOKIE_SECURE=false` on HTTP; switch to `true` after HTTPS
- Required captcha assets include CNN, PyTorch fuel CRNN, fuel vocab, and Keras fallback model
- Keras runs in-process; the `17:30–08:00` OTP interval is predictive, not a guaranteed UTCMS window
- Waybill `success` requires three-witness reconciliation; browser success alone is not final
- Universal mobile anti-zoom enforced across iOS and Android

Server/container/firewall/environment claims are runtime facts. When direct evidence is
missing, document them as `requires runtime verification` rather than inferring them
from Compose or `.env.example`.

## Active Guides

| Category | Documents |
|---|---|
| Deployment | `DEPLOYMENT_GUIDE.md`, `docs/operations/DEPLOYMENT_GUIDE.md` |
| Server status | `docs/operations/TROUBLESHOOTING.md` |
| Development startup | `docs/guides/QUICK_START.md`, `scripts/start_system.sh` |
| Security and issues | `ISSUES.md` |
| Architecture | `docs/BARPRO_KNOWLEDGE_GRAPH.md`, `AGENTS.md`, `ARCHITECTURE.md` |

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

Files under `docs/architecture/` carrying a “Legacy design” banner are retained
for design history only. They may contain obsolete routes, schema or TLS assumptions;
the tracked knowledge graph and root `ARCHITECTURE.md` take precedence.

Last updated: 2026-08-23 (v2.9.4)

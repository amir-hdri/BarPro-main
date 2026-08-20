# Deployment Guide

This document is the current operational checklist for deploying BarPro on the production server.

## Current topology

- **Model B Scale-Out Deployment (Current Production):**
  - Central Server (16 GB RAM / 4 vCPU): API on port 8000, Web on port 3000, PostgreSQL on port 5432 (UFW protected), Redis on port 6379 (UFW protected), Celery Scheduler, Celery Beat, Celery Worker 1, and Squid 1 on port 3128.
  - Remote Worker Nodes: Dedicated VPS nodes in Iran with static IPs, running Celery Worker 2/3 and local Squid proxy (via `compose/worker-node.yml`).
- Public entrypoint: Nginx on port `80` (HTTP) and `443` (HTTPS ready).
- Dynamic hybrid proxy fallback: Clean Iranian Proxy Pool (Zero IP Restriction) automatically active.

## Before you deploy

- Pull the latest repository state into `/opt/barpro`
- Ensure `.env` exists and contains production secrets
- Keep `AUTH_COOKIE_SECURE=false` while the site is HTTP-only; set `true` once HTTPS is enabled
- Confirm required ML assets exist in the repo checkout
- Confirm disk usage stays below the project target threshold

Required assets:

- `persian_number_ocr.keras`
- `app/automation/captcha/assets/captcha_cnn.pth`
- `app/automation/captcha/assets/fuel_captcha_crnn.pth`
- `app/automation/captcha/assets/fuel_captcha_vocab.json`

## Deployment commands

Initial bring-up:

```bash
cd /opt/barpro
bash manage.sh start
```

Update an existing installation:

```bash
cd /opt/barpro
git pull
bash manage.sh deploy
```

Manual migration fallback:

```bash
cd /opt/barpro
bash manage.sh migrate
```

## What `manage.sh deploy` does

- Builds the backend image
- Builds the frontend image
- Runs database migrations via `alembic upgrade head`
- Restarts backend and web layers with Docker Compose

## Verified application state

- Current Alembic head is `036_management_tables_and_activity_logs_fix`
- Frontend Docker builds inside `apps/web/Dockerfile`
- No prebuilt `.next/standalone` upload is required
- JWT transport uses the `httpOnly` cookie `utcms_auth_token`
- Universal mobile anti-zoom and viewport locking enforced

## Validation after deploy

```bash
bash manage.sh status
bash manage.sh health
docker compose -f compose/backend.yml config
docker compose -f compose/web.yml config
```

Optional smoke check:

```bash
docker run --rm barpro_backend:latest python -c "from app.main import app; print(app.title)"
```

## Safe rollback approach

- Roll back with Git to a known good commit using normal, reviewable Git operations
- Re-run `bash manage.sh deploy`
- If the database schema changed incompatibly, restore from a known good backup before downgrading code

Do not use destructive Git commands in routine operational playbooks.

## Backups

Create an on-demand database backup:

```bash
cd /opt/barpro
bash manage.sh backup
```

Backups are written under `output/backups/`.

## Security follow-ups

- Run `sudo bash scripts/secure_squid_ports.sh` on the server
- Add the same script to `@reboot`
- Enable HTTPS before switching `AUTH_COOKIE_SECURE=true`
- Do not expose Redis or PostgreSQL publicly

## Troubleshooting

- If deploy warns about migrations, run `bash manage.sh migrate`
- If frontend fails to start, inspect `bash manage.sh logs frontend` and `bash manage.sh logs nginx`
- If auth fails after login, review cookie settings, CORS, and `FRONTEND_URL`
- If Compose config warns about unset secrets, review `.env`

Last updated: 2026-08-20 (v2.9.2)

# Deployment Guide

This document is the current operational checklist for deploying BarPro on the production server.

## Current topology

- Single host deployment with dual public IPs
- Public entrypoint: Nginx on port `80`
- Internal services: FastAPI `8000`, Next.js `3000`, PostgreSQL `5432`, Redis `6379`
- Three Squid egress proxies: `3128`, `3129`, `3130`
- Docker Compose files live under `compose/`

## Before you deploy

- Pull the latest repository state into `/opt/barpro`
- Ensure `.env` exists and contains production secrets
- Keep `AUTH_COOKIE_SECURE=false` while the site is HTTP-only
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
- Attempts `alembic upgrade head`
- Restarts backend and web layers with Docker Compose

## Verified application state

- Current Alembic head is `015_add_client_subscription_dates`
- Frontend Docker builds inside `apps/web/Dockerfile`
- No prebuilt `.next/standalone` upload is required
- JWT transport uses the `httpOnly` cookie `utcms_auth_token`
- Frontend no longer depends on sending Bearer tokens from localStorage

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

Last updated: 2026-07-08

# راهنمای استقرار BarPro در production

این سند وضعیت فعلی و تاییدشده استقرار BarPro را برای سرور production شرح می‌دهد.

## نمای کلی معماری

- استقرار فعلی روی **یک سرور** انجام می‌شود که دو IP عمومی دارد: `188.121.123.16` و `95.38.233.90`
- همه سرویس‌ها با Docker Compose لایه‌ای اجرا می‌شوند
- ورودی عمومی فقط از طریق Nginx روی پورت `80` است
- بک‌اند FastAPI روی پورت داخلی `8000` و فرانت‌اند Next.js روی پورت داخلی `3000` اجرا می‌شوند
- سه پروکسی Squid برای خروجی workerها استفاده می‌شوند: `3128`، `3129`، `3130`
- JWT از طریق کوکی `httpOnly` با نام `utcms_auth_token` حمل می‌شود

## پیش‌نیازهای سرور

- Ubuntu 22.04 یا مشابه
- Docker Engine و Docker Compose V2
- Git
- حداقل `4 vCPU` و `12 GB RAM`
- مسیر استقرار: `/opt/barpro`

## متغیرهای محیطی ضروری

فایل `.env` را از روی `.env.example` بسازید و حداقل این مقادیر را تنظیم کنید:

- `API_KEY`
- `JWT_SECRET`
- `POSTGRES_PASSWORD`
- `REDIS_PASSWORD`
- `DRIVER_ENCRYPTION_KEY`
- `MASTER_ADMIN_USERNAME`
- `MASTER_ADMIN_PASSWORD`
- `AUTH_COOKIE_SECURE=false` برای استقرار HTTP فعلی
- `CAPTCHA_PROVIDER=auto` یا یکی از `composite`, `cnn`, `pytorch_fuel`, `keras_ocr`, `enhanced_ocr`, `local_ocr`, `off`

> پس از فعال‌سازی HTTPS باید `AUTH_COOKIE_SECURE=true` شود.

## فایل‌ها و assetهای ضروری

این فایل‌ها باید در checkout سرور وجود داشته باشند:

- `persian_number_ocr.keras`
- `app/automation/captcha/assets/captcha_cnn.pth`
- `app/automation/captcha/assets/fuel_captcha_crnn.pth`
- `app/automation/captcha/assets/fuel_captcha_vocab.json`
- `alembic/versions/015_add_client_subscription_dates.py`

## استقرار اولیه

```bash
git clone <repo-url> /opt/barpro
cd /opt/barpro
cp .env.example .env
```

سپس `.env` را کامل کنید و استقرار را اجرا کنید:

```bash
bash manage.sh start
```

ترتیب لایه‌ها به این صورت است:

1. `infra` - PostgreSQL و Redis
2. `proxy` - Squid 1/2/3
3. `backend` - FastAPI, Celery workers, Celery Beat
4. `web` - Next.js و Nginx
5. `mon` - Prometheus

## دستورات اصلی عملیات

| دستور | کاربرد |
|---|---|
| `bash manage.sh start` | راه‌اندازی کل سیستم |
| `bash manage.sh stop` | توقف کل سیستم |
| `bash manage.sh restart` | ری‌استارت کل سیستم |
| `bash manage.sh status` | وضعیت کانتینرها، دیسک و RAM |
| `bash manage.sh health` | health check سرویس‌ها |
| `bash manage.sh logs backend` | مشاهده لاگ بک‌اند |
| `bash manage.sh deploy` | build, migration, restart |
| `bash manage.sh migrate` | اجرای دستی `alembic upgrade head` |
| `bash manage.sh backup` | backup فشرده PostgreSQL |

## روند انتشار نسخه جدید

```bash
cd /opt/barpro
git pull
bash manage.sh deploy
```

فرمان `deploy` این کارها را انجام می‌دهد:

- backend image را build می‌کند
- frontend image را build می‌کند
- migrationها را با `alembic upgrade head` اجرا می‌کند
- سرویس‌های backend و web را با `up -d --remove-orphans` به‌روزرسانی می‌کند

## وضعیت فرانت‌اند در Docker

- فایل `apps/web/Dockerfile` اکنون multi-stage است
- سرور دیگر به `.next/standalone` از قبل ساخته‌شده نیاز ندارد
- `docker compose -f compose/web.yml build frontend` از یک checkout تمیز build کامل را انجام می‌دهد

## وضعیت احراز هویت

- login از سمت بک‌اند کوکی `httpOnly` را set می‌کند
- فرانت‌اند دیگر Bearer token را از localStorage ارسال نمی‌کند
- localStorage فقط برای داده‌های غیرحساس UI/session استفاده می‌شود
- روی HTTP فعلی باید `AUTH_COOKIE_SECURE=false` بماند

## مایگریشن‌های تاییدشده

Alembic head فعلی:

```bash
015_add_client_subscription_dates
```

مهاجرت‌های جدید مرتبط:

- `014_add_year_month_to_fuel_inquiries.py`
- `015_add_client_subscription_dates.py`

## بررسی پس از استقرار

```bash
bash manage.sh status
bash manage.sh health
docker compose -f compose/backend.yml config
docker compose -f compose/web.yml config
```

در صورت نیاز، smoke check بک‌اند:

```bash
docker run --rm barpro_backend:latest python -c "from app.main import app; print(app.title)"
```

## امنیت و کارهای دستی باقی‌مانده

- برای Squidهای `3129` و `3130` اسکریپت `scripts/secure_squid_ports.sh` را با `sudo` اجرا کنید
- برای اجرای خودکار در reboot همان اسکریپت را به crontab اضافه کنید
- Prometheus را عمومی expose نکنید مگر آگاهانه
- هرگز secretها یا `.env` را commit نکنید

## فعال‌سازی HTTPS

استقرار فعلی HTTP-only است. پس از نصب گواهی TLS:

1. تنظیمات SSL در `infra/nginx/nginx.conf` و `compose/web.yml` را فعال کنید
2. مقدار `AUTH_COOKIE_SECURE=true` را در `.env` قرار دهید
3. `bash manage.sh deploy` را اجرا کنید

## خطاهای رایج

- اگر `docker compose ... config` درباره secretها هشدار داد، `.env` روی shell فعلی بارگذاری نشده یا کامل نیست
- اگر migration خودکار fail شد، `bash manage.sh migrate` را دستی اجرا کنید
- اگر فرانت‌اند بالا نیامد، `bash manage.sh logs frontend` و `bash manage.sh logs nginx` را بررسی کنید
- اگر login کار نکرد، مقدارهای `FRONTEND_URL`, `BACKEND_CORS_ORIGINS` و `AUTH_COOKIE_SECURE` را بررسی کنید

## وضعیت تایید فعلی

موارد زیر روی این شاخه تایید شده‌اند:

- `docker compose -f compose/backend.yml build backend`
- `docker compose -f compose/web.yml build frontend`
- `npm run build` در `apps/web`
- `npm audit --omit=dev` با خروجی بدون vulnerability
- `alembic heads` با head برابر `015_add_client_subscription_dates`

*آخرین بروزرسانی: 2026-07-08*

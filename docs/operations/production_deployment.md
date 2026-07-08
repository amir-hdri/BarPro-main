# استقرار production

این سند جمع‌بندی تنظیمات production برای BarPro در وضعیت فعلی پروژه است.

## مشخصات سرور فعلی

- `4 vCPU`
- `12 GB RAM`
- یک سرور واحد با دو IP عمومی
- Ubuntu 22.04 LTS یا مشابه

## سرویس‌های production

- `nginx` - ورودی عمومی روی پورت `80`
- `frontend` - Next.js 15 روی پورت داخلی `3000`
- `backend` - FastAPI روی پورت داخلی `8000`
- `postgres` - PostgreSQL 16
- `redis` - Redis 7
- `celery_worker_1`, `celery_worker_2`, `celery_worker_3`
- `celery_beat`
- `squid1`, `squid2`, `squid3`
- `prometheus`

## تنظیمات کلیدی production

- `AUTH_COOKIE_SECURE=false` تا قبل از فعال‌سازی HTTPS
- `CAPTCHA_PROVIDER=auto` در حالت پیش‌فرض
- `HEADLESS=true`
- secretها فقط در `.env`
- احراز هویت JWT فقط از طریق کوکی `httpOnly`

## استقرار

```bash
cd /opt/barpro
git pull
bash manage.sh deploy
```

در صورت استقرار اولیه:

```bash
cd /opt/barpro
bash manage.sh start
```

## بررسی سلامت

```bash
bash manage.sh status
bash manage.sh health
```

بررسی دستی endpointها:

```bash
curl http://127.0.0.1:8000/health
curl http://127.0.0.1:8000/docs
```

## مایگریشن و داده

- Alembic head فعلی `015_add_client_subscription_dates` است
- برای اجرای دستی migration از `bash manage.sh migrate` استفاده کنید
- برای backup دیتابیس از `bash manage.sh backup` استفاده کنید

## فرانت‌اند و build

- `apps/web/Dockerfile` multi-stage است
- دیگر نیازی به artifact از پیش‌ساخته `/.next/standalone` نیست
- production build با `npm run build` تایید شده است

## HTTPS

در حال حاضر deployment روی HTTP است. پس از نصب TLS:

1. تنظیمات SSL را در Nginx فعال کنید
2. `AUTH_COOKIE_SECURE=true` را تنظیم کنید
3. `bash manage.sh deploy` را دوباره اجرا کنید

## حداقل مانیتورینگ

- `bash manage.sh status`
- `bash manage.sh health`
- بررسی لاگ‌های `backend`, `frontend`, `nginx`
- بررسی مصرف RAM و disk

## کارهای امنیتی تکمیلی

- `sudo bash scripts/secure_squid_ports.sh`
- افزودن همان اسکریپت به `crontab` با `@reboot`
- عدم expose عمومی Redis, PostgreSQL و Squid 2/3

Last updated: 2026-07-08

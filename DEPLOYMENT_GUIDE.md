# راهنمای استقرار BarPro در production (نسخه v2.9.2)

این سند وضعیت فعلی و تاییدشده استقرار BarPro را برای سرور production شرح می‌دهد.

## نمای کلی معماری

- **توپولوژی اصلی (Model B — توزیع‌شده Scale-Out):**
  - **سرور مرکزی (Central Server):** ۱۶ گیگابایت RAM، ۴ هسته vCPU، شامل سرویس‌های Nginx (پورت 80/443)، بک‌اند FastAPI (پورت داخلی 8000)، فرانت‌اند Next.js 15 (پورت داخلی 3000)، دیتابیس PostgreSQL 16 (پورت 5432 با حفاظت UFW)، کش و صف Redis 7 (پورت 6379 با حفاظت UFW)، Celery Scheduler، Celery Beat، Celery Worker 1 و Squid 1 (پورت 3128).
  - **ورکر نودهای ریموت (Remote Worker Nodes):** سرورهای VPS اختصاصی در دیتاسنترهای داخلی ایران، هر کدام دارای IP استاتیک ایرانی تمیز، Celery Worker محلی و Squid محلی روی پورت 3128 (از طریق `compose/worker-node.yml`).
- **توپولوژی تک‌سرور (Model A):** تمام سرویس‌ها به همراه ۳ ورکر و ۳ پروکسی Squid روی یک سرور با ۲ یا چند IP عمومی.
- **استخر تمیز پروکسی ایرانی (Clean Iranian Proxy Pool):** سیستم اگریگیتور و پروب خودکار پروکسی‌های ایرانی جهت رفع قطعی محدودیت‌های IP در ثبت بارنامه و استعلام سهمیه سوخت.
- **احراز هویت و نشست:** توکن JWT از طریق کوکی امن `httpOnly` با نام `utcms_auth_token` منتقل می‌شود.
- **ارگونومی موبایل:** بهینه‌سازی کامل ضدزوم (iOS و Android) و قفل مقیاس Viewport.

## پیش‌نیازهای سرور مرکزی

- Ubuntu 22.04 LTS یا جدیدتر
- Docker Engine و Docker Compose V2 (`docker compose`)
- Git
- حداقل `4 vCPU` و `16 GB RAM`
- مسیر استقرار: `/opt/barpro`

## متغیرهای محیطی ضروری (`.env`)

فایل `.env` را بر اساس `.env.example` بسازید و تنظیم کنید:

- `API_KEY`
- `JWT_SECRET` (حداقل ۳۲ کاراکتر)
- `POSTGRES_PASSWORD`
- `REDIS_PASSWORD`
- `DRIVER_ENCRYPTION_KEY` (کلید Fernet ۳۲ بایتی)
- `MASTER_ADMIN_USERNAME`
- `MASTER_ADMIN_PASSWORD`
- `POSTGRES_BIND=0.0.0.0` (جهت اتصال ورکر نودهای ریموت تحت فایروال UFW)
- `REDIS_BIND=0.0.0.0` (جهت اتصال ورکر نودهای ریموت تحت فایروال UFW)
- `AUTH_COOKIE_SECURE=false` (برای استقرار HTTP فعلی؛ پس از فعال‌سازی HTTPS روی `true` تنظیم شود)
- `CAPTCHA_PROVIDER=auto` (یا یکی از `composite`, `cnn`, `pytorch_fuel`, `keras_ocr`, `enhanced_ocr`, `local_ocr`)

## فایل‌ها و مدل‌های ضروری CAPTCHA

این فایل‌ها باید در checkout سرور وجود داشته باشند:

- `persian_number_ocr.keras` (مدل Keras OCR فال‌بک سوخت)
- `app/automation/captcha/assets/captcha_cnn.pth` (مدل CNN حل کپچای ریاضی لاگین)
- `app/automation/captcha/assets/fuel_captcha_crnn.pth` (مدل CRNN حل کپچای متنی فارسی سوخت)
- `app/automation/captcha/assets/fuel_captcha_vocab.json` (دیکشنری واژگان کپچای سوخت)

## استقرار اولیه

```bash
git clone <repo-url> /opt/barpro
cd /opt/barpro
cp .env.example .env
# ویرایش و مقداردهی متغیرهای امنیتی .env
bash manage.sh start
```

ترتیب لایه‌های داکر کامپوز:

1. `infra` - PostgreSQL 16 و Redis 7
2. `proxy` - پروکسی Squid 1 (و Squid 2/3 در صورت اجرای تک‌سرور)
3. `backend` - FastAPI, Celery Worker 1, Celery Scheduler, Celery Beat
4. `web` - Next.js 15 و Nginx
5. `mon` - Prometheus

## دستورات اصلی عملیات (`manage.sh`)

| دستور | کاربرد |
|---|---|
| `bash manage.sh start` | راه‌اندازی گام‌به‌گام و لایه‌ای کل سیستم |
| `bash manage.sh stop` | توقف گریسفول کل سیستم |
| `bash manage.sh restart` | ری‌استارت منظم کل سرویس‌ها |
| `bash manage.sh status` | وضعیت کانتینرها، مصرف رم، دیسک و پردازنده |
| `bash manage.sh health` | بررسی سلامت دیتابیس، ردیس، API و فرانت‌اند |
| `bash manage.sh logs backend` | مشاهده زنده لاگ بک‌اند |
| `bash manage.sh deploy` | بیلد، مهاجرت دیتابیس و انتشار نسخه جدید |
| `bash manage.sh migrate` | اجرای مهاجرت‌های دیتابیس (`alembic upgrade head`) |
| `bash manage.sh backup` | بکاپ کامل و فشرده از PostgreSQL |

## مهاجرت‌های دیتابیس (Alembic)

آخرین نسخه Alembic Head تاییدشده:
```bash
036_management_tables_and_activity_logs_fix
```

## وضعیت فرانت‌اند در Docker

- بیلد فرانت‌اند به صورت Multi-stage داخل `apps/web/Dockerfile` انجام می‌شود.
- هیچ نیازی به آپلود دستی پوشه `.next/standalone` نیست.
- `docker compose -f compose/web.yml build frontend` بیلد بدون خطا و بهینه‌سازی‌شده را ایجاد می‌کند.

## امنیت بین‌سروری و فایروال (UFW)

1. روی سرور مرکزی فایروال UFW را با اسکریپت `scripts/setup_firewall_central.sh` پیکربندی کنید.
2. با اضافه شدن هر ورکر ریموت جدید، از اسکریپت `scripts/add_worker_firewall.sh <WORKER_IP>` استفاده کنید تا پورت‌های 5432 و 6379 فقط برای همان ورکر باز شوند.
3. در صورت استفاده از Squidهای پورت 3129 و 3130 روی سرور مرکزی، اسکریپت `scripts/secure_squid_ports.sh` را جهت محدودسازی به لوکال‌هاست اجرا کنید.

## فعال‌سازی HTTPS

1. پس از صدور و نصب گواهینامه SSL در مسیر `infra/nginx/certs/`:
2. بخش‌های SSL در `infra/nginx/nginx.conf` را فعال کنید.
3. مقدار `AUTH_COOKIE_SECURE=true` را در `.env` قرار دهید.
4. `bash manage.sh deploy` را اجرا نمایید.

---

*وضعیت: تأییدشده و پایدار (v2.9.2 — 2026-08-20)*

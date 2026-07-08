# راهنمای شروع سریع BarPro

این راهنما برای اجرای سریع پروژه از checkout فعلی است. مسیرهای قدیمی `BarPro` هستند.

## پیش‌نیازها

- Docker Engine و Docker Compose V2
- Python 3.11 برای اجرای تست‌ها و ابزارهای محلی
- Node.js 20 برای توسعه فرانت‌اند
- فایل `.env` کامل‌شده بر اساس `.env.example`

## اجرای کامل با Docker

```bash
cp .env.example .env
# .env را ویرایش و secretها را تنظیم کنید
bash manage.sh start
bash manage.sh health
```

آدرس‌های محلی:

| سرویس | آدرس |
|---|---|
| Frontend via Nginx | `http://localhost` |
| Backend API داخلی | `http://localhost:8000` |
| API Docs داخلی | `http://localhost:8000/docs` |

## اجرای فقط زیرساخت برای توسعه

```bash
bash manage.sh start infra
bash manage.sh start proxy
```

Backend development:

```bash
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

Frontend development:

```bash
cd apps/web
npm install
npm run dev
```

## احراز هویت

- JWT در کوکی `httpOnly` با نام `utcms_auth_token` ذخیره می‌شود
- فرانت‌اند Bearer token را از localStorage ارسال نمی‌کند
- برای HTTP فعلی مقدار `AUTH_COOKIE_SECURE=false` لازم است
- بعد از HTTPS مقدار `AUTH_COOKIE_SECURE=true` شود

## مایگریشن

```bash
bash manage.sh migrate
```

Alembic head فعلی:

```text
015_add_client_subscription_dates
```

## تست و build سریع

```bash
python -m ruff check app tests
pytest tests/test_config_validation.py tests/test_multitenant_auth.py tests/test_master_admin.py
cd apps/web && npm run build && npm audit --omit=dev
```

## Docker buildهای تاییدشده

```bash
docker compose -f compose/backend.yml build backend
docker compose -f compose/web.yml build frontend
```

فرانت‌اند داخل Docker build می‌شود و نیازی به آپلود دستی `.next/standalone` نیست.

## توقف سیستم

```bash
bash manage.sh stop
```

## عیب‌یابی سریع

| مشکل | اقدام |
|---|---|
| فایل `.env` پیدا نمی‌شود | `cp .env.example .env` و مقداردهی secretها |
| migration اجرا نشد | `bash manage.sh migrate` |
| login کار نمی‌کند | `AUTH_COOKIE_SECURE`, `FRONTEND_URL`, CORS و کوکی مرورگر را بررسی کنید |
| فرانت بالا نمی‌آید | `bash manage.sh logs frontend` و `bash manage.sh logs nginx` |
| کپچا solve نمی‌شود | assetهای `app/automation/captcha/assets/` و `persian_number_ocr.keras` را بررسی کنید |

Last updated: 2026-07-08

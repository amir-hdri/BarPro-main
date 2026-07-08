# راهنمای راه‌اندازی سیستم

این راهنما دستورات فعلی راه‌اندازی BarPro را پوشش می‌دهد.

## اجرای production-like محلی یا سرور

```bash
cd /opt/barpro
bash manage.sh start
```

اگر روی ماشین توسعه اجرا می‌کنید، همین دستور را از ریشه repo اجرا کنید.

## ترتیب لایه‌ها

```bash
bash manage.sh start infra
bash manage.sh start proxy
bash manage.sh start backend
bash manage.sh start web
bash manage.sh start mon
```

`bash manage.sh start` همه این لایه‌ها را به ترتیب اجرا می‌کند.

## بررسی وضعیت

```bash
bash manage.sh status
bash manage.sh health
```

## مشاهده لاگ

```bash
bash manage.sh logs backend
bash manage.sh logs frontend
bash manage.sh logs nginx
```

## توسعه Backend

ابتدا زیرساخت را بالا بیاورید:

```bash
bash manage.sh start infra
bash manage.sh start proxy
```

سپس backend را دستی اجرا کنید:

```bash
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

## توسعه Frontend

```bash
cd apps/web
npm install
npm run dev
```

نسخه فعلی فرانت‌اند Next.js 15 است. برای Docker production build نیازی به اجرای دستی `.next/standalone/server.js` نیست.

## انتشار نسخه جدید

```bash
cd /opt/barpro
git pull
bash manage.sh deploy
```

## اجرای migration دستی

```bash
bash manage.sh migrate
```

## backup دیتابیس

```bash
bash manage.sh backup
```

## توقف سیستم

```bash
bash manage.sh stop
```

## نکات مهم

- `.env` را commit نکنید
- روی HTTP مقدار `AUTH_COOKIE_SECURE=false` را حفظ کنید
- بعد از HTTPS مقدار `AUTH_COOKIE_SECURE=true` شود
- Alembic head فعلی `015_add_client_subscription_dates` است
- فرانت‌اند از کوکی `httpOnly` برای JWT استفاده می‌کند
- Squid ports `3129` و `3130` باید با `scripts/secure_squid_ports.sh` محدود شوند

Last updated: 2026-07-08

# استقرار Production برای ربات دائمی UTCMS

## مشخصات پیشنهادی سرور

- `8 vCPU`
- `16 GB RAM`
- `100 GB NVMe`
- `Ubuntu 22.04 LTS`

برای بار بیشتر یا چند اپراتور هم‌زمان:

- `12 vCPU`
- `24 GB RAM`
- `150 GB NVMe`

## چینش سرویس‌ها

- `nginx`: reverse proxy و TLS termination
- `api`: سرویس FastAPI/Uvicorn
- `worker`: اجرای صف Celery و Playwright
- `redis`: broker/result backend
- `postgres`: داده‌های عملیاتی و صف

## تنظیمات عملیاتی پیشنهادی

- `WAYBILL_MAX_CONCURRENT=2`
- `BROWSER_POOL_SIZE=4`
- `CELERY_CONCURRENCY=4`
- `HEADLESS=true`
- `ALLOW_LIVE_SUBMIT=true`

این اعداد برای پایداری بهتر انتخاب شده‌اند؛ bottleneck اصلی مرورگرهای Playwright هستند، نه مدل CNN.

## Nginx پیشنهادی

نمونه کانفیگ:

```nginx
server {
    listen 80;
    server_name your-domain.example;
    return 301 https://$host$request_uri;
}

server {
    listen 443 ssl http2;
    server_name your-domain.example;

    ssl_certificate /etc/letsencrypt/live/your-domain.example/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/your-domain.example/privkey.pem;

    client_max_body_size 25m;
    proxy_read_timeout 600s;
    proxy_send_timeout 600s;

    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
```

## مانیتورینگ سیستم

حداقل این‌ها را فعال کنید:

- `Node Exporter` برای CPU/RAM/Disk
- `Prometheus` برای scrape
- `Grafana` برای داشبورد
- `Loki + Promtail` یا حداقل `docker logs` rotation برای لاگ
- uptime monitor برای `/healthz` و `/readyz`

## آلارم‌های مهم

- RAM بالاتر از `85%`
- Disk بالاتر از `80%`
- افزایش خطاهای `401/429/5xx`
- افت success rate ثبت بارنامه
- افزایش failure rate کپچا
- backlog زیاد در صف Redis/Celery

## الگوی استقرار

1. فایل `.env.production.example` را به `.env` کپی کنید.
2. secretها را تغییر دهید.
3. دسترسی پوشه `.auth` را محدود کنید.
4. با Compose بالا بیاورید:

```bash
docker compose up -d --build
```

5. سلامت را بررسی کنید:

```bash
curl http://127.0.0.1:8000/healthz
curl http://127.0.0.1:8000/readyz
```

## نکات مهم امنیتی

- `API_KEY` و `JWT_SECRET` طولانی و تصادفی باشند.
- `API_AUTH_MODE=api_key_or_jwt` برای production مناسب است.
- دسترسی عمومی مستقیم به Redis و Postgres ندهید.
- فقط `nginx` روی اینترنت expose شود.
- برای `.auth` و backup دیتابیس سیاست backup روزانه داشته باشید.

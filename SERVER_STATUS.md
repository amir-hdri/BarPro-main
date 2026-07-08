# BarPro — وضعیت سرور
# آخرین بروزرسانی: 2026-07-08

## 📊 اطلاعات سرور

| آیتم | مقدار |
|------|-------|
| IP اصلی | 188.121.123.16 (Nginx port 80, Backend, Frontend, Squid 1) |
| IP ثانویه | 95.38.233.90 (Squid 2 port 3129, Squid 3 port 3130) |
| هر دو IP | یک سرور فیزیکی — 4 vCPU، 12 GB RAM |
| مسیر پروژه | `/opt/barpro` |
| دیسک | 21 GB used / 70 GB total (31%) |
| URL قابل دسترسی | `http://95.38.233.90` فعلی؛ پس از نصب TLS از دامنه HTTPS استفاده شود |

---

## 🐳 وضعیت کانتینرها

| Container | Image | وضعیت |
|-----------|-------|--------|
| barpro-nginx | nginx:1.27-alpine | ✅ Healthy |
| barpro-frontend | barpro_frontend | ✅ Healthy |
| barpro-backend | barpro_backend | ✅ Healthy |
| barpro-worker-1 | barpro_celery_worker_1 | ✅ Healthy |
| barpro-worker-2 | barpro_celery_worker_2 | ✅ Healthy |
| barpro-worker-3 | barpro_celery_worker_3 | ✅ Healthy |
| barpro-beat | barpro_celery_beat | ✅ Healthy |
| barpro-postgres | postgres:16 | ✅ Healthy |
| barpro-redis | redis:7 | ✅ Healthy |
| barpro-squid-1 | ubuntu/squid | ✅ Healthy |
| barpro-squid-2 | ubuntu/squid | ✅ Healthy |
| barpro-squid-3 | ubuntu/squid | ✅ Healthy |
| barpro-prometheus | prom/prometheus | ✅ Healthy |

### آخرین اعتبارسنجی محلی build/deploy

| مورد | نتیجه |
|------|-------|
| Backend Docker image | ✅ `docker compose -f compose/backend.yml build backend` |
| Frontend Docker image | ✅ `docker compose -f compose/web.yml build frontend` |
| Backend image smoke import | ✅ `from app.main import app` |
| Frontend production build | ✅ `npm run build` |
| Production npm audit | ✅ `npm audit --omit=dev` بدون vulnerability |
| Alembic head | ✅ `015_add_client_subscription_dates` |

---

## ✅ تست‌های سلامت

```
GET http://95.38.233.90/              → HTTP 200         ✅ (Next.js صفحه اصلی)
GET http://95.38.233.90/auth          → HTTP 200         ✅ (صفحه ورود)
GET http://95.38.233.90/api/healthz   → {"status":"ok"}  ✅
GET http://95.38.233.90/api/v1/healthz→ {"status":"ok"}  ✅
```

---

## ❌ مشکلات شناسایی‌شده و علت‌ها (2026-07-03)

### 1. CSP مسدودکننده اسکریپت‌های Next.js (علت اصلی صفحه سفید)
| | |
|---|---|
| **مشکل** | صفحه خالی برگردانده می‌شد (`<body>` بدون محتوا)، خطای `Refused to execute inline script` در کنسول مرورگر |
| **علت ریشه‌ای** | هدر `Content-Security-Policy: script-src 'self'` تمام اسکریپت‌های inline Next.js (از جمله chunks، webpack runtime) را مسدود می‌کرد |
| **فایل** | `infra/nginx/http-server.conf:8` |
| **راهکار** | تغییر به `script-src 'self' 'unsafe-inline' 'unsafe-eval'` |
| **وضعیت** | ✅ رفع شد |

### 2. عدم Resolution DNS در Nginx (علت اصلی قطعی API)
| | |
|---|---|
| **مشکل** | درخواست‌های `/api/*` به‌خطای 500 با `invalid URL prefix` منجر می‌شدند |
| **علت ریشه‌ای** | Nginx از upstream-name های داکر (`backend:8000`) استفاده می‌کرد اما `resolver` در بلاک http تعریف نشده بود؛ همچنین `proxy_pass` متغیر (`$backend_addr`) بدون `set` متناظر باعث خطای `uninitialized variable` شد |
| **فایل** | `infra/nginx/nginx.conf` و `infra/nginx/http-server.conf` |
| **راهکار** | افزودن `resolver 127.0.0.11 ipv6=off valid=30s;` در http block و بازگشت به `proxy_pass http://backend_upstream;` |
| **وضعیت** | ✅ رفع شد |

### 3. Config Stale در کانتینر (علت 500 بعد از رفع مشکل بالا)
| | |
|---|---|
| **مشکل** | بعد از اعمال تغییرات با `sed` روی host و `nginx -s reload`، بعضی location ها همچنان خطا می‌دادند |
| **علت ریشه‌ای** | Docker bind-mount از inode فایل پیروی می‌کند؛ `sed` یک inode جدید ایجاد می‌کند ولی کانتینر هنوز فایل قدیمی را می‌بیند. `nginx -s reload` کافی نیست |
| **راهکار** | حذف و ایجاد مجدد کانتینر با `docker rm -f barpro-nginx` سپس `manage.sh start web` |
| **وضعیت** | ✅ رفع شد |

### 4. IP اصلی (188.121.123.16:80) قابل دسترسی نیست
| | |
|---|---|
| **مشکل** | اتصال به http://188.121.123.16 از خارج از سرور timeout می‌خورد |
| **علت ریشه‌ای** | احتمالاً Hairpin NAT/محدودیت routing در دیتاسنتر؛ امکان DNAT مفقود یا فیلتر upstream |
| **راهکار موقت** | استفاده از http://95.38.233.90 به‌جای IP اصلی |
| **وضعیت** | ❌ رفع نشده — نیازمند بررسی provider دیتاسنتر |

### 5. مقادیر اشتباه در Deploy Scripts
| | |
|---|---|
| **مشکل** | `NEXT_PUBLIC_API_URL` در چندین deploy script مقدار `http://188.121.123.16:8000` داشت (باید `/api` باشد) |
| **علت ریشه‌ای** | scripts پروژه absolute URL هاردکد شده بودند که برای معماری Nginx-reverse-proxy نادرست است |
| **فایل‌ها** | `scripts/deploy_remote.sh`، `deploy_remote.py`، `deploy_single_vm.py` |
| **راهکار** | تغییر از `http://$IP:8000` به `/api` در ۶ مکان مختلف + افزودن `FRONTEND_URLS` |
| **وضعیت** | ✅ رفع شد |

### 6. `.env.example` مقادیر پیش‌فرض نادرست
| | |
|---|---|
| **مشکل** | `FRONTEND_URL` لوکال‌هاست و `NEXT_PUBLIC_API_URL` پورت 8000 داشت |
| **علت ریشه‌ای** | مخصوص development نوشته شده بود نه production |
| **راهکار** | بروزرسانی به `FRONTEND_URL=http://YOUR_SERVER_IP` و `NEXT_PUBLIC_API_URL=/api` |
| **وضعیت** | ✅ رفع شد |

---

## 🗄️ دیتابیس

| | |
|-|-|
| موتور | PostgreSQL 16 |
| نام DB | `utcms_rpa` |
| آخرین migration | `015_add_client_subscription_dates` (head) |
| تعداد جداول | 21 (20 + alembic_version) |

### جداول موجود
`activity_logs`, `admin_driver_schedules`, `alembic_version`, `botstats`,
`clients`, `domain_events`, `driver_daily_counters`, `driver_plates`,
`driver_runtime_states`, `driver_schedules`, `driver_session_metadata`,
`drivers`, `fuel_inquiries` (با ستون‌های `year` و `month`), `proxy_endpoints`, `subscription_plans`,
`super_admins`, `upload_batches`, `waybill_attempts`, `waybill_jobs`,
`waybill_task_logs`, `waybilltask`

---

## 📁 ساختار فایل‌ها روی سرور

```
/opt/barpro/
├── app/                    ← کد بک‌اند (از git)
├── apps/web/               ← کد فرانت‌اند (از git)
├── alembic/                ← migrations (از git)
├── compose/                ← Docker Compose files
├── infra/                  ← nginx, squid, prometheus config
├── .env                    ← متغیرهای محیطی (هرگز commit نشود)
├── playwright-browsers/    ← Chromium (107 MB, volume داکر)
├── persian_number_ocr.keras ← مدل fallback OCR سوخت (13 MB)
├── app/automation/captcha/assets/captcha_cnn.pth ← مدل CNN ورود
├── app/automation/captcha/assets/fuel_captcha_crnn.pth ← مدل PyTorch کپچای سوخت
├── app/automation/captcha/assets/fuel_captcha_vocab.json ← vocab مدل سوخت
└── output/                 ← لاگ‌ها و backups
```

---

## 🔗 دسترسی SSH

```bash
# اتصال از Mac (فقط از طریق IP ثانویه)
ssh ubuntu@95.38.233.90

# اتصال به IP اصلی از داخل سرور
ssh ubuntu@188.121.123.16  # یا localhost از داخل سرور

# دلیل: IP 188.121.123.16:22 از VPN ایران قابل دسترسی نیست
# IP 95.38.233.90:22 از VPN قابل دسترسی است
```

---

## 👤 دسترسی ادمین

| مورد | مقدار |
|------|-------|
| endpoint ورود | `POST /api/v1/admin/login` |
| نام کاربری | مقدار `MASTER_ADMIN_USERNAME` در `.env` |
| رمز عبور | مقدار `MASTER_ADMIN_PASSWORD` در `.env`؛ هرگز در مستندات commit نشود |

> ⚠️ در deployment فعلی JWT در کوکی `httpOnly` با نام `utcms_auth_token` ذخیره می‌شود. روی HTTP مقدار `AUTH_COOKIE_SECURE=false` لازم است؛ پس از HTTPS مقدار `true` شود.

---

*آخرین بروزرسانی: 2026-07-08*

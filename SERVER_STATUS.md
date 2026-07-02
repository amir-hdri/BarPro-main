# BarPro — وضعیت سرور
# آخرین بروزرسانی: ۱۱ تیر ۱۴۰۵ (2026-07-02)

## 📊 اطلاعات سرور

| آیتم | مقدار |
|------|-------|
| IP اصلی | 188.121.123.16 (Nginx port 80, Backend, Frontend, Squid 1) |
| IP ثانویه | 95.38.233.90 (Squid 2 port 3129, Squid 3 port 3130) |
| هر دو IP | یک سرور فیزیکی — 4 vCPU، 12 GB RAM |
| مسیر پروژه | `/opt/barpro` |
| دیسک | 21 GB used / 70 GB total (31%) |

---

## 🐳 وضعیت کانتینرها (2026-07-02)

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

---

## ✅ تست‌های سلامت

```
GET http://188.121.123.16/healthz → {"status":"ok"}  ✅
GET http://188.121.123.16/        → HTTP 200         ✅
Alembic: 013_add_admin_driver_schedules (head)        ✅
```

---

## 🗄️ دیتابیس

| | |
|-|-|
| موتور | PostgreSQL 16 |
| نام DB | `utcms_rpa` |
| آخرین migration | `013_add_admin_driver_schedules` (head) |
| تعداد جداول | 21 (20 + alembic_version) |

### جداول موجود
`activity_logs`, `admin_driver_schedules`, `alembic_version`, `botstats`,
`clients`, `domain_events`, `driver_daily_counters`, `driver_plates`,
`driver_runtime_states`, `driver_schedules`, `driver_session_metadata`,
`drivers`, `fuel_inquiries`, `proxy_endpoints`, `subscription_plans`,
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
├── persian_number_ocr.keras ← مدل OCR سوخت (13 MB)
├── login captch/captcha_cnn.pth ← مدل CNN ورود (1.7 MB)
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

*آخرین بروزرسانی: 2026-07-02 — توسط Antigravity AI Agent*

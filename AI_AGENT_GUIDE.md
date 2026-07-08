# BarPro — راهنمای جامع برای AI Agent
# آخرین بروزرسانی: 2026-07-08

> این فایل برای **AI Agent حرفه‌ای** طراحی شده است.
> هر بخش دقیق، فنی و قابل اجرا است.

---

## ۱. هویت پروژه

**BarPro** یک فریمورک RPA (Robotic Process Automation) چند‌مستأجره است برای ثبت خودکار بارنامه در سامانه ملی حمل‌ونقل ایران (`barname.utcms.ir`). از Playwright برای اتوماسیون مرورگر، OCR (PyTorch CNN + PyTorch fuel CRNN + Keras) برای حل CAPTCHA، Squid Proxy برای جابجایی IP و Celery برای مدیریت صف استفاده می‌کند.

---

## ۲. معماری کلی

```
کاربر (Browser)
    ↓
Nginx :80 (reverse proxy)
    ├── /api/v1/* → FastAPI Backend :8000
    ├── /ws/*     → FastAPI WebSocket :8000
    └── /*        → Next.js Frontend :3000

FastAPI Backend :8000
    ├── PostgreSQL 16 (ORM: SQLModel + asyncpg)
    ├── Redis 7 (cache + Celery broker)
    └── Celery Workers ×3
            ├── Worker 1 → Squid 1 (:3128) → egress via 188.121.123.16
            ├── Worker 2 → Squid 2 (:3129) → egress via 95.38.233.90
            └── Worker 3 → Squid 3 (:3130) → egress via 95.38.233.90
```

**یک سرور — دو IP عمومی:**
- `188.121.123.16` → Nginx (port 80), Backend, Frontend, Squid 1
- `95.38.233.90` → Squid 2 (port 3129), Squid 3 (port 3130)

---

## ۳. اطلاعات اتصال سرور

```bash
# SSH (از Mac با VPN ایران)
ssh ubuntu@95.38.233.90     # ← این IP کار می‌کند
ssh ubuntu@188.121.123.16   # ← از VPN بلاک است

# مسیر پروژه
/opt/barpro/

# اجرای دستور روی سرور
sshpass -p "$SSH_PASSWORD" ssh -o ConnectTimeout=10 -o StrictHostKeyChecking=no ubuntu@95.38.233.90 "COMMAND"
```

> ⚠️ **مهم:** هرگز `SSH_PASSWORD` را در کد hardcode نکنید. از env var استفاده کنید.

---

## ۴. ساختار کد (کامل)

```
BarPro/
├── app/                         ← بک‌اند (FastAPI / Python 3.11)
│   ├── api/
│   │   └── routes/
│   │       ├── multitenant.py   ← /api/v1/* (auth, drivers, waybill-jobs, plates, schedules)
│   │       ├── waybill_entry.py ← /waybill/* (ثبت بارنامه)
│   │       ├── waybill_map.py   ← /waybill/* (نقشه)
│   │       ├── management.py    ← /management/* (مدیریت)
│   │       ├── system.py        ← /healthz, /readyz, /metrics, ...
│   │       ├── rpa_phase1.py    ← /api/v1/rpa/phase1/*
│   │       ├── admin_reporting.py ← /admin/reports/*
│   │       ├── user_reporting.py ← /user/reports/*
│   │       ├── reports.py       ← /reports/*
│   │       ├── itmb_ws.py       ← /waybill/ws/waybill (WebSocket)
│   │       └── realtime.py      ← /events/*
│   ├── automation/
│   │   ├── browser.py           ← مدیریت Playwright + Chromium
│   │   ├── captcha/             ← CNN solver + Keras OCR
│   │   └── proxy_rotator.py     ← Squid proxy انتخاب
│   ├── core/
│   │   ├── config.py            ← Settings (pydantic)
│   │   ├── database.py          ← AsyncEngine + migrations on startup
│   │   ├── redis.py             ← Redis connection (threading.Lock)
│   │   ├── security.py          ← JWT + hashing
│   │   └── rate_limiter.py      ← fail-closed limiter
│   ├── models/
│   │   ├── admin.py             ← SuperAdmin, SubscriptionPlan, AdminDriverSchedule, ActivityLog
│   │   ├── multitenant.py       ← Client, Driver, Plate, WaybillJob, ...
│   │   └── __init__.py
│   ├── services/
│   │   ├── task_service.py      ← CRUD + Redis counter cache
│   │   ├── auth_service.py
│   │   └── ...
│   ├── workers/
│   │   ├── celery_app.py        ← Celery configuration
│   │   ├── waybill_worker.py    ← اصلی‌ترین worker
│   │   ├── phase1_tasks.py
│   │   └── tasks.py             ← event loop per worker process
│   └── realtime/
│       └── events.py            ← WebSocket hub
├── apps/web/                    ← فرانت‌اند (Next.js 15 / TypeScript / Tailwind)
│   └── src/
│       ├── app/                 ← App Router pages
│       │   ├── page.tsx         ← /  (داشبورد)
│       │   ├── auth/page.tsx    ← /auth
│       │   ├── new/page.tsx     ← /new
│       │   ├── history/page.tsx ← /history
│       │   ├── drivers/page.tsx ← /drivers
│       │   ├── fuel/page.tsx    ← /fuel
│       │   ├── reports/page.tsx ← /reports
│       │   ├── settings/page.tsx ← /settings
│       │   └── admin/           ← /admin/*
│       ├── lib/
│       │   ├── api.ts           ← axios client + withCredentials cookie auth
│       │   └── auth.ts          ← ذخیره اطلاعات غیرحساس session در localStorage
│       ├── components/          ← کامپوننت‌های مشترک
│       └── schemas/             ← Zod schemas
├── alembic/
│   └── versions/               ← زنجیره migration تا head فعلی 015
├── compose/
│   ├── infra.yml               ← PostgreSQL + Redis
│   ├── proxy.yml               ← Squid ×3
│   ├── backend.yml             ← FastAPI + Celery ×3 + Beat
│   ├── web.yml                 ← Nginx + Frontend
│   └── monitoring.yml          ← Prometheus
├── infra/
│   ├── nginx/
│   │   ├── nginx.conf          ← upstream config
│   │   └── http-server.conf    ← location blocks
│   └── squid/squid_*.conf      ← تنظیم هر Squid
├── scripts/
│   ├── server_deploy.py        ← deploy مرحله‌ای (--steps 1,2,3,4,5)
│   ├── upload_and_setup.py     ← upload کد به سرور
│   ├── secure_squid_ports.sh   ← iptables برای Squid 3129/3130
│   └── db_backup.sh            ← backup PostgreSQL
├── tests/                      ← pytest (asyncio_mode=auto)
├── manage.sh                   ← مدیریت سرور (start/stop/health/deploy/migrate)
├── Dockerfile                  ← بک‌اند image (لایه‌بندی pip برای cache)
└── .env                        ← متغیرهای محیطی (هرگز commit نشود)
```

---

## ۵. همه Endpoint‌های API

### بدون prefix (مستقیم از Nginx)
| Method | Path | Auth |
|--------|------|------|
| GET | `/healthz` | ❌ |
| GET | `/readyz` | ❌ |
| GET | `/metrics` | ❌ |
| GET | `/auth-config` | ❌ |
| GET | `/ui` | ❌ |
| WS | `/ws/waybill` | JWT |
| GET | `/events/history` | — |
| GET | `/workers/heartbeats` | — |
| POST | `/workers/recover-stalled` | — |
| GET | `/captcha/monitor` | — |
| POST | `/captcha/diagnose` | — |
| GET | `/browser-pool/health` | — |
| POST | `/browser-pool/heal` | — |
| GET | `/security/report` | — |
| GET | `/errors/stats` | — |
| POST | `/circuit-breaker/toggle` | ✅ sensitive |
| GET | `/baseinfo/status` | ✅ sensitive |
| POST | `/baseinfo/refresh` | ✅ sensitive |

### `/api/v1/` (multitenant.py)
| Method | Path | نقش |
|--------|------|-----|
| POST | `/api/v1/auth/register` | عمومی |
| POST | `/api/v1/auth/login` | عمومی (`email`+`password`) |
| POST | `/api/v1/auth/logout` | JWT |
| GET | `/api/v1/auth/me` | JWT |
| GET | `/api/v1/auth/stats` | JWT |
| POST | `/api/v1/admin/login` | عمومی (`username`+`password`) |
| GET | `/api/v1/admin/clients` | Admin |
| POST | `/api/v1/admin/clients` | Admin |
| PUT | `/api/v1/admin/clients/{id}` | Admin |
| DELETE | `/api/v1/admin/clients/{id}` | Admin |
| POST | `/api/v1/drivers` | JWT |
| GET | `/api/v1/drivers` | JWT |
| GET | `/api/v1/drivers/{id}` | JWT |
| PUT | `/api/v1/drivers/{id}` | JWT |
| DELETE | `/api/v1/drivers/{id}` | JWT |
| POST | `/api/v1/plates` | JWT |
| GET | `/api/v1/plates` | JWT |
| PUT | `/api/v1/plates/{id}` | JWT |
| DELETE | `/api/v1/plates/{id}` | JWT |
| POST | `/api/v1/driver-schedules` | JWT |
| GET | `/api/v1/driver-schedules` | JWT |
| PUT | `/api/v1/driver-schedules/{id}` | JWT |
| DELETE | `/api/v1/driver-schedules/{id}` | JWT |
| POST | `/api/v1/driver-schedules/run-due` | JWT |
| POST | `/api/v1/waybill-jobs` | JWT |
| GET | `/api/v1/waybill-jobs` | JWT |
| GET | `/api/v1/waybill-jobs/{id}` | JWT |
| GET | `/api/v1/waybill-jobs/{id}/timeline` | JWT |
| GET | `/api/v1/waybill-jobs/{id}/logs` | JWT |
| PATCH | `/api/v1/waybill-jobs/{id}` | JWT |
| DELETE | `/api/v1/waybill-jobs/{id}` | JWT |
| POST | `/api/v1/waybill-jobs/{id}/retry` | JWT |
| POST | `/api/v1/waybill-jobs/{id}/requeue` | JWT |
| POST | `/api/v1/upload/excel` | JWT |
| GET | `/api/v1/upload/batches/{id}` | JWT |
| GET | `/api/v1/reports/daily-summary` | JWT |
| GET | `/api/v1/reports/driver-performance` | JWT |
| POST | `/api/v1/fuel-inquiries` | JWT |
| GET | `/api/v1/fuel-inquiries` | JWT |
| GET | `/api/v1/fuel-inquiries/{id}` | JWT |
| GET | `/api/v1/excel-template` | sensitive |

### `/management/` و `/admin/reports/` و `/user/reports/`
| Path | توضیح |
|------|-------|
| `/management/customers` | مدیریت مشتریان |
| `/management/routes` | مسیرها |
| `/management/accounts` | اکانت‌ها |
| `/management/queue` | صف |
| `/management/import/excel` | import اکسل |
| `/admin/reports/summary` | آمار ادمین |
| `/admin/reports/diagnostics` | تشخیص ادمین |
| `/user/reports/summary` | آمار کاربر |
| `/user/reports/daily` | گزارش روزانه |
| `/user/reports/performance` | عملکرد |
| `/user/reports/errors` | تحلیل خطا |

### `/api/v1/rpa/phase1/` (چند‌مستأجره)
| Path | توضیح |
|------|-------|
| `/api/v1/rpa/phase1/overview` | نمای کلی |
| `/api/v1/rpa/phase1/drivers/{id}/runtime` | وضعیت راننده |
| `/api/v1/rpa/phase1/scheduler/plan` | برنامه زمان‌بند |

---

## ۶. دیتابیس

### جداول و مدل‌ها

| جدول | مدل Python | فایل |
|------|------------|------|
| `super_admins` | `SuperAdmin` | `models/admin.py` |
| `subscription_plans` | `SubscriptionPlan` | `models/admin.py` |
| `admin_driver_schedules` | `AdminDriverSchedule` | `models/admin.py` |
| `activity_logs` | `ActivityLog` | `models/admin.py` |
| `clients` | `Client` | `models/multitenant.py` |
| `drivers` | `Driver` | `models/multitenant.py` |
| `driver_plates` | `DriverPlate` | `models/multitenant.py` |
| `driver_schedules` | `DriverSchedule` | `models/multitenant.py` |
| `driver_runtime_states` | `DriverRuntimeState` | `models/multitenant.py` |
| `driver_daily_counters` | `DriverDailyCounter` | `models/multitenant.py` |
| `driver_session_metadata` | `DriverSessionMetadata` | `models/multitenant.py` |
| `waybill_jobs` | `WaybillJob` | `models/multitenant.py` |
| `waybill_task_logs` | `WaybillTaskLog` | `models/multitenant.py` |
| `waybill_attempts` | `WaybillAttempt` | `models/multitenant.py` |
| `upload_batches` | `UploadBatch` | `models/multitenant.py` |
| `fuel_inquiries` | `FuelInquiry` | `models/multitenant.py` |
| `botstats` | `BotStats` | `models/admin.py` |
| `domain_events` | `DomainEvent` | (migration) |
| `proxy_endpoints` | `ProxyEndpoint` | (migration) |
| `waybilltask` | `WaybillTask` | `models/admin.py` (legacy) |

### زنجیره Migrations

```
001_initial → 002_phase1_rpa_backend → 003_add_waybill_jobs_correlation_id
→ 004_add_otp_backoff_and_timezone → 005_fix_constraint_conflicts
→ 006_add_performance_indexes → 007_add_multi_level_system
→ 008_add_sched_id_waybill_jobs → 009_add_access_level_to_clients
→ 010_add_missing_columns → 011_add_driver_plates
→ 3ef63013cff9_add_client_limits → 4a5b6c7d8e9f_ensure_max_plates_column
→ 5b6c7d8e9f0a_add_fuel_inquiries → 012_add_optimization_indexes
→ 013_add_admin_driver_schedules → 014_add_year_month_to_fuel_inquiries
→ 015_add_client_subscription_dates  ← HEAD (جدیدترین)
```

---

## ۷. تنظیمات و متغیرهای محیطی

| متغیر | توضیح | پیش‌فرض |
|-------|-------|---------|
| `API_KEY` | کلید API backend | — |
| `JWT_SECRET` | کلید امضای JWT (حداقل 32 کاراکتر) | — |
| `DRIVER_ENCRYPTION_KEY` | Fernet key برای رمزنگاری رمز راننده | — |
| `MASTER_ADMIN_PASSWORD` | رمز ادمین اصلی | — |
| `POSTGRES_PASSWORD` | رمز PostgreSQL | — |
| `REDIS_PASSWORD` | رمز Redis | — |
| `HEADLESS` | مرورگر headless | `true` |
| `CAPTCHA_PROVIDER` | `auto/composite/cnn/pytorch_fuel/keras_ocr/enhanced_ocr/local_ocr/off` | `auto` |
| `CAPTCHA_MODE` | `provider_only/manual_fallback` | `provider_only` |
| `CAPTCHA_TIMEOUT_SECONDS` | timeout برای captcha | `120` |
| `KERAS_PYTHON_PATH` | مسیر Python 3.12 برای Keras | `/opt/barpro/venv/bin/python` |
| `KERAS_MODEL_PATH` | فایل مدل Keras OCR | `persian_number_ocr.keras` |
| `AUTH_COOKIE_SECURE` | فعال‌سازی Secure flag روی کوکی JWT | `false` روی HTTP، `true` پس از HTTPS |
| `AVAILABLE_IP_INDICES` | شاخص‌های IP فعال | `"1,2"` |
| `ENVIRONMENT` | `production/development` | `production` |

---

## ۸. مدل‌های CAPTCHA

| صفحه | روش | مدل | Provider |
|------|-----|-----|---------|
| ورود (math: "2+3") | PyTorch CNN | `app/automation/captcha/assets/captcha_cnn.pth` | `cnn` |
| استعلام سوخت (متن فارسی عددی) | PyTorch CRNN | `app/automation/captcha/assets/fuel_captcha_crnn.pth` + vocab | `pytorch_fuel` |
| استعلام سوخت fallback | Keras OCR | `persian_number_ocr.keras` | `keras_ocr` |

جریان `auto`: CNN → PyTorch fuel → Keras → Enhanced → Local (Tesseract) → fail

---

## ۹. دستورات مفید

### مدیریت سرور
```bash
bash manage.sh start        # راه‌اندازی کامل
bash manage.sh stop         # توقف
bash manage.sh status       # CPU/RAM/disk/containers
bash manage.sh health       # بررسی DB/Redis/API/Frontend
bash manage.sh deploy       # pull از GitHub + migrate + restart
bash manage.sh migrate      # فقط alembic upgrade head
bash manage.sh backup-db    # snapshot PostgreSQL
```

### Docker Compose (ترتیب صحیح)
```bash
docker compose -f compose/infra.yml up -d
docker compose -f compose/proxy.yml up -d
docker compose -f compose/backend.yml up -d
docker compose -f compose/web.yml up -d
docker compose -f compose/monitoring.yml up -d
```

### Alembic
```bash
docker exec barpro-backend alembic current      # نسخه فعلی
docker exec barpro-backend alembic upgrade head  # اعمال همه migrations
docker exec barpro-backend alembic history       # تاریخچه
```

### Deployment مرحله‌ای
```bash
# فقط آپلود کد (بدون rebuild)
python3 scripts/server_deploy.py --ip 95.38.233.90 --steps 1

# فقط rebuild داکر
python3 scripts/server_deploy.py --ip 95.38.233.90 --steps 3

# فقط migration
python3 scripts/server_deploy.py --ip 95.38.233.90 --steps 4

# تست نهایی
python3 scripts/server_deploy.py --ip 95.38.233.90 --steps 5
```

### تست API
```bash
# سلامت
curl http://188.121.123.16/healthz

# ورود
curl -X POST http://188.121.123.16/api/v1/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email":"user@example.com","password":"secret"}'

# لیست بارنامه‌ها
curl http://188.121.123.16/api/v1/waybill-jobs \
  -H "Authorization: Bearer TOKEN"
```

---

## ۱۰. تست‌ها

```bash
# همه تست‌ها
pytest

# فقط unit
pytest -m unit

# فقط integration
pytest -m integration

# بدون تست‌های آهسته
pytest -m "not slow"
```

**نکته:** تست‌های دیتابیس نیاز به PostgreSQL دارند (`compose/infra.yml`).
تست‌های Playwright نیاز به `playwright install chromium` دارند.

---

## ۱۱. استانداردهای کد

### Python (Backend)
- **Formatter:** Black (line-length 120)
- **Imports:** isort با black profile
- **Linting:** Ruff (E, W, F, I, B, C4, UP)
- **Type check:** mypy (strict mode)
- **Pattern:** Async/Await در سراسر کد

### TypeScript (Frontend)
- **Framework:** Next.js 15 (App Router) + React 19
- **Forms:** React Hook Form + Zod
- **Data:** React Query + Axios
- **Styling:** Tailwind CSS + Heroicons

---

## ۱۲. نقاط خطرناک و هشدارها

> ⛔ **هرگز hardcode نکنید:** credentials، IP، password

> ⛔ **هرگز commit نکنید:** `.env`، فایل‌های secrets

> ⚠️ **`except: pass`** — همه باید لاگ داشته باشند، نه نادیده گرفته شوند

> ⚠️ **`engine.dispose()`** در Celery task — حذف شده، دوباره اضافه نکنید

> ⚠️ **`asyncio.Lock`** در class instance — از `threading.Lock` استفاده کنید

> ⚠️ **`autoretry_for = (Exception,)`** — فقط exception مشخص retry کنید

> ⚠️ **`network_mode: host`** در compose — برای routing دو IP لازم است، حذف نکنید

---

## ۱۳. وضعیت فعلی (2026-07-08)

### ✅ کامل و در حال اجرا
- Docker backend image build: ✅ `barpro_backend:latest`
- Docker frontend image build: ✅ `barpro-frontend:latest`
- Frontend production build: ✅ `npm run build`
- Production frontend audit: ✅ `npm audit --omit=dev` بدون vulnerability
- Backend import smoke inside image: ✅
- Database migration head: `015_add_client_subscription_dates`

### ⬜ نیاز به اقدام دستی کاربر
1. **HTTPS:** نصب Let's Encrypt cert + uncomment `listen 443` در nginx
2. **Firewall Squid:** اجرای `sudo bash scripts/secure_squid_ports.sh`
3. **crontab:** اضافه‌کردن `@reboot sudo bash /opt/barpro/scripts/secure_squid_ports.sh`
4. **HTTPS hardening:** پس از نصب certificate مقدار `AUTH_COOKIE_SECURE=true` شود

---

*آخرین اعتبارسنجی: 2026-07-08*

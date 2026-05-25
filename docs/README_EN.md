# بارنامه خودکار (BarPro)

> **📌 معماری جدید:** پروژه به معماری monorepo ارتقا یافته است. فرانت‌اند اصلی با Next.js و Tailwind در پوشه `apps/web/` و بک‌اند در `app/` قرار دارد. تمامی مستندات در راستای این تغییرات به‌روزرسانی شده‌اند.


سامانه هوشمند ثبت بارنامه شهری UTCMS با ربات RPA و رابط کاربری وب فارسی.

---

## 🏗️ معماری پروژه

```
BarPro/
├── app/                              ← بک‌اند Python FastAPI (ربات RPA — پورت ۸۰۰۰)
│   ├── api/routes/                   ← REST API endpoints (۱۱ روتر)
│   │   ├── multitenant.py            ← مدیریت چند مستأجر: auth, drivers, waybill-jobs
│   │   ├── waybill_entry.py          ← ثبت دستی و آپلود اکسل
│   │   ├── waybill_map.py            ← انتخاب مکان و نقشه
│   │   ├── management.py             ← مدیریت صف و گزارشات
│   │   ├── reports.py                ← آمار و داشبورد
│   │   ├── system.py                 ← Health, Metrics, Monitoring
│   │   └── realtime.py               ← WebSocket برای بروزرسانی زنده
│   ├── automation/                   ← موتور RPA (Playwright)
│   │   ├── waybill_enhanced.py       ← ربات پیشرفته با Self-Healing + OTP Graceful Exit
│   │   ├── waybill_bot_multitenant.py← ربات چند مستأجر
│   │   ├── location_selector.py      ← انتخاب مکان روی نقشه
│   │   ├── map_controller.py         ← کنترل نقشه Google/OpenLayers/Leaflet
│   │   ├── captcha/                  ← حل خودکار کپچا (CNN + Provider + Math)
│   │   └── stealth*.py               ← آنتی‌دیتکت مرورگر
│   ├── core/                         ← زیرساخت: Config, Database, Network, Resilience
│   ├── schemas/                      ← Pydantic models
│   ├── services/                     ← Business logic
│   │   ├── rpa_scheduler_service.py  ← زمان‌بند با پشتیبانی OTP_BACKOFF
│   │   ├── multitenant_service.py    ← سرویس چند مستأجر
│   │   └── excel_upload_service.py   ← پردازش اکسل
│   └── workers/                      ← Celery workers
│       ├── waybill_worker.py         ← Worker اصلی با پشتیبانی OTP_BACKOFF
│       └── tasks.py                  ← وظایف Celery
│
├── apps/
│   ├── web/                          ← فرانت‌اند Next.js 15 (پورت ۳۰۰۰)
│   │   ├── src/
│   │   │   ├── app/                  ← App Router (صفحات)
│   │   │   │   ├── layout.tsx        ← فونت Vazirmatn + RTL + PWA manifest
│   │   │   │   ├── page.tsx          ← داشبورد اصلی
│   │   │   │   ├── new/page.tsx      ← فرم بارنامه + JobStatusTracker
│   │   │   │   └── history/page.tsx  ← تاریخچه با کارت‌های رنگی
│   │   │   ├── components/
│   │   │   │   ├── forms/WaybillForm.tsx   ← فرم ۷ فیلدی + React Query useMutation
│   │   │   │   ├── JobStatusTracker.tsx    ← نمایش وضعیت با OTP_BACKOFF alert
│   │   │   │   └── layout/MobileShell.tsx  ← نوار ناوبری موبایل
│   │   │   ├── hooks/useWaybillJob.ts      ← WebSocket real-time updates (به‌جای Polling)
│   │   │   ├── lib/api.ts                  ← Axios + JWT interceptor
│   │   │   └── schemas/waybillSchema.ts    ← Zod v4 validation
│   │   └── public/manifest.json      ← PWA فارسی
│   └── backend/                      ← بک‌اند Node.js (Prisma + Express — اختیاری)
│
├── alembic/                          ← مایگریشن‌های دیتابیس
│   └── versions/
│       ├── 001_initial.py
│       ├── 002_phase1_rpa_backend.py
│       ├── 003_add_waybill_jobs_correlation_id.py
│       └── 004_add_otp_backoff_and_timezone.py  ← افزودن OTP_BACKOFF
│
├── docker-compose.yml                ← Full stack: postgres, redis, backend, frontend, nginx
├── Dockerfile                        ← Python backend image
└── .env                              ← تنظیمات محیطی
```

---

## 🚀 شروع سریع

### پیش‌نیازها
| مورد | نسخه |
|---|---|
| Python | 3.11+ |
| Node.js | 20+ |
| PostgreSQL | 16+ |
| Redis | 7+ |

### ۱. نصب وابستگی‌ها
```bash
# بک‌اند Python
pip install -r requirements.txt
playwright install chromium

# فرانت‌اند Node.js
cd apps/web
yarn install
```

### ۲. تنظیمات محیطی
```bash
cp .env.example .env
# ویرایش .env و تنظیم:
# - DATABASE_URL
# - REDIS_URL
# - FRONTEND_URL=http://localhost:3000
# - JWT_SECRET
```

### ۳. اجرای پروژه
```bash
# روش ۱: Docker Compose (توصیه شده)
docker compose up --build

# روش ۲: Development (دستی)
# Terminal 1 — بک‌اند
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload

# Terminal 2 — فرانت‌اند
cd apps/web && yarn dev
```

---

## 🔌 اتصال فرانت به بک‌اند

| مورد | مقدار |
|---|---|
| **بک‌اند API** | `http://localhost:8000/api` |
| **فرانت پورت** | `3000` |
| **CORS** | `FRONTEND_URL=http://localhost:3000` |
| **Auth** | JWT Bearer token (از کوکی `auth_token`) |

### Endpointهای کلیدی
| روش | مسیر | توضیح |
|---|---|---|
| `POST` | `/api/v1/auth/login` | ورود کاربر |
| `POST` | `/api/v1/waybill-jobs` | ایجاد بارنامه جدید |
| `GET` | `/api/v1/waybill-jobs/{job_id}` | دریافت وضعیت کار |
| `POST` | `/api/v1/drivers` | افزودن راننده |
| `GET` | `/api/v1/drivers` | لیست رانندگان |
| `POST` | `/api/v1/upload/excel` | آپلود اکسل |

---

## 🤖 قابلیت‌های ربات RPA

### Self-Healing Mechanics
- **Fallback Locators**: استفاده از `.or_()` برای انتخاب چندگانه
- **Exponential Backoff**: `T_wait(k) = 2^k × 1000ms` (حداکثر ۳ تلاش)
- **Overlay Detection**: تشخیص و بستن خودکار مودال‌های مسدود
- **Network Resilience**: تلاش مجدد خطاهای شبکه با jitter

### OTP Graceful Exit
- تشخیص خودکار مودال OTP پس از ثبت
- خروج امن بدون نشت حافظه
- بازگشت وضعیت `OTP_BACKOFF` + `next_retry_at_minutes_add: 60`
- Worker زمان بعدی را محاسبه و در DB ذخیره می‌کند

### حل کپچا
- **CNN Neural Network**: مدل محلی آموزش‌دیده
- **Math Expression Parser**: تجزیه عبارت‌های ریاضی
- **External Provider API**: سرویس خارجی (اختیاری)
- **Manual Input**: ورود دستی در حالت non-headless

### انتخاب مکان
- **Google Maps**: کلیک روی نقشه و انتخاب مختصات
- **OpenLayers**: پشتیبانی از نقشه‌های OpenLayers
- **Leaflet**: پشتیبانی از Leaflet
- **Dropdown Fallback**: انتخاب از منوی کشویی
- **Text Input**: ورود متن برای شهر/استان

---

## 📱 رابط کاربری وب

### تکنولوژی‌ها
| ابزار | نسخه |
|---|---|
| Next.js | 15 (App Router) |
| TypeScript | 5.7 |
| Tailwind CSS | 4 |
| Shadcn UI | — |
| React Query | v5 |
| Zod | v4 |
| Playwright | — |

### ویژگی‌ها
- ✅ **فارسی + RTL** با فونت Vazirmatn
- ✅ **PWA** — نصب‌پذیر روی موبایل
- ✅ **Mobile-First** — طراحی واکنش‌گرا
- ✅ **تاریخ شمسی** — نمایش تاریخ به شمسی
- ✅ **تاریخچه** — نمایش کارت‌های رنگی وضعیت
- ✅ **وضعیت زنده** — Polling هر ۳ ثانیه
- ✅ **Toast** — اعلان‌های موفقیت/خطا

### وضعیت‌های کار (Job Status)
| وضعیت | توضیح | رنگ |
|---|---|---|
| `pending` | در انتظار | خاکستری |
| `queued` | در صف | خاکستری |
| `in_progress` | در حال پردازش | آبی |
| `otp_backoff` | توقف موقت (نیاز به پیامک) | کهربایی ⚠️ |
| `success` | موفق | سبز ✅ |
| `failed` | ناموفق | قرمز ❌ |
| `dead_letter` | عدم ثبت نهایی | قرمز |

---

## 🗄️ دیتابیس

### جداول اصلی
| جدول | توضیح |
|---|---|
| `clients` | مشتریان (مستأجران) |
| `drivers` | رانندگان با اعتبارنامه UTCMS |
| `waybill_jobs` | کارهای ثبت بارنامه |
| `waybill_task_logs` | لاگ اجرای هر کار |
| `upload_batches` | دسته‌های آپلود اکسل |

### مایگریشن
```bash
# ایجاد مایگریشن جدید
alembic revision -m "description"

# اجرای مایگریشن‌ها
alembic upgrade head
```

---

## 🔐 امنیت

- رمزنگاری رمز عبور رانندگان (Fernet)
- JWT Authentication برای API
- CORS محدود به FRONTEND_URL
- Rate Limiting برای endpointها
- Input Validation با Pydantic + Zod
- HTTP Strict Transport Security (HSTS)

---

## 📊 Monitoring

| ابزار | آدرس |
|---|---|
| Prometheus | `http://localhost:9090` |
| FastAPI Docs | `http://localhost:8000/docs` |
| Health Check | `http://localhost:8000/healthz` |

---

## 🐛 عیب‌یابی

| مشکل | راه‌حل |
|---|---|
| CORS error | `FRONTEND_URL` در `.env` بررسی شود |
| کپچا حل نمی‌شود | مدل CNN در `app/automation/captcha/assets/` بررسی شود |
| OTP تشخیص داده نمی‌شود | سلکتورهای `_check_otp_after_submit` بروزرسانی شود |
| فرانت build نمی‌شود | `cd apps/web && rm -rf .next node_modules && yarn install` |

---

## 📝 لایسنس

این پروژه برای استفاده داخلی توسعه داده شده است.

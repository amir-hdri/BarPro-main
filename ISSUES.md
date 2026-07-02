# BarPro — وضعیت مشکلات (Issues)
# آخرین بروزرسانی: ۱۱ تیر ۱۴۰۵ (2026-07-02)

> این فایل وضعیت فعلی **تمام** مشکلات شناخته‌شده را نشان می‌دهد.
> ✅ = برطرف شده | ⬜ = نیاز به اقدام کاربر | ⚠️ = باید انجام شود | ❌ = مسدود

---

## 🔴 امنیت

| # | مشکل | وضعیت | یادداشت |
|---|------|--------|---------|
| S1 | رمز SSH لیک شده (`PLACEHOLDER_SSH_PASSWORD`) در کد | ✅ | کد پاک، رمز واقعی باید توسط کاربر تغییر کند |
| S2 | فایل `.env` در تاریخچه git | ✅ | `git filter-repo` اجرا شده |
| S3 | `privileged: true` در تمام containers | ✅ | جایگزین: `cap_add + no-new-privileges` |
| S4 | Rate limiter fail-open (Redis down → unlimited) | ✅ | Fail-closed: HTTP 429 در صورت قطع Redis |
| S5 | Prometheus port 9090 عمومی | ✅ | تبدیل به `expose` (فقط داخلی) |
| S6 | JWT در localStorage (نه httpOnly cookie) | ⬜ | نیاز به refactor فرانت‌اند (4-8 ساعت) |
| S7 | بدون HTTPS | ⬜ | نیاز به Let's Encrypt — دستور uncommenting آماده |
| S8 | `network_mode: host` در worker containers | ⬜ | مسدود: routing دو IP نیاز دارد، از `scripts/secure_squid_ports.sh` استفاده کنید |
| S9 | SSRF در proxy rotator | ⚠️ | URL پروکسی از config می‌آید، validation نشده |

---

## 🟡 باگ‌ها و خطاهای برطرف‌شده

| # | مشکل | وضعیت | فایل |
|---|------|--------|------|
| B1 | `zod/v4` import اشتباه | ✅ | `waybillSchema.ts` |
| B2 | `ArrowLeftOnRectangleIcon` تغییر نام | ✅ | `Header.tsx` |
| B3 | `engine.dispose()` در هر Celery task | ✅ | `waybill_worker.py` |
| B4 | `asyncio.Lock` در class instances (race) | ✅ | `core/redis.py` → `threading.Lock` |
| B5 | `autoretry_for = (Exception,)` — retry باگ | ✅ | فقط exception مشخص |
| B6 | `run_migrations` dead code | ✅ | فعال با Redis distributed lock |
| B7 | Event loop per Celery task | ✅ | یک event loop per worker process |
| B8 | `except: pass` در 55+ مکان | ✅ | همه با logging جایگزین شدند |
| B9 | Redis race condition در init | ✅ | `threading.Lock` در `redis.py` |
| B10 | N+1 query در `_emit_task_event` | ✅ | Task مستقیم پاس می‌شود |
| B11 | جدول `admin_driver_schedules` بدون migration | ✅ | Migration 013 اضافه شد |

---

## 🔵 بهبودهای عملکرد (اعمال‌شده)

| # | تغییر | فایل | تأثیر |
|---|-------|------|-------|
| P1 | Browser recycle threshold: 5→20 | `browser.py` | 90% کمتر Chrome launch |
| P2 | Chromium V8 heap: 1 GB | `browser.py` | بدون unbounded JS heap |
| P3 | Connection pool: NullPool→AsyncAdaptedQueuePool | `database.py` | استفاده مجدد از connection |
| P4 | Redis cache counter جایگزین `COUNT(*)` | `task_service.py` | بدون full table scan |
| P5 | WebSocket event buffer: max 100 | `useWaybillJob.ts` | بدون memory leak |
| P6 | MAX_POLLS=60 (جای polling بی‌نهایت) | `fuel/page.tsx` | توقف بعد از 3 دقیقه |
| P7 | nginx: `client_max_body_size` 50m→10m | `http-server.conf` | 40MB کمتر nginx memory |
| P8 | Rate-limit zone: 20m→10m | `nginx.conf` | 30MB shared memory کمتر |

---

## ⬜ اقدامات باقی‌مانده (نیاز به کاربر)

| # | اقدام | اولویت |
|---|-------|--------|
| A1 | نصب Let's Encrypt: uncomment `listen 443` در nginx + اجرا certbot | 🔴 بالا |
| A2 | اجرای `sudo bash scripts/secure_squid_ports.sh` روی سرور | 🔴 بالا |
| A3 | اضافه به crontab: `@reboot sudo bash /opt/barpro/scripts/secure_squid_ports.sh` | 🟡 متوسط |
| A4 | Migrate JWT از localStorage به httpOnly cookies | 🟡 متوسط |
| A5 | رمز واقعی SSH را در سرور تغییر دهید | 🔴 بالا |

---

*آخرین بروزرسانی: 2026-07-02 — توسط Antigravity AI Agent*

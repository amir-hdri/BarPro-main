# BarPro — قوانین حیاتی و خطوط قرمز پروژه

> **این سند اجباری است.** هر توسعه‌دهنده، AI agent، یا contributor باید قبل از هر تغییری این سند را مطالعه کند.
> نقض هر یک از موارد زیر می‌تواند باعث از دست رفتن داده، نفوذ امنیتی، یا از کار افتادن سرویس شود.

---

## 🔴 خطوط قرمز مطلق (هرگز نقض نشوند)

### 0. ثبت نهایی در UTCMS

```
❌ هرگز status داخلی یا بسته‌شدن modal را معادل ثبت نهایی اعلام نکنید
❌ هرگز SUCCESS بدون tracking code را موفق نگه ندارید
❌ هرگز ALLOW_LIVE_SUBMIT را به‌صورت پیش‌فرض فعال نکنید
```

- ثبت نهایی فقط با تطبیق tracking code در پاسخ RPA، دیتابیس BarPro و History/Search UTCMS اثبات می‌شود.
- payload ناقص باید پیش از proxy/browser/driver-slot به `needs_review` برود.
- قرارداد زنده و محدودیت‌های سامانه در `docs/UTCMS_CONSTRAINTS.md` نگهداری می‌شود.

### 1. امنیت اعتبارنامه‌ها

```
❌ هرگز credential واقعی را در کد hardcode نکنید
❌ هرگز فایل .env را commit نکنید
❌ هرگز SSH password در script نگذارید
❌ هرگز JWT_SECRET کوتاه‌تر از 32 کاراکتر استفاده نکنید
```

- تمام secrets باید از **environment variables** (`.env`) خوانده شوند
- در تست‌ها از کلیدهای mock حداقل 32 بایت استفاده کنید: `"test-secret-key-32bytes-padding00"`
- `.env.example` باید همیشه به‌روز باشد — این تنها سند رسمی برای متغیرهای محیطی است
- فایل‌های `.env`, `celerybeat-schedule.db`, `*.db` در `.gitignore` هستند — **هرگز اضافه نکنید**

### 2. امنیت نرخ‌گذاری (Rate Limiter)

```
❌ هرگز rate limiter را fail-open نکنید (باید fail-closed باشد)
❌ هرگز X-Forwarded-For را بدون اعتبارسنجی trust نکنید
❌ هرگز endpoint /auth/login و /auth/register را بدون rate limit رها نکنید
```

- Rate limiter در صورت Redis unavailable باید **HTTP 429** برگرداند (نه اجازه دهد)
- IP واقعی از `request.client.host` (که Nginx set کرده) خوانده می‌شود، نه از `X-Forwarded-For`
- Rule های rate limit در `app/main.py` تعریف‌اند — قبل از اضافه کردن endpoint جدید آن‌ها را بررسی کنید

### 3. Token Blacklist

```
❌ هرگز is_blacklisted را fail-open (return False) نکنید
```

- اگر Redis unavailable باشد، `is_blacklisted()` باید `True` برگرداند (fail-closed)
- این رفتار در `app/core/token_blacklist.py` پیاده‌سازی شده — تغییر ندهید

### 4. Docker و Container Security

```
❌ هرگز privileged: true به container اضافه نکنید
❌ هرگز network_mode: host را حذف نکنید (تا وقتی dual-IP routing نیاز دارد)
❌ هرگز security_opt: [no-new-privileges:true] را حذف نکنید
```

- Container ها از `cap_add: [SYS_ADMIN, NET_ADMIN]` به جای `privileged: true` استفاده می‌کنند
- Squid ports 3129/3130 باید با `iptables` به localhost محدود شوند (`scripts/secure_squid_ports.sh`)

### 5. Database و ORM

```
❌ هرگز engine.dispose() در Celery task صدا نزنید
❌ هرگز asyncio.new_event_loop() در هر task ایجاد نکنید
❌ هرگز NullPool برای connection pooling استفاده نکنید
❌ هرگز session.execute() برای SELECT queries در SQLModel استفاده نکنید
```

- برای DML (INSERT/UPDATE/DELETE): از `conn = await session.connection()` و `conn.execute()` استفاده کنید
- برای SELECT: از `session.exec(select(...))` استفاده کنید (SQLModel API)
- Connection pool باید `AsyncAdaptedQueuePool(pool_size=2, max_overflow=2)` باشد
- `engine.dispose()` فقط در shutdown handler صدا زده می‌شود، نه در هر task

### 6. Security Headers

```
❌ هرگز security headers را در responses حذف نکنید
❌ هرگز CSP را بدون frame-ancestors, base-uri, form-action تنظیم نکنید
❌ هرگز Permissions-Policy را تنظیم نکنید
```

- تمام responses (Nginx و FastAPI) باید دارای headers زیر باشند:
  - `X-Content-Type-Options: nosniff`
  - `X-Frame-Options: DENY`
  - `X-XSS-Protection: 1; mode=block`
  - `Referrer-Policy: strict-origin-when-cross-origin`
  - `Content-Security-Policy` با frame-ancestors 'none', base-uri 'self', form-action 'self'
  - `Permissions-Policy: geolocation=(), microphone=(), camera=()`

### 7. Redis Configuration

```
❌ هرگز Redis را بدون connection pool تنظیمات استفاده نکنید
❌ هرگز timeout و retry برای Redis تنظیم نکنید
```

- تمام Redis clients باید دارای تنظیمات زیر باشند:
  - `socket_connect_timeout`: 5
  - `socket_timeout`: 5
  - `retry_on_timeout`: True
  - `health_check_interval`: 30
  - `max_connections`: 10-20 (بسته به usage)

---

## 🟠 قوانین معماری حیاتی

### 6. Celery و Async

- Event loop باید **per-worker-process** باشد (نه per-task)
- از `asyncio.to_thread()` برای عملیات blocking مثل bcrypt هش کردن استفاده کنید
- `autoretry_for` فقط باید exceptions خاص و شناخته‌شده را شامل شود (نه `Exception` کلی)
- Browser Chrome instances باید **recycle** شوند (پس از 20 استفاده موفق، نه per-task)

### 7. WebSocket و Realtime

- Events از Worker ها باید از طریق **Redis pub/sub** به API process برسند
- Buffer WebSocket events باید حداکثر 100 event داشته باشد
- Polling باید محدود باشد: `MAX_POLLS=60` (3 دقیقه max)

### 8. Queue Management

- Queue depth باید از **Redis HINCRBY** خوانده شود (نه full-table scan)
- در startup، counter باید از DB seed شود (bootstrap)
- هرگز در هر status transition یک SELECT COUNT کامل اجرا نکنید

### 9. Browser Automation

- هرگز listener های page را بدون cleanup رها نکنید (`page.remove_listener()` در close)
- Timeout برای تمام browser close operations اجباری است
- Chromium V8 heap باید `--max-old-space-size=1024` (1 GB) محدود باشد
- هر browser session از یک Squid proxy اختصاصی استفاده می‌کند

---

## 🟡 الزامات تست و کیفیت

### 10. تست‌ها

```bash
# قبل از هر PR/push این‌ها باید pass شوند:
.venv/bin/pytest tests/ -q --tb=short
# نتیجه مورد انتظار: ≥989 tests, 0 failed
```

- تست‌هایی که به DB/Redis نیاز دارند: `pytest -m integration` (در production server)
- Mock های `page.on()` باید `MagicMock()` باشند (نه `AsyncMock`) — Playwright's `page.on()` sync است
- JWT_SECRET در تست‌ها باید ≥32 بایت باشد
- هرگز `except: pass` — حداقل `logger.exception(...)` یا `logger.warning(...)`

### 11. کد Python

- **Black** با `line-length=120` برای formatting
- **Ruff** با `select: E, W, F, I, B, C4, UP` برای linting
- **isort** با `black profile` برای import sorting
- Type hints اجباری برای تمام function signatures جدید
- هرگز `except: pass` — silence کردن exception ممنوع است

### 12. کد TypeScript/React

- **Zod** imports از `zod` نه `zod/v4` (پکیج `zod@3.24.1` است)
- **Heroicons v2** — از نام‌های جدید مثل `ArrowRightStartOnRectangleIcon` استفاده کنید
- JWT در **httpOnly cookie** ذخیره می‌شود، نه localStorage
- `withCredentials: true` در تمام Axios requests

---

## 🔵 الزامات Deployment

### 13. ترتیب اجرای Docker Compose

```bash
# ترتیب صحیح:
1. docker compose -f compose/infra.yml up -d      # DB + Redis
2. docker compose -f compose/proxy.yml up -d      # Squid proxies
3. docker compose -f compose/backend.yml up -d    # API + Workers
4. docker compose -f compose/web.yml up -d        # Nginx + Frontend
5. docker compose -f compose/monitoring.yml up -d # Prometheus
```

**هرگز ترتیب را تغییر ندهید** — backend به infra وابسته است، web به backend.

### 14. Migration های Database

```bash
# قبل از هر deployment:
bash manage.sh migrate   # یا: alembic upgrade head
```

- Migration ها با **PostgreSQL session-level advisory lock** اجرا می‌شوند؛
  کلید قفل `MIGRATION_ADVISORY_LOCK_ID` است و timeout از
  `MIGRATION_LOCK_TIMEOUT_SECONDS` خوانده می‌شود.
- HEAD فعلی: `038_add_multiroute_batch_distance`
- هرگز migration را manually روی production DB اجرا نکنید — از `manage.sh migrate` استفاده کنید

### 15. محدودیت‌های منابع (16 GB RAM — Central Server)

> **سرور مرکزی 16 GB RAM** — Workers 2/3 روی Remote Worker VPSها اجرا می‌شوند (Model B Scale-out)

| Container | Limit | Reservation | shm_size | تغییر |
|-----------|-------|-------------|----------|-------|
| PostgreSQL | **1.5 GB** | 768 MB | — | ↑ از 1 GB |
| Redis | **512 MB** | 256 MB | — | ↑ از 256 MB |
| Backend API | **512 MB** | 256 MB | 256 MB | ↑ از 256 MB |
| Celery Worker 1 | **3 GB** | 2.5 GB | 512 MB | ↑ از 2.5 GB |
| Celery Scheduler | **768 MB** | 384 MB | 128 MB | Dedicated rpa_scheduler consumer (FIX-A1) |
| Celery Beat | **256 MB** | 128 MB | — | ↑ از 128 MB (OOM fix) |
| Frontend (Next.js) | **1 GB** | 512 MB | — | ↑ از 512 MB |
| Nginx | **512 MB** | 256 MB | — | ↑ از 256 MB |
| Squid ×3 | 128 MB each | 64 MB each | — | — |
| Prometheus | 256 MB | 128 MB | — | — |
| Alertmanager | 128 MB | 64 MB | — | — |
| Grafana | 256 MB | 128 MB | — | — |
| **Total limits** | **~10.5 GB** ← fits in 16 GB with ~5.5 GB headroom | | | |

> Workers 2/3 (هر کدام 3 GB) روی Remote Worker VPS اجرا می‌شوند و در بودجه سرور مرکزی نیستند. Squid 2/3 فقط در استقرار تک‌سروره (Model A) وجود دارند.

### 16. پس از نصب HTTPS

```bash
# این مراحل را به ترتیب انجام دهید:
1. Let's Encrypt cert نصب کنید
2. listen 443 را در nginx.conf uncomment کنید
3. AUTH_COOKIE_SECURE=true در .env تنظیم کنید
4. bash manage.sh deploy
```

### 16.5 تنظیم FRONTEND_URL در دیپلوی Production
- متغیر محیطی `FRONTEND_URL` (یا `FRONTEND_URLS`) حتماً باید در محیط production ست شده باشد.
- در غیر این صورت، برنامه در زمان راه‌اندازی با خطای `RuntimeError` بالا نخواهد آمد تا از وقوع بی‌صدای خطای CORS جلوگیری شود.

---

## 🟢 فرآیندهای عملیاتی

### 17. ایمن‌سازی Squid Ports

```bash
# پس از هر reboot:
sudo bash scripts/secure_squid_ports.sh

# برای اجرای خودکار، در crontab اضافه کنید:
@reboot sudo bash /opt/barpro/scripts/secure_squid_ports.sh
```

### 18. Proxy Health Check

```bash
# قبل از شروع هر browser session:
GET /api/v1/system/proxies/health
```

- Worker ها قبل از session, Squid proxy را health check می‌کنند
- در صورت ناموجود بودن proxy، task باید fail شود نه hang

### 19. Captcha Providers (ترتیب auto)

```
auto → CNN (login math) → PyTorch CRNN (fuel Persian) → Keras OCR → Enhanced → Local
```

- Keras OCR باید **in-process** باشد (نه subprocess جداگانه که OOM ایجاد می‌کند)
- مدل Keras فقط یک بار per-worker-process بارگذاری می‌شود (lazy load)

### 20. Index های Database (اجرا یک بار روی production)

> **توجه**: این index ها در migration 029 (`029_add_waybill_jobs_optimization_indexes.py`) ایجاد شده‌اند.
> برای اجرای آن‌ها روی production: `bash manage.sh migrate`

```sql
CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_wj_status_priority_created
ON waybill_jobs (status, priority DESC, created_at ASC);

CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_wj_status_next_retry
ON waybill_jobs (status, next_retry_at);

CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_wj_status_covering
ON waybill_jobs (status) INCLUDE (id);
```

> علاوه بر index های بالا، model `WaybillJob` دارای index های زیر می‌باشد:
> - `idx_waybill_jobs_client_id` (client_id)
> - `idx_waybill_jobs_driver_id` (driver_id)
> - `idx_waybill_jobs_status` (status)
> - `idx_waybill_jobs_created_at` (created_at)
> - `idx_waybill_jobs_celery_task_id` (celery_task_id)

---

## 📊 معیارهای سلامت سیستم

| معیار | وضعیت سالم | آستانه هشدار |
|-------|------------|--------------|
| تست‌ها | ≥989 tests, 0 failed | هر failed |
| RAM usage | <85% (10.2 GB) | >90% (10.8 GB) |
| Disk | <85% | >90% |
| Queue depth | <50 per worker | >100 per worker |
| Captcha success rate | >85% | <70% |
| Browser recycle rate | 1 restart per 20 jobs | <10 jobs per restart |

---

## 🔗 مراجع مهم

| فایل | محتوا |
|------|-------|
| [AGENTS.md](./AGENTS.md) | راهنمای جامع برای AI agents |
| [ARCHITECTURE.md](./ARCHITECTURE.md) | معماری کامل سیستم |
| [DEPLOYMENT_GUIDE.md](./DEPLOYMENT_GUIDE.md) | راهنمای deployment |
| [ISSUES.md](./ISSUES.md) | مشکلات شناخته‌شده |
| [.env.example](./.env.example) | template متغیرهای محیطی |
| [manage.sh](./manage.sh) | ابزار مدیریت سرور |

---

## 📅 تاریخچه اصلاحات حیاتی

| تاریخ | اصلاح |
|-------|-------|
| 2026-08-02 | اضافه کردن security headers به backend FastAPI |
| 2026-08-02 | پیکربندی Redis connection pool با timeout/retry |
| 2026-08-02 | حذف hardcoded secrets از GitHub Actions workflows |
| 2026-08-02 | بهبود CSP header با frame-ancestors, base-uri, form-action |
| 2026-08-02 | اضافه کردن Permissions-Policy header |
| 2026-08-02 | پیکربندی Nginx DNS resolver برای dynamic upstream |
| 2026-08-02 | بهبود error messages برای phone validation |
| 2026-08-02 | اضافه کردن logging به exception handler در _helpers.py |
| 2026-08-02 | به‌روزرسانی کامل تمام مستندات |
| 2026-07-27 | رفع fail-open در token_blacklist و rate_limiter |
| 2026-07-27 | رفع X-Forwarded-For spoofing در rate_limiter |
| 2026-07-27 | رفع double json.loads روی JSONB columns |
| 2026-07-27 | رفع RuntimeWarning از page.on() mock در تست‌ها |
| 2026-07-27 | رفع InsecureKeyLengthWarning در JWT test fixtures |
| 2026-07-10 | Redis pub/sub bridge برای WebSocket cross-process events |
| 2026-07-10 | Keras OCR in-process (حذف subprocess per-captcha) |
| 2026-07-09 | Squid proxy pre-flight health check |
| 2026-07-08 | httpOnly cookie برای JWT |
| 2026-06-30 | حذف engine.dispose() per-task |
| 2026-06-30 | Chrome recycle threshold: 20 |

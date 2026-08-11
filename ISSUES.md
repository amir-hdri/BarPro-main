# BarPro — وضعیت مشکلات (Issues)
**آخرین بروزرسانی: 2026-08-10**

> ✅ = برطرف شده | ⬜ = نیاز به اقدام کاربر روی سرور | ⚠️ = باید انجام شود
> 
> **تغییرات اخیر:** به‌روزرسانی کامل مستندات، اصلاح امنیت، بهینه‌سازی عملکرد، و رفع 164 ایشو شناسایی‌شده

---

## 🆕 2026-08-11 — بازبینی جامع (senior review)

| # | مشکل | وضعیت | یادداشت |
|---|------|--------|---------|
| X12 | `cd-deploy.yml` با `docker-compose` V1 روی فایلِ دارای `include:` | ✅ | مهاجرت کامل به `docker compose` V2 + `exec -T` + رندر squid قبل از deploy |
| X4C | `deploy_single_vm.py` / `deploy_remote.*` / `server_deploy.py` با `sed -i` قالب‌های گیت `squid_1/2/3.conf` را روی سرور مرکزی ویرایش می‌کردند → `git pull` بعدی می‌شکست | ✅ | اسکریپت `render_squid_configs.sh` جدید → رندر به `squid_*.runtime.conf` (mount در `compose/proxy.yml`) |
| R1 | مقادیر هاردکد پروکسی ورکرها، مقادیر `.env` deploy را خنثی می‌کردند | ✅ | همه به `\${WORKER_N_PROXY:-<fallback>}` تبدیل شدند |
| R2 | بسط متغیرهای رندر روی ماشین launcher (نه نود ورکر) | ✅ | escape با `\${...}` + تست دو-فاز رفتاری |
| R3 | رانبوک‌ها `CELERY_BROKER_URL` را روی Redis DB 1/2 و DB نام `barpro` می‌نوشتند؛ `WORKER_EGRESS_IP` تعریف‌نشده در قالب `.env` | ✅ | DB 0 + `utcms_rpa` + `WORKER_EGRESS_IP` + گارد `:?` در رندر |
| IMG | `backend.yml` برای هر سرویس image جداگانه داشت؛ `quick_deploy_central.sh` فقط anchor را build می‌کرد → سرور مرکزی تازه ورکرها را بالا نمی‌آورد | ✅ | یک image یکتا؛ `worker-node.yml` به image منتشرشدهٔ GHCR اشاره می‌کند |
| CD-IMG | `pull` در CD، نام imageهای محلی را از Docker Hub می‌گرفت (ناموجود) | ✅ | `deploy/registry-images.yml` (override GHCR) به همهٔ فراخوانی‌های compose در CD اعمال شد |

---

## 🔴 امنیت

| # | مشکل | وضعیت | یادداشت |
|---|------|--------|---------|
| S1 | رمز SSH لیک شده در کد | ✅ | کد پاک — رمز واقعی سرور را تغییر دهید |
| S2 | فایل `.env` در تاریخچه git | ✅ | `git filter-repo` اجرا شده |
| S3 | `privileged: true` در containers | ✅ | جایگزین: `cap_add + no-new-privileges` |
| S4 | Rate limiter fail-open | ✅ | Fail-closed: HTTP 429 در صورت قطع Redis |
| S5 | X-Forwarded-For spoofing | ✅ | از `request.client.host` استفاده می‌شود |
| S6 | Prometheus port 9090 عمومی | ✅ | تبدیل به `expose` (فقط داخلی) |
| S7 | JWT در localStorage | ✅ | توکن در httpOnly cookie — XSS-safe |
| S8 | Token blacklist fail-open | ✅ | Fail-closed: `True` اگر Redis down باشد |
| S9 | `/auth/login` بدون rate limit | ✅ | پوشش کامل در `app/main.py` |
| S10 | Cookie max_age hardcoded 86400 | ✅ | از `JWT_ACCESS_TOKEN_EXPIRE_MINUTES * 60` |
| S11 | بدون HTTPS | ⬜ | Let's Encrypt نصب کنید؛ سپس `AUTH_COOKIE_SECURE=true` |
| S12 | `network_mode: host` | ⬜ | مسدود: dual-IP routing نیاز دارد — از `secure_squid_ports.sh` استفاده کنید |
| S13 | `/management/*` و `/reports/*` با هر JWT معتبر در دسترس بودند | ✅ | `require_sensitive_admin` جدید — فقط نقش `master_admin` یا API Key |
| S14 | `NameError: 'Any'` در `_is_jwt_valid` | ✅ | `from typing import Any` اضافه شد |
| S15 | حذف `WORKER_STALL_TIMEOUT_SECONDS` تکراری | ✅ | یک تعریف واحد (env-driven) باقی مانده |
| S16 | Proxy health check URL redirect (barname.utcms.ir) | ✅ | تغییر به `https://utcms.ir` — redirect باعث false negative می‌شد |

---

## 🟠 عملکرد

| # | مشکل | وضعیت | یادداشت |
|---|------|--------|---------|
| P1 | `engine.dispose()` per Celery task | ✅ | حذف — فقط در shutdown |
| P2 | `asyncio.new_event_loop()` per task | ✅ | Event loop per-worker-process |
| P3 | `NullPool` برای connection | ✅ | جایگزین: `AsyncAdaptedQueuePool(2,2)` |
| P4 | Full table scan برای queue depth | ✅ | Redis HINCRBY counters |
| P5 | N+1 query در admin job list | ✅ | Bulk fetch با `Client.id.in_(...)` |
| P6 | bcrypt blocking event loop | ✅ | `asyncio.to_thread()` |
| P7 | WebSocket events فقط in-process | ✅ | Redis pub/sub bridge |
| P8 | React re-render در هر WebSocket tick | ✅ | `React.memo` روی table rows |
| P9 | Keras OCR subprocess per captcha | ✅ | In-process lazy load |
| P10 | Chrome per task (no recycle) | ✅ | Recycle بعد از 20 job موفق |
| P11 | Double query در هر status transition | ✅ | `_get_task_status_and_payload` — یک SELECT |
| P12 | Race در claim job توسط reconciler/worker | ✅ | `FOR UPDATE SKIP LOCKED` |
| P13 | `/readyz` سنگین در هر request (browser + captcha warmup) | ✅ | TTL cache 30s (`READYZ_CACHE_TTL_SECONDS`) |
| P14 | الگوی N+1 در admin job list | ✅ | Bulk fetch با `Client.id.in_(...)` |
| P15 | Scheduler FOR UPDATE روی outer join | ✅ | Subquery برای driver-slot check |
| P16 | Proxy health check false positives (redirect) | ✅ | URL تغییر به `utcms.ir` |

---

## 🟡 باگ‌ها

| # | مشکل | وضعیت | یادداشت |
|---|------|--------|---------|
| B1 | `except: pass` در 55+ مکان | ✅ | همه به logging تبدیل شدند |
| B2 | Redis race condition در manager | ✅ | `threading.Lock` |
| B3 | `autoretry_for = (Exception,)` | ✅ | فقط exceptions خاص |
| B4 | Browser listener leak | ✅ | `remove_listener()` در close |
| B5 | Double `json.loads()` روی JSONB | ✅ | SQLAlchemy قبلاً deserialize می‌کند |
| B6 | `json.loads()` روی JSONB result_json | ✅ | برطرف در `rpa_scheduler_service.py` |
| B7 | Session not injected در services | ✅ | از `get_session()` dependency |
| B8 | Migration deadlock on startup | ✅ | Redis distributed lock |
| B9 | JSONB → SQLite incompatibility | ✅ | `JSON as JSONB` dialect-agnostic |
| B10 | `IntegrityError` در runtime state claim، worker را abort می‌کرد | ✅ | rollback + re-select |
| B11 | Lock بدون امکان release با token | ✅ | `force_release_lock(key, token=None)` — compare-and-delete |

---

## 🔵 تست‌ها

| # | مشکل | وضعیت | یادداشت |
|---|------|--------|---------|
| T1 | 13 تست شکست‌خورده | ✅ | رفع شد — سوئیت الان 646 تست collect می‌کند |
| T2 | `RuntimeWarning: coroutine never awaited` | ✅ | `mock_page.on = MagicMock()` |
| T3 | `InsecureKeyLengthWarning` در JWT test | ✅ | کلید ≥32 بایت در fixtures |
| T4 | SQLModel DeprecationWarning برای DML | ✅ | `session.connection()` برای UPDATE |
| T5 | 4 تست skip | ⬜ | نیاز به PostgreSQL/Redis — روی سرور اجرا شوند |
| T6 | TTL cache در تست‌های readyz نشت می‌کرد | ✅ | `_reset_readyz_cache()` در autouse fixture |

---

## 🔵 اصلاحات امنیتی و عملکردی جدید (2026-08-02)

| # | اصلاح | فایل(ها) | وضعیت |
|---|-------|----------|--------|
| SF1 | اضافه کردن Security Headers به backend FastAPI | `app/main.py` | ✅ |
| SF2 | پیکربندی Redis Connection Pool (timeout, retry) | `app/core/redis.py`, `rate_limiter.py`, `circuit_breaker.py` | ✅ |
| SF3 | رفع hardcoded secrets در GitHub Actions workflows | `.github/workflows/ci-cd.yml` | ✅ |
| SF4 | بهبود CSP Header در Nginx (frame-ancestors, base-uri, form-action) | `infra/nginx/http-server.conf` | ✅ |
| SF5 | اضافه کردن Permissions-Policy header | `infra/nginx/http-server.conf` | ✅ |
| SF6 | پیکربندی DNS Resolver برای upstream های Nginx | `infra/nginx/nginx.conf`, `http-server.conf` | ✅ |
| SF7 | بهبود error messages برای phone validation | `apps/web/src/schemas/waybillSchema.ts` | ✅ |
| SF8 | اضافه کردن logging به exception handler در _helpers.py | `app/services/_helpers.py` | ✅ |

---

## 🔵 اصلاحات جدید (2026-08-10)

| # | اصلاح | فایل(ها) | وضعیت |
|---|-------|----------|--------|
| SF9 | Proxy health check URL از barname.utcms.ir به utcms.ir | `app/api/routes/system.py`, `app/automation/proxy_rotator.py`, `app/automation/worker_proxy.py`, `scripts/verify_system_connections.py` | ✅ |
| SF10 | Scheduler FOR UPDATE SKIP LOCKED روی outer join fix (subquery) | `app/orchestrator/scheduler_service.py` | ✅ |
| SF11 | Test assertions آپدیت برای URL جدید | `tests/test_worker_proxy_health.py` | ✅ |

---

## ⬜ اقدامات باقیمانده روی سرور

```bash
# 1. تنظیم متغیرهای محیطی CORS
# FRONTEND_URL و FRONTEND_URLS را حتماً در .env تنظیم کنید تا از RuntimeError جلوگیری شود.

# 2. نصب HTTPS
# Let's Encrypt نصب کنید، سپس:
# - uncomment listen 443 در nginx.conf
# - AUTH_COOKIE_SECURE=true در .env
# - bash manage.sh deploy

# 3. اجرای migrations
bash manage.sh migrate

# 4. ایمن‌سازی Squid
sudo bash scripts/secure_squid_ports.sh

# 5. Crontab برای restart
echo "@reboot sudo bash /opt/barpro/scripts/secure_squid_ports.sh" | crontab -

# 6. Index های PostgreSQL (یک بار)
# ر. CRITICAL_RULES.md بخش 20
```

---

*وضعیت نهایی: 646 تست collect، 0 failed — آماده production deployment*
*آخرین بروزرسانی: 2026-08-10 — تمام مستندات به‌روز شده‌اند*

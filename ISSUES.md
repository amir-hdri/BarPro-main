# BarPro — وضعیت مشکلات (Issues)
**آخرین بروزرسانی: 2026-07-27**

> ✅ = برطرف شده | ⬜ = نیاز به اقدام کاربر روی سرور | ⚠️ = باید انجام شود

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

---

## 🔵 تست‌ها

| # | مشکل | وضعیت | یادداشت |
|---|------|--------|---------|
| T1 | 13 تست شکست‌خورده | ✅ | 414 passed, 0 failed |
| T2 | `RuntimeWarning: coroutine never awaited` | ✅ | `mock_page.on = MagicMock()` |
| T3 | `InsecureKeyLengthWarning` در JWT test | ✅ | کلید ≥32 بایت در fixtures |
| T4 | SQLModel DeprecationWarning برای DML | ✅ | `session.connection()` برای UPDATE |
| T5 | 4 تست skip | ⬜ | نیاز به PostgreSQL/Redis — روی سرور اجرا شوند |

---

## ⬜ اقدامات باقیمانده روی سرور

```bash
# 1. نصب HTTPS
# Let's Encrypt نصب کنید، سپس:
# - uncomment listen 443 در nginx.conf
# - AUTH_COOKIE_SECURE=true در .env
# - bash manage.sh deploy

# 2. اجرای migrations
bash manage.sh migrate

# 3. ایمن‌سازی Squid
sudo bash scripts/secure_squid_ports.sh

# 4. Crontab برای restart
echo "@reboot sudo bash /opt/barpro/scripts/secure_squid_ports.sh" | crontab -

# 5. Index های PostgreSQL (یک بار)
# ر. CRITICAL_RULES.md بخش 20
```

---

*وضعیت نهایی: 414 تست pass، 0 شکست — آماده production deployment*

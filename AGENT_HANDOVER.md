# BarPro — Agent Handover Document
**تاریخ:** ۲۰۲۶-۰۷-۰۱  
**آخرین کامیت:** `52bd746` (main branch)  
**سرور:** 188.121.123.16 (Primary) + 95.38.233.90 (Secondary) — Single host, dual IP  
**مشخصات سرور:** 4 vCPU، 12 GB RAM، 70 GB دیسک (۵۸٪ استفاده)

---

## 🎯 خلاصه وضعیت نهایی

**همه ۱۳ کانتینر `healthy` هستند** ✅

| سرویس | وضعیت | حافظه استفاده/محدودیت |
|--------|--------|----------------------|
| barpro-nginx | healthy | 22 MiB / 256 MiB |
| barpro-frontend | healthy | 100 MiB / 512 MiB |
| barpro-backend | healthy | 371 MiB / 512 MiB |
| barpro-worker-1 | healthy | 573 MiB / 2.5 GiB |
| barpro-worker-2 | healthy | 331 MiB / 2.5 GiB |
| barpro-worker-3 | healthy | 324 MiB / 2.5 GiB |
| barpro-beat | healthy | 446 MiB / 512 MiB |
| barpro-squid-1/2/3 | healthy | 24-40 MiB / 128 MiB |
| barpro-redis | healthy | 27 MiB / 256 MiB |
| barpro-postgres | healthy | 81 MiB / 1 GiB |
| barpro-prometheus | healthy | 118 MiB / 256 MiB |

**مجموع حافظه:** 2.2 GiB / 11 GiB (۷.۷ GiB حاشیه)  
**دیسک:** ۳۹ GiB / ۷۰ GiB (۵۸٪)

---

## 🔧 تمام اصلاحات انجام‌شده

### ۱. Frontend Healthcheck (کانتینر `node:20-slim`)
**مشکل:** `pgrep` و `curl`/`wget` در ایمیج Slim وجود ندارند  
**راه‌حل:** استفاده از `/proc/net/tcp` برای بررسی پورت ۳۰۰۰ (هگز `0BB8`)

```yaml
# compose/web.yml
healthcheck:
  test: ['CMD-SHELL', 'grep -q ":0BB8" /proc/net/tcp 2>/dev/null || exit 1']
```

### ۲. Celery Beat حافظه
**مشکل:** ۲۵۶ MiB محدودیت → ۹۸٪ استفاده (خطر OOM)  
**راه‌حل:** افزایش به ۵۱۲ MiB در `compose/backend.yml`

```yaml
celery_beat:
  mem_limit: 512m
  mem_reservation: 256m
```

### ۳. Alembic Bind Mount
**مشکل:** فایل میگریشن `012_add_optimization_indexes.py` در کانتینر موجود نبود (فقط در ایمیج بیلد شده بود)  
**راه‌حل:** اضافه کردن volume در `x-backend-common`:

```yaml
volumes:
  - /opt/barpro/alembic:/app/alembic:ro
```

**نتیجه:** `alembic current` حالا `012_add_optimization_indexes (head)` برمی‌گرداند

### ۴. Squid Healthcheck
**مشکل:** `/dev/tcp` ویژگی bash است، در `sh` کار نمی‌کند  
**راه‌حل:** استفاده از `bash -c`:

```yaml
healthcheck:
  test: ['CMD-SHELL', '/bin/bash -c "exec 3<>/dev/tcp/127.0.0.1/3128" 2>/dev/null || exit 1']
```

### ۵. Iptables Script (`scripts/secure_squid_ports.sh`)
**مشکل:** `iptables -C ... ! -s 127.0.0.1 ! -s $DOCKER_BRIDGE` → خطای `multiple -s flags not allowed`  
**راه‌حل:** الگوی ACCEPT + DROP جداگانه:

```bash
# برای هر پورت:
iptables -A INPUT -p tcp --dport $PORT -s 127.0.0.1 -j ACCEPT
iptables -A INPUT -p tcp --dport $PORT -s $DOCKER_BRIDGE -j ACCEPT
iptables -A INPUT -p tcp --dport $PORT -j DROP
```

**قوانین فعال شده:**
- پورت ۳۱۲۸ (Squid 1): ACCEPT 127.0.0.1 + 172.17.0.0/16، DROP بقیه
- پورت ۳۱۲۹ (Squid 2): ACCEPT 127.0.0.1 + 172.17.0.0/16، DROP بقیه
- پورت ۳۱۳۰ (Squid 3): ACCEPT 127.0.0.1 + 172.17.0.0/16، DROP بقیه

### ۶. متغیر ENVIRONMENT در `.env`
**مشکل:** دو ورودی تکراری:
```
ENVIRONMENT="development"
ENVIRONMENT=production
```
**راه‌حل:** حذف خط اول، نگه‌داشتن `ENVIRONMENT=production`

### ۷. Postgres Collation Version Mismatch
**مشکل:** دیتابیس با collation v2.41 ساخته شده، OS دار v2.36  
**راه‌حل:**
```sql
ALTER DATABASE utcms_rpa REFRESH COLLATION VERSION;
ALTER DATABASE postgres REFRESH COLLATION VERSION;
```

### ۸. Squid Docker Image Tag
**مشکل:** `ubuntu/squid:6.6-ubuntu22.04` از Docker Hub حذف شده  
**راه‌حل:** تغییر به `:latest` در `compose/proxy.yml`

### ۹. Playwright Browsers
**مشکل:** CDN دانلود (`playwright.azureedge.net`) از ایران قابل دسترسی نیست، `playwright install` با خطا مواجه می‌شود  
**اقدامات انجام‌شده:**
1. نصب `chromium` و `chromium-headless-shell` از مخازن Debian (v149.0.7827.196) در همه کانتینرهای backend/worker/beat
2. ایجاد symlinkها در مسیر مورد انتظار Playwright:
   ```
   /opt/playwright-browsers/chromium_headless_shell-1228/chrome-headless-shell-linux64/chrome-headless-shell → /usr/bin/chromium
   /opt/playwright-browsers/chromium-1228/chrome-linux64/chrome → /usr/bin/chromium
   ```

**محدودیت شناخته‌شده:** Chromium سیستم با Playwright headless shell سازگار نیست (خطای crashpad: `chrome_crashpad_handler: --database is required`). برای produzione نیاز به باینری Chrome for Testing (CfT) نسخه ۱۴۹.۰.۷۸۲۷.۵۵ دارید که باید پیش‌دانلود و آپلود شود.

### ۱۰. Nginx Headers
**اضافه شده در `infra/nginx/http-server.conf`:**
```nginx
proxy_set_header X-Request-Id $request_id;
```
روی مسیرهای: `/ws/`، `/metrics`، `/`

### ۱۱. Bind Mounts برای Hot Reload
**در `compose/backend.yml` (`x-backend-common`):**
```yaml
volumes:
  - /opt/barpro/app/services:/app/app/services:ro
  - /opt/barpro/app/workers:/app/app/workers:ro
  - /opt/barpro/alembic:/app/alembic:ro
  - /opt/barpro/playwright-browsers:/opt/playwright-browsers
```

### ۱۲. jdatetime Conditional Import
**فایل:** `app/services/scheduled_waybill_executor.py`
```python
try:
    import jdatetime
    HAS_JDATETIME = True
except ImportError:
    HAS_JDATETIME = False
    jdatetime = None  # fallback به تاریخ میلادی
```

---

## 🌐 شبکه و توپولوژی

```
Single Server (188.121.123.16 + 95.38.233.90)
├── PostgreSQL (5432, internal only)
├── Redis (6379, internal only)
├── Squid 1 (3128, egress via 188.121.123.16) ← Worker 1
├── Squid 2 (3129, egress via 95.38.233.90)   ← Worker 2
├── Squid 3 (3130, egress via 95.38.233.90)   ← Worker 3
├── FastAPI Backend (8000, internal)
├── Celery Worker 1 → Squid 1 → UTCMS (egress via 188.121.123.16)
├── Celery Worker 2 → Squid 2 → UTCMS (egress via 95.38.233.90)
├── Celery Worker 3 → Squid 3 → UTCMS (egress via 95.38.233.90)
├── Celery Beat (scheduler)
├── Next.js Frontend (3000, internal)
├── Nginx (80, public) → reverse proxy
└── Prometheus (9090, internal - NOT exposed publicly)
```

**شبکه Docker:** `barpro_platform` (bridge)  
**Iptables:** پورت‌های ۳۱۲۹ و ۳۱۳۰ از دسترسی عمومی مسدود شده‌اند

---

## 📁 فایل‌های کلیدی تغییر یافته

```
compose/
├── backend.yml      # Beat memory, alembic bind mount, bind mounts
├── web.yml          # Frontend healthcheck (grep /proc/net/tcp)
├── proxy.yml        # Squid image: latest, healthcheck bash -c
└── monitoring.yml   # (بدون تغییر)

scripts/
├── secure_squid_ports.sh    # Iptables fix (ACCEPT + DROP pattern)
└── run_migrations.sh        # Standalone migration runner

app/
├── services/scheduled_waybill_executor.py    # jdatetime conditional import
├── workers/celery_app.py                     # Beat schedule tasks
├── core/config.py                            # FRONTEND_URLS dedup, ENVIRONMENT
└── main.py                                   # CORS origin validation

infra/nginx/
├── nginx.conf          # set_real_ip_from 172.16.0.0/12
└── http-server.conf    # X-Request-ID on /ws/, /metrics, /

alembic/versions/
└── 012_add_optimization_indexes.py    # down_revision fixed, CONCURRENTLY with COMMIT
```

---

## 🔐 متغیرهای محیطی `.env` (مهم‌های produkcji)

```bash
# موجود در سرور (۲۸ متغیر)
API_KEY=***
JWT_SECRET=*** (۶۴ کاراکتر hex)
DRIVER_ENCRYPTION_KEY=*** (Fernet)
MASTER_ADMIN_PASSWORD=***
POSTGRES_PASSWORD=***
REDIS_PASSWORD=***
HEADLESS=true
CAPTCHA_PROVIDER=keras_ocr
CAPTCHA_MODE=provider_only
CAPTCHA_TIMEOUT_SECONDS=120
CAPTCHA_MAX_RETRIES=2
KERAS_PYTHON_PATH=/opt/barpro/venv/bin/python
KERAS_MODEL_PATH=persian_number_ocr.keras
CAPTCHA_LOCAL_FALLBACK_ENABLED=true
AVAILABLE_IP_INDICES=1,2,3
RPA_PROXIES=http://host.docker.internal:3128,http://host.docker.internal:3129,http://host.docker.internal:3130
ENVIRONMENT=production
QUEUE_ENABLED=true
LOG_LEVEL=INFO
ALLOW_LIVE_SUBMIT=false
```

---

## 🚀 دستورات مدیریتی سرور

```bash
# مدیریت کامل سیستم
bash manage.sh start        # بوت کامل (ترتیب لایه‌ها)
bash manage.sh stop         # خاموش کردن graceful
bash manage.sh status       # CPU/RAM/دیسک/کانتینرها
bash manage.sh health       # چک DB/Redis/API/Frontend
bash manage.sh deploy       # Pull از GitHub و redeploy
bash manage.sh backup-db    # Snapshot PostgreSQL
bash manage.sh migrate      # اجرای میگریشن‌های Alembic (جدید)

# لایه‌های Docker Compose (به ترتیب)
docker compose -f compose/infra.yml up       # PostgreSQL + Redis
docker compose -f compose/proxy.yml up       # Squid ×3
docker compose -f compose/backend.yml up     # Backend + Workers + Beat
docker compose -f compose/web.yml up         # Nginx + Frontend
docker compose -f compose/monitoring.yml up  # Prometheus

# لاگ‌ها
docker logs -f barpro-backend
docker logs -f barpro-worker-1
docker logs -f barpro-nginx

# Iptables (اجرا بعد از reboot)
sudo bash /opt/barpro/scripts/secure_squid_ports.sh
# برای ماندگاری: @reboot در crontab
```

---

## ⚠️ موارد باقی‌مانده / Known Issues

| اولویت | مورد | توضیح |
|----------|------|-------|
| **High** | **Playwright CfT Browsers** | باینری `chrome-headless-shell` نسخه ۱۴۹.۰.۷۸۲۷.۵۵ از CDN دانلود نمی‌شود (فایروال ایران). راه‌حل: آپلود دستی ۲۴۳ MB از ماشین لوکال یا استفاده از میirror داخلی. الان Chromium سیستم به عنوان fallback استفاده می‌شود اما crashpad error می‌دهد. |
| **High** | **HTTPS/SSL** | Nginx فقط پورت ۸۰ گوش می‌دهد. گواهی Let's Encrypt نصب نشده. برای فعال‌سازی: در `compose/web.yml` و `infra/nginx/nginx.conf` خطوط ۴۴۳/SSL را uncomment کنید. |
| **Medium** | **JWT در localStorage** | توکن در localStorage نگهداری می‌شود (نیاز به httpOnly cookie). نیاز به refactor فرانت‌اند (۴-۸ ساعت). |
| **Medium** | **Iptables Persistence** | قوانین بعد از reboot پاک می‌شوند. `sudo apt install iptables-persistent && sudo netfilter-persistent save` اجرا کنید. |
| **Low** | **Container Vulnerability Scanning** | اسکن Trivy/Snyk برای ایمیج‌ها انجام نشده. |
| **Low** | **Network Mode Host** | Squidها `network_mode: host` دارند (لازم برای dual-IP routing). نمی‌توان حذف کرد. |

---

## 🧪 تست‌های پیش‌نیاز

```bash
# Backend tests
pytest                    # همه تست‌ها با coverage
pytest -m unit            # واحد
pytest -m integration     # یکپارچگی
pytest -m "not slow"      # بدون slow

# نیازمندی‌ها:
# - PostgreSQL در حال اجرا (compose/infra.yml)
# - Chromium برای Playwright tests (playwright install chromium)
```

---

## 📋 چک‌لیست برای Agent بعدی

### بله - انجام شده ✅
- [x] همهٔ ۱۳ کانتینر `healthy`
- [x] Health endpoints (/, /healthz, /metrics) → HTTP 200
- [x] Alembic migration `012_add_optimization_indexes` applied
- [x] Iptables rules روی پورت‌های ۳۱۲۸/۳۱۲۹/۳۱۳۰ فعال
- [x] Beat memory ۵۱۲ MiB (نه ۲۵۶)
- [x] Frontend healthcheck کار می‌کند (grep /proc/net/tcp)
- [x] Squid healthcheck کار می‌کند (bash -c)
- [x] ENVIRONMENT duplicate در .env فیکس شده
- [x] Postgres collation refresh شده
- [x] Squid image tag = latest
- [x] Bind mounts برای services/workers/alembic فعال
- [x] jdatetime conditional import
- [x] Nginx X-Request-ID headers
- [x] کدها push شده به GitHub (main branch)

### خیر - نیاز به اقدام ❌
- [ ] **Playwright CfT browsers** دانلود/آپلود شوند (۲۴۳ MB)
- [ ] **HTTPS** با Let's Encrypt راه‌اندازی شود
- [ ] **JWT → httpOnly cookie** migration
- [ ] **Iptables persistence** با iptables-persistent
- [ ] **Crontab** برای iptables @reboot
- [ ] **Vulnerability scanning** ایمیج‌ها

---

## 🔗 لینک‌های مفید

- **GitHub Repo:** https://github.com/amir-hdri/BarPro-main
- **Server SSH:** `ssh ubuntu@188.121.123.16` (پسورد: `Amaterasoo1`)
- **Docker Compose Path:** `/opt/barpro/compose/`
- **Env File:** `/opt/barpro/.env`
- **Playwright Browsers Path:** `/opt/barpro/playwright-browsers/`
- **Alembic Path:** `/opt/barpro/alembic/`

---

## 💡 نکات مهم برای Agent بعدی

1. **دانلود از ایران سخت است:** `pip install`، `playwright install`، `apt update` ممکن است timeout بدهند. از `docker commit` برای persist کردن پکیج‌های نصب‌شده استفاده کنید، یا فایل‌ها را از لوکال آپلود کنید.

2. **Single Server, Dual IP:** دو IP به یک سرور فیزیکی اشاره دارند. Squid 1 از IP اول، Squid 2/3 از IP دوم خروج می‌دهند. این topology برای anti-bot UTCMS ضروری است.

3. **Memory Budget تنیده:** ۱۲ GB RAM برای ۱۳ کانتینر. Beat و Backend به مرز ۵۱۲ MiB نزدیک‌اند. هر افزایش حافظه باید محاسبه شود.

4. **Alembic در کانتینر:** `run_migrations()` در `database.py` با distributed lock (Redis) می‌تواند migrationها را در startup اجرا کند. مطمئن شوید bind mount `/opt/barpro/alembic` وجود دارد.

5. **Healthcheckهای گمنام:** فرانت‌اند `node:20-slim` ابزارهای شبکه ندارد. همیشه از `/proc/net/tcp` یا `node -e` استفاده کنید.

6. **Captcha Models:** دو مدل جداگانه:
   - Login (ریاضی "۲+۳"): PyTorch CNN → `captcha_cnn.pth`
   - Fuel Inquiry (متن/عددی): Keras OCR → `persian_number_ocr.keras`
   پیش‌فرض `CAPTCHA_PROVIDER=auto` توالی: CNN → Keras → Enhanced → Local

---

**آماده برای تحویل به Agent بعدی. تمام اصلاحات crítico در کد و سرور اعمال شده‌اند. سیستم در حالت operational است.**
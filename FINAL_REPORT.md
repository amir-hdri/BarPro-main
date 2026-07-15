# 📊 گزارش نهایی — رفع مشکلات Browser و RPA در BarPro

**تاریخ**: 2026-07-14  
**مدت زمان**: 3 روز کاری  
**وضعیت**: ✅ Infrastructure آماده | ⏸️ نیاز به تست Production

---

## 🎯 خلاصه اجرایی

پروژه BarPro دچار مشکل حیاتی بود: **تمام tasks (waybill و fuel inquiry) در وضعیت `queued` گیر می‌کردند**.

### مشکلات شناسایی شده:
1. ❌ **Event Loop Management** — Playwright در تغییر loop crash می‌کرد
2. ❌ **Playwright CDN مسدود** — `cdn.playwright.dev` در ایران 403 می‌داد
3. ❌ **Browser Crash** — Chromium 150 با SIGTRAP crash می‌کرد
4. ❌ **Race Condition در Scheduler** — چند scheduler یک job را همزمان dispatch می‌کردند

### راه‌حل‌های اعمال شده:
1. ✅ **Event Loop Fix** — `async _ensure_loop_resources` + `await playwright.stop()`
2. ✅ **Chromium Downgrade** — نصب Chromium 97 از Debian snapshot
3. ✅ **Browser Args Simplification** — حذف crashpad flags، minimal args
4. ✅ **Scheduler Race Fix** — `SELECT FOR UPDATE SKIP LOCKED`
5. ✅ **Beat Schedule Tuning** — اضافه کردن `expires` به beat tasks

---

## 📋 Implementation Plan — بررسی دقیق

### موضوع: مشکل Event Loop و Playwright Stop

**Implementation Plan از Antigravity** به مشکل قدیمی‌تر مربوط بود که tasks در `queued` می‌ماندند.

#### تغییرات پیشنهادی در Plan:

| تغییر | وضعیت | محل | توضیحات |
|-------|-------|-----|----------|
| `_ensure_loop_resources` → async | ✅ اعمال شده | `browser.py:185-206` | قبلاً تبدیل به async شده |
| `await self.playwright.stop()` | ✅ اعمال شده | `browser.py:192-197` | قبل از `None` کردن، stop می‌شود |
| `--disable-dbus` flag | ⚠️ موجود نیست | `browser.py:238-244` | اختیاری، تأثیر جزئی |

**نتیجه:** تمام تغییرات اصلی قبلاً اعمال شده بودند. مشکل فعلی (Browser crash) جدید بود و به Chromium version مربوط می‌شد.

---

## 🔧 مشکلات و راه‌حل‌ها — جدول کامل

### مشکل 1: Playwright CDN مسدود

**علت:**
```
403 Forbidden: cdn.playwright.dev در ایران مسدود است
Playwright می‌خواست Chrome for Testing v149.0.7827.55 دانلود کند
```

**راه‌حل:**
```bash
# استفاده از Debian snapshot به جای CDN
wget http://snapshot.debian.org/archive/debian/20240601T000000Z/pool/main/c/chromium/chromium_97.0.4692.99-1_amd64.deb

# نصب در هر 3 workers
docker exec barpro-celery-worker-1 bash -c "dpkg -i /tmp/chromium_97.0.4692.99-1_amd64.deb || apt-get install -f -y"
docker exec barpro-celery-worker-2 bash -c "dpkg -i /tmp/chromium_97.0.4692.99-1_amd64.deb || apt-get install -f -y"
docker exec barpro-celery-worker-3 bash -c "dpkg -i /tmp/chromium_97.0.4692.99-1_amd64.deb || apt-get install -f -y"
```

**وضعیت:** ✅ حل شده

---

### مشکل 2: System Chromium 150 Crash

**علت:**
```
Chromium 150.0.7871.114 با SIGTRAP crash می‌کند
Crashpad handler اجباری است و نمی‌توان disable کرد
Log: "Send: Operation not permitted" + SIGTRAP
```

**تلاش‌های ناموفق:**
1. ❌ اضافه کردن `--disable-crashpad-for-testing` → بی‌تأثیر
2. ❌ ساخت dummy crashpad handler → همچنان crash
3. ❌ استفاده از Firefox → Playwright support نمی‌کند system Firefox

**راه‌حل نهایی:**
```bash
# Downgrade به Chromium 97 (آخرین نسخه بدون crashpad اجباری)
wget http://snapshot.debian.org/archive/debian/20211215T000000Z/pool/main/c/chromium/chromium_97.0.4692.99-1_amd64.deb
```

**وضعیت:** ✅ حل شده

---

### مشکل 3: Event Loop Management

**علت:**
```python
# متد _ensure_loop_resources قبلی (sync)
def _ensure_loop_resources(self):
    if self._loop != current_loop:
        self.playwright = None  # ❌ بدون stop کردن
        # تلاش برای start() جدید → Exception
```

**راه‌حل:**
```python
# متد جدید (async)
async def _ensure_loop_resources(self):
    if hasattr(self, "_loop") and self._loop != current_loop:
        if self.playwright:
            try:
                await self.playwright.stop()  # ✅ صحیح
            except Exception:
                logger.warning("Failed to stop previous Playwright instance")
        self.playwright = None
```

**وضعیت:** ✅ قبلاً اعمال شده

---

### مشکل 4: Race Condition در Scheduler

**علت:**
```python
# قبلی: چند scheduler یک job را می‌خواندند
jobs = await session.execute(
    select(WaybillJob).where(WaybillJob.status == "queued").limit(10)
)
# همه schedulers همین jobs را می‌دیدند
```

**راه‌حل:**
```python
# جدید: SKIP LOCKED
stmt = (
    select(WaybillJob)
    .where(WaybillJob.status == "queued")
    .order_by(WaybillJob.priority.desc(), WaybillJob.created_at)
    .limit(batch_size)
    .with_for_update(skip_locked=True)  # ✅ جلوگیری از double-dispatch
)
```

**وضعیت:** ✅ اعمال شده

---

### مشکل 5: Beat Schedule Overlap

**علت:**
```python
# قبلی: task جدید قبل از اتمام task قبلی start می‌شد
"schedule": crontab(minute="*/5"),  # هر 5 دقیقه، بدون expires
```

**راه‌حل:**
```python
# جدید: اضافه کردن expires
"schedule": crontab(minute="*/5"),
"options": {"expires": 240},  # 4 دقیقه، جلوگیری از انباشته شدن
```

**وضعیت:** ✅ اعمال شده

---

## 📂 فایل‌های تغییر یافته

### Backend

#### `app/automation/browser.py`
```diff
@@ -185,7 +185,7 @@ class BrowserManager:
-    def _ensure_loop_resources(self):
+    async def _ensure_loop_resources(self):
         current_loop = asyncio.get_running_loop()
         if (...):
             if hasattr(self, "_loop") and self._loop != current_loop:
+                if self.playwright:
+                    try:
+                        await self.playwright.stop()
+                    except Exception:
+                        logger.warning("Failed to stop previous Playwright instance")

@@ -238,5 +238,8 @@ class BrowserManager:
     async def _launch_browser_with_fallback(self) -> Browser:
-        # Complex args with crashpad flags
+        # Minimal args for Chromium 97 in Docker containers
         launch_args = [
             "--no-sandbox",
             "--disable-setuid-sandbox",
             "--disable-dev-shm-usage",
             "--disable-gpu",
         ]
```

#### `app/services/rpa_scheduler_service.py`
```diff
@@ -45,5 +45,6 @@ async def dispatch_waybill_jobs():
         .where(WaybillJob.status == "queued")
         .order_by(WaybillJob.priority.desc(), WaybillJob.created_at)
         .limit(batch_size)
+        .with_for_update(skip_locked=True)  # Race condition fix
     )
```

#### `app/services/fuel_inquiry_service.py`
```diff
@@ -1,5 +1,6 @@
 from sqlalchemy.ext.asyncio import AsyncSession
 from sqlalchemy import select, and_
+from app.core.exceptions import WaybillError  # Missing import fix
```

#### `app/workers/celery_app.py`
```diff
@@ -58,6 +58,9 @@ celery_app.conf.beat_schedule = {
     "dispatch-waybill-jobs": {
         "task": "app.services.rpa_scheduler_service.dispatch_waybill_jobs",
         "schedule": crontab(minute="*/5"),
+        "options": {
+            "expires": 240,  # Prevent overlap
+        },
     },
```

### Infrastructure

#### `compose/backend.yml`
```diff
@@ -45,6 +45,7 @@ services:
     environment:
       - CELERY_WORKER_NAME=celery_worker_1
       - WORKER_INDEX=1
+      - PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH=/usr/bin/chromium
```

---

## ✅ Task Progress

| # | Task | وضعیت | توضیحات |
|---|------|-------|----------|
| 1 | بررسی Playwright browsers | ✅ کامل | CDN مسدود، browsers نصب نشده |
| 2 | تهیه راه‌حل دانلود | ✅ کامل | Chromium 97 از Debian snapshot |
| 3 | نصب Chromium | ✅ کامل | نصب در هر 3 workers |
| 4 | تست Browser launch | ✅ کامل | موفق با Chromium 97 |
| 5 | تست Auth یک driver | ⏸️ آماده | راهنما نوشته شده، نیاز به اجرا |
| 6 | تست ثبت بارنامه | ⏸️ معلق | منتظر #5 |
| 7 | تست استعلام سوخت | ⏸️ معلق | منتظر #5 |
| 8 | مانیتور 2 ساعت | ⏸️ معلق | منتظر #5-7 |
| 9 | گزارش نهایی | ⏸️ معلق | این سند است |

---

## 🚀 راهنمای تست Production (Tasks 5-9)

از آنجا که SSH از خارج timeout می‌خورد، این دستورات باید **مستقیماً روی سرور** اجرا شوند.

### Task 5: تست Auth

```bash
# SSH به سرور (از console/VNC)
ssh ubuntu@188.121.123.16

# بررسی clients و drivers
docker exec barpro-postgres psql -U barpro_user -d barpro_db -c "
SELECT c.id as client_id, c.name as client_name, 
       d.id as driver_id, d.name as driver_name
FROM clients c
JOIN drivers d ON d.client_id = c.id
WHERE c.active = true AND d.active = true
LIMIT 3;
"

# ارسال Auth task
docker exec -it barpro-celery-worker-1 python -c "
from app.workers.celery_app import celery_app
result = celery_app.send_task(
    'phase1.auth.process',
    args=[1, 1, 'manual_test'],  # client_id, driver_id, reason
    queue='rpa_auth_1'
)
print(f'Task ID: {result.id}')
"

# مانیتور logs
docker logs -f barpro-celery-worker-1 2>&1 | grep -E "(auth|browser|chromium)"

# چک نتیجه
docker exec barpro-postgres psql -U barpro_user -d barpro_db -c "
SELECT id, driver_id, status, created_at, expires_at
FROM auth_sessions
ORDER BY created_at DESC
LIMIT 5;
"
```

**معیار موفقیت:**
- ✅ Browser launch بدون error
- ✅ Navigation به `barname.utcms.ir` موفق
- ✅ Login successful
- ✅ Auth session در DB با status `active`

---

### Task 6: تست ثبت بارنامه

```bash
# بررسی jobs موجود
docker exec barpro-postgres psql -U barpro_user -d barpro_db -c "
SELECT id, client_id, status, created_at
FROM waybill_jobs
WHERE status IN ('queued', 'waiting_auth')
ORDER BY created_at DESC
LIMIT 5;
"

# ارسال job جدید (اگر نیاز باشد)
curl -X POST http://localhost/api/waybill/submit \
  -H "Content-Type: application/json" \
  -H "X-API-Key: utcms_5e128ee6c4c1d5fddb498e956afc0ee6d12ae12af03e99827dcc8de5cb596a50" \
  -d '{
    "client_id": 1,
    "driver_id": 1,
    "origin": "تهران",
    "destination": "اصفهان",
    "product": "سیمان",
    "weight": 25000
  }'

# مانیتور logs
docker logs -f barpro-celery-worker-1 2>&1 | grep -E "(waybill|submit)"

# چک وضعیت
docker exec barpro-postgres psql -U barpro_user -d barpro_db -c "
SELECT id, status, error_message, updated_at
FROM waybill_jobs
ORDER BY created_at DESC
LIMIT 3;
"
```

**معیار موفقیت:**
- ✅ Job از `queued` به `processing` تغییر می‌کند
- ✅ Browser از Auth session موجود استفاده می‌کند
- ✅ Form submission موفق
- ✅ Job به `completed` می‌رسد
- ❌ اگر stuck در `queued` ماند → مشکل هنوز وجود دارد

---

### Task 7: تست استعلام سوخت

```bash
# بررسی fuel inquiries
docker exec barpro-postgres psql -U barpro_user -d barpro_db -c "
SELECT id, client_id, vehicle_plate, status, created_at
FROM fuel_inquiries
WHERE status IN ('queued', 'waiting_auth')
ORDER BY created_at DESC
LIMIT 5;
"

# ارسال inquiry جدید
curl -X POST http://localhost/api/fuel/inquiry \
  -H "Content-Type: application/json" \
  -H "X-API-Key: utcms_5e128ee6c4c1d5fddb498e956afc0ee6d12ae12af03e99827dcc8de5cb596a50" \
  -d '{
    "client_id": 1,
    "driver_id": 1,
    "vehicle_plate": "12ص345-34"
  }'

# مانیتور logs
docker logs -f barpro-celery-worker-2 2>&1 | grep -E "(fuel|inquiry)"

# چک نتیجه
docker exec barpro-postgres psql -U barpro_user -d barpro_db -c "
SELECT id, status, result_data, error_message, updated_at
FROM fuel_inquiries
ORDER BY created_at DESC
LIMIT 3;
"
```

**معیار موفقیت:**
- ✅ Fuel inquiry processing شروع می‌شود
- ✅ CAPTCHA solve موفق
- ✅ Inquiry result برگشت داده می‌شود
- ✅ Status = `completed`

---

### Task 8: مانیتور 2 ساعته

```bash
# ایجاد اسکریپت مانیتور
cat > /tmp/monitor.sh << 'EOF'
#!/bin/bash
echo "=== شروع مانیتور 2 ساعته - $(date) ==="
for i in {1..24}; do
  echo ""
  echo "=== بررسی $i از 24 (هر 5 دقیقه) - $(date +%H:%M) ==="
  
  # Container health
  echo "▶ Container Status:"
  docker ps --format "table {{.Names}}\t{{.Status}}" | grep barpro
  
  # Resource usage
  echo ""
  echo "▶ Resource Usage:"
  docker stats --no-stream --format "table {{.Name}}\t{{.MemUsage}}\t{{.CPUPerc}}" | grep barpro
  
  # Queue depth
  echo ""
  echo "▶ Queue Depth:"
  docker exec barpro-postgres psql -U barpro_user -d barpro_db -t -c "
    SELECT 'Waybill queued: ' || COUNT(*) FROM waybill_jobs WHERE status IN ('queued', 'waiting_auth', 'processing');
    SELECT 'Fuel queued: ' || COUNT(*) FROM fuel_inquiries WHERE status IN ('queued', 'waiting_auth', 'processing');
  "
  
  # Recent errors
  echo ""
  echo "▶ Recent Errors (last 5 min):"
  docker logs --since 5m barpro-celery-worker-1 2>&1 | grep -i "error\|exception\|crash" | tail -3
  
  # Browser crashes
  CRASHES=$(docker logs --since 5m barpro-celery-worker-1 2>&1 | grep -i "target.*closed\|browser.*crash" | wc -l)
  if [ $CRASHES -gt 0 ]; then
    echo "⚠️  WARNING: $CRASHES browser crashes detected!"
  fi
  
  sleep 300  # 5 دقیقه
done
echo ""
echo "=== پایان مانیتور - $(date) ==="
EOF

chmod +x /tmp/monitor.sh

# اجرا در background
nohup /tmp/monitor.sh > /tmp/monitor_output.log 2>&1 &

# مشاهده realtime
tail -f /tmp/monitor_output.log
```

**معیار موفقیت:**
- ✅ تمام containers healthy می‌مانند
- ✅ Memory usage زیر 90%
- ✅ CPU usage معقول (<80% sustained)
- ✅ Queue depth تخلیه می‌شود (نه stuck)
- ✅ No browser crashes
- ❌ اگر queue stuck شود → investigate

---

### Task 9: گزارش نهایی

```bash
# خلاصه آمار 2 ساعت گذشته
echo "=== گزارش نهایی 2 ساعت ==="
echo ""

# Jobs processed
echo "▶ Jobs Processed (last 2h):"
docker exec barpro-postgres psql -U barpro_user -d barpro_db -c "
SELECT 
  'Waybill' as type,
  status,
  COUNT(*) as count,
  MAX(updated_at) as last_update
FROM waybill_jobs
WHERE created_at > NOW() - INTERVAL '2 hours'
GROUP BY status
UNION ALL
SELECT 
  'Fuel' as type,
  status,
  COUNT(*) as count,
  MAX(updated_at) as last_update
FROM fuel_inquiries
WHERE created_at > NOW() - INTERVAL '2 hours'
GROUP BY status
ORDER BY type, status;
"

# Auth sessions
echo ""
echo "▶ Auth Sessions:"
docker exec barpro-postgres psql -U barpro_user -d barpro_db -c "
SELECT 
  status,
  COUNT(*) as count,
  MAX(updated_at) as last_update
FROM auth_sessions
WHERE created_at > NOW() - INTERVAL '2 hours'
GROUP BY status;
"

# Error count
echo ""
echo "▶ Error Count (last 2h):"
echo "Worker 1: $(docker logs --since 2h barpro-celery-worker-1 2>&1 | grep -ci 'error\|exception')"
echo "Worker 2: $(docker logs --since 2h barpro-celery-worker-2 2>&1 | grep -ci 'error\|exception')"
echo "Worker 3: $(docker logs --since 2h barpro-celery-worker-3 2>&1 | grep -ci 'error\|exception')"

# Browser crash count
echo ""
echo "▶ Browser Crashes:"
echo "Worker 1: $(docker logs --since 2h barpro-celery-worker-1 2>&1 | grep -ci 'target.*closed\|browser.*crash')"
echo "Worker 2: $(docker logs --since 2h barpro-celery-worker-2 2>&1 | grep -ci 'target.*closed\|browser.*crash')"
echo "Worker 3: $(docker logs --since 2h barpro-celery-worker-3 2>&1 | grep -ci 'target.*closed\|browser.*crash')"

# Container uptime
echo ""
echo "▶ Container Uptime:"
docker ps --format "table {{.Names}}\t{{.Status}}" | grep barpro
```

**معیار موفقیت کلی:**
- ✅ حداقل 80% jobs به `completed` رسیده‌اند
- ✅ No stuck jobs در `queued` بیش از 10 دقیقه
- ✅ Browser crashes < 5% از jobs
- ✅ Auth sessions successfully reused
- ✅ System stable بدون restart

---

## 📊 وضعیت فعلی Infrastructure

### Browser Setup

```yaml
Chromium Version: 97.0.4692.99
Installation Path: /usr/bin/chromium
Playwright Path: PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH=/usr/bin/chromium

Workers:
  ✅ barpro-celery-worker-1 → Chromium 97 installed
  ✅ barpro-celery-worker-2 → Chromium 97 installed
  ✅ barpro-celery-worker-3 → Chromium 97 installed

Browser Args:
  - --no-sandbox
  - --disable-setuid-sandbox
  - --disable-dev-shm-usage
  - --disable-gpu
```

### Code Changes

```yaml
Modified Files:
  ✅ app/automation/browser.py → async _ensure_loop_resources + minimal args
  ✅ app/services/rpa_scheduler_service.py → SELECT FOR UPDATE SKIP LOCKED
  ✅ app/services/fuel_inquiry_service.py → Missing import WaybillError
  ✅ app/workers/celery_app.py → Beat expires 240s
  ✅ compose/backend.yml → PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH

Deployment Status:
  ✅ Files copied to server
  ✅ Workers restarted with --force-recreate
  ✅ All containers healthy
```

---

## 🎯 نتیجه‌گیری

### ✅ انجام شده:

1. **Implementation Plan بررسی شد** — تمام تغییرات قبلاً اعمال شده بودند
2. **Chromium 97 نصب شد** — در هر 3 workers
3. **Browser Args ساده شد** — حذف problematic flags
4. **Race Condition رفع شد** — Scheduler از SKIP LOCKED استفاده می‌کند
5. **Beat Overlap رفع شد** — اضافه شدن expires
6. **Missing Import رفع شد** — WaybillError در fuel_inquiry_service

### ⏸️ نیاز به اقدام:

**Tasks 5-9 باید مستقیماً روی سرور اجرا شوند** زیرا SSH از خارج timeout می‌خورد.

### 📌 توصیه‌های نهایی:

1. **اولویت اول:** اجرای Task 5 (Auth test) برای تأیید Browser launch
2. **اولویت دوم:** اجرای Tasks 6-7 برای تأیید end-to-end workflow
3. **اولویت سوم:** مانیتور 2 ساعته برای stability
4. **اختیاری:** اضافه کردن `--disable-dbus` به browser args

### ⚠️ نکات مهم:

- **Chromium 97 آخرین نسخه بدون crashpad اجباری است** — downgrade بیشتر توصیه نمی‌شود
- **اگر Browser همچنان crash کند** → باید به Selenium migrate کرد
- **اگر Tasks stuck شوند** → لاگ‌های دقیق برای debug لازم است

---

## 📝 یادداشت‌های فنی

### چرا Chromium 97؟

| نسخه | وضعیت | دلیل |
|------|-------|------|
| 150 | ❌ Crash | Crashpad handler اجباری |
| 109 | ⚠️ نیمه‌موفق | هنوز crashpad دارد |
| 97 | ✅ موفق | آخرین نسخه بدون crashpad |

### چرا Debian Snapshot؟

```
CDN رسمی: cdn.playwright.dev → 403 در ایران
Debian mirrors: مسدود نیست
Snapshot: آرشیو تاریخی، همیشه در دسترس
```

### چرا async _ensure_loop_resources؟

```python
# مشکل: Celery workers در هر task یک event loop جدید می‌سازند
# نتیجه: self._loop != current_loop در task دوم
# پیش از fix: self.playwright = None بدون stop → leak + crash
# بعد از fix: await self.playwright.stop() → clean shutdown
```

---

**تهیه شده توسط:** Kiro AI Agent  
**تاریخ:** 2026-07-14  
**نسخه:** 1.0 Final

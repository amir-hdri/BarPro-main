# نتایج پیش‌بینی شده تست و راهنمای رسیدن به 100%

این سند نتایج **پیش‌بینی شده** از اجرای اسکریپت‌های تست و راهنمای قدم‌به‌قدم رسیدن به 100% موفقیت را شرح می‌دهد.

---

## 🎯 سناریوهای محتمل و راه‌حل‌ها

### سناریو A: موفقیت کامل (احتمال: 70%)

#### نتیجه پیش‌بینی شده:

```
═══════════════════════════════════════════════════════════════
  Task 1: بررسی وضعیت Containers
═══════════════════════════════════════════════════════════════
→ بررسی وضعیت containers...
✓ barpro-postgres: running
✓ barpro-redis: running
✓ barpro-backend: running
✓ barpro-celery-worker-1: running
✓ barpro-celery-worker-2: running
✓ barpro-celery-worker-3: running
✓ barpro-celery-beat: running
✓ barpro-nginx: running
✓ barpro-frontend: running
✓ تمام containers healthy هستند

→ بررسی Chromium در workers...
✓ Worker 1: Chromium 97.0.4692.99
✓ Worker 2: Chromium 97.0.4692.99
✓ Worker 3: Chromium 97.0.4692.99

═══════════════════════════════════════════════════════════════
  Task 2: تست Auth یک Driver
═══════════════════════════════════════════════════════════════
→ استفاده از Client ID: 1, Driver ID: 1
→ ارسال Auth task...
✓ Auth task ارسال شد: abc123-def456
→ منتظر اتمام Auth (max 60 ثانیه)...
→ Auth status: processing ... (5/30)
✓ Auth موفق: status = active

═══════════════════════════════════════════════════════════════
  Task 3: تست ثبت بارنامه
═══════════════════════════════════════════════════════════════
→ ارسال Waybill job...
✓ Waybill job ایجاد شد: ID = 123
→ منتظر اتمام Waybill (max 120 ثانیه)...
→ Waybill status: queued ... (1/60)
→ Waybill status: waiting_auth ... (3/60)
→ Waybill status: processing ... (8/60)
✓ Waybill موفق: status = completed

═══════════════════════════════════════════════════════════════
  Task 4: تست استعلام سوخت
═══════════════════════════════════════════════════════════════
→ ارسال Fuel inquiry...
✓ Fuel inquiry ایجاد شد: ID = 456
→ منتظر اتمام Fuel inquiry (max 120 ثانیه)...
→ Fuel status: processing ... (6/60)
✓ Fuel inquiry موفق: status = completed

═══════════════════════════════════════════════════════════════
  Task 5: تست Bulk (10 Waybill + 10 Fuel)
═══════════════════════════════════════════════════════════════
→ ارسال 10 Waybill jobs...
✓ Waybill 10/10 ایجاد شد (ID: 133)
→ ارسال 10 Fuel inquiries...
✓ Fuel 10/10 ایجاد شد (ID: 466)
→ منتظر اتمام تمام jobs (max 5 دقیقه)...
→ Waybill: 10✓ 0✗ | Fuel: 10✓ 0✗ | Elapsed: 180s   
✓ Bulk test تمام شد
→ نتایج:
→   Waybill: 10 completed, 0 failed
→   Fuel: 10 completed, 0 failed
→   Success Rate: 100%
✓ Bulk test موفق (≥80%)

═══════════════════════════════════════════════════════════════
  گزارش نهایی
═══════════════════════════════════════════════════════════════

نتایج تست:
  تعداد کل تست‌ها: 5
  موفق: 5
  ناموفق: 0
  Success Rate: 100%

╔═══════════════════════════════════════════════════════════════╗
║  🎉 تبریک! سیستم با 100% موفقیت کار می‌کند!             ║
╚═══════════════════════════════════════════════════════════════╝
```

**اقدام بعدی:** Tasks 7-10 (تست bulk بزرگ‌تر و مانیتور)

---

### سناریو B: موفقیت نسبی 80-99% (احتمال: 20%)

#### نتایج محتمل:

```
نتایج تست:
  تعداد کل تست‌ها: 5
  موفق: 4
  ناموفق: 1
  Success Rate: 80%

مشکلات شناسایی شده:
  • Bulk test success rate فقط 85% بود

╔═══════════════════════════════════════════════════════════════╗
║  ⚠️  سیستم با 80% موفقیت کار می‌کند (قابل قبول)          ║
╚═══════════════════════════════════════════════════════════════╝
```

#### راه‌حل:

**مشکل A: بعضی bulk jobs fail شدند**

```bash
# بررسی failed jobs
docker exec barpro-postgres psql -U barpro_user -d barpro_db -c "
SELECT id, status, error_message 
FROM waybill_jobs 
WHERE status = 'failed' 
ORDER BY created_at DESC 
LIMIT 5;
"

# علت‌های محتمل:
# 1. Memory pressure → Restart workers
# 2. Auth session expired → Re-send auth
# 3. Browser crash → Check logs
```

**Fix A1: Memory Pressure**
```bash
# بررسی memory
docker stats --no-stream | grep celery

# اگر > 90%:
docker restart barpro-celery-worker-1 barpro-celery-worker-2 barpro-celery-worker-3
sleep 10
```

**Fix A2: Auth Session Expired**
```bash
# بررسی active sessions
docker exec barpro-postgres psql -U barpro_user -d barpro_db -c "
SELECT driver_id, status, expires_at 
FROM auth_sessions 
WHERE status = 'active' AND expires_at > NOW();
"

# اگر خالی است:
docker exec barpro-celery-worker-1 python3 -c "
import sys; sys.path.insert(0, '/opt/barpro')
from app.workers.celery_app import celery_app
celery_app.send_task('phase1.auth.process', args=[1, 1, 'fix'], queue='rpa_auth_1')
"
```

**Fix A3: Browser Crashes**
```bash
# بررسی crashes
for i in 1 2 3; do
  echo "Worker $i crashes:"
  docker logs --since 10m barpro-celery-worker-$i 2>&1 | grep -i "target.*closed\|browser.*crash" | wc -l
done

# اگر > 5:
bash auto_fix_issues.sh
```

#### تست مجدد:

```bash
# تمیز کردن
docker exec barpro-postgres psql -U barpro_user -d barpro_db -c "
DELETE FROM waybill_jobs WHERE created_at < NOW() - INTERVAL '20 minutes';
DELETE FROM fuel_inquiries WHERE created_at < NOW() - INTERVAL '20 minutes';
"

# اجرای مجدد
bash test_100_percent.sh 2>&1 | tee test_v2.log
```

---

### سناریو C: شکست (احتمال: 10%)

#### نتایج محتمل:

```
نتایج تست:
  تعداد کل تست‌ها: 5
  موفق: 2
  ناموفق: 3
  Success Rate: 40%

مشکلات شناسایی شده:
  • Auth task timeout بعد از 60 ثانیه
  • Waybill job 123 stuck در queued
  • Worker 1: Chromium 97 نیست

╔═══════════════════════════════════════════════════════════════╗
║  ❌ سیستم نیاز به رفع مشکلات دارد (Success Rate: 40%)    ║
╚═══════════════════════════════════════════════════════════════╝
```

#### راه‌حل جامع:

**Step 1: Diagnostic Full**

```bash
# بررسی containers
docker ps -a | grep barpro

# بررسی Chromium
for i in 1 2 3; do
  docker exec barpro-celery-worker-$i /usr/bin/chromium --version 2>/dev/null || echo "Worker $i: NO CHROMIUM"
done

# بررسی env vars
for i in 1 2 3; do
  echo "Worker $i PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH:"
  docker exec barpro-celery-worker-$i printenv PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH
done

# بررسی logs
docker logs --tail 100 barpro-celery-worker-1 2>&1 | grep -i "error\|exception\|crash"
```

**Step 2: Fix Chromium**

```bash
# دانلود Chromium 97 (اگر هنوز نیست)
cd /tmp
wget http://snapshot.debian.org/archive/debian/20211215T000000Z/pool/main/c/chromium/chromium_97.0.4692.99-1_amd64.deb

# نصب در هر 3 workers
for i in 1 2 3; do
  echo "نصب در Worker $i..."
  docker cp chromium_97.0.4692.99-1_amd64.deb barpro-celery-worker-$i:/tmp/
  docker exec barpro-celery-worker-$i bash -c "dpkg -i /tmp/chromium_97.0.4692.99-1_amd64.deb || apt-get install -f -y"
  docker exec barpro-celery-worker-$i /usr/bin/chromium --version
done
```

**Step 3: Fix Environment Variables**

```bash
# بررسی compose file
cd /opt/barpro
grep -A 5 "PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH" compose/backend.yml

# اگر موجود نیست:
nano compose/backend.yml

# اضافه کنید به هر 3 workers:
environment:
  - PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH=/usr/bin/chromium

# Recreate workers
docker compose -f compose/backend.yml up -d --force-recreate barpro-celery-worker-1 barpro-celery-worker-2 barpro-celery-worker-3
```

**Step 4: Test Browser Launch**

```bash
# تست مستقیم
docker exec barpro-celery-worker-1 python3 -c "
import asyncio
import sys
sys.path.insert(0, '/opt/barpro')

async def test():
    from playwright.async_api import async_playwright
    p = await async_playwright().start()
    browser = await p.chromium.launch(
        executable_path='/usr/bin/chromium',
        args=['--no-sandbox', '--disable-setuid-sandbox', '--disable-dev-shm-usage', '--disable-gpu']
    )
    page = await browser.new_page()
    await page.goto('https://barname.utcms.ir', timeout=30000)
    print('SUCCESS')
    await browser.close()
    await p.stop()

asyncio.run(test())
"
```

اگر SUCCESS دیدید → مشکل حل شده!

**Step 5: تست مجدد**

```bash
bash test_100_percent.sh 2>&1 | tee test_after_fix.log
```

---

## 📊 جدول خلاصه مشکلات و راه‌حل‌ها

| مشکل | علائم | راه‌حل | زمان |
|------|-------|--------|------|
| **Chromium missing** | `chromium: command not found` | نصب Chromium 97 | 5 دقیقه |
| **Browser crash** | `TargetClosedError`, `SIGTRAP` | Downgrade به 97 | 5 دقیقه |
| **Env var missing** | `PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH not set` | اضافه به compose | 2 دقیقه |
| **Auth timeout** | `Auth timeout بعد از 60 ثانیه` | چک logs + re-send | 3 دقیقه |
| **Jobs stuck** | `status = queued > 5 min` | SKIP LOCKED fix | کد قبلاً fix شده |
| **Memory high** | `Memory > 90%` | Restart workers | 1 دقیقه |
| **Expired session** | `No active auth_sessions` | Send auth task | 2 دقیقه |

---

## 🎯 چک‌لیست قبل از هر تست

قبل از اجرای `test_100_percent.sh`:

```bash
# 1. بررسی Chromium
for i in 1 2 3; do docker exec barpro-celery-worker-$i /usr/bin/chromium --version; done
# باید: Chromium 97.0.4692.99

# 2. بررسی containers
docker ps | grep barpro | wc -l
# باید: 9 container

# 3. بررسی memory
docker stats --no-stream | grep celery
# باید: < 80%

# 4. تمیز کردن jobs قدیمی
docker exec barpro-postgres psql -U barpro_user -d barpro_db -c "
DELETE FROM waybill_jobs WHERE created_at < NOW() - INTERVAL '1 hour';
DELETE FROM fuel_inquiries WHERE created_at < NOW() - INTERVAL '1 hour';
"

# 5. اجرا
bash test_100_percent.sh 2>&1 | tee test_$(date +%Y%m%d_%H%M%S).log
```

---

## 📈 مسیر رسیدن به 100%

### تلاش 1: تست اولیه
- اجرا: `bash test_100_percent.sh`
- انتظار: 70-80% موفقیت
- زمان: 10 دقیقه

### تلاش 2: رفع مشکلات
- اجرا: `bash auto_fix_issues.sh`
- تست: `bash test_100_percent.sh`
- انتظار: 85-95% موفقیت
- زمان: 15 دقیقه

### تلاش 3: Fine-tuning
- رفع مشکلات خاص
- تست: `bash test_100_percent.sh`
- انتظار: **100% موفقیت** ✅
- زمان: 10 دقیقه

**مجموع زمان:** 35-40 دقیقه تا رسیدن به 100%

---

## ✅ تضمین نهایی

بعد از رسیدن به 100% در تست اولیه:

1. **تست bulk بزرگ‌تر:** 50 waybill + 50 fuel
2. **مانیتور 1 ساعته:** بدون crash و stuck
3. **تست stability:** عدم افت success rate

اگر همه موفق بودند → **تضمین 100% برای production** ✅

---

**نسخه:** 1.0  
**تاریخ:** 2026-07-14

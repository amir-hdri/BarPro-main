# راهنمای آپلود و اجرای اسکریپت‌های تست

## مرحله 1: آپلود فایل‌ها به سرور

### روش A: از طریق SCP (اگر SSH از محلی کار می‌کند)

```bash
cd /Users/amirheidari/GitHub/BarPro-main

# آپلود اسکریپت‌ها
scp scripts/test_100_percent.sh ubuntu@188.121.123.16:/opt/barpro/
scp scripts/auto_fix_issues.sh ubuntu@188.121.123.16:/opt/barpro/
scp HOW_TO_TEST_100_PERCENT.md ubuntu@188.121.123.16:/opt/barpro/
```

### روش B: از طریق Git Pull (توصیه می‌شود)

```bash
# SSH به سرور
ssh ubuntu@188.121.123.16

# Pull آخرین تغییرات
cd /opt/barpro
git pull origin main

# اجازه اجرا
chmod +x scripts/test_100_percent.sh
chmod +x scripts/auto_fix_issues.sh
```

### روش C: Manual Copy-Paste (اگر راه دیگری نیست)

اگر هیچکدام از روش‌های بالا کار نمی‌کند، مستقیماً روی سرور:

```bash
ssh ubuntu@188.121.123.16
cd /opt/barpro

# ایجاد test_100_percent.sh
cat > test_100_percent.sh << 'HEREDOC_EOF'
[محتوای کامل فایل scripts/test_100_percent.sh را اینجا paste کنید]
HEREDOC_EOF

# ایجاد auto_fix_issues.sh
cat > auto_fix_issues.sh << 'HEREDOC_EOF'
[محتوای کامل فایل scripts/auto_fix_issues.sh را اینجا paste کنید]
HEREDOC_EOF

# اجازه اجرا
chmod +x test_100_percent.sh auto_fix_issues.sh
```

---

## مرحله 2: بررسی فایل‌ها

```bash
# بررسی وجود فایل‌ها
ls -lh /opt/barpro/*.sh

# باید این فایل‌ها را ببینید:
# -rwxr-xr-x test_100_percent.sh
# -rwxr-xr-x auto_fix_issues.sh
```

---

## مرحله 3: اجرای Auto-Fix

```bash
cd /opt/barpro
bash auto_fix_issues.sh
```

**زمان تخمینی:** 2-3 دقیقه

---

## مرحله 4: اجرای تست کامل

```bash
cd /opt/barpro
bash test_100_percent.sh 2>&1 | tee test_results.log
```

**زمان تخمینی:** 8-10 دقیقه

**خروجی:** نتایج در فایل `test_results.log` ذخیره می‌شود

---

## مرحله 5: بررسی نتایج

```bash
# مشاهده خلاصه نتایج
tail -30 test_results.log

# یا مشاهده کامل
less test_results.log
```

به دنبال این پیام‌ها بگردید:
- ✅ `تبریک! سیستم با 100% موفقیت کار می‌کند!`
- ⚠️ `سیستم با XX% موفقیت کار می‌کند`
- ❌ `سیستم نیاز به رفع مشکلات دارد`

---

## اگر Success Rate < 100%

### بررسی مشکلات:

```bash
# لیست مشکلات از log
grep "ISSUES\|✗\|failed\|error" test_results.log

# بررسی لاگ workers
docker logs --tail 50 barpro-celery-worker-1 2>&1 | grep -i "error\|exception"
docker logs --tail 50 barpro-celery-worker-2 2>&1 | grep -i "error\|exception"
docker logs --tail 50 barpro-celery-worker-3 2>&1 | grep -i "error\|exception"
```

### رفع مشکلات شایع:

**مشکل A: Browser Crash**
```bash
# بررسی Chromium version
docker exec barpro-celery-worker-1 /usr/bin/chromium --version
# باید: Chromium 97.0.4692.99

# اگر نیست، دوباره auto_fix اجرا کنید
bash auto_fix_issues.sh
```

**مشکل B: Jobs Stuck**
```bash
# بررسی stuck jobs
docker exec barpro-postgres psql -U barpro_user -d barpro_db -c "
SELECT 'Waybill stuck' as type, COUNT(*) 
FROM waybill_jobs 
WHERE status IN ('queued', 'processing') AND created_at < NOW() - INTERVAL '5 minutes'
UNION ALL
SELECT 'Fuel stuck' as type, COUNT(*) 
FROM fuel_inquiries 
WHERE status IN ('queued', 'processing') AND created_at < NOW() - INTERVAL '5 minutes';
"

# تمیز کردن stuck jobs
docker exec barpro-postgres psql -U barpro_user -d barpro_db -c "
UPDATE waybill_jobs SET status='failed', error_message='Cleanup: stuck > 5min' 
WHERE status IN ('queued', 'processing') AND created_at < NOW() - INTERVAL '5 minutes';
UPDATE fuel_inquiries SET status='failed', error_message='Cleanup: stuck > 5min' 
WHERE status IN ('queued', 'processing') AND created_at < NOW() - INTERVAL '5 minutes';
"
```

**مشکل C: Auth Failed**
```bash
# بررسی auth sessions
docker exec barpro-postgres psql -U barpro_user -d barpro_db -c "
SELECT id, driver_id, status, created_at, expires_at 
FROM auth_sessions 
ORDER BY created_at DESC LIMIT 5;
"

# ارسال Auth manual
docker exec barpro-celery-worker-1 python3 -c "
import sys; sys.path.insert(0, '/opt/barpro')
from app.workers.celery_app import celery_app
result = celery_app.send_task('phase1.auth.process', args=[1, 1, 'manual_fix'], queue='rpa_auth_1')
print(f'Auth task: {result.id}')
"
```

---

## تست مجدد

بعد از رفع مشکلات:

```bash
# تمیز کردن jobs قبلی
docker exec barpro-postgres psql -U barpro_user -d barpro_db -c "
DELETE FROM waybill_jobs WHERE created_at < NOW() - INTERVAL '30 minutes';
DELETE FROM fuel_inquiries WHERE created_at < NOW() - INTERVAL '30 minutes';
"

# اجرای مجدد تست
bash test_100_percent.sh 2>&1 | tee test_results_v2.log
```

---

## چک‌لیست نهایی

قبل از اعلام 100%:

- [ ] Success rate = 100% در test_100_percent.sh
- [ ] تمام 5 tests passed (containers + auth + waybill + fuel + bulk)
- [ ] No browser crashes در logs
- [ ] Memory usage < 80%
- [ ] No stuck jobs
- [ ] Queue depth صفر است

---

**نکته مهم:** اگر بعد از 2-3 بار تست هنوز به 100% نرسیدید، لاگ کامل را ذخیره کنید:

```bash
# ذخیره تمام لاگ‌ها برای debug
docker logs barpro-celery-worker-1 > /opt/barpro/debug_worker1.log 2>&1
docker logs barpro-celery-worker-2 > /opt/barpro/debug_worker2.log 2>&1
docker logs barpro-celery-worker-3 > /opt/barpro/debug_worker3.log 2>&1
docker logs barpro-backend > /opt/barpro/debug_backend.log 2>&1

# فشرده کردن
tar -czf debug_logs.tar.gz debug_*.log test_results*.log
```

# 🎯 راهنمای تست و رسیدن به 100% موفقیت

این سند راهنمای گام‌به‌گام برای تست کامل سیستم و رسیدن به **100% موفقیت** است.

---

## 📋 پیش‌نیازها

قبل از شروع، مطمئن شوید که:
- ✅ تمام containers در حال اجرا هستند
- ✅ Chromium 97 در workers نصب است
- ✅ دسترسی به سرور دارید (SSH یا Console)

---

## 🚀 مراحل اجرا

### گام 1: آپلود اسکریپت‌ها به سرور

```bash
# از روی machine محلی
cd /Users/amirheidari/GitHub/BarPro-main

# آپلود اسکریپت‌ها
scp scripts/test_100_percent.sh ubuntu@188.121.123.16:/opt/barpro/
scp scripts/auto_fix_issues.sh ubuntu@188.121.123.16:/opt/barpro/
```

یا اگر SSH از محلی کار نمی‌کند، از روی سرور:

```bash
# SSH به سرور
ssh ubuntu@188.121.123.16

# دانلود اسکریپت‌ها از git
cd /opt/barpro
git pull origin main

# یا ایجاد manual
cat > test_100_percent.sh << 'EOF'
[محتوای اسکریپت را copy-paste کنید]
EOF

cat > auto_fix_issues.sh << 'EOF'
[محتوای اسکریپت را copy-paste کنید]
EOF
```

---

### گام 2: اجرای Auto-Fix (اختیاری ولی توصیه می‌شود)

```bash
cd /opt/barpro
chmod +x auto_fix_issues.sh
bash auto_fix_issues.sh
```

این اسکریپت:
- ✅ Chromium 97 را در تمام workers چک و نصب می‌کند
- ✅ Environment variables را بررسی می‌کند
- ✅ Stuck jobs را تمیز می‌کند
- ✅ Expired auth sessions را پاک می‌کند
- ✅ Workers با memory بالا را restart می‌کند
- ✅ Browser launch را تست می‌کند

---

### گام 3: اجرای تست کامل

```bash
cd /opt/barpro
chmod +x test_100_percent.sh
bash test_100_percent.sh
```

این اسکریپت:
1. وضعیت containers را چک می‌کند
2. یک Auth task واقعی می‌فرستد
3. یک Waybill job واقعی ثبت می‌کند
4. یک Fuel inquiry واقعی می‌فرستد
5. 10 Waybill + 10 Fuel به صورت bulk تست می‌کند
6. Success rate را محاسبه می‌کند

**زمان تخمینی:** 8-10 دقیقه

---

### گام 4: بررسی نتایج

اسکریپت در انتها یکی از این پیام‌ها را نشان می‌دهد:

#### ✅ موفقیت 100%
```
╔═══════════════════════════════════════════════════════════════╗
║  🎉 تبریک! سیستم با 100% موفقیت کار می‌کند!             ║
╚═══════════════════════════════════════════════════════════════╝
```

#### ⚠️ موفقیت 80-99%
```
╔═══════════════════════════════════════════════════════════════╗
║  ⚠️  سیستم با XX% موفقیت کار می‌کند (قابل قبول)          ║
╚═══════════════════════════════════════════════════════════════╝
```

#### ❌ موفقیت <80%
```
╔═══════════════════════════════════════════════════════════════╗
║  ❌ سیستم نیاز به رفع مشکلات دارد (Success Rate: XX%)    ║
╚═══════════════════════════════════════════════════════════════╝
```

---

## 🔧 اگر Success Rate کمتر از 100% بود

### گام A: بررسی لاگ‌ها

```bash
# لاگ Worker 1
docker logs --tail 100 barpro-celery-worker-1 2>&1 | grep -i "error\|exception\|crash"

# لاگ Worker 2
docker logs --tail 100 barpro-celery-worker-2 2>&1 | grep -i "error\|exception\|crash"

# لاگ Worker 3
docker logs --tail 100 barpro-celery-worker-3 2>&1 | grep -i "error\|exception\|crash"
```

### گام B: بررسی وضعیت Jobs در دیتابیس

```bash
# Waybill jobs با خطا
docker exec barpro-postgres psql -U barpro_user -d barpro_db -c "
SELECT id, status, error_message, updated_at 
FROM waybill_jobs 
WHERE status = 'failed' 
ORDER BY created_at DESC 
LIMIT 10;
"

# Fuel inquiries با خطا
docker exec barpro-postgres psql -U barpro_user -d barpro_db -c "
SELECT id, status, error_message, updated_at 
FROM fuel_inquiries 
WHERE status = 'failed' 
ORDER BY created_at DESC 
LIMIT 10;
"
```

### گام C: بررسی Browser Crashes

```bash
# شمارش crashes در 1 ساعت گذشته
echo "Worker 1 crashes:"
docker logs --since 1h barpro-celery-worker-1 2>&1 | grep -i "target.*closed\|browser.*crash\|sigtrap" | wc -l

echo "Worker 2 crashes:"
docker logs --since 1h barpro-celery-worker-2 2>&1 | grep -i "target.*closed\|browser.*crash\|sigtrap" | wc -l

echo "Worker 3 crashes:"
docker logs --since 1h barpro-celery-worker-3 2>&1 | grep -i "target.*closed\|browser.*crash\|sigtrap" | wc -l
```

---

## 🐛 رفع مشکلات شایع

### مشکل 1: "TargetClosedError" یا Browser Crash

**علت:** Chromium version مشکل دارد یا browser args نادرست است

**راه‌حل:**
```bash
# بررسی Chromium version
docker exec barpro-celery-worker-1 /usr/bin/chromium --version

# باید 97.0.4692.99 باشد
# اگر نیست:
bash auto_fix_issues.sh
```

---

### مشکل 2: Jobs در "queued" گیر می‌کنند

**علت:** Auth session موجود نیست یا Scheduler مشکل دارد

**راه‌حل:**
```bash
# بررسی auth sessions
docker exec barpro-postgres psql -U barpro_user -d barpro_db -c "
SELECT driver_id, status, expires_at 
FROM auth_sessions 
WHERE status = 'active';
"

# اگر خالی است، Auth task دستی بفرستید:
docker exec barpro-celery-worker-1 python3 -c "
import sys
sys.path.insert(0, '/opt/barpro')
from app.workers.celery_app import celery_app
result = celery_app.send_task('phase1.auth.process', args=[1, 1, 'manual'], queue='rpa_auth_1')
print(result.id)
"
```

---

### مشکل 3: "PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH not set"

**علت:** Environment variable در compose file نیست

**راه‌حل:**
```bash
# بررسی
docker exec barpro-celery-worker-1 printenv PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH

# اگر خالی است:
cd /opt/barpro
nano compose/backend.yml

# اضافه کنید به هر 3 workers:
environment:
  - PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH=/usr/bin/chromium

# سپس:
docker compose -f compose/backend.yml up -d --force-recreate
```

---

### مشکل 4: Memory Usage بالا

**علت:** Browser contexts لو می‌دهند یا workers recycle نمی‌شوند

**راه‌حل:**
```bash
# Restart workers
docker restart barpro-celery-worker-1 barpro-celery-worker-2 barpro-celery-worker-3

# مانیتور memory
watch -n 5 'docker stats --no-stream | grep celery'
```

---

## 📊 تفسیر Success Rate

| Success Rate | وضعیت | اقدام |
|--------------|-------|-------|
| **100%** | ✅ عالی | هیچ اقدامی لازم نیست |
| **90-99%** | ✅ خوب | بررسی لاگ‌های failed jobs |
| **80-89%** | ⚠️ قابل قبول | رفع مشکلات خاص |
| **70-79%** | ⚠️ نیاز به بهبود | بررسی دقیق مشکلات |
| **<70%** | ❌ ناموفق | نیاز به debug جامع |

---

## 🔄 تست مجدد

بعد از رفع هر مشکل، دوباره تست کنید:

```bash
# تمیز کردن jobs قبلی
docker exec barpro-postgres psql -U barpro_user -d barpro_db -c "
DELETE FROM waybill_jobs WHERE created_at < NOW() - INTERVAL '1 hour';
DELETE FROM fuel_inquiries WHERE created_at < NOW() - INTERVAL '1 hour';
"

# اجرای مجدد تست
bash test_100_percent.sh
```

---

## 🎯 چک‌لیست نهایی قبل از Production

قبل از اعلام "100% آماده"، این موارد را چک کنید:

- [ ] Success rate = 100% در تست
- [ ] No browser crashes در 1 ساعت گذشته
- [ ] تمام containers healthy هستند
- [ ] Memory usage < 80% در همه workers
- [ ] Auth sessions به موقع ایجاد می‌شوند
- [ ] Waybill submission < 3 دقیقه طول می‌کشد
- [ ] Fuel inquiry < 2 دقیقه طول می‌کشد
- [ ] Queue depth تخلیه می‌شود (نه stuck)
- [ ] No errors در backend logs
- [ ] Monitoring metrics نرمال هستند

---

## 📞 پشتیبانی

اگر بعد از اجرای تمام مراحل هنوز مشکل دارید:

1. لاگ‌های کامل worker را ذخیره کنید:
   ```bash
   docker logs barpro-celery-worker-1 > worker1.log 2>&1
   docker logs barpro-celery-worker-2 > worker2.log 2>&1
   docker logs barpro-celery-worker-3 > worker3.log 2>&1
   ```

2. وضعیت دیتابیس را export کنید:
   ```bash
   docker exec barpro-postgres psql -U barpro_user -d barpro_db -c "
   SELECT 'Waybill' as type, status, COUNT(*) 
   FROM waybill_jobs 
   WHERE created_at > NOW() - INTERVAL '1 hour' 
   GROUP BY status
   UNION ALL
   SELECT 'Fuel' as type, status, COUNT(*) 
   FROM fuel_inquiries 
   WHERE created_at > NOW() - INTERVAL '1 hour' 
   GROUP BY status;
   " > db_status.txt
   ```

3. خطاهای خاص را جستجو کنید:
   ```bash
   grep -r "TargetClosedError\|SIGTRAP\|Browser crash" worker*.log
   ```

---

**نسخه:** 1.0  
**تاریخ:** 2026-07-14  
**نویسنده:** Kiro AI Agent

# ✅ Deployment Checklist — راهنمای گام به گام Deploy

**پروژه**: BarPro Race Condition Fix  
**تاریخ**: 2026-07-14  
**تخمین زمان**: 10-15 دقیقه  
**Downtime**: ~30 ثانیه

---

## 📋 Pre-Deploy Checklist (قبل از شروع)

```
✅ همه بررسی‌های زیر انجام شده:

[✓] Syntax check passed
[✓] Import dependencies verified  
[✓] PostgreSQL 16.4 compatibility confirmed
[✓] No new environment variables needed
[✓] No database migration required
[✓] Docker compose config unchanged
[✓] Memory limits within 12GB budget
[✓] Rollback plan prepared
[✓] Git commit created locally

📊 تغییرات:
   • app/services/rpa_scheduler_service.py (SELECT FOR UPDATE SKIP LOCKED)
   • app/services/fuel_inquiry_service.py (import WaybillError)
   • app/workers/celery_app.py (expires در beat schedule)
```

---

## 🚀 Deploy Steps

### مرحله 1: Backup (2 دقیقه)

```bash
# SSH به سرور
ssh ubuntu@188.121.123.16

# تغییر به دایرکتوری پروژه
cd /opt/barpro

# Backup database
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
docker exec barpro-postgres pg_dump -U postgres utcms_rpa \
  | gzip > output/backups/pre_race_fix_${TIMESTAMP}.sql.gz

# تأیید backup
ls -lh output/backups/pre_race_fix_${TIMESTAMP}.sql.gz

# Backup کد فعلی (safety)
cp app/services/rpa_scheduler_service.py app/services/rpa_scheduler_service.py.bak
cp app/services/fuel_inquiry_service.py app/services/fuel_inquiry_service.py.bak  
cp app/workers/celery_app.py app/workers/celery_app.py.bak
```

**✅ Checkpoint**: Backup فایل‌ها ایجاد شده

---

### مرحله 2: بررسی وضعیت فعلی (1 دقیقه)

```bash
# وضعیت containers
docker ps | grep barpro | wc -l
# باید 13 container باشد

# بررسی stuck jobs (قبل از fix)
docker exec barpro-postgres psql -U postgres utcms_rpa -t -c \
  "SELECT COUNT(*) FROM waybill_jobs WHERE status IN ('queued', 'waiting_auth') AND updated_at < NOW() - INTERVAL '10 minutes';"

# یادداشت تعداد: _____ stuck jobs

# لاگ Beat فعلی
docker logs barpro-celery-beat --tail 20 | grep "phase1.scheduler.plan"
```

**✅ Checkpoint**: تعداد stuck jobs ثبت شد

---

### مرحله 3: Pull و Apply تغییرات (2 دقیقه)

```bash
cd /opt/barpro

# بررسی branch فعلی
git status
git branch

# Pull از GitHub (اگر push شده)
git pull origin main

# یا اگر فایل‌ها به صورت دستی کپی شده‌اند:
# فایل‌ها از local به /opt/barpro کپی شده‌اند

# تأیید تغییرات
git diff HEAD~1 app/services/rpa_scheduler_service.py | grep "with_for_update"
# باید خط with_for_update(skip_locked=True) را ببینیم

git diff HEAD~1 app/services/fuel_inquiry_service.py | grep "WaybillError"
# باید خط import WaybillError را ببینیم

git diff HEAD~1 app/workers/celery_app.py | grep "expires"
# باید خط expires را ببینیم
```

**✅ Checkpoint**: تغییرات روی سرور اعمال شده

---

### مرحله 4: Rebuild Images (3-5 دقیقه)

```bash
cd /opt/barpro

# Build backend image
docker compose -f compose/backend.yml build --no-cache

# تأیید build
docker images | grep barpro_backend | head -1
# باید تاریخ/زمان جدید داشته باشد
```

**✅ Checkpoint**: Images جدید ساخته شده

---

### مرحله 5: Deploy (Restart Services) (1 دقیقه)

```bash
# Restart backend services (شامل workers و beat)
docker compose -f compose/backend.yml restart

# یا برای clean restart:
# docker compose -f compose/backend.yml down
# docker compose -f compose/backend.yml up -d

# انتظار برای سالم شدن
echo "⏳ Waiting 15 seconds for services to start..."
sleep 15
```

**✅ Checkpoint**: Services ری‌استارت شده

---

### مرحله 6: Verification فوری (2 دقیقه)

```bash
# 1. وضعیت containers
docker ps | grep -E "barpro-(backend|worker|beat)"
# همه باید "Up" باشند

# 2. Health check
docker exec barpro-backend curl -f http://localhost:8000/healthz
# باید {"status":"ok"} برگرداند

# 3. PostgreSQL syntax test
docker exec barpro-postgres psql -U postgres utcms_rpa -c \
  "SELECT job_id FROM waybill_jobs WHERE status = 'pending' LIMIT 1 FOR UPDATE SKIP LOCKED;"
# نباید خطا دهد

# 4. لاگ Beat (چک کردن scheduler)
docker logs barpro-celery-beat --tail 30
# نباید ERROR داشته باشد

# 5. لاگ Workers  
docker logs barpro-worker-1 --tail 20
# نباید crash یا import error داشته باشد
```

**✅ Checkpoint**: همه سرویس‌ها سالم هستند

---

### مرحله 7: Functional Test (3 دقیقه)

```bash
# انتظار 2-3 دقیقه برای اولین چرخه scheduler
sleep 180

# بررسی stuck jobs (بعد از fix)
docker exec barpro-postgres psql -U postgres utcms_rpa -t -c \
  "SELECT COUNT(*) FROM waybill_jobs WHERE status IN ('queued', 'waiting_auth') AND updated_at < NOW() - INTERVAL '10 minutes';"

# انتظار: تعداد کاهش یافته یا 0

# بررسی لاگ dispatch
docker logs barpro-celery-beat --since 3m | grep "phase1.scheduler.plan"
# باید scheduled tasks را ببینیم

# بررسی job processing
docker exec barpro-postgres psql -U postgres utcms_rpa -c \
  "SELECT status, COUNT(*) FROM waybill_jobs WHERE created_at > NOW() - INTERVAL '10 minutes' GROUP BY status;"
```

**✅ Checkpoint**: Jobs در حال process شدن هستند

---

## 🎯 Success Criteria

Deploy موفق است اگر:

```
✅ همه containers "Up" و "healthy" هستند
✅ Health endpoint پاسخ می‌دهد
✅ PostgreSQL FOR UPDATE SKIP LOCKED بدون خطا اجرا می‌شود
✅ Beat scheduler هر N ثانیه plan می‌کند
✅ Workers jobs را process می‌کنند
✅ تعداد stuck jobs کاهش یافته یا 0 است
✅ هیچ ERROR حاد در logs نیست
✅ Memory usage < 90%
```

---

## ⚠️ Warning Signs (نشانه‌های خطر)

اگر هر کدام از این‌ها مشاهده شد، به ROLLBACK_PLAN.md مراجعه کنید:

```
❌ Containers restart loop دارند
❌ Beat scheduler متوقف شده
❌ خطای PostgreSQL syntax
❌ همه jobs به failed می‌روند
❌ Memory > 90% برای بیش از 5 دقیقه
❌ CPU > 95% مداوم
❌ تعداد stuck jobs افزایش می‌یابد
```

**→ اقدام**: فوری rollback با روش 1 (2 دقیقه)

---

## 📊 Post-Deploy Monitoring (30 دقیقه اول)

```bash
# Terminal 1: Monitor Beat
docker logs barpro-celery-beat -f | grep "phase1.scheduler.plan"

# Terminal 2: Monitor Worker 1
docker logs barpro-worker-1 -f

# Terminal 3: Monitor Stats
watch -n 10 'docker stats --no-stream | grep barpro'

# Terminal 4: Monitor Stuck Jobs
watch -n 60 'docker exec barpro-postgres psql -U postgres utcms_rpa -t -c "SELECT COUNT(*) FROM waybill_jobs WHERE status IN (\"queued\", \"waiting_auth\") AND updated_at < NOW() - INTERVAL \"15 minutes\";"'
```

در 30 دقیقه اول:
- ✅ Stuck jobs count باید کاهش یابد
- ✅ Success rate باید > 60% باشد
- ✅ Memory باید stable باشد
- ✅ Logs نباید ERROR حاد داشته باشند

---

## 📝 24-Hour Check (بعد از 24 ساعت)

```bash
ssh ubuntu@188.121.123.16

cd /opt/barpro

# 1. Stuck jobs
docker exec barpro-postgres psql -U postgres utcms_rpa -t -c \
  "SELECT COUNT(*) FROM waybill_jobs WHERE status IN ('queued', 'waiting_auth') AND updated_at < NOW() - INTERVAL '15 minutes';"
# انتظار: 0 یا نزدیک به 0

# 2. Success rate (24h)
docker exec barpro-postgres psql -U postgres utcms_rpa -c \
  "SELECT status, COUNT(*), ROUND(100.0 * COUNT(*) / SUM(COUNT(*)) OVER(), 2) as percentage FROM waybill_jobs WHERE created_at > NOW() - INTERVAL '24 hours' GROUP BY status ORDER BY COUNT(*) DESC;"
# انتظار: success > 70%

# 3. Fuel inquiries (24h)
docker exec barpro-postgres psql -U postgres utcms_rpa -c \
  "SELECT status, COUNT(*) FROM fuel_inquiries WHERE created_at > NOW() - INTERVAL '24 hours' GROUP BY status;"
# انتظار: success majority

# 4. Errors در logs
docker logs barpro-celery-beat --since 24h | grep -i error | wc -l
docker logs barpro-worker-1 --since 24h | grep -i error | wc -l
# انتظار: < 50 errors

# 5. System resources
docker stats --no-stream | grep barpro
# Memory همه < 90%

# 6. Uptime
docker ps --filter "name=barpro" --format "table {{.Names}}\t{{.Status}}"
# همه Up بدون restart
```

---

## 📞 در صورت مشکل

### مرحله deploy که مشکل دارد:

1. **مرحله 3-4 (Build)**: اگر build fail شد
   ```bash
   # بررسی logs
   docker compose -f compose/backend.yml logs
   
   # اگر syntax error: فایل‌های backup را restore کنید
   cp app/services/*.bak app/services/
   ```

2. **مرحله 5-6 (Start/Health)**: اگر services up نشدند
   ```bash
   # مشاهده logs
   docker logs barpro-backend
   docker logs barpro-worker-1
   
   # rollback سریع (روش 1)
   # رجوع به ROLLBACK_PLAN.md
   ```

3. **مرحله 7 (Functional)**: اگر jobs stuck ماندند
   ```bash
   # مانیتور 30 دقیقه بیشتر
   # اگر بهبود نیافت → rollback
   ```

---

## 🎉 Deploy Success!

اگر همه checkpoint‌ها ✅ شدند:

```
✅ Deploy موفق بود!

📋 اقدامات بعدی:
   1. ثبت در تاریخچه: "Race condition fix deployed on YYYY-MM-DD"
   2. مانیتور 24 ساعته با دستورات بالا
   3. اطلاع به تیم
   4. حذف backup files بعد از 1 هفته:
      rm app/services/*.bak

📄 مستندات:
   • DIAGNOSIS_REPORT.md — تحلیل مشکل
   • ROLLBACK_PLAN.md — در صورت نیاز
   • این فایل — برای deploy‌های بعدی
```

---

**تهیه‌کننده**: Kiro AI  
**تاریخ**: 2026-07-14  
**نسخه**: 1.0  
**Estimated Total Time**: 10-15 minutes  
**Actual Downtime**: ~30 seconds

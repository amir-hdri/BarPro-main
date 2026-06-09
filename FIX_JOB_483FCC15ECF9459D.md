# ✅ راهنمای کامل اصلاح مشکل شغل job_483fcc15ecf9459d

## 📋 خلاصه مشکل

شغل `job_483fcc15ecf9459d` برای **۸ روز** در وضعیت `WAITING_AUTH` گیر کرده بود و هر 30 دقیقه یکبار دوباره سعی می‌کرد اما شکست می‌خورد.

### 🔴 علت اصلی
1. **باگ در تابع `cleanup_stuck_jobs`**: تنها وضعیت‌های `QUEUED` و `IN_PROGRESS` را چک می‌کرد، ولی `WAITING_AUTH` را پوشش نمی‌داد
2. **چرخه بی‌نهایت در `plan_due_jobs`**: وقتی `bundle is None` بود، وضعیت به `WAITING_AUTH` تنظیم می‌شد اما `submit_after` دوباره تنظیم **نمی‌شد**
3. **مشکل اسکیما دیتابیس**: ستون `max_plates` در جدول `clients` وجود نداشت که باعث `sqlalchemy.exc.ProgrammingError` می‌شد

---

## 🔧 تغییرات اعمال شده

### 1. اصلاح تابع `cleanup_stuck_jobs` ✅
**فایل:** `app/services/rpa_scheduler_service.py` - خطوط 173-194

```python
# قبل:
stmt = select(WaybillJob).where(
    or_(
        (WaybillJob.status == TaskStatus.QUEUED.value) & (WaybillJob.updated_at < queued_cutoff),
        (WaybillJob.status == TaskStatus.IN_PROGRESS.value) & (WaybillJob.updated_at < in_progress_cutoff)
    )
)

# بعد:
waiting_auth_cutoff = now - timedelta(hours=1)
waiting_retry_cutoff = now - timedelta(hours=1)
otp_backoff_cutoff = now - timedelta(hours=2)

stmt = select(WaybillJob).where(
    or_(
        (WaybillJob.status == TaskStatus.QUEUED.value) & (WaybillJob.updated_at < queued_cutoff),
        (WaybillJob.status == TaskStatus.IN_PROGRESS.value) & (WaybillJob.updated_at < in_progress_cutoff),
        (WaybillJob.status == TaskStatus.WAITING_AUTH.value) & (WaybillJob.updated_at < waiting_auth_cutoff),
        (WaybillJob.status == TaskStatus.WAITING_RETRY.value) & (WaybillJob.updated_at < waiting_retry_cutoff),
        (WaybillJob.status == TaskStatus.OTP_BACKOFF.value) & (WaybillJob.updated_at < otp_backoff_cutoff),
    )
)
```

### 2. اصلاح تنظیم `submit_after` در `plan_due_jobs` ✅
**فایل:** `app/services/rpa_scheduler_service.py` - خط 149

```python
# قبل:
if bundle is None:
    # ...
    job.status = TaskStatus.WAITING_AUTH.value
    # submit_after دوباره تنظیم نمی‌شد!

# بعد:
if bundle is None:
    # ...
    job.status = TaskStatus.WAITING_AUTH.value
    job.submit_after = now + timedelta(seconds=utcms_config.DRIVER_RETRY_DELAY_SECONDS)
```

### 3. اضافه کردن مایگریشن جدید برای ستون `max_plates` ✅
**فایل جدید:** `alembic/versions/4a5b6c7d8e9f_ensure_max_plates_column.py`

این مایگریشن اطمینان می‌دهد که ستون `max_plates` در جدول `clients` وجود دارد، حتی اگر مایگریشن قبلی (`3ef63013cff9`) اعمال نشده باشد.

---

## 📊 وضعیت‌های پشتیبان شده توسط cleanup_stuck_jobs

| وضعیت | تایم‌اوت | علت |
|--------|----------|------|
| `QUEUED` | 15 دقیقه | انتظار طولانی در صف |
| `IN_PROGRESS` | 30 دقیقه | در حال اجرا اما گیر کرده |
| `WAITING_AUTH` | 1 ساعت | انتظار برای احراز هویت |
| `WAITING_RETRY` | 1 ساعت | انتظار برای تلاش مجدد |
| `OTP_BACKOFF` | 2 ساعت | انتظار برای کد OTP |

---

## 🚀 دستورات اعمال تغییرات

### 1. اعمال مایگریشن‌های دیتابیس
```bash
# رفتن به دایرکتوری پروژه
cd /Users/amirheidari/GitHub/BarPro-main

# فعال کردن محیط مجازی
source .venv/bin/activate

# اعمال تمام مایگریشن‌ها
alembic upgrade head

# یا به صورت اختصاصی
alembic upgrade 4a5b6c7d8e9f
```

### 2. ری‌استارت سرویس‌ها
```bash
# ری‌استارت backend و celery worker
docker-compose restart backend celery worker

# یا اگر از اسکریپت استفاده می‌کنید
./scripts/start_system.sh
```

### 3. اجرای دستی cleanup برای بازیابی فوری
```bash
# اگر می‌خواهید فوراً شغل گیر کرده بازیابی شود
source .venv/bin/activate
python -c "
from app.services.rpa_scheduler_service import rpa_scheduler_service
import asyncio

async def cleanup():
    count = await rpa_scheduler_service.cleanup_stuck_jobs()
    print(f'Recovered {count} stuck jobs')

asyncio.run(cleanup())
"
```

---

## 🔍 بررسی وضعیت پس از اعمال تغییرات

### 1. چک کردن وضعیت شغل
```bash
curl -H "Authorization: Bearer YOUR_TOKEN" \
  http://localhost:8000/api/v1/waybills/jobs/job_483fcc15ecf9459d
```

### 2. بررسی لاگ‌ها
```bash
# جستجوی لاگ‌های مربوط به بازیابی
grep -i "recovering_stuck_job" /var/log/barpro/*.log

# جستجوی لاگ‌های مربوط به شغل خاص
grep -i "job_483fcc15ecf9459d" /var/log/barpro/rpa/*.log

# بررسی آخرین وضعیت در دیتابیس
SELECT job_id, status, updated_at, submit_after, last_error, error_category 
FROM waybill_jobs 
WHERE job_id = 'job_483fcc15ecf9459d';
```

---

## 📝 لاگ‌های مربوطه

### لاگ‌های قبل از اصلاح
```
sqlalchemy.exc.ProgrammingError: column clients.max_plates does not exist
```

### لاگ‌های مورد انتظار پس از اصلاح
```
recovering_stuck_job: job_id=job_483fcc15ecf9459d, old_status=waiting_auth, last_updated=2026-06-01T14:39:00
```

---

## ✅ خلاصه تغییرات

| شماره | فایل | تغییر | اولویت |
|--------|------|--------|---------|
| 1 | `app/services/rpa_scheduler_service.py:186-193` | اضافه کردن وضعیت‌های WAITING_AUTH, WAITING_RETRY, OTP_BACKOFF به cleanup | 🔴 بحرانی |
| 2 | `app/services/rpa_scheduler_service.py:149` | تنظیم submit_after برای جلوگیری از حلقه بی‌نهایت | 🔴 بحرانی |
| 3 | `alembic/versions/4a5b6c7d8e9f_...` | مایگریشن جدید برای اطمینان از وجود max_plates | 🟡 مهم |

---

## 🎯 راه‌های جلوگیری از تکرار مشکل

1. **مونیتورینگ**: اضافه کردن هشدار برای شغل‌هایی که بیش از 1 ساعت در وضعیت WAITING_AUTH هستند
2. **تست خودکار**: تست واحد برای تابع cleanup_stuck_jobs با تمام وضعیت‌ها
3. **مکانیزم fallback**: اگر احراز هویت مکرر شکست می‌خورد، پس از 5 بار شکست، شغل را به وضعیت FAILED ببرید
4. **لاگ‌ها**: بررسی منظم لاگ‌ها برای تشخیص الگوی شکست‌های مکرر

---

## 📞 تماس در صورت مشکل

اگر پس از اعمال این تغییرات همچنان مشکل وجود داشت:
1. لاگ‌ها را بررسی کنید
2. وضعیت دیتابیس را چک کنید
3. از دستورات زیر برای دیباگ استفاده کنید:

```bash
# بررسی تمام شغل‌های گیر کرده
SELECT job_id, status, updated_at, submit_after 
FROM waybill_jobs 
WHERE status IN ('waiting_auth', 'waiting_retry', 'otp_backoff') 
AND updated_at < NOW() - INTERVAL '1 hour';

# بررسی شمارنده‌های تلاش
SELECT job_id, attempt_count, last_error 
FROM waybill_jobs 
WHERE status = 'waiting_auth' 
ORDER BY attempt_count DESC;
```

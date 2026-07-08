# گزارش مشکلات سیستم
**تاریخ:** 2026-05-01
**زمان:** 19:35

---

## 🔴 مشکلات شناسایی شده

### 1. Migration ناقص است ❌

**وضعیت فعلی:**
- نسخه migration: `005_fix_constraint_conflicts`
- نسخه مورد انتظار: `006_add_performance_indexes`

**توضیح:**
Migration 006 که شامل indexes عملکردی است، اجرا نشده. این indexes برای بهبود عملکرد queries ضروری هستند.

**تأثیر:**
- کندی در queries پایگاه داده
- عدم بهینه‌سازی جستجوها

**راه‌حل:**
```bash
cd /opt/barpro
source /Users/amirheidari/Python-ML/bin/activate
export DATABASE_URL="postgresql+asyncpg://postgres:<DB_PASSWORD>@127.0.0.1:5432/utcms_rpa"
alembic upgrade head
```

---

### 2. محدودیت‌های Sandbox محیط اجرا ⚠️

**مشکلات:**
1. **عدم امکان bind به پورت‌های شبکه**
   - خطا: `[Errno 1] operation not permitted`
   - تأثیر: نمی‌توان backend را اجرا کرد

2. **عدم دسترسی به Docker API**
   - خطا: `permission denied while trying to connect to the docker API`
   - تأثیر: نمی‌توان containers را مدیریت کرد

3. **محدودیت اتصال شبکه با asyncpg**
   - خطا: `PermissionError: [Errno 1] Operation not permitted`
   - تأثیر: نمی‌توان از asyncpg برای اتصال استفاده کرد

**توضیح:**
این محدودیت‌ها مربوط به سیاست‌های امنیتی محیط sandbox هستند و در محیط واقعی وجود ندارند.

**راه‌حل:**
اجرای دستورات در ترمینال واقعی (خارج از sandbox)

---

### 3. خطا در اسکریپت بررسی پایگاه داده 🐛

**خطا:**
```
psycopg2.errors.UndefinedColumn: column "username" does not exist
```

**علت:**
اسکریپت `full_database_check.py` سعی می‌کند ستون `username` را از جدول `drivers` بخواند، اما این ستون وجود ندارد.

**راه‌حل:**
اصلاح query در اسکریپت (این مشکل فقط در اسکریپت تست است، نه در سیستم اصلی)

---

## ✅ وضعیت خوب پایگاه داده

### داده‌های موجود:
- **Clients:** 6 مشتری
- **Drivers:** 5 راننده
- **Waybill Jobs:** 8 job
- **Waybill Attempts:** 11 تلاش
- **Domain Events:** 173 event
- **Waybill Task Logs:** 56 log

### ساختار صحیح:
- ✅ 14 جدول ایجاد شده
- ✅ 23 index عملکردی موجود
- ✅ 16 foreign key تعریف شده
- ✅ 45 constraint فعال

---

## 📊 خلاصه وضعیت

| بخش | وضعیت | توضیح |
|-----|-------|-------|
| ساختار پایگاه داده | ✅ خوب | تمام جداول و روابط صحیح است |
| داده‌های اولیه | ✅ خوب | clients و drivers موجود است |
| Migration | ⚠️ ناقص | نیاز به اجرای migration 006 |
| Indexes | ⚠️ ناقص | indexes migration 006 نصب نشده |
| محیط اجرا | ❌ محدود | sandbox permissions |

---

## 🔧 اقدامات لازم (به ترتیب اولویت)

### 1. اجرای Migration 006 (بالاترین اولویت)

**دستور:**
```bash
# در ترمینال واقعی (خارج از sandbox)
cd /opt/barpro
source /Users/amirheidari/Python-ML/bin/activate

# تنظیم DATABASE_URL
export DATABASE_URL="postgresql+asyncpg://postgres:<DB_PASSWORD>@127.0.0.1:5432/utcms_rpa"

# اجرای migration
alembic upgrade head
```

**نتیجه مورد انتظار:**
```
INFO  [alembic.runtime.migration] Running upgrade 005_fix_constraint_conflicts -> 006_add_performance_indexes
```

**بررسی موفقیت:**
```bash
# بررسی نسخه
psql -h 127.0.0.1 -U postgres -d utcms_rpa -c "SELECT version_num FROM alembic_version"

# باید نمایش دهد: 006_add_performance_indexes
```

### 2. راه‌اندازی کامل سیستم

**دستور:**
```bash
./scripts/start_system.sh
```

**بررسی:**
```bash
# بررسی containers
docker ps

# بررسی backend
curl http://localhost:8000/health

# بررسی logs
tail -f logs/backend.log
```

### 3. تست ثبت بارنامه واقعی

**دستور:**
```bash
source /Users/amirheidari/Python-ML/bin/activate
python scripts/real_waybill_test.py
```

**پیش‌نیازها:**
- اطمینان از تنظیم `UTCMS_USERNAME` و `UTCMS_PASSWORD` در `.env`
- اطمینان از اجرای backend
- اطمینان از دسترسی به اینترنت

---

## 💡 توصیه‌های بهبود

### کوتاه‌مدت:
1. ✅ اجرای migration 006
2. ✅ تست کامل سیستم با `./scripts/test_system.sh`
3. ✅ ثبت یک بارنامه تست

### میان‌مدت:
1. اضافه کردن health checks بیشتر
2. بهبود error handling در migrations
3. اضافه کردن monitoring برای performance

### بلندمدت:
1. پیاده‌سازی CI/CD pipeline
2. اضافه کردن integration tests
3. بهبود documentation

---

## 📞 راهنمای عیب‌یابی

### اگر migration 006 با خطا مواجه شد:

**خطا: "relation does not exist"**
```bash
# بررسی جداول موجود
psql -h 127.0.0.1 -U postgres -d utcms_rpa -c "\dt"

# اگر جدول وجود ندارد، migration قبلی را دوباره اجرا کنید
alembic downgrade -1
alembic upgrade head
```

**خطا: "index already exists"**
```bash
# حذف indexes موجود
psql -h 127.0.0.1 -U postgres -d utcms_rpa -c "
DROP INDEX IF EXISTS idx_waybilltask_status_created;
DROP INDEX IF EXISTS idx_waybilljob_client_status;
-- و سایر indexes
"

# سپس migration را دوباره اجرا کنید
alembic upgrade head
```

### اگر backend اجرا نشد:

**بررسی پورت:**
```bash
lsof -i :8000
# اگر پورت اشغال است:
kill -9 <PID>
```

**بررسی logs:**
```bash
tail -100 logs/backend.log
```

**بررسی environment variables:**
```bash
env | grep -E "(DATABASE|REDIS|UTCMS)"
```

---

## ✅ نتیجه‌گیری

**مشکل اصلی:** Migration 006 اجرا نشده است.

**راه‌حل:** اجرای `alembic upgrade head` در ترمینال واقعی.

**وضعیت کلی:** سیستم سالم است و فقط نیاز به تکمیل migration دارد.

**زمان تخمینی برای رفع:** 5-10 دقیقه

---

**پایان گزارش**

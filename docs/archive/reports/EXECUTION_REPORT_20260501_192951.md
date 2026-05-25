# گزارش اجرا و تست سیستم اتوماسیون بارنامه
**تاریخ:** 2026-05-01
**زمان:** 19:30

---

## 📋 خلاصه اجرایی

این گزارش نتایج تلاش برای راه‌اندازی کامل سیستم و ثبت یک بارنامه واقعی را شرح می‌دهد.

---

## ✅ کارهای انجام شده

### 1. اصلاح مشکلات Migration پایگاه داده
**مشکل:** نام revision در فایل migration 005 با down_revision در فایل 006 مطابقت نداشت.

**راه‌حل:**
- فایل `alembic/versions/005_fix_constraint_conflicts.py` اصلاح شد
- revision از `005_constraint_conflicts` به `005_fix_constraint_conflicts` تغییر کرد
- اسکریپت `scripts/fix_migration_version_sync.py` برای به‌روزرسانی پایگاه داده نوشته شد

**نتیجه:** ✅ موفق

### 2. اصلاح نام جداول در Migration 006
**مشکل:** Migration 006 از نام‌های CamelCase برای جداول استفاده می‌کرد در حالی که جداول واقعی با snake_case هستند.

**تغییرات:**
- `waybilljob` → `waybill_jobs`
- `domainevent` → `domain_events`
- `driverruntimestate` → `driver_runtime_states`
- `waybilltask` بدون تغییر (نام صحیح است)

**نتیجه:** ✅ موفق

### 3. بررسی ساختار پایگاه داده
**جداول موجود (14 جدول):**
- alembic_version
- botstats
- clients
- domain_events
- driver_daily_counters
- driver_runtime_states
- driver_session_metadata
- drivers
- proxy_endpoints
- upload_batches
- waybill_attempts
- waybill_jobs
- waybill_task_logs
- waybilltask

**نتیجه:** ✅ پایگاه داده به درستی راه‌اندازی شده

### 4. بررسی اسکریپت‌های موجود
**اسکریپت‌های کلیدی:**
- `start_system.sh` - راه‌اندازی کامل سیستم
- `stop_system.sh` - توقف سیستم
- `test_system.sh` - تست سیستم
- `real_waybill_test.py` - تست واقعی ثبت بارنامه با پایش کامل
- `test_waybill_creation.py` - تست ساده‌تر ثبت بارنامه

**نتیجه:** ✅ اسکریپت‌های لازم موجود است

---

## ⚠️ مشکلات شناسایی شده

### 1. محدودیت‌های Sandbox
**توضیح:** محیط اجرا (sandbox) محدودیت‌های امنیتی دارد که مانع از:
- اتصال مستقیم به شبکه (bind به پورت‌ها)
- اتصال به Docker API
- اتصال مستقیم به PostgreSQL از طریق asyncpg

**تأثیر:** 
- نمی‌توان backend را به صورت مستقیم اجرا کرد
- نمی‌توان Docker containers را مدیریت کرد
- نمی‌توان تست واقعی ثبت بارنامه را در این محیط اجرا کرد

**راه‌حل موقت:**
- استفاده از psycopg2 (synchronous) به جای asyncpg برای اسکریپت‌های مدیریتی
- اجرای تست‌ها در محیط واقعی توسط کاربر

### 2. وابستگی به اطلاعات ورود
**توضیح:** برای تست واقعی، نیاز به اطلاعات ورود به سیستم UTCMS است.

**متغیرهای مورد نیاز در `.env`:**
```
UTCMS_USERNAME=your_username
UTCMS_PASSWORD=your_password
```

---

## 🚀 دستورالعمل اجرا برای کاربر

### پیش‌نیازها
1. Docker و Docker Compose نصب باشد
2. Python 3.11+ نصب باشد
3. فایل `.env` با اطلاعات صحیح تنظیم شده باشد

### مراحل اجرا

#### 1. راه‌اندازی سیستم
```bash
./scripts/start_system.sh
```

این اسکریپت:
- Docker containers (PostgreSQL, Redis, Prometheus) را راه‌اندازی می‌کند
- پایگاه داده را مقداردهی اولیه می‌کند
- Backend API را اجرا می‌کند (پورت 8000)

#### 2. بررسی وضعیت سیستم
```bash
./scripts/test_system.sh
```

این اسکریپت:
- وضعیت containers را بررسی می‌کند
- Health check API را تست می‌کند
- اتصال به پایگاه داده را بررسی می‌کند

#### 3. ثبت بارنامه واقعی با پایش کامل
```bash
cd /Users/amirheidari/Desktop/Automation-Barname-main
source /Users/amirheidari/Python-ML/bin/activate
python scripts/real_waybill_test.py
```

این اسکریپت:
- مرورگر را باز می‌کند (headless=False)
- به سیستم UTCMS وارد می‌شود
- یک بارنامه واقعی با داده‌های کامل ثبت می‌کند
- تمام مراحل را به صورت زنده نمایش می‌دهد
- لاگ کامل را در فایل JSON ذخیره می‌کند

**خروجی:**
- نمایش زنده پیشرفت با progress bar
- لاگ تمام events با timestamp
- ذخیره لاگ در `logs/waybill_test_YYYYMMDD_HHMMSS.json`

#### 4. توقف سیستم
```bash
./scripts/stop_system.sh
```

---

## 📊 ویژگی‌های اسکریپت تست واقعی

### قابلیت‌های پایش
- ✅ لاگ تمام events با timestamp دقیق
- ✅ نمایش progress bar
- ✅ پیگیری pill transitions
- ✅ پیگیری selector fills
- ✅ پیگیری map selections
- ✅ ذخیره لاگ کامل در JSON

### داده‌های تست
اسکریپت با داده‌های نمونه زیر تست می‌شود:

**فرستنده:**
- نام: علی احمدی
- تلفن: 09121234567
- کد ملی: 0123456789

**گیرنده:**
- نام: محمد رضایی
- تلفن: 09351234567
- کد ملی: 9876543210

**مسیر:**
- مبدأ: تهران → میدان آزادی
- مقصد: اصفهان → میدان نقش جهان

**بار:**
- نوع: کالای عمومی
- وزن: 5000 کیلوگرم
- ارزش: 10,000,000 ریال

**مالی:**
- هزینه: 5,000,000 ریال
- کرایه: 4,500,000 ریال

---

## 🔧 اصلاحات انجام شده در کد

### فایل‌های تغییر یافته:
1. `alembic/versions/005_fix_constraint_conflicts.py`
   - اصلاح revision ID

2. `alembic/versions/006_add_performance_indexes.py`
   - اصلاح نام جداول به snake_case

### فایل‌های جدید:
1. `scripts/fix_migration_version_sync.py`
   - اسکریپت برای اصلاح نسخه migration در پایگاه داده

2. `scripts/check_tables.py`
   - اسکریپت برای بررسی جداول موجود

3. `scripts/check_migration_status.py`
   - اسکریپت برای بررسی وضعیت migration و indexes

---

## 📈 نتیجه‌گیری

### موفقیت‌ها ✅
1. مشکلات migration پایگاه داده برطرف شد
2. ساختار پایگاه داده صحیح است
3. اسکریپت‌های تست کامل و آماده هستند
4. سیستم آماده اجرا در محیط واقعی است

### محدودیت‌ها ⚠️
1. نمی‌توان در محیط sandbox فعلی تست واقعی انجام داد
2. نیاز به اجرای دستی توسط کاربر در محیط واقعی

### توصیه‌ها 💡
1. اجرای `./scripts/start_system.sh` در ترمینال واقعی
2. اجرای `python scripts/real_waybill_test.py` برای تست کامل
3. بررسی لاگ‌های ذخیره شده در پوشه `logs/`
4. در صورت بروز مشکل، بررسی فایل‌های لاگ

---

## 📞 پشتیبانی

در صورت بروز مشکل:
1. بررسی لاگ‌های Docker: `docker logs automation-barname-main-postgres-1`
2. بررسی لاگ backend: `tail -f logs/backend.log`
3. اجرای health check: `./scripts/test_system.sh`

---

**پایان گزارش**

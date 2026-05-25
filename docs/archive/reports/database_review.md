# بررسی و تحلیل دیتابیس (Database Review)

با توجه به عدم دسترسی مستقیم به دیتابیس پروداکشن (PostgreSQL)، این تحلیل بر اساس ساختار مدل‌های تعریف شده در کد (SQLModel / SQLAlchemy) و اسکریپت‌های تحلیلی موجود انجام شده است.

## ۱. مشکلات اسکریپت تحلیل دیتابیس (`scripts/analyze_database.py`)
اسکریپت `analyze_database.py` به کوئری‌های خاص PostgreSQL (مانند `pg_stat_user_tables` و `pg_stat_statements`) وابستگی دارد. این اسکریپت در محیط‌های توسعه که از SQLite استفاده می‌کنند با خطا مواجه می‌شد. این مشکل با اضافه کردن یک بررسی اولیه برای اطمینان از اجرای آن فقط روی PostgreSQL برطرف شد.

## ۲. ساختار جداول و مدل‌ها
### فایل `app/models.py`
جداول اصلی:
- `BotStats`
- `WaybillTask`

### فایل `app/models_management.py`
جداول اصلی:
- `ManagedCustomer`
- `ManagedRoute`
- `ManagedAccount`
- `ManagedQueueItem`
- `ManagedSyncLog`

### فایل `app/models_multitenant.py`
جداول اصلی:
- `Client`
- `Driver`
- `DriverPlate`
- `DriverSchedule`
- `WaybillJob`
- `WaybillTaskLog`
- `UploadBatch`
- `BotStats`
- `WaybillTask`

### فایل `app/models_legacy.py`
جداول اصلی:
- `BotStats`
- `WaybillTask`

### فایل `app/models_rpa.py`
جداول اصلی:
- `DriverRuntimeState`
- `DriverDailyCounter`
- `DriverSessionMetadata`
- `WaybillAttempt`
- `DomainEvent`
- `ProxyEndpoint`

### فایل `app/models/admin.py`
جداول اصلی:
- `SuperAdmin`
- `SubscriptionPlan`
- `AdminDriverSchedule`
- `ActivityLog`

## ۳. مشکلات احتمالی و پیشنهادات بهینه‌سازی (بر اساس کد)

### الف) مشکل N+1 Queries
در برخی از سرویس‌ها و کوئری‌ها ممکن است به دلیل استفاده از ORM (مانند SQLModel/SQLAlchemy) بدون استفاده از `selectinload` یا `joinedload` برای روابط (Relationships)، مشکل N+1 Query رخ دهد. توصیه می‌شود در کوئری‌هایی که نیاز به لود کردن رکوردهای مرتبط دارند، از eager loading استفاده شود.

### ب) ایندکس‌های مفقوده (Missing Indexes)
اگرچه برخی از فیلدها دارای `index=True` هستند، اما برای جستجوهای ترکیبی (Compound Queries) که روی چند ستون همزمان انجام می‌شوند، ایندکس‌های ترکیبی در `__table_args__` تعریف نشده‌اند که می‌تواند باعث کاهش کارایی در جداول بزرگ شود.

### ج) مدیریت داده‌های بزرگ (JSON Payload)
در جدولی مانند `WaybillTask` فیلدهای `payload_json` و `result_json` از نوع `Text` هستند. در پایگاه داده PostgreSQL بهتر است این فیلدها به عنوان `JSONB` تعریف شوند تا امکان جستجو و ایندکس‌گذاری بهینه روی محتوای JSON فراهم شود.

### د) پاک‌سازی جداول حجیم
جداول لاگ و تسک مانند `WaybillTask`، `ActivityLog` و `WaybillTaskLog` به سرعت رشد می‌کنند. نیاز به پیاده‌سازی یک مکانیزم پاک‌سازی دوره‌ای (Data Retention Policy) برای حذف یا آرشیو داده‌های قدیمی (مثلاً قدیمی‌تر از ۹۰ روز) وجود دارد تا حجم دیتابیس بیش از حد افزایش نیابد.

### ه) آمارگیری و Performance
استفاده از توابع تحلیلی مانند `pg_stat_statements` در `analyze_database.py` بسیار عالی است. پیشنهاد می‌شود این اسکریپت در محیط پروداکشن به صورت دوره‌ای (مثلاً به عنوان یک Cron Job) اجرا شود و خروجی آن مانیتور شود تا کوئری‌های کند شناسایی شوند.

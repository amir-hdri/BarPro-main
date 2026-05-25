## ۴. ساختار APIها (API Design)

با توجه به معماری چند‌مستأجره (Multi-Tenant) و پیاده‌سازی سرویس‌ها، معماری مسیرها به شکل زیر طراحی و عملیاتی شده است:

### ۴.۱ مسیرهای مربوط به Auth و Tenant (مستأجرین)
- `POST /api/v1/auth/login` : دریافت JWT و شروع سشن (Session Vault)
- `POST /api/v1/tenants/` : ایجاد شرکت جدید (ویژه Super Admin)
- `GET /api/v1/tenants/{client_id}` : واکشی اطلاعات مستأجر
- `POST /api/v1/tenants/{client_id}/api-keys` : تولید API Key برای دسترسی برنامه‌نویسی

### ۴.۲ موجودیت‌های پایه (Drivers & Plates)
- `POST /api/v1/drivers/` : اضافه کردن راننده و ذخیره اطلاعات رمزنگاری شده (Credentials) با کلاس AES
- `GET /api/v1/drivers/` : دریافت لیست رانندگان مجاز برای مستأجر
- `PUT /api/v1/drivers/{driver_id}/plates` : تخصیص و اعتبارسنجی پلاک برای راننده
- `GET /api/v1/drivers/{driver_id}/status` : بررسی وضعیت سلامت راننده (آیا نیازمند OTP است؟)

### ۴.۳ مدیریت بارنامه‌ها (Waybills)
- `POST /api/v1/waybills/single` : ارسال یک بارنامه جدید در صف پردازش (Redis/BullMQ/Celery)
- `POST /api/v1/waybills/bulk` : پردازش و اعتبارسنجی فایل اکسل بارنامه‌ها
- `GET /api/v1/waybills/status/{job_id}` : چک کردن وضعیت اجرای یک بارنامه
- `DELETE /api/v1/waybills/{job_id}` : لغو بارنامه‌ای که در وضعیت Pending قرار دارد

### ۴.۴ مانیتورینگ و لاگ‌ها (Management & Monitoring)
- `GET /api/v1/reports/dashboard` : داشبورد آماری کلی، بارنامه‌های امروز، آمار موفقیت و شکست‌ها
- `GET /api/v1/system/healthz` : بررسی سلامت تمامی وابستگی‌ها (Database, Redis, Worker, Captcha Server)
- `GET /api/v1/reports/audit-logs` : استخراج لاگ‌های سیستمی و ردگیری اعمال کاربران

---

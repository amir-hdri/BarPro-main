# راهنمای راه‌اندازی سیستم UTCMS

## وب اپ جدید با موفقیت ساخته شد! 🎉

یک رابط کاربری مدرن، سریع و کاملاً responsive با ویژگی‌های زیر طراحی شده است:

### ✨ ویژگی‌ها:

- **طراحی مدرن و حرفه‌ای** با Tailwind CSS
- **کاملاً Responsive** برای موبایل، تبلت و دسکتاپ
- **سریع و بهینه** با Next.js 16 و Turbopack
- **یکپارچه با Backend** - تمام APIها متصل شده‌اند
- **بدون خطا** - تست شده و آماده استفاده

### 📱 صفحات:

1. **داشبورد** (`/`) - نمای کلی آمار سیستم
2. **ثبت بارنامه** (`/new`) - فرم کامل ثبت بارنامه
3. **تاریخچه** (`/history`) - لیست و جستجوی بارنامه‌ها
4. **رانندگان** (`/drivers`) - مدیریت رانندگان
5. **گزارشات** (`/reports`) - تحلیل و گزارش‌گیری
6. **تنظیمات** (`/settings`) - تنظیمات سیستم

---

## 🚀 راه‌اندازی سیستم

### روش 1: استفاده از اسکریپت خودکار (توصیه می‌شود)

در ترمینال خودتان این دستور را اجرا کنید:

```bash
cd /Users/amirheidari/Desktop/Automation-Barname-main
./scripts/start_system.sh
```

### روش 2: راه‌اندازی دستی

#### مرحله 1: راه‌اندازی Docker Services

```bash
cd /Users/amirheidari/Desktop/Automation-Barname-main
docker compose up -d postgres redis prometheus
```

#### مرحله 2: راه‌اندازی Backend

در یک ترمینال جدید:

```bash
cd /Users/amirheidari/Desktop/Automation-Barname-main

export DATABASE_URL="postgresql+asyncpg://postgres:<DB_PASSWORD>@127.0.0.1:5432/utcms_rpa"
export REDIS_URL="redis://:${REDIS_PASSWORD}@127.0.0.1:6379/0"
export REDIS_PASSWORD="your_secure_redis_password_here"
export PORT=8000

/Users/amirheidari/Python-ML/bin/python3 -m uvicorn app.main:app --host 0.0.0.0 --port 8000
```

#### مرحله 3: راه‌اندازی Frontend

در یک ترمینال جدید دیگر:

```bash
cd /Users/amirheidari/Desktop/Automation-Barname-main/apps/web

export PATH="/opt/node/bin:$PATH"
export NEXT_PUBLIC_API_URL="http://localhost:8000/api"
export PORT=3000
export HOSTNAME=0.0.0.0

/opt/node/bin/node .next/standalone/server.js
```

---

## 🌐 دسترسی به سیستم

بعد از راه‌اندازی، مرورگر را باز کنید:

- **Frontend (وب اپ)**: http://localhost:3000
- **Backend API**: http://localhost:8000/docs
- **Prometheus**: http://localhost:9090

---

## 🛑 توقف سیستم

```bash
cd /Users/amirheidari/Desktop/Automation-Barname-main
./scripts/stop_system.sh
```

یا به صورت دستی:

```bash
# توقف Backend و Frontend
pkill -f "uvicorn app.main:app"
pkill -f "node.*server.js"

# توقف Docker
docker compose down
```

---

## 📝 نکات مهم

1. **حتماً از ترمینال خودتان اجرا کنید** - نه از طریق ابزارهای دیگر
2. **ترمینال را باز نگه دارید** - بستن ترمینال باعث توقف سرویس‌ها می‌شود
3. **پورت‌ها را چک کنید** - مطمئن شوید پورت‌های 3000 و 8000 آزاد هستند
4. **Docker باید در حال اجرا باشد** - Docker Desktop را روشن کنید

---

## 🎨 تکنولوژی‌های استفاده شده

### Frontend:
- Next.js 16.2.3 (با Turbopack)
- React 19
- TypeScript
- Tailwind CSS 3
- Heroicons

### Backend:
- FastAPI
- PostgreSQL
- Redis
- Prometheus

---

## 🐛 عیب‌یابی

### مشکل: Frontend باز نمی‌شود

```bash
# چک کنید که Backend در حال اجرا است
curl http://localhost:8000/docs

# چک کنید که Frontend در حال اجرا است
curl http://localhost:3000

# لاگ‌ها را بررسی کنید
tail -f output/backend.log
tail -f output/frontend.log
```

### مشکل: خطای اتصال به دیتابیس

```bash
# مطمئن شوید Docker در حال اجرا است
docker ps

# اگر نیست، راه‌اندازی کنید
docker compose up -d postgres redis
```

### مشکل: پورت اشغال است

```bash
# پیدا کردن پروسس روی پورت 8000
lsof -i :8000

# پیدا کردن پروسس روی پورت 3000
lsof -i :3000

# کشتن پروسس (PID را جایگزین کنید)
kill -9 <PID>
```

---

## 📞 پشتیبانی

اگر مشکلی داشتید:

1. لاگ‌های `output/backend.log` و `output/frontend.log` را بررسی کنید
2. مطمئن شوید تمام سرویس‌های Docker در حال اجرا هستند
3. مطمئن شوید Node.js و Python نصب شده‌اند

---

**موفق باشید! 🚀**

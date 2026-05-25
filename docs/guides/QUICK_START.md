# راهنمای راه‌اندازی سریع UTCMS Automation

> **📌 معماری جدید:** پروژه به معماری monorepo ارتقا یافته است. فرانت‌اند اصلی با Next.js و Tailwind در پوشه `apps/web/` و بک‌اند در `app/` قرار دارد. تمامی مستندات در راستای این تغییرات به‌روزرسانی شده‌اند.


## 🚀 راه‌اندازی در 3 دقیقه

### پیش‌نیازها
- ✅ Docker Desktop (در حال اجرا)
- ✅ Python 3.11+ (محیط مجازی: `/Users/amirheidari/Python-ML`)
- ✅ Node.js 20+
- ✅ PostgreSQL و Redis (از طریق Docker)

---

## گام 1: راه‌اندازی Docker

```bash
cd /Users/amirheidari/Desktop/Automation-Barname-main
docker compose up -d
```

**بررسی وضعیت:**
```bash
docker ps
```

باید 3 container ببینید:
- `postgres:16-alpine` (پورت 5432)
- `redis:7-alpine` (پورت 6379)
- `prometheus` (پورت 9090)

---

## گام 2: راه‌اندازی Backend

```bash
./scripts/start_backend.sh
```

**خروجی موفق:**
```
✅ اتصال به دیتابیس موفق
🚀 راه‌اندازی Backend API...
📍 Backend در حال اجرا: http://localhost:8000
```

**تست Backend:**
```bash
curl http://localhost:8000/
# خروجی: {"message":"سیستم اتوماسیون UTCMS فعال است"}
```

---

## گام 3: راه‌اندازی Frontend

**در ترمینال جدید:**
```bash
./scripts/start_frontend.sh
```

**خروجی موفق:**
```
🚀 راه‌اندازی Frontend...
📍 Frontend در حال اجرا: http://localhost:3000
```

---

## 🎯 دسترسی به سیستم

| سرویس | آدرس | توضیحات |
|-------|------|---------|
| Frontend | http://localhost:3000 | رابط کاربری |
| Backend API | http://localhost:8000 | REST API |
| API Docs | http://localhost:8000/docs | Swagger UI |
| Prometheus | http://localhost:9090 | Metrics |
| PostgreSQL | localhost:5432 | Database |
| Redis | localhost:6379 | Cache |

---

## 🔧 تنظیمات اولیه

### 1. تنظیم اطلاعات ورود UTCMS

**فایل:** `.env`

```bash
# اضافه کنید:
UTCMS_USERNAME=your_username
UTCMS_PASSWORD=your_password
```

### 2. تنظیم API Key (اختیاری)

Frontend به صورت پیش‌فرض از localStorage استفاده می‌کند.

---

## 🧪 تست سیستم

### تست Backend
```bash
# Health check
curl http://localhost:8000/

# API documentation
open http://localhost:8000/docs
```

### تست Database
```bash
docker exec -it automation-barname-main-postgres-1 \
  psql -U postgres -d utcms_rpa -c "SELECT COUNT(*) FROM clients;"
```

### اجرای تست‌ها
```bash
cd /Users/amirheidari/Desktop/Automation-Barname-main
source /Users/amirheidari/Python-ML/bin/activate
pytest tests/ -v
```

---

## 📊 مانیتورینگ

### لاگ‌های Backend
```bash
# در ترمینال Backend
# لاگ‌ها به صورت JSON structured نمایش داده می‌شوند
```

### لاگ‌های Docker
```bash
docker logs automation-barname-main-postgres-1
docker logs automation-barname-main-redis-1
```

### Prometheus Metrics
```bash
open http://localhost:9090
```

---

## 🛠️ عیب‌یابی

### مشکل: Backend راه‌اندازی نمی‌شود

**بررسی Docker:**
```bash
docker ps
# اگر containers نبودند:
docker compose up -d
```

**بررسی دیتابیس:**
```bash
docker exec -it automation-barname-main-postgres-1 \
  psql -U postgres -c "\l"
```

### مشکل: Frontend راه‌اندازی نمی‌شود

**نصب dependencies:**
```bash
cd apps/web
yarn install
```

**بررسی Backend:**
```bash
curl http://localhost:8000/
```

### مشکل: خطای اتصال به دیتابیس

**بررسی password:**
```bash
# در .env یا docker-compose.yml
POSTGRES_PASSWORD=<DB_PASSWORD>
```

**Restart containers:**
```bash
docker compose down
docker compose up -d
```

---

## 🔄 دستورات مفید

### توقف سیستم
```bash
# توقف Backend: Ctrl+C در ترمینال Backend
# توقف Frontend: Ctrl+C در ترمینال Frontend
# توقف Docker:
docker compose down
```

### Restart سیستم
```bash
docker compose restart
./scripts/start_backend.sh
./scripts/start_frontend.sh
```

### پاک‌سازی
```bash
# پاک کردن containers
docker compose down -v

# پاک کردن node_modules
cd apps/web
rm -rf node_modules
yarn install
```

---

## 📚 مستندات بیشتر

- [گزارش جامع بررسی](./COMPREHENSIVE_AUDIT_REPORT.md)
- [گزارش ارتقا](./UPGRADE_REPORT.md)
- [گزارش پیاده‌سازی](./UPGRADE_IMPLEMENTATION_REPORT.md)
- [مشکلات و راه‌حل‌ها](./PROBLEMS_AND_SOLUTIONS.md)

---

## 💡 نکات مهم

1. **همیشه Docker را قبل از Backend راه‌اندازی کنید**
2. **Backend باید قبل از Frontend اجرا شود**
3. **برای ثبت بارنامه واقعی، اطلاعات ورود UTCMS الزامی است**
4. **تست‌ها را قبل از deploy اجرا کنید**

---

**آخرین به‌روزرسانی:** 2025-05-01  
**نسخه:** 2.1.0

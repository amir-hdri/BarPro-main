# 🛠️ راهنمای حل مشکلات (Troubleshooting Guide)

## فهرست‌ مشکلات

1. [اتصال دیتابیس](#اتصال-دیتابیس)
2. [ارتباط فرانت‌اند و بک‌اند](#ارتباط-فرانت‌اند-و-بک‌اند)
3. [مشکلات Redis](#مشکلات-redis)
4. [مشکلات Docker](#مشکلات-docker)
5. [مشکلات Migration](#مشکلات-migration)
6. [مشکلات CORS](#مشکلات-cors)
7. [مشکلات Authentication](#مشکلات-authentication)

---

## اتصال دیتابیس

### ❌ خطا: "connection refused" یا "could not connect to server"

**علت احتمالی:**
- PostgreSQL service شروع نشده است
- PORT 5432 اشغال است
- DATABASE_URL غلط است

**حل:**

```bash
# 1️⃣ بررسی اینکه PostgreSQL در حال اجرا است
docker-compose ps | grep postgres

# 2️⃣ اگر اجرا نمی‌شد، شروع کنید
docker-compose up -d postgres

# 3️⃣ بررسی logs
docker-compose logs postgres

# 4️⃣ Test اتصال
psql postgresql://postgres:PASSWORD@localhost:5432/utcms_rpa
```

### ❌ خطا: "no more connections allowed"

**علت**: Connection pool exhausted

**حل:**

```python
# app/core/database.py - بررسی pool_size

engine_kwargs = {
    "pool_size": 20,        # اگر کم است، بیشتر کنید
    "max_overflow": 10,     # overflow برای بار سنگین
    "pool_timeout": 30,     # timeout
}
```

```bash
# یا restart کنید
docker-compose restart backend
```

### ❌ خطا: "relation does not exist" یا "column not found"

**علت**: Migrations اجرا نشده است

**حل:**

```bash
# 1️⃣ مشاهده وضعیت migrations
alembic current

# 2️⃣ اجرای migrations
alembic upgrade head

# 3️⃣ اگر مشکل داشت، downgrade و دوباره upgrade کنید
alembic downgrade base
alembic upgrade head
```

### ❌ خطا: "pool_pre_ping=True" و connection hang می‌کند

**حل:**

```python
# app/core/database.py
engine_kwargs = {
    "pool_size": 20,
    "max_overflow": 10,
    "pool_timeout": 30,     # ⚠️ این را بیشتر کنید
    "pool_recycle": 3600,   # recycling time
    "pool_pre_ping": True,  # health check
}
```

---

## ارتباط فرانت‌اند و بک‌اند

### ❌ خطا: CORS error "Access to XMLHttpRequest blocked by CORS policy"

**علت احتمالی:**
- Frontend URL غلط در backend است
- CORS middleware disabled است
- Frontend از port غلط استفاده می‌کند

**حل:**

```bash
# 1️⃣ بررسی FRONTEND_URL در .env
grep FRONTEND_URL .env

# اگر خالی است:
echo "FRONTEND_URL=http://localhost:3000" >> .env
```

```python
# app/main.py - بررسی CORS

cors_origins = _frontend_origins()
if not cors_origins:
    cors_origins = [
        "http://localhost:3000",
        "http://127.0.0.1:3000",
    ]

# ✅ این باید true باشد
print(f"CORS Origins: {cors_origins}")
```

```bash
# 2️⃣ Test CORS
curl -H "Origin: http://localhost:3000" \
  -H "Access-Control-Request-Method: GET" \
  -H "Access-Control-Request-Headers: authorization" \
  -X OPTIONS http://localhost:8000/healthz -v
```

### ❌ خطا: "API_BASE_URL is undefined" یا 404 on requests

**علت**: NEXT_PUBLIC_API_URL غلط تنظیم شده است

**حل:**

```bash
# 1️⃣ بررسی .env.local
cat apps/web/.env.local

# اگر خالی است:
echo "NEXT_PUBLIC_API_URL=http://127.0.0.1:8000" > apps/web/.env.local

# 2️⃣ Rebuild frontend
docker-compose down frontend
docker-compose up -d frontend --build
```

```typescript
// apps/web/src/lib/api.ts - بررسی
export const API_BASE_URL = (
    process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000'
).replace(/\/+$/, '').replace(/\/api$/, '');

console.log('API_BASE_URL:', API_BASE_URL); // debug
```

### ❌ خطا: 401 Unauthorized - Token invalid

**علت**: Token expired یا localStorage خالی است

**حل:**

```typescript
// apps/web/src/lib/api.ts - بررسی token handling

function getStoredTokenCandidate(): string | null {
  if (typeof window === 'undefined') return null;
  return (
    localStorage.getItem('utcms_auth_token') ||
    localStorage.getItem('utcms_token') ||
    localStorage.getItem('access_token') ||
    localStorage.getItem('token') ||
    null
  );
}

// Browser console
localStorage.getItem('utcms_auth_token') // بررسی token
localStorage.clear() // پاک کردن
```

```bash
# Backend - بررسی JWT_SECRET
grep JWT_SECRET .env

# اگر خالی است:
echo "JWT_SECRET=$(python3 -c 'import secrets; print(secrets.token_urlsafe(32))')" >> .env
```

---

## مشکلات Redis

### ❌ خطا: "connection refused" یا Redis not connecting

**حل:**

```bash
# 1️⃣ بررسی Redis
docker-compose ps | grep redis

# 2️⃣ شروع اگر نیست
docker-compose up -d redis

# 3️⃣ بررسی logs
docker-compose logs redis

# 4️⃣ Test اتصال
redis-cli -h localhost -p 6379 -a PASSWORD ping
```

### ❌ خطا: "WRONGPASS" یا "Authentication failed"

**علت**: REDIS_PASSWORD غلط است

**حل:**

```bash
# 1️⃣ بررسی .env
grep REDIS_PASSWORD .env

# 2️⃣ Generate random password
python3 -c "import secrets; print(secrets.token_urlsafe(16))"

# 3️⃣ Update .env
REDIS_PASSWORD=YOUR_NEW_PASSWORD

# 4️⃣ Restart Redis و Backend
docker-compose restart redis backend
```

### ❌ خطا: Redis memory exhausted

**حل:**

```bash
# 1️⃣ بررسی memory usage
redis-cli -a PASSWORD info memory

# 2️⃣ Clear old keys
redis-cli -a PASSWORD FLUSHDB

# 3️⃣ یا restart
docker-compose restart redis
```

---

## مشکلات Docker

### ❌ خطا: "docker-compose command not found"

**حل:**

```bash
# اگر Docker Desktop نیست:
pip install docker-compose

# یا Docker V2 plugin:
docker compose up -d  # بدون hyphen
```

### ❌ خطا: "No space left on device"

**حل:**

```bash
# 1️⃣ Clean up Docker
docker system prune -a

# 2️⃣ Remove volumes اگر safe است
docker volume prune

# 3️⃣ Restart
docker-compose up -d
```

### ❌ خطا: "Port already in use"

**حل:**

```bash
# 1️⃣ Find process using port
lsof -i :5432  # PostgreSQL
lsof -i :6379  # Redis
lsof -i :8000  # Backend
lsof -i :3000  # Frontend

# 2️⃣ Kill process (be careful!)
kill -9 <PID>

# 3️⃣ یا استفاده از port دیگری
docker-compose -f docker-compose.yml \
  -e POSTGRES_PORT=5433 \
  -e REDIS_PORT=6380 \
  up -d
```

### ❌ خطا: Service "backend" depends on service "postgres" which is unhealthy

**حل:**

```bash
# 1️⃣ بررسی healthcheck
docker-compose ps

# 2️⃣ View detailed logs
docker-compose logs postgres

# 3️⃣ Restart postgres
docker-compose restart postgres

# 4️⃣ Then restart backend
docker-compose restart backend
```

---

## مشکلات Migration

### ❌ خطا: "Can't locate revision identified by" یا migration conflicts

**حل:**

```bash
# 1️⃣ بررسی current revision
alembic current

# 2️⃣ Downgrade to base
alembic downgrade base

# 3️⃣ Upgrade to head
alembic upgrade head

# 4️⃣ اگر هنوز مشکل دارد:
# منually check alembic/versions/
ls -la alembic/versions/
```

### ❌ خطا: "Multiple heads detected"

**حل:**

```bash
# 1️⃣ بررسی heads
alembic heads

# 2️⃣ Fix merge conflict
alembic merge --message "merge heads" <rev1> <rev2>

# 3️⃣ Upgrade
alembic upgrade head
```

### ❌ خطا: "Can't drop table - constraint violations"

**حل:**

```bash
# 1️⃣ بررسی constraints
SELECT constraint_name FROM information_schema.table_constraints 
WHERE table_name='table_name';

# 2️⃣ Manually drop constraints
ALTER TABLE table_name DROP CONSTRAINT constraint_name;

# 3️⃣ Re-run migration
alembic upgrade head
```

---

## مشکلات CORS

### ✅ Test CORS

```bash
# Method 1: curl with headers
curl -H "Origin: http://localhost:3000" \
  -H "Access-Control-Request-Method: GET" \
  -X OPTIONS http://localhost:8000/healthz -v

# Method 2: Browser console
fetch('http://localhost:8000/healthz', {
  credentials: 'include',
  headers: {
    'Content-Type': 'application/json'
  }
})
```

### ❌ خطا: "No 'Access-Control-Allow-Origin' header"

**حل:**

```python
# app/main.py - بررسی

cors_origins = _frontend_origins()
print(f"DEBUG: CORS origins = {cors_origins}")  # بررسی

if not cors_origins:
    cors_origins = ["http://localhost:3000", "http://127.0.0.1:3000"]

app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_origins,  # ✅ باید شامل frontend URL باشد
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
```

---

## مشکلات Authentication

### ❌ خطا: Login fails - "Invalid credentials"

**حل:**

```bash
# 1️⃣ بررسی user exists
psql -U postgres -d utcms_rpa -c "SELECT * FROM clients WHERE client_code='test';"

# 2️⃣ Create test user
python3 scripts/init_database.py

# 3️⃣ بررسی password hash
# Use bcrypt برای verify
```

### ❌ خطا: JWT errors - "Invalid token"

**حل:**

```python
# Backend - بررسی JWT config
from app.core.config import utcms_config

print(f"JWT_SECRET_LENGTH: {len(utcms_config.JWT_SECRET)}")  # should > 32
print(f"JWT_ALGORITHM: {getattr(utcms_config, 'JWT_ALGORITHM', 'HS256')}")

# اگر مشکل دارد:
# Generate new JWT_SECRET
python3 -c "import secrets; print(secrets.token_urlsafe(32))"
```

---

## Debugging Tips

### 📝 Enable Debug Logging

```bash
# Set LOG_LEVEL
export LOG_LEVEL=DEBUG

# یا در .env
echo "LOG_LEVEL=DEBUG" >> .env

# Restart backend
docker-compose restart backend
```

### 🔍 Inspect Requests

```bash
# Browser DevTools - Network tab
# Check:
# 1. Request URL
# 2. Request Headers (Authorization, Origin)
# 3. Response Headers (CORS headers)
# 4. Response Body (error message)
```

### 📊 Check Service Health

```bash
# Health endpoint
curl http://localhost:8000/healthz | jq

# Readiness endpoint
curl http://localhost:8000/readyz | jq

# Both should return status: ok/ready
```

### 🔗 Test Direct Database Query

```python
# python3
import asyncio
from sqlalchemy import text
from app.core.database import engine

async def test():
    async with engine.begin() as conn:
        result = await conn.execute(text("SELECT 1"))
        print(result.fetchall())

asyncio.run(test())
```

---

## Verification Checklist

بررسی نقطه‌ای قبل از troubleshooting پیشرفته:

- [ ] `.env` file وجود دارد و کامل است
- [ ] Docker services در حال اجرا هستند
- [ ] Database URL صحیح است
- [ ] FRONTEND_URL برای CORS صحیح است
- [ ] Redis password مطابقت دارد
- [ ] PORT 5432, 6379, 8000, 3000 آزاد هستند
- [ ] Migrations اجرا شده‌اند
- [ ] Frontend `.env.local` دارای NEXT_PUBLIC_API_URL است

---

## نیاز به کمک بیشتر؟

```bash
# اجرای verification script
python3 scripts/verify_system_connections.py

# View comprehensive logs
docker-compose logs -f

# Health check
python3 scripts/health_check.py
```

---

**آخرین بروزرسانی**: 2026-06-09

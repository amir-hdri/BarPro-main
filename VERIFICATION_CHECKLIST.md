# ✅ Comprehensive Connection Verification Checklist

## Pre-Deployment Verification

### 📋 Environment Configuration

- [ ] **Root .env file exists**
  ```bash
  ls -la .env
  ```
  
- [ ] **Required environment variables**
  ```bash
  grep -E "JWT_SECRET|DRIVER_ENCRYPTION_KEY|DATABASE_URL|REDIS_URL" .env
  ```
  
- [ ] **Frontend .env.local configured**
  ```bash
  cat apps/web/.env.local
  # Should contain: NEXT_PUBLIC_API_URL=http://127.0.0.1:8000
  ```

---

### 🗄️ Database Connection

#### Configuration Files
- [ ] `app/core/database.py` contains:
  - [ ] `pool_size = 20`
  - [ ] `max_overflow = 10`
  - [ ] `pool_timeout = 30`
  - [ ] `pool_recycle = 3600`
  - [ ] `pool_pre_ping = True`

#### Connection URL
- [ ] DATABASE_URL format: `postgresql+asyncpg://user:pass@host:5432/dbname`
- [ ] Hostname resolves correctly (ping postgres container)
- [ ] Port 5432 accessible from backend container

#### Docker Setup
- [ ] PostgreSQL service in docker-compose.yml
  ```yaml
  postgres:
    image: postgres:16
    healthcheck:
      test: ['CMD-SHELL', 'pg_isready -U postgres']
  ```
  
- [ ] Health check passes
  ```bash
  docker-compose ps | grep postgres
  # Status should be "healthy"
  ```

#### Migrations
- [ ] `alembic.ini` present and configured
- [ ] `alembic/versions/` contains migration files
- [ ] Current migration state: `alembic current`
- [ ] No pending migrations: `alembic upgrade head`

---

### 🔌 Redis Connection

#### Configuration
- [ ] REDIS_URL in .env
- [ ] REDIS_PASSWORD set
- [ ] Redis connection URL format: `redis://:PASSWORD@host:6379/0`

#### Docker Setup
- [ ] Redis service in docker-compose.yml
  ```yaml
  redis:
    image: redis:7
    command: ["redis-server", "--appendonly", "yes", "--requirepass", "${REDIS_PASSWORD}"]
  ```

#### Connectivity
- [ ] Health check passes
  ```bash
  docker-compose ps | grep redis
  # Status should be "healthy"
  ```

#### Test Connection
- [ ] Direct connection test
  ```bash
  redis-cli -h localhost -p 6379 -a PASSWORD ping
  # Should return PONG
  ```

---

### 🌐 Frontend-Backend Communication

#### CORS Configuration

- [ ] FRONTEND_URL set in backend .env
  ```bash
  grep FRONTEND_URL .env
  ```

- [ ] Backend CORS middleware configured
  - [ ] `app/main.py` has `CORSMiddleware`
  - [ ] Allowed origins include frontend URL
  - [ ] `allow_credentials=True`
  - [ ] Methods include: GET, POST, PUT, PATCH, DELETE, OPTIONS

#### Frontend API Configuration

- [ ] `apps/web/.env.local` contains NEXT_PUBLIC_API_URL
- [ ] `apps/web/src/lib/api.ts` exists
- [ ] axios client properly configured
  - [ ] baseURL set from environment
  - [ ] withCredentials enabled
  - [ ] Auth interceptor implemented

#### Network Connectivity

- [ ] Backend accessible from frontend container
  ```bash
  curl http://backend:8000/healthz
  ```

- [ ] Frontend accessible from browser
  ```bash
  curl http://localhost:3000
  ```

- [ ] CORS headers present
  ```bash
  curl -H "Origin: http://localhost:3000" http://localhost:8000/healthz -v
  # Should have Access-Control-Allow-Origin header
  ```

---

### 🔐 Authentication & JWT

#### Configuration
- [ ] JWT_SECRET set and > 32 characters
  ```bash
  grep JWT_SECRET .env | wc -c  # Should be > 32
  ```

- [ ] JWT algorithm configured (default: HS256)

#### Token Management
- [ ] Frontend stores token in localStorage
  - [ ] `utcms_auth_token` key exists
  - [ ] Token persists after page reload

- [ ] Backend validates tokens
  - [ ] `app/api/` routes have JWT dependency
  - [ ] 401 response for invalid tokens

#### Test Authentication
- [ ] Login endpoint works
  ```bash
  curl -X POST http://localhost:8000/api/v1/auth/login \
    -H "Content-Type: application/json" \
    -d '{"username":"test","password":"test"}'
  ```

- [ ] Protected endpoint requires token
  ```bash
  curl http://localhost:8000/api/v1/waybills  # Should fail
  curl -H "Authorization: Bearer TOKEN" \
    http://localhost:8000/api/v1/waybills  # Should work
  ```

---

### 📦 Docker Orchestration

#### Services Status
- [ ] PostgreSQL running and healthy
  ```bash
  docker-compose ps postgres
  ```

- [ ] Redis running and healthy
  ```bash
  docker-compose ps redis
  ```

- [ ] Backend running
  ```bash
  docker-compose ps backend
  ```

- [ ] Frontend running
  ```bash
  docker-compose ps frontend
  ```

#### Service Dependencies
- [ ] Backend starts after PostgreSQL and Redis
- [ ] Frontend accessible through Nginx
- [ ] Network isolation (platform network)
- [ ] Volume persistence working

#### Port Mapping
- [ ] PostgreSQL: 5432:5432
- [ ] Redis: 6379:6379
- [ ] Backend: 8000:8000
- [ ] Frontend: 3000:3000
- [ ] Nginx: 80:80 (and 443:443 for HTTPS)

---

### 🔍 API Endpoints

#### Health Check Endpoints
- [ ] `/healthz` returns 200 OK
  ```bash
  curl http://localhost:8000/healthz
  # {"status": "ok"}
  ```

- [ ] `/readyz` returns complete readiness check
  ```bash
  curl http://localhost:8000/readyz
  # {
  #   "database": "ok",
  #   "redis": "ok",
  #   "captcha_model": "ok",
  #   ...
  # }
  ```

#### Core Endpoints
- [ ] Waybill endpoints mounted
  - [ ] GET `/waybill/...`
  - [ ] POST `/waybill/create`

- [ ] Management endpoints mounted
  - [ ] GET `/api/v1/management/...`
  - [ ] POST `/api/v1/management/...`

- [ ] Auth endpoints mounted
  - [ ] POST `/api/v1/auth/login`
  - [ ] POST `/api/v1/auth/logout`

---

### 📊 Monitoring & Logging

#### Request Tracing
- [ ] X-Request-ID header in responses
- [ ] Correlation ID tracking enabled
- [ ] Request timing logged

#### Logging Configuration
- [ ] LOG_LEVEL set (DEBUG/INFO/WARNING/ERROR)
- [ ] Logs visible in docker-compose logs
  ```bash
  docker-compose logs -f backend
  ```

#### Prometheus Metrics
- [ ] Prometheus service running
  ```bash
  docker-compose ps prometheus
  ```

- [ ] Metrics endpoint working
  ```bash
  curl http://localhost:9090
  ```

---

### 🧪 Testing

#### Unit Tests
- [ ] Database tests pass
  ```bash
  pytest tests/test_system_health.py -v
  ```

- [ ] API tests pass
  ```bash
  pytest tests/test_api.py -v
  ```

#### Integration Tests
- [ ] Multi-tenant tests pass
  ```bash
  pytest tests/test_multitenant_*.py -v
  ```

- [ ] Health checks pass
  ```bash
  python3 scripts/health_check.py
  ```

#### Verification Scripts
- [ ] Connection verification script
  ```bash
  python3 scripts/verify_system_connections.py
  ```

---

### 🔒 Security Checks

#### Secrets Management
- [ ] No hardcoded credentials in code
- [ ] All secrets in .env file
- [ ] .env file in .gitignore
- [ ] .env.example shows template only

#### CORS & Origin Validation
- [ ] CORS only allows known origins
- [ ] Credentials require explicit allow
- [ ] Preflight requests handled correctly

#### Data Isolation
- [ ] Multi-tenancy enforced
- [ ] client_id checked on all queries
- [ ] No cross-tenant data access possible

#### Encryption
- [ ] Password hashing with bcrypt
- [ ] Sensitive fields encrypted
- [ ] JWT tokens signed with secret

---

### 📈 Performance & Scalability

#### Connection Pooling
- [ ] Pool utilization monitored
- [ ] No connection exhaustion errors
- [ ] Health check working (pool_pre_ping)

#### Caching
- [ ] Redis properly caching data
- [ ] Cache invalidation working
- [ ] No stale cache issues

#### Rate Limiting
- [ ] Rate limits enforced on public endpoints
- [ ] 429 response when limit exceeded
- [ ] Headers show remaining requests

---

## 🚀 Quick Start Verification

### One-Command Verification
```bash
# Run all checks
python3 scripts/verify_system_connections.py

# Expected output: ✅ All checks passed
```

### Docker-Based Verification
```bash
# Start all services
docker-compose up -d

# Check all services healthy
docker-compose ps

# Expected: All Status = "Up" or "healthy"
```

### API Verification
```bash
# Test health
curl http://localhost:8000/healthz

# Test readiness
curl http://localhost:8000/readyz

# Test CORS
curl -H "Origin: http://localhost:3000" \
  -X OPTIONS http://localhost:8000/healthz -v
```

### Database Verification
```bash
# Connect to database
psql postgresql://postgres:PASSWORD@localhost:5432/utcms_rpa

# Run query
SELECT * FROM clients LIMIT 1;
```

---

## 📝 Sign-Off Checklist

When all boxes are checked, the system is ready:

- [ ] All environment variables configured
- [ ] Database connectivity verified
- [ ] Redis connectivity verified
- [ ] CORS properly configured
- [ ] JWT authentication working
- [ ] API endpoints responding
- [ ] Frontend connecting to backend
- [ ] WebSocket connections working
- [ ] Health checks passing
- [ ] All tests passing
- [ ] No errors in logs
- [ ] Performance metrics acceptable

---

## 🆘 If Any Checks Fail

1. **Refer to TROUBLESHOOTING.md** for specific issue
2. **Check logs**: `docker-compose logs -f [service]`
3. **Run verification script**: `python3 scripts/verify_system_connections.py`
4. **Review ARCHITECTURE.md** for connection flow
5. **Check SYSTEM_HEALTH_REPORT.md** for detailed analysis

---

## 📞 Support Resources

- 📖 **Documentation**: `SYSTEM_HEALTH_REPORT.md`
- 🏗️ **Architecture**: `ARCHITECTURE.md`
- 🛠️ **Troubleshooting**: `TROUBLESHOOTING.md`
- ✅ **Verification**: `scripts/verify_system_connections.py`
- 🏥 **Health Check**: `scripts/health_check.py`

---

**Version**: 2.0.0  
**Last Updated**: 2026-06-09  
**Status**: ✅ Production Ready

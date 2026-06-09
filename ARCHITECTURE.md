# 🏗️ معماری و شماتیک سیستم BarPro

## 1. معماری کلی سیستم

```
┌─────────────────────────────────────────────────────────────────┐
│                    CLIENT BROWSER                               │
│                                                                  │
│  ┌────────────────────────────────────────────────────────────┐ │
│  │           Next.js Frontend (Port 3000)                    │ │
│  │  • React 19 + TypeScript                                   │ │
│  │  • Tailwind CSS + Heroicons                                │ │
│  │  • React Query + Axios                                     │ │
│  │  • React Hook Form + Zod Validation                        │ │
│  └────────────────────────────────────────────────────────────┘ │
└────────────────┬────────────────────────────────────────────────┘
                 │
                 │ CORS + HTTPS
                 │ API Calls (http://localhost:8000)
                 │
        ┌────────▼───────────┐
        │   Nginx (80/443)    │
        │   Reverse Proxy     │
        └────────┬───────────┘
                 │
┌────────────────┴──────────────────────────────────────────┐
│                                                             │
│  ┌──────────────────────────────────────────────────────┐ │
│  │         FastAPI Backend (Port 8000)                 │ │
│  │  ┌───────────────────────────────────────────────┐  │ │
│  │  │  • Request Middleware (tracing, auth)        │  │ │
│  │  │  • CORS Middleware (allow origins)           │  │ │
│  │  │  • Rate Limiter (public/auth endpoints)      │  │ │
│  │  └───────────────────────────────────────────────┘  │ │
│  │                       │                              │ │
│  │  ┌──────────────────┬─┴────────────┬──────────────┐ │ │
│  │  │                  │              │              │ │ │
│  │  ▼                  ▼              ▼              ▼ │ │
│  │ ┌────────┐   ┌──────────┐   ┌──────────┐   ┌────────┐
│  │ │Waybill │   │Management│   │Admin     │   │System  │
│  │ │Routes  │   │Routes    │   │Routes    │   │Routes  │
│  │ └────────┘   └──────────┘   └──────────┘   └────────┘
│  │                                                       │
│  └─────────────────────┬─────────────────────────────────┘
│                        │
│    ┌───────────────────┼───────────────────┐
│    │                   │                   │
│    ▼                   ▼                   ▼
│  ┌─────────┐    ┌────────────┐     ┌───────────┐
│  │ Services│    │ Automation │     │ Monitoring│
│  │(Business│    │ Engine(RPA)│     │(Prometheus)
│  │ Logic)  │    │            │     │           │
│  └─────────┘    └────────────┘     └───────────┘
└────┬────────────────┬──────────────────┬───┬───────┘
     │                │                  │   │
     ▼                ▼                  ▼   ▼
┌──────────────┐ ┌──────────────┐ ┌──────────────┐
│ PostgreSQL   │ │ Redis        │ │ Playwright   │
│ (Database)   │ │ (Cache/Queue)│ │ (Browser)    │
│ Port 5432    │ │ Port 6379    │ │              │
└──────────────┘ └──────────────┘ └──────────────┘
```

---

## 2. جریان درخواست (Request Flow)

```
1. FRONTEND REQUEST
   ┌─────────────────────────────────────────┐
   │ Browser Action                          │
   │ (Click, Form Submit, etc.)              │
   └────────────┬────────────────────────────┘
                │
   2. AXIOS CLIENT
   ┌────────────▼────────────────────────────┐
   │ axios.post('/api/v1/waybills', data)    │
   │ Headers:                                 │
   │ - Authorization: Bearer JWT             │
   │ - Content-Type: application/json        │
   │ - X-Request-ID: uuid                    │
   └────────────┬────────────────────────────┘
                │
   3. BROWSER SECURITY
   ┌────────────▼────────────────────────────┐
   │ CORS Pre-flight Check (OPTIONS)         │
   │ Origin: http://localhost:3000           │
   │ Verify Backend allows this origin       │
   └────────────┬────────────────────────────┘
                │
   4. FASTAPI MIDDLEWARE
   ┌────────────▼────────────────────────────┐
   │ Request Context Middleware              │
   │ ├─ Generate/Extract Request ID          │
   │ ├─ Bind Execution Context               │
   │ ├─ Rate Limiting Check                  │
   │ └─ Trace Span Creation                  │
   └────────────┬────────────────────────────┘
                │
   5. ROUTING & VALIDATION
   ┌────────────▼────────────────────────────┐
   │ Match API Route                         │
   │ Parse Request Body (Pydantic)           │
   │ Validate Input Schema                   │
   └────────────┬────────────────────────────┘
                │
   6. BUSINESS LOGIC
   ┌────────────▼────────────────────────────┐
   │ Service Layer                           │
   │ ├─ Auth Check (JWT validation)          │
   │ ├─ Tenant Isolation Check               │
   │ ├─ Business Rules Validation            │
   │ └─ Task/Operation Processing            │
   └────────────┬────────────────────────────┘
                │
   7. DATABASE INTERACTION
   ┌────────────▼────────────────────────────┐
   │ Get Session from Pool                   │
   │ Execute Query (async)                   │
   │ ├─ Connection Health Check              │
   │ ├─ Transaction Begin                    │
   │ ├─ Execute SQL                          │
   │ ├─ Commit/Rollback                      │
   │ └─ Return to Pool                       │
   └────────────┬────────────────────────────┘
                │
   8. RESPONSE
   ┌────────────▼────────────────────────────┐
   │ JSON Response (Pydantic schema)         │
   │ Status: 200 OK                          │
   │ Headers:                                 │
   │ - X-Request-ID: uuid                    │
   │ - Content-Type: application/json        │
   └────────────┬────────────────────────────┘
                │
   9. FRONTEND HANDLING
   ┌────────────▼────────────────────────────┐
   │ Axios Response Interceptor              │
   │ Update React Query Cache                │
   │ Update UI Component State               │
   │ Show Success/Error Toast                │
   └─────────────────────────────────────────┘
```

---

## 3. Connection Pooling Flow

```
┌─────────────────────────────────────────────────────────┐
│         SQLAlchemy Connection Pool                       │
│         (pool_size=20, max_overflow=10)                  │
│                                                          │
│  ┌────────────────────────────────────────────────────┐ │
│  │  Idle Connections (20)                            │ │
│  │  [conn] [conn] [conn] [conn] [conn] ...           │ │
│  │    #1     #2     #3     #4     #5                 │ │
│  └────────────────────────────────────────────────────┘ │
│                                                          │
│  When request arrives:                                  │
│  1. pool_pre_ping=True → SELECT 1 (health check)       │
│  2. If healthy → give to request                       │
│  3. If not healthy → discard + create new              │
│                                                          │
│  ┌────────────────────────────────────────────────────┐ │
│  │  When pool exhausted (all 20 in use)              │ │
│  │  1. Check max_overflow (10 additional allowed)    │ │
│  │  2. Create temporary connection                   │ │
│  │  3. pool_timeout=30s → wait for available         │ │
│  │  4. If timeout exceeded → raise exception         │ │
│  │                                                    │ │
│  │  pool_recycle=3600 → recycle connections every   │ │
│  │  hour to avoid stale connections                 │ │
│  └────────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────┘
```

---

## 4. Multi-Tenancy Data Isolation

```
┌──────────────────────────────────────────────────┐
│          PostgreSQL Database                     │
│        (utcms_rpa)                              │
│                                                  │
│  ┌──────────────────────────────────────────┐  │
│  │     Tenant 1 (client_id=1)              │  │
│  │                                          │  │
│  │  clients → id=1, client_code='client1' │  │
│  │  drivers → 5 drivers (client_id=1)     │  │
│  │  waybill_tasks → 100 tasks (client1)   │  │
│  │  reports → 50 reports (client1)        │  │
│  │                                          │  │
│  │  Query Filter: WHERE client_id = 1     │  │
│  └──────────────────────────────────────────┘  │
│                                                  │
│  ┌──────────────────────────────────────────┐  │
│  │     Tenant 2 (client_id=2)              │  │
│  │                                          │  │
│  │  clients → id=2, client_code='client2' │  │
│  │  drivers → 3 drivers (client_id=2)     │  │
│  │  waybill_tasks → 50 tasks (client2)    │  │
│  │  reports → 30 reports (client2)        │  │
│  │                                          │  │
│  │  Query Filter: WHERE client_id = 2     │  │
│  └──────────────────────────────────────────┘  │
│                                                  │
│  [Complete isolation at database level]         │
│  [Row-level security via queries]               │
│  [No accidental data leakage possible]           │
└──────────────────────────────────────────────────┘
```

---

## 5. Authentication Flow

```
┌────────────────────────────────────────┐
│  LOGIN REQUEST                         │
│  POST /api/v1/auth/login               │
│  Body: {username, password}            │
└────────────┬───────────────────────────┘
             │
   ┌─────────▼────────────┐
   │ Validate Credentials │
   │ Query DB for Client  │
   │ bcrypt.verify() pwd  │
   └─────────┬────────────┘
             │
   ┌─────────▼────────────┐
   │ Create JWT Token     │
   │ Payload:             │
   │ - sub: client_id     │
   │ - client_code        │
   │ - iat: now           │
   │ - exp: now + 24h     │
   │ Sign with JWT_SECRET │
   └─────────┬────────────┘
             │
   ┌─────────▼────────────────────────┐
   │ Response                          │
   │ {                                 │
   │   access_token: "eyJxxx...",      │
   │   token_type: "bearer",           │
   │   user: { id, name, ... }         │
   │ }                                 │
   └─────────┬────────────────────────┘
             │
   ┌─────────▼────────────────────────┐
   │ Frontend Store Token              │
   │ localStorage.setItem(              │
   │   'utcms_auth_token',             │
   │   access_token                    │
   │ )                                 │
   └─────────┬────────────────────────┘
             │
   ┌─────────▼────────────────────────┐
   │ Subsequent Requests               │
   │ Headers: {                        │
   │   Authorization: Bearer eyJxxx... │
   │ }                                 │
   └────────────────────────────────────┘
```

---

## 6. WebSocket Connection for Real-time Updates

```
Frontend                              Backend
  │                                     │
  │ ws://localhost:8000/ws/job/123      │
  │────────────────────────────────────>│
  │                                     │
  │ (WebSocket Handshake)               │
  │<────────────────────────────────────│
  │                                     │
  │ (Connected)                         │
  │                                     │
  │ (RPA Task Running)                  │
  │                                     │
  │                                  [Step 1: Login]
  │<────────────────────────────────────│
  │  {type: "status_update",            │
  │   step: "login",                    │
  │   progress: 10%}                    │
  │                                  [Step 2: Fill Form]
  │<────────────────────────────────────│
  │  {type: "status_update",            │
  │   step: "fill_form",                │
  │   progress: 50%}                    │
  │                                  [Step 3: Submit]
  │<────────────────────────────────────│
  │  {type: "status_update",            │
  │   step: "submit",                   │
  │   progress: 90%}                    │
  │                                  [Complete]
  │<────────────────────────────────────│
  │  {type: "completed",                │
  │   result: "success",                │
  │   tracking_number: "123456"}        │
  │                                     │
  │ Close WebSocket Connection          │
  │ (cleanup)                           │
```

---

## 7. Performance & Scalability

```
┌─────────────────────────────────────────────────┐
│            Load Balancing Strategy              │
│                                                 │
│  1. CONNECTION POOLING                          │
│     ├─ Base Pool: 20 connections               │
│     ├─ Overflow: +10 during peaks              │
│     ├─ Health Check: every request             │
│     └─ Recycling: every 3600 seconds           │
│                                                 │
│  2. CACHING (Redis)                             │
│     ├─ Session cache (TTL: 24h)                │
│     ├─ Task queue (processing tasks)           │
│     ├─ Rate limit counters                     │
│     └─ Distributed lock management             │
│                                                 │
│  3. RATE LIMITING                               │
│     ├─ Public endpoints: 10/min                │
│     ├─ Auth endpoints: 5/min                   │
│     ├─ User endpoints: 100/min                 │
│     └─ Admin endpoints: 1000/min               │
│                                                 │
│  4. CELERY WORKERS                              │
│     ├─ Background task processing              │
│     ├─ RPA automation execution                │
│     ├─ Report generation                       │
│     └─ Email/notification sending              │
└─────────────────────────────────────────────────┘
```

---

## 8. Error & Recovery Flow

```
┌──────────────────────────────────┐
│   Request Processing             │
│                                  │
│   try:                           │
│     ├─ Validate Input           │
│     ├─ Check Auth               │
│     ├─ Load Data                │
│     ├─ Process Business Logic   │
│     ├─ Commit Transaction       │
│     └─ Return Response          │
│   except Exception as e:        │
│     ├─ Log Error with Context   │
│     ├─ Rollback Transaction     │
│     ├─ Return Error Response    │
│     └─ Close Session            │
│   finally:                      │
│     └─ Cleanup Resources        │
└──────────────────────────────────┘

Error Handling Layers:
┌──────────────────────────────┐
│ 1. Input Validation (Pydantic)
│    → 422 Unprocessable Entity
│
│ 2. Authentication (JWT)
│    → 401 Unauthorized
│
│ 3. Authorization (Tenant)
│    → 403 Forbidden
│
│ 4. Business Logic
│    → 400/409 Custom Error
│
│ 5. Database
│    → Retry with backoff
│    → 503 Service Unavailable
│
│ 6. Unexpected
│    → 500 Internal Server Error
│    → Alert monitoring system
└──────────────────────────────┘
```

---

## 9. Security Layers

```
┌─────────────────────────────────────────────────┐
│           SECURITY ARCHITECTURE                 │
│                                                 │
│  1. TRANSPORT SECURITY                          │
│     ├─ HTTPS/WSS (in production)               │
│     ├─ TLS 1.3+                                 │
│     └─ Certificate validation                   │
│                                                 │
│  2. AUTHENTICATION                              │
│     ├─ JWT tokens (HS256)                       │
│     ├─ Token expiration (24h)                   │
│     ├─ Password hashing (bcrypt)                │
│     └─ Refresh token rotation                   │
│                                                 │
│  3. AUTHORIZATION                               │
│     ├─ Multi-tenancy enforcement                │
│     ├─ Row-level security (client_id check)    │
│     ├─ Role-based access (admin/user)           │
│     └─ Rate limiting by user                    │
│                                                 │
│  4. DATA PROTECTION                             │
│     ├─ Database encryption (sensitive fields)  │
│     ├─ Password field hashing                   │
│     ├─ Secrets in environment                   │
│     └─ No hardcoded credentials                 │
│                                                 │
│  5. INPUT VALIDATION                            │
│     ├─ Pydantic schema validation               │
│     ├─ SQL injection prevention (parameterized)│
│     ├─ XSS prevention (no HTML in JSON)         │
│     └─ CORS policy enforcement                  │
│                                                 │
│  6. MONITORING                                  │
│     ├─ Request logging & tracing                │
│     ├─ Error tracking                           │
│     ├─ Performance monitoring                   │
│     └─ Alert on suspicious activity             │
└─────────────────────────────────────────────────┘
```

---

## 11. تاب‌آوری و بازیابی هوشمند (System Resilience)

### 11.1 بازیابی تسک‌های متوقف شده
سیستم مجهز به یک ناظر هوشمند (`RPASchedulerService`) است که به صورت دوره‌ای (هر ۵ دقیقه) وضعیت تمامی تسک‌ها را بررسی می‌کند:
- **تایم‌اوت صف (QUEUED):** اگر تسکی بیش از ۱۵ دقیقه در صف بماند و توسط هیچ کارگری برداشته نشود، سیستم آن را بازیابی کرده و برای تلاش مجدد آماده می‌کند.
- **تایم‌اوت پردازش (IN_PROGRESS):** اگر فرآیند پردازش یک تسک بیش از ۳۰ دقیقه طول بکشد (نشانه احتمالی کرش کارگر یا قطع شبکه)، سیستم به صورت خودکار وضعیت آن را ریست کرده و از بن‌بست خارج می‌کند.

### 11.2 لایه‌های محافظتی RPA
تمامی سرویس‌های خودکارسازی (`RPAAuthService` و `RPASubmitService`) دارای بلوک‌های مدیریت استثنای سراسری هستند:
- **Atomic State Reset:** در صورت بروز هرگونه خطای پیش‌بینی نشده در مرورگر یا کد خودکارسازی، وضعیت درایور و تسک بلافاصله به حالت امن (READY یا FAILED) بازگردانده می‌شود.
- **Cleanup on Crash:** تمامی منابع مرورگر (Context, Page) حتی در صورت بروز خطا به صورت اجباری بسته می‌شوند تا از نشت حافظه (Memory Leak) جلوگیری شود.

---

## 12. نکات نهایی و نگهداری


```
User Action
    │
    ├─ Is it a real-time update?
    │  └─ YES → WebSocket Connection
    │           (ws://localhost:8000/ws/...)
    │
    └─ Is it a data mutation (POST/PUT/DELETE)?
       ├─ YES → Check if heavy operation
       │        ├─ YES → Celery Task Queue
       │        │        (async processing)
       │        │
       │        └─ NO → Direct API Call
       │               (sync response)
       │
       └─ NO → Direct API Call (GET)
               └─ Cache Check (Redis)
                  ├─ HIT → Return from cache
                  └─ MISS → Query DB, cache result
```

---

**نسخه**: 2.0.0  
**آخرین بروزرسانی**: 2026-06-09  
**معمار سیستم**: Microservices-based Multi-tenant RPA Platform

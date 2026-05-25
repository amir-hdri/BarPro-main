# نمودار معماری سیستم Multi-Tenant

## 📐 معماری کلی

```
┌─────────────────────────────────────────────────────────────────┐
│                        UTCMS Automation SaaS                     │
│                         Multi-Tenant System                      │
└─────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────┐
│                          USER LAYERS                             │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  ┌──────────────┐                                               │
│  │ Master Admin │  ← مدیریت کل سیستم                           │
│  └──────┬───────┘                                               │
│         │                                                        │
│         ├─── مدیریت Clients                                     │
│         ├─── تنظیم محدودیت‌ها                                  │
│         └─── مشاهده تمام داده‌ها                               │
│                                                                  │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐         │
│  │  Client 1    │  │  Client 2    │  │  Client N    │         │
│  │ (Tenant 1)   │  │ (Tenant 2)   │  │ (Tenant N)   │         │
│  └──────┬───────┘  └──────┬───────┘  └──────┬───────┘         │
│         │                  │                  │                  │
│    ┌────┴────┐        ┌───┴────┐        ┌───┴────┐            │
│    │ Driver  │        │ Driver │        │ Driver │            │
│    │ Driver  │        │ Driver │        │ Driver │            │
│    └─────────┘        └────────┘        └────────┘            │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────┐
│                        API LAYER (FastAPI)                       │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  ┌────────────────┐  ┌────────────────┐  ┌────────────────┐   │
│  │ Auth Endpoints │  │ Client APIs    │  │ Admin APIs     │   │
│  ├────────────────┤  ├────────────────┤  ├────────────────┤   │
│  │ /auth/register │  │ /drivers       │  │ /admin/clients │   │
│  │ /auth/login    │  │ /jobs          │  │ /admin/drivers │   │
│  │ /auth/me       │  │ /stats         │  │ /admin/stats   │   │
│  └────────────────┘  └────────────────┘  └────────────────┘   │
│                                                                  │
│  ┌──────────────────────────────────────────────────────────┐  │
│  │              JWT Authentication Middleware                │  │
│  │         (Tenant Isolation + Authorization)                │  │
│  └──────────────────────────────────────────────────────────┘  │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────┐
│                      SERVICE LAYER                               │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐         │
│  │   Client     │  │   Driver     │  │  Waybill     │         │
│  │   Service    │  │   Service    │  │   Service    │         │
│  └──────┬───────┘  └──────┬───────┘  └──────┬───────┘         │
│         │                  │                  │                  │
│         └──────────────────┴──────────────────┘                 │
│                            │                                     │
│                  ┌─────────▼─────────┐                          │
│                  │  RPA Automation   │                          │
│                  │  ├─ Dispatcher    │                          │
│                  │  ├─ Scheduler     │                          │
│                  │  ├─ Runtime       │                          │
│                  │  └─ Browser Pool  │                          │
│                  └───────────────────┘                          │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────┐
│                      DATA LAYER                                  │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  ┌──────────────────────────────────────────────────────────┐  │
│  │                    PostgreSQL Database                    │  │
│  ├──────────────────────────────────────────────────────────┤  │
│  │                                                           │  │
│  │  ┌─────────┐  ┌─────────┐  ┌──────────────┐            │  │
│  │  │ clients │  │ drivers │  │ waybill_jobs │            │  │
│  │  ├─────────┤  ├─────────┤  ├──────────────┤            │  │
│  │  │ id      │  │ id      │  │ id           │            │  │
│  │  │ code    │  │ client_id│ │ client_id    │            │  │
│  │  │ email   │  │ nat_code│  │ driver_id    │            │  │
│  │  │ status  │  │ utcms_* │  │ payload      │            │  │
│  │  │ limits  │  │ status  │  │ status       │            │  │
│  │  └─────────┘  └─────────┘  └──────────────┘            │  │
│  │                                                           │  │
│  │  ┌──────────────┐  ┌──────────────┐                     │  │
│  │  │ task_logs    │  │ domain_events│                     │  │
│  │  └──────────────┘  └──────────────┘                     │  │
│  │                                                           │  │
│  └──────────────────────────────────────────────────────────┘  │
│                                                                  │
│  ┌──────────────────────────────────────────────────────────┐  │
│  │                      Redis Cache                          │  │
│  ├──────────────────────────────────────────────────────────┤  │
│  │  • Session Storage                                        │  │
│  │  • Rate Limiting                                          │  │
│  │  • Job Queue                                              │  │
│  │  • Runtime State                                          │  │
│  └──────────────────────────────────────────────────────────┘  │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

---

## 🔐 Data Isolation (جداسازی داده)

```
┌─────────────────────────────────────────────────────────────────┐
│                    Tenant Isolation Pattern                      │
└─────────────────────────────────────────────────────────────────┘

Client 1 (ID: 1)                    Client 2 (ID: 2)
├── Drivers                         ├── Drivers
│   ├── Driver A (client_id=1)     │   ├── Driver X (client_id=2)
│   └── Driver B (client_id=1)     │   └── Driver Y (client_id=2)
│                                   │
├── Jobs                            ├── Jobs
│   ├── Job 001 (client_id=1)      │   ├── Job 101 (client_id=2)
│   └── Job 002 (client_id=1)      │   └── Job 102 (client_id=2)
│                                   │
└── Logs                            └── Logs
    ├── Log 1 (client_id=1)             ├── Log 1 (client_id=2)
    └── Log 2 (client_id=1)             └── Log 2 (client_id=2)

❌ Client 1 CANNOT access Client 2's data
❌ Client 2 CANNOT access Client 1's data
✅ Master Admin CAN access ALL data
```

---

## 🔄 Request Flow

```
┌─────────────────────────────────────────────────────────────────┐
│                    Typical API Request Flow                      │
└─────────────────────────────────────────────────────────────────┘

1. Client Request
   │
   ├─→ POST /api/v1/jobs
   │   Headers: Authorization: Bearer <jwt_token>
   │   Body: { driver_national_code, origin, destination, ... }
   │
2. Authentication Middleware
   │
   ├─→ Verify JWT Token
   │   ├─→ Extract client_id from token
   │   └─→ Load Client from database
   │
3. Authorization Check
   │
   ├─→ Check client.status == "active"
   ├─→ Check daily_limit not exceeded
   └─→ Check concurrent_tasks not exceeded
   │
4. Service Layer
   │
   ├─→ WaybillJobService.create_job()
   │   ├─→ Validate driver belongs to client
   │   │   WHERE driver.client_id = current_client.id
   │   │
   │   ├─→ Create job with client_id
   │   │   INSERT INTO waybill_jobs (client_id, ...)
   │   │
   │   └─→ Dispatch to RPA
   │
5. RPA Automation
   │
   ├─→ Load driver credentials (encrypted)
   ├─→ Login to UTCMS
   ├─→ Fill waybill form
   └─→ Submit and track
   │
6. Response
   │
   └─→ Return job_id and status to client
```

---

## 🗄️ Database Schema

```
┌─────────────────────────────────────────────────────────────────┐
│                      Entity Relationships                        │
└─────────────────────────────────────────────────────────────────┘

┌──────────────┐
│   clients    │
│──────────────│
│ id (PK)      │
│ client_code  │◄─────────┐
│ email        │          │
│ status       │          │
│ max_drivers  │          │
│ max_tasks    │          │
└──────────────┘          │
                          │
                          │ 1:N
                          │
                ┌─────────┴────────┐
                │                  │
        ┌───────▼──────┐   ┌──────▼──────────┐
        │   drivers    │   │  waybill_jobs   │
        │──────────────│   │─────────────────│
        │ id (PK)      │   │ id (PK)         │
        │ client_id(FK)│   │ client_id (FK)  │
        │ national_code│   │ driver_id (FK)  │◄──┐
        │ utcms_user   │   │ job_id          │   │
        │ utcms_pass   │   │ status          │   │
        │ status       │   │ payload_json    │   │
        └──────────────┘   └─────────────────┘   │
                │                  │              │
                └──────────────────┘              │
                         1:N                      │
                                                  │
                                          ┌───────┴────────┐
                                          │  task_logs     │
                                          │────────────────│
                                          │ id (PK)        │
                                          │ job_id (FK)    │
                                          │ step           │
                                          │ status         │
                                          │ message        │
                                          └────────────────┘
```

---

## 🔒 Security Layers

```
┌─────────────────────────────────────────────────────────────────┐
│                      Security Architecture                       │
└─────────────────────────────────────────────────────────────────┘

Layer 1: Network
├── HTTPS/TLS
├── CORS Policy
└── Rate Limiting

Layer 2: Authentication
├── JWT Tokens (24h expiry)
├── bcrypt Password Hashing
└── Token Refresh

Layer 3: Authorization
├── Role-Based Access (Admin/Client)
├── Tenant Isolation (client_id filter)
└── Resource Ownership Verification

Layer 4: Data Protection
├── Password Encryption (Fernet)
├── Sensitive Data Masking
└── Audit Logging

Layer 5: Application
├── Input Validation (Pydantic)
├── SQL Injection Prevention (SQLModel)
└── XSS Protection
```

---

## 📊 Subscription Limits Flow

```
┌─────────────────────────────────────────────────────────────────┐
│                    Limit Enforcement Flow                        │
└─────────────────────────────────────────────────────────────────┘

Request: Create New Job
│
├─→ Check 1: Daily Limit
│   │
│   ├─→ Query: COUNT jobs WHERE client_id=X AND date=today
│   │
│   ├─→ IF count >= client.max_daily_tasks
│   │   └─→ REJECT: "Daily limit reached"
│   │
│   └─→ PASS
│
├─→ Check 2: Concurrent Tasks
│   │
│   ├─→ Query: COUNT jobs WHERE client_id=X AND status IN (pending, in_progress)
│   │
│   ├─→ IF count >= client.max_concurrent_tasks
│   │   └─→ QUEUE: "Wait for slot"
│   │
│   └─→ PASS
│
├─→ Check 3: Driver Limit
│   │
│   ├─→ Query: COUNT drivers WHERE client_id=X
│   │
│   ├─→ IF count >= client.max_drivers
│   │   └─→ REJECT: "Driver limit reached"
│   │
│   └─→ PASS
│
└─→ CREATE JOB
```

---

**تهیه‌کننده:** Claude AI Assistant  
**تاریخ:** 2025-05-01

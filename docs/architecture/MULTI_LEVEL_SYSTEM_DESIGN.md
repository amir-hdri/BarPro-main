> Legacy design note: this document is not the current database/API/state
> contract. Use docs/BARPRO_KNOWLEDGE_GRAPH.md and ARCHITECTURE.md.

# طراحی سیستم چندسطحی مدیریت کاربران و ثبت بارنامه
**تاریخ:** 2025-05-01  
**نسخه:** 3.0.0

---

## 📋 خلاصه اجرایی

طراحی یک سیستم Multi-Tenant با معماری سه‌سطحی:
1. **Super Admin** - مدیر کل سیستم
2. **Panel Users (Clients)** - کاربران با پنل اختصاصی
3. **Drivers** - رانندگان متعلق به هر کاربر

---

## 🏗️ معماری سیستم

### نقش‌ها و سطوح دسترسی

```
┌─────────────────────────────────────────────────────────┐
│                    SUPER ADMIN                          │
│  - مدیریت کامل کاربران                                 │
│  - تعیین سقف راننده/پلاک برای هر کاربر                 │
│  - مشاهده تمام گزارشات                                  │
│  - مدیریت تنظیمات سیستم                                 │
└────────────────────┬────────────────────────────────────┘
                     │
        ┌────────────┴────────────┐
        │                         │
┌───────▼────────┐       ┌───────▼────────┐
│  PANEL USER 1  │       │  PANEL USER 2  │
│  - پنل اختصاصی │       │  - پنل اختصاصی │
│  - مدیریت      │       │  - مدیریت      │
│    رانندگان    │       │    رانندگان    │
│  - ثبت بارنامه │       │  - ثبت بارنامه │
│  - گزارشات     │       │  - گزارشات     │
└───────┬────────┘       └───────┬────────┘
        │                        │
   ┌────┴────┐              ┌────┴────┐
   │         │              │         │
┌──▼──┐  ┌──▼──┐        ┌──▼──┐  ┌──▼──┐
│ DR1 │  │ DR2 │        │ DR3 │  │ DR4 │
└─────┘  └─────┘        └─────┘  └─────┘
```

---

## 📊 مدل داده‌ها (Database Schema)

### 1. جدول Super Admin

```sql
CREATE TABLE super_admins (
    id SERIAL PRIMARY KEY,
    username VARCHAR(50) UNIQUE NOT NULL,
    email VARCHAR(255) UNIQUE NOT NULL,
    hashed_password VARCHAR(255) NOT NULL,
    full_name VARCHAR(255),
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW(),
    last_login_at TIMESTAMP
);

-- ادمین پیش‌فرض
INSERT INTO super_admins (username, email, hashed_password, full_name)
VALUES ('admin', 'admin@utcms.local', '$2b$12$...', 'مدیر سیستم');
```

### 2. جدول Panel Users (Clients) - بهبود یافته

```sql
CREATE TABLE clients (
    id SERIAL PRIMARY KEY,
    client_code VARCHAR(50) UNIQUE NOT NULL,
    username VARCHAR(50) UNIQUE NOT NULL,
    email VARCHAR(255) UNIQUE NOT NULL,
    hashed_password VARCHAR(255) NOT NULL,
    
    -- اطلاعات شخصی
    full_name VARCHAR(255) NOT NULL,
    company_name VARCHAR(255),
    phone VARCHAR(20),
    national_code VARCHAR(10),
    
    -- وضعیت
    status VARCHAR(20) DEFAULT 'active', -- active, suspended, inactive
    is_active BOOLEAN DEFAULT TRUE,
    
    -- محدودیت‌ها (تعیین شده توسط Super Admin)
    max_drivers INTEGER DEFAULT 10,
    max_concurrent_tasks INTEGER DEFAULT 2,
    max_daily_tasks INTEGER DEFAULT 100,
    
    -- اشتراک
    subscription_plan_id INTEGER REFERENCES subscription_plans(id),
    subscription_start_date TIMESTAMP,
    subscription_end_date TIMESTAMP,
    
    -- متادیتا
    metadata_json TEXT,
    notes TEXT,
    
    -- تاریخچه
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW(),
    last_login_at TIMESTAMP,
    created_by_admin_id INTEGER REFERENCES super_admins(id)
);

CREATE INDEX idx_clients_status ON clients(status);
CREATE INDEX idx_clients_username ON clients(username);
CREATE INDEX idx_clients_email ON clients(email);
```

### 3. جدول Drivers - بهبود یافته

```sql
CREATE TABLE drivers (
    id SERIAL PRIMARY KEY,
    client_id INTEGER NOT NULL REFERENCES clients(id) ON DELETE CASCADE,
    
    -- اطلاعات شناسایی
    driver_national_code VARCHAR(10) NOT NULL,
    full_name VARCHAR(255) NOT NULL,
    phone VARCHAR(20),
    license_number VARCHAR(50),
    
    -- اطلاعات خودرو
    vehicle_plate VARCHAR(20) NOT NULL,
    vehicle_type VARCHAR(50),
    vehicle_model VARCHAR(100),
    
    -- اعتبارنامه UTCMS (رمزنگاری شده)
    utcms_username VARCHAR(100) NOT NULL,
    utcms_password_encrypted TEXT NOT NULL,
    
    -- وضعیت
    status VARCHAR(20) DEFAULT 'active', -- active, inactive, suspended
    runtime_status VARCHAR(40) DEFAULT 'idle', -- idle, busy, auth_required, error
    
    -- تنظیمات زمان‌بندی خودکار
    auto_schedule_enabled BOOLEAN DEFAULT FALSE,
    schedule_config JSONB, -- {"days": ["monday", "tuesday"], "time": "08:00", "frequency": "daily"}
    
    -- آمار
    total_waybills INTEGER DEFAULT 0,
    successful_waybills INTEGER DEFAULT 0,
    failed_waybills INTEGER DEFAULT 0,
    last_waybill_at TIMESTAMP,
    
    -- احراز هویت
    last_auth_at TIMESTAMP,
    last_session_expires_at TIMESTAMP,
    last_error_code VARCHAR(64),
    last_error_message TEXT,
    
    -- تاریخچه
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW(),
    
    UNIQUE(client_id, driver_national_code),
    UNIQUE(client_id, vehicle_plate)
);

CREATE INDEX idx_drivers_client_id ON drivers(client_id);
CREATE INDEX idx_drivers_status ON drivers(status);
CREATE INDEX idx_drivers_runtime_status ON drivers(runtime_status);
CREATE INDEX idx_drivers_auto_schedule ON drivers(auto_schedule_enabled) WHERE auto_schedule_enabled = TRUE;
```

### 4. جدول Subscription Plans

```sql
CREATE TABLE subscription_plans (
    id SERIAL PRIMARY KEY,
    name VARCHAR(50) NOT NULL,
    name_fa VARCHAR(100) NOT NULL,
    description TEXT,
    
    -- قیمت‌گذاری
    price_monthly DECIMAL(10,2),
    price_yearly DECIMAL(10,2),
    
    -- محدودیت‌ها
    max_drivers INTEGER NOT NULL,
    max_concurrent_tasks INTEGER NOT NULL,
    max_daily_tasks INTEGER NOT NULL,
    
    -- ویژگی‌ها
    features JSONB,
    
    -- وضعیت
    is_active BOOLEAN DEFAULT TRUE,
    is_public BOOLEAN DEFAULT TRUE,
    
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);

-- پلن‌های پیش‌فرض
INSERT INTO subscription_plans (name, name_fa, price_monthly, max_drivers, max_concurrent_tasks, max_daily_tasks, features)
VALUES 
    ('Basic', 'پایه', 500000, 5, 1, 50, '{"support": "email", "api_access": false}'),
    ('Pro', 'حرفه‌ای', 1500000, 20, 5, 200, '{"support": "priority", "api_access": true}'),
    ('Enterprise', 'سازمانی', 5000000, 100, 20, 1000, '{"support": "24/7", "api_access": true, "custom_features": true}');
```

### 5. جدول Waybill Jobs - بهبود یافته

```sql
-- جدول فعلی را حفظ می‌کنیم و فقط فیلدهای جدید اضافه می‌کنیم
ALTER TABLE waybill_jobs ADD COLUMN IF NOT EXISTS scheduled_by VARCHAR(20) DEFAULT 'manual'; -- manual, auto_schedule, api
ALTER TABLE waybill_jobs ADD COLUMN IF NOT EXISTS schedule_id INTEGER REFERENCES driver_schedules(id);
```

### 6. جدول Driver Schedules (جدید)

```sql
CREATE TABLE driver_schedules (
    id SERIAL PRIMARY KEY,
    driver_id INTEGER NOT NULL REFERENCES drivers(id) ON DELETE CASCADE,
    
    -- تنظیمات زمان‌بندی
    schedule_type VARCHAR(20) NOT NULL, -- daily, weekly, monthly, custom
    schedule_time TIME NOT NULL, -- زمان اجرا
    schedule_days JSONB, -- ["monday", "tuesday", ...]
    
    -- تنظیمات بارنامه
    waybill_template JSONB NOT NULL, -- قالب بارنامه
    
    -- وضعیت
    is_active BOOLEAN DEFAULT TRUE,
    last_run_at TIMESTAMP,
    next_run_at TIMESTAMP,
    
    -- آمار
    total_runs INTEGER DEFAULT 0,
    successful_runs INTEGER DEFAULT 0,
    failed_runs INTEGER DEFAULT 0,
    
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);

CREATE INDEX idx_schedules_driver_id ON driver_schedules(driver_id);
CREATE INDEX idx_schedules_next_run ON driver_schedules(next_run_at) WHERE is_active = TRUE;
```

### 7. جدول Activity Logs (جدید)

```sql
CREATE TABLE activity_logs (
    id SERIAL PRIMARY KEY,
    
    -- کاربر
    user_type VARCHAR(20) NOT NULL, -- super_admin, client
    user_id INTEGER NOT NULL,
    
    -- عملیات
    action VARCHAR(50) NOT NULL, -- create_client, edit_driver, delete_waybill, etc.
    entity_type VARCHAR(50), -- client, driver, waybill, etc.
    entity_id INTEGER,
    
    -- جزئیات
    description TEXT,
    changes JSONB, -- {"old": {...}, "new": {...}}
    
    -- متادیتا
    ip_address VARCHAR(45),
    user_agent TEXT,
    
    created_at TIMESTAMP DEFAULT NOW()
);

CREATE INDEX idx_activity_user ON activity_logs(user_type, user_id);
CREATE INDEX idx_activity_created ON activity_logs(created_at);
```

---

## 🔐 احراز هویت و مجوزدهی

### JWT Token Structure

```json
{
  "sub": "user_id",
  "user_type": "super_admin | client",
  "username": "username",
  "email": "email@example.com",
  "permissions": ["read:drivers", "write:drivers", "read:waybills"],
  "exp": 1234567890,
  "iat": 1234567890
}
```

### سطوح دسترسی

#### Super Admin Permissions
```python
SUPER_ADMIN_PERMISSIONS = [
    "read:all",
    "write:all",
    "delete:all",
    "manage:clients",
    "manage:system",
    "view:analytics",
]
```

#### Client Permissions
```python
CLIENT_PERMISSIONS = [
    "read:own_drivers",
    "write:own_drivers",
    "delete:own_drivers",
    "read:own_waybills",
    "write:own_waybills",
    "read:own_reports",
]
```

---

## 🎨 طراحی Frontend

### ساختار صفحات

```
/
├── /login                    # صفحه ورود (Super Admin + Client)
├── /admin                    # پنل Super Admin
│   ├── /dashboard           # داشبورد کلی
│   ├── /clients             # مدیریت کاربران
│   │   ├── /new            # ایجاد کاربر جدید
│   │   ├── /[id]           # ویرایش کاربر
│   │   └── /[id]/drivers   # مشاهده رانندگان کاربر
│   ├── /analytics           # آنالیتیکس و گزارشات
│   └── /settings            # تنظیمات سیستم
│
└── /panel                    # پنل Client
    ├── /dashboard           # داشبورد شخصی
    ├── /drivers             # مدیریت رانندگان
    │   ├── /new            # افزودن راننده
    │   ├── /[id]           # ویرایش راننده
    │   └── /[id]/schedule  # تنظیم زمان‌بندی
    ├── /waybills            # مدیریت بارنامه‌ها
    │   ├── /new            # ثبت بارنامه جدید
    │   └── /history        # تاریخچه بارنامه‌ها
    ├── /reports             # گزارشات
    └── /profile             # پروفایل کاربر
```

### Component Structure

```
src/
├── app/
│   ├── (auth)/
│   │   └── login/
│   ├── (admin)/
│   │   ├── layout.tsx
│   │   ├── dashboard/
│   │   ├── clients/
│   │   └── analytics/
│   └── (panel)/
│       ├── layout.tsx
│       ├── dashboard/
│       ├── drivers/
│       ├── waybills/
│       └── reports/
│
├── components/
│   ├── admin/
│   │   ├── ClientForm.tsx
│   │   ├── ClientList.tsx
│   │   └── ClientStats.tsx
│   ├── panel/
│   │   ├── DriverForm.tsx
│   │   ├── DriverList.tsx
│   │   ├── ScheduleForm.tsx
│   │   └── WaybillForm.tsx
│   └── shared/
│       ├── Layout.tsx
│       ├── Sidebar.tsx
│       ├── Header.tsx
│       ├── ErrorBoundary.tsx
│       └── LoadingSpinner.tsx
│
├── contexts/
│   ├── AuthContext.tsx
│   ├── AdminContext.tsx
│   └── PanelContext.tsx
│
├── hooks/
│   ├── useAuth.ts
│   ├── useClients.ts
│   ├── useDrivers.ts
│   └── useWaybills.ts
│
└── lib/
    ├── api.ts
    ├── auth.ts
    └── utils.ts
```

---

## 🔌 API Endpoints

### Super Admin Endpoints

```
POST   /api/v1/admin/login
GET    /api/v1/admin/dashboard/stats
GET    /api/v1/admin/clients
POST   /api/v1/admin/clients
GET    /api/v1/admin/clients/:id
PUT    /api/v1/admin/clients/:id
DELETE /api/v1/admin/clients/:id
PATCH  /api/v1/admin/clients/:id/status
GET    /api/v1/admin/clients/:id/drivers
GET    /api/v1/admin/clients/:id/waybills
GET    /api/v1/admin/analytics
GET    /api/v1/admin/activity-logs
```

### Client Panel Endpoints

```
POST   /api/v1/auth/login
GET    /api/v1/panel/dashboard/stats
GET    /api/v1/panel/drivers
POST   /api/v1/panel/drivers
GET    /api/v1/panel/drivers/:id
PUT    /api/v1/panel/drivers/:id
DELETE /api/v1/panel/drivers/:id
POST   /api/v1/panel/drivers/:id/schedule
GET    /api/v1/panel/drivers/:id/schedule
PUT    /api/v1/panel/drivers/:id/schedule/:scheduleId
DELETE /api/v1/panel/drivers/:id/schedule/:scheduleId
POST   /api/v1/panel/waybills
GET    /api/v1/panel/waybills
GET    /api/v1/panel/waybills/:id
GET    /api/v1/panel/reports
```

---

## 📝 مراحل پیاده‌سازی

### فاز 1: Backend (2-3 روز)
1. ✅ ایجاد migration برای جداول جدید
2. ✅ ایجاد models برای Super Admin, Schedules, Activity Logs
3. ✅ پیاده‌سازی authentication برای Super Admin
4. ✅ پیاده‌سازی CRUD endpoints برای مدیریت Clients
5. ✅ پیاده‌سازی endpoints برای مدیریت Drivers
6. ✅ پیاده‌سازی scheduling system
7. ✅ پیاده‌سازی activity logging

### فاز 2: Frontend - Admin Panel (2-3 روز)
1. ✅ ایجاد layout و routing برای Admin
2. ✅ پیاده‌سازی صفحه login
3. ✅ پیاده‌سازی dashboard
4. ✅ پیاده‌سازی مدیریت Clients
5. ✅ پیاده‌سازی analytics

### فاز 3: Frontend - Client Panel (2-3 روز)
1. ✅ ایجاد layout و routing برای Panel
2. ✅ پیاده‌سازی dashboard
3. ✅ پیاده‌سازی مدیریت Drivers
4. ✅ پیاده‌سازی scheduling UI
5. ✅ پیاده‌سازی waybill management
6. ✅ پیاده‌سازی reports

### فاز 4: Testing & Optimization (1-2 روز)
1. ✅ Unit tests
2. ✅ Integration tests
3. ✅ E2E tests
4. ✅ Performance optimization
5. ✅ Security audit

---

**تهیه‌کننده:** Claude (Anthropic)  
**تاریخ:** 2025-05-01

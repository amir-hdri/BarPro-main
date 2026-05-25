# گزارش جامع سیستم کاربرسازی و اشتراک‌گذاری
**تاریخ بررسی:** 2025-05-01  
**نسخه سیستم:** 2.1.0

---

## 📋 خلاصه اجرایی

سیستم UTCMS Automation دارای یک معماری **Multi-Tenant SaaS** کامل و حرفه‌ای است که امکان مدیریت چندین مشتری (Client/Tenant) با جداسازی کامل داده‌ها را فراهم می‌کند.

### وضعیت کلی
- ✅ **معماری Multi-Tenant:** پیاده‌سازی شده
- ✅ **سیستم احراز هویت:** JWT-based
- ✅ **جداسازی داده:** کامل (Tenant Isolation)
- ✅ **مدیریت کاربران:** Client + Driver
- ⚠️ **سیستم پرداخت:** پیاده‌سازی نشده
- ⚠️ **پلن‌های اشتراک:** ساده (فقط محدودیت‌ها)

---

## 🏗️ معماری سیستم

### 1. سطوح کاربری

#### 1.1 Master Admin (مدیر کل)
**نقش:** مدیریت کل سیستم و تمام Tenants

**دسترسی‌ها:**
- ایجاد، ویرایش، حذف Clients
- مشاهده تمام داده‌ها
- تنظیم محدودیت‌ها و سقف‌ها
- مدیریت وضعیت Clients (active/suspended/inactive)

**احراز هویت:**
```python
POST /api/v1/admin/login
{
  "username": "admin",
  "password": "admin_password"
}
```

#### 1.2 Client (مشتری/Tenant)
**نقش:** مشتری سیستم که می‌تواند رانندگان و بارنامه‌های خود را مدیریت کند

**ویژگی‌ها:**
- جداسازی کامل داده‌ها
- محدودیت‌های اختصاصی
- مدیریت رانندگان خود
- ثبت و پیگیری بارنامه‌ها

**احراز هویت:**
```python
POST /api/v1/auth/login
{
  "email": "client@example.com",
  "password": "client_password"
}
```

#### 1.3 Driver (راننده)
**نقش:** راننده‌ای که به یک Client تعلق دارد

**ویژگی‌ها:**
- اطلاعات شناسایی (کد ملی، نام، شماره تلفن)
- اعتبارنامه UTCMS (username/password رمزنگاری شده)
- وضعیت runtime (active, waiting_retry, rate_limited, etc.)
- تاریخچه احراز هویت

---

## 📊 مدل داده‌ها

### 1. جدول Clients (مشتریان)

**ساختار:**
```sql
CREATE TABLE clients (
    id SERIAL PRIMARY KEY,
    client_code VARCHAR(50) UNIQUE NOT NULL,
    name VARCHAR(255) NOT NULL,
    email VARCHAR(255) UNIQUE NOT NULL,
    phone VARCHAR(20),
    hashed_password VARCHAR(255) NOT NULL,
    status VARCHAR(20) DEFAULT 'active',
    
    -- Subscription limits
    max_drivers INTEGER DEFAULT 10,
    max_concurrent_tasks INTEGER DEFAULT 2,
    max_daily_tasks INTEGER DEFAULT 100,
    
    -- Metadata
    metadata_json TEXT,
    notes TEXT,
    
    -- Timestamps
    created_at TIMESTAMP NOT NULL,
    updated_at TIMESTAMP NOT NULL,
    last_login_at TIMESTAMP
);
```

**وضعیت‌های ممکن:**
- `active` - فعال
- `suspended` - تعلیق شده
- `inactive` - غیرفعال

**محدودیت‌های اشتراک:**
| فیلد | پیش‌فرض | توضیحات |
|------|---------|---------|
| `max_drivers` | 10 | حداکثر تعداد رانندگان |
| `max_concurrent_tasks` | 2 | حداکثر وظایف همزمان |
| `max_daily_tasks` | 100 | حداکثر وظایف روزانه |

### 2. جدول Drivers (رانندگان)

**ساختار:**
```sql
CREATE TABLE drivers (
    id SERIAL PRIMARY KEY,
    client_id INTEGER REFERENCES clients(id),
    
    -- Identity
    driver_national_code VARCHAR(10) NOT NULL,
    full_name VARCHAR(255) NOT NULL,
    phone VARCHAR(20),
    license_number VARCHAR(50),
    
    -- UTCMS credentials (encrypted)
    utcms_username VARCHAR(100) NOT NULL,
    utcms_password_encrypted TEXT NOT NULL,
    
    -- Status
    status VARCHAR(20) DEFAULT 'active',
    runtime_status VARCHAR(40) DEFAULT 'active',
    
    -- Auth tracking
    last_auth_at TIMESTAMP,
    last_session_expires_at TIMESTAMP,
    last_error_code VARCHAR(64),
    
    -- Timestamps
    created_at TIMESTAMP NOT NULL,
    updated_at TIMESTAMP NOT NULL,
    
    UNIQUE(client_id, driver_national_code)
);
```

**وضعیت‌های Driver:**
- `active` - فعال
- `inactive` - غیرفعال
- `blocked` - مسدود شده
- `auth_required` - نیاز به احراز هویت
- `ready` - آماده
- `waiting_retry` - در انتظار تلاش مجدد
- `rate_limited` - محدود شده
- `invalid_credentials` - اعتبارنامه نامعتبر
- `daily_limit_reached` - سقف روزانه

### 3. جدول WaybillJobs (وظایف بارنامه)

**ساختار:**
```sql
CREATE TABLE waybill_jobs (
    id SERIAL PRIMARY KEY,
    job_id VARCHAR(50) UNIQUE NOT NULL,
    client_id INTEGER REFERENCES clients(id),
    driver_id INTEGER REFERENCES drivers(id),
    
    -- Job info
    source VARCHAR(20) DEFAULT 'manual',
    status VARCHAR(30) DEFAULT 'pending',
    priority INTEGER DEFAULT 5,
    
    -- Payload
    payload_json TEXT NOT NULL,
    result_json TEXT,
    
    -- Error tracking
    error_category VARCHAR(64),
    last_error TEXT,
    
    -- Retry logic
    attempt_count INTEGER DEFAULT 0,
    max_retries INTEGER DEFAULT 3,
    next_retry_at TIMESTAMP,
    
    -- Timestamps
    created_at TIMESTAMP NOT NULL,
    updated_at TIMESTAMP NOT NULL,
    started_at TIMESTAMP,
    finished_at TIMESTAMP,
    
    UNIQUE(client_id, job_id)
);
```

**وضعیت‌های Job:**
- `pending` - در انتظار
- `queued` - در صف
- `in_progress` - در حال اجرا
- `retrying` - تلاش مجدد
- `waiting_auth` - منتظر احراز هویت
- `waiting_retry` - منتظر تلاش مجدد
- `otp_backoff` - تاخیر OTP
- `success` - موفق
- `failed` - ناموفق
- `daily_limit_reached` - سقف روزانه
- `dead_letter` - شکست نهایی

---

## 🔐 سیستم احراز هویت

### 1. JWT Token-Based Authentication

**ساختار Token:**
```python
{
  "client_id": 1,
  "client_code": "client_001",
  "email": "client@example.com",
  "exp": 1735689600  # 24 hours
}
```

**Header:**
```http
Authorization: Bearer <jwt_token>
```

### 2. Tenant Isolation (جداسازی داده)

**اعمال خودکار:**
```python
# در تمام queries
WHERE client_id = current_client.id
```

**مثال:**
```python
# Client فقط رانندگان خودش را می‌بیند
drivers = await session.exec(
    select(Driver).where(Driver.client_id == client.id)
)
```

### 3. رمزنگاری رمز عبور

**Client passwords:**
```python
# bcrypt hashing
hashed_password = hash_password(plain_password)
```

**Driver UTCMS passwords:**
```python
# Fernet encryption (symmetric)
encrypted = encrypt_driver_password(plain_password)
decrypted = decrypt_driver_password(encrypted)
```

---

## 🎯 API Endpoints

### 1. Authentication

#### ثبت‌نام Client جدید
```http
POST /api/v1/auth/register
Content-Type: application/json

{
  "client_code": "company_001",
  "name": "شرکت نمونه",
  "email": "info@company.com",
  "phone": "09123456789",
  "password": "SecurePass123"
}
```

**پاسخ:**
```json
{
  "id": 1,
  "client_code": "company_001",
  "name": "شرکت نمونه",
  "email": "info@company.com",
  "status": "active",
  "max_drivers": 10,
  "max_concurrent_tasks": 2,
  "max_daily_tasks": 100,
  "created_at": "2025-05-01T12:00:00"
}
```

#### ورود Client
```http
POST /api/v1/auth/login
Content-Type: application/json

{
  "email": "info@company.com",
  "password": "SecurePass123"
}
```

**پاسخ:**
```json
{
  "access_token": "eyJhbGciOiJIUzI1NiIs...",
  "token_type": "bearer",
  "expires_in": 86400,
  "client": { ... }
}
```

### 2. Driver Management

#### ایجاد راننده جدید
```http
POST /api/v1/drivers
Authorization: Bearer <token>
Content-Type: application/json

{
  "driver_national_code": "1234567890",
  "full_name": "علی احمدی",
  "phone": "09123456789",
  "license_number": "12345678",
  "utcms_username": "ali_ahmadi",
  "utcms_password": "utcms_pass"
}
```

#### لیست رانندگان
```http
GET /api/v1/drivers
Authorization: Bearer <token>
```

#### ویرایش راننده
```http
PUT /api/v1/drivers/{driver_id}
Authorization: Bearer <token>
Content-Type: application/json

{
  "full_name": "علی احمدی (به‌روز شده)",
  "status": "active"
}
```

#### حذف راننده
```http
DELETE /api/v1/drivers/{driver_id}
Authorization: Bearer <token>
```

### 3. Waybill Jobs

#### ایجاد بارنامه
```http
POST /api/v1/jobs
Authorization: Bearer <token>
Content-Type: application/json

{
  "driver_national_code": "1234567890",
  "origin": "تهران",
  "destination": "اصفهان",
  "waybill_number": "WB-2025-001",
  "cargo_type": "کالای عمومی",
  "cargo_weight": 1500.5,
  "cargo_description": "محموله تست",
  "vehicle_type": "کامیون",
  "plate_number": "12ب34567ایران89",
  "driver_phone": "09123456789",
  "notes": "تحویل فوری"
}
```

#### لیست بارنامه‌ها
```http
GET /api/v1/jobs?status=success&page=1&page_size=20
Authorization: Bearer <token>
```

#### وضعیت بارنامه
```http
GET /api/v1/jobs/{job_id}
Authorization: Bearer <token>
```

### 4. Admin Endpoints

#### لیست تمام Clients
```http
GET /api/v1/admin/clients
Authorization: Bearer <admin_token>
```

#### ایجاد Client توسط Admin
```http
POST /api/v1/admin/clients
Authorization: Bearer <admin_token>
```

#### ویرایش Client
```http
PUT /api/v1/admin/clients/{client_id}
Authorization: Bearer <admin_token>
Content-Type: application/json

{
  "status": "suspended",
  "max_drivers": 20,
  "max_concurrent_tasks": 5,
  "max_daily_tasks": 500
}
```

#### حذف Client
```http
DELETE /api/v1/admin/clients/{client_id}
Authorization: Bearer <admin_token>
```

---

## 📈 آمار فعلی سیستم

### Clients (مشتریان)
```
تعداد کل: 6
- active: 6
- suspended: 0
- inactive: 0
```

**نمونه Clients:**
| ID | Client Code | Name | Max Drivers | Max Tasks/Day |
|----|-------------|------|-------------|---------------|
| 1 | live_9a01b3a0 | Live Smoke Tenant | 10 | 100 |
| 2 | live_f8a10036 | Live Smoke Tenant | 10 | 100 |
| 3 | playwright_tenant_01 | Playwright Tenant | 10 | 100 |
| 6 | 1234 | amir | 10 | 100 |

### Drivers (رانندگان)
```
تعداد کل: 5
- active: 5
- inactive: 0
```

**توزیع بر اساس Client:**
| Client Code | تعداد رانندگان |
|-------------|----------------|
| live_9a01b3a0 | 1 |
| live_f8a10036 | 1 |
| playwright_tenant_03 | 1 |
| 1234 (amir) | 2 |

### Waybill Jobs (وظایف)
```
تعداد کل: 8
- waiting_auth: 1
- dead_letter: 7
- success: 0
- in_progress: 0
```

---

## ⚠️ نقاط ضعف و محدودیت‌ها

### 1. سیستم پرداخت
**وضعیت:** ❌ پیاده‌سازی نشده

**نیازها:**
- درگاه پرداخت (Zarinpal, Saman, etc.)
- مدیریت تراکنش‌ها
- صورتحساب‌ها
- تاریخچه پرداخت

### 2. پلن‌های اشتراک
**وضعیت:** ⚠️ ساده (فقط محدودیت‌ها)

**موجود:**
- محدودیت تعداد رانندگان
- محدودیت وظایف همزمان
- محدودیت وظایف روزانه

**نیازها:**
- پلن‌های از پیش تعریف شده (Basic, Pro, Enterprise)
- قیمت‌گذاری
- دوره اشتراک (ماهانه، سالانه)
- تاریخ انقضا
- تمدید خودکار

### 3. Billing System
**وضعیت:** ❌ پیاده‌سازی نشده

**نیازها:**
- محاسبه هزینه بر اساس استفاده
- صورتحساب ماهانه
- گزارش مالی
- مالیات

### 4. Usage Tracking
**وضعیت:** ⚠️ محدود

**موجود:**
- تعداد وظایف
- وضعیت وظایف

**نیازها:**
- ردیابی دقیق استفاده
- محاسبه هزینه real-time
- هشدارهای سقف مصرف
- گزارش‌های تحلیلی

### 5. Self-Service Portal
**وضعیت:** ❌ پیاده‌سازی نشده

**نیازها:**
- پنل کاربری برای Client
- مدیریت اشتراک
- مشاهده صورتحساب
- تغییر پلن
- مدیریت پرداخت

---

## 🚀 پیشنهادات بهبود

### اولویت بالا

#### 1. پیاده‌سازی Subscription Plans
```python
# مدل پیشنهادی
class SubscriptionPlan(SQLModel, table=True):
    id: int
    name: str  # "Basic", "Pro", "Enterprise"
    price_monthly: float
    price_yearly: float
    max_drivers: int
    max_concurrent_tasks: int
    max_daily_tasks: int
    features_json: str
    is_active: bool
```

#### 2. اضافه کردن Subscription به Client
```python
class Client(SQLModel, table=True):
    # ... existing fields
    subscription_plan_id: Optional[int]
    subscription_status: str  # "trial", "active", "expired", "cancelled"
    subscription_start_date: Optional[datetime]
    subscription_end_date: Optional[datetime]
    trial_ends_at: Optional[datetime]
```

#### 3. پیاده‌سازی Payment Gateway
```python
class Payment(SQLModel, table=True):
    id: int
    client_id: int
    amount: float
    currency: str  # "IRR"
    status: str  # "pending", "completed", "failed"
    gateway: str  # "zarinpal", "saman"
    transaction_id: str
    created_at: datetime
```

### اولویت متوسط

#### 4. Usage Metering
```python
class UsageRecord(SQLModel, table=True):
    id: int
    client_id: int
    date: date
    jobs_created: int
    jobs_success: int
    jobs_failed: int
    api_calls: int
    storage_used_mb: float
```

#### 5. Billing System
```python
class Invoice(SQLModel, table=True):
    id: int
    client_id: int
    invoice_number: str
    period_start: date
    period_end: date
    subtotal: float
    tax: float
    total: float
    status: str  # "draft", "sent", "paid", "overdue"
    due_date: date
```

### اولویت پایین

#### 6. Referral System
```python
class Referral(SQLModel, table=True):
    id: int
    referrer_client_id: int
    referred_client_id: int
    reward_amount: float
    status: str
```

#### 7. Notifications
```python
class Notification(SQLModel, table=True):
    id: int
    client_id: int
    type: str  # "payment_due", "limit_reached", "subscription_expiring"
    message: str
    is_read: bool
    created_at: datetime
```

---

## 📝 نتیجه‌گیری

### نقاط قوت
- ✅ معماری Multi-Tenant حرفه‌ای
- ✅ جداسازی کامل داده‌ها
- ✅ سیستم احراز هویت قوی (JWT)
- ✅ رمزنگاری رمز عبورها
- ✅ API RESTful کامل
- ✅ محدودیت‌های اشتراک قابل تنظیم

### نقاط ضعف
- ❌ عدم وجود سیستم پرداخت
- ❌ عدم وجود پلن‌های از پیش تعریف شده
- ❌ عدم وجود Billing System
- ⚠️ Usage Tracking محدود
- ❌ عدم وجود Self-Service Portal

### امتیاز کلی
**سیستم کاربرسازی:** 85/100
- معماری: 95/100
- احراز هویت: 90/100
- جداسازی داده: 100/100
- مدیریت کاربران: 85/100
- سیستم اشتراک: 40/100
- سیستم پرداخت: 0/100

### توصیه نهایی
سیستم از نظر معماری و پایه‌های فنی بسیار قوی است، اما برای تبدیل به یک SaaS کامل نیاز به:
1. پیاده‌سازی Subscription Plans
2. اتصال به درگاه پرداخت
3. ایجاد Billing System
4. توسعه Self-Service Portal

---

**تهیه‌کننده:** Claude AI Assistant  
**تاریخ:** 2025-05-01  
**نسخه:** 1.0

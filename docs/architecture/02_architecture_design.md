## ۲. طراحی معماری سیستم (System Architecture)

### 2.1 نمای کلی معماری
سیستم با رویکرد سرویس‌گرا (Service-Oriented) و Event-Driven با معماری زیر پیشنهاد و پیاده‌سازی شده است:
- **Backend Framework**: فریم‌ورک Python FastAPI جهت ایجاد اندپوینت‌های سریع و Asynchronous. (مستقر در `app/api`)
- **RPA Engine**: موتور Playwright با الگوی Self-Healing، آنتی‌دیتکت (Stealth) و Proxy Rotation.
  - منطق پیدا کردن المان‌ها با یک الگوریتم Fallback-based تحت عنوان `SmartLocator` ساخته شده است (مستقر در `app/bot/core`).
- **Queue/Background Jobs**: ابزار Celery به همراه Redis (یا BullMQ) برای توزیع وظایف و کنترل کانکارنسی RPA تا فشار به سرور مقصد کنترل شود.
- **Database**: PostgreSQL همراه با SQLAlchemy / SQLModel جهت تراکنش‌های مقاوم با ایزوله‌سازی کلاینت‌ها (`models_multitenant.py`).
- **Caching & Lock**: دیتابیس در حافظه Redis جهت Rate Limiting، کنترل توزیع‌یافته (Distributed Locks) و مدیریت Sessionهای ورود (Session Vault).
- **AI/Captcha**: پیاده‌سازی مکانیزم حل کپچا با سرویس‌های Third-Party و Fallback کردن روی CNN Models در صورت عدم پاسخگویی (`app/bot/captcha/interceptor.py`).

### 2.2 معماری Worker (Job Scheduler & Worker)
طراحی Scheduler به شکل کاملاً Asynchronous برای توزیع بار در یک ساختار Master-Slave انجام می‌شود:
- **Producer (API)**: تمامی درخواست‌ها توسط Pydantic Models اعتبارسنجی اولیه شده (در `app/schemas`) و در یک صف تحت نام `waybill_jobs` می‌نشینند.
- **Scheduler**: زمان‌بند برای اجرای کارهای زمان‌بندی شده (Scheduled Waybills) در دوره‌های خاص.
- **Consumers (RPA Nodes)**: کلاستر توزیع‌شده‌ای از Workerها که تسک‌های بارنامه را از صف می‌خوانند و فرآیند اتوماسیون شامل (Login, Captcha Intercept, Form Submit) را در محیط ایزوله (Incognito Context) انجام می‌دهند.
- **Backoff & Graceful Exit**: استراتژی هندلینگ خطاها که به محض دریافت OTP یا Session Invalidation کانکشن را موقتاً قطع کرده (`CircuitBreaker`) و پردازش را به صف باطل‌شده (Dead-letter یا Retry Queue) برمی‌گرداند تا در زمان آینده با سلامت بالاتر انجام پذیرد.

---

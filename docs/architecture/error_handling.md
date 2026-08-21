> Legacy design note. For current error taxonomy, retry routing, circuit
> isolation, and reconciliation use docs/BARPRO_KNOWLEDGE_GRAPH.md and code.

# سیستم خطا یابی و رفع خطا (Error Handling System)

این سند طراحی سیستم حرفه‌ای خطا یابی و رفع خطا را برای این پروژه شرح می‌دهد.

## وضعیت فعلی
در `app/core/error_handler.py` متدهای اولیه‌ای مانند `safe_execute` و دکوراتورهای `retry_on_exception` و `async_retry_on_exception` وجود دارد. همچنین `app/core/exceptions.py` حاوی یک ساختار سلسله مراتبی از استثناها با کد خطاهای ساخت‌یافته است (ErrorCode).

## تغییرات اعمال شده (سیستم پیشرفته)

### 1. ثبت مرکزی خطاها (Centralized Error Registry)
- کلاس `ErrorReporter` در ماژول `app/core/error_handler.py` ساخته شد تا یک نقطه ورودی واحد برای مدیریت، فرمت‌بندی و لاگ کردن کامل خطاها (به همراه Traceback و متن دسته‌بندی شده) داشته باشیم. متد `log_exception_context` نیز از آن بهره‌مند شده است.

### 2. سیستم هشدار و اطلاع‌رسانی (Alerting System)
- کلاس `ErrorReporter` به `app/core/alerts.py` (گزارش‌دهی از طریق Webhook/تلگرام/اسلک و...) متصل شد. اگر خطا از دسته‌بندی‌های بحرانی مثل `BOT_DETECTED`, `AUTH_FAILURE`, `WORKER_RESOURCE_ERROR` باشد، یا درجه خطا به طور دستی روی critical/high تنظیم شود، بلافاصله `alert_manager.emit` فراخوانی می‌شود.

### 3. داشبورد و مانیتورینگ خطاها
- در `app/api/routes/system.py` متد و آدرس جدیدی به نام `/errors/stats` ایجاد شد که می‌تواند برای نمایش داشبورد خطاها و بررسی فراوانی و دسته‌بندی‌های خطا در بک‌اند و فرانت‌اند مورد استفاده قرار گیرد.

### 4. بازیابی خودکار (Auto-Recovery)
- سیستم مبتنی بر Worker (در `recovery_manager`) و Circuit Breaker کماکان برای مقابله با خطاهای شبکه و Resource Crash‌ها فعال هستند و استثناهایی که `retryable=True` هستند توسط سیستم صف (Celery/DB) مجدداً تلاش خواهند شد.

### 5. تست و اطمینان از سلامت سیستم
- برای اطمینان از کارکرد صحیح، اندپوینت `/errors/stats` در تست‌های موجود `test_system_health.py` پوشش داده شد.

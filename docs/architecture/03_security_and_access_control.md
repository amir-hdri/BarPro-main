## ۳. امنیت و کنترل دسترسی (Security & Access Control)

### 3.1 احراز هویت و Authorization
- استفاده از JWT با طول عمر کوتاه (Access Token) در کنار Refresh Token امن (HttpOnly Cookie).
- کنترل سطح دسترسی بر مبنای نقش (Role-Based Access Control) جهت تفکیک Super Admin و Tenant User.

### 3.2 مدیریت Credentials و داده‌های حساس
- تمامی کلمه‌های عبور سامانه UTCMS در پایگاه داده با استفاده از الگوریتم رمزنگاری متقارن (AES-GCM با Fernet) رمزگذاری می‌شوند. کلید رمزنگاری فقط در Environment Variables یا سرویس KMS سیستم عامل/کلاد ذخیره می‌شود.

### 3.3 امنیت API و ورودی‌ها
- Validate تمام ورودی‌ها توسط مدل‌های Pydantic (تطابق کامل ساختار و Type).
- اعمال Rate Limiting روی درخواست‌های حساس (مثلا تلاش‌های پی‌درپی برای ورود یا ثبت بارنامه).
- محافظت در برابر SQL Injection، XSS (هرچند API بیس است) و CSRF (از طریق تنظیمات صحیح Cookie).

### 3.4 ثبت فعالیت‌ها (Audit Logs)
- سیستم تمامی CRUDها بر روی موجودیت‌های پایه را نگهداری می‌کند و آدرس IP متقاضی را با Timestamp ثبت می‌نماید.

---

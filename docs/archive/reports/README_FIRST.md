# مستندات و راهنمای اولیه پروژه BarPro

> **📌 معماری جدید:** پروژه به معماری monorepo ارتقا یافته است. فرانت‌اند اصلی با Next.js و Tailwind در پوشه `apps/web/` و بک‌اند در `app/` قرار دارد. تمامی مستندات در راستای این تغییرات به‌روزرسانی شده‌اند.


سیستم با موفقیت دیباگ و اصلاح شده است. تغییرات اصلی انجام شده:

## ۱. رفع خطاهای حیاتی E2E (تست جریان کامل ربات)
- تصحیح مکانیزم استخراج Base64 کپچا هنگام نبود تگ `<canvas>` به‌واسطه‌ی رندر `evaluate` جاوااسکریپت و شبیه‌سازی مطمئن‌تر آن برای تست‌ها.
- رفع مشکل تایم‌اوت `bounding_box` در `Playwright` برای گرفتن اسکرین‌شات از عناصر ناپایدار فرم.
- افزایش تحمل‌پذیری (Resilience) ربات نسبت به المان‌های ناقص در زمان اجرای `EnhancedWaybillManager` با استفاده از `try-except` در فرآیند Click و Fallback به متد جاوااسکریپت `page.evaluate`.
- **نتیجه:** وضعیت تست `test_e2e_bot.py::test_e2e_self_healing_bot_flow` که حیاتی‌ترین شبیه‌سازی سیستم RPA است، کاملا موفق و **PASSED** می‌باشد.

## ۲. اضافه شدن مستند معماری و موجودیت‌ها (در پوشه docs/architecture)
- تمامی موارد خواسته‌شده از جمله طراحی دیتابیس موجودیت‌های اصلی (Super Admin, User, Driver, Plate, UTCMS Credential, Waybill, Log), روابط بین آن‌ها، معماری Schedulerها برای بک‌اند، معماری سیستم مانیتورینگ خطاها، و معماری امنیتی و RBAC مطابق با ساختار چند مستأجره در فایل‌های اختصاصی زیر ایجاد شدند:
  - `01_requirements_analysis.md`
  - `02_architecture_design.md`
  - `03_security_and_access_control.md`
  - `04_api_design.md`
  - `05_logging_and_reporting.md`
  - `06_test_scenarios.md`
  - `07_future_improvements.md`

## ۳. امنیت سیستم
- منطق رمزنگاری (Encryption) در سرویس `secrets_manager.py` برای تمامی Credentialها (پسورد بارنامه کشوری کاربران) وجود دارد که کلیدهای امنیتی متقارن را ایزوله می‌کند.
- `startup_validation.py` تایید می‌کند که سیستم بدون کلیدهای امنیتی معتبر Run نشود.
- `error_taxonomy.py` خطاهای داخلی سیستم را استانداردسازی کرده و از افشای اطلاعات Stack Trace در محیط Production (از طریق XSS یا API leaks) جلوگیری می‌کند.

## اجرای پروژه
با توجه به برطرف‌شدن وابستگی‌ها و آپدیت `.gitignore` کافیست:
```bash
# نصب نیازمندی‌ها
pip install -r requirements.txt
pip install -r requirements-dev.txt

# اجرای تست‌ها
pytest tests/
```

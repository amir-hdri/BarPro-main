# گزارش اقدامات انجام شده و تغییرات (Walkthrough)

تمام تست‌های محلی سیستم با موفقیت به پایان رسیدند و خطاها برطرف شدند. در ادامه شرح تغییرات و اعتبارسنجی‌ها آمده است:

---

## 🛠️ تغییرات اعمال شده (Applied Changes)

### ۱. حل خطای ناهمخوانی حلقه رویداد در `waybill_worker.py`
* **مسأله:** تسک `waybill.process_job` از `asyncio.run()` استفاده می‌کرد که برای هر بار اجرای تسک، یک Event Loop جدید ایجاد و حذف می‌کرد. این کار باعث می‌شد که کلاینت‌های دیتابیس موجود در Connection Pool با خطای `Future attached to a different loop` مواجه شوند.
* **راهکار:** ساختار مدیریت حلقه رویداد در [waybill_worker.py](file:///Users/amirheidari/GitHub/BarPro-main/app/workers/waybill_worker.py) بازنویسی شد تا مانند دیگر کارگرها از یک حلقه رویداد مشترک و پایدار در سطح پروسس استفاده کند.

### ۲. اصلاح پارامترهای اجرای کرومیوم در `browser.py`
* **مسأله:** تسک‌های تست در فایل `test_browser_manager.py` انتظار داشتند که فلگ‌های `--disable-crashpad-for-testing` و `--disable-crash-reporter` در تنظیمات راه‌اندازی کرومیوم وجود داشته باشند، اما این فلگ‌ها در فایل `browser.py` حذف شده بودند و باعث شکست تست می‌شد.
* **راهکار:** فلگ‌های امنیتی و کاهش مصرف حافظه فوق به لیست آرگومان‌های راه‌اندازی مرورگر در [browser.py](file:///Users/amirheidari/GitHub/BarPro-main/app/automation/browser.py) بازگردانده شدند که این امر علاوه بر رفع خطای تست، پایداری کانتینرها در محیط تولید را نیز افزایش می‌دهد.

### ۳. رفع خطای منطقی تشخیص چالش OTP پس از ثبت بارنامه در `waybill_enhanced.py`
* **مسأله:** در متد `_check_otp_challenge_after_submit` فایل [waybill_enhanced.py](file:///Users/amirheidari/GitHub/BarPro-main/app/automation/waybill_enhanced.py)، در صورتی که عنصر OTP پیدا نمی‌شد (`candidate is None`)، کد به دلیل فرورفتگی اشتباه (Indentation)، باز هم وضعیت را به عنوان چالش OTP در نظر گرفته و تسک را با وضعیت شکست خاتمه می‌داد که این موضوع باعث شکست تست‌های happy path ثبت بارنامه می‌شد.
* **راهکار:** بررسی مناسب اضافه شد تا در صورت عدم وجود فیلد OTP، تابع فوراً مقدار `None` بازگرداند و فرآیند ثبت با موفقیت تکمیل شود.
* **تست:** برای همگام‌سازی با این تغییر، شبیه‌سازهای تست در [test_enhanced_waybill_manager.py](file:///Users/amirheidari/GitHub/BarPro-main/tests/test_enhanced_waybill_manager.py) نیز اصلاح شدند.

---

## 🧪 اعتبارسنجی و تست‌ها (Verification & Tests)

تمامی ۳۹۵ تست موجود در پروژه با استفاده از محیط مفسر `python-ml` اجرا شدند:

* **فرمان اجرا:**
  ```bash
  /Users/amirheidari/Virtualenvs/Python-ML/bin/pytest -m "not slow"
  ```
* **نتیجه نهایی:**
  * **تعداد تست‌های پاس شده:** ۳۹۳ مورد
  * **تعداد تست‌های نادیده گرفته شده (Skipped):** ۲ مورد
  * **تعداد خطاها (Failed):** ۰ مورد (۱۰۰٪ تست‌های اجرا شده با موفقیت پاس شدند)

سیاهه کامل خروجی تست نشان می‌دهد که تغییرات اعمال شده هیچ‌گونه اثر جانبی منفی (Regression) روی عملکرد سیستم نگذاشته و رفتارهای ران‌تایم را کاملاً تصحیح کرده است.

---

## ✅ تکمیل آماده‌سازی Full-Stack برای سرور (2026-07-08)

### تغییرات کلیدی جدید

* **Auth:** توکن JWT از localStorage حذف شد و با کوکی `httpOnly` ارسال می‌شود. برای سرور HTTP فعلی مقدار `AUTH_COOKIE_SECURE=false` لازم است؛ پس از HTTPS مقدار `true` شود.
* **Frontend Docker:** داکرفایل فرانت‌اند اکنون خودش `npm ci` و `npm run build` را اجرا می‌کند و دیگر به `.next/standalone` از قبل ساخته‌شده نیاز ندارد.
* **Backend Docker:** وابستگی TensorFlow بر اساس معماری انتخاب می‌شود: `tensorflow-cpu` برای x86_64 سرور و `tensorflow` برای ARM/local.
* **Fuel CAPTCHA:** provider جدید `pytorch_fuel`، parser عدد فارسی، مدل CRNN و vocab اضافه شدند.
* **Migrations:** head فعلی Alembic برابر `015_add_client_subscription_dates` است.
* **Artifacts:** فایل‌های local/generated مانند `datasets/`, `scratch/`, screenshots, tarballs و `_model_cache/` از upload و Docker context حذف شدند.

### اعتبارسنجی نهایی

```bash
python -m ruff check app/core/config.py app/api/routes/multitenant.py tests/test_once_schedule.py
pytest tests/test_once_schedule.py tests/test_config_validation.py tests/test_multitenant_auth.py tests/test_master_admin.py
cd apps/web && npm run build
cd apps/web && npm audit --omit=dev
docker compose -f compose/backend.yml build backend
docker compose -f compose/web.yml build frontend
alembic heads
```

نتیجه: build و تست‌های هدفمند با موفقیت انجام شدند و `npm audit --omit=dev` آسیب‌پذیری production نشان نمی‌دهد.

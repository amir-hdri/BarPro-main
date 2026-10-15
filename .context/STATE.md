<!--schema:2.0.0-->
<!--agent:Antigravity-->
<!--timestamp:2026-10-15T20:05:00+03:30-->
<!--cairn-phase:2-->

# 🎯 هدف جاری
پروژه پایداری چرخه حیات بارنامه و بهینه‌سازی ورود و لاگ‌های سرور (Server Logs Optimization & Driver Login Throttling) — فاز ۲ و ۳: پیاده‌سازی سازوکار ورود هدفمند، کنترل‌شده و زمانبندی‌شده رانندگان به سامانه UTCMS، جلوگیری از لاگین‌های تکراری و بی‌هدف، برطرف‌سازی خطاهای زمانبندی و روتینگ در لاگ‌های سرور، و استقرار روی سرور مرکزی.

## ✅ کارهای انجام‌شده
- **طراحی و پیاده‌سازی سیستم ورود هدفمند رانندگان (Targeted & Scheduled Driver Login Architecture):**
  - افزودن پارامتر الزامی هدفمندی (`purpose`) در تمام درخواست‌های ورود راننده (`waybill_submission`, `shipping_start`, `shipping_finish`, `shipping_waypoint`, `reconciliation_audit`).
  - ارتقای `app/automation/login_attempt_ledger.py`: اعمال سهمیه‌بندی ساعتی (حداکثر ۶ لاگین کامل در ساعت برای هر راننده - `LOGIN_MAX_HOURLY = 6`) و ایجاد فاصله زمانی اجباری حداقل ۹۰ ثانیه بین دو لاگین کامل (`LOGIN_MIN_INTERVAL_SECONDS = 90`).
  - جلوگیری از لاگین‌های بی‌هدف و تکراری: غیرفعال‌سازی تسک پس‌زمینه سنگین `rpa-session-keepalive` در زمانبندی کرون Celery Beat (که قبلاً هر ۳۰ دقیقه برای همه رانندگان به صورت خودکار و کورکورانه مرورگر باز می‌کرد).
  - استفاده بهینه و حداکثری از Session Vault ردیس: اولویت مطلق با توکن زنده Bearer، تمدید سبک و تک‌درخواستی از طریق `refresh_token` (بدون حل کپچا و بدون پسورد)، و قفل توزیع‌شده ردیس برای جلوگیری از لاگین همزمان.
- **برطرف‌سازی خطاهای شناسایی‌شده در ممیزی لاگ‌های زنده سرور:**
  - رفع کرش روتینگ در `app/travel/route.py` و `app/services/route_authority.py`: ساخت آفست مصنوعی محلی (~۱۰۰ متر) برای مختصات یکسان مبدأ و مقصد در `straight_line_fallback` و جلوگیری قطعی از بروز خطای `ValueError: route geometry needs at least two distinct points`.
  - رفع نویز لاگ در `app/services/driver_schedule_service.py`: مدیریت صریح استثنای `HTTPException(409)` مربوط به تعارض سفر فعال راننده و ثبت آن در سطح لاگ `INFO` به جای `ERROR` با traceback.
  - اصلاح ارور `scheduler_service.py`: هدایت خودکار جاب‌های بدون راننده (`driver_id is None`) به وضعیت `needs_review` با `TaskStatus.NEEDS_REVIEW.value`.
  - بهینه‌سازی زمانبندی Celery Beat: افزایش زمان انقضای تسک‌های `orchestrator-dispatcher` و `otp-stream-sweep` از ۴ ثانیه به ۱۰ ثانیه برای جلوگیری از انقضای ناخواسته ناشی از jitter صف.
  - اصلاح لاگ DNS Sinkhole در `app/automation/clean_ip_pool.py` به سطح INFO همراه با ثبت نام هاست.
  - جاروب و نهایی‌سازی `DispatchIntent`های رها شده در `app/orchestrator/claim_reaper.py`.
- **پاکسازی رکوردهای سرگردان در پایگاه‌داده سرور مرکزی:**
  - به‌روزرسانی جاب سرگردان `job_34fc35310ca24756` به وضعیت `needs_review`.
  - به‌روزرسانی اینتنت رها شده `ca6527e7-d847-474e-962a-a5352358a4f1` به `completed`.
- **تست، اعتبارسنجی و استقرار:**
  - نگارش تست‌های اعتبارسنجی جدید برای فاصله‌گذاری و سقف ساعتی در `tests/test_login_attempt_ledger.py`.
  - اجرای کامل ۶۴ تست در سوئیت‌های `test_route_authority.py`، `test_travel_route.py`، `test_login_attempt_ledger.py` و `test_gps_session_vault.py` با خروجی ۱۰۰٪ موفق.
  - اجرای کامل ۲۹ تست در سوئیت‌های زمانبندی `test_beat_schedule_wiring.py`، `test_rpa_dispatch_scheduler.py`، `test_scheduler_policy.py` و ... با خروجی ۱۰۰٪ موفق.
  - پاس شدن بدون اخطار ابزار `ruff check`.
  - استقرار فایل‌ها روی سرور مرکزی (`87.107.160.251`) و راه‌اندازی مجدد ۴ کانتینر (`barpro-backend`، `barpro-scheduler`، `barpro-worker-1`، `barpro-beat`).
  - پایش لاگ‌های زنده سرور: تأیید کارکرد روان تمام تسک‌ها در بازه کمتر از ۲۰ میلی‌ثانیه بدون هیچ‌گونه خطا یا هشدار تکراری.

## 📁 فایل‌های تغییریافته
- `app/core/config.py`
- `app/automation/login_attempt_ledger.py`
- `app/automation/gps_shipping_manager.py`
- `app/automation/clean_ip_pool.py`
- `app/orchestrator/claim_reaper.py`
- `app/orchestrator/scheduler_service.py`
- `app/services/route_authority.py`
- `app/services/driver_schedule_service.py`
- `app/travel/route.py`
- `app/workers/celery_app.py`
- `tests/test_login_attempt_ledger.py`
- `.context/STATE.md`

## 🎯 تسک دقیق بعدی
ادامه مانیتورینگ سلامت سرویس‌ها و هماهنگی جهت تست ثبت بارنامه بعدی راننده محمدزاده طبق زمانبندی تنظیم‌شده.

## 🧠 تصمیمات فنی و چرایی
- مسدودسازی ورود بی‌هدف رانندگان در سطح هسته و حذف تسک کور keepalive برای حفظ سلامت اکانت رانندگان در WAF سامانه‌ کشوری.
- ارجحیت توکن‌های کش‌شده و رفرش‌توکن بر لاگین کامل، که ضمن کاهش مصرف کپچا و کاهش هزینه منابع سرور، مانع از قفل شدن اکانت‌ها می‌شود.
- هندلینگ نرم خطای ۴۰۹ در زمانبندی رانندگان، که از ثبت تریس‌بک‌های گیج‌کننده و غلط‌انداز در لاگ‌های پروداکشن جلوگیری می‌کند.

## ⚠️ نکات حساس و موانع
- هرگونه درخواست لاگین مجدد با `force_reauth=True` در صورتی که توکن معتبر و زنده در ردیس باشد، به توکن موجود fallback داده می‌شود تا راننده دچار throttle نشود.

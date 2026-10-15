<!--schema:2.0.0-->
<!--agent:Antigravity-->
<!--timestamp:2026-10-15T20:21:00+03:30-->
<!--cairn-phase:2-->

# 🎯 هدف جاری
پروژه پایداری چرخه حیات بارنامه و بهینه‌سازی ورود و لاگ‌های سرور (Server Logs Optimization & Driver Login Throttling) — اتمام و تأیید قطعی فاز ۱ در کرن (Phase 1 Verified)، همگام‌سازی وضعیت ایشیوها در گیت‌هاب ترکر (Issues #93 و #94 بسته شدند؛ #95، #96، #98، #99 در وضعیت in_progress با کامنت‌های مستند)، و ورود به فاز ۲.

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
- **تأیید فاز ۱ در کرن و همگام‌سازی ترکر گیت‌هاب (Cairn Phase 1 Verification & Tracker Sync):**
  - ثبت خطوط لجر همراه شواهد تایپ‌شده برای ایشیوهای ۹۳ و ۹۴ از طریق ابزار `ledger_append`.
  - ایجاد مستند اعتبارسنجی رسمی `.cairn/plans/phases/01-server-diagnostics-and-failure-root-cause-audit/VERIFICATION.md` با وضعیت `VERIFIED`.
  - به‌روزرسانی وضعیت فاز ۱ در `.cairn/plans/roadmap.md` به `verified`.
  - تأیید انطباق کرن با `plan_drift` (صفر دریفت؛ همه ۸ ایشیو در وضعیت ok).
  - به‌روزرسانی ایشیوهای فازهای ۲ تا ۴ در ترکر گیت‌هاب: ایشیوهای #95، #96، #98 و #99 به وضعیت `in_progress` ارتقا یافتند و کامنت‌های پیشرفت فنی به همراه شواهد کامیت ثبت گردید.

## 📁 فایل‌های تغییریافته
- `.cairn/plans/phases/01-server-diagnostics-and-failure-root-cause-audit/LEDGER.md`
- `.cairn/plans/phases/01-server-diagnostics-and-failure-root-cause-audit/VERIFICATION.md`
- `.cairn/plans/roadmap.md`
- `.cairn/outlook.json`
- `.cairn/tracker-marker.json`
- `.context/STATE.md`

## 🎯 تسک دقیق بعدی
پیشبرد فاز ۲ (`cairn work 2`): ادامه تست چرخه حیات بارنامه برای راننده محمدزاده، بررسی نهایی وضعیت فورواردر پیامک، و اعتبارسنجی تراکنش‌های صدور با پروتکل Two-Witness Proof.

## 🧠 تصمیمات فنی و چرایی
- فاز ۱ رسماً با شواهد تایپ‌شده لاگ‌های زنده سرور و تست‌های خودکار بسته شد تا ترکر و گیت کاملاً منطبق باشند.
- ارتقای ایشیوهای #96، #98، #99 به `in_progress` شکاف ترکر را برطرف کرد و تضمین نمود کارهای استقراریافته در کامیت `2405ed6` در وضعیت ایشیوها منعکس شده‌اند.

## ⚠️ نکات حساس و موانع
- متغیر `ALLOW_LIVE_SUBMIT` کماکان `false` نگه داشته شده است تا ثبت زنده بارنامه صرفاً تحت نظارت اپراتور انجام شود.

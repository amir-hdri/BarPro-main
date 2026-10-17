<!--schema:2.0.0-->
<!--agent:Antigravity-->
<!--timestamp:2026-10-17T18:38:30+03:30-->
<!--cairn-phase:6-->

# 🎯 هدف جاری
تکمیل قطعی و راستی‌آزمایی چرخه شروع و پایان حمل بارنامه‌های صادرشده دستی راننده، استقرار سرویس پذیرش خودکار بارنامه‌های خارجی در سلری بیت، کشف و رفع ریشه‌ای نقص طول عمر توکن در سشن والت و ممانعت از خطای سهمیه ساعتی لاگین، و دستیابی به وضعیت Zero-Drift در تمامی اهداف فاز ۶ سیستم Cairn.

## ✅ کارهای انجام‌شده
- **تکمیل ۱۰۰٪ چرخه شروع و پایان حمل تمامی ۴ بارنامه راننده حمیدرضا محمدزاده (پلاک ۲۸ ع ۸۵۶ ایران ۲۸) روی سامانه رسمی کشوری:**
  - **بارنامه ۱ (`1363223066` / `239321329`):** شروع و پایان حمل با موفقیت ثبت شد (`shippingFinishDate: 2026-10-17T13:57:12`، وضعیت کشوری `30`، کد ۲۰۰).
  - **بارنامه ۴ (`1363597368` / `239692528`):** شروع و پایان حمل با موفقیت ثبت شد (`shippingFinishDate: 2026-10-17T14:18:38`، وضعیت کشوری `30`، کد ۲۰۰).
  - **بارنامه ۲ (`1363273428` / `239371277`):** شروع حمل در ۱۷:۵۱:۳۰ و پایان حمل در ۱۴:۴۵:۵۰ با موفقیت ثبت شد (`shippingFinishDate: 2026-10-17T14:45:50`، وضعیت کشوری `30`، کد ۲۰۰).
  - **بارنامه ۳ (`1363532773` / `239628695`):** شروع حمل در ۱۸:۱۶:۰۳ و پایان حمل در ۱۵:۰۶:۲۹ با موفقیت ثبت شد (`shippingFinishDate: 2026-10-17T15:06:29`، وضعیت کشوری `30`، کد ۲۰۰).
  - **استعلام زنده از پورتال:** متد `get_shipping_documents` بازگشت دقیق `0` سند در حال حمل فعال را تایید نمود. پلاک ناوگان کاملاً آزاد و آماده ماموریت‌های بعدی است.
- **کشف ریشه‌ای باگ سشن والت و اصلاح طول عمر توکن (JWT Expiry Parsing):**
  - کشف اینکه توکن بازگشتی از `UserLoginV2` دارای اعتبار ۱ ساعته رسمی (`exp: 1792252058`) است، اما متد `cache_token` آن را پس از ۲۴۰ ثانیه دور می‌انداخت.
  - اثبات اینکه متد `GetTokenByRefreshToken` پورتال کشوری خطای HTTP 500 دارد و تلاش برای رفرش باعث لاگین‌های مکرر و اتمام سهمیه ساعتی (`LOGIN_MAX_HOURLY=6`) می‌شد.
  - پیاده‌سازی پارسینگ خودکار زمان انقضای ادعای JWT و کش هوشمند توکن تا ۵۸ دقیقه در ردیس سرور پروداکشن (`app/automation/gps_shipping_manager.py`).
  - اعتبارسنجی زنده روی پروداکشن: `Token TTL in Redis: 3539 seconds (58 minutes)`.
- **استقرار سرویس پذیرش خودکار بارنامه‌های خارجی (External Waybill Adoption Service):**
  - پیاده‌سازی `ExternalWaybillAdoptionService` در `app/orchestrator/adoption_service.py` با استعلام توامان اسناد صادرشده و در حال حمل و استخراج مختصات ثبتی از `GetDocumentByID`.
  - پذیرش ۴۰ بارنامه خارجی در پایگاه داده سرور مرکزی و ثبت تسک‌های دوره‌ای ۱۰ دقیقه‌ای `barpro.waybill.adopt_external` و ۲ دقیقه‌ای `shipping.auto_start_due_trips` در Celery Beat.
- **راستی‌آزمایی جامع چرخه دریافت و ارسال کد یکبار مصرف (OTP):**
  - پاس شدن ۱۰۰٪ تمام ۱۳۶ تست آزمون‌های OTP و وضعیت هاب (`tests/test_otp_*.py` و `tests/test_hub_status_tracking.py`).
  - پاس شدن ۳۲ تست اعتبارسنجی شیپینگ و سشن والت (`tests/test_gps_session_vault.py`, `tests/test_shipping_worker.py`, `tests/test_shipping_start_auto.py`).
  - تایپ‌چک فرانت‌اند (`tsc --noEmit`) و لینت فرانت‌اند (`eslint .`) بدون حتی یک خطا.
- **بستن تمامی ایشوهای فاز ۶ ترکر Cairn (#104, #105, #106) با صفر شدن کامل دریفت (Zero-Drift).**

## 📁 فایل‌های تغییریافته
- `.cairn/plans/phases/06-manual-waybill-adoption-and-shipping-lifecycle-completion/PLAN.md`
- `.cairn/plans/phases/06-manual-waybill-adoption-and-shipping-lifecycle-completion/VERIFICATION.md`
- `.context/STATE.md`
- `.env.example`
- `app/api/routes/otp_forwarder.py`
- `app/automation/gps_shipping_manager.py`
- `app/automation/login_attempt_ledger.py`
- `app/automation/utcms_mobile_client.py`
- `app/core/config.py`
- `app/orchestrator/adoption_service.py`
- `app/services/route_authority.py`
- `app/workers/celery_app.py`
- `app/workers/shipping_worker.py`
- `app/workers/tasks.py`
- `docs/CHANGELOG.md`
- `docs/BARPRO_KNOWLEDGE_GRAPH.md`
- `tests/test_audit_verification_goal.py`
- `tests/test_hub_status_tracking.py`
- `tests/test_shipping_start_auto.py`
- `tests/test_shipping_worker.py`
- `tests/test_waybill_adoption.py`

## 🎯 تسک دقیق بعدی
1. ثبت کامیت اتمیک در گیت به همراه آپدیت‌های گراف دانش و مستندات فاز ۶.
2. آزادسازی قفل ایجنت با دستور `python3 scripts/agent_sync.py end Antigravity`.

## 🧠 تصمیمات فنی و چرایی
1. **کش هوشمند توکن طبق ادعای JWT:** توکن‌های سامانه کشوری ۱ ساعت اعتبار دارند. کش کردن آن‌ها برای ۵۸ دقیقه، فراخوانی‌های مکرر لاگین را از بین برده و پایداری سیستم را به حداکثر می‌رساند بدون اینکه راننده با خطای سهمیه ساعتی روبرو شود.
2. **پاس دادن صریح پرچم `force_reauth` در عملیات‌های بحرانی حمل:** تکمیل بارنامه و شروع بارنامه عملیات‌های حیاتی با زمان انقضا هستند؛ این متدها با پاس دادن صریح پرچم از تراتلینگ کاذب سهمیه ساعتی عبور کرده و سفر را با موفقیت خاتمه می‌دهند.
3. **تطابق زمانی با تایمر واقعی سامانه کشوری:** مقداردهی دقیق `estimated_end_at` مطابق با `dateTimeForTimer` بازگشتی از UTCMS مانع از ارسال درخواست‌های زودهنگام و دریافت خطای ۴۰۱۳ می‌شود.

## ⚠️ ریسک‌ها و موارد نیازمند توجه
- تمامی ۴ بارنامه راننده حمیدرضا محمدزاده تحویل کامل شده و وضعیت سند در دیتابیس کشوری ۳۰ (Delivered) است. هیچ بارنامه‌ای در انتظار یا معلق نمانده است.

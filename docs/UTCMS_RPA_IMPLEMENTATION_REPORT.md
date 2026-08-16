# گزارش جامع نوسازی و بازمهندسی ربات ثبت بارنامه UTCMS (فازهای ۱.۵ تا ۱.۱۶)

**پروژه:** سامانه BarPro — ربات اختصاصی ثبت خودکار بارنامه در پورتال UTCMS (`barname.utcms.ir`)  
**نسخه گزارش:** ۲.۰.۰  
**تاریخ تکمیل:** ۲۴ مرداد ۱۴۰۵ (15 August 2026)  
**روش ثبت:** Playwright Web Automation (مرورگر واقعی) بدون وابستگی به APIهای غیررسمی، با تفکیک قطعی حالت متنی (`user_text`) از نقشه و مختصات جغرافیایی.

---

## ۱. خلاصه اجرایی و دستاوردها

در این پروژه، معماری ربات بارنامه BarPro برای هماهنگی ۱۰۰٪ با پورتال رسمی UTCMS بازمهندسی گردید. تمامی فرآیندهای پر کردن فرم، انتخاب مبدأ و مقصد، اعتبارسنجی ورودی، بازخوانی مقادیر از DOM (Read-Back)، مدیریت پنجره OTP، کلید یکتای مسیر، و تطبیق پس از ثبت (Reconciliation) مورد بازنویسی و ارتقا قرار گرفتند.

### مهم‌ترین شاخص‌های عملکردی پیاده‌سازی شده:
1. **جدول ماتریس فیلدها (Field Matrix):** تدوین ماتریس کامل ۱۴ فرم پورتال (`docs/UTCMS_FIELD_MATRIX.md`) به همراه مشخصات فنی، انتخابگرهای اصلی و جایگزین، شروط اعتبارسنجی و فیکسچر ماشین‌خوان (`tests/fixtures/utcms/field_matrix.json`).
2. **قرارداد مسیر متنی (`user_text` Mode):** تعریف سند رسمی (`docs/USER_TEXT_ROUTE_CONTRACT.md`) و الزام حالت متنی برای تمام درخواست‌های مبدأ و مقصد. مختصات جغرافیایی و GPS به صورت کامل نادیده گرفته شده و ژئوکدینگ معکوس حذف گردید.
3. **بازمهندسی `LocationSelector`:** ترتیب اجرای گام‌به‌گام و اتمیک (فعال‌سازی تب $\to$ انتخاب استان $\to$ انتظار بارگذاری AJAX شهرها $\to$ انتخاب قطعی شهر $\to$ بازخوانی شهر $\to$ درج آدرس $\to$ بازخوانی آدرس $\to$ کنترل خطاهای فرم). منع قطعی حدس زدن یا انتخاب گزینه اول.
4. **پالایش اعتبارسنجی Payload:** کنترل الگوریتمی رقم کنترلی کد ملی ۱۰ رقمی، منع نام‌های تک‌کلمه‌ای تکراری، اعتبارسنجی پلاک ملی و مناطق آزاد، و ممانعت از پر کردن مقادیر با حدس یا پیش‌فرض.
5. **ایمنی جهش‌ها (Mutation Safety & 3-Way Proof):** ثبت نیات (Intent)، ثبت هش درخواست، قفل همزمانی راننده (حداکثر ۱ ثبت همزمان به ازای هر راننده)، منع تلاش مجدد خودکار روی POSTهای جهشی، و انتقال وضعیت به `UNKNOWN` در موارد پاسخ مبهم.
6. **تطبیق واقعی (Reconciliation):** بازخوانی و استعلام وضعیت با DataTables APIs پورتال شامل `/Barname/History/GetHistoryFirstList`، `/Barname/DocumentList/GetIssuedDocumentsNew`، و `/Barname/Document/showTrackingCode`.

---

## ۲. گزارش جزئیات فاز به فاز

### فاز ۱.۵: ماتریس فیلدها و اثبات Locatorها (Field Matrix)
- مستندات جامع در [`docs/UTCMS_FIELD_MATRIX.md`](file:///Users/amirheidari/GitHub/BarPro-main/docs/UTCMS_FIELD_MATRIX.md) و [`docs/UTCMS_ROUTE_FIELD_MATRIX.md`](file:///Users/amirheidari/GitHub/BarPro-main/docs/UTCMS_ROUTE_FIELD_MATRIX.md).
- فیکسچر JSON در [`tests/fixtures/utcms/field_matrix.json`](file:///Users/amirheidari/GitHub/BarPro-main/tests/fixtures/utcms/field_matrix.json).
- آزمون‌های اعتبارسنجی ساختار و Read-Back در [`tests/test_utcms_field_matrix.py`](file:///Users/amirheidari/GitHub/BarPro-main/tests/test_utcms_field_matrix.py) (۵ آزمون موفق).

### فاز ۱.۶: حالت اجباری `user_text` برای مبدأ و مقصد
- تدوین سند قرارداد در [`docs/USER_TEXT_ROUTE_CONTRACT.md`](file:///Users/amirheidari/GitHub/BarPro-main/docs/USER_TEXT_ROUTE_CONTRACT.md).
- اصلاح اسکیماهای [`app/schemas/waybill.py`](file:///Users/amirheidari/GitHub/BarPro-main/app/schemas/waybill.py) و [`app/schemas/multitenant.py`](file:///Users/amirheidari/GitHub/BarPro-main/app/schemas/multitenant.py).
- بازنویسی تابع `compute_canonical_route_key` جهت محاسبه کلید یکتای مسیر منحصراً از روی مقادیر متنی کاربر (`province + city + district + address`) بدون دخالت مختصات.
- آزمون‌های اختصاصی در [`tests/test_user_text_route_contract.py`](file:///Users/amirheidari/GitHub/BarPro-main/tests/test_user_text_route_contract.py) (۴ آزمون موفق).

### فاز ۱.۷: اصلاح و نوسازی Location Selector
- بازنویسی متدهای `select_location` و `_try_utcms_direct_fill` در [`app/automation/location_selector.py`](file:///Users/amirheidari/GitHub/BarPro-main/app/automation/location_selector.py).
- اضافه شدن متدهای بازخوانی مستقیم DOM (`_read_element_value`, `_read_selected_option`).
- تطابق فازی گزینه‌ها منحصراً در صورت تطابق یکتا (Unique Match) و ممانعت از انتخاب رندوم یا گزینه اول.
- آزمون‌های گزینش مکان و صحت Read-Back در [`tests/test_user_text_location_selection.py`](file:///Users/amirheidari/GitHub/BarPro-main/tests/test_user_text_location_selection.py) و [`tests/test_route_readback.py`](file:///Users/amirheidari/GitHub/BarPro-main/tests/test_route_readback.py) (۷ آزمون موفق).

### فاز ۱.۸: پالایش اعتبارسنجی ورودی بارنامه
- افزودن `_validate_iranian_national_code` جهت بررسی الگوریتم Checksum کدهای ملی راننده و اشخاص.
- جلوگیری از ثبت نام‌های تک‌کلمه‌ای تکراری برای اشخاص حقیقی (مانند "علی علی").
- الزام وجود نام شرکت برای اشخاص حقوقی.
- کنترل مثبت بودن وزن کالا و کامل بودن نوع بسته‌بندی.
- آزمون‌های پالایش در [`tests/test_waybill_payload_validation.py`](file:///Users/amirheidari/GitHub/BarPro-main/tests/test_waybill_payload_validation.py) (۸ آزمون موفق).

### فاز ۱.۹: اصلاح WaybillEnhancedManager
- تفکیک قطعی مسیر متنی از نقشه در [`app/automation/waybill_enhanced.py`](file:///Users/amirheidari/GitHub/BarPro-main/app/automation/waybill_enhanced.py).
- عدم فراخوانی `calculate_distance` یا ماژول‌های نقشه در حالت `user_text`.
- گنجاندن ساختار کامل بازخوانی‌شده مسیر در خروجی اجرایی (`result["route"]`).

### فاز ۱.۱۰: سرویس مدیریت و پایدارسازی مسیر
- اصلاح متد `_build_route_key` در [`app/services/management_service.py`](file:///Users/amirheidari/GitHub/BarPro-main/app/services/management_service.py) جهت استفاده از تابع قطعی `compute_canonical_route_key`.
- Nullable بودن و اختیاری بودن فیلدهای Lat/Lng در دیتابیس و مدیریت موجودیت‌ها.

### فاز ۱.۱۱: چرخه حیات OTP و Submission Gate
- سرویس `UTCMSSubmissionGate` وظیفه تشخیص پنجره زمانی رایگان (OTP-free) و پنجره‌های نیازمند پیامک را بر عهده دارد.
- مشاغل در صورت فعال بودن وضعیت OTP در وضعیت `waiting_submission_window` نگه داشته می‌شوند تا منابع سرور و ورکرها هدر نرود.

### فاز ۱.۱۲: ایمنی جهش‌ها (Mutation Safety) و Idempotency
- تخصیص قفل همزمانی راننده (`driver_lock`) جهت تضمین حداکثر ۱ فرآیند ثبت فعال به ازای هر راننده.
- عدم تکرار خودکار درخواست‌های تغییردهنده وضعیت (Mutation POSTs).
- در صورت بروز خطای تایم‌اوت یا قطع اتصال پس از ارسال نهایی، وضعیت شغل بلافاصله به `UNKNOWN` تغییر می‌یابد تا پیش از استعلام مجدد، ثبت تکراری انجام نشود.

### فاز ۱.۱۳: تطبیق واقعی با سامانه UTCMS (Reconciliation)
- تکمیل پیاده‌سازی [`app/orchestrator/utcms_reconciliation_scraper.py`](file:///Users/amirheidari/GitHub/BarPro-main/app/orchestrator/utcms_reconciliation_scraper.py).
- پشتیبانی همزمان از استعلام مستقیم شناسه سند (`showTrackingCode`)، تاریخچه اسناد (`GetHistoryFirstList`)، و اسناد صادرشده (`GetIssuedDocumentsNew`).

### فاز ۱.۱۴: پنل کاربری و API چندمستأجره
- پشتیبانی از بارگذاری اسناد بر اساس تفکیک هر راننده و مستأجر.
- نمایش مسیرهای متنی (استان، شهر، آدرس) در خروجی‌های API و پنل مدیریت.

### فاز ۱.۱۵: ۲۱ سناریوی آزمون جامع
- ایجاد و اجرای موفق مجموعه آزمون در [`tests/test_utcms_phase1_comprehensive.py`](file:///Users/amirheidari/GitHub/BarPro-main/tests/test_utcms_phase1_comprehensive.py) شامل ۲۱ سناریوی کلیدی پوشش‌دهنده کل چرخه حیات بارنامه.

---

## ۳. تحلیل ریسک‌ها و نکات حیاتی

1. **اعتبارسنجی WAF و IP ایرانی:**
   کلیه ارتباطات خروجی با پورتال UTCMS صرفاً باید از طریق پروکسی‌های Squid با IP معتبر ایرانی انجام پذیرد تا با WAF و خطای 444 مواجه نشوند.
2. **پایداری Session و احراز هویت:**
   در صورتی که سشن راننده منقضی شود، سیستم بلافاصله از لاگین سریع HTTP به همراه حل خودکار کپچا (CNN Solver) استفاده می‌کند.
3. **تغییرات ساختار DOM پورتال:**
   سلکتورهای اصلی و جایگزین در `selectors.py` و `UTCMS_FIELD_MATRIX.md` ثبت شده‌اند. در صورت تغییر در کلاس‌های CSS پورتال، مکان‌یاب‌های Fallback بر اساس `name` و ساختار DOM فرم فعال خواهند بود.

---

## ۴. اقلام نیازمند تأیید در محیط زنده (Live Capture)

- [ ] استعلام زنده نمونه کد رهگیری صادرشده از متد `showTrackingCode` با سشن واقعی.
- [ ] آزمایش ارسال زنده در پنجره زمانی غیرپیک با راننده نمونه آزمایشی.
- [ ] بازبینی لاگ‌های تفصیلی Nginx و ورکرها در زمان ثبت آزمایشی.

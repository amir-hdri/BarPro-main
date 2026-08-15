# ممیزی و خط مبنای اتوماسیون BarPro UTCMS (Baseline Audit)

**تاریخ ایجاد:** ۱۵ اوت ۲۰۲۶ (۱۴۰۵/۰۵/۲۴)  
**نسخه:** 1.0.0  
**هدف:** مستندسازی خط مبنای سامانه، نتایج ممیزی `utcms_scraper`، فهرست کمبودها بر اساس فایل و شماره خط، و بررسی امنیتی رازها و اعتبارسنجی اولیه.

---

## ۱. نتایج آزمون خط مبنا (Test Suite Baseline)

- **مجموع تست‌های اجراشده:** ۷۷۷
- **تعداد موفق (Passed):** ۷۷۴
- **تعداد چشم‌پوشی‌شده (Skipped):** ۳
- **تعداد شکست (Failed):** ۰
- **زمان اجرا:** ~۶ دقیقه و ۴۶ ثانیه

> تست `tests/test_location_service_and_routes.py::test_api_v1_location_routes` که به دلیل عدم تطابق ساختار خروجی لیست با آبجکت شکست می‌خورد، بررسی و اصلاح شد و تمامی تست‌های فعلی در وضعیت ۱۰۰٪ پاس قرار گرفتند.

---

## ۲. ممیزی `utcms_scraper` و قرنطینه داده‌های محرمانه

### ۲.۱ ساختار و داده‌های کشف‌شده در اسکرپر:
- پوشه اسکرپر در مسیر بیرونی `/Users/amirheidari/GitHub/scrapy/utcms_scraper/` شامل فایل‌های ضبط شبکه (`extract_network.json`)، ساختار فرم‌ها (`extract_forms.json`)، صفحات HTML استخراج‌شده (`doclist.html`)، و مستندات رسمی وب‌سرویس (`ws-guide.txt` و `FIELD_SPEC.md`) است.
- **اطلاعات حساس شناسایی‌شده:**
  - کدملی و اطلاعات هویتی تستی/واقعی رانندگان در `session_cookies.json`، `session_storage_state.json` و `UTCMS_COMPLETE_REPORT.md`.
  - کوکی‌های سشن (`.Aggregation.Session`, `Barname`, `ApplicationToken`, `cookiesession1`).
- **خط‌مشی امنیتی و قرنطینه:**
  - مسیر اسکرپر در مخزن اصلی BarPro نیست و نباید وارد git شود.
  - فایل `.gitignore` پروژه BarPro ممیزی شد؛ تمامی فایل‌های `utcms_state_*.json`، `.auth/`، `.env`، `remote_*.json`، لاگ‌ها و شات‌های احراز هویت در وضعیت ignore قرار دارند.
  - تمامی فیکسچرهای تستی در `tests/fixtures/utcms/` به‌صورت کاملاً **Sanitized و Synthetic** (جایگزینی با کدملی‌های نمونه `3830000000`، مقادیر رداکت‌شده و بدون هرگونه توکن و کوکی واقعی) ذخیره خواهند شد.

---

## ۳. جدول جامع کمبودها و نواقص فنی (Deficiency Matrix)

| ردیف | مؤلفه | فایل و شماره خط | شرح کمبود / آسیب‌پذیری | اولویت |
|:---:|:---|:---|:---|:---:|
| ۱ | **مدل وضعیت Job** | [`app/orchestrator/state_machine.py:4-20`](file:///Users/amirheidari/GitHub/BarPro-main/app/orchestrator/state_machine.py#L4-L20) | فقدان وضعیت `waiting_submission_window`؛ وضعیتهای `UNKNOWN` و `RECONCILING` نیازمند همگام‌سازی با چرخه ثبت بدون OTP هستند. | بحرانی (P0) |
| ۲ | **ثبت Intent و لاگ جهش‌ها** | [`app/models_multitenant.py:291-378`](file:///Users/amirheidari/GitHub/BarPro-main/app/models_multitenant.py#L291-L378) | عدم ذخیره پایدار `document_id`، دایجست درخواست (`request_digest`) و زمان ارسال قطعی قبل از کلیک Submit روی مدل `WaybillJob`. | بحرانی (P0) |
| ۳ | **دروازه سراسری ثبت UTCMS** | [`app/services/rpa_scheduler_service.py:94-248`](file:///Users/amirheidari/GitHub/BarPro-main/app/services/rpa_scheduler_service.py#L94-L248) | عدم وجود سرویس `UTCMSSubmissionGate`؛ زمان‌بندی Jobها وضعیت زنده سامانه را بررسی نکرده و در زمان فعال بودن OTP بودجه تلاش را می‌سوزاند. | بحرانی (P0) |
| ۴ | **پایش تطبیقی وضعیت سامانه** | [`app/models_rpa.py`](file:///Users/amirheidari/GitHub/BarPro-main/app/models_rpa.py) | فقدان جدول ذخیره وضعیت سامانه (`utcms_gate_states` / `system_observations`) با فیلدهای `state`, `observed_at`, `valid_until`, `next_probe_at`, `source`, `worker_id`, `evidence`. | بحرانی (P0) |
| ۵ | **انتقال Mutation-Safe** | [`app/automation/waybill_enhanced.py:3720-3770`](file:///Users/amirheidari/GitHub/BarPro-main/app/automation/waybill_enhanced.py#L3720-L3770) | امکان تلاش مجدد در زمان بروز خطای پس از ارسال یا عدم وجود کد رهگیری؛ ضرورت انتقال قطعی به `UNKNOWN` و شروع Reconciliation قبل از هر اقدام مجدد. | بحرانی (P0) |
| ۶ | **اسکرپر آشتی و اعتبارسنجی** | [`app/orchestrator/utcms_reconciliation_scraper.py:34-106`](file:///Users/amirheidari/GitHub/BarPro-main/app/orchestrator/utcms_reconciliation_scraper.py#L34-L106) | استفاده از آدرس‌های هاردکد ساختگی (`/Barname/Document/History`) و سلکتورهای جنریک به‌جای اندپوینت‌های واقعی DataTables نظیر `/Barname/History/GetHistoryFirstList` و `/Barname/Document/showTrackingCode`. | بحرانی (P0) |
| ۷ | **بررسی Eventual Consistency** | [`app/orchestrator/reconciliation_service.py:22-130`](file:///Users/amirheidari/GitHub/BarPro-main/app/orchestrator/reconciliation_service.py#L22-L130) | عدم پیاده‌سازی فواصل زمانی تطبیق تدریجی (۱۵ ثانیه، ۴۵ ثانیه، ۲ دقیقه، ۵ دقیقه) در مواجهه با تأخیر ایندکس‌شدن بارنامه در UTCMS. | بالا (P1) |
| ۸ | **قفل توزیع‌شده راننده و Probe** | [`app/workers/waybill_worker.py:929-980`](file:///Users/amirheidari/GitHub/BarPro-main/app/workers/waybill_worker.py#L929-L980) | لزوم اطمینان از تک‌ثبتی بودن هر راننده در هر لحظه و تفکیک پروب کم‌نرخ سراسری از اجرای Jobها. | بالا (P1) |
| ۹ | **متریک‌های دیده‌پذیری (Observability)** | [`app/monitoring/metrics.py`](file:///Users/amirheidari/GitHub/BarPro-main/app/monitoring/metrics.py) | فقدان متریک‌های استاندارد پرومتئوس برای وضعیت Gate، خطاهای مبهم، کشف OTP و موفقیت/عدم‌موفقیت Reconciliation. | متوسط (P2) |
| ۱۰ | **پنل و APIهای تاریخچه رانندگان** | [`app/api/routes/user_reporting.py`](file:///Users/amirheidari/GitHub/BarPro-main/app/api/routes/user_reporting.py) | لزوم نمایش شفاف وضعیت‌های `UNKNOWN`، `RECONCILING` و جلوگیری از نمایش ثبت موفق بدون شواهد سه‌گانه. | متوسط (P2) |

---

## ۴. تأیید الزامات امنیتی و خطوط قرمز

1. مقدار پیش‌فرض `ALLOW_LIVE_SUBMIT=false` در کل کدبیس تضمین می‌شود.
2. هیچ کد رهگیری ساختگی یا نتیجه موفق بدون شواهد سه‌گانه (RPA + دیتابیس + استعلام UTCMS) ثبت نخواهد شد.
3. هیچ اطلاعات محرمانه‌ای در متن تعهدات، لاگ‌ها یا فیکسچرها قرار نگرفته و نخواهد گرفت.

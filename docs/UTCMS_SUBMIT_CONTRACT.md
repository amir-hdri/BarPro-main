# قرارداد تعامل و ثبت بارنامه در سامانه UTCMS (Submit & Query Contract)

**تاریخ تدوین:** ۱۵ اوت ۲۰۲۶ (۱۴۰۵/۰۵/۲۴)  
**نسخه:** 1.0.0  
**مرجع استخراج:** آزمون‌های میدانی BarPro و تحلیل داده‌های `utcms_scraper`

---

## ۱. جدول اندپوینت‌ها، ورودی‌ها، خروجی‌ها و کدهای وضعیت

| اندپوینت | متد | پارامترهای ورودی کلیدی | ساختار خروجی | Status Code | سناریوهای خطا / پیام‌ها |
|---|:---:|---|---|:---:|---|
| `/Barname/Account/OldLogin` | POST | `NationalCode`, `Password`, `DNTCaptchaInputText`, `DNTCaptchaToken`, `CapType=1`, `RequestVerificationToken` | `{"success": true/false, "message": "...", "data": null}` | 200 / 400 | `400`: توکن CSRF نامعتبر<br>`200 (success=false)`: رمز نادرست یا کپچای اشتباه |
| `/Barname/Document/GetCostSettings` | GET | بدون ورودی (نیاز به سشن معتبر) | `{"resultCode": 200, "obj": {"otpValidityPeriod": 5, "tajmiiFlag": true, "mapFlag": true, ...}}` | 200 / 408 / 444 | `408`: محدودیت سراسری صدور<br>`444`: شناسایی هدر/UA غیرمجاز |
| `/Barname/Document/fillStates` | GET | بدون ورودی | `{"resultCode": 200, "obj": [{"id": 1, "name": "تهران", ...}]}` | 200 | لیست ۳۱ استان |
| `/Barname/Document/fillgridesender` | POST | DataTables params (`draw`, `start`, `length`, `function=fillgridesender`) | `{"draw": 1, "recordsTotal": N, "data": [...]}` | 200 | لیست فرستنده‌های ذخیره‌شده |
| `/Barname/Document/fillgrideReceiver` | POST | DataTables params (`draw`, `start`, `length`, `function=fillgrideReceiver`) | `{"draw": 1, "recordsTotal": N, "data": [...]}` | 200 | لیست گیرنده‌های ذخیره‌شده |
| `/Barname/Document/fillgridDriver` | POST | DataTables params (`function=fillgridDriver`) | `{"draw": 1, "recordsTotal": N, "data": [...]}` | 200 | لیست رانندگان ناوگان |
| `/Barname/Document/fillgridPelak` | POST | DataTables params (`function=fillgridPelak`) | `{"draw": 1, "recordsTotal": N, "data": [...]}` | 200 | لیست پلاک‌های ناوگان |
| `/Barname/PrintReport/printbarnameNew` | POST | فیلدهای فرم نهایی + `RequestVerificationToken` | HTML صفحه تایید / ریدایرکت / پاپ‌آپ OTP (`#FormSendOtpCode`) | 200 / 302 / 500 | `500`: خطای اعتبارسنجی سرویس‌های پشتی<br>نمایش مودال OTP در صورت نیاز به احراز |
| `/Barname/History/GetHistoryFirstList` | POST | DataTables params + `function=GetHistoryFirstList` + `data=[{"fromDate": "", "toDate": "", "docNo": "", ...}]` | `{"draw": 1, "recordsTotal": N, "data": [{"RowID": 1, "docNo": "...", "driverFullName": "...", ...}]}` | 200 / 500 | `500 ("اطلاعات یافت نشد")`: در صورت نبود رکورد مطابق فیلتر |
| `/Barname/DocumentList/GetIssuedDocumentsNew` | POST | DataTables params + `function=GetIssuedDocumentsNew` + `Cleanform=true` + `input=...` | `{"draw": 1, "recordsTotal": N, "data": [{"docNo": "...", "driverNationalCode": "...", "PelakNumber": "..."}]}` | 200 / 500 | `500`: نیاز به انتخاب جستجو |
| `/Barname/DocumentList/GetShippingDocumentNew` | POST | DataTables params + `function=GetShippingDocumentNew` + `Cleanform=true` + `input=...` | `{"draw": 1, "recordsTotal": N, "data": [{"docNo": "...", "shippingDate": "..."}]}` | 200 / 500 | `500`: نیاز به انتخاب جستجو |
| `/Barname/Document/showTrackingCode` | GET | `id={document_id}` | `{"resultCode": 200, "obj": {"trackingCode": "...", "issueDate": "..."}}` | 200 / 404 | نمایش مستقیم کد رهگیری سند با شناسه |

---

## ۲. رفتار نهایی Submit و نحوه مواجهه با OTP (`isOtpNeeded`)

1. **ارسال فرم نهایی:**
   - درخواست POST به `/Barname/PrintReport/printbarnameNew` ارسال می‌شود.
   - **حالت ۱ (OTP غیرفعال / سامانه آزاد):** سرور بارنامه را مستقیماً صادر نموده و صفحه تایید با کد رهگیری (`docNo` / `#TrackingCode`) یا ریدایرکت به صفحه چاپ بارنامه بازمی‌گردد.
   - **حالت ۲ (OTP فعال):** سرور مودال `#FormSendOtpCode` را نمایش می‌دهد که شامل فیلدهای ورودی کد ۶ رقمی و شمارنده اعتبار (معمولاً ۵ دقیقه) است.
2. **پایش تطبیقی وضعیت OTP:**
   - **تشخیص Passive (غیرمخرب):** با فراخوانی `/Barname/Document/GetCostSettings` تنظیمات پیکربندی دریافت می‌شود. با این حال، تنظیمات صرفاً پارامترهای عمومی را برمی‌گردانند و ممکن است به تنهایی رفتار قطعی SMS را در لحظه کلیک نهایی مشخص نکنند.
   - **اعلام صریح محدودیت Passive Probe:** سامانه UTCMS اندپوینت مجزای `is_otp_active_now` به‌صورت عمومی ارائه نمی‌دهد. بنابراین دروازه سراسری (`UTCMSSubmissionGate`) بر اساس:
     - ۱) تحلیل پاسخ‌های ثبت قبلی،
     - ۲) اجرای پروب کنترل‌شده تک‌کارگر با قفل توزیع‌شده Redis،
     - ۳) فرضیه بازه زمانی ۱۸:۰۰ تا ۰۸:۰۰ (صرفاً به‌عنوان Prediction و نه قانون صلب)،
     وضعیت سامانه را به یکی از حالات `otp_free`، `otp_required`، `unknown` یا `degraded` تغییر می‌دهد.

---

## ۳. فیکسچرهای ذخیره‌شده (Sanitized Fixtures)

تمامی فیکسچرهای بدون اطلاعات محرمانه در مسیر `tests/fixtures/utcms/` قرار دارند:
- `cost_settings_response.json`: تنظیمات زنده هزینه‌ها و OTP
- `history_first_list_response.json`: خروجی استاندارد استعلام تاریخچه اسناد با DataTables
- `issued_documents_response.json`: خروجی لیست اسناد صادرشده
- `shipping_documents_response.json`: خروجی اسناد در حال حمل
- `show_tracking_code_response.json`: خروجی دریافت مستقیم کد رهگیری
- `submit_otp_challenge_response.json`: ساختار پاسخ فعال‌شدن چالش OTP
- `submit_success_response.json`: ساختار پاسخ ثبت موفق و دریافت کد رهگیری

---

## ۴. مواردی که هنوز نیازمند Capture کنترل‌شده هستند

1. ساختار دقیق پاسخ JSON اندپوینت `printbarnameNew` در سناریوی AJAX Submit درون مرورگر (جهت استخراج سریع‌تر `document_id` پیش از رندر UI).
2. بررسی امکان وجود پاسخ‌های خاص هدر WAF نظیر `X-OTP-Enforced` یا نشانگرهای اختصاصی در پاسخ‌های استاتیک بدون ارسال فرم کامل.
3. رفتار سامانه در روزهای تعطیل رسمی و تفاوت احتمالی پنجره‌های زمانی بدون OTP.

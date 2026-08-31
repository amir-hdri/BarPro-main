# قرارداد تعامل و ثبت بارنامه در سامانه UTCMS (Submit & Query Contract)

**تاریخ تدوین:** ۱۵ اوت ۲۰۲۶ (۱۴۰۵/۰۵/۲۴)  
**نسخه:** 1.1.0
**آخرین بازنگری:** ۳۰ اوت ۲۰۲۶ — اندپوینت ثبت، قرارداد OTP و نقش `#GoFinalStep` اصلاح شد  
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
| `/Barname/Document/UpdateRegisterNewOld` | POST | فیلدهای فرم نهایی + `DNTCaptchaInputText`, `DNTCaptchaToken`, `IsDraft`, `SendSMS`, `sourceStateId`, `sourceCityId`, `sourceAddress`, `loadList`, `value`, `t1..t4` | `{"resultCode": 200, "obj": {"id": N, "isOtpNeeded": bool}}` | 200 / 500 | مسیر `#CapType == 1`؛ دو مسیر دیگر `UpdateRegisterNewNewOld` و `UpdateRegisterNewNew` |
| `/Barname/Document/IssueDocumentByOtpNew` | POST | `docId`, `code` | `{"resultCode": 200, ...}` | 200 / 500 | تأیید کد پیامکی پس از ساخته شدن رکورد سند |
| `/Barname/History/ResendOtpForIssueDocumen` | POST | `documentId` | `{"resultCode": 200, ...}` | 200 | ارسال مجدد کد پیامکی |
| `/Barname/PrintReport/printbarnameNew` | POST | فیلدهای سند + `RequestVerificationToken` | HTML صفحهٔ چاپ | 200 / 302 / 500 | مسیر **چاپ** است، نه ثبت |
| `/Barname/History/GetHistoryFirstList` | POST | DataTables params + `function=GetHistoryFirstList` + `data=[{"fromDate": "", "toDate": "", "docNo": "", ...}]` | `{"draw": 1, "recordsTotal": N, "data": [{"RowID": 1, "docNo": "...", "driverFullName": "...", ...}]}` | 200 / 500 | `500 ("اطلاعات یافت نشد")`: در صورت نبود رکورد مطابق فیلتر |
| `/Barname/DocumentList/GetIssuedDocumentsNew` | POST | DataTables params + `function=GetIssuedDocumentsNew` + `Cleanform=true` + `input=...` | `{"draw": 1, "recordsTotal": N, "data": [{"docNo": "...", "driverNationalCode": "...", "PelakNumber": "..."}]}` | 200 / 500 | `500`: نیاز به انتخاب جستجو |
| `/Barname/DocumentList/GetShippingDocumentNew` | POST | DataTables params + `function=GetShippingDocumentNew` + `Cleanform=true` + `input=...` | `{"draw": 1, "recordsTotal": N, "data": [{"docNo": "...", "shippingDate": "..."}]}` | 200 / 500 | `500`: نیاز به انتخاب جستجو |
| `/Barname/Document/showTrackingCode` | GET | `id={document_id}` | `{"resultCode": 200, "obj": {"trackingCode": "...", "issueDate": "..."}}` | 200 / 404 | نمایش مستقیم کد رهگیری سند با شناسه |

---

## ۲. رفتار نهایی Submit و نحوه مواجهه با OTP (`isOtpNeeded`)

> **بازنگری ۳۰ اوت ۲۰۲۶:** بند زیر با خواندن مستقیم `hagigihogugitemplate.js` و
> inventory زندهٔ مرحلهٔ نهایی اصلاح شد. ادعای قبلی که ثبت نهایی به
> `/Barname/PrintReport/printbarnameNew` می‌رود **نادرست** بود؛ آن اندپوینت مسیر
> چاپ است. اندپوینت ذخیره با مقدار `#CapType` تعیین می‌شود. شرح کامل در
> [UTCMS_SITE_BEHAVIOR_AND_BOT_RESPONSE.md](UTCMS_SITE_BEHAVIOR_AND_BOT_RESPONSE.md).

1. **ارسال فرم نهایی:** کلیک روی `#btnRegisterFinished` («ثبت نهایی سند حمل»)
   ذخیره را POST می‌کند. اندپوینت بر اساس فیلد مخفی `#CapType`:

   | `#CapType` | کپچا | اندپوینت |
   |:---:|---|---|
   | `0` | ویجت `window.cap` + `#CapToken` | `POST /Barname/Document/UpdateRegisterNewNewOld` |
   | `1` | DNTCaptcha (**مقدار مشاهده‌شدهٔ زنده**) | `POST /Barname/Document/UpdateRegisterNewOld` |
   | سایر | `#CaptchaCode` | `POST /Barname/Document/UpdateRegisterNewNew` |

   پاسخ: `{"resultCode": 200, "obj": {"id": <documentId>, "isOtpNeeded": bool}}`

   - **`isOtpNeeded == false`:** `showTrackingCode` بلافاصله اجرا می‌شود.
   - **`isOtpNeeded == true`:** سایت `#DocumentId = obj.id` می‌گذارد و مودال
     **`#GetOptCodeModal`** را باز می‌کند (نه `#FormSendOtpCode`). کد در `#otp`
     وارد و با `#submitOtp` به
     `POST /Barname/Document/IssueDocumentByOtpNew {docId, code}` فرستاده می‌شود.
     ارسال مجدد: `POST /Barname/History/ResendOtpForIssueDocumen {documentId}`.
   - در هر دو حالت کد رهگیری از
     `GET /Barname/Document/showTrackingCode?id=<objid>` در `#TrackingCodeNumber`
     می‌نشیند و **خودِ UTCMS روی `#GoFinalStep` کلیک می‌کند**. پس `#GoFinalStep`
     دکمهٔ ناوبری پیش از ثبت نیست و پیش از ذخیره `display:none` است؛ سیگنال
     آمادگی، visible بودن `#btnRegisterFinished` است.
   - **هشدار ایمنی:** رکورد سند **پیش از** تأیید OTP ساخته می‌شود. ثبت داخل پنجرهٔ
     OTP بدون داشتن کد، سند نیمه‌صادرشده باقی می‌گذارد.
2. **پایش تطبیقی وضعیت OTP:**

   - **تشخیص Passive (غیرمخرب):** با فراخوانی `/Barname/Document/GetCostSettings` تنظیمات پیکربندی دریافت می‌شود. با این حال، تنظیمات صرفاً پارامترهای عمومی را برمی‌گردانند و ممکن است به تنهایی رفتار قطعی SMS را در لحظه کلیک نهایی مشخص نکنند.
   - **اعلام صریح محدودیت Passive Probe:** سامانه UTCMS اندپوینت مجزای `is_otp_active_now` به‌صورت عمومی ارائه نمی‌دهد. بنابراین دروازه سراسری (`UTCMSSubmissionGate`) بر اساس:
     - ۱) تحلیل پاسخ‌های ثبت قبلی،
     - ۲) اجرای پروب کنترل‌شده تک‌کارگر با قفل توزیع‌شده Redis،
     - ۳) فرضیه بازه زمانی ۱۷:۳۰ تا ۰۸:۰۰ به وقت تهران (صرفاً به‌عنوان Prediction و نه قانون صلب)،
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

1. پاسخ زندهٔ `UpdateRegisterNewOld` در یک ثبت واقعی موفق (ساختار از سورس استخراج شده، ولی هنوز یک ثبت زندهٔ کامل ضبط نشده است).
2. بررسی امکان وجود پاسخ‌های خاص هدر WAF نظیر `X-OTP-Enforced` یا نشانگرهای اختصاصی در پاسخ‌های استاتیک بدون ارسال فرم کامل.
3. رفتار سامانه در روزهای تعطیل رسمی و تفاوت احتمالی پنجره‌های زمانی بدون OTP.

---

## ۵. پیش‌شرط‌های الزامی پیش از هر Submit

این بند از 2026-08-27 اضافه شده و بر همهٔ مسیرهای ثبت حاکم است:

1. ترتیب ناوبری `OldLogin → Notification → کلیک منو → Document/HagigiHogugi` روی
   همان session احرازشده؛ deep-link سرد پاسخ 408 می‌دهد.
2. عبور از گیت «زنده بودن JavaScript فرم» (jQuery، jQuery UI autocomplete،
   validator و handler دکمهٔ مرحلهٔ بعد). فرم DOM-کامل ولی بدون JavaScript
   نامعتبر است و نباید پر یا submit شود.
3. read-back موفق همهٔ فیلدهای اجباری، از جمله هر دو موبایل و مقدار/برچسب
   استان و شهر مبدا و مقصد.
4. POST ثبت دقیقاً یک بار، بدون retry و بدون مسیر دوم.

مرجع کامل: [UTCMS_BOT_BEHAVIOR_CONTRACT.md](UTCMS_BOT_BEHAVIOR_CONTRACT.md)

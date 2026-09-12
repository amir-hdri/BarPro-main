# گزارش بررسی و جایگزینی transport موبایل UTCMS

تاریخ بررسی: 2026-09-11
APK مرجع: /Users/amirheidari/Documents/Default Project/com.baarnameshahri-1.7.9.apk
SHA-256: d685873632736ab19e168daf6faf3af63791089f743341e81581bfcc25c13554

## خلاصه اجرایی

ربات به APK متصل نمی‌شود. APK فقط برای استخراج قرارداد API استفاده می‌شود و
ربات مستقیماً به API اپ متصل می‌گردد. در این مرحله transport جدید به‌صورت
opt-in پیاده شده است:

- UTCMS_TRANSPORT=web رفتار فعلی Playwright است و مقدار پیش‌فرض باقی می‌ماند.
- UTCMS_TRANSPORT=shadow فقط login/query خواندنی موبایل را اجرا می‌کند.
- UTCMS_TRANSPORT=mobile مسیر API موبایل را اجرا می‌کند؛ در حالت عادی dry-run
  است و هیچ mutation ارسال نمی‌کند.
- فقط ALLOW_LIVE_SUBMIT=true می‌تواند InsertDocumentHagigiV3 یا OTP mutation
  را باز کند؛ این فلگ باید برای یک job مستقل و تحت نظارت اپراتور فعال شود.

## شواهد APK

### قطعی (CODE-VERIFIED)

- Package: com.baarnameshahri
- Version: 1.7.9، version code 29
- React Native + Hermes؛ مجیک Hermes در bundle مشاهده شد.
- Base URL رمزگشایی‌شده:
  https://mobservices-barname.utcms.ir/baarnameh_sd/API
- wrapperهای endpoint در bundle شامل موارد زیر هستند:
  - POST /Account/UserLoginV2
  - POST /Utils/GetCaptcha
  - POST /Account/GetTokenByRefreshToken
  - POST /Document/InsertDocumentHagigiV3
  - POST /Document/IssueDocumentByOtp
  - POST /Document/ResendOtpForIssueDocument
  - POST /Document/GetDocTrackingCode
  - POST /Document/GetDocumentByID
  - POST /Document/GetIssuedDocuments
  - POST /Document/GetShippingDocuments
- بدنه login: nationalCode، password، capToken
- بدنه insert شامل: token، load، source، destination، sender،
  receiver، driverNationalCode، truck، insurance، value،
  bearingCost، rent، preRent، postRent، fuelType، sendSMS، docID،
  isDraft، selfDeclaredTimeOfStartShipment
- IssueDocumentByOtp بدنه docId و code دارد.
- هدرهای wrapper: Content-Type، ServicePassword، SecurityKey.
  فرمول مشاهده‌شده برای SecurityKey برابر MD5 رشته JSON بدنه است.
- ServicePassword شامل تاریخ روز در قالب YYYYMMDD است:
  9#$K<31l0?+;YYYYMMDD0KxsoSx)IFI&
- مجوزهای دوربین، میکروفون، مخاطبین، تماس و SMS در مانیفست مشاهده نشدند.
  مجوزهای location، notification، storage، biometric، foreground service و
  boot مشاهده شدند.

### نیازمند آزمون زنده (PENDING-LIVE)

- نوع دقیق بعضی فیلدهای load/source/destination/truck (object در برابر ID یا
  رشته فشرده) باید با پاسخ واقعی و حساب تست تأیید شود.
- ترتیب کلیدهای JSON و رفتار encoding یونیکد باید روی endpoint واقعی تأیید شود.
- قالب واقعی پاسخ obj/data/result و محل دقیق document ID/tracking code باید
  برای همه نسخه‌های حساب‌ها نمونه‌برداری شود.
- دو خانواده CAPTCHA در جریان اپ دیده می‌شود (ورود و مرحله صدور) و نوع/رفتار
  آن می‌تواند با زمان و وضعیت UTCMS تغییر کند؛ client نباید نوع را حدس بزند.
- `isOtpNeeded` و طول OTP باید با حساب تست تأیید شوند؛ PDF/ویدیو کد پنج‌رقمی را
  توصیف می‌کنند، اما decompile APK برای `SmsInput` مقدار `length=6` دارد.
- رفتار refresh token پس از encodeURIComponent باید با یک refresh read-only
  تأیید شود.
- scheme/deep-link، tamper detection، encryption storage و فعال بودن New
  Architecture از شواهد فعلی قرارداد عملیاتی قطعی محسوب نمی‌شوند.

## پیاده‌سازی در BarPro

- app/automation/mobile_payload_adapter.py: تبدیل صریح payload نرمال‌شده به DTO
  موبایل؛ فیلدهای اجباری بدون مقدار پیش‌فرض بررسی می‌شوند.
- app/automation/utcms_mobile_client.py: client غیرقابل retry برای API موبایل،
  امضای هدر، login، refresh، CAPTCHA، query، insert و OTP.
- app/automation/waybill_bot_multitenant.py: انتخاب transport و نتیجه امن
  validated، unknown یا tracking acknowledgement.
- app/automation/browser.py و app/workers/waybill_worker.py: در حالت mobile
  یا shadow هیچ browser process یا page ساخته نمی‌شود.
- app/core/config.py و .env.example: feature flag و timeoutهای جدید.
- tests/test_utcms_mobile_contract.py: تست mapping، digest، gate mutation و
  envelope login.

## گیت‌های ایمنی

1. نتیجه بدون tracking code هرگز success نهایی نیست؛ به unknown و
   reconciliation خواندنی می‌رود.
2. پاسخ مبهم یا timeout پس از insert هرگز retry یا resubmit نمی‌شود.
3. password، token، refresh token، cookie و پاسخ CAPTCHA وارد log/fixture نمی‌شوند.
4. حالت web rollback فوری است؛ تغییر env به UTCMS_TRANSPORT=web کافی است.
5. سه شاهد موفقیت همچنان لازم‌اند: tracking پاسخ، ذخیره همان کد، و History/Search
   مطابق در UTCMS. تا اثبات reconciliation موبایل، History وب شاهد سوم باقی می‌ماند.

## برنامه آزمون

### پیش از canary

- نصب dependencyهای پروژه و اجرای تست contract.
- اجرای shadow روی worker ایزوله با CAPTCHA حل‌شده و credential تستی.
- ثبت فقط metadata غیرحساس: status code، result code، latency، وجود token expiry،
  document query count و digest کوتاه تصویر CAPTCHA.
- مقایسه field-by-field بین payload نرمال BarPro و DTO موبایل.

### آزمون زنده read-only

- GetCaptcha، UserLoginV2، refresh token، GetDocumentByID،
  GetIssuedDocuments و GetShippingDocuments.
- در پاسخ مبهم یا mismatch فوراً توقف؛ هیچ insert خودکار در این مرحله مجاز نیست.

### canary mutation

- job جدید با idempotency تازه، driver/plate و payload واقعی و تأییدشده.
- ALLOW_LIVE_SUBMIT=true فقط برای همان اجرا و با operator حاضر.
- دقیقاً یک درخواست insert؛ بدون retry، fallback یا اجرای همزمان.
- اگر OTP خواسته شد، job به unknown/submission_unconfirmed می‌رود مگر اینکه
  اپراتور code معتبر را از کانال رسمی وارد کند.
- ثبت document ID، tracking code و History/Search به‌عنوان سه شاهد.

## ریسک‌ها و معیار تصمیم

| ریسک | اثر | معیار عبور |
|---|---|---|
| تغییر قرارداد DTO | رد یا ثبت ناقص | چند پاسخ واقعی بدون mismatch |
| WAF/IP | login یا query ناپایدار | egress ایرانی تأییدشده و خطای تفکیک‌شده |
| CAPTCHA/OTP | توقف workflow | نرخ حل و طول OTP مشاهده‌شده، بدون حدس |
| پاسخ بدون tracking | موفقیت کاذب | unknown + reconciliation، هرگز success |
| duplicate submission | خسارت عملیاتی | idempotency، lock، no-retry و canary تک‌job |
| drift بین worker و scheduler | رفتار متناقض | تست مشترک result contract در هر دو مسیر |

## وضعیت فعلی

- پیاده‌سازی کد و contract tests اضافه شده‌اند.
- هیچ ثبت سند، ارسال OTP یا mutation واقعی اجرا نشده است.
- به‌علت نبود credential مجاز و نبود Android runtime، آزمون live فعلاً فقط در
  سطح آماده‌سازی و read-only قابل انجام است.
- پس از آماده شدن credential و payload تستی، مرحله بعد باید shadow و سپس
  canary تک‌job باشد؛ transport وب تا پایان اثبات سه‌شاهدی مسیر rollback است.

آخرین verification محلی: `10 passed` برای contract موبایل، `43 passed` برای
مجموعه متمرکز موبایل/validation/mutation-safety، Ruff و compile بدون خطا. اجرای
کل suite به‌علت ورود به یک تست Playwright طولانی در این محیط متوقف شد؛ نتیجه آن
را به‌عنوان pass کامل گزارش نمی‌کنیم.

## الحاقیه شواهد PDF و ویدیو

مطابق صفحات PDF و شرح ویدئوی ارسالی، فرم واقعی این فیلدها را مرحله‌به‌مرحله
می‌گیرد: طرف حقیقی/حقوقی، اطلاعات کامل فرستنده و گیرنده، انتخاب پلاک و راننده
از لیست حساب، الزام ارتباط راننده با خودرو، یک یا چند کالا، وزن، تعداد بسته،
ارزش کل، نقشه و آدرس متنی مبدأ/مقصد، کدپستی هر دو نقطه، کرایه و سهم‌های مالی،
CAPTCHA دوم، OTP و رسید tracking. این شواهد با DTO استخراج‌شده از APK سازگار
هستند، اما جایگزین پاسخ زنده API نیستند (`PENDING-LIVE`).

OTP و CAPTCHA زمان‌محورند: تنها سیگنال قابل اتکا برای OTP، `isOtpNeeded` در پاسخ
UTCMS و برای CAPTCHA، نوع/تصویر/توکن مرحله جاری است. پنجره‌های ساعتی موجود در
پیکربندی پروژه فقط prediction هستند و مجوز ارسال را ایجاد نمی‌کنند.

«مراحل حمل» پس از صدور سند، lifecycle جداگانه‌ای است. وجود endpointهای
`RegisterStartOfShipping` و `RegisterEndOfShipping` در APK قطعی است؛ نام دقیق
همه وضعیت‌ها و این‌که چه مقدار آن‌ها خودکار از GPS می‌آیند، هنوز
`PENDING-LIVE` است.

تکرار یک بارنامه با همان مشخصات در روزهای مختلف مجاز است. هر روز/درخواست باید
Job و کلید idempotency مستقل داشته باشد؛ فقط همان تلاش پس از timeout یا نتیجه
مبهم نباید دوباره POST شود.

## الحاقیه پیاده‌سازی و OTP (2026-09-11)

در ادامه بررسی، سه مسیر اجرایی هم‌تراز شد:

1. Scheduler در `UTCMS_TRANSPORT=mobile|shadow` دیگر Chromium یا proxy مرورگر
   نمی‌سازد و همان `WaybillAutomationBot` را با context خالی برای مسیر API اجرا
   می‌کند. حالت `web` بدون تغییر باقی مانده است.
   در حالت dry-run/shadow نیز DTO نهایی APK با token آزمایشی build می‌شود تا
   شناسه کالا، بسته‌بندی، بیمه، مختصات و کرایه واقعاً اعتبارسنجی شوند؛ صرفاً
   فهرست نام فیلدها اعتبارسنجی محسوب نمی‌شود.
2. اگر پاسخ واقعی `InsertDocumentHagigiV3` مقدار `isOtpNeeded=true` بدهد، این
   پاسخ بر پیش‌بینی ساعت مقدم است. Job به `UNKNOWN` با
   `error_category=otp_required` و `requires_operator_otp=true` می‌رود، شناسه
   سند حفظ می‌شود، و گیت سراسری با observation `OTP_REQUIRED` بسته می‌شود.
3. reconciliation خودکار Job منتظر OTP را به‌عنوان بارنامه مبهم در History
   جست‌وجو نمی‌کند. این Job تا ورود اپراتوری OTP یا تصمیم صریح پشتیبانی متوقف
   می‌ماند؛ retry یا ارسال دوباره Insert مجاز نیست.

رفتار زمانی همان قرارداد قبلی است: پنجره ۱۷:۳۰ تا ۰۸:۰۰ تهران فقط prediction
است. فقط observation زنده `OTP_FREE` اجازه mutation می‌دهد و `OTP_REQUIRED` یا
`UNKNOWN` ارسال را متوقف می‌کند. بنابراین دریافت OTP غیرمنتظره در روز نیز گیت
را می‌بندد و برنامه را به ساعت ثابت وابسته نمی‌کند. طول کد در client پنج یا شش
رقم پذیرفته می‌شود تا اختلاف شواهد و نسخه‌های اپ باعث حدس اجباری نشود؛ مقدار
OTP هرگز در log، evidence یا پاسخ sanitised ذخیره نمی‌شود.

### آزمون‌های این مرحله

- قرارداد APK و payload: `10 passed`
- bot موبایل، scheduler بدون browser، parity scheduler و mutation guard:
  `24 passed`
- مجموعه focused نهایی شامل قرارداد موبایل، bot/scheduler، گیت و تشخیص OTP،
  reconciliation، live-submit guard و mutation safety: `55 passed`
- Ruff، compileall و `git diff --check`: موفق
- اجرای کل suite تا اولین تست طولانی Playwright: `329 passed` در ۶:۵۸ دقیقه؛
  برای جلوگیری از باز ماندن process با `Ctrl-C` متوقف شد و pass کامل محسوب نمی‌شود.
- آزمون زنده `GetCaptcha`: انجام نشد؛ resolver متناوباً timeout شد و اتصال
  مستقیم به IP حل‌شده `185.173.168.105:443` نیز `connection refused` بود. هیچ
  credential، OTP یا mutation ارسال نشد.

در نتیجه، مسیر موبایل برای dry-run و ادغام با worker/scheduler آماده است؛ اما
تأیید قرارداد پاسخ زنده، حل خودکار هر دو خانواده CAPTCHA و تکمیل OTP اپراتوری
هنوز به یک حساب تست مجاز و egress قابل‌دسترسی نیاز دارد. تا آن زمان مقدار
`UTCMS_TRANSPORT=web` و `ALLOW_LIVE_SUBMIT=false` باید حفظ شوند.

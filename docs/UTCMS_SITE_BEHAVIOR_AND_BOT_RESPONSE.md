# رفتار سامانه UTCMS و پاسخ ربات BarPro در برابر آن

**تاریخ تدوین:** ۳۰ اوت ۲۰۲۶ (۱۴۰۵/۰۶/۰۸)
**نسخه:** 1.0.0
**مرجع استخراج:** خواندن مستقیم `hagigihogugitemplate.js` از کش asset روی worker2 + اجراهای زندهٔ read-only شمارهٔ ۱۵ تا ۲۱ روی سرورهای عملیاتی

این سند تنها مرجع یکپارچهٔ «سایت چه می‌کند / ربات چه پاسخی می‌دهد» است. هر ادعای این
سند یا از سورس جاوااسکریپت خودِ UTCMS استخراج شده یا در یک اجرای زندهٔ ثبت‌شده
مشاهده شده است؛ موارد اثبات‌نشده صریحاً با برچسب «تأییدنشده» مشخص شده‌اند.

---

## ۱. لایهٔ دسترسی: چرا مرورگر تنها کافی نیست

| رفتار سامانه | پاسخ ربات |
|---|---|
| WAF بر اساس اثر انگشت TLS تصمیم می‌گیرد؛ کلاینت غیر‌کرومی پاسخ 408/444 می‌گیرد | همهٔ ترافیک از `curl_cffi` با پروفایل Chrome عبور می‌کند (`UtcmsHttpLogin` برای ورود، `UtcmsHttpBrowserBridge` برای صفحه) |
| هر **handshake تازه** روی یک IP خروجی throttle می‌شود (خطای `SSL_connect` یا HTTP 408) | اتصال گرم نگه داشته می‌شود؛ بین اجراها ۹۰ تا ۱۸۰ ثانیه فاصله؛ asset‌ها روی یک session یک‌بارمصرف و جدا از session فرم فرستاده می‌شوند |
| state سمت سرور فقط با کوکی منتقل نمی‌شود | session احرازشدهٔ لاگین با `adopt_authenticated_session` به bridge منتقل و به همان thread پین می‌شود (کش اتصال libcurl thread-local است) |
| deep-link سرد به فرم صدور پاسخ 408 می‌دهد | ترتیب اجباری `OldLogin → Notification → کلیک منو → Document/HagigiHogugi` |
| کوکی کهنهٔ `ApplicationToken` در صفحه، XHR‌های بعدی را با 408/500/400 می‌شکند | هدر `Cookie` روی XHR زمان اجرا حذف می‌شود |

---

## ۲. سیاست asset: چه چیزی stub می‌شود و چرا

این بخش گران‌ترین درس پروژه است. سه بار سیاست asset عوض شد و هر بار یک باگ
رفتاری تولید کرد که شبیه باگ asset نبود:

| نوع asset | تصمیم فعلی | دلیل |
|---|---|---|
| `script` | **هرگز stub نمی‌شود** | handler آمادهٔ قالب، `FormDocumenDetailsRegister` و `FormValidation.Framework.Bootstrap` را صدا می‌زند که در فایل‌های «حیاتی» دستی‌فهرست‌شده نبودند؛ با بدنهٔ خالی، handler استثنا می‌داد و هر رفتار بعدی (autocomplete بار، `fillBoxType`، `GETUserFleetListTajmi`، handler تغییر پلاک/راننده) بی‌صدا از بین می‌رفت |
| `stylesheet` | **هرگز stub نمی‌شود** | `.modal { display: none }` از CSS می‌آید. با CSS خالی هر مودال بستهٔ Bootstrap — از جمله مودال OTP — جعبهٔ واقعی می‌گیرد و Playwright آن را visible می‌خواند؛ تصمیم‌های OTP/CAPTCHA ربات تصمیم‌های visibility هستند، پس CSS اینجا «رفتار» است نه تزئین |
| `image` کپچا | **هرگز stub و هرگز کش نمی‌شود** | `/DNTCaptchaImage/Show?data=…` خودِ چالش است. با بدنهٔ خالی تصویر شکسته می‌شد، solver هیچ چیزی نمی‌خواند و یک مقدار یک‌کاراکتری بی‌ربط در فیلد می‌گذاشت. کش هم ممنوع است چون هر چالش یک‌بارمصرف و به توکن سمت سرور گره خورده است |
| سایر `image` و `font` | stub با بدنهٔ خالی | صفحهٔ صدور ده‌ها فایل می‌کشد؛ عبور این سیل از curl، handshake تازه تولید می‌کند که سطح استاتیک UTCMS آن را reset می‌کند. هیچ‌کدام رفتار یا visibility را عوض نمی‌کنند |

کش asset روی دیسک (`/tmp/utcms_asset_cache`) فرم را قطعی می‌کند: هر فایلی که یک
اجرا موفق به دانلودش شود، اجرای بعدی را سریع‌تر و کم‌وابسته‌تر می‌کند — به‌جز
تصاویر کپچا که صریحاً مستثنا شده‌اند.

---

## ۳. نقشهٔ pane‌های فرم صدور

فرم یک wizard از نوع Bootstrap pill است. هر pane تا فعال نشدن `display:none`
است — این تنها نکته‌ای است که بیشترین باگ را تولید کرده.

| pane | محتوا | نکتهٔ ربات |
|---|---|---|
| `pills-1` … `pills-4` | فرستنده، گیرنده، راننده، پلاک | از grid‌های DataTables پر می‌شوند (`fillgridesender`, `fillgrideReceiver`, `fillgridDriver`, `fillgridPelak`) |
| `pills-5` | آدرس و موقعیت **مبدأ** (`#ddStateSource`, `#ddCitySource`, `#txtAddressSource`) | تا فعال نشدن مخفی است؛ هر کوئری با فیلتر `:visible` صفر گزینه می‌خواند |
| `pills-6` | آدرس و موقعیت **مقصد** (`#ddStateDest`, `#ddCityDest`) | همان مشکل |
| `pills-7` … `pills-8` | بار، بسته‌بندی، مبلغ و گزینه‌های حمل | `KalaSearch` و `fillBoxType` |
| `pills-9` | **مرحلهٔ ثبت نهایی**: کپچا + `#btnRegisterFinished` | مرحله‌ای که ربات در dry-run روی آن متوقف می‌شود |
| `pills-10` | **پس از صدور**: `#TrackingCodeNumber` (disabled) + دکمه‌های چاپ بارنامهٔ فرستنده/گیرنده/راننده + `#NewRegister` | فقط بعد از ثبت موفق نمایان می‌شود |

نکتهٔ حاصل از اجرای زنده: `#GoFinalStep` («مرحله نهایی») **ناوبری خودِ سایت پس از
ذخیره** است، نه دکمهٔ پیش از ثبت. پیش از ثبت `display:none` است و انتظار برای
کلیک روی آن اشتباه بود؛ سیگنال آمادگی مرحلهٔ نهایی، **visible شدن
`#btnRegisterFinished`** است.

---

## ۴. dropdown‌های استان و شهر: دو نقص بالادستی

هر دو نقص در ۳۰ اوت ۲۰۲۶ به‌صورت زنده اثبات شدند.

**نقص یک — سایت گزینه‌های خودش را خراب می‌کند.**
`/Barname/Document/fillStates` با `Content-Type: application/json` پاسخ می‌دهد، پس
jQuery یک آبجکت parse‌شده به handler می‌دهد. handler سایت اما `$.each(Doc, …)` را
روی **پاکت** (`resultCode`, `resultMessage`, `obj`) اجرا می‌کند و آن هم بعد از
`remove()` کردن گزینه‌های واقعی. نتیجه: `#ddStateSource` یک placeholder به‌همراه
دقیقاً سه گزینهٔ `undefined` می‌شود. `/Barname/Document/FillProvinces` همان داده را
با `text/plain` می‌دهد و `InitSourceAddresses` درست parse می‌کند — پس هرکدام دیرتر
برسد برنده است، یعنی یک race.

**نقص دو — select‌ها در pane بسته هستند.** توضیح بخش ۳.

**پاسخ ربات:**
- گزینه‌ها مستقیماً از `FillProvinces` و `FillCities?StateId=<id>` خوانده و در select بازسازی می‌شوند (`_backfill_select_options`)
- سلکتور با fallback «مخفی اما attached» resolve می‌شود (`_resolve_selector`)، چون `page.select_option`/`page.fill` روی عنصر مخفی معلق می‌مانند
- انتخاب با JS انجام و `input`/`change` و `jQuery(el).trigger('change')` دستی dispatch می‌شود
- الف مقصورهٔ عربی نرمال‌سازی می‌شود: UTCMS «خراسان رضوى» و «آذربایجان شرقى» با `ى` (U+0649) برمی‌گرداند در حالی که اپراتور «رضوی» تایپ می‌کند
- read-back اجباری است: ذخیرهٔ نهایی `sourceStateId`/`sourceCityId` را از `.val()` می‌فرستد، پس id‌ها باید id واقعی UTCMS باشند (نمونهٔ تأییدشده: خراسان رضوی = `10`، کاشمر = `1200`)

---

## ۵. مرحلهٔ ثبت نهایی: سه پیاده‌سازی کپچا و سه اندپوینت

مقدار فیلد مخفی `#CapType` تعیین می‌کند سایت کدام نسخهٔ کپچا را سرو کرده و در
نتیجه ذخیره به کدام اندپوینت POST می‌شود:

| `#CapType` | پیاده‌سازی کپچا | اندپوینت ذخیره | کنترل refresh |
|:---:|---|---|---|
| `0` | ویجت `window.cap` (`#CapToken`) | `POST /Barname/Document/UpdateRegisterNewNewOld` | `window.cap.reset()` |
| `1` | **DNTCaptcha** (`#DNTCaptchaInputText`, `#DNTCaptchaText`, `#DNTCaptchaToken`) | `POST /Barname/Document/UpdateRegisterNewOld` | `#dntCaptchaRefreshButton` |
| سایر | `#CaptchaCode` | `POST /Barname/Document/UpdateRegisterNewNew` | `#btnReloadCaptcha` |

**مشاهدهٔ زندهٔ ۳۰ اوت ۲۰۲۶ (راننده ۵):** `#CapType == "1"`، یعنی مسیر واقعی این
حساب `UpdateRegisterNewOld` است. `window.cap` وجود ندارد و `#CaptchaCode` و
`#btnReloadCaptcha` روی صفحه نیستند، پس دو مسیر دیگر برای این حساب بی‌ربط‌اند —
ولی ربات باید هر سه را پشتیبانی کند چون `#CapType` تصمیم سمت سرور است.

نوع چالش DNT در این استقرار **جمع دو عدد به‌صورت تصویر با فونت دست‌نویس** است
(نه متن قابل خواندن از DOM). پس:

- استراتژی `math` که hint متنی اطراف فیلد را می‌خواند شکست می‌خورد و لاگ
  `submit_math_captcha_low_confidence` می‌دهد — این رفتار **درست** است، نه خطا
- سپس زنجیرهٔ provider (`CnnCaptchaProvider` → `PyTorchFuelCaptchaProvider` →
  `KerasOcrCaptchaProvider` → `EnhancedOcrProvider` → `LocalOcrCaptchaProvider`)
  تصویر را OCR می‌کند و `_normalize_captcha_solution` عبارت را حساب می‌کند
- در اجرای ۲۱ نتیجه با چالش تصویر مطابق بود (`submit_provider_captcha_solved`).
  این **یک** نمونهٔ تأییدشده است؛ نرخ موفقیت روی چند چالش پشت‌سرهم سنجیده نشده

### فیلدهای payload ذخیره

`IsDraft`, `DNTCaptchaText`, `DNTCaptchaInputText`, `DNTCaptchaToken`, `capToken`,
`SendSMS` (از `$("#sendsmsvalue").is(':checked')`), `loadList`, `value`,
`sourcePostalCode`, `t1`…`t4`, `SelfDeclaredTimeOfStartShipment`,
`IsCompanySender`, `IsCompanyReceiver`, به‌همراه
`sourceAddress` = `$("#txtAddressSource").val()`,
`sourceCityId` = `$("#ddCitySource").val()`,
`sourceStateId` = `$("#ddStateSource").val()`.

### پاسخ ذخیره

```json
{"resultCode": 200, "obj": {"id": <documentId>, "isOtpNeeded": true|false}}
```

---

## ۶. قرارداد OTP (استخراج‌شده از `hagigihogugitemplate.js`)

۱. `#btnRegisterFinished` ذخیره را POST می‌کند.
۲. اگر `obj.isOtpNeeded == true`: سایت `#DocumentId = obj.id` می‌گذارد، مودال
   **`#GetOptCodeModal`** را نمایش می‌دهد و کد پیامکی را در `#otp` می‌خواهد؛
   `#submitOtp` به `POST /Barname/Document/IssueDocumentByOtpNew {docId, code}`
   می‌فرستد. ارسال مجدد:
   `POST /Barname/History/ResendOtpForIssueDocumen {documentId}`.
۳. اگر `isOtpNeeded == false`: `showTrackingCode` بلافاصله اجرا می‌شود.
۴. در هر دو حالت کد رهگیری از
   `GET /Barname/Document/showTrackingCode?id=<objid>` در `#TrackingCodeNumber`
   می‌نشیند و **خودِ UTCMS روی `#GoFinalStep` کلیک می‌کند** و `#pills-tab` را
   `d-none` می‌کند.

### دو پیامد ایمنی که باید در کد رعایت شود

- **رکورد سند پیش از تأیید OTP ساخته می‌شود.** ثبت داخل پنجرهٔ OTP بدون داشتن کد،
  یک سند نیمه‌صادرشده باقی می‌گذارد. به همین دلیل دروازهٔ ثبت در آن بازه باید
  بسته بماند و «fail-closed» رفتار کند.
- **وجود مودال هیچ چیزی را اثبات نمی‌کند.** `#GetOptCodeModal` از لحظهٔ لود صفحه
  در DOM هست با `class="modal fade"`، `aria-hidden="true"`، `#otp` با کلاس
  `visually-hidden` و تایمر `02:00`. فقط کلاس `.show` معنی‌دار است. مقدار
  `otpDuration = 3` در صفحه ست می‌شود.

### مثبت کاذبی که وقت زیادی گرفت

placeholder فیلد کپچا «کد امنیتی را وارد نمایید» است، پس پروب عمومی
`input[placeholder*='کد']` در **هر** اجرا وجود چالش OTP را گزارش می‌کرد. تشخیص
OTP اکنون بر `#GetOptCodeModal.show` و عبارات مخصوص پیامک تکیه می‌کند و
ورودی‌های کپچا با
`:not([name*='captcha' i]):not([id*='captcha' i])` صریحاً حذف می‌شوند.

### قانون عملیاتی اپراتور

بازهٔ نیاز به کد پیامکی: حدوداً **۱۷:۳۰ تا ۰۸:۰۰ به وقت تهران**. بین ۰۸:۰۰ تا
۱۷:۳۰ بارنامه بدون کد پیامکی ثبت می‌شود. این قانون در `UTCMSSubmissionGate`
فقط **پیش‌بینی** است، نه قانون صلب؛ مشاهدهٔ زنده بر آن اولویت دارد.

---

## ۷. مرزهای ایمنی ثبت (mutation boundary)

| قاعده | محل اعمال |
|---|---|
| `ALLOW_LIVE_SUBMIT` به‌صورت پیش‌فرض `False` است | `utcms_config` روی هر سه سرور |
| کلیک ثبت **حداکثر یک بار**، بدون retry و بدون fallback | `_click_once_no_retry` |
| دروازهٔ زندهٔ ثبت بلافاصله پیش از اولین کلیک mutating بررسی می‌شود؛ بررسی‌های scheduler صرفاً advisory هستند | `utcms_submission_gate.is_submission_allowed()` |
| خطای پس از dispatch شدن کلیک → وضعیت `unknown` و ارجاع به reconciliation (POST ممکن است رفته باشد) | `mutation_submit_post_click_error_route_to_unknown` |
| هیچ فیلدی با دادهٔ ساختگی پر نمی‌شود؛ داده ناقص باشد اجرا رد می‌شود | `validate_live_waybill_payload` |
| هرگز job‌ای که کد رهگیری یا `document_id` دارد دوباره ثبت نمی‌شود | لایهٔ صف |
| کد پیامکی و پاسخ کپچا هرگز لاگ نمی‌شوند | `_sanitize_evidence` |
| موفقیت ثبت با سه شاهد اثبات می‌شود: کد رهگیری RPA + `waybill_jobs.result_json` + History/Search خودِ UTCMS | رویهٔ عملیاتی |

---

## ۸. جدول نقص‌های بالادستی شناسایی‌شده

| نقص سایت | نشانه‌ای که تولید می‌کند | دور زدن در ربات |
|---|---|---|
| `fillStates` روی پاکت JSON پیمایش می‌کند | «گزینه‌های استان بارگذاری نشدند» که شبیه timeout است | backfill از `FillProvinces`/`FillCities` |
| race بین `fillStates` و `InitSourceAddresses` | نتیجهٔ غیرقطعی بین اجراها | نوشتن گزینه‌ها توسط ربات، سپس read-back اجباری |
| select‌های موقعیت در pane بستهٔ `pills-5`/`pills-6` | صفر گزینه با کوئری `:visible` | `_resolve_selector` با fallback مخفی + انتخاب با JS |
| `ShowNotification` / `GetNotificationList` پاسخ 400 می‌دهند | خطای شبکه در لاگ، بدون اثر رفتاری | نادیده گرفته می‌شود (تأییدنشده که بی‌ضرر است در همهٔ مسیرها) |
| `/assets/vendor/mappNew/assets/languages/fa.json` و `en.json` وجود ندارند | `requestfailed` روی نقشه | نقشه از مسیر متنی دور زده می‌شود |
| خطای `pagingButton` در `pageerror` | یک استثنای JS در هر لود صفحه | بی‌اثر بر مسیر ثبت؛ صرفاً ثبت می‌شود |
| نام استان‌ها با `ى` عربی | عدم تطابق متن با ورودی اپراتور | نرمال‌سازی `ى`→`ی` و `ي`→`ی` |

---

## ۹. گزارش اجراهای زندهٔ read-only

| اجرا | تاریخ | نتیجه |
|:---:|---|---|
| ۱۵ | ۳۰ اوت | شکست: «گزینه‌های استان (Origin) بارگذاری نشدند» — ریشه: pane بسته + باگ `fillStates` |
| ۱۶ | ۳۰ اوت | موفق پس از اصلاح موقعیت: `province_value: "10"`, `city_value: "1200"` |
| ۱۷ | ۳۰ اوت | dry-run پاک: `ready_for_submit: true`, `otp_challenge_visible: false` |
| ۱۸ | ۳۰ اوت | inventory کامل مرحلهٔ نهایی: `#CapType == "1"` |
| ۱۹ / ۲۰ | ۳۰ اوت | solver اجرا شد؛ کشف اینکه تصویر کپچا stub شده و خروجی بی‌ربط است |
| ۲۱ | ۳۰ اوت | پس از اصلاح passthrough تصویر: تصویر واقعی لود شد و پاسخ solver با چالش مطابق بود |

در همهٔ این اجراها: `final_submit_clicked: false`، `captcha_solved` گزارش شده فقط
به‌معنای پر شدن فیلد است، `sms_requested: false`، `mutation_dispatched: false`.

---

## ۱۰. سلکتورهای مرجع مرحلهٔ نهایی

| سلکتور | نقش | وضعیت پیش از ثبت |
|---|---|---|
| `#btnRegisterFinished` | «ثبت نهایی سند حمل» — دکمهٔ ثبت واقعی | visible، enabled |
| `#GoFinalStep` | «مرحله نهایی» — ناوبری پس از ذخیرهٔ خودِ سایت | `display:none` |
| `#btnregisterbarname` | «ثبت بارنامه» | attached ولی نامرئی |
| `#DNTCaptchaInputText` | ورودی کپچا (placeholder: «کد امنیتی را وارد نمایید») | visible، enabled |
| `#dntCaptchaRefreshButton` | تازه‌سازی کپچا (تگ `a`) | visible |
| `#GetOptCodeModal` | مودال کد پیامکی | در DOM، بسته (`modal fade`, `aria-hidden="true"`) |
| `#otp` / `#submitOtp` / `#sendVerificationCode` | ورودی، ثبت و ارسال مجدد کد | نامرئی |
| `#TrackingCodeNumber` | کد رهگیری | خالی و `disabled` |
| `#sendsmsvalue` | چک‌باکس اطلاع‌رسانی پیامکی | نامرئی |

---

## ۱۱. ابزار بازتولید

```bash
python scripts/probe_waybill_final_stage.py --payload-file /secure/waybill.json --driver-id 5 --attempt-captcha --captcha-artifact-dir /tmp/captcha_probe
```

این اسکریپت `ALLOW_LIVE_SUBMIT` را سخت‌کد `False` می‌کند، هرگز روی کنترل ثبت کلیک
نمی‌کند، هرگز کد پیامکی نمی‌خواهد و هیچ فیلد خالی را با دادهٔ ساختگی پر نمی‌کند.
با `--attempt-captcha` فقط فیلد کپچا پر می‌شود (عملی کاملاً client-side) و خروجی
solver تنها روی دیسک و برای بازبینی اپراتور نوشته می‌شود، نه در لاگ.

اسناد مرتبط: [UTCMS_SUBMIT_CONTRACT.md](UTCMS_SUBMIT_CONTRACT.md) ·
[UTCMS_OTP_DETECTION.md](UTCMS_OTP_DETECTION.md) ·
[UTCMS_BOT_BEHAVIOR_CONTRACT.md](UTCMS_BOT_BEHAVIOR_CONTRACT.md) ·
[UTCMS_GATE_RUNBOOK.md](UTCMS_GATE_RUNBOOK.md)





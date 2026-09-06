# قوانین و رفتار الزامی ربات BarPro در مواجهه با سامانه UTCMS

**آخرین بازبینی: 2026-08-30**
**دامنه: `barname.utcms.ir` (صدور بارنامه) و `utcms.ir/ShowFuelQuota.aspx` (استعلام سوخت)**

این سند مرجع واحد «رفتار الزامی ربات» است: هر قاعده‌ای که RPA باید در تعامل با
UTCMS رعایت کند، به‌همراه شاهد آن. سند مکمل موارد زیر است و با آن‌ها تناقض ندارد:

- [قرارداد و محدودیت‌های UTCMS](UTCMS_CONSTRAINTS.md) — رفتار مشاهده‌شدهٔ سامانه
- [قرارداد submit](UTCMS_SUBMIT_CONTRACT.md) و [Runbook گیت](UTCMS_GATE_RUNBOOK.md)
- [ماتریس فیلدها](UTCMS_FIELD_MATRIX.md) و [مغایرت‌گیری](UTCMS_RECONCILIATION.md)
- [قوانین بحرانی پروژه](../CRITICAL_RULES.md)

## 0. برچسب اعتبار مطالب

| برچسب | معنا |
|---|---|
| `CODE-VERIFIED` | در کد پیاده و با تست واحد پوشش داده شده است |
| `LIVE-OBSERVED` | در آزمون زندهٔ کنترل‌شده روی Worker مشاهده شده است |
| `PENDING-LIVE` | فرضیهٔ اصلاح‌شده که هنوز شاهد زندهٔ کامل ندارد |

هیچ ادعایی بدون یکی از این سه برچسب در این سند مجاز نیست.

## 1. خطوط قرمز (بدون استثنا)

1. **دادهٔ ساختگی ممنوع است.** موبایل، کد ملی، پلاک، ارزش بار، آدرس و نام طرفین
   هرگز با مقدار جعلی، مقدار پیش‌فرض یا شمارهٔ راننده جایگزین نمی‌شوند. payload
   ناقص باید به `needs_review/payload_validation_failed` برود. `CODE-VERIFIED`
2. **ثبت نهایی فقط یک بار.** درخواست POST ثبت هیچ‌گاه retry، fallback یا مسیر
   دوم ندارد؛ تنها متدهای `GET/HEAD` قابل retry هستند. `CODE-VERIFIED`
3. **`ALLOW_LIVE_SUBMIT=false` پیش‌فرض است.** فعال‌سازی فقط برای یک Job
   اعتبارسنجی‌شده، با نظارت اپراتور و برای یک اجرا. `CODE-VERIFIED`
4. **Job دارای tracking code دوباره submit نمی‌شود**؛ و `success` بدون tracking
   code به `needs_review/submission_unconfirmed` تنزل می‌یابد. `CODE-VERIFIED`
5. **Job مبهم (ambiguous) بازاجرا نمی‌شود.** برای آزمون زنده باید Job جدید با
   کلید idempotency جدید ساخته شود تا خطر ثبت تکراری صفر شود.
6. **اعتبارنامه هرگز چاپ یا ذخیره نمی‌شود.** رمز SSH/UTCMS فقط از ورودی امن یا
   متغیر محیطی خوانده می‌شود؛ پاسخ CAPTCHA در log یا metadata ذخیره نمی‌شود.
7. **حاضر بودن DOM «موفقیت» نیست.** بستن modal، پیام UI یا وضعیت داخلی بدون سه
   شاهد بند ۶ اثبات ثبت نیست.

## 2. قرارداد transport و session

پیاده‌سازی: [`app/automation/http_browser_bridge.py`](../app/automation/http_browser_bridge.py)

UTCMS بخشی از وضعیت ناوبری صدور را بیرون از cookie jar و وابسته به همان اتصال
نگه می‌دارد. بنابراین «کدام درخواست روی کدام session برود» بخشی از قرارداد است،
نه جزئیات پیاده‌سازی.

| نوع درخواست | مسیر مجاز | دلیل |
|---|---|---|
| login (POST) | session اختصاصی `curl_cffi` با fingerprint کروم | Chromium در handshake رد می‌شود `LIVE-OBSERVED` |
| landing / منو (`Notification`) | Chromium بومی از طریق Squid | Chromium این صفحه را پایدار می‌آورد `LIVE-OBSERVED` |
| document صدور (`HagigiHogugi`) | همان session دقیق login، پس از یک بازدید `Notification` | deep-link سرد و session بازسازی‌شده HTTP 408 می‌گیرد `LIVE-OBSERVED` |
| اسکریپت‌های حیاتی فرم | prefetch ترتیبی روی همان session، سپس تحویل از cache به Chromium | Chromium روی این فایل‌ها `ERR_CONNECTION_CLOSED/RESET` می‌گیرد `LIVE-OBSERVED` |
| سایر asset (css/font/image/js غیرحیاتی) | Chromium بومی | bridge کردن همه‌ی assetها serialization و timeout ۴۸۰ ثانیه‌ای ساخت `LIVE-OBSERVED` |
| XHR/fetch فرم (KalaSearch، استان/شهر، راننده) | تا پیش از تحویل فرم: session جدا؛ پس از آن: همان session فرم | AJAX صفحهٔ landing اتصال مشترک را می‌سوزاند و navigation بعدی خطا می‌دهد `LIVE-OBSERVED` |
| POST ثبت نهایی | همان session فرم، دقیقاً یک بار | جلوگیری از ثبت تکراری `CODE-VERIFIED` |

قواعد الزامی:

1. session احرازشدهٔ login فقط برای documentهای صدور و assetهای حیاتی رزرو
   می‌شود؛ ترافیک landing نباید آن را مصرف کند. `CODE-VERIFIED`
2. پس از مصرف فرم prefetch‌شده، XHRهای فرم روی همان session ارتقا می‌یابند و
   `_preserve_authenticated_session` فعال می‌شود. `CODE-VERIFIED`
3. reset یا خطای asset/document هرگز session احرازشده را reset نمی‌کند؛ در غیر
   این صورت یک اختلال گذرا به ۴۰۸ قطعی تبدیل می‌شود. `CODE-VERIFIED`
4. prefetch اسکریپت‌ها فقط شامل فهرست حیاتی است: `jquery.js`، `jquery-ui.js`،
   `jquery.validate.js`، `formvalidation.popular*`، `formhelper.js`،
   `hagigihogugitemplate.js` و `hagigihogugi.js`. واکشی همهٔ اسکریپت‌های صفحه در
   آزمون زنده باعث فرسودن اتصال پیش از رسیدن به `hagigihogugi*.js` شد.
   `LIVE-OBSERVED`
5. شکست prefetch یک فایل، تحویل فرم را باطل نمی‌کند؛ فقط log می‌شود و گیت
   بند ۴ مسئول جلوگیری از ادامهٔ ناایمن است. `CODE-VERIFIED`
6. session ساخته‌شده از cookie تنها، جانشین session احرازشده نیست. `LIVE-OBSERVED`

## 3. قرارداد ناوبری تا فرم

ترتیب مجاز، دقیقاً: `OldLogin` → `Notification` → کلیک منوی «حمل بارنامه» →
`Document/HagigiHogugi`.

- deep-link سرد به فرم پاسخ 408 با body کوتاه (نمونهٔ مشاهده‌شده ۳۹ بایت) می‌دهد؛
  این به‌تنهایی شاهد outage یا block شدن IP نیست. `LIVE-OBSERVED`
- navigation مستقیم به URL فرم فقط به‌عنوان آخرین recovery مجاز است، نه مسیر اول.
  `CODE-VERIFIED`
- اگر session روی URL قدیمی مانده باشد، ابتدا landing احرازشده warm می‌شود.
  `CODE-VERIFIED`

## 4. گیت «زنده بودن فرم» (نه فقط حاضر بودن DOM)

پیاده‌سازی: `_probe_form_javascript` و `_require_live_form_javascript` در
[`app/automation/waybill_enhanced.py`](../app/automation/waybill_enhanced.py)

در آزمون زندهٔ 2026-08-27، HTML فرم کامل (≈۲۵۸ کیلوبایت با همهٔ markerها) تحویل
شد اما اسکریپت‌های آن reset شده بودند. نتیجه: انتخاب نوع شخص فیلد نام را باز
نمی‌کرد و `KalaSearch` هیچ گزینه‌ای برنمی‌گرداند، در حالی که همهٔ markerهای DOM
موجود بودند. `LIVE-OBSERVED`

بنابراین ورود به مرحلهٔ تکمیل فیلدها تنها با تأیید همهٔ شرط‌های زیر مجاز است:

| سیگنال | شرط عبور |
|---|---|
| `window.jQuery` | تابع باشد |
| `jQuery.ui.autocomplete` | موجود باشد (لازمهٔ جست‌وجوی کالا) |
| `jQuery.validator` | موجود باشد (لازمهٔ validation فرم) |
| handler دکمهٔ مرحلهٔ بعد (`btnGoLVL2`/`GoLVL2`) | نام تابع inline استخراج و در `window` تعریف شده باشد |

- در صورت عدم عبور تا مهلت (پیش‌فرض ۲۰ ثانیه) خطای کاربرپسند فارسی صادر می‌شود و
  هیچ فیلدی پر نمی‌شود. `CODE-VERIFIED`
- اگر probe اصلاً قابل اجرا نباشد (page double یا خطای سطح صفحه) گیت fail-closed
  نمی‌شود؛ سایر گیت‌ها مسئول آن خطا هستند. `CODE-VERIFIED`
- این گیت روی همهٔ مسیرهای بازکردن فرم اعمال می‌شود، چون در
  `_ensure_waybill_form_page` بالای مسیر ناوبری قرار گرفته است. `CODE-VERIFIED`

## 5. قرارداد فیلدها و read-back

قاعدهٔ کلی: هر مقدار پس از درج، از همان selector موفق read-back و مقایسه می‌شود؛
هر mismatch یا پیام validation، عبور به مرحلهٔ بعد را ممنوع می‌کند. `CODE-VERIFIED`

| بخش | قاعدهٔ الزامی |
|---|---|
| موبایل فرستنده/گیرنده | ۱۱ رقم، شروع با `09`، واقعی و متمایز از شمارهٔ راننده؛ preflight زنده قبل از رزرو منابع |
| نام طرفین | حقیقی: نام و نام خانوادگی؛ حقوقی: نام دفتر/شرکت |
| کالا | مقدار از autocomplete زندهٔ `KalaSearch` انتخاب شود؛ تطابق دقیق و یکتا الزامی است. چند تطابق ⇒ خطا، نه انتخاب دلبخواه |
| بسته‌بندی | فقط از گزینه‌های موجود select |
| وزن و ارزش | عدد مثبت؛ وزن با واحد UI (تن) و ارزش به ریال |
| کرایه / پس‌کرایه | فیلد `#txtkeraye` (کلیدهای `rent` و `postRent`) در بک‌اند UTCMS اجباری است (کد خطای ۴۰۲۵). مقدار فیلد قبل از کلیک ثبت نهایی اعتبارسنجی شده و پیش‌فرض معتبر ۵,۰۰۰,۰۰۰ ریال تضمین می‌گردد `CODE-VERIFIED` `LIVE-OBSERVED` |
| زمان بارگیری | فیلد `SelfDeclaredTimeOfStartShipment` باید دارای تاریخ و ساعت معتبر (`HH:mm`) باشد. تابع کلاینتی `window.validateTime` که این فیلد را پاک می‌کرد خنثی شده و لایه شبکه ساعت را تضمین می‌کند `CODE-VERIFIED` `LIVE-OBSERVED` |
| مختصات و نقشه | در حالت متنی (`user_text` با `mapFlag=true`)، مقادیر `citySourceMap`، `CityDestMap` و مختصات اعشاری باید درج شوند تا از خطای ۵۰۰ سرور ASP.NET جلوگیری شود `CODE-VERIFIED` `LIVE-OBSERVED` |
| پلاک/راننده | پلاک فعال و متعلق به همان راننده؛ حساب UTCMS فعال با رمز قابل decrypt |
| مبدأ/مقصد | تب درست → استان با تطابق نام → اتمام AJAX شهرها → شهر با تطابق یکتا → آدرس در textarea → read-back مقدار و برچسب هر سه |
| فیلدهای غیراجباری | خالی می‌مانند؛ پر کردن با مقدار ساختگی ممنوع است |

payload با شکل ترکیبی (طرفین nested همراه مبدا/مقصد رشته‌ای) باید نرمال‌سازی شود،
نه اینکه پیش از باز شدن مرورگر با `ValueError` سقوط کند. `CODE-VERIFIED`

## 6. اثبات ثبت: قاعدهٔ سه‌شاهدی

ثبت فقط زمانی قطعی است که هر سه شاهد موجود باشند:

1. پاسخ RPA شامل tracking code غیرخالی؛
2. همان tracking code در `waybill_jobs.result_json`؛
3. رکورد مطابق در History/Search خود UTCMS.

نبود هر شاهد ⇒ `needs_review/submission_unconfirmed`، نه `success`. `CODE-VERIFIED`

## 7. پروتکل آزمون کنترل‌شده (dry-run) پیش از هر ثبت زنده

1. Job جدید و مستقل با idempotency تازه ساخته می‌شود؛ Jobهای ambiguous دست‌نخورده
   می‌مانند.
2. `ALLOW_LIVE_SUBMIT=false` و بدون mutation در DB/UTCMS.
3. اجرای candidate به‌صورت process ایزوله روی Worker، بدون جایگزینی فایل‌های سرویس.
4. شواهد لازم در هر مرحله: status و طول body صفحهٔ فرم، نتیجهٔ گیت بند ۴،
   read-back تطبیقی هر دو موبایل، پاسخ `KalaSearch`، مقدار و برچسب استان/شهر
   مبدا و مقصد، و screenshot بدون داده‌های حساس. dry-run هیچ کلیک ناوبری روی
   `#GoFinalStep`/`#btnregisterbarname` نمی‌زند — آن‌ها ناوبری **پس از ذخیرهٔ**
   خودِ UTCMS هستند و پیش از ثبت مخفی‌اند؛ سیگنال آمادگی، visible بودن
   `#btnRegisterFinished` است. dry-run باید مقدار `#CapType`، سطح CAPTCHA، مودال
   `#GetOptCodeModal` (فقط کلاس `.show` معنی‌دار است)، کنترل ارسال OTP و تنظیمات
   passive `GetCostSettings` را ثبت کند؛ در این شاخه solver کپچا، ارسال SMS و
   کلیک mutation ممنوع است.
5. توقف فوری در نخستین mismatch؛ گزارش دلیل دقیق به‌جای تلاش کورکورانه. نبود
   کنترل ثبت نهایی یا نامشخص بودن OTP به `needs_review` می‌رود.
6. ثبت زنده تنها پس از عبور کامل مرحلهٔ ۴ و تأیید اپراتور.

## 8. طبقه‌بندی خطا، backoff و مدیریت IP

- 408/429/500/502/503/504 گذرا هستند و بودجهٔ CAPTCHA را مصرف نمی‌کنند.
- 408 عمومی یا متن «قادر به پاسخگویی» تنها retry/backoff را فعال می‌کند و به‌تنهایی
  `WORKER_IP_INDEX` را block نمی‌کند.
- reset TLS، `connection closed`، `X-Squid-Error`، 403/429 و علائم صریح block
  می‌توانند IP را موقتاً (۳۰ دقیقه) از routing خارج کنند.
- پس از 429 از `Retry-After` یا backoff حداقل ۲۵ ثانیه استفاده می‌شود.
- health check پروکسی «سلامت tunnel» را از «سلامت لحظه‌ای UTCMS» جدا می‌کند.
- اگر هیچ Worker سالم و unblocked نباشد، routing باید fail-closed باشد؛ dispatch
  به صف خیالی یا IP blocked ممنوع است.
- ورود IP به pool عملیاتی نیازمند `egress_verified=true` و `observed_country=IR`
  است؛ metadata اعلامی کافی نیست.

## 9. صف، همزمانی و قفل راننده

- concurrency مؤثر RPA روی هر Worker برابر ۱ است.
- هر راننده یک `active_execution_id` دارد؛ Job دوم همان راننده به
  `waiting_retry/driver_submission_in_progress` می‌رود.
- driver slot فقط توسط intent مالک آزاد می‌شود و با Execution زنده آزاد نمی‌شود.
- صف سوخت (`barpro.fuel.inquiry`) مستقل است و قفل submission بارنامه را تصاحب
  نمی‌کند.

## 10. CAPTCHA و استعلام سوخت

- ورود بارنامه: DNT CAPTCHA ریاضی (`CapType=1`) با CNN محلی؛ استعلام سوخت:
  `#imgCapchaEdit1` با PyTorch Fuel CRNN و fallback Keras درون همان process.
- مدل‌ها lazy و thread-safe یک بار در هر Worker بارگذاری می‌شوند؛ subprocess
  مجزا برای هر CAPTCHA ممنوع است.
- فقط نوع، ابعاد، مسیر و digest کوتاه تصویر برای تحلیل drift ثبت می‌شود.
- استعلام سوخت: کد ملی، پلاک معتبر و دورهٔ جلالی با timezone `Asia/Tehran`؛ claim
  اتمیک با unique index مانع اجرای تکراری یک راننده/دوره می‌شود.
- شواهدی از تغییر ساعت‌محور نوع CAPTCHA دیده نشده؛ تغییرات واقعی مربوط به WAF،
  rate limit و IP egress بوده است.

## 11. وضعیت فعلی و کارهای باقی‌مانده

آخرین آزمون‌های زنده (2026-08-27، Worker 1، بدون mutation):

| مرحله | نتیجه |
|---|---|
| ورود HTTP با CAPTCHA محلی | موفق `LIVE-OBSERVED` |
| `Notification` → فرم روی همان session | موفق، HTML کامل و همهٔ markerها `LIVE-OBSERVED` |
| خطای ۴۰۸ deep-link سرد | برطرف‌شده با ترتیب session `LIVE-OBSERVED` |
| اسکریپت‌های حیاتی روی session احرازشده | همه ۲۰۰ در آزمون ترتیبی `LIVE-OBSERVED` |
| prefetch «همهٔ» اسکریپت‌های صفحه | رد شد؛ اتصال پیش از `hagigihogugi*.js` فرسود `LIVE-OBSERVED` |
| session سرد جداگانه برای assetها | رد شد؛ همان TLS reset `LIVE-OBSERVED` |
| prefetch فهرست حیاتی + گیت زنده بودن فرم | پیاده و تست‌شده، در انتظار تأیید زنده `PENDING-LIVE` |
| read-back موبایل فرستنده/گیرنده در DOM | مطابق مقادیر ورودی `LIVE-OBSERVED` |
| ثبت نهایی زنده با سه شاهد | **انجام نشده** — تا عبور گیت بند ۴ مجاز نیست |

قدم بعدی مجاز: یک dry-run ایزوله با نسخهٔ فعلی؛ در صورت عبور همهٔ سیگنال‌های
بند ۴ و صحت read-backها، ثبت زنده با نظارت اپراتور و مانیتورینگ سه‌شاهدی.

## 12. چک‌لیست انتشار و بازسازی سرورها

```bash
python -m ruff check app tests
pytest -q
git push origin main
```

سپس روی هر گره (Central، Worker 2، Worker 3) با رمز از ورودی امن:

```bash
SSH_PASSWORD=***  python scripts/deploy_and_verify_all.py
```

- `manage.sh deploy` پیش از build، وجود تغییر tracked محلی را رد می‌کند و
  `git pull --ff-only origin main` می‌زند؛ پس push مقدم بر بازسازی است.
- پس از بازسازی: `bash manage.sh health`، بررسی نسخهٔ image و صحت Squid.
- تغییر transport بدون اجرای dry-run ایزوله روی همان نسخه، مجاز نیست.




# قرارداد و محدودیت‌های عملیاتی UTCMS

**آخرین بازبینی میدانی: 2026-08-27**

این سند مرجع واحد رفتار مشاهده‌شده‌ی `barname.utcms.ir` و
`utcms.ir/ShowFuelQuota.aspx` است. مقادیر این سند «قرارداد رسمی منتشرشده‌ی
UTCMS» نیستند؛ بر اساس فرم زنده، پاسخ‌های شبکه، لاگ‌های Worker و آزمون‌های
کنترل‌شده‌ی BarPro ثبت شده‌اند. هر تغییر سامانه باید ابتدا در حالت dry-run
بررسی و سپس این سند به‌روزرسانی شود.

## 1. وضعیت ثبت واقعی

- ورود HTTP با `curl_cffi` و CAPTCHA محلی در IPهای سالم موفق مشاهده شده است.
- صفحه‌ی post-login و لینک‌های منوی بارنامه قابل کشف‌اند.
- آزمون میدانی 2026-08-26 نشان داد درخواست مستقیم و بدون session به
  `/Barname/Document/HagigiHogugi` می‌تواند HTTP 408 و body کوتاه برگرداند، در حالی که
  همان صفحه پس از `Login -> Notification -> menu click` سالم باز می‌شود.
- بنابراین 408 روی deep-link سرد، به‌تنهایی شاهد outage یا block بودن IP نیست.
- آزمون 2026-08-27 نشان داد فرم می‌تواند از نظر HTML کامل تحویل شود اما
  اسکریپت‌های آن reset شده باشند؛ در این وضعیت تکمیل فیلد یا ثبت مجاز نیست و
  گیت «زنده بودن فرم» باید مسیر را متوقف کند.
- برای آزمون‌های این سند tracking code سه‌شاهدی جدید تولید نشده است؛ بنابراین ثبت موفق جدید اعلام نمی‌شود.
- `ALLOW_LIVE_SUBMIT` باید پیش‌فرض `false` بماند. فعال‌سازی آن فقط برای یک Job
  ازپیش‌اعتبارسنجی‌شده و با نظارت اپراتور مجاز است.

ثبت فقط زمانی قطعی است که هر سه شاهد موجود باشند:

1. پاسخ RPA شامل tracking code غیرخالی باشد؛
2. همان tracking code در `waybill_jobs.result_json` ذخیره شده باشد؛
3. رکورد مطابق در History/Search خود UTCMS مشاهده شود.

موفقیت UI، بسته‌شدن modal، dry-run یا status داخلی بدون این سه شاهد، اثبات
ثبت نهایی نیست.

## 2. فیلدهای اجباری فرم بارنامه

BarPro فقط فیلدهای زیر را از کاربر می‌گیرد و payload ناقص را پیش از رزرو proxy،
مرورگر و driver slot رد می‌کند:

| بخش | فیلد اجباری | قواعد |
|---|---|---|
| حساب | راننده | حساب UTCMS فعال و رمز قابل decrypt |
| خودرو | پلاک | پلاک فعال و متعلق به همان راننده |
| مبدأ | استان، شهر، آدرس | رشته‌ی غیرخالی؛ استان و شهر جداگانه |
| مقصد | استان، شهر، آدرس | رشته‌ی غیرخالی؛ استان و شهر جداگانه |
| طرفین | نام کامل فرستنده و گیرنده | شخص حقیقی: حداقل نام و نام خانوادگی؛ حقوقی: نام دفتر/شرکت |
| طرفین | موبایل فرستنده و گیرنده | شماره واقعی ایران، ۱۱ رقم و با `09`؛ با شماره راننده یا مقدار ساختگی جایگزین نشود |
| کالا | نوع کالا | مقدار غیرخالی |
| کالا | بسته‌بندی | مانند فله/کیسه؛ مطابق گزینه‌ی قابل انتخاب سایت |
| کالا | وزن | مقدار عددی مثبت با واحد تن در UI |
| کالا | ارزش تقریبی | مقدار عددی مثبت، به ریال |

کد ملی و آدرس تکمیلی طرفین، تعداد، شرح بار، نوع خودرو، کرایه،
روش پرداخت و مهلت زمانی در فرم مشاهده‌شده برای ثبت پایه اجباری نبودند و از UI
اصلی حذف شده‌اند. این فیلدها نباید با مقدار ساختگی پر شوند.

قرارداد اعمال مبدا و مقصد:

1. تب درست فعال شود؛
2. استان با تطبیق نام انتخاب و value+label همان selector بازخوانی شود؛
3. بارگذاری AJAX شهرها کامل شود؛
4. شهر فقط با تطبیق یکتا انتخاب و value+label بازخوانی شود؛
5. آدرس در textarea درج و از همان selector موفق read-back شود؛
6. در صورت هر mismatch یا پیام validation، transition به مرحله بعد ممنوع است.

## 3. CAPTCHA

| صفحه | ساختار مشاهده‌شده | Provider اصلی |
|---|---|---|
| ورود بارنامه | DNT CAPTCHA ریاضی، `CapType=1`، PNG (نمونه 129×96) | CNN محلی |
| استعلام سوخت | `#imgCapchaEdit1`، عبارت/عدد فارسی | PyTorch Fuel CRNN |
| fallback سوخت | همان تصویر | Keras OCR درون همان process |

- در داده‌های موجود شواهدی از تغییر نوع CAPTCHA بر اساس ساعت دیده نشد.
- تغییر واقعی مشاهده‌شده مربوط به WAF، rate limit، reset اتصال و IP egress بود،
  نه تغییر ساعت‌محور CAPTCHA.
- نوع، ابعاد، مسیر و digest کوتاه تصویر برای تحلیل drift ثبت می‌شود؛ پاسخ
  CAPTCHA هرگز در log یا metadata ذخیره نمی‌شود.
- مدل Fuel به‌صورت lazy و thread-safe یک بار در هر Worker process بارگذاری
  می‌شود. subprocess مجزا برای هر CAPTCHA ممنوع است.

## 4. محدودیت IP، WAF و شبکه

- UTCMS دسترسی IP ایران را انتظار دارد. هر Worker باید از Squid محلی و IP
  ثابت ایرانی خود خارج شود.
- HTTP login با fingerprint کروم `curl_cffi` پایدارتر از TLS مستقیم Chromium
  است. Chromium ممکن است `ERR_CONNECTION_CLOSED` یا صفحه‌ی «درخواست مجاز
  نمی‌باشد» دریافت کند.
- HTTP 429 و پاسخ‌های 408/500/502/503/504 transient هستند و نباید بودجه‌ی
  CAPTCHA را مصرف کنند.
- 408 عمومی یا متن «قادر به پاسخگویی» فقط retry/backoff را فعال می‌کند و به‌تنهایی
  `WORKER_IP_INDEX` را block نمی‌کند.
- reset TLS، connection closed، `X-Squid-Error`، 403/429 و علائم صریح block/egress
  می‌توانند IP مربوطه را موقتاً از routing خارج کنند.
- وقتی registry Worker دارد ولی هیچ Worker تازه، فعال و unblocked نیست، routing
  باید fail-closed باشد؛ dispatch به queue خیالی یا IP blocked ممنوع است.
- health check پروکسی باید «سلامت tunnel» را از «سلامت لحظه‌ای UTCMS» جدا کند.
  پاسخ واقعی HTTP بدون `X-Squid-Error` اثبات می‌کند Squid در دسترس است؛ یک reset
  upstream به‌تنهایی نباید Worker را دائماً drain کند.
- Clean IP screening بدون credential فقط login surface پایدار را probe می‌کند.
  `HagigiHogugi` فقط بعد از session معتبر و menu flow قابل ارزیابی است.
- ورود به pool عملیاتی نیازمند `egress_verified=true` و `observed_country=IR` است؛
  metadata اعلامی source یا فایل متنی URL به‌تنهایی کافی نیست.
- pool مشترک در Redis نگهداری می‌شود تا Workerهای Remote همان snapshot تازه را ببینند.
  نتیجه صفر، pool/file قدیمی را invalidate می‌کند.

## 5. Bridge مرورگر

- Bridge requestهای UTCMS از نوع `document`, `xhr`, `fetch` را با `curl_cffi`
  عبور می‌دهد. علاوه بر آن، فقط اسکریپت‌های حیاتی فرم صدور (jquery، jquery-ui،
  jquery.validate، formvalidation.popular، formhelper، hagigihogugitemplate و
  hagigihogugi) از همان session احرازشده پیش‌واکشی و از cache به Chromium تحویل
  می‌شوند.
- سایر JS/CSS/font/image باید توسط Chromium از Squid دریافت شوند. Bridge کردن
  همه‌ی assetها باعث serialization، resetهای TLS و timeout 480 ثانیه‌ای شد.
- آزمون 2026-08-27 نشان داد Chromium روی همین اسکریپت‌های حیاتی
  `ERR_CONNECTION_CLOSED/RESET` می‌گیرد؛ در آن حالت DOM فرم کامل است ولی فرم
  «زنده» نیست (انتخاب نوع شخص فیلد نام را باز نمی‌کند و `KalaSearch` خالی است).
  بنابراین حاضر بودن markerهای DOM شرط کافی برای تکمیل فرم نیست.
- session جدا و سرد برای assetها همان TLS reset را می‌گیرد؛ پیش‌واکشی باید در
  ادامه‌ی همان session موفق `Login → Notification → HagigiHogugi` انجام شود.
- پیش‌واکشی «همه‌ی» اسکریپت‌های صفحه رد شد: اتصال پیش از رسیدن به
  `hagigihogugi*.js` فرسود. فهرست حیاتی حداقلی الزامی است و شکست یک فایل نباید
  تحویل فرم را باطل کند.
- session دقیق `curl_cffi` که login را کامل کرده به Bridge منتقل می‌شود و برای
  documentهای صدور رزرو می‌ماند؛ ترافیک AJAX صفحه‌ی landing روی session جداگانه
  می‌رود، وگرنه اتصال مشترک می‌سوزد و navigation بعدی خطا می‌دهد. پس از مصرف فرم،
  XHRهای فرم روی همان session ارتقا می‌یابند. بازسازی session صرفاً از cookieها
  ممکن است context سرور را از دست بدهد.
- reset یا خطای asset/document نباید session احرازشده را reset کند.
- document صدور ابتدا از landing احرازشده‌ی Notification و لینک منوی داخلی باز می‌شود؛
  direct goto فقط recovery انتهایی است.

مرجع کامل رفتار الزامی ربات: [قوانین و رفتار ربات در مواجهه با UTCMS](UTCMS_BOT_BEHAVIOR_CONTRACT.md)

## 6. صف، Worker و جلوگیری از تداخل

- concurrency مؤثر RPA روی هر remote Worker برابر 1 است.
- هر راننده فقط یک `active_execution_id` دارد. Job دوم همان راننده به
  `waiting_retry/driver_submission_in_progress` منتقل می‌شود.
- driver slot فقط توسط intent مالک آزاد می‌شود و اگر Execution زنده وجود داشته
  باشد آزاد نمی‌شود.
- payload ناقص به `needs_review/payload_validation_failed` می‌رود و نباید retry
  شبکه‌ای شود.
- Job دارای tracking code دوباره submit نمی‌شود. `success` بدون tracking code
  به `needs_review/submission_unconfirmed` تنزل می‌یابد.
- اگر Worker سالم موجود نباشد، intent شکست کنترل‌شده می‌خورد، slot آزاد و Job
  برای retry آینده نگه داشته می‌شود.

## 7. زمان‌بندی پیشنهادی

UTCMS زمان تضمین‌شده یا پنجره‌ی رسمی برای ثبت پشت‌سرهم منتشر نکرده است؛ بنابراین
زمان‌بندی باید adaptive باشد، نه مبتنی بر یک ساعت ثابت:

- یک Job در هر Worker و یک Job در هر راننده؛
- preflight شبکه قبل از ایجاد browser session؛
- فاصله‌ی پایه حداقل 0.8 ثانیه به‌علاوه jitter بین عملیات سبک؛
- بعد از 429 از `Retry-After` یا backoff حداقل 25 ثانیه استفاده شود؛
- بعد از block/egress failure، IP به مدت 30 دقیقه از pool خارج شود؛
- retry راننده/tenant به‌طور پیش‌فرض 30 دقیقه است؛
- در افزایش failure rate، dispatch جدید متوقف و فقط health probe کم‌نرخ اجرا شود؛
- ثبت گروهی تنها پس از یک dry-run موفق و یک live submission دارای سه شاهد فوق.

## 8. استعلام سوخت

- endpoint عمومی فعلی `https://utcms.ir/ShowFuelQuota.aspx` است.
- ورودی‌های اجباری: کد ملی راننده، پلاک معتبر و دوره‌ی سال/ماه جلالی.
- دوره با timezone استاندارد `Asia/Tehran` محاسبه می‌شود، نه offset ثابت.
- claim اتمیک و unique index فعال، اجرای تکراری یک راننده/دوره را منع می‌کند.
- queue سوخت (`barpro.fuel.inquiry`) مستقل از صف بارنامه است و نباید driver
  submission lock بارنامه را تصاحب کند.
- status موفق فقط با quota data معتبر ثبت می‌شود؛ modal خطا، CAPTCHA ناموفق یا
  timeout باید دسته‌بندی و قابل retry باشد.

## 9. چک‌لیست تغییرات آینده UTCMS

در صورت مشاهده‌ی drift سامانه، قبل از live submit این موارد ثبت شوند:

1. URL و status نهایی؛
2. نام/نوع فیلدهای required و گزینه‌های select؛
3. signature غیرحساس CAPTCHA؛
4. headerهای `Server`, `Via`, `X-Squid-Error`, `Retry-After`؛
5. IP index و Worker؛
6. نتیجه‌ی dry-run و screenshot بدون اطلاعات حساس؛
7. نتیجه‌ی تست قرارداد payload و test suite کامل.

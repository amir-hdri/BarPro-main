# گزارش ممیزی فنی BarPro — ۲۰۲۶-۱۰-۰۶

> مبنا: `main` در `6c5564ea7483f127f2e23e785148009114bae49b`. مخزن در آغاز تغییر محلی نداشت. کاربر در ادامه همین گفتگو اصلاح کد، بهبود UI، مستندسازی و commit/push روی main را مجاز کرد. یافته‌های زیر درباره نسخه مبنا هستند؛ نتیجه اصلاحات در بخش پایانی جدا ثبت می‌شود. ارجاع‌های شماره خطِ یافته‌های مبنا به `6c5564e` مربوط‌اند و پس از اصلاح جابه‌جا شده‌اند؛ برای بازسازی از `git show 6c5564e:<path>` استفاده کنید.
>
> وضعیت سند: ممیزی مبنا نهایی شده؛ نتایج گیت نهایی اصلاحات در ادامه ثبت می‌شود.

بازتولیدهای نسخه مبنا نقص‌های واقعی زیر را تأیید کردند. مهم‌ترین مشکلات به جداسازی مشتری‌ها، جلوگیری از فراخوانی مجدد صدور، مالکیت قفل OTP و بازیابی تحویل پیامک مربوط‌اند. موفقیت بخشی از تست‌ها این مشکلات را رد نمی‌کند؛ چند ضعف دقیقاً در رفتارهایی رخ می‌دهند که بدل‌های تست آن‌ها را مدل نمی‌کنند.

## دامنه و روش

- بررسی معماری، مسیرهای حساس و تغییرات ۲۰ commit اخیر: `58a342c..6c5564e`، شامل **۸۶ فایل تغییرکرده**. ممیزی امنیتی رسمی پلاگین روی بازه ثابت ۸ commit اخیر `e664e54..6c5564e` انجام شد.
- موجودی مخزن: **۲۱۳ فایل Python در app، ۱۹۲ فایل test_*.py**. واردکردن واقعی برنامه و ساخت OpenAPI موفق بود: **۱۴۹ مسیر OpenAPI و ۹۹ schema**. این تعداد موجودی است و ادعای بازبینی خط‌به‌خط همه فایل‌ها نیست. شواهد: [snapshot](repository-snapshot.json)، [import/OpenAPI](backend-import-routes.log).
- ابتدا گراف دانش، قوانین حیاتی و قراردادهای UTCMS خوانده شد. اسکیل‌های `deep-codebase-analysis`، `fullstack-production-audit`، `codex-security:security-diff-scan`، RPA، Celery، ایمنی صدور، fullstack-sync، UI guard و بررسی استقرار به‌کار رفتند. ابزارها شامل Codex Security MCP، مرورگر واقعی CUA/Chromium، Redis ایزوله، pytest، mypy، Ruff، Black، Bandit و auditهای وابستگی بودند.
- بازتولیدهای OTP از **Redis واقعی روی Unix socket خصوصی** و کلاینت UTCMS مصنوعی استفاده کردند. بازتولیدهای گزارش‌گیری از ASGI و SQLite درون‌حافظه‌ای استفاده کردند. آزمون محدودیت ۵۰ رکورد، تابع واقعی و SQL کامپایل‌شده را با مرز دیتابیس شبیه‌سازی‌شده اجرا کرد.
- وضعیت production، firewall، IP خروجی ایران، revision دیتابیس سرور و نتیجه زنده UTCMS در این ممیزی تأیید نشده‌اند. هیچ ادعای صدور واقعی بارنامه یا موفقیت استقرار مطرح نمی‌شود.

## یافته‌های با اولویت بالا

### A01 — P1 — حذف OTP مشتری دیگر از مسیر ثبت دستی

مسیر ثبت دستی ابتدا مالکیت job را بررسی می‌کرد، اما `phone` دلخواه درخواست را به پاک‌سازی privileged می‌فرستاد. با job موفق متعلق به مشتری A و شماره مشتری B، پاسخ HTTP200 داده شد و دو کلید OTP/pending مشتری B به صفر رسید؛ هیچ درخواست UTCMS اجرا نشد.

شواهد: [بازتولید ASGI، SQLite و Redis واقعی](security-reproductions.log)، [گزارش مهرشده Codex Security](security-baseline/report.md)، source baseline در `otp_forwarder.py:522` و `otp_wakeup_consumer.py:254`. شدت امنیتی این اختلال بین tenantها Medium و اولویت عملیاتی رفع آن P1 است؛ افشای کد یا صدور غیرمجاز واقعی ادعا نشده است.

### A02 — P1 — امکان فراخوانی دوباره صدور برای سند دارای کد رهگیری

در [waybill_job_service.py:589](/Users/amirheidari/GitHub/BarPro-main/app/services/waybill_job_service.py:589) تنها وضعیت `success` مانع صدور می‌شود. درحالی‌که مسیر عادی Worker، کد رهگیری دریافتی را تا تطبیق گروهی در وضعیت `unknown/tracking_received` نگه می‌دارد. بنابراین OTP دیررس می‌تواند برای سندی با رهگیری ذخیره‌شده، دوباره `IssueDocumentByOtp` را صدا بزند.

اشکال دوم همان محدوده این است که job پیش از گرفتن قفل خوانده می‌شود و پس از گرفتن موفق قفل بازخوانی نمی‌شود؛ درخواست دوم می‌تواند بعد از اتمام درخواست اول، با شیء قدیمی دوباره صدور را اجرا کند. شاهد [otp-reproductions.log](otp-reproductions.log): سناریوی `persisted_tracking_does_not_prevent_reissue` یک فراخوانی اضافی؛ سناریوی `stale_prelease_job_allows_repeat_mutation` دو فراخوانی برای یک document. این اثبات فراخوانی تکراری برنامه است، نه ادعای ساخته‌شدن دو سند واقعی در UTCMS.

اصلاح لازم: بازخوانی وضعیت و رهگیری پایدار زیر قفل، منع صدور مستقل از status در صورت وجود tracking، و ثبت پایدار «عملیات آغازشده/نتیجه نامعلوم» برای بازیابی بدون ارسال مجدد.

### A03 — P1 — مالکیت و انقضای قفل OTP درست مدیریت نمی‌شود

[otp_keys.py:85](/Users/amirheidari/GitHub/BarPro-main/app/automation/otp_keys.py:85) برای همه دارندگان مقدار ثابت `1` می‌گذارد؛ TTL برابر ۳۰ ثانیه است و آزادسازی با `DEL` بدون تطبیق مالک انجام می‌شود. بخش حفاظت‌شده شامل ورود، صدور، ذخیره دیتابیس و شروع حمل است و تمدید قفل ندارد.

بازتولید واقعی Redis: A قفل می‌گیرد؛ پس از انقضا B می‌گیرد؛ آزادسازی دیرهنگام A قفل B را حذف می‌کند و C هم وارد می‌شود. شاهد `expired_owner_deletes_successor_lease` در [لاگ](otp-reproductions.log). افزایش TTL به‌تنهایی کافی نیست؛ توکن یکتای مالک، compare-and-delete اتمیک، تمدید کنترل‌شده و حفاظت پایدار در برابر تکرار لازم است.

### A04 — P1 — جریان پایدار OTP در سه وضعیت پیام را از دست می‌دهد

در [otp_wakeup_consumer.py:323](/Users/amirheidari/GitHub/BarPro-main/app/services/otp_wakeup_consumer.py:323):

1. ساخت گروه با `$`، پیام‌های موجود قبل از اولین اجرا را جا می‌اندازد.
2. خواندن فقط با `>`، پیام تحویل‌شده ولی ACKنشده پس از crash را بازیابی نمی‌کند؛ مسیر reclaim وجود ندارد.
3. resolver خطا را به `success:false` تبدیل می‌کند، اما مصرف‌کننده بدون بررسی نتیجه `XACK` می‌زند؛ خطای موقت هم از صف قابل تلاش مجدد خارج می‌شود.

هر سه با Redis واقعی بازتولید شدند: backlog موجود ولی صفر dispatch؛ یک pending باقی‌مانده پس از crash؛ و خطای 503 با pending صفر و تلاش بعدی صفر. شواهد: سه سناریوی نخست [لاگ OTP](otp-reproductions.log)، [کد sweep:353](/Users/amirheidari/GitHub/BarPro-main/app/services/otp_wakeup_consumer.py:353). اصلاح لازم: خواندن backlog، بازیابی pendingهای رهاشده، تفکیک نتیجه نهایی/قابل تلاش مجدد و ACK فقط پس از ثبت پایدار نتیجه. تکرار تحویل پیام نباید اجازه تکرار mutation نامعلوم UTCMS باشد.

### A05 — P1 — صدور پیش از اعتبارسنجی انتقال وضعیت انجام می‌شود

resolver وضعیت `pending` را می‌پذیرد ([otp_wakeup_consumer.py:213](/Users/amirheidari/GitHub/BarPro-main/app/services/otp_wakeup_consumer.py:213)). سرویس ابتدا صدور را انجام می‌دهد و سپس `pending → success` را درخواست می‌کند که ماشین حالت مجاز نمی‌داند ([waybill_job_service.py:778](/Users/amirheidari/GitHub/BarPro-main/app/services/waybill_job_service.py:778)).

بازتولید: یک فراخوانی صدور، سپس `StateTransitionError: 'pending' → 'success' not allowed` و **صفر commit دیتابیس**. شاهد `pending_job_issued_before_state_validation` در [لاگ](otp-reproductions.log). صلاحیت وضعیت و challenge باید قبل از POST بررسی شود و نتیجه خارجی، حتی در صورت شکست ادامه پردازش، قابل بازیابی پایدار بماند.

### A06 — P1 — کش رانندگان بین ورود دو مشتری در همان مرورگر جدا نشده است

کلید query برابر `['drivers']` است و ۱۲۰ ثانیه تازه محسوب می‌شود ([drivers/page.tsx:91](/Users/amirheidari/GitHub/BarPro-main/apps/web/src/app/drivers/page.tsx:91)). QueryClient در provider ریشه پایدار می‌ماند ([QueryProvider.tsx:10](/Users/amirheidari/GitHub/BarPro-main/apps/web/src/providers/QueryProvider.tsx:10))؛ خروج از حساب کش را پاک نمی‌کند.

بازتولید با QueryClient/QueryObserver واقعی و دو هویت مصنوعی: حساب B داده A را دریافت کرد و فهرست درخواست‌ها فقط `[A]` بود. شاهد [frontend-cache-probe.log](frontend-cache-probe.log). بازتولید کامل تعویض حساب در مرورگر به‌علت محدودیت fixture قطعی نشد؛ سطح اثبات این یافته اجرای کتابخانه واقعی همراه با تطبیق مسیر کد است. اصلاح: tenant/session در query key، لغو درخواست‌های قبلی و پاک‌سازی کش هنگام تغییر هویت.

## سایر نقص‌های عملکردی و قراردادی

| شناسه / اولویت | یافته و اثر | شاهد و اصلاح لازم |
|---|---|---|
| A07 / P2 | secret فورواردر در query URL پذیرفته می‌شود؛ خطر ورود secret مشترک به access log | بازتولید query-secret با HEALTH_CHECK پاسخ HTTP200 داد؛ Nginx در `infra/nginx/nginx.conf:44` مقدار `$request` را لاگ می‌کند. [شاهد](security-reproductions.log)، [اسکن مهرشده](security-baseline/report.md). افشای واقعی production مشاهده نشده؛ مسیر به استفاده فورواردر از query و دسترسی مهاجم به لاگ وابسته است. |
| A08 / P2 | راهنمای جدید فورواردر فقط URL و POST را می‌دهد و توکن اجباری را حذف کرده است؛ پیروی از راهنما اتصال را برقرار نمی‌کند. | [drivers/page.tsx:1024](/Users/amirheidari/GitHub/BarPro-main/apps/web/src/app/drivers/page.tsx:1024)، [otp_forwarder.py:47](/Users/amirheidari/GitHub/BarPro-main/app/api/routes/otp_forwarder.py:47)، [probe](frontend-contract-probes.log): بدون توکن 401، بدون secret تنظیم‌شده 503. راهنمای احراز هویت امن و تست اتصال لازم است؛ secret سراسری نباید در اختیار هر مشتری قرار گیرد. |
| A09 / P2 | دکمه کپی در HTTP معمولی کار نمی‌کند؛ فراخوانی مستقیم `navigator.clipboard.writeText` بدون بررسی قابلیت و مدیریت خطاست. | [drivers/page.tsx:993](/Users/amirheidari/GitHub/BarPro-main/apps/web/src/app/drivers/page.tsx:993)، [مرورگر واقعی](frontend-browser-evidence.json): `isSecureContext=false` و `clipboard=undefined` در HTTP غیر-loopback. fallback انتخاب/کپی و نمایش موفقیت فقط پس از نتیجه لازم است. |
| A10 / P2 | UI بدون هیچ بررسی اتصال می‌گوید دریافت خودکار «فعال است». health نیز با Redis سالم و secret خالی `healthy` می‌دهد، درحالی‌که intake برابر 503 است. | [history/page.tsx:1805](/Users/amirheidari/GitHub/BarPro-main/apps/web/src/app/history/page.tsx:1805)، [otp_forwarder.py:556](/Users/amirheidari/GitHub/BarPro-main/app/api/routes/otp_forwarder.py:556)، [probe](frontend-contract-probes.log). نمایش وضعیت باید از آمادگی واقعی و آخرین دریافت معتبر تغذیه شود؛ سلامت Redis به‌تنهایی آمادگی دریافت OTP نیست. |
| A11 / P2 | کد منقضی موجود در Redis Stream همچنان dispatch می‌شود و در submit_otp با زمان فعلی و TTL جدید ذخیره می‌شود. | [consumer:345](/Users/amirheidari/GitHub/BarPro-main/app/services/otp_wakeup_consumer.py:345)، [service:647](/Users/amirheidari/GitHub/BarPro-main/app/services/waybill_job_service.py:647)، سناریوی `expired_stream_code_is_dispatched` در [لاگ](otp-reproductions.log): کد یک ساعت منقضی، یک dispatch. بررسی expiry و اتصال به challenge اصلی لازم است؛ پذیرش آن توسط UTCMS اثبات نشده است. |
| A12 / P2 | تکمیل OTP مستقیماً در API یا scheduler انجام می‌شود و پراکسی process انتخاب می‌شود، نه Worker متعلق به job. | [service:665](/Users/amirheidari/GitHub/BarPro-main/app/services/waybill_job_service.py:665)، [consumer:284](/Users/amirheidari/GitHub/BarPro-main/app/services/otp_wakeup_consumer.py:284)، سناریوی `otp_completion_ignores_assigned_worker_proxy` در [لاگ](otp-reproductions.log). job مربوط به Worker2، پراکسی scheduler را گرفت. ارسال فرمان به صف Worker مالک و حفظ session/egress لازم است. ردشدن واقعی توسط WAF یا تأخیر production اندازه‌گیری نشده است. |
| A13 / P2 | اگر همه اعضای pending set منقضی باشند، پاک‌سازی اجرا نمی‌شود و دو شناسه کهنه برای همیشه AMBIGUOUS ایجاد می‌کنند. | [consumer:71](/Users/amirheidari/GitHub/BarPro-main/app/services/otp_wakeup_consumer.py:71)، سناریوی `all_stale_jobs_not_pruned` در [لاگ](otp-reproductions.log): هر دو عضو پس از resolve باقی ماندند. ابتدا staleها حذف و سپس تعداد اعضای معتبر بررسی شود. |
| A14 / P2 | بازیابی حمل از DB، قبل از بررسی ETA و حذف موارد دیده‌شده در Redis فقط ۵۰ رکورد را می‌گیرد؛ سفر آماده پشت آن‌ها دیده نمی‌شود. | [gps_shipping_manager.py:1387](/Users/amirheidari/GitHub/BarPro-main/app/automation/gps_shipping_manager.py:1387)، [بازتولید](shipping-reproductions.log): ۵۰ سفر آینده + سفر ۵۱ آماده؛ دو sweep صفر نتیجه، کنترل با limit51 یک نتیجه. فیلتر dueness در SQL یا pagination/cursor منصفانه لازم است. PostgreSQL واقعی محلی در دسترس نبود؛ مرز SQL در این بازتولید شبیه‌سازی شده است. |
| A15 / P3؛ قدیمی و باز | تاریخ نامعتبر در گزارش مدیریتی به‌جای خطای ورودی، HTTP500 می‌دهد. | [admin_reporting_service.py:383](/Users/amirheidari/GitHub/BarPro-main/app/services/admin_reporting_service.py:383)، [ASGI probe](reporting-reproductions.log). همان O5 در ISSUES.md دوباره تأیید شد. تبدیل تاریخ در schema یا نگاشت ValueError به 400/422 لازم است. |
| A16 / P2؛ قدیمی و باز | شمارنده «امروز» داشبورد مرز UTC را استفاده می‌کند و با تاریخچه تهران ۳٫۵ ساعت اختلاف دارد. | [user_reporting_service.py:721](/Users/amirheidari/GitHub/BarPro-main/app/services/user_reporting_service.py:721)، [SQLite probe](reporting-reproductions.log): بار ساعت ۰۰:۳۰ تهران در تاریخچه همان روز هست ولی today_jobs=0. همان O6 دوباره تأیید شد؛ مرز روز مشترک تهران لازم است. |

## کیفیت و شکاف‌های تست

### A17 — P2 — گیت mypy در محیط همسان با CI شکست می‌خورد

در محیط تازه Python **3.11.15** با نصب مستقیم `requirements-dev.txt` و `requirements-typecheck.txt`، دستور `mypy app/ --ignore-missing-imports` **۸ خطا در ۲ فایل، از ۲۱۳ فایل بررسی‌شده** داد: شاخه‌های ناسازگار dict/str در `waybill_job_service.py:684,829,893` و انتساب `str|None` به `str` در `otp_forwarder.py:403,412`. [لاگ کامل](backend-mypy-ci-python311.log).

اجرای اولیه در محیط محلی Python3.12 با کتابخانه‌های ML نصب‌شده، ۳۰ خطا در ۷ فایل داشت؛ ۲۲ خطای اضافه وابسته به حضور typeهای ML است و به‌عنوان همان خروجی CI گزارش نمی‌شود. [لاگ محلی](backend-mypy.log). گیت در [ci-test.yml:55](/Users/amirheidari/GitHub/BarPro-main/.github/workflows/ci-test.yml:55) و [ci-cd.yml:70](/Users/amirheidari/GitHub/BarPro-main/.github/workflows/ci-cd.yml:70) الزام‌آور است.

### A18 — اولویت رفع وابستگی‌ها؛ سطح exploitability جداگانه

ممیزی اولیه با node_modules محلی انجام شد و سپس نصب تمیز Node20 از lock نیز جدا اجرا شد. نتیجه اولیه `npm audit` برابر ۱۹ مورد بود: ۱ critical، ۱۵ high و ۳ moderate. این عدد شمار advisoryهای کتابخانه‌ای/زنجیره وابستگی است و اثبات ۱۹ مسیر نفوذ مستقل در BarPro نیست. [لاگ اولیه](frontend-audit.log).

`pip-audit -r requirements.txt --desc --strict` موفق بود و `No known vulnerabilities found` داد. این خروجی درباره resolve فعلی requirements است، نه image مستقر یا تمامی packageهای محیط محلی. [لاگ](backend-pip-audit.log).

Bandit مطابق CI با `-r app/ -ll -ii` exit1 داد و ۶ مورد گزارش کرد. دو MD5 در پروتکل UTCMS، دو `torch.load` و دو مسیر موقت باید با مدل تهدید خودشان بررسی شوند؛ جایگزینی خودسرانه MD5 ممکن است قرارداد امضای بالادست را بشکند. این شش هشدار به شش exploit تأییدشده تبدیل نشده‌اند. [لاگ](backend-bandit.log).

### A19 — P2 — integration CI اتصال واقعی سرویس‌ها را نمی‌آزماید

`pytest -m integration` با **۲۱۱۶ deselected و exit5** هیچ تستی انتخاب نکرد. دستور واقعی integration CI دو تست را اجرا و پاس کرد؛ یکی `assert True` و دیگری lifecycle با SQLite و heartbeat شبیه‌سازی‌شده است. بنابراین این خروجی اثبات همکاری PostgreSQL، Redis Streams، lease و تراکنش‌ها نیست. [لاگ marker](backend-pytest-integration-marker.log)، [لاگ مسیر CI](backend-pytest-ci-integration-paths.log)، [تحلیل کد](test-gap-audit.md).

بدل Redis در تست‌های OTP، TTL و pending entries و offset گروه را مدل نمی‌کند. به همین علت خطاهای A03/A04 با تست سبز قابل جمع‌اند. ادعاهای قطعی «رفع بحران/جلوگیری از هر تداخل» در snapshot دانش باید پس از افزودن تست Redis واقعی بازنویسی شوند؛ سند تاریخی جای شاهد فعلی را نمی‌گیرد.

### A20 — P2 — تست E2E ظاهراً محلی، مسیر شبکه خارجی دارد

`tests/test_e2e_bot.py` از HTML درون‌حافظه‌ای استفاده می‌کند، ولی `auth.login` قبل از login_url داده‌شده، HTTP-first را با LOGIN_URL تنظیمات اجرا می‌کند؛ fallback نیز URL زنده UTCMS را اضافه می‌کند. همچنین selectorهای غایب، بودجه‌های چندثانیه‌ای را به‌ترتیب مصرف می‌کنند. این تست `slow` نیست و timeout سراسری ندارد. [تحلیل و file:lineها](test-gap-audit.md).

اجرای نخست مجموعه، پس از **۴۵۴٫۸۳ ثانیه و ۶۵۷ passed** با SIGINT متوقف شد؛ پیش از توقف، پیشروی در تست E2E بسیار کند بود و سپس ادامه پیدا کرد. بنابراین ادعای «هنگ دائمی» نداریم. اجرای بعدی این تست و تست صریح اتصال زنده سوخت را کنار گذاشت. دسترسی خارجی پنهان از تحلیل کد اثبات شده؛ نتیجه موفق احراز هویت یا ثبت زنده از این اجرا اثبات نشده است. [ثبت توقف](backend-test-interruption.json)، [لاگ](backend-pytest-not-slow.log).

### A21 — P2 — تست‌های frontend در CI اجرا نمی‌شوند

فرمان `npm test` در package.json وجود دارد ولی دو workflow بررسی‌شده فقط lint/typecheck/build/audit را اجرا می‌کنند. نتیجه تست در Node20 و نصب تمیز در جدول نهایی اضافه می‌شود. این گیت باید با runtime اعلام‌شده CI سازگار و به workflow متصل شود.

## نتیجه آزمون‌ها

این جدول پس از اتمام اجراهای فعال نهایی می‌شود؛ لاگ‌های مستقل در همین پوشه نگهداری شده‌اند.

| بررسی | نتیجه فعلی |
|---|---|
| `uvx ruff check app/ tests/` | exit0؛ All checks passed |
| `black --check app/ tests/` | exit0؛ ۴۱۲ فایل بدون نیاز به تغییر |
| mypy در محیط Python3.11 مشابه CI | exit1؛ ۸ خطا در ۲ فایل |
| `pytest -m unit` | exit0؛ ۱۲۵ passed، ۱۹۹۱ deselected |
| `pytest -m integration` | exit5؛ بدون تست انتخاب‌شده |
| مسیرهای integration CI | exit0؛ ۲ passed |
| مجموعه غیر-live باقی‌مانده | در حال اجرا |
| `pip-audit -r requirements.txt --desc --strict` | exit0؛ No known vulnerabilities found |
| Bandit مطابق CI | exit1؛ ۶ هشدار نمایش‌داده‌شده |
| frontend نصب محلی: lint/typecheck/test/build | lint/typecheck/build موفق، ۳۵ تست موفق؛ وابستگی‌ها با lock کاملاً یکسان نبودند |
| frontend نصب تمیز / Node20 | در حال اجرا |
| UI واقعی 1440 و 390 | RTL و فونت و نبود overflow کلی تأیید؛ اشکالات A08/A09 باقی‌اند |
| اسکریپت‌های schema/auth/WebSocket | هر سه passed؛ دامنه محدود اسکریپت‌ها جای بازتولید عملکردی را نمی‌گیرد |
| audit-codebase / topology / memory | هر سه passed؛ فقط پیکربندی. سقف‌های اعلام‌شده Central برابر ۹۶۰۰MiB است، نه RSS زنده |
| import برنامه و OpenAPI | موفق؛ ۱۴۹ path و ۹۹ schema |

## محدودیت‌ها و مواردی که به‌عنوان باگ اثبات‌شده حساب نشدند

- استثنای مستند mobile OTP برای نمایش success پیش از History، به‌تنهایی باگ تازه شمرده نشد. مسئله A02 فراخوانی دوباره با وجود رهگیری پایدار است.
- در submit_otp، `redis_manager.get() is None` اجرای بدون lease را ممکن می‌کند؛ اما این حالت در پیاده‌سازی فعلی عموماً نبود کتابخانه Redis است، نه قطعی معمول شبکه. فقط در ضمیمه OTP به‌عنوان نقص دفاعی مشروط آمده است.
- موضوع سیاست سخت‌گیرانه IP ایرانی در O1 قبلاً با تصمیم استقراری کاربر بسته شده؛ پیشنهاد تضعیف آن داده نشده است. وضعیت زنده IP/پروکسی بررسی نشده است.
- O2/O3/O4 در ISSUES.md درباره recovery دستی حمل و ETAهای قدیمی هنوز lead معتبرند؛ کد مسیر unknown و 409 مشاهده شد، ولی بازتولید جدید کامل همه آن‌ها در این کار انجام نشد و در شمار یافته‌های بازتولیدشده نیامده‌اند.
- Docker daemon محلی در دسترس نبود. `initdb` نیز به‌دلیل نبود binary سرور `postgres` اجرا نشد؛ فقط ابزارهای libpq موجودند. مهاجرت‌ها و اجرای image کامل PostgreSQL16 در این ممیزی تأیید نشده‌اند. [خطای setup](postgres-isolated-setup.log).
- بازبینی گیت ظاهری UI نشان‌دهنده موفقیت end-to-end سامانه زنده نیست. تصاویر صرفاً ساخت محلی با داده مصنوعی هستند: [desktop](frontend-drivers-desktop.png)، [mobile](frontend-drivers-mobile.png).

## ترتیب پیشنهادی رفع و معیار پذیرش

1. **جداسازی مشتری و صدور:** A01/A02/A03/A05/A06؛ معیار: هیچ کلید مشتری دیگر تغییر نکند، رهگیری موجود هیچ POST تازه‌ای تولید نکند، مالک قدیمی نتواند قفل مالک جدید را حذف کند، و انتقال نامعتبر قبل از mutation رد شود.
2. **تحویل پایدار OTP:** A04/A11/A12/A13؛ معیار: restart و crash و 503 با Redis واقعی آزمایش شود، کد منقضی dispatch نشود، و تکمیل روی Worker/egress مالک انجام شود.
3. **قرارداد محصول و عملیات:** راهنمای توکن امن، کپی سازگار با HTTP، وضعیت واقعی اتصال، pagination بازیابی حمل و یکسان‌سازی تاریخ تهران.
4. **گیت‌های انتشار:** رفع mypy، triage و ارتقای dependencyهای واقعاً مرتبط، integration با سرویس واقعی، حذف دسترسی خارجی پنهان از E2E، اجرای frontend tests در runtime CI و سپس اجرای دوباره کامل گیت‌ها.

معیارهای بالا مبنای اصلاح شدند. نتیجه کد فعلی و محدودیت‌های باقی‌مانده در بخش زیر آمده است؛ این گزارش گواهی وضعیت production نیست.


## اصلاحات مجازشده و معیار پذیرش توسعه‌یافته

کاربر علاوه بر رفع نقص‌ها، ساده‌سازی رابط، تفکیک بارنامه هر راننده/روز، نمایش هر استعلام سوخت با تاریخ خودش، اصلاح نقشه و GPS شبیه‌سازی‌شده را خواست. ترجیح نهایی کاربر، انتقال منطقی نقطه حرکت به نزدیک‌ترین خیابان قابل‌تردد است؛ نقطه انتخابی اولیه برای ردگیری تغییر نگه داشته می‌شود.

| یافته/نیاز | اصلاح کد | شاهد رگرسیون |
|---|---|---|
| A01–A05، A11–A13 | شماره از job/راننده مجاز، challenge پایدار، ورکر مالک، lease توکن‌دار، قفل ردیف و fence قبل از POST، reclaim و ACK نتیجه نهایی، جلوگیری از سند دوم همان راننده | `tests/test_otp_reliability_regressions.py`، `tests/test_otp_wakeup_and_lifecycle.py`، [گزارش OTP](otp-remediation-verification.md) |
| A06 | کلید query دارای هویت، لغو درخواست و پاک‌سازی هنگام تغییر حساب | تست session-query و گیت مرورگر A→خروج→B |
| A07–A10 | رد query secret، config بدون secret و دارای مالکیت، readiness واقعی، کپی HTTP با نتیجه واقعی، پیام accepted به‌جای صدور | `tests/test_otp_forwarder_hardening.py`، [تست route و نقشه](map-and-route-tests.log) |
| A14–A16 | cursor کلید اصلی برای recovery، تاریخ نامعتبر 4xx، مرز مشترک روز تهران | `tests/test_audit_shipping_reporting_regressions.py`، [تاریخ history](history-date-final.log) |
| A17 | اصلاح typeهای JSON و import اختیاری مدل‌ها | گیت mypy نهایی با Python3.11 و محیط ML |
| A18 | ارتقای سازگار Next/Axios/Sharp/parser و محدودسازی load مدل به tensor، فایل‌های خصوصی بدون symlink، حفظ MD5 قراردادی | [رفع گیت امنیت](SECURITY_GATE_FIXES.fa.md)، npm/pip audit و Bandit نهایی |
| A19–A21 | تست Redis واقعی و PostgreSQL سرویس‌دار، E2E محلی با شبکه بسته، live opt-in، اجرای تست frontend روی Node20 در CI | [گزارش integration](HERMETIC_INTEGRATION.fa.md) و لاگ‌های نهایی |
| سوابق راننده/روز | فیلتر سمت API، صفحه‌بندی و پیوند روشن از راننده؛ هر استعلام رکورد مستقل با زمان و دوره سهمیه | تست‌های history/record-filters و مرورگر |
| هویت تاریخی سوخت | snapshot نام/پلاک و زمان شروع/پایان؛ داده قدیمی بدون جعل مقدار تاریخی | `tests/test_history_identity_contracts.py` و migration042 |
| نقشه و آدرس | fallback محدود، حذف پوشش محوکننده، بازنشانی آدرس قدیمی، geocode خیابانی و cache دقیق‌تر، popup با textContent | `tests/test_map_address_regressions.py`، `apps/web/test/map-tiles.test.mjs` و مرورگر |
| GPS و مسیر منطقی | نگهداری نقطه اولیه و نقطه مؤثر خیابان، محدودیت snap و metadata، ETA محافظه‌کارانه، رد مختصات/ETA نامعتبر | تست‌های GPS و route authority و read-back Android؛ بدون اجرای زنده |

دو نقص تکمیلی هنگام بهبود UI پیدا شدند: تاریخچه سوخت فقط آخرین ۱۰۰ رکورد را client-side فیلتر می‌کرد و فیلتر راننده را اعمال نمی‌کرد؛ snapshotهای سهمیه نیز جمع می‌شدند. همچنین آدرس‌های کنترل‌شده توسط کاربر در popup نقشه مستقیماً HTML می‌شدند. این مسیرها در اصلاحات پوشش داده شدند. تاریخ API بدون offset، با توجه به افزودن Z در formatter موجود، به‌عنوان باگ قطعی ۳٫۵ ساعته UI شمرده نشده است؛ serialization صریح UTC بهبود قرارداد API است.

## محدودیت‌های باقی‌مانده و ارتقا

- `npm audit --audit-level=moderate` در نصب تمیز ثبت‌شده هنوز exit1 با **۸ high** از زنجیره ابزار توسعه `braces` می‌دهد (GHSA-vfj7-8cjw-p6xm، بازه `*`). نسخه اصلاح‌شده سازگار در بررسی موجود نبود. این تعداد ۸ exploit مستقل برنامه نیست. `npm audit --omit=dev` صفر است. هیچ bypass یا ارتقای major کور برای سبزکردن CI اضافه نشد؛ ci-cd همچنان آن را مسدود می‌کند.
- migration سوابق سوخت و هماهنگی همه Worker/API/Scheduler برای rollout لازم است. worker قدیمیِ دارای صدور inline باید drain شود. job قدیمی فاقد challenge معتبر، خودکار صادر نمی‌شود و به تطبیق فقط‌خواندنی نیاز دارد.
- PostgreSQL16، Docker build/runtime، WAF/IP، سخت‌افزار Android و UTCMS زنده محلی آزموده نشده‌اند. تست SQLite قفل PostgreSQL را اثبات نمی‌کند. هیچ mock GPS شاهد حضور واقعی خودرو نیست.
- بخش‌های هم‌زمان مرتبط با تفکیک AGENTS، agent-reference و Gemini متعلق به کار دیگری‌اند؛ بدون تغییر حفظ شده و از کامیت این ممیزی جدا می‌مانند.

## گیت نهایی اصلاحات

نتیجه اجرای کامل در این بخش و فایل‌های `*-final.log` ثبت می‌شود. اجرای موردی جای اجرای کامل را نمی‌گیرد.

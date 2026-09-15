# گزارش راستی‌آزمایی جلسه Antigravity و ارزیابی سامانه ثبت GPS

**مرجع جلسه:** 609d52c3-0463-430c-bb62-c967a912e9bc  
**تاریخ بررسی:** ۱۵ سپتامبر ۲۰۲۶  
**مخزن و commit بررسی‌شده:** BarPro-main در 9d2198d  
**دامنه:** راستی‌آزمایی ادعاهای جلسه، مسیرهای /shipping/*، کلاینت موبایل UTCMS، Session Vault، Android Bridge و بسته FakeTraveler.

## حکم اجرایی

ادعاهای جلسه درباره اصلاح هدرها، جداسازی دو میزبان UTCMS، محاسبه SecurityKey، استفاده از data=، مسیر GET برای refresh و وجود گارد پراکسی عمدتاً با کد و آزمون‌های محلی تأیید می‌شوند. با این حال، چند ادعای کلیدی جلسه بیش از شواهد موجود قطعی بیان شده‌اند: «عبور ۱۰۰٪ بدون بلاک»، «رفع کامل 429»، «کش ۱۱۲ تا ۱۱۵ دقیقه‌ای JWT»، «صحت قطعی قرارداد کسب‌وکاری شروع/پایان»، و «اجرایی بودن Android Bridge» از شواهد موجود نتیجه نمی‌شوند.

سامانه فعلی ثبت GPS یک ثبت سرورمحور با مختصات anchor و مسیر برنامه‌ریزی‌شده است. مسیر Android/FakeTraveler هنوز در حد طرح و پل مشاهده‌ای است؛ پل فعلی عمداً هیچ مکان‌یابی یا کلیک ثبت بار انجام نمی‌دهد. در محیط production نیز ALLOW_LIVE_SUBMIT=False است، Redroid/ADB/FakeTraveler مستقر نیست و هیچ ثبت GPS زنده در این بررسی انجام نشد.

چهار ریسک بحرانی باید پیش از فعال‌سازی ثبت زنده برطرف شوند:

1. پاسخ business-level ناموفق مانند resultCode=4014 می‌تواند موفقیت تلقی شود و وضعیت را in_transit یا delivered کند.
2. برای start و finish قفل توزیع‌شده، CAS یا fencing وجود ندارد؛ درخواست‌های هم‌زمان چند mutation واقعی ایجاد می‌کنند.
3. status می‌تواند بدون بررسی مالکیت tenant از Redis به tenant دیگر برگردد و finish قبل از احراز مالکیت، وضعیت Redis را تغییر می‌دهد.
4. doc_no ارسالی به Job، سند UTCMS یا شاهد reconciliation متصل نیست و می‌تواند سندی غیر از سند Job را هدف بگیرد.

## درجه شواهد

- CODE VERIFIED: مستقیماً از کد فعلی قابل مشاهده است.
- TEST VERIFIED: آزمون محلی یا شبیه‌سازی کنترل‌شده روی کد فعلی پاس شده است.
- HISTORICAL LIVE VERIFIED: در artifactهای جلسه، اجرای زنده تاریخی ثبت شده؛ الزاماً وضعیت امروز نیست.
- RUNTIME UNVERIFIED: کد وجود دارد، اما دستگاه/زیرساخت/اجرای زنده برای آن موجود نیست.
- NOT PROVEN / OVERCLAIMED: ادعا از شواهد موجود قوی‌تر است یا با شواهد مخالف روبه‌روست.

## ماتریس ادعاهای جلسه

| ادعا | حکم | مدرک و محدودیت |
|---|---|---|
| default_headers=False هدرهای Client Hints دسکتاپ را حذف می‌کند | CODE/TEST VERIFIED | در app/automation/utcms_mobile_client.py:157-163,215-222 و wire capture تاریخی جلسه. این فقط حذف هدرهای پیش‌فرض است و به‌تنهایی اثبات‌کننده عبور WAF نیست. |
| X-Requested-With حذف شده است | CODE/TEST VERIFIED | _mobile_base_headers() در app/automation/utcms_mobile_client.py:120-132 چنین هدرهایی ندارد؛ نبودن آن در capture تاریخی گزارش شده است. |
| Accept مطابق Axios است | CODE/TEST VERIFIED | مقدار در app/automation/utcms_mobile_client.py:127-132 ثابت است. |
| دو میزبان cptch.utcms.ir و mobservices-barname.utcms.ir لازم‌اند | VERIFIED، اما «۱۰۰٪ بدون بلاک» ثابت نیست | config فعلی API را روی mobservices دارد و CapJS روی cptch است. artifact جلسه login/fleet موفق دارد، اما همان جلسه non-JSON، 429 و business rejection هم دارد. |
| اصلاح _post از content= به data= | CODE/TEST VERIFIED | app/automation/utcms_mobile_client.py:224-233 بایت‌های JSON امضاشده را با data= می‌فرستد. |
| refresh با GET و query parameter انجام می‌شود | CODE/TEST VERIFIED؛ live refresh کامل نیست | app/automation/utcms_mobile_client.py:462-473 و تست contract. در stepهای 2238/2240 جلسه، refresh زنده پاسخ non-JSON داشته است. |
| ServicePassword و SecurityKey مطابق APK هستند | CODE و APK-string VERIFIED | محاسبه در app/automation/utcms_mobile_client.py:134-150؛ موفقیت login تاریخی سازگاری عملی را به‌صورت غیرمستقیم نشان می‌دهد. |
| OTP چهار تا هشت رقم است | TEST VERIFIED فقط | boundary test محلی این بازه را می‌پذیرد؛ مدرک رسمی UTCMS یا مشاهده زنده برای کل بازه ارائه نشده است. |
| endpointهای PDF، تاریخ و revoke درست‌اند | CODE/TEST VERIFIED | قرارداد متدها و guardها تست شده‌اند؛ فقط تاریخ شمسی شاهد live موفق دارد، PDF و revoke live-verified نیستند. |
| CapJS PoW کار می‌کند | HISTORICAL LIVE VERIFIED | چند اجرای تاریخی challenge/redeem در artifact جلسه؛ این نتیجه به certificate، شبکه و وضعیت فعلی وابسته است. |
| نبود proxy در production با HTTP 503 متوقف می‌شود | CODE/TEST VERIFIED | app/api/routes/shipping_gps.py:174-180,296-301؛ outage زنده در production اجرا نشده است. |
| Session Vault JWT را ۱۱۲ تا ۱۱۵ دقیقه cache می‌کند | FALSE AS STATED | token در app/automation/gps_shipping_manager.py:468-475 با TTL پیش‌فرض ۲۴۰ ثانیه و refresh token با TTL 7000 ثانیه ذخیره می‌شود. عدد تاریخی 6731s مربوط به refresh token یا یک مشاهده خاص است، نه TTL عمومی JWT. |
| Session Vault، 429 را eradication می‌کند | OVERCLAIMED | loginهای تکراری را کم می‌کند؛ Redis failure، انقضای cache، force reauth و مسیرهای دیگر هنوز می‌توانند login/429 ایجاد کنند. |
| asymmetry بین start و finish قرارداد قطعی کسب‌وکاری است | CODE VERIFIED؛ BUSINESS CONTRACT UNVERIFIED | start فقط StartShippingWithGps و finish دو mutation را صدا می‌زند (shipping_gps.py:185-215,307-360). نام endpointها در APK وجود دارد، اما ترتیب و معنای کسب‌وکاری با ثبت GPS زنده ثابت نشده است. |
| Android Bridge با ۵۷ تست اجرایی شده است | STALE/INACCURATE | کد فعلی observation-only است؛ tests/test_android_bridge.py و مجموعه ترکیبی فعلی ۹۶ تست موبایل/Bridge را نشان می‌دهند، نه ۵۷ تست اختصاصی معتبر. runtime دستگاه اثبات نشده است. |
| «۰٪ WAF block» و «۱۰۰٪ موفقیت» | NOT PROVEN / OVERCLAIMED | یک یا چند flow موفق تاریخی نمی‌تواند نرخ صفر بلاک را ثابت کند؛ همان session شامل 429، non-JSON و rejection است. |
| full suite «۱۰۰/۱۰۰» یا «۷۴ passed» به‌عنوان وضعیت فعلی | STALE | 74 passed فقط snapshot تاریخی یک subset است. تعداد تست باید از اجرای commit فعلی گزارش شود. |

## مسیر فعلی ثبت GPS

### start

در app/api/routes/shipping_gps.py:130-235، endpoint ابتدا feature flag را چک می‌کند، Job/driver را می‌خواند، state را از Redis می‌گیرد، route anchor را با tolerance 0.0002 تطبیق می‌دهد، origin witness را اضافه می‌کند، سپس از Session Vault به UTCMS login/client می‌گیرد و StartShippingWithGps را می‌فرستد. پس از هر پاسخ dictionary، بدون اعتبارسنجی business result، وضعیت in_transit ذخیره و پاسخ started برگردانده می‌شود.

### finish

در app/api/routes/shipping_gps.py:247-382، state از Redis بار می‌شود و مقصد تطبیق داده می‌شود. مقصد به gps_list اضافه می‌شود، سپس وضعیت finishing در Redis ذخیره می‌گردد؛ بعد از آن _get_job_and_driver() و مالکیت Job بررسی می‌شود (:283-290). در ادامه FinishShippingWithGps و RegisterEndOfShipping اجرا می‌شوند و در صورت هر dictionary بودن پاسخ‌ها، state به delivered تغییر می‌کند.

### status

در app/api/routes/shipping_gps.py:390-460 اگر state در Redis موجود باشد، پاسخ بر اساس همان state ساخته می‌شود. مسیر state-first قبل از احراز مالکیت Job، زمینه افشای state بین tenantها را ایجاد می‌کند.

### waypoint و GPS evidence

init_shipping() در app/automation/gps_shipping_manager.py:688-735 waypointهای interpolated را برای نمایش می‌سازد. کامنت کد می‌گوید waypointها نباید evidence تلقی شوند و فقط gps_list operator/device مجاز است؛ اما خود gps_list فقط Type، مختصات، altitude، speed و Date دارد و metadata لازم برای provider، observation time، Android session و provenance را ندارد.

## یافته‌های بازتولیدشده و رتبه‌بندی ریسک

### CRITICAL-1: موفقیت کاذب در rejection کسب‌وکاری

UtcmsMobileClient._post() در app/automation/utcms_mobile_client.py:248-256 فقط خطای HTTP و resultCodeهای 3000/3001 را reject می‌کند. routeهای GPS هر dictionary دیگری را موفق می‌دانند (shipping_gps.py:216-227 و :360-375).

در بازتولید کنترل‌شده محلی، resultCode=4014 برای start به status=started و state in_transit تبدیل شد. برای finish نیز finish resultCode=4014 همراه history resultCode=1 به status=delivered تبدیل شد. این تست هیچ mutation زنده‌ای به UTCMS نفرستاد، اما مسیر تصمیم‌گیری فعلی را اثبات می‌کند.

**اثر:** ثبت داخلی موفق می‌شود در حالی‌که UTCMS ممکن است سند را رد کرده باشد؛ سپس retry یا reconciliation می‌تواند وضعیت متناقض و ثبت تکراری ایجاد کند.

**شرط رفع:** schema/allowlist موفقیت برای هر endpoint، بررسی resultCode، obj، پیام و witnessهای UTCMS؛ عدم تغییر state تا تأیید صریح mutation.

### CRITICAL-2: نبود mutation lock و compare-and-set

Redis در save_shipping_state() و load_shipping_state() فقط GET/SET معمولی است (gps_shipping_manager.py:670-685). start بین load و mutation قفل ندارد. finish نیز guard وضعیت و دو mutation را بدون fencing انجام می‌دهد.

بازتولید هم‌زمان محلی:

~~~text
CONCURRENT_START  => utc_ms_mutations=2
CONCURRENT_FINISH => finish_mutations=2, history_mutations=2
~~~

**اثر:** دو worker یا retry شبکه می‌توانند دو ثبت start یا چهار mutation finish ایجاد کنند.

**شرط رفع:** lock کوتاه‌مدت per job، token fencing، CAS روی version/state، idempotency key و ثبت durable mutation intent پیش از فراخوانی UTCMS.

### CRITICAL-3: نشت tenant و تغییر state پیش از احراز مالکیت

GET /shipping/status/{job_id} در صورت وجود state Redis، مالکیت Job را به‌طور مستقل verify نمی‌کند. در تست کنترل‌شده، tenant دوم state شامل doc-owned را دریافت کرد:

~~~text
CROSS_TENANT_STATUS => returned_status=in_transit, doc_no=doc-owned
~~~

در finish، state finishing قبل از _get_job_and_driver() ذخیره می‌شود. با Job متعلق به tenant دیگر، پاسخ HTTP 404 برگشت اما state قبل از auth ذخیره شده بود:

~~~text
CROSS_TENANT_FINISH => http=404, state_saved_before_auth=['finishing']
~~~

**شرط رفع:** احراز tenant و driver قبل از هر read/write state؛ کلید Redis tenant-scoped؛ status از DB/ownership شروع شود، نه از state قابل حدس با job id.

### CRITICAL-4: عدم binding بین doc_no و Job

ShippingStartRequest.doc_no در shipping_gps.py:38-45 از client گرفته می‌شود و در init_shipping() ذخیره و در start_shipping_with_gps() استفاده می‌شود (:140 و :191-197). مقایسه‌ای با WaybillJob.document_id، result_json، tracking code، mutation_status یا reconciliation انجام نمی‌شود.

بازتولید محلی نشان داد Job معتبر می‌تواند با doc_no=doc-unrelated mutation را فراخوانی کند.

**اثر:** driver معتبر می‌تواند سند دیگری از همان حساب را هدف بگیرد یا سندی را mutate کند که سه witness ثبت موفق آن موجود نیست.

### HIGH-5: Redis outage پس از mutation fail-open است

save_shipping_state() اگر Redis manager مقدار None بدهد، بی‌صدا return می‌کند (gps_shipping_manager.py:670-675). بنابراین ممکن است UTCMS mutation موفق شود، API پاسخ success بدهد و state لازم برای finish ذخیره نشده باشد:

~~~text
REDIS_UNAVAILABLE => save_raised=False, load_after_save=None
~~~

**شرط رفع:** بعد از mutation موفق، persistence اجباری و قابل اثبات؛ در failure باید نتیجه unknown/reconciling شود، نه success بی‌قید.

### HIGH-6: state transitionهای نامعتبر

start فقط in_transit و delivered را block می‌کند (shipping_gps.py:136-138). stateهای finishing، failed و ready می‌توانند دوباره start شوند. بازتولید:

~~~text
finishing -> started (1 mutation)
failed    -> started (1 mutation)
ready     -> started (1 mutation)
~~~

همچنین finish ابتدا finishing را ذخیره می‌کند و بعد credential را چک می‌کند؛ نبود credential state را در finishing گیر می‌اندازد.

**شرط رفع:** ماشین حالت صریح و transaction/fence برای انتقال‌ها؛ مسیر unknown/reconciling/needs_review برای نتیجه مبهم.

### HIGH-7: timestamp و فاصله GPS مصنوعی یا mislabeled هستند

interpolate_waypoints() در app/automation/gps_shipping_manager.py:254-345 waypoint را بر اساس مسیر خط مستقیم و زمان تهران تولید می‌کند؛ timestamp با literal Z منتشر می‌شود، در حالی‌که Z باید UTC باشد. skew بازتولیدشده ۳.۵ ساعت بود. در finish نیز Date از dest_wp["ts"] تخمینی start گرفته می‌شود (shipping_gps.py:270-280)، نه زمان واقعی مشاهده finish.

distance_km در gps_shipping_manager.py:406-413 از Haversine با ضریب 1.25 تخمین زده می‌شود و همان مقدار به gPSTotalTraveledDistanceField می‌رود؛ measured travel distance نیست. altitude و speed نیز operator-supplied هستند.

**اثر:** evidence قابل دفاعِ دستگاه/سرویس مکان‌یابی نیست و ممکن است UTCMS یا reconciliation آن را با داده واقعی اشتباه بگیرد.

### HIGH-8: نگهداری state فقط در Redis با TTL ثابت

save_shipping_state() state را با TTL ثابت 86400 ذخیره می‌کند (gps_shipping_manager.py:670-675)، بدون persistence در DB و بدون تمدید TTL. حمل طولانی‌تر از ۲۴ ساعت state را از دست می‌دهد؛ برای finishing/failed نیز reconciliation GPS مستقل وجود ندارد.

### HIGH-9: TLS verification خاموش است

UtcmsMobileClient.__init__ مقدار verify=False دارد (utcms_mobile_client.py:100-117) و همان مقدار به همه curl_cffi.AsyncSessionها می‌رسد (:157-164، :215-222 و مسیر CapJS). بررسی تازه certificate هر دو میزبان را قابل verify نشان داد (cptch_tls=0 و mobservices_tls=0).

**اثر:** credential، bearer token و mutation payload در برابر MITM آسیب‌پذیرند.

**نشانه نگهداری:** سه تست قدیمی در tests/test_audit_verification_goal.py انتظار دارند verify اصلاً وجود نداشته باشد؛ با کد فعلی هر سه fail شدند. این شکست باید با تصمیم امنیتی روشن برطرف شود، نه با به‌روزرسانی کورکورانه تست.

### MEDIUM-10: اعتبارسنجی ورودی ناقص

- Pydantic برای latitude/longitude مقدارهای NaN/Infinity را رد می‌کند.
- job_id و doc_no خالی در مدل request پذیرفته می‌شوند.
- payload ذخیره‌شده با NaN می‌تواند extract_coordinates_from_payload() را با ValueError متوقف کند.
- origin و destination یکسان پذیرفته می‌شوند و distance صفر تولید می‌شود.

## اجرای آزمون و وضعیت محیط

آزمون‌های فعلی روی checkout جاری:

~~~text
tests/test_shipping_gps_contract.py
tests/test_shipping_gps_runtime.py
tests/test_gps_session_vault.py
16 passed in 0.35s

tests/test_utcms_mobile_contract.py
tests/test_android_bridge.py
tests/test_mobile_waybill_bot.py
tests/test_worker_proxy_and_rotator.py
96 passed in 6.34s

ruff روی ماژول‌های GPS/mobile/bridge و تست‌های مرتبط
All checks passed!
~~~

ممیزی تاریخی tests/test_audit_verification_goal.py در checkout فعلی:

~~~text
3 failed, 12 passed
~~~

هر سه شکست از این انتظار قدیمی ناشی می‌شوند که AsyncSession فقط default_headers=False داشته باشد؛ کد فعلی verify=False را نیز پاس می‌کند. این تست‌ها یک regression/security signal هستند، نه مدرک شکست هدرها.

محدودیت‌های runtime:

- image production شامل pytest نیست؛ اجرای تست داخل آن با No module named pytest متوقف شد.
- production روی 9d2198d است و ALLOW_LIVE_SUBMIT=False.
- /healthz سالم و /readyz آماده گزارش شده، اما probe زنده ITMB/cache در readiness skip شده است.
- هیچ Redroid، ADB listener، binder evidence یا FakeTraveler مستقر در production مشاهده نشد.
- build FakeTraveler اجرا نشد چون محیط JDK 11 دارد و Gradle به JDK 17 نیاز دارد؛ این blocker محیطی است، نه pass منبع.
- در این بررسی هیچ POST/ثبت GPS زنده به UTCMS اجرا نشد.

## Android Bridge و FakeTraveler

پل app/android_bridge/ عمداً observation-only است. AndroidBridge._require_enabled() در app/android_bridge/client.py:268-275 در حالت فعلی bridge_disabled می‌دهد و probe فقط boot، package path، SDK، UI و proxy setting را مشاهده می‌کند (:285-305 به بعد). خروجی CLI نیز execution_authorized=False است.

بسته FakeTraveler با package cl.coders.faketraveler بررسی شد. geo: فقط inputهای UI را پر می‌کند؛ applyLocation() سرویس provider را شروع می‌کند و دکمه Apply به Stop تغییر می‌یابد. بنابراین کلیک تکراری یا فرض «geo intent یعنی location applied» معتبر نیست. receiver با action org.woheller69.mocklocation.UPDATE_LOCATION وجود ندارد؛ سرویس exported=false است.

نتیجه آمادگی Android:

| لایه | وضعیت |
|---|---|
| سورس Bridge و fail-closed disabled state | CODE/TEST VERIFIED |
| ADB به serial مشخص و خواندن packageها | RUNTIME UNVERIFIED |
| FakeTraveler build/install | BLOCKED تا JDK 17 |
| provider applied و read-back از Android | UNVERIFIED |
| اجرای اپ رسمی com.baarnameshahri روی Redroid | UNVERIFIED |
| ثبت/finish از اپ رسمی با یک session فعال | UNVERIFIED |
| اثبات WAF/IP برای مسیر Android | UNVERIFIED |

## اشکال مدیریت شواهد

artifactهای جلسه در مسیر زیر حاوی JWT، refresh token، شماره ملی، تلفن و مشخصات خودرو هستند:

/Users/amirheidari/.gemini/antigravity/brain/609d52c3-0463-430c-bb62-c967a912e9bc

این یک defect جدی در evidence handling است. گزارش حاضر عمداً هیچ credential یا داده شخصی را بازنشر نمی‌کند. باید tokenها revoke/rotate، artifactها redacted و دسترسی فایل‌ها محدود شود؛ همچنین از درج token خام در transcript و log جلوگیری شود.

## نتیجه و معیار فعال‌سازی

در وضعیت فعلی، سامانه برای **dry-run، استخراج مختصات، نمایش route و آزمون قرارداد** قابل استفاده است، اما برای ثبت GPS زنده آماده اعلام نمی‌شود. فعال‌سازی باید تا تحقق این معیارها متوقف بماند:

1. allowlist موفقیت برای هر UTCMS mutation و witness قابل ذخیره.
2. binding قطعی Job/tenant/driver/document و احراز مالکیت قبل از هر state mutation.
3. lock/CAS/fencing و idempotency برای start، finish و history.
4. state durable در DB و مسیر unknown -> reconciling -> success|needs_review.
5. TLS verification روشن با CA صحیح و تست‌های contract به‌روز.
6. timestamp UTC واقعی، provenance کامل، provider/session ID و تفکیک planned waypoint از observed sample.
7. اجرای آزمایشگاهی Redroid + FakeTraveler با JDK 17، ADB خصوصی، provider read-back و تست end-to-end بدون live submit پیش‌فرض.
8. آزمون production کنترل‌شده فقط پس از ثبت مجوز، با یک سند آزمایشی و witnessهای سه‌گانه؛ نتیجه HTTP یا پاسخ browser به‌تنهایی proof نیست.

این گزارش بر اساس کد commit جاری، آزمون‌های محلی، شبیه‌سازی‌های کنترل‌شده، artifactهای تاریخی جلسه و بررسی سورس/APK تهیه شده است. نتیجه آن برای تصمیم release است؛ ادعای موفقیت ثبت زنده GPS در این بررسی وجود ندارد.

## اصلاحات اعمال‌شده پس از ممیزی

پس از ممیزی، اصلاحات زیر در کد اعمال و با تست پوشش داده شد:

- پاسخ mutationهای GPS فقط با resultCode صریح 200 پذیرفته می‌شود؛ envelope ناقص یا business rejection به unknown/needs-review مسیر می‌گیرد.
- start و finish قفل توزیع‌شده per-job دارند و در صورت نبود قفل، mutation اجرا نمی‌شود.
- status و finish پیش از خواندن یا نوشتن state، مالکیت tenant/job و driver را بررسی می‌کنند.
- doc_no باید تنها document_id معتبر Job باشد؛ سند مبهم یا نامرتبط رد می‌شود.
- state در Redis با TTL هفت‌روزه و در result envelope خود Job نیز ذخیره می‌شود؛ شکست هر دو storage success کاذب تولید نمی‌کند.
- timeout یا خطا پس از آغاز POST به وضعیت unknown می‌رود و تکرار خودکار ممنوع می‌ماند.
- finish بدون measured_distance_km مثبت از دستگاه یا اپ رسمی، fail-closed می‌شود؛ فاصله تخمینی route دیگر به‌عنوان distance اندازه‌گیری‌شده ارسال نمی‌شود.
- timestampهای evidence از زمان مشاهده UTC تولید می‌شوند و provider/provenance/ObservedAt همراه anchor ثبت می‌گردد.
- TLS verification کلاینت موبایل به‌صورت پیش‌فرض روشن شد و خاموش‌کردن آن در production ممنوع است.
- رابط وب پیش از پایان حمل، مقدار مسافت اندازه‌گیری‌شده را به‌صورت صریح مطالبه می‌کند.
- artifactهای موقت SSH که host-key checking را خاموش و credential را از transcript استخراج می‌کردند حذف شدند؛ preflight audit اکنون سبز است.

شواهد اجرای پس از اصلاح:

~~~text
GPS/mobile/bridge regression: 102 passed in 1.34s
Ruff: All checks passed
Frontend lint: passed
Frontend production build: passed
Codebase audit: passed
Memory audit: passed
Topology audit: passed
Live HTTP healthz: {"status":"ok"}
Live HTTP readyz: status=ready; database/browser/config/queue/circuit_breaker=ok
Live TLS: cptch ssl_verify_result=0; mobservices ssl_verify_result=0
Live read-only CapJS site-key probe: key present; no mutation endpoint called
~~~

Full repository pytest در این محیط پس از گزارش 102 تست، در teardown بدون خروجی جدید hang کرد و به‌صورت کنترل‌شده متوقف شد؛ بنابراین برای آن ادعای pass کامل ثبت نمی‌شود. هیچ ثبت GPS یا mutation زنده UTCMS در این اصلاحات اجرا نشده است.

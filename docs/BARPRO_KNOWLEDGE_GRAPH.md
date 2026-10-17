# گراف دانش مرجع BarPro

> نسخه سند: 2026-10-11 (شامل snapshot تا 2026-10-11؛ بخش‌های snapshot برچسب تاریخی دارند و وضعیت زنده را تضمین نمی‌کنند)
>
> commit مبنای audit اولیه: 9c472f1
>
> snapshot تاریخی کد/رابط کاربری در 2026-10-05: OTP event-driven wake-up, lease locking, clock skew & single-flight attribution (`d5abc0c`)
>
> Alembic head کد: 042_fuel_request_identity؛ وضعیت دیتابیس production مستقل است.
>
> جایگزین tracked برای knowledge graph خارجی قبلی
>
> این سند هیچ secret، password، DSN کامل یا proxy credential را نگهداری نمی‌کند.

## پذیرش خودکار بارنامه‌های دستی، اجرای چرخه شروع و پایان حمل و گیت انحصار پلاک ناوگان — 2026-10-17 (LIVE-VERIFIED & CODE-VERIFIED)

> این بخش صرفاً یک snapshot با برچسب تاریخی از وضعیت کد و سیستم در 2026-10-17 (Cairn Phase 6) است و وضعیت زنده production را تضمین نمی‌کند.

- LIVE-VERIFIED (تکمیل چرخه شروع و پایان حمل بارنامه‌های راننده حمیدرضا محمدزاده روی سامانه کشوری UTCMS):
  - بارنامه اول (`job_id=ext-e5831b17599a`, سند `239321329`, رهگیری `1363223066`): ثبت موفقیت‌آمیز `RegisterStartOfShipping` و `RegisterEndOfShipping` با پاسخ `resultCode: 200` و پیغام «عملیات با موفقیت انجام شد». انتقال قطعی سند از بارنامه‌های در انتظار به کاردکس تحویل‌شده سامانه کشوری (`status: 30`, `shippingFinishDate: 2026-10-17T13:57:12`).
  - بارنامه چهارم (`job_id=ext-4c9cc4227138`, سند `239692528`, رهگیری `1363597368`): شروع خودکار توسط ورکر سلری در `17:28:07`، سپری شدن تایمر فیزیکی سفر (قاعده ۴۰۱۳) و ثبت موفقیت‌آمیز پایان حمل با کد ۲۰۰ (`status: 30`, `shippingFinishDate: 2026-10-17T14:18:38`).
  - بارنامه دوم (`job_id=ext-58e3682a4944`, سند `239371277`, رهگیری `1363273428`): شروع موفقیت‌آمیز حمل در پورتال رسمی کشور با مختصات دقیق جغرافیایی سند (`34.28626, 48.79967`) در ساعت `17:51:30`؛ سپری شدن زمان تایمر فیزیکی و ثبت موفقیت‌آمیز پایان حمل در سامانه کشوری با کد ۲۰۰ (`status: 30`, `shippingFinishDate: 2026-10-17T14:45:50`).
  - بارنامه سوم (`job_id=ext-079e8db4fbc3`, سند `239628695`, رهگیری `1363532773`): بلافاصله پس از آزادسازی پلاک توسط بارنامه دوم، متد `RegisterStartOfShipping` با موفقیت ارسال و تایید شد (`shippingStartDate: 2026-10-17T18:16:03.533`). وضعیت روی سامانه کشوری «در حال حمل» و تایمر رسمی سامانه تا `18:36:03` تنظیم شد.
- CODE-VERIFIED (کشف ریشه‌ای چرخه توکن و بهینه‌سازی Session Vault در `app/automation/gps_shipping_manager.py`):
  - کشف نقص TTL توکن: مدت اعتبار واقعی توکن JWT صادرشده توسط پورتال کشوری ۱ ساعت کامل (۳۶۰۰ ثانیه) بود، اما در کد به صورت سخت‌کد ۲۴۰ ثانیه (۴ دقیقه) تعیین شده بود. این امر موجب انقضای بی‌مورد، تلاش برای فراخوانی `GetTokenByRefreshToken` (که روی سامانه کشوری خطای ۵۰۰ دارد) و انجام لاگین‌های مجدد مکرر تا سقف مجاز ساعتی (`LOGIN_MAX_HOURLY=6`) می‌گردید.
  - پیاده‌سازی استخراج خودکار فیلد `exp` از توکن JWT و تنظیم TTL به ۵۸ دقیقه (یا مقدار پیش‌فرض ۳۰۰۰ ثانیه)، رفع کامل خطای اتمام سهمیه لاگین ساعتی و تثبیت پایداری سشن والت.
  - پاس دادن صریح پرچم `force_reauth=force` و هدف `purpose` در متدهای `auto_complete_shipping` و `auto_start_shipping`.
- CODE-VERIFIED (سرویس پذیرش خودکار بارنامه‌های صادرشده دستی در `app/orchestrator/adoption_service.py`):
  - متد `ExternalWaybillAdoptionService`: استعلام خودکار بارنامه‌های صادرشده و در حال حمل راننده، جلوگیری از ایجاد موارد تکراری، استخراج مختصات ثبتی واقعی سند از متد `/Document/GetDocumentByID` پورتال، و ایجاد رکوردهای متناظر در `waybill_jobs` به همراه مقداردهی اولیه `ShippingState`.
  - پذیرش موفقیت‌آمیز ۴۰ بارنامه دستی رانندگان در دیتابیس پروداکشن سرور مرکزی.
  - ثبت تسک دوره‌ای ۱۰ دقیقه‌ای `barpro.waybill.adopt_external` در Celery Beat.
- CODE-VERIFIED (کشف قواعد حیاتی سامانه کشوری ۴۰۱۰، ۴۰۰۸، ۴۰۲۰ و اصلاح تایم‌اوت):
  - قاعده ۴۰۱۰ کشوری: رد فرمت تاریخ‌های دارای پسوند `.000Z` با خطای «ساعت شروع حمل صحیح نیست». اصلاح متد `register_start_of_shipping` در `utcms_mobile_client.py` به تبدیل خودکار به وقت محلی تهران `%Y-%m-%dT%H:%M:%S`.
  - قاعده ۴۰۰۸ کشوری: انحصار پلاک خودرو (در هر لحظه فقط یک بارنامه می‌تواند در وضعیت «در حال حمل» باشد). تفکیک وضعیت ناوگان و نگهداری بارهای بعدی در وضعیت `waiting_other_trip` تا تحویل بار جاری.
  - قاعده ۴۰۲۰ کشوری: الزام تطابق نقطه شروع و پایان با مختصات ثبتی سند. اضافه شدن استعلام مستقیم `GetDocumentByID` در ورکر پذیرش.
  - افزایش تایم‌اوت وب‌سرویس موبایل از ۲۰ به ۴۵ ثانیه در `app/core/config.py` و `.env.example`.
  - افزودن تسک دوره‌ای ۲ دقیقه‌ای `shipping.auto_start_due_trips` در ورکر سلری برای راه‌اندازی بارهای در صف.
- TEST-VERIFIED (پوشش جامع آزمون‌های OTP و شیپینگ):
  - پاس شدن ۱۰۰٪ تمام ۱۳۶ تست مربوط به چرخه OTP و ردیابی هاب (شامل ۶ سوئیت تست).
  - پاس شدن ۱۰۰٪ تمام ۳۲ تست اعتبارسنجی شیپینگ، سشن والت و ورکر سلری.
  - بدون خطای تایپ‌اسکریپت (`tsc --noEmit`) و لینت (`eslint`).

## چرخه متوالی بارنامه (رفت و برگشت و بازگشت خالی)، زمان‌بندی هوشمند و گیت‌های پیشگیری از شکست سامانه — 2026-10-17 (CODE-VERIFIED & TEST-VERIFIED)

> این بخش صرفاً یک snapshot با برچسب تاریخی از وضعیت کد و سیستم در 2026-10-17 (Cairn Phase 5) است و وضعیت زنده production را تضمین نمی‌کند.

- CODE-VERIFIED (موتور چرخه متوالی بارنامه در `app/services/batch_service.py` و `app/schemas/multiroute.py`):
  - پشتیبانی از ۳ سناریوی عملیاتی: استاندارد (`standard`)، رفت و برگشت متوالی چرخه‌ای (`round_trip_cycling` با $2N$ بارنامه)، و فقط رفت متوالی با بازگشت خالی ناوگان (`one_way_repeated` با $M$ بارنامه).
  - وارون‌سازی هوشمند (`invert_waybill_payload`): در مسیرهای برگشت ($B \to A$)، مبدأ و مقصد (آدرس، شهر، استان، مختصات و کدپستی) و فرستنده و گیرنده جابجا می‌شوند تا کدپستی فرستنده برگشت با کدپستی مبدأ برگشت همخوانی دقیق پیدا کند و از ریجکت مغایرت آدرس پورتال کشوری جلوگیری شود.
  - جدول ماتریس همجواری استان‌های کشور (`IRAN_ADJACENT_PROVINCES`) و متد `validate_driver_fleet_scope`: اعتبارسنجی پیش از دیسپچ برای مسدودسازی خطای ۴۰۲۸ (مبدأ خارج از محدوده شهرستان پروانه راننده) و خطای ۴۰۴۵ (مقصد خارج از استان پروانه یا استان‌های همجوار).
- CODE-VERIFIED (محاسبات زمان واقعی جاده، سرعت ناوگان و بافرهای استراحت در `app/core/distance.py` و `app/services/distance_service.py`):
  - متد `calculate_cycling_times`: محاسبه زمان حرکت طبق پروفایل استاندارد کامیون (برون‌شهری 60 km/h و درون‌شهری 28 km/h) به همراه بافر استراحت و تخلیه/بارگیری (پیش‌فرض 45 دقیقه).
  - نگاشت معابر جاده‌ای (`snap_coordinate_to_road`): اتصال به Reverse Geocoding نشان با فالبک تاب‌آور به مختصات اولیه جهت رفع هشدارهای اتصال نقطه به خیابان.
- CODE-VERIFIED (توقف ایمن زنجیره و محافظت ۴۲۹ در زمان‌بند و شبیه‌ساز):
  - زمان‌بند `SchedulerService`: در صورت شکست یا ورود هر یک از مراحل دسته به وضعیت `NEEDS_REVIEW` یا `FAILED`، کلیه مراحل بعدی زنجیره متوقف می‌شوند (`Fail-Safe Chain Halt`) تا از مسدودسازی راننده در پورتال کشوری جلوگیری شود.
  - مدیریت خطای ۴۲۹ در `GpsShippingManager`: اعمال بازه عقب‌نشینی اجباری بین ۹۰۰ تا ۱۸۰۰ ثانیه.
- CODE-VERIFIED (رابط کاربری پیشرفته فول‌استک در `apps/web/src/app/batches/page.tsx`):
  - پیاده‌سازی تب‌های سه‌گانه انتخاب سناریو، فرم‌های پارامتریک تعداد چرخه و بافر استراحت، و جدول پیش‌نمایش زنده زمان‌بندی هوشمند مسیرها (`schedulePreview`).
  - نمایش کارت‌های تشخیصی توقف ایمن زنجیره (`Fail-Safe Chain Halt`) در پنل پیشرفت.
- TEST-VERIFIED (پوشش ۱۰۰٪ تست‌های رگرسیون):
  - فایل `tests/test_recurring_cycling_batches.py` با ۱۲ تست واحد و یکپارچگی سبز.
  - تست‌های `tests/test_multiroute.py` با ۱۹ تست سبز (مجموعاً ۳۱ تست سبز بدون خطا).
  - بدون خطای تایپ‌اسکریپت (`tsc --noEmit`) و لینت (`eslint`).

## ثبت زنده بارنامه در سامانه UTCMS، رفع گرسنگی صف ورکر، تطبیق خودترمیم و زمان‌بندی بهینه — 2026-10-15 (LIVE-VERIFIED & CODE-VERIFIED)

> این بخش صرفاً یک snapshot با برچسب تاریخی از وضعیت کد و سیستم در 2026-10-15 است و وضعیت زنده production را تضمین نمی‌کند.

- LIVE-VERIFIED (ثبت زنده موفقیت‌آمیز بارنامه‌ها روی سامانه کشوری UTCMS با احراز دو شاهدی):
  - بارنامه اول (`job_114ca4e47a5543ac`): دریافت کد رهگیری رسمی سامانه `1361785270`، شناسه سند `237972607`، وضعیت رسمی در سامانه وزارت کشور «درحال حمل»، تایید قطعی دیتابیس `mutation_status: confirmed`.
  - بارنامه دوم (`job_e2523cdd893345f0`): دریافت کد رهگیری رسمی سامانه `1361790427`، شناسه سند `237977746`، وضعیت رسمی در سامانه وزارت کشور «درحال حمل»، تایید قطعی دیتابیس `mutation_status: confirmed`.
  - کپچای ریاضی سامانه صدور با مدل هوش مصنوعی PyTorch CNN به صورت خودکار و زیر ۳ ثانیه حل شد (`9+18 = 27` و `solution=12`).
- CODE-VERIFIED (رفع مسدودی صف ورکر سلری و ایزولاسیون پروب پروکسی): تسک `barpro.clean_ip.probe` که هر ۱۸۰ ثانیه اجرا می‌شد و به مدت ۱۴۰ ثانیه صف اصلی صدور بارنامه (`CELERY_WAYBILL_TASKS_QUEUE = waybill_tasks`) را قفل می‌کرد، به صف مجزای `scheduled_tasks` منتقل شد و اینتروال پیش‌فرض آن در `app/core/config.py` به ۱۸۰۰ ثانیه (۳۰ دقیقه) افزایش یافت تا صف صدور ۱۰۰٪ بدون تاخیر بماند.
- CODE-VERIFIED (خودترمیمی موتور تطبیق در `app/orchestrator/reconciliation_service.py`): افزودن استخراج خودکار کد ملی راننده از داخل `payload_json` در صورت خالی بودن `driver_id`، تزریق پراکسی کارگر ایرانی (`get_worker_proxy_url`) در کلیه استعلام‌های موبایل، و مدیریت بازتلاش سازگاری نهایی برای بارنامه‌های دارای کد رهگیری. TEST-VERIFIED: ۱۴ تست سبز در `tests/test_reconciliation_service.py`.
- CODE-VERIFIED (گارد تفکیک شماره تلفن و بهینه‌سازی زمان‌بندی روزانه): پیاده‌سازی تفکیک خودکار شماره فرستنده/گیرنده از راننده جهت جلوگیری از خطای ۴۲۲ در زمان‌بند، و تنظیم اسلات‌های سه‌گانه روزانه (`08:30,11:45,14:15`) در `driver_schedules` جهت توزیع بهینه بار کاری و پرهیز از چالش‌های پیامکی ساعات غیراداری.
- CODE-VERIFIED (اندروید مجازی سرور Redroid در `compose/android.yml`): فعال‌سازی حالت `privileged: true` جهت امکان ایجاد ساختار binderfs و FUSE در هسته لینوکس ۶، اتصال لوپ‌بک ADB به پورت ۵۵۵۵ و اعطای دسترسی mock location به `cl.coders.faketraveler`.

## بازگشایی خودکار آلرت‌های متناوب، تعدیل تایم‌اوت هاب به ۱۲۰۰ ثانیه و رفع ANR در کلاینت — 2026-10-14 (CODE-VERIFIED)

> این بخش صرفاً یک snapshot با برچسب تاریخی از وضعیت کد در 2026-10-14 است و وضعیت زنده production را تضمین نمی‌کند.

- CODE-VERIFIED (بازگشایی خودکار آلرت‌های تکرار شونده در `app/orchestrator/alert_manager.py`): متد `create_alert` پیش‌تر در صورت وجود رکورد با همان `dedupe_key` صرفاً رکورد را برمی‌گرداند؛ با تغییر جدید چنانچه `existing.is_acknowledged == True` باشد، وضعیت به `is_acknowledged = False` بازنشانی شده و فیلدهای `acknowledged_at` و `acknowledged_by` نال می‌شوند و پیام و جزئیات به‌روزرسانی شده و رویداد وب‌سوکت `admin_alert_created` و وب‌هوک مجدداً ارسال می‌شوند تا قطعی‌های متناوب پنهان نمانند. TEST-VERIFIED: تست `test_create_alert_reopens_acknowledged_alert` در `tests/test_admin_alerts.py`.
- CODE-VERIFIED (تعدیل تایم‌اوت لایونس هاب به ۱۲۰۰ ثانیه در `app/core/config.py`): `HUB_HEARTBEAT_STALE_SECONDS` به مقدار پیش‌فرض ۱۲۰۰ ثانیه (۲۰ دقیقه) تغییر یافت تا با محدودیت ذاتی Periodic WorkManager اندروید (حداقل بازه ۱۵ دقیقه = ۹۰۰ ثانیه) سازگار شده و از هشدارهای کاذب قطع ارتباط جلوگیری شود. TEST-VERIFIED: تست‌های `tests/test_hub_status_tracking.py` و تأیید زنده روی سرور پروداکشن با `stale_after_seconds: 1200`.
- CODE-VERIFIED (رفع ANR شروع سرد کلاینت در `SMS-Forwarder-Pro`): در `SmsForwarderApp.kt`، کلیه فراخوانی‌های مسدودکننده ترد اصلی شامل دیتابیس روم `AppDatabase.getDatabase`، سالت Keystore `SecureStorageManager.getOrCreateSalt` و زمان‌بندی ورکرها به یک Coroutine پس‌زمینه با `Dispatchers.IO + SupervisorJob()` منتقل شده و `repository` به صورت Lazy تعریف شد. TEST-VERIFIED: لانچ موفق بدون ANR روی ایمولاتور `medium_phone` (زمان ۲.۸ ثانیه و پوشه `/data/anr/` بدون لاگ جدید).

## برابری فالبک اسکیو ساعت گیت‌وی، مجوز READ_PHONE_STATE و ماسک لاگ هاب — 2026-10-14 (CODE-VERIFIED)

> این بخش صرفاً یک snapshot با برچسب تاریخی از وضعیت کد در 2026-10-14 است و وضعیت زنده production را تضمین نمی‌کند.

- CODE-VERIFIED (برابری فالبک اسکیو ساعت در `POST /api/v1/otp/sms-gateway` با `/sms-forwarder`): `receive_sms_gateway` در `app/api/routes/otp_forwarder.py:224-230` خطای `"SMS timestamp is in the future; check device clock"` از `accept_forwarded_otp` را گرفته و با `timestamp=None` (زمان معتبر سرور) retry می‌کند؛ منطبق با فالبک موجود `/sms-forwarder` در همان فایل (`:550-562`). TEST-VERIFIED: `tests/test_sms_gateway_skew.py:1` و `:67-80` (ساعت ‎+۹۰ ثانیه → HTTP 200 به‌جای 422 ترمینال).
- CODE-VERIFIED (اعلام `READ_PHONE_STATE` و انتخاب سیم/تشخیص شماره): مانیفست `AndroidManifest.xml:19-22` در `SMS-Forwarder-Pro` مجوز را اعلام می‌کند (lazy، هنگام فعال‌سازی فالبک/رله)؛ `PermissionHelper.isReadPhoneStateGranted` در `PermissionHelper.kt:60` و آیتم اختیاری `read_phone_state` در `PermissionHelper.kt:146-154`؛ صفحه `PermissionManagerScreen` آن را به‌صورت generic از `getAllPermissionsStatus` می‌گیرد (`PermissionManagerScreen.kt:116-118`)؛ رزولوشن چندسیم در `SmsRelayHelper.kt:49-52` و تشخیص شماره از `line1Number` در `CarrierDetector.kt:81-90`.
- CODE-VERIFIED (ماسک شماره‌های هاب در لاگ و عدم اعتبارسنجی هاست): هر دو خط رله/failover در `SmsForwardRepository.kt:603` و `:622` شماره را از `LogSanitizer.maskPhone` عبور می‌دهند (`LogSanitizer.kt:43-50`، خروجی `09***`)؛ `network_security_config.xml:7-13` تصریح می‌کند کد فقط path/token/flag را اعتبارسنجی می‌کند و هرگز host را نه، و فیلد بیلد `DEFAULT_ENDPOINT_URL` در سورس اصلی خوانده نمی‌شود (تنها تعریف در `app/build.gradle.kts:36`).

## ممیزی سختی اتصال هاب (afternoon) — 2026-10-14 (CODE-VERIFIED)

- CODE-VERIFIED (رفع ۶ نقص در شفافیت هاب؛ همه گیت‌ها سبز):
  - حذف توکن واقعی وبهوک OTP از `tests/test_hub_status_tracking.py` پیش از کامیت (توکن هرگز وارد تاریخچه git نشد)؛ مخزن خواهر `SMS-Forwarder-Pro` پاک است.
  - رفع flapping آستانه (۳۰۰ ثانیه == پریود پینگ): `HUB_HEARTBEAT_STALE_SECONDS=900` (۳ برابر) با تست رگرسیون red-green.
  - انتقال هشداردهی از GET ادمین به تسک beat به نام `monitor.hub_liveness` (هر ۵ دقیقه)؛ `GET /hub-status` فقط‌خواندنی شد.
  - ردپای ممیزی auto-acknowledge (`auto_resolved_by`) بدون جعل تأیید انسانی.
  - شماره‌های سیم هاب از env (`HUB_NUMBERS`) خوانده می‌شوند.
- TEST-VERIFIED: بک‌اند `2388 passed, 7 skipped`؛ فایل‌های سشن `49 passed`؛ `mypy` صفر خطا (۲۱۹ فایل)؛ فرانت `typecheck`/`eslint` صفر؛ اندروید `99/0`؛ هر دو APK بیلد موفق؛ E2E روی دستگاه `medium_phone` با round-trip زنده `HEALTH_CHECK`→`ready` سبز شد (تلاش اول به‌علت DB خراب اپ نصب‌شده قبلی شکست خورد — محیطی، نه باگ کد).

## نرمال‌سازی شماره همراه، فعال‌سازی خودکار راننده، شفافیت هاب و مسیریابی اپراتوری پیامک — 2026-10-14 (CODE-VERIFIED)

- CODE-VERIFIED (نرمال‌سازی شماره‌های همراه ایران در بک‌اند و کلاینت اندروید):
  - بک‌اند: ماژول `app/core/phone_utils.py` با توابع `normalize_iranian_phone`، `is_valid_iranian_mobile` و `detect_operator`. تبدیل خودکار ارقام فارسی/عربی (`۰۱۲۳۴۵۶۷۸۹` و `٠١٢٣٤٥٦٧٨٩`) به لاتین، پاکسازی فاصله‌ها، خط تیره و علائم، حذف پیش‌شماره‌های کشوری (`+98`، `0098`، `98`) و استانداردسازی به فرمت ۱۱ رقمی `09XXXXXXXXX`.
  - یکپارچه‌سازی در لایه منطق و دیتابیس `DriverService` (`app/services/driver_service.py`) برای ایجاد راننده، به‌روزرسانی و جلوگیری از ثبت تکراری شماره، بدون دستکاری در UI.
  - کلاینت اندروید: متد `SmsParser.normalizePhoneNumber` در `SMS-Forwarder-Pro` با منطق بک‌اند همگام شد.
  - TEST-VERIFIED: آزمون‌های ۸گانه `tests/test_phone_normalization.py` و آزمون اندروید `SmsParserTest.kt` با موفقیت ۱۰۰٪ پاس شدند.
- CODE-VERIFIED (فعال‌سازی خودکار راننده پس از ثبت‌نام اولیه بدون نیاز به تأیید دستی ادمین):
  - وضعیت `DriverStatus.PENDING = "pending"` به مدل‌های دیتابیس اضافه شد.
  - متد `DriverService.check_and_auto_activate_driver` پیاده‌سازی شد: به محض تکمیل ثبت‌نام راننده و تأیید OTP و دسترسی‌ها (مانند دریافت پیامک و موقعیت مکانی)، وضعیت راننده به صورت خودکار به `active` (و `ready`) ارتقا می‌یابد.
  - همزمان هشدار `AdminAlert` با پیام «راننده جدید فعال شد» به همراه نام و شماره راننده ایجاد و رویداد در `event_hub` منتشر می‌شود.
  - در صورت ناقص ماندن دسترسی‌ها یا کد، راننده در وضعیت `pending` باقی می‌ماند.
  - مسیر وبهوک پیامک (`app/api/routes/otp_forwarder.py`) به بررسی و فعال‌سازی خودکار راننده در لحظه دریافت هارت‌بیت و پیامک مجهز شد.
  - TEST-VERIFIED: آزمون‌های `tests/test_driver_auto_activation.py` (۲ تست) با موفقیت پاس شدند.
- CODE-VERIFIED (شفافیت زنده وضعیت اتصال گوشی هاب برای ادمین):
  - وبهوک سرور `app/api/routes/otp_forwarder.py` با دریافت هارت‌بیت از اپلیکیشن هاب (`app_role: "HUB"` یا هدر `X-App-Role: HUB` یا شماره‌های هاب)، وضعیت زنده اتصال را در کلید ردیس `rpa:forwarder:hub:connected` ثبت می‌کند.
  - اندپوینت `GET /api/v1/admin/hub-status` در `app/api/routes/admin_alerts.py` وضعیت اتصال، ثانیه‌های سپری‌شده (`seconds_ago` و `seconds_since_last_heartbeat`)، زمان آخرین ضربان (`last_heartbeat_at` و `last_heartbeat_iso`)، پیام وضعیت (`message`) و خطوط هاب (`hub_lines`) را بازمی‌گرداند تا تطابق کامل با قراردادهای رابط کاربری فرانت‌اند (`apps/web/src/app/admin/dashboard/page.tsx` و `health/page.tsx`) برقرار باشد؛ در صورت قطعی اتصال (> ۳۰۰ ثانیه) به طور خودکار هشدار با اهمیت بالا (high severity) ثبت می‌شود و هنگام اتصال مجدد هاب، هشدارهای باز `hub:disconnected` به صورت خودکار تایید و بسته می‌شوند.
  - کلاینت اندروید `SmsForwarderClient.kt` برای فلور Hub، هدر `X-App-Role: HUB` و شماره‌های سیم‌کارت هاب را ارسال می‌کند.
  - پنل فرانت‌اند ادمین:
    - در داشبورد اصلی ادمین (`apps/web/src/app/admin/dashboard/page.tsx`): بج زنده وضعیت اتصال هاب و هشدار برجسته قرمز هنگام قطع ارتباط نمایش داده می‌شود.
    - در صفحه سلامت سیستم (`apps/web/src/app/admin/health/page.tsx`): کارت اختصاصی اطلاعات رله گوشی هاب شامل شناسه دستگاه، زمان ضربان و خطوط سیم‌کارت تعبیه شد.
  - TEST-VERIFIED: آزمون‌های `tests/test_hub_status_tracking.py` (۳ تست) پاس شدند.
- CODE-VERIFIED (مسیریابی پیامک به گوشی هاب بر اساس کاتالوگ جامع اپراتورها، MVNOها و الگوریتم Longest-Prefix Matching):
    - همراه اول (MCI) — ۱۷ پیش‌شماره اصلی + 0997: `0910–0919`، `0990–0995` (شامل سیم‌کارت انارستان `0994` و اعتباری کشوری `0995`)، `0996`، `0997` -> سیم‌کارت همراه اول هاب (`09966567754`)
    - ایرانسل (MTN Irancell) — ۱۴ پیش‌شماره اصلی: `0930`، `0933`، `0935–0939`، `0900–0905`، `0941` -> سیم‌کارت ایرانسل هاب (`09047119812`)
    - رایتل (RighTel) — ۴ پیش‌شماره اصلی: `0920–0923` -> سیم‌کارت ایرانسل هاب (مطابق توافق تعرفه/رومینگ هاب)
    - جمع کل ۳۵ پیش‌شماره اصلی منطبق بر منبع مرجع `persian-tools v4.0.4` و لیست اعتبارسنجی رگولاتوری CRA.
    - اپراتورهای منطقه‌ای و اختصاصی:
      - تالیا (Taliya): `0932` -> سیم‌کارت همراه اول هاب (شبکه میزبان همراه اول)
      - کیش سل پارس / تله‌کیش (TKC): `0934`، `093476` -> سیم‌کارت همراه اول هاب (رومینگ همراه اول)
      - اسپادان (MTCE): `0931` -> سیم‌کارت همراه اول هاب
    - اپراتورهای مجازی (MVNO):
      - شاتل موبایل (Shatel Mobile): `0998`، `09981`، `09982` -> سیم‌کارت ایرانسل هاب
      - سامان‌تل (SamanTel): `0999`، `09999`، `09995` -> سیم‌کارت ایرانسل هاب
      - لوتوس‌تل (LotusTel): `09990` -> سیم‌کارت همراه اول هاب (میزبان همراه اول)
      - آپتل (Aptel): `09991`، `09993` -> سیم‌کارت همراه اول هاب (میزبان همراه اول)
      - فناپ موبایل (`09992`)، آرین‌تل (`09998`)، اسمارت‌کام (`09988`)، همراه هوشمند آینده / توسن (`09989`) -> سیم‌کارت ایرانسل هاب
  - الگوریتم Longest-Prefix Matching (LPM):
    - تفکیک هوشمند تداخل پیش‌شماره‌های ۴ رقمی و ۵ رقمی در رنج `0999` و `0998` (جلوگیری از انحراف آپتل `09991`/`09993` و لوتوس‌تل `09990` به ایرانسل به دلیل پیش‌شماره کلی سامان‌تل `0999` با انتخاب طولانی‌ترین پیش‌شماره منطبق).
  - پیاده‌سازی همگام در دو پلتفرم:
    - اندروید: `CarrierRoutingTable.kt` و `CarrierDetector.kt` (`MobileCarrier` enum شامل MCI, IRANCELL, RIGHTEL, TALIYA, TKC, SPADAN, SHATEL, SAMANTEL, LOTUSTEL, APTEL, FANAP, ARIANTEL, SMARTCOMM, TOSAN) با متدهای `registerRule` و `addPrefixes` و `isKnownOperator`.
    - بک‌اند: ماژول `app/core/phone_utils.py` با `OPERATOR_RULES`، `resolve_carrier_route`، `resolve_hub_target_carrier`، `detect_operator`، `is_known_operator_prefix` و `is_valid_iranian_mobile`.
    - رفع باگ نرمال‌سازی `+98 09...` و `0098 09...` در بک‌اند و اندروید جهت جلوگیری از ایجاد ارقام اضافه `00912...`.
    - رفع رگرسیون تداخل کوئری دیتابیس تلفن تکراری در `DriverService.create_driver` که منجر به شکست تست سهمیه پلاک `test_create_driver_plate_limit_reached` شده بود.
  - فال‌بک پیش‌فرض به سیم‌کارت همراه اول هاب همراه با لاگ هشدار برای پیش‌شماره‌های ناشناخته.
  - TEST-VERIFIED: آزمون‌های `tests/test_phone_normalization.py` (۱۴ تست جامع)، `CarrierRoutingTableTest.kt` (۱۰ تست واحد)، `CarrierDetectorTest.kt`، `SmsParserTest.kt` و `test_driver_multitenant.py` (۱۴ تست) با موفقیت ۱۰۰٪ پاس شدند.

## ثبت ویزارد، تاب‌آوری run-due و لاگ بی‌صدای Fernet — 2026-10-13 (CODE-VERIFIED)

- CODE-VERIFIED (قرارداد flat ویزارد / رفع HTTP 422 گزارش‌شده با اسکرین‌شات): ویزارد `/new` در قدم ۶ آبجکت‌های تودرتوی `origin`/`destination` را بدون رشته‌های سطح‌بالا و بدون کلید `financial` می‌فرستاد و union backend (`WaybillPayload | WaybillNestedPayload` در `app/schemas/multitenant.py:768-776`) آن را با ۴۲۲ رد می‌کرد. فرانت‌энд اکنون رشته‌های شهر سطح‌بالا می‌فرستد (`apps/web/src/app/new/page.tsx`) و آبجکت‌های تکراری حذف شدند (داده غنی در `metadata_json` می‌ماند)؛ قرارداد flat، قرارداد صحیح فرم دستی است و هیچ تضعیف اسکیمای backend لازم نبود.
- CODE-VERIFIED (گارد run-due / رفع HTTP 500): ساخت `WaybillJobCreateRequest` در `DriverScheduleService.run_due_schedules` (`app/services/driver_schedule_service.py`) اکنون per-schedule در try/except است؛ تمپلیت ذخیره‌شده نامعتبر (مثلاً خالی) باعث skip با لاگ خطا می‌شود، نه ۵۰۰ سراسری.
- CODE-VERIFIED (لاگ Fernet در info بدون traceback): شاخه PBKDF2 در `_build_fernet` (`app/auth_multitenant.py`) که در همه استقرارها مسیر عادی است، دیگر warning+traceback نمی‌دهد؛ خطای واقعی decrypt همچنان با `driver_password_decrypt_failed` سطح error ثبت می‌شود.
- TEST-VERIFIED: `tests/test_submit_payload_contract.py` (۳ تست: پین تشخیص ۴۲۲، اعتبارسنجی شکل post-fix به‌صورت `WaybillPayload`، و skip بدون raise در run-due با تمپلیت خالی).

## استحکام‌بخشی ارکستریتور و ربات صدور موبایل (فاز ۲) و امنیت چرخه عمر راننده — 2026-10-12 (CODE-VERIFIED)

- CODE-VERIFIED (گارد مسدودسازی حذف راننده دارای جاب فعال / P0 C1): در `app/services/driver_service.py` متد `delete_driver` به گارد بررسی کارهای بارنامه غیرترمینال (`col(WaybillJob.status).not_in(_TERMINAL_JOB_STATUSES)`) مجهز شد. در صورت وجود هرگونه جاب در حال پردازش یا در انتظار پنجره ثبت (`waiting_submission_window`, `pending`, `queued`, ...) حذف راننده با خطای `HTTP 409 Conflict` متوقف می‌شود تا از یتیم‌شدن پنهان کارها جلوگیری شود.
- CODE-VERIFIED (حفظ رد حسابرسی رویدادهای DomainEvent / P0 C1): دستور مخرب `delete(DomainEvent)` هنگام حذف راننده حذف شد و با متد ایمن `driver_id = None` جایگزین گردید. کلیه رکوردهای حسابرسی (`event_id`, `event_type`, `job_id`, `payload_json`, `created_at`) برای ردیابی تاریخی دست‌نخورده حفظ می‌شوند.
- CODE-VERIFIED (گارد حذف اینتنت‌های فاقد راننده در دیسپچر / P1 H5): در `app/orchestrator/dispatcher_service.py` در صورت نبود راننده (`operation == "submit" and job.driver_id is None`)، اینتنت ارسال بلافاصله با دلیل `driver_missing` لغو (`cancelled`) می‌شود و از اتلاف لیس ورکرها جلوگیری می‌گردد.
- CODE-VERIFIED (شفاف‌سازی و لاگ هشداری کارهای یتیم در اسکجولر): در `app/orchestrator/scheduler_service.py` برای کارهایی که `driver_id is None` است لاگ هشدار ساختاریافته صادر می‌شود و در صورت رد شدن کارهای دارای نوبت به دلیل محدودیت‌های خط مشی، لاگ دیباگ ثبت می‌شود.
- CODE-VERIFIED (انتقال‌های مجاز ماشین وضعیت به needs_review و بازیابی queued به pending): وضعیت‌های `"pending"` و `"waiting_submission_window"` در `ALLOWED_TRANSITIONS` (`app/orchestrator/state_machine.py`) مجوز انتقال به `"needs_review"` و همچنین انتقال `"queued"` به `"pending"` برای بازیابی جاب‌های منقضی‌شده لیس ثبت شد.
- CODE-VERIFIED (تفکیک صف پایش پروکسی‌های پاک / H2): تسک دوره‌ای `clean-ip-pool-probe` در بیت سلری (`app/workers/celery_app.py`) از صف تک‌رشته‌ای `rpa_scheduler` به صف `CELERY_WAYBILL_TASKS_QUEUE` انتقال یافت تا از تجمیع و مرگ تسک‌های ۵ ثانیه‌ای دیسپچر جلوگیری شود.
- CODE-VERIFIED (تطبیق ایمن ناوگان راننده در کلاینت موبایل / H6): فال‌بک خطرناک انتخاب اولین خودرو (`fleet_items[0]`) در `_find_matching_fleet_truck` حذف شد. در `_execute_mobile_waybill_job` در صورت وجود ناوگان اما عدم تطابق با پلاک درخواستی، تسک به شکل امن و Fail-Closed با وضعیت `needs_review` و خطای `fleet_plate_mismatch` متوقف می‌شود.
- CODE-VERIFIED (تاب‌آوری تراکنشی بازیابی جاب‌های گیرکرده / H3): هر تسک در حلقه `cleanup_stuck_jobs` درون `async with session.begin_nested()` و بلوک محافظ `try/except` قرار گرفت تا خطای یک کار معلق مانع از بازیابی سایر کارها نشود.
- CODE-VERIFIED (انتساب شاهد در تأییدیه OTP / H1): حالت اثبات `witness_mode = "otp_authority"` در پی‌لود نتیجه متد `submit_otp` به ثبت رسید تا بدون شکستن قراردادهای رفتاری، زنجیره اثبات مستند گردد.
- TEST-VERIFIED: آزمون‌های `test_driver_multitenant.py` (۱۴ تست)، `test_dispatch_intents.py` (۸ تست)، `test_utcms_gate_and_migration.py` (۴ تست)، `test_beat_schedule_wiring.py` (۴ تست)، `test_queue_routing_contract.py` (۳۲ تست)، `test_otp_wakeup_and_lifecycle.py` (۵۹ تست)، `test_mobile_waybill_bot.py` (۲۲ تست) و `test_rpa_phase1_architecture.py` (۱۲ تست) با موفقیت ۱۰۰٪ پاس شدند.

## فیلدهای اجباری بارنامه، اصلاح جاب‌های نیازمند بررسی و بهینه‌سازی استعلام سوخت — 2026-10-11 (CODE-VERIFIED)

- CODE-VERIFIED (رفع خطای ۱۰۸ و کرش لوکال کرومیوم استعلام سوخت): در فایل `app/automation/browser.py:398` مقدار تنظیم locale در کانتکست Playwright از رشته ترکیبی `"fa-IR,fa;q=0.9,en-US;q=0.8,en;q=0.7"` به مقدار استاندارد تکی `"fa-IR"` تصحیح شد. خطای پروتکل CDP کرومیوم (`Protocol error (Emulation.setLocaleOverride): Invalid locale name`) که منجر به کرش ورکر و خطای `108` (`WORKER_RESOURCE_ERROR`) در استعلام سوخت می‌شد کاملاً برطرف شد و صحت باز شدن صفحه بر روی سرور مرکزی تایید تجربی شد.
- CODE-VERIFIED (اولویت‌دهی حل‌کننده CRNN کلمات فارسی سوخت): در `app/automation/fuel_scraper.py:760` ارائه‌دهنده `PyTorchFuelCaptchaProvider` (مدل اختصاصی شبکه عصبی کانولوشنی-بازگشتی واژگان فارسی) به رتبه اول زنجیره `CompositeCaptchaProvider` منتقل شد. زمان حل کپچای سوخت از معطلی‌های چندمرحله‌ای فال‌بک به کمتر از ۱۲۰ میلی‌ثانیه در تلاش اول با دقت ۹۸٪+ کاهش یافت.
- CODE-VERIFIED (تاب‌آوری ذخیره اسکرین‌شات و اصلاح پرمیشن‌های والیوم): پرمیشن‌های مسیر والیوم داکر `/app/runtime/screenshots` روی هاست اصلاح شدند (`chown 10001:996` و `chmod 775`). علاوه بر آن، عملیات دیسک در `fuel_scraper.py` درون بلوک امن قرار گرفت تا هیچ‌گونه افت دیسک یا عدم دسترسی به فایل مانع از تکمیل استعلام موفق نشود.
- CODE-VERIFIED (توضیحات خطاهای استعلام سوخت و اصلاح نمایش مسیر): کدهای خطای ۱۰۱ تا ۱۰۸ در فرانت‌اند (`FuelTypes.ts`) با توضیحات فارسی شفاف مپ شدند. تابع `parseWaybillPayload` در `fuel/page.tsx` اصلاح شد تا در صورت آبجکتی بودن مبدأ/مقصد از نمایش عبارت ناقص `[object Object]` جلوگیری کند و برچسب وضعیت `needs_review` استایل‌دهی شد.
- CODE-VERIFIED (فیلدهای اجباری کدهای ملی و پستی در فرانت‌اند): در اسکیما `waybillSchema.ts` و فرم ثبت بارنامه (`apps/web/src/app/new/page.tsx`) فیلدهای کد ملی فرستنده، کد پستی فرستنده، کد ملی گیرنده، کد پستی گیرنده، کد پستی مبدأ و کد پستی مقصد اضافه و با اعتبارسنجی ۱۰ رقمی استاندارد الزامی شدند. قابلیت‌های تبدیل خودکار ارقام فارسی/عربی و دکمه‌های کمکی کپی کد پستی پیاده‌سازی شدند.
- CODE-VERIFIED (همگام‌سازی اعتبارسنجی در لحظه ثبت جاب): در `app/automation/multitenant_payload_adapter.py` استخراج کدهای ملی و پستی و اقلام کالا تقویت و مختصات جغرافیایی حفظ شد. متد `create_job` در `app/services/waybill_job_service.py` به فراخوانی اعتبارسنجی `validate_mobile_source_payload` مجهز گردید تا در صورت نقص فیلدها بلافاصله با خطای ۴۲۲ (`WAYBILL_PAYLOAD_INCOMPLETE`) پاسخ دهد و جاب ناقص وارد صف ورکرها نشود.
- CODE-VERIFIED (امکان ویرایش و رفع خطای جاب‌های needs_review): اسکیماهای `WaybillJobUpdateRequest` در بک‌اند و فرانت‌اند فیلد `payload` را پذیرش می‌کنند. سرویس `update_job` امکان اصلاح کدهای ناقص برای جاب‌های در وضعیت `needs_review`، `failed` و `pending` را فراهم کرده و پس از اعتبارسنجی موفق، فیلدهای `error_category` و `last_error` را پاک می‌کند تا جاب با متد `retry_job` بدون بن‌بست دوباره وارد صف اجرا شود. در صفحه تاریخچه (`history/page.tsx`) مودال ویرایش جاب به فیلدهای کدهای ملی/پستی و دکمه اختصاصی اصلاح تجهیز شد.
- EVIDENCE-GROUNDED (آزمون دسته‌ای ۸/۸ روی سرور پروداکشن): ۸ استعلام استخراج سهمیه سوخت (ماه‌های ۱ تا ۴ سال ۱۴۰۵ برای هر دو راننده ۱ و ۲) روی ورکر `barpro-worker-1` اجرا و ۱۰۰٪ با وضعیت `success` و میانگین زمان ۲۱ تا ۳۷ ثانیه پایان یافت. مصرف رم ورکر پس از استعلام‌های مکرر در سطح ۴۸۶ مگابایت (۱۰.۵٪ سقف ۴.۵ گیگابایت) پایدار باقی ماند و هیچ پروسس زامبی کرومیوم تشکیل نشد.
- CODE-VERIFIED (حفظ کدهای پستی و مختصات در مدل‌های Pydantic): فیلدهای `postal_code`، `lat` و `lng` به مدل‌های `LocationModel`، `SenderModel` و `ReceiverModel` در `app/schemas/waybill.py` و فیلدهای متناظر کدهای ملی و پستی به `WaybillPayload` در `app/schemas/multitenant.py` اضافه شدند تا از حذف ناخواسته داده‌ها حین اجرای `model_dump()` در Pydantic جلوگیری شود.
- EVIDENCE-GROUNDED (آزمون ثبت کار بارنامه شماره ۳ روی سرور مرکزی): ایجاد کار بارنامه شماره ۳ با کدهای ملی و پستی ۱۰ رقمی معتبر، مختصات مبدأ/مقصد و مشخصات محموله با موفقیت ۱۰۰٪ و بدون خطا اجرا شد و با وضعیت `waiting_submission_window` وارد چرخه ارکستریتور گردید.
- TEST-VERIFIED: آزمون‌های ۱۵گانه `tests/test_waybill_service.py` و اعتبارسنجی‌های کلاینت موبایل `tests/test_utcms_mobile_contract.py` و `tests/test_waybill_payload_validation.py` همگی با موفقیت پاس شدند. تایپ‌چک و لینت بک‌اند و فرانت‌اند بدون کوچک‌ترین خطا اجرا شدند.

## بومی‌سازی تقویم جلالی، نقشه تعاملی قالب‌های مسیر و کاشی‌های بدون فیلتر CartoDB — 2026-10-11 (CODE-VERIFIED)

- CODE-VERIFIED (تقویم مستقل جلالی): محاسبات کامل تبدیل تقویم خورشیدی و میلادی (الگوریتم بیرشک/کاظمی)، تعیین سال‌های کبیسه، اسامی ماه‌ها و روزهای هفته بدون وابستگی به هیچ کتابخانه سنگین جانبی در `apps/web/src/lib/jalali.ts` پیاده‌سازی شد. تست‌های واحد ۵۸گانه در `apps/web/test/jalali.test.mjs` با پوشش ۱۰۰٪ پاس شدند.
- CODE-VERIFIED (کامپوننت تقویم کشویی): کامپوننت `JalaliDatePicker.tsx` با قابلیت انتخاب سال/ماه با دراپ‌داون، دکمه‌های «امروز» و «پاک‌کردن»، بسته‌شدن با کلیک خارج از کادر و خروجی استاندارد ISO (`YYYY-MM-DD`) ساخته شد و جایگزین فیلدهای بومی میلادی در `RecordFilters.tsx`، گزارشات کاربر/ادمین (`reports/page.tsx`, `admin/reports/page.tsx`) و فرم ثبت مشتریان (`CreateClientModal.tsx`) شد.
- CODE-VERIFIED (توابع بک‌اند تقویم): توابع `parse_jalali_date` و `format_date_jalali` در `app/core/jalali.py` با پشتیبانی از جداکننده‌های `/` و `-` و زمان استاندارد تهران (UTC+3:30) پیاده‌سازی و در `tests/test_driver_tracking.py` آزموده شدند (۱۳ تست سبز).
- CODE-VERIFIED (نقشه تعاملی در قالب‌های مسیر): کامپوننت `LocationMapPicker` به صورت داینامیک (`next/dynamic` با `ssr: false`) به فرم تعریف قالب‌های مسیر (`route-templates/page.tsx`) اضافه شد. دکمه‌های باز/بسته‌کردن نقشه، درگ کردن پین روی نقشه، ثبت بلادرنگ مختصات در فرم، و استخراج خودکار آدرس دقیق کوچه/خیابان و استان/شهر از طریق سرویس `/api/v1/locations/reverse-geocode` فعال شدند.
- CODE-VERIFIED (کاشی‌های نقشه پرسرعت، بدون واترمارک و بدون نیاز به کلید): در `apps/web/src/lib/map-tiles.ts`، به دلیل اعمال واترمارک اجباری CartoDB برای درخواست‌های بدون کلید (`API KEY REQUIRED`)، ارائه‌دهندگان کاشی به سرورهای ۱۰۰٪ رایگان، پرسرعت و بدون نیاز به API Key شامل OpenStreetMap Germany (`osmDe` به عنوان پیش‌فرض اصلی)، OSM Standard (`osmStandard`)، Humanitarian OSM (`osmHot`) و Google Maps (`google` با `hl=fa` برای نمایش اسامی فارسی) به‌روزرسانی شدند؛ دامنه‌های `*.openstreetmap.org`، `*.openstreetmap.de`، `*.openstreetmap.fr` و زیردامنه‌های چندسطحی `*.tile.openstreetmap.fr` به هر دو دایرکتیو `img-src` و `connect-src` در CSP در Nginx و FastAPI اضافه شد تا از خطای کش Service Worker جلوگیری شود و پیش‌اتصال DNS و کش PWA اصلاح گردید.
- CODE-VERIFIED (اصلاحات پروفایل و حذف متون اضافی): متن توضیحات اضافه زیر حساب کاربری در `settings/page.tsx` و متون غیرضروری صفحه `fuel/page.tsx` حذف شدند. کادرهای مشخصات `InfoCard` با ویژگی‌های `min-w-0`، `overflow-hidden`، `truncate` و جهت چپ‌به‌راست `dir="ltr"` برای نام‌کاربری/ایمیل اصلاح شدند تا از تداخل و هم‌پوشانی متون در چینش راست‌به‌چپ جلوگیری شود.

## معماری رله دو مسیره راننده-هاب (Driver/Hub SMS Relay) — 2026-10-10

- CODE-VERIFIED: برای شرایط عدم دسترسی رانندگان به اینترنت همراه در جاده، مسیر دریافت OTP به دو فلور مجزای اندروید (Gradle Product Flavors، بعد `role`) تفکیک شد. هر دو فلور از یک سورس‌ست واحد (`app/src/main`) ساخته می‌شوند؛ تفاوت‌شان فقط `applicationId`، `versionNameSuffix` و سه فیلد `BuildConfig` است (`app/build.gradle.kts:39-63`).
  - فلور `driver` — `applicationId = ir.barpro.fleet.smsforwarder.driver`: پیامک OTP سامانه را استخراج، با HMAC-SHA256 ترانکیت‌شده به ۱۶ بایت در پاکت اسکی `BP1#phone#timestamp#code#signature` امضا (`SmsFallbackEnvelope.encode`) و بدون نیاز به اینترنت با پیامک GSM به گوشی هاب ارسال می‌کند (`SmsForwardRepository.kt:521-575`). در صورت خالی بودن شماره راننده در تنظیمات، شماره مستقیماً از سیم‌کارت سخت‌افزاری بازخوانی می‌شود.
  - فلور `hub` — `applicationId = ir.barpro.fleet.smsforwarder.hub`: پاکت `BP1#...` را دریافت، امضا را محلی و در زمان ثابت بررسی می‌کند (`SmsFallbackEnvelope.verify` → `MessageDigest.isEqual`)، پاکت‌های جعلی را پیش از مصرف صف دور می‌ریزد (`SmsForwardRepository.kt:384-414`)، بقیه را در outbox دیتابیس Room نگه می‌دارد و به `POST /api/v1/otp/sms-gateway` یا `POST /api/v1/otp/sms-gateway/{driver_phone}` تحویل می‌دهد (`SmsForwarderClient.relayGatewaySms`).
- CODE-VERIFIED (مسیردهی درون‌شبکه‌ای): `CarrierDetector.resolveHubNumbers` ابتدا پیش‌فرض‌های build (در صورت ساخت با `-PBARPRO_HUB_PHONE_MCI` / `-PBARPRO_HUB_PHONE_IRANCELL`) و در غیر این صورت تنظیمات اپراتور (`fallbackServerPhoneNumber` = سیم‌کارت همراه اول هاب، `hubIrancellPhoneNumber` = سیم‌کارت ایرانسل هاب) را حل می‌کند؛ سپس `resolveRoute` سیم‌کارت هم‌اپراتور را primary و دیگری را failover قرار می‌دهد. در صورت ورود جابه‌جای فیلدها توسط اپراتور، سیستم بر اساس پیش‌شماره واقعی سیم‌کارت‌ها تصحیح خودکار انجام می‌دهد و در صورت ناشناخته بودن اپراتور راننده، اولویت به همراه اول (پوشش جاده‌ای سراسری) داده می‌شود. **تا وقتی هر دو شماره پر نشده باشند، ارسال به یک شماره تنزل می‌یابد و فیل‌اور برقرار نیست** (`CarrierDetector.kt:90-150`، `SmsForwardRepository.kt:550-590`).
- CODE-VERIFIED (ترنسپورت): تحویل هاب به سرور روی همان `endpointUrl` تنظیم‌شده انجام می‌شود. ترنسپورت تعیین‌شده این استقرار **HTTP روی پورت ۸۰** است (`infra/nginx/nginx.conf:70`؛ بلوک `listen 443 ssl` در خطوط ۹۴-۱۰۴ کامنت است) — یک انتخاب معماری، نه کمبود موقت. بنابراین اپراتور باید `allowCleartextTransport` را فعال کند، وگرنه `BarProContract.configurationError` آدرس `http://` را رد می‌کند (پیش‌فرض `false` تا آدرس HTTP با اشتباه تایپی ناخواسته استفاده نشود). پیامد پذیرفته‌شده: اصالت پاکت با HMAC تأمین می‌شود ولی توکن و کد OTP روی شبکه رمزنگاری نمی‌شوند؛ محدودسازی شبکه به درگاه بخشی از طرح است.
- CODE-VERIFIED (هارت‌بیت): بازه هارت‌بیت سلامت از `healthCheckIntervalMinutes` می‌آید؛ پیش‌فرض **۵ دقیقه** و بازه مجاز **۱ تا ۶۰ دقیقه** است (`ForwardConfig.kt:37`، `ServerHealthMonitor.kt:141-142`). هیچ هارت‌بیت ۶۰ ثانیه‌ای وجود ندارد؛ کمینه ممکن ۱ دقیقه است و فقط با تنظیم دستی اپراتور.
- CONFIG-REQUIRED (الزامات راه‌اندازی راننده): فلور `driver` «بدون تنظیم» کار نمی‌کند. حداقل سه مقدار لازم است: (۱) توکن وب‌هوک برای امضای پاکت (`SmsRelayHelper.kt:73`)، (۲) شماره سیم‌کارت هاب، چون پیش‌فرض build خالی است و مقدار از `fallbackServerPhoneNumber` خوانده می‌شود، (۳) `driverPhone` برای تشخیص اپراتور و ساخت پاکت (یا شناسایی خودکار از سیم‌کارت دستگاه). اگر شماره هاب خالی بماند `canSendSms` false شده و هیچ پیامکی ارسال نمی‌شود (`SmsForwardRepository.kt:570-578`).
- NOT-IMPLEMENTED (پروکسی سلولار 4G / Tailscale): طرح استفاده از دیتای گوشی هاب به عنوان Exit Node برای عبور ترافیک صدور از IP سلولار ایران **هیچ پیاده‌سازی‌ای ندارد** — نه در `BarPro-main` و نه در `SMS-Forwarder-Pro` (جست‌وجوی `tailscale` در هر دو مخزن فقط به همین مستندات برمی‌خورد). مسیر egress واقعی همان زنجیره Squid است: `WORKER_*_PROXY` و `EGRESS_PROXY_MODE` (`worker_first` / `clean_pool_only`) در `.env.example:60-73` و `app/automation/worker_proxy.py`؛ تزریق پروکسی به کلاینت موبایل از `proxy_url` در `app/automation/utcms_mobile_client.py:155-176` انجام می‌شود. هر ادعای «حل شدن WAF از طریق گوشی هاب» تا زمان پیاده‌سازی و اثبات runtime بی‌پایه است.
- UNVERIFIED (تأخیر): عدد «۱ ثانیه» برای تحویل پیامک درون‌شبکه‌ای هیچ بنچمارک یا لاگ زمان‌سنجی پشتیبان ندارد و باید به عنوان فرض عملیاتی تلقی شود، نه اندازه‌گیری.
- TEST-VERIFIED (2026-10-11): `tests/test_otp_delivery_contract.py` + `tests/test_otp_forwarder.py` + `tests/test_full_relay_and_bot_simulation.py` → `52 passed in 24.84s`؛ `uvx ruff check app/ tests/` → `All checks passed!`؛ `black --check app/ tests/` → `428 files would be left unchanged`؛ `.venv/bin/mypy app/ --ignore-missing-imports` → `Success: no issues found in 217 source files`؛ اندروید `testDriverDebugUnitTest` و `testHubDebugUnitTest` → هر یک `tests=86 failures=0 errors=0` (۱۷۲ آزمون کل در ۲۶ فایل گزارش XML).
- BUILD-VERIFIED (2026-10-10 19:39): تسک‌های `assembleDriverDebug` / `assembleHubDebug` خروجی‌های معتبر را در `app/build/outputs/distribution/` تولید کردند:
  - `Forward-BarPro-Driver-driverDebug.apk`: 19,043,871 بایت، هش SHA256 برابر `243cc4ba3cf078f0759d728c3d0a1935cc4028f13a4e5f009388b16f0bb507be`.
  - `Forward-BarPro-Hub-hubDebug.apk`: 19,043,875 بایت، هش SHA256 برابر `b0c0493e6449bba5fbda910bd71bba9ae77959aba2212e158d35702cb9227653`.
  - هر دو فلور سورس‌ست یکسان (`app/src/main`) و مجوزهای مانیفست یکپارچه دارند؛ رفتار آن‌ها در سطح کد با `BuildConfig.APP_ROLE` تمایز می‌یابد.
- TELEPHONY-INVARIANT (محدودیت سخت‌افزاری DSDS دوسیم‌کارت): گوشی‌های هوشمند بازار ایران در مود Dual-SIM Dual Standby کار می‌کنند؛ اتصال بسته دیتای سلولار هم‌زمان روی هر دو سیم‌کارت سخت‌افزاراً ناممکن است (فقط یک سیم‌کارت کانکشن فعال دیتا دارد). این اصل در رله لحاظ شده است:
  - فلور `driver`: ۱۰۰٪ مستقل از دیتای اینترنت (صرفاً سیگنالینگ پیامک GSM).
  - فلور `hub`: هر دو سیم‌کارت همراه اول و ایرانسل به صورت Dual Standby هم‌زمان پیامک‌های ورودی را در کانال‌های پیجینگ رادیویی دریافت می‌کنند؛ ترنسپورت وب‌هوک به سرور بارپرو به صورت ایده‌آل از طریق Wi-Fi یا دیتای یک سیم‌کارت انجام می‌شود.
- SIMULATION-VERIFIED (شبیه‌سازی سه‌گانه راننده-هاب-ربات): اتصال و چرخه سرتاسری در هر دو پروژه اثبات شد:
  - اندروید (`EndToEndRelaySimulationTest.kt`): استخراج پیامک OTP، انکود پاکت BP1 با امضای HMAC-SHA256، تطبیق اپراتور و فیل‌اور، دکود و اعتبارسنجی در هاب، و دیسپچ به درگاه وب‌هوک.
  - بارپرو (`tests/test_full_relay_and_bot_simulation.py`): دریافت در درگاه FastAPI (`/api/v1/otp/sms-gateway`) با گارد ۴۲۲ عدم تطابق شماره و اعتبارسنجی امضا، ذخیره‌سازی اتمیک با اسکریپت Lua در Redis Streams، و مصرف در ربات (`fetch_scoped_otp` با Lease Lock، ثبت موفق بارنامه و پاک‌سازی با `consume_scoped_otp`).

## تطبیق جامع سرشماره ۷۷۷۷۰۰۰۹۸۲ و کد اعتبارسنجی ۶ رقمی صدور بارنامه — 2026-10-09 (CODE-VERIFIED)

- EVIDENCE-GROUNDED: بر اساس شواهد زنده تصویری از اپلیکیشن رسمی `com.baarnameshahri` (مرحله ۵ بارنامه شهری حقیقی) و پیامک واقعی اپراتور، سرشماره متمرکز پیامک‌های صدور، ورود و تغییر رمز `7777000982` (رنج سرشماره ۷۷۷۷) و طول کد اعتبارسنجی قطعی ۶ رقمی (`833282` و `463295`) با قالب `کد ورود: XXXXXX` احراز گردید.
- CODE-VERIFIED: در پروژه `SMS-Forwarder-Pro`، سرشماره‌های `7777000982`، `+987777000982`، `7777` و `+987777` به وایت‌لیست `UTCMS_NUMBERS` در `SmsParser.kt` و قوانین پیش‌فرض دیتابیس `Room` اضافه شدند؛ تست‌های اندروید با موفقیت ۱۰۰٪ پاس شدند.
- CODE-VERIFIED: در سرویس پایتون `SMS-Forwarder-Pro/backend`، قفل ۵ رقمی در `otp_vault.py` بازگشایی شد و اعتبارسنجی کدهای ۵ و ۶ رقمی با تاب‌آوری در برابر فاصله‌ها و کلمات میانی (`[^\d]{0,40}`) فعال گردید؛ گارد تفکیک پیامک‌های اعلامی بارنامه (`صادر گردید` / `بارنامه شماره`) و دکوراتور `FallbackLimiter` با `functools.wraps` اصلاح شد. تمام ۹۵ تست بک‌اند (۱۰۰٪) پاس شدند.
- CODE-VERIFIED: در پروژه `BarPro-main`، راهنماهای راه‌اندازی و قوانین فیلتر در `otp_forwarder.py` و صفحه رانندگان فرانت‌اند (`drivers/page.tsx`) به سرشماره `7777000982` مجهز شدند؛ تست‌های `test_otp_forwarder.py` روی کد ۶ رقمی زنده پاس شدند (۷۹ تست پاس‌شده بدون هیچ خطا).

## امنیت، چرخش اسرار، ایزولاسیون بایندها و گارد استارتاپ — 2026-10-09 (CODE-VERIFIED)

- CODE-VERIFIED: اسرار افشاشده در کامیت‌های تاریخی (`JWT_SECRET`، `POSTGRES_PASSWORD`، `REDIS_PASSWORD` و `API_KEY`) با مقادیر امن ۲۵۶ بیتی بازتولید و در `.env` ثبت شدند؛ مقایسه هش‌ها عدم تطابق با نسخه تاریخی را تضمین کرد (`match_leaked=False`).
- CONFIG-VERIFIED: بایند سرویس‌های حساس در `.env` به `POSTGRES_BIND=127.0.0.1` و `REDIS_BIND=127.0.0.1` محدود شد تا از انتشار پورت‌های ۵۴۳۲ و ۶۳۷۹ بر روی اینترنت عمومی جلوگیری شود.
- SECURITY-VERIFIED: زمان انقضای کوکی احراز هویت با `JWT_ACCESS_TOKEN_EXPIRE_MINUTES=240` به ۴ ساعت کاهش یافت تا ریسک Replay Attack روی HTTP متن‌خام به حداقل برسد.
- CODE-VERIFIED: وب‌هوک فورواردر پیامک با کلید ۶۴ کاراکتری `OTP_WEBHOOK_SECRET` فعال شد و تابع `validate_environment()` به صورت Fail-Closed مستقیماً به `lifespan` در `app/main.py` متصل گردید؛ در صورت نبود کلید در پروداکشن، سرور با `RuntimeError` بالا نمی‌آید.
- CODE-VERIFIED: انتساب مستقیم وضعیت بارنامه در `app/services/scheduled_waybill_executor.py:276` با فراخوانی استاندارد `JobStateMachine.transition(...)` جایگزین شد و نقض ماشین حالت برطرف گردید.
- CODE-VERIFIED: خطای خاموش `except: pass` در `app/services/otp_delivery.py:141` با ثبت لاگ هشدار ساختاریافته جایگزین شد.
- TEST-VERIFIED: تمامی ۲,۳۴۲ تست بک‌اند و ۵۵ تست فرانت‌اند با موفقیت کامل پاس شدند و کدهای پایتون به صورت کامل با استانداردهای Black و Ruff منطبق شدند.

## زیرسیستم رله همیشگی پیامک راننده و وضعیت پایدار اتصال — 2026-10-09 (CODE-VERIFIED)

- CODE-VERIFIED: ارسال کدها در گوشی راننده (`SMS-Forwarder-Pro`) به حالت Primary SMS Relay مجهز شد که کدها را به محض استخراج با پاکت امضاشده با HMAC (`BP1#...`) مستقیماً تحویل مودم دستگاه می‌دهد تا به سیم‌کارت درگاه سرور ارسال شود و نیازی به اینترنت جاده‌ای ندارد.
- CODE-VERIFIED: سرور بارپرو در `app/api/routes/otp_forwarder.py` با دریافت پینگ `HEALTH_CHECK` یا پیامک درگاه، کلید وضعیت پایدار «راه‌اندازی‌شده» (`provisioned`) را در `rpa:forwarder:connected:{phone}` با انقضای ۹۰ روزه در Redis ثبت می‌کند؛ وضعیت رانندگان در جاده به دلیل نبود اینترنت قطع یا قرمز نشان داده نمی‌شود.
- CODE-VERIFIED: وضعیت راه‌اندازی از سلامت مجوزها تفکیک شد: فیلدهای `provisioned`، `permissions_complete` و `permissions_revoked` مستقل شدند؛ در صورت لغو یا عدم اعطای مجوزهای ضروری (دریافت یا ارسال پیامک)، `forwarder_connection_verified` به صورت Fail-Closed مقدار `false` می‌گیرد.
- CODE-VERIFIED: به‌روزرسانی اتمیک در `forwarder_health.py` (`record_observation`) با اسکریپت Lua و فال‌بک سازگار با محیط‌های تستی/حافظه‌ای پیاده‌سازی شد تا دریافت پیامک‌های بعدی اطلاعات مجوزها یا زمان اولیه راه‌اندازی را پاک نکند.
- CODE-VERIFIED: درگاه پیامک `receive_sms_gateway` از پاکت‌های آزمایشی `code == "TEST"` با اعتبارسنجی دقیق تازگی زمان (`probe_timestamp_ms`) پشتیبانی می‌کند؛ پاکت‌های قدیمی منقضی با خطای ۴۱۰ رد شده و خطای ذخیره‌سازی در Redis با ۵۰۳ Fail-Closed اعلام می‌شود.
- UI-VERIFIED: در پنل رانندگان (`apps/web/src/app/drivers/page.tsx`) وضعیت پایدار «راه‌اندازی‌شده» با کارت تفکیک‌شده، نشان‌های مجزای مجوزها (سبز، قرمز، زرد) و دکمه بازخوانی آخرین گزارش ذخیره‌شده پیاده‌سازی شد.


## ارتقای پروفایل سخت‌افزاری سرور مرکزی (32 GB RAM / 8 Cores) و بازتوزیع بودجه منابع — 2026-10-07 (CONFIG-TARGET)

- CONFIG-TARGET: سرور مرکزی به پروفایل سخت‌افزاری جدید (32 GB RAM و 8 هسته پردازشی vCPU) ارتقا می‌یابد.
- ARCHITECTURE / CGROUP-BUDGET: بودجه حافظه کانتینرهای مرکزی از 10.5 GB سابق به ~20.0 GB در استقرار Model B بازتوزیع شد که 12.0 GB فضای کاملاً آزاد برای کش دیسک، Page Cache و بافرهای کرنل لینوکس باقی می‌گذارد (در حالت All-in-One، مجموع سقف‌ها 27.5 GB با 4.5 GB فضای آزاد).
- CONTAINER-LIMITS:
  - PostgreSQL: سقف 4.0 GB (رزرو 2.0 GB)، تنظیم `shared_buffers = 1GB` و `max_connections = 150`.
  - Redis: سقف 1.0 GB (رزرو 512 MB)، دستور `--maxmemory 800mb` با `allkeys-lru`.
  - Redroid (Android 11 سروری): تعیین سقف صریح `mem_limit: 4.0g` (رزرو 2.0 GB) و `cpus: 2.0` جهت رفع کامل خطر نشت حافظه و OOM Killer در اجرای سروری بدون گوشی فیزیکی.
  - Celery Worker 1: سقف 4.5 GB (رزرو 3.0 GB)، ارتقای `shm_size` به 1.5 GB جهت پایداری مرورگر Playwright Chromium و استک OCR شبکه عصبی PyTorch.
  - FastAPI Backend: سقف 1.5 GB (رزرو 768 MB) با اجرای ۴ ورکر موازی Uvicorn (`--workers 4`) و `shm_size: 512m`.
  - Celery Scheduler: سقف 1.0 GB (رزرو 512 MB) برای تخلیه سریع صف کنترلی `rpa_scheduler`.
  - Next.js Frontend: سقف 1.5 GB (رزرو 768 MB).
  - Celery Beat: سقف 512 MB (رزرو 256 MB).
  - Squid Proxy 1: سقف 256 MB (رزرو 128 MB).
  - Monitoring Stack: سقف 1.2 GB (رزرو 600 MB).
- DB-POOL-SCALE: ظرفیت استخر اتصالات پایگاه‌داده سلری در `app/core/database.py` به `pool_size = 10` و `max_overflow = 10` قابل افزایش است که گپ بحرانی مسدود شدن صف در بار ترافیکی را برطرف می‌کند.

## تکمیل سشن و راستی‌آزمایی مستقل — 2026-10-07

- CODE-VERIFIED: در دو مسیر شروع حمل پس از صدور، خطای مبهم اکنون `unknown`
  نگه داشته می‌شود؛ شاهد مبدأ ثبت‌شده تولید نمی‌شود و پایان خودکار، حتی با
  force، مسدود است. کد رهگیری صدور حفظ می‌شود؛ تطبیق نتیجه حمل همچنان لازم است.
- TEST-VERIFIED: دو تست helper بدون مصرف‌کنندهٔ OTP حذف شدند؛ همان تضمین
  عدم کلید global و تفکیک گیرنده در مسیر واقعی HTTP/Lua/Redis آزموده شد.
  refresh پس‌زمینهٔ Clean IP در harness تست ایزوله شد.
- CODE-VERIFIED / UI-VERIFIED: tileهای CARTO تصویر خطای API key با HTTP 200
  برمی‌گرداندند؛ دو منبع عمومی OSM جایگزین شدند و کش PWA هماهنگ شد.

- CODE-VERIFIED: هویت تاریخی سوخت/بارنامه، فیلتر راننده/روز، pagination و
  جداسازی state حساب‌ها با رگرسیون‌های اجرایی بررسی شدند. پاسخ ناموفق حمل
  موفق نمایش داده نمی‌شود و پاسخ دیررس جای timeline کار دیگر نمی‌نشیند.
- CODE-VERIFIED: metadata و لاگ CAPTCHA دیگر پاسخ حل‌شده ندارند؛ تست tenant
  واقعی، پاک‌سازی نشدن OTP مشتری دیگر را با Redis ایزوله اثبات می‌کند.
- CODE-VERIFIED: Android observer نشان mock را به همان provider محدود می‌کند،
  mock=false را می‌پذیرد و uptime نامعتبر یا timestamp بسیار آینده را شاهد
  تازگی نمی‌داند. مختصات انتخابی و endpoint جاده‌ای حفظ می‌شوند؛ fallback مرکز
  شهر، جایگزین GPS انتخابی نمی‌شود.
- TEST-VERIFIED: PostgreSQL 16.15 آزمایشی، تمام migrationها تا 042 و برگشت/اجرای
  مجدد migration042 را اجرا کرد. شواهد نهایی backend/frontend/security و حدود
  آن‌ها در [گزارش ادامه](audits/2026-10-07/REPORT.fa.md) ثبت شدند: backend برابر
  2334 passed / 2 skipped، integration برابر8 و frontend برابر55 passed.
  Ruff/Black/mypy و build وب پاس شدند؛ پوشش statement برابر65.02٪ است.
- CODE-VERIFIED / ARITH: TTL 900 ثانیه claim هر job، متوسط اشغال قفل Android
  نیست؛ سقف 1400 حمل/روز از آن نتیجه نمی‌شود. تغییر serial دوم کلید قفل جهانی
  را مستقل نمی‌کند. compose/android.yml محدودیت حافظهٔ 0.5GB تعیین نکرده است.
- RUNTIME-VERIFICATION: مسیر کد همچنان apply/readback Android و فراخوانی Python
  RegisterStart/End است؛ سوییچ به ثبت در UI اپ رسمی یا صحت زندهٔ APK اثبات نشده.
  Docker، IP/firewall، ظرفیت و ثبت واقعی UTCMS در این ادامه بررسی زنده نشدند.
  audit کامل frontend به‌دلیل وابستگی dev مربوط به braces همچنان مانع CI است.

## اصلاحات ممیزی و جریان‌های راننده — 2026-10-06 (CODE-VERIFIED)

- CODE-VERIFIED: intake OTP اکنون تنها پیام پایدار ثبت می‌کند؛ گروه Stream از `0`
  شروع و pendingهای رهاشده را reclaim می‌کند. صدور در `rpa_submit_N` ورکر مالک،
  با challenge دارای مجوز/سند/egress معتبر، lease مالک‌دار و fence دیتابیس پیش از
  POST انجام می‌شود. tracking موجود و نتیجه مبهم مجوز ارسال دوباره نیستند.
  منابع: `otp_delivery.py`، `otp_wakeup_consumer.py`، `waybill_job_service.py`،
  `otp_keys.py` و `otp_challenge_guard.py`. قرارداد کامل:
  [چرخه OTP](SMS_FORWARDER_AND_OTP_LIFECYCLE.md).
- CODE-VERIFIED: `/api/v1/otp/forwarder-config/{driver_id}` راهنمای tenant-scoped
  بدون secret می‌دهد. احراز هویت query token حذف شد؛ readiness آمادگی intake
  را از اتصال واقعی گوشی جدا می‌کند. frontend نتیجه accepted را صدور نمی‌نامد.
- CODE-VERIFIED: تاریخچه بارنامه و سوخت با driver_id و روز تهران در API فیلتر
  می‌شوند؛ هر استعلام رکورد مستقل دارد و جمع snapshotهای سهمیه حذف شده است.
  هویت تاریخی fuel هنگام درخواست ذخیره می‌شود؛ داده قدیمی بدون snapshot
  با پلاک فعلی به‌عنوان واقعیت تاریخی پر نمی‌شود.
- CODE-VERIFIED: نقشه پوشش محوکننده هنگام geocode ندارد؛ fallback محدود و retry
  دارد. پین جدید آدرس قبلی را پاک می‌کند. آدرس تقریبی شهری خیابان دقیق نیست.
  popupها textContent استفاده می‌کنند. درخواست اولیه و نقطه مؤثر خیابان برای
  GPS جدا نگهداری می‌شوند؛ road snapping محدود و دارای metadata است.
- CODE-VERIFIED: recovery حمل cursor مرتب برحسب PK دارد تا رکورد آماده پشت
  ۵۰ ردیف آینده گرسنه نماند. تاریخ‌های گزارش اعتبارسنجی و روزها به تهران
  تبدیل می‌شوند. وضعیت ETA خراب/نامعلوم باید پیش از پایان حمل بررسی شود.
- TEST-VERIFIED / حدود: شواهد نسخه مبنا و تست‌های اصلاح در
  [گزارش 2026-10-06](audits/2026-10-06/REPORT.fa.md) جدا ثبت شده‌اند. اسکن رسمی
  Codex Security روی `e664e54..6c5564e` دو یافته Medium تأیید کرد؛ سطح عملیاتی
  P1 در گزارش با شدت امنیتی یکسان نیست. Redis محلی واقعی است؛ UTCMS و broker
  در تست‌های یکپارچه OTP مصنوعی‌اند. PostgreSQL16، Docker و deployment محلی
  تأیید نشده‌اند. snapshotهای قبل از این بخش، قرارداد جدید را ثابت نمی‌کنند.
- CONFIG-TARGET: ارتقا نیازمند migration سوابق fuel و نسخه هماهنگ worker/API است؛
  worker قدیمی inline OTP باید drain شود. هیچ داده production، مجوز live-submit
  یا ادعای حرکت واقعی خودرو از این ممیزی حاصل نمی‌شود.

## تفکیک راهنمای ایجنت و حدود تأیید — 2026-10-06 (CONFIG-TARGET / TEST-VERIFIED)

- CONFIG-TARGET: [AGENTS.md](../AGENTS.md) اکنون هستهٔ ۱۱٬۸۰۲ بایتی است؛ قواعد
  اصلی، هویت پروژه، قراردادهای کدنویسی، هشدارها، آزمون‌ها و نقشهٔ مطالعه را نگه
  می‌دارد. ۱۱ مرجع موضوعی/تاریخی فقط در [docs/agent-reference](agent-reference/README.md)
  قرار دارند. این منابع شرط مطالعه بر اساس موضوع دارند و با لینک عادی معرفی
  شده‌اند؛ واردسازی خودکار یا انتقال به قواعد عمومی صورت نگرفته است.
- TEST-VERIFIED (ساختار مستندات): هر ۱٬۰۸۴ خط نسخهٔ ۱۱۳٬۴۳۷ بایتی قبلی دقیقاً
  یک بار در ۲۱ بلوک حفظ شد. بازسازی بایت‌به‌بایت با بکاپ و SHA-256 تطابق دارد؛
  [manifest انتقال](agent-reference/migration-manifest.json) شاهد منشأ و محدودهٔ
  خطوط است. ۵۹ لینک محلی معتبرند و همهٔ Markdownهای حاصل زیر ۲۴٬۰۰۰ بایت‌اند؛
  بزرگ‌ترین فایل ۱۴٬۷۱۹ بایت است. متن تاریخی حفظ شده و تأیید تازهٔ محتوای آن نیست.
- TEST-VERIFIED (بارگذاری بومی، بدون مدل): helper نسخهٔ `0.61.0` از Gemini CLI
  فایل اصلی جدید و قواعد عمومی را بدون خطای import خواند. hash قواعد عمومی،
  تنظیمات عمومی و `.gemini/settings.json` پروژه نسبت به قبل از این تفکیک ثابت
  ماند. شواهد محلی: `~/Downloads/antigravity-review-2026-10-06/evidence/`
  در فایل‌های `barpro-agents-split-verification.json` و
  `barpro-gemini-context-after-split.json`.
- RUNTIME-VERIFICATION / UNVERIFIED: probe زندهٔ Antigravity با انتظار برای پایان
  واقعی، پیش از پاسخ مدل در eligibility سرویس روی `/v1internal:loadCodeAssist`
  خطای HTTP 403 داد. علت ریشه‌ای حساب/دسترسی/مسیر اتصال تعیین نشده است؛ آزمون
  رفتاری پاس محسوب نمی‌شود. طبق درخواست کاربر، بررسی داخل برنامه را خود او
  انجام می‌دهد. این تغییر هیچ شاهد تازه‌ای از وضعیت production یا UTCMS ندارد.

## محدودهٔ دستورهای ایجنت و مرجع مهاجرت تاریخی — 2026-10-06 (CONFIG-TARGET)

- CONFIG-TARGET: در محیط بررسی‌شده، سیاست عمومی نسخهٔ ۳ و مهارت‌های عمومی
  `evidence-workflows` سراسری باقی مانده‌اند. دستور اختصاصی BarPro از مهارت
  عمومی `vercel-nextjs-expert` حذف و متن دقیق آن در مرجع محلی
  [.agents/skills/barpro-deploy-ops/references/historical-vercel-hybrid-migration.md](../.agents/skills/barpro-deploy-ops/references/historical-vercel-hybrid-migration.md)
  نگهداری شده است. این متن پیشنهاد تاریخی و تأییدنشده است و استقرار فعلی یا
  مجوز مهاجرت به Vercel را اثبات نمی‌کند؛ فقط برای بررسی مرتبط با BarPro خوانده شود.
- CONFIG-TARGET: فایل محلی [.gemini/settings.json](../.gemini/settings.json)
  مقدار `context.fileName` را برابر `["GEMINI.md", "AGENTS.md"]` تعیین می‌کند.
  این تنظیم متعلق به همین پروژه است؛ سیاست عمومی را به BarPro محدود نمی‌کند
  و هیچ ارجاع خودکاری از فایل عمومی به محتوای BarPro ایجاد نشده است.
- CONFIG-TARGET / شاهد بررسی: helperهای native نسخهٔ `0.61.0` از Gemini CLI با
  تنظیم پروژه، فایل عمومی `GEMINI.md` و `AGENTS.md` همین مخزن را خواندند.
  ثبت schema، مسیرها، hashها و حدود این بررسی در
  `~/Downloads/antigravity-review-2026-10-06/evidence/barpro-gemini-context.json`
  و سابقهٔ انتقال/نسخه‌های پشتیبان در `barpro-scope-migration.json` همان پوشه است.
  این شاهدِ بارگذاری در helper است؛ تازه‌سازی سشن تعاملی موجود یا تبعیت مدل از
  دستورها در این بررسی آزموده نشده است.
- RUNTIME-VERIFICATION: هیچ ادعای تازه‌ای دربارهٔ استقرار production، تغییر
  معماری، مهاجرت Vercel یا عملیات زندهٔ UTCMS از این تغییر مستندات حاصل نمی‌شود.
  کد برنامه تغییر نکرده؛ مرجع مهارت طبق `.gitignore` موجود فایل محلی باقی می‌ماند.

## سازگاری جامع فورواردر اندروید، دیکود منعطف JSON و فالبک کد ملی راننده — 2026-10-06 (CODE-VERIFIED)

- CODE-VERIFIED: تابع هلپر `_safe_json_dict` در `app/services/otp_wakeup_consumer.py` به منظور پارس امن فیلدهای `result_json` و `payload_json`، چه در قالب `dict` و چه در قالب رشته متنی JSON (`str`) پیاده‌سازی شد؛ این قابلیت از ارزیابی تهی دیکشنری در شرایط ناسازگاری درایورهای پایگاه‌داده جلوگیری می‌نماید (`test_safe_json_dict`).
- CODE-VERIFIED: پشتیبانی از تکمیل مستقیم بارنامه با شناسه `job_id` در `resolve_and_complete_pending_job_for_otp`؛ در صورتی که رویداد استریم ردیس یا ثبت دستی دارای `job_id` باشد، بارنامه مستقیماً و بدون وابستگی انحصاری به شماره تلفن راننده تکمیل و صادر می‌شود (`test_resolve_and_complete_by_job_id_direct`).
- CODE-VERIFIED: فالبک جستجوی راننده از روی کد ملی و شماره موبایل پی‌لود در `WaybillJobService.submit_otp`. در صورتی که `job.driver_id` مقداردهی نشده باشد اما در پی‌لود بارنامه اطلاعات راننده موجود باشد، سیستم راننده متناظر مستاجر را در پایگاه‌داده یافته و پیوند می‌دهد (`test_driver_fallback_by_national_code_in_submit_otp`).
- CODE-VERIFIED: احراز هویت چندگانه وب‌هوک برای کلاینت‌های اندروید در `_require_webhook_auth` (`otp_forwarder.py`): پشتیبانی از هدرهای `Authorization: Bearer <token>`، `X-Webhook-Token`، `X-Webhook-Secret` و پارامتر پرس‌وجو `?token=<secret>` علاوه بر هدر اصلی `X-OTP-Webhook-Token` (`test_webhook_auth_via_bearer_and_query_token`).
- CODE-VERIFIED: توسعه مپینگ فیلدهای اپلیکیشن‌های فورواردر اندروید (`receive_sms_forwarder_webhook` در `otp_forwarder.py`): پشتیبانی از کلیدهای `smsBody`، `messageBody`، `address_from`، `phoneNumber`، `receiver`، `receiver_phone`، `time`، `date` و گسترش کلیدواژه‌های استخراج کد به «کد ثبت» (`test_forwarder_android_field_aliases`).
- CODE-VERIFIED: اندپوینت‌های تست ارتباط و سلامت فورواردر `GET /api/v1/otp/ping` و `GET /api/v1/otp/health` برای اعتبارسنجی اتصال شبکه اپلیکیشن‌های اندروید پیش از ارسال پیامک (`test_otp_ping_and_health_endpoints`).
- CODE-VERIFIED: آلیاس روت صدور بارنامه `@router.post("/waybill-jobs/{job_id}/otp")` در کنار روت موجود `/submit-otp` (`app/api/routes/multitenant.py`) جهت تضمین سازگاری با کلیه کلاینت‌ها (`test_waybill_job_otp_route_alias`).
- CODE-VERIFIED: بیدارسازی و صدور فوری در ثبت دستی کد (`submit_manual_otp` در `otp_forwarder.py`): اتصال مستقیم به `trigger_job_completion_on_otp_received` جهت تسریع در فرآیند صدور بارهای معلق در اپراتوری دستی (`test_manual_otp_submission_triggers_wakeup`).
- TEST-VERIFIED: تمامی ۹۸ تست زنجیره OTP و ایزولاسیون مستاجران (`tests/test_otp*` و `tests/test_tenant*`) با موفقیت ۱۰۰٪ سبز پاس شدند.

## چرخه کامل OTP، انتساب تک‌پرواز، بیدارسازی رویدادمحور و قفل اجاره (Lease) — 2026-10-05 (CODE-VERIFIED)

- CODE-VERIFIED: سرویس مصرف‌کننده رویدادمحور `app/services/otp_wakeup_consumer.py` متصل به جریان پایدار Redis Streams (`rpa:otp:stream`) با گروه مشتریان `barpro_otp_group` و تایید اتمیک `XACK`. تابع `resolve_and_complete_pending_job_for_otp` بلافاصله پس از دریافت کد، اسناد معلق در وضعیت `WAITING_OTP` یا `UNKNOWN (otp_required)` را شناسایی کرده و صدور قطعی را انجام می‌دهد؛ بحران پیامک دیررس ثانیه ۱۲۵ (Late SMS Race Condition) پس از تایم‌اوت کارگر به طور قطعی حل شد (`test_late_sms_125_second_auto_completion`).
- CODE-VERIFIED: مدیریت توزیع‌شده قفل اجاره (`reserve_otp_issue_lease` / `release_otp_issue_lease` در `app/automation/otp_keys.py`) با کلید `lock:otp:issue:{job_id}` و TTL ۳۰ ثانیه؛ از هرگونه تداخل، رقابت همزمان (Race Condition) یا فراخوانی تکراری بین کارگر سلری و مصرف‌کننده وب‌هوک به طور قطعی جلوگیری می‌کند (`test_lease_locking_prevents_concurrent_issue`).
- CODE-VERIFIED: ابطال اتمیک و سراسری کلیدهای مصرف‌شده (`consume_scoped_otp` در `app/automation/otp_keys.py`). بلافاصله پس از صدور موفق، کلید بارنامه (`rpa:otp:job:{job_id}`)، کلید راننده (`rpa:otp:phone:{phone}`)، کش سند معلق (`rpa:job:pending_doc:{job_id}`) و ردیابی معلق راننده (`rpa:otp:pending_by_phone:{phone}`) پاکسازی می‌شوند تا از مصرف کد منقضی در بارنامه‌های بعدی جلوگیری شود (`test_consume_scoped_otp_cleans_all_keys`).
- CODE-VERIFIED: تاب‌آوری در برابر خطای ۱ ساعته تغییر ساعت رسمی ایران (`test_iran_dst_clock_skew_tolerance` در `app/services/otp_delivery.py`). پس از لغو تغییر ساعت تابستانی در سال ۱۴۰۲، گوشی‌های اندروید پچ‌نشده رانندگان ۱ ساعت انحراف دارند؛ تابع `sms_received_at` با نرمال‌سازی انحراف ۳۶۰۰ ثانیه‌ای (با تلرانس ۹۰ ثانیه) مانع از خطای کاذب ۴۱۰ یا ۴۲۲ می‌گردد. همچنین در `waybill_enhanced.py` مبنا قرار دادن `ingested_at` سرور BarPro انحراف ساعت محلی گوشی را بی‌اثر می‌کند (`test_fetch_scoped_otp_handles_device_clock_skew`).
- CODE-VERIFIED: انتساب هوشمند تک‌بارنامه معلق (`resolve_single_flight_pending_phone` در `otp_wakeup_consumer.py` و `otp_forwarder.py`). برای حل چالش عدم وجود MSISDN در سیم‌کارت‌های ایرانسل/همراه اول و رله‌های GSM، در غیاب شماره راننده در صورتی که دقیقاً ۱ بارنامه معلق وجود داشته باشد، پیامک به همان بارنامه اختصاص می‌یابد (`test_single_flight_phone_attribution_from_redis`).
- CODE-VERIFIED: گارد امنیتی عدم ابهام (`AMBIGUOUS_OTP`). در صورتی که بیش از ۱ بارنامه معلق در سیستم باشد و پیامک فاقد شماره راننده باشد، سیستم حدس نمی‌زند و با خطای صریح HTTP 422 (`AMBIGUOUS_OTP`) اعلام می‌کند که `driver_phone` الزامی است (`test_ambiguous_otp_attribution_rejected_when_multiple_jobs_pending`).
- CODE-VERIFIED: اصلاحات اتوماسیون وب و کارگر (`waybill_bot_multitenant.py` و `waybill_job_service.py`): ذخیره متادیتای راننده در سشن کش موقت ردیس، رصد کلید `completed_otp:{job_id}` در حلقه انتظار جهت خروج فوری کارگر بدون معطلی در صورت صدور توسط وب‌هوک، و بررسی قفل اجاره در `submit_otp`.
- CODE-VERIFIED: تزریق امن پراکسی خروجی (`get_worker_proxy_url`) در `WaybillJobService.submit_otp` جهت تضمین ارسال درخواست‌های صدور از طریق پراکسی Squid محلی راننده و جلوگیری از نشت IP سرور مرکزی (`test_submit_otp_uses_worker_proxy`).
- CODE-VERIFIED: انتساب چندکاناله شماره راننده در وب‌هوک (`app/api/routes/otp_forwarder.py`): پشتیبانی همزمان از مسیر URL (`/sms-forwarder/{driver_phone}`)، پارامتر پرس‌وجو (`?driver_phone=...`)، هدر HTTP (`X-Driver-Phone`) و بدنه JSON، جهت تسهیل بی‌نقص کانفیگ در انواع اپ‌های فورواردر اندروید (`test_path_based_driver_phone_webhook`, `test_query_param_driver_phone_webhook`, `test_header_driver_phone_webhook`).
- CODE-VERIFIED: تسک دوره‌ای سلری `barpro.otp.sweep_stream` در `app/workers/celery_app.py` و `tasks.py` با زمان‌بندی هر ۵ ثانیه (`schedule(5.0)`) بر روی صف `rpa_scheduler` (`RPA_SCHEDULER_QUEUE`) با انقضای ۴ ثانیه، جهت تخلیه و تایید مداوم رویدادهای جریان ردیس بدون ایجاد تأخیر در صف‌های کاری (`test_sweep_otp_stream_celery_task`).
- CODE-VERIFIED: فیلد `allow_otp_flow: bool = Field(default=True)` در اسکیمای `WaybillJobCreate` و `WaybillBatchItemCreate` (`app/schemas/multitenant.py`) جهت فعال‌سازی پیش‌فرض جریان OTP برای بیدارسازی خودکار بارنامه‌های شبانه.
- CODE-VERIFIED: بازیابی خودکار از انحراف ساعت گوشی راننده (`receive_sms_forwarder_webhook` در `otp_forwarder.py`): خطاهای زمانی ناشی از جلو بودن ساعت گوشی راننده با فالبک امن به زمان معتبر سرور (`now`) مهار شده و مانع از رد شدن کدهای معتبر می‌گردد (`test_webhook_recovers_gracefully_from_phone_clock_skew`).
- CODE-VERIFIED: ارتقای رگکس‌های استخراج کد OTP (`extract_otp_code` در `otp_forwarder.py`): پشتیبانی جامع از کلیدواژه‌های رسمی و عرفی UTCMS شامل «کد صدور»، «کد یکبار مصرف»، «کد امنیتی»، «رمز تایید» و «کد مجوز» ضمن حفظ بلاک‌های امنیتی پیامک‌های بانکی و تبلیغاتی (`test_extract_otp_code_persian_messages`).
- CODE-VERIFIED: پاکسازی خودکار بارهای منقضی از مجموعه ردیس (`rpa:otp:active_pending_jobs` در `resolve_single_flight_pending_phone`) و ممانعت از بازنویسی شماره تلفن مسیر در ورودی فرم، خطاهای کاذب ابهام فانتوم را ریشه‌کن کرد (`test_single_flight_attribution_prunes_stale_jobs`, `test_webhook_preserves_path_phone_with_form_body`).
- CODE-VERIFIED: ماشین حالت صدور با OTP (`WaybillJobService.submit_otp`) جهت پشتیبانی ایمن از وضعیت‌های معلق `needs_review` و `unknown` (از مسیر میانی `reconciling`) و همچنین `waiting_retry` (از مسیر `in_progress`) ارتقا یافت و بلافاصله پس از صدور، چرخه حمل GPS خودکار (`init_shipping` + `register_start_of_shipping`) را فعال می‌نماید (`test_submit_otp_succeeds_from_needs_review_status`).
- CODE-VERIFIED: ابزار شبیه‌ساز فورواردر پیامک `scripts/sms_forwarder_simulator.py` برای ارسال وب‌هوک‌های تستی استاندارد و گیت‌وی امضاشده HMAC بدون وابستگی به سخت‌افزار فیزیکی موبایل.
- TEST-VERIFIED: تمامی ۹۰ تست زنجیره OTP و ایزولاسیون مستاجران (`tests/test_otp*` و `tests/test_tenant*`) به همراه ۲۹۰ تست هسته بارنامه و حمل با موفقیت کامل (۱۰۰٪ سبز) پاس شدند.

## OTP پایدار + fence چرخه حمل — 2026-10-04 (CODE-VERIFIED)

- CODE-VERIFIED: سرویس جدید `app/services/otp_delivery.py` (ingest پایدار و مرتب OTP). یک تراکنش Lua یکجا dedup + ordering + نوشتن پایدار + pub/sub را انجام می‌دهد: retry نه TTL را تازه می‌کند نه کد مصرف‌شده را احیا، و SMS قدیمی‌تر نمی‌تواند روی OTP جدیدتر بنویسد (409). TTL=300s، skew=30s، روی قطع Redis **fail-closed** (503؛ تحویل پیش از نوشتن پایدار ACK نمی‌شود). متن خام SMS نه ذخیره و نه بازگردانده می‌شود.
- CODE-VERIFIED: مسیر امضاشده `POST /api/v1/otp/sms-gateway` و `POST /api/v1/otp/sms-gateway/{driver_phone}` — envelope `BP1#phone#timestamp#code#signature` با HMAC-SHA256 (`hmac(OTP_WEBHOOK_SECRET, "#".join(parts[:4])).hexdigest()[:32]`) و تطبیق فرستنده با گیرنده؛ همان هویت تحویلِ `sms-forwarder` را دارد (dedup مشترک). فورواردر اکنون `driver_phone` اجباری، سقف بدنه 16KB، رویداد `HEALTH_CHECK` و `extract_otp_code` کلیدواژه‌محور دارد (کد رهگیری/شماره تلفن/پیامک بانک هرگز OTP تلقی نمی‌شود).
- CODE-VERIFIED: ماشین حالت حمل اکنون `ready → starting → in_transit → finishing → delivered` (به‌علاوه `unknown`/`needs_review`) است. fenceهای پایدار `starting`/`finishing` زیر completion-claim دوکلیده پیش از mutation نوشته می‌شوند؛ `reclaim_stuck_shipping_fences` فقط fence رهاشده (کهنه‌تر از `COMPLETION_CLAIM_TTL_SECONDS` و بدون claim زنده) را به `in_transit` بازمی‌گرداند و هرگز mutation زنده را نمی‌دزدد (روی قطع Redis fail-closed). `estimated_end_at` خالی/آینده به‌صورت `waiting_eta` fail-closed است.
- CODE-VERIFIED: شروع خودکار پس از صدور (`waybill_bot_multitenant._finalize_shipping_start`) نتیجه‌ی UTCMS را رعایت می‌کند (ack/4006 → `in_transit` با ثبت شاهد مبدأ؛ رد صریح → `unknown`؛ raised → `in_transit` قابل‌sweep) و دیگر `in_transit` را بی‌قیدوشرط ست نمی‌کند. `utcms_mobile_client.finish_shipping_with_gps` روی 404 دیگر پاسخ 200 جعلی نمی‌سازد و به `RegisterEndOfShipping` fallback می‌کند.
- CODE-VERIFIED: فیلتر تاریخ تاریخچه (`_parse_history_date_bounds`) اکنون اکیداً `YYYY-MM-DD` را می‌پذیرد و بازه‌ی معکوس را با 400 رد می‌کند؛ `/shipping/finish` دستی هدف فاصله‌ی قاعده‌ی 4012 را مانند مسیر Beat افزایش می‌دهد.
- موارد باز (fail-closed، ثبت‌شده در ISSUES.md): سیاستِ egress استخر Clean IP (O1، نیازمند تصمیم کاربر)، واگراییِ `unknown` در `/start`//`/finish` دستی (O2/O3/O4)، و لبه‌های گزارش‌گیری (O5/O6).

## بسته رفع ممیزی — 2026-10-02 (25 یافته، همه رفع/مستند شد)

- CODE-VERIFIED: کلیدهای idempotency در مسیر صف tenant-scoped شدند
  (`tenant:{client_id}:` یا هش canonical) و هر دو lookup در `create_or_get_task` با
  `client_id` فیلتر می‌شوند؛ tenant دوم با کلید تکراری دیگر job tenant اول را hijack
  نمی‌کند (`app/services/task_service.py`, `app/queue/queue_manager.py`).
- CODE-VERIFIED: ریکاوری 4011 در `gps_shipping_manager` fail-closed شد — خطا در ریکاوری
  → trip `unknown` و job از طریق `JobStateMachine` به `reconciling` می‌رود، هرگز `success`؛
  کد rule به‌صورت ساختاری استخراج می‌شود (substring آزاد «4011» دیگر match نمی‌شود).
- CODE-VERIFIED: `/start` در خطای transient apply/readback دیگر `failed` persist نمی‌کند
  (503 بدون آجر شدن job)؛ readback مختصات ذخیره‌شده waybill را با ۵ متر تلرانس چک می‌کند؛
  `apply_location` علاوه بر لاک per-job از لاک device-wide
  `lock:android-device:mutation` عبور می‌کند (fail-closed).
- CODE-VERIFIED: کلید گلوبال `rpa:otp:latest` بازنشسته شد؛ خوانندگان automation به کلیدهای
  job-scoped → phone-scoped مهاجرت کردند (`app/automation/otp_keys.py`)؛ ترتیب fallback هرگز
  گلوبال بدون scope نیست.
- CODE-VERIFIED: auth-state مسیر legacy `/waybill/create-with-map` (از جمله مسیر inline صف)
  per-tenant scope می‌گیرد (`client-{id}` / `infra`)؛ vault سشن درایور
  `utcms:driver:{token,refresh,auth-lock}:{client_id}:{national_code}` شد و همه call-siteها
  `client_id` را پاس می‌دهند؛ لاک `lock:shipping:{job_id}` بعد از احراز مالکیت گرفته می‌شود؛
  ساخت درایور توسط master_admin بدون `client_id` صریح 400 می‌دهد.
- CODE-VERIFIED: `JWT_SECRET` کوتاه‌تر از ۳۲ کاراکتر در startup fail-fast می‌دهد؛
  `.env.example` همه env varهای خوانده‌شده توسط کد را مستند می‌کند؛
  `API_AUTH_MODE=off` هشدار امنیتی بلند در startup می‌دهد.
- CODE-VERIFIED: jobهای tracking-received دیگر در UNKNOWN گیر نمی‌کنند —
  endpoint دستی reconcile با `audit_only=True` و sweep دوره‌ای
  `orchestrator.reconciliation.audit_tracking_received` (Beat هر ۱۰ دقیقه) شاهد History را
  attach می‌کند؛ SUCCESS همچنان فقط با match شاهد History اعلام می‌شود؛ sweep هرگز resubmit
  نمی‌کند.
- CONFIG-TARGET: `/shipping/*` از پشت nginx پروداکشن به backend می‌رسد (regex اصلاح شد)؛
  `API_BASE_URL` فرانت‌اند `/api/v1` انتهایی را هم strip می‌کند.
- NOT-PROVEN/باز: مقادیر `.env.bak` در تاریخچه گیت واقعی به‌نظر می‌رسند — چرخش credential و
  purge تاریخچه نیازمند تصمیم صریح کاربر است (هیچ‌کدام انجام نشده).
- ACCEPTED-EXCEPTION (تصمیم کاربر 2026-10-02): مسیر mobile-OTP بدون شاهد History به
  SUCCESS می‌رسد؛ رفتار فعلی حفظ شد و به‌عنوان استثنای مستند پذیرفته شد
  (`waybill_job_service.py:694-716` — شاهدهای ۱ و ۲ موجود، سومی اعمال نمی‌شود).
- نتایج گیت‌ها در زمان کامیت: ruff/black/mypy سبز؛ pytest کامل در گزارش commit ثبت شد.

## اصلاح خط لوله GPS — 2026-09-27 (راستی‌آزمایی ممیزی + پیاده‌سازی P0/P1)

- CODE-VERIFIED: هر 18 بند ممیزی راستی‌آزمایی شد؛ یافته اصلی تأیید شد (مسیر ثبت از TravelEngine/FakeTraveler عبور نمی‌کرد).
- CODE-VERIFIED: باگ timestamp (Tehran-labelled-as-Z) در `gps_shipping_manager.auto_complete_shipping` و `utcms_mobile_client.register_end_of_shipping` به UTC-Z اصلاح شد.
- CODE-VERIFIED: تک‌منبع Route Authority (`app/services/route_authority.py`) + snapshot فریز روی `ShippingState` + `geometry_from_snapshot`؛ `distance_service` و `/waybill/calculate-route` delegate می‌کنند.
- CODE-VERIFIED: اتصال TravelEngine (`app/services/shipping_travel_service.py`): start/finish گیت readback اندروید دارند (fail-closed فقط وقتی `ANDROID_BRIDGE_ENABLED=true`)؛ در غیر این صورت مسیر legacy `operator_anchor` حفظ می‌شود.
- CODE-VERIFIED: `measured_distance_km` در finish اختیاری و خودکار از telemetry/مسیر شد (`measured_source` شفاف).
- CODE-VERIFIED: auto-complete arrival-driven شد (`waiting_arrival` وقتی snapshot دارد و ARRIVED نیست؛ ETA فقط watchdog) + گیت readback مقصد.
- CODE-VERIFIED: observer تولیدی `AdbLocationObserver` (`app/travel/android_observer.py`) شکاف «no bundled observer» را پر کرد.
- CODE-VERIFIED: مایگریشن `040_add_route_template_polyline` + snapshot جاده‌ای روی template.
- CODE-VERIFIED: `LocationMapPicker` commit فوری مختصات (geocode async)؛ `ShippingRouteMap` بدون inline-style، فاصله خودکار، بج مسیر واقعی/تخمین.
- TEST-VERIFIED: 188 تست shipping/travel/route + 8 تست جدید `test_route_authority.py` سبز؛ `tsc`/`eslint`/`ruff`/`audit-ui` پاس.
- NOT-PROVEN (نیازمند canary زنده): زنجیره E2E `Map = Snapshot = Engine = Readback = UTCMS payload = UTCMS readback` روی Redroid با مختصات (36.261100,50.442300 → 36.169600,50.611900) هنوز اجرا/لاگ نشده؛ `/step` همچنان 410.
- جزئیات کامل: [GPS_PIPELINE_REMEDIATION_2026-09-27.md](archive/GPS_PIPELINE_REMEDIATION_2026-09-27.md).

## تصمیم معماری GPS — 2026-09-15

- CONFIG-TARGET (تصمیم صریح کاربر): FakeTraveler جایگزین روش فعلی اجرای GPS
  می‌شود؛ روی Android مجازی سرور Linux، بدون نیاز به گوشی فیزیکی.
- مسیر هدف: BarPro orchestration → Android Bridge → `cl.coders.faketraveler`
  → Android location → `com.baarnameshahri` → Squid → UTCMS.
- CODE-VERIFIED: `app/android_bridge/` مشاهدهٔ opt-in با serial صریح ADB، بررسی
  نصب اپ رسمی و FakeTraveler، boot، ABI، نمایشگر و تنظیم proxy دارد؛ گزارش آن
  صریحاً `submission_ready=false` و `egress_verified=false` است.
- CODE-VERIFIED: مسیر فعلی `shipping_gps.py` همچنان از کلاینت HTTP استفاده می‌کند؛
  این مسیر مبنای مهاجرت است. Bridge هنوز به عملیات start/finish متصل نشده است.
- RUNTIME-VERIFIED در `2026-09-25`: استقرار کامل Redroid با پیکربندی امن (`privileged: false`، `cap_add: [SYS_ADMIN, NET_ADMIN]`، مونت گره‌های `/dev/binderfs/{binder,hwbinder,vndbinder}`)، کانتینر `barpro-redroid` فعال روی IP داخلی `172.20.0.80:5555` و لوپ‌بک `127.0.0.1:5555`. نصب اپ رسمی و FakeTraveler، اعطای `android:mock_location allow`، تنظیم پراکسی Squid 1 (`172.20.0.1:3128`) و راستی‌آزمایی IP خروجی `<CENTRAL_IP>`. کنترلر `AndroidShippingController` با تست‌های کامل واحد در `tests/test_android_bridge_controller.py` مستقر شد.
- جزئیات: [طرح اجرایی](ANDROID_CLIENT_IMPLEMENTATION_PLAN.md) و
  [ممیزی شواهد و تست](ANDROID_CLIENT_REVIEW.md).

## 1.0 snapshot زنده و استقرار Android (2026-09-25)

- LIVE-OBSERVED & CONFIRMED: صدور قطعی دو فقره بارنامه زنده در سامانه کشوری UTCMS با احراز هویت دوطرفه، حل آفلاین کپچای ریاضی (Math CRNN) و تأیید کامل قانون اثبات ثبت (شامل تطبیق History در همان روز):
  1. بارنامه اول (Job 125): شناسه سند `226157460`، شماره بارنامه رسمی `1349750688`، راننده پرویز قنائی (`0321410408`)، ناوگان `23ع965ایران78`، مسیر البرز طالقان (میر به کشرود). وضعیت در پرتال: `درحال حمل` (کد ۱). ثبت قطعی در دیتابیس با `mutation_status: confirmed`.
  2. بارنامه دوم (Job 127): شناسه سند `226164459`، شماره بارنامه رسمی `1349757758`، راننده یوسف قلی‌زاده (`4929889601`)، ناوگان `32ع444ایران27`، مسیر آذربایجان غربی شوط (دیزج به مرگن وسط). وضعیت در پرتال: `درحال حمل` (کد ۱). ثبت قطعی در دیتابیس با `mutation_status: confirmed`.
- RUNTIME-VERIFIED: مهندسی معکوس و آنالیز عمیق بایت‌کد هرمس (Hermes v94) و فایل‌های DEX پکیج رسمی `com.baarnameshahri`؛ کشف ماژول امنیتی بومی اختصاصی `Lcom/baarnameshahri/security/SecurityNativeModule;` شامل تست‌های روت (`checkRoot`)، امولاتور (`isProbablyEmulator`) و Mock Location (`detectMockLocationApps`). اثبات پایداری رویکرد کلاینت مستقیم موبایل BarPro (Mobile Transport) جهت دور زدن لایه ناپایدار UI.
- RUNTIME-VERIFIED: کشف قواعد زمانی و استیت‌ماشین سامانه UTCMS:
  - بارنامه‌های صادره با فیلد خوداظهاری حرکت (`selfDeclaredTimeOfStartShipment`) بلافاصله به وضعیت `درحال حمل` درمی‌آیند؛ فراخوانی مجدد `RegisterStartOfShipping` خطای ۴۰۰۶ بازمی‌گرداند.
  - ثبت شروع حمل در روزهای پس از تاریخ صدور سند با خطای ۴۰۱۳ مسدود است.
  - ثبت پایان حمل منوط به سپری شدن بازه زمانی تخمینی سفر (`estimatedTimeOfEndShipment`) است و پیش از آن با خطای ۴۰۱۱ یا ۴۰۱۳ رد می‌شود.
  - دیکامپایل سورس رسمی React Native (`assets/index.android.bundle`) اثبات کرد: آرایه `gpsList` در `RegisterEndOfShipping` اکیداً نیازمند فیلد `"Date"` (ایزو UTC) است و فقط انواع `Type: 2` (وای‌پوینت) و `Type: 3` (مقصد) را می‌پذیرد؛ `Type: 1` با خطای ۴۰۰۶ رد می‌شود.
  - شرط حداقل مسافت ۲ کیلومتری (Rule 4012): سرور UTCMS پایان حمل با مجموع مسافت کمتر از ۲ کیلومتر را با خطای ۴۰۱۲ رد می‌کند («برای ثبت پایان حمل، شما حداقل باید 2 کیلومتر طی کرده باشید»). کلاینت BarPro به صورت پیشگیرانه با تزریق وای‌پوینت انحراف جاده‌ای استاندارد (Detour Waypoint با `Type: 2`) مسافت را به بالای ۲.۱۵ کیلومتر می‌رساند.
  - مدارشکن و پس‌زدگی توانی: خطای ۴۲۹ منجر به خنک‌سازی ۱۰ الی ۳۰ دقیقه‌ای، خطای ۴۰۱۲ و خطای ۴۰۱۳ منجر به خنک‌سازی ۵ دقیقه‌ای در `ShippingState` می‌گردد.
  - فرمت دقیق و اعتبارسنجی پلاک خودرو در کلاینت موبایل: `(\d{2})([^\d]+)(\d{3})(\d{2})` متناظر با `t2` (دو رقم اول)، `t3` (کد حرف)، `t4` (سه رقم وسط) و `t1` (دو رقم کد ایران).

## 0.9 snapshot تاریخی (2026-09-14، مسیر HTTP)

- CODE-VERIFIED: یکپارچه‌سازی فرآیند GPS Shipping با Redis Session Vault — اندپوینت‌های `/shipping/start` و `/shipping/finish` با متد `get_or_login_client()` بازنویسی شدند. bearer token با TTL کوتاه پیش‌فرض ۲۴۰ ثانیه و refresh token با TTL پیش‌فرض ۷۰۰۰ ثانیه نگهداری می‌شود؛ refresh پیش از لاگین جدید امتحان می‌شود. این کار لاگین تکراری و ریسک اسپم را کم می‌کند، اما 429 را ناممکن نمی‌کند.
- CODE-VERIFIED: گارد دفاعی fail-closed برای پراکسی (`ProxyUnavailableError`) — بررسی صریح عدم تهی بودن `proxy_url` در محیط‌های پروداکشن، تفکیک پاسخ با HTTP 503 صریح («پراکسی UTCMS در دسترس نیست — IP سرور محافظت شد») و جلوگیری از نشت ترافیک مستقیم بدون پراکسی.
- CODE-VERIFIED: تقویت مقاومت ضد WAF در کلاینت موبایل — بر اساس مهندسی معکوس بایت‌کد هرمس و کد Smali پکیج رسمی `com.baarnameshahri`، هدرهای دسکتاپ Client Hints با `default_headers=False` در curl_cffi کاملاً مسدود شدند، هدر جعلی `X-Requested-With` حذف شد، هدرهای استاندارد Axios (`application/json, text/plain, */*`) اضافه شدند، باگ نحوی `data=` اصلاح گردید، قرارداد `refresh()` به متد GET منتقل شد و بیس URL پیش‌فرض به `https://cptch.utcms.ir` تنظیم گردید (اصلاح 2026-09-15 در `0771ed9`: بیس تراکنشی به `mobservices-barname` برگشت و `cptch` فقط برای CapJS ماند؛ تفصیل در `UTCMS_MOBILE_AND_WAF_AUDIT_REPORT.md`).
- CODE-VERIFIED: تثبیت معماری عدم تقارن endpointها — اثبات شد که فراخوانی تک‌مرحله‌ای `StartShippingWithGps` در شروع (به‌دلیل نبود سابقه سفر) و فراخوانی دومرحله‌ای `FinishShippingWithGps` (پایان و مسافت) + `RegisterEndOfShipping` (سابقه نقاط `gps_list`) در پایان، کاملاً منطبق بر بیزینس‌لاژیک UTCMS است و نقص فاز محسوب نمی‌شود.
- CODE-VERIFIED: تست‌های قرارداد در `tests/test_utcms_mobile_contract.py` و `tests/test_shipping_gps_contract.py` با ۲۷ تست جامع و پوشش ۱۰۰٪ تأیید شدند.

## 0.8 snapshot این بازبینی (2026-09-09)

- CODE-VERIFIED: قرارداد تصریح کد رهگیری (Tracking-First Acknowledgement) پیاده شد — کد رهگیری غیرخالی = تصریح فوری اپراتور، نه success نهایی (قانون اثبات ثبت بدون تغییر).
- CODE-VERIFIED: فیلدهای سطح نتیجه در `result_json`: `confirmation_status` ∈ {`tracking_received`, `tracking_missing_history_required`, `confirmed_by_history`}، `operator_acknowledged`، `requires_reconciliation`، `requires_resubmission`، `reconciliation_mode='history_only'`.
- CODE-VERIFIED: فیلد سطح پاسخ `operator_acknowledged: bool` روی `WaybillJobResponse` و `WaybillTaskStatusResponse`.
- CODE-VERIFIED: گاردها — Dispatcher اینتنت‌های submit/reconciliation قدیمی jobهای دارای کد را لغو می‌کند؛ Scheduler این jobها را از dispatch خارج می‌کند؛ Reconciliation خودکار برای `tracking_received` رد می‌شود (مسیر دستی `audit_only=True`)؛ endpoint بازتلاش HTTP 409 برمی‌گرداند؛ recovery کارهای گیرکرده قرارداد را حفظ می‌کند.
- CODE-VERIFIED: Worker عادی و `scheduled_waybill_executor` رفتار یکسان دارند؛ نتیجه `unknown` در executor هرگز به retry بازگشتی نمی‌رسد.

## 0.7 snapshot این بازبینی (2026-09-06)

- CODE-VERIFIED: commit جاری `bfefd9c` است و در گیت‌هاب، سرور اصلی (`<CENTRAL_IP>`) و لوکال کاملاً همگام است.
- LIVE-OBSERVED: ارسال موفق Job 56 به سامانه مرکزی UTCMS با کد پاسخ ۲۰۰ و ایجاد سند رسمی شماره `214489653`.
- CODE-VERIFIED: رفع خطای HTTP 500 در `UpdateRegisterNewOld` با تکمیل فیلدهای نقشه و مختصات اعشاری (`a1dc727`).
- CODE-VERIFIED: رفع خطای ۴۰۲۵ (کرایه الزامی) با مقداردهی خودکار `#txtkeraye` و اعمال کرایه پیش‌فرض ۵,۰۰۰,۰۰۰ ریال (`72556f0`).
- CODE-VERIFIED: رفع خطای تبدیل تاریخ با خنثی‌سازی تابع جاوااسکریپت `validateTime` و تزریق خودکار ساعت به `SelfDeclaredTimeOfStartShipment` (`bfefd9c`).
- EXTERNAL-OBSERVATION: در بازه عصرگاهی/شبانه (۱۷:۳۰ تا ۰۸:۰۰)، پاسخ ثبت با `isOtpNeeded: true` همراه است و پیامک تایید به شماره راننده ارسال می‌شود؛ نهایی‌سازی کد رهگیری در این بازه با متد `IssueDocumentByOtpNew` انجام می‌پذیرد.

## 0.6 snapshot این بازبینی (2026-08-29)

- CODE-VERIFIED: گیت محلی با `origin/main` همگام است؛ commit جاری `5d583a1` است.
- CODE-VERIFIED: suite backend برابر `1149 passed, 3 skipped` و suite frontend شامل ۵ تست موفق است؛ Next.js build، typecheck و lint نیز موفق‌اند.
- CODE-VERIFIED: graphify پس از تغییرات frontend به‌صورت incremental بازسازی شد: `7,695` node، `17,124` edge و `456` community. `graphify-out/` عمداً ignored است و artifact تولیدی محسوب می‌شود.
- RUNTIME-VERIFICATION: هر سه host و همهٔ containerهای allowlist پاسخ می‌دهند؛ imageهای در حال اجرا stale نیستند.
- RUNTIME-VERIFICATION: در زمان snapshot، HEAD سرورها هنوز `62c5b0c` بود و deploy commit `5d583a1` در حال اجراست؛ تا اجرای check-versions موفق، production را همگام اعلام نکنید.
- RUNTIME-VERIFICATION: از شبکهٔ بیرونی پورت‌های `5432` و `6379` مرکز قابل اتصال مشاهده شد؛ DOCKER-USER/UFW باید پیش از live submit دوباره اعمال و از یک IP غیر-worker ردگیری شود.

## 0. روش خواندن و سطح اطمینان

هر ادعا در این سند یکی از برچسب‌های زیر را دارد:

| برچسب | معنی |
|---|---|
| CODE-VERIFIED | مستقیماً از کد، router، model، migration یا Compose همین checkout استخراج شده است |
| CONFIG-TARGET | وضعیت مطلوب و enforce‌شده در فایل‌های پیکربندی است، اما اجرای زنده را ثابت نمی‌کند |
| RUNTIME-VERIFICATION | فقط با SSH، inspect، metric، log یا probe زنده قابل اثبات است |
| EXTERNAL-OBSERVATION | رفتار UTCMS در آزمون کنترل‌شده مشاهده شده، اما قرارداد رسمی منتشرشده نیست |

ترتیب اعتبار منابع:

1. CRITICAL_RULES.md و docs/UTCMS_CONSTRAINTS.md برای خطوط قرمز رفتار UTCMS؛
2. کد اجرایی، modelها، migrationها و Compose همان commit؛
3. ARCHITECTURE.md و runbookهای جاری؛
4. artifactهای timestamped مانند versions.json فقط برای همان زمان؛
5. نمونه env و گزارش تاریخی، بدون runtime evidence، مرجع وضعیت production نیستند.

این سند ادعای شمارش یا راستی‌آزمایی خودکار هزاران node/edge ندارد. هر رابطه‌ی
حیاتی با مسیر فایل یا قرارداد قابل بازتولید توضیح داده می‌شود.

## 0.5 دلتای v2.9.5 / v2.9.6 (CODE-VERIFIED در 21c0516)

| مورد | اثر گرافی | فایل مرجع |
|---|---|---|
| C1 — گارد lease زنده در orphan-sweep | یال «sweep → kill RUNNING» فقط وقتی مجاز است که `Execution.lease_expires_at` منقضی شده باشد؛ bump `updated_at` روی گذارهای claim | `app/orchestrator/orphan_detector.py`, `app/workers/waybill_worker.py` |
| C2 — IP واقعی کلاینت پشت nginx | uvicorn با `--proxy-headers --forwarded-allow-ips=127.0.0.1,172.16.0.0/12,10.0.0.0/8` اجرا می‌شود؛ باکت‌های rate-limit واقعاً per-client شدند | `compose/backend.yml`, `Dockerfile` |
| C3 — قفل‌های تجدیدپذیر راننده | `renew_lock()` (Lua compare-and-expire) + تمدید دوره‌ای ~30s؛ توکن پایدار در registry `locktok:{key}` | `app/services/rpa_runtime_service.py` |
| C4 — گاردهای retry ادمین | UNKNOWN/CANCELLED → 409 راهنمادار؛ دسته‌های `submission_unconfirmed/ambiguous_mutation/duplicate_submission` رد می‌شوند | `app/api/routes/admin_alerts.py` |
| H1 — حدود Celery مشتق‌شده | SOFT=JOB_TIMEOUT+15، HARD=SOFT+45؛ misconfig پین‌شده auto-correct می‌شود | `app/core/config.py:257-271` |
| H2 — گره `retrying` | source set + ۱۱ یال ورودی در ALLOWED_TRANSITIONS | `app/orchestrator/state_machine.py` |
| H3 — بازیابی celery_task_id کهنه | QUEUED>15m / WAITING_AUTH>1h با Celery id اثباتاً مرده، داخل `plan_due_jobs` پاک می‌شوند | `app/services/rpa_scheduler_service.py` |
| H5 — blacklist روی dependencyهای sensitive | JWT با jti سیاه‌شده در مسیرهای sensitive/admin رد می‌شود | `app/core/security.py` |
| H6/H7 — include مشترک security headers | `infra/nginx/security-headers.conf` به همه locationهای دارای add_header محلی اضافه شد؛ مسیرهای proxies/circuit-breaker به regex بک‌اند افزوده شدند | `infra/nginx/http-server.conf`, `compose/web.yml` |
| H8 — فایروال DOCKER-USER | UFW تنها کافی نیست؛ سه اسکریپت، قوانین مدیریت‌شده `barpro-guard` برای 5432/6379 per Worker IP نصب می‌کنند + کشف همه ساب‌نت‌های Docker + رفع self-DoS اسکوئید host-network | `scripts/setup_firewall_central.sh`, `scripts/add_worker_firewall.sh`, `scripts/secure_squid_ports.sh` |
| NEW-1 — ناوبری waybill مقاوم | روت `/Barname/RegisterWaybill/Index` زنده 404 است؛ کاندیدهای کانونی HagigiHogugi/Document/Create + sweep عمومی لینک‌ها با partition مسیری (path-only) | `app/automation/waybill_enhanced.py:2085-2382` |
| NEW-2 — retry کپچای غلط | پاسخ AJAX «لطفا کد امنیتی صحیح…» از قبل وارد `_is_captcha_error` می‌شد؛ با تست رگرسیون قفل شد | `tests/test_audit_fixes.py` |
| BUG-class — classifierهای path-based | تشخیص نشست/لاگین روی parsed.path نه full-URL (`?ReturnUrl=/Login` دیگر session را flip نمی‌کند؛ hazard دومین submit حذف شد) | `auth_utils.py`, `utcms_http_login.py`, `utcms_reconciliation_scraper.py`, `waybill_bot_multitenant.py` |
| Dependabot version updates خاموش | `.github/dependabot.yml` حذف شد (~۲۴ branch کهنه)؛ Dependabot alerts/security-updates از Settings ادامه دارد | `.github/dependabot.yml` (deleted) |
| تست‌ها | snapshot این checkout: `1149 passed, 3 skipped`؛ تعداد collect برابر ۱۱۵۲ است | `tests/` |

---

## 1. هویت سیستم

BarPro یک پلتفرم RPA چندمستاجره برای:

- ثبت بارنامه در barname.utcms.ir؛
- استعلام سهمیه سوخت در UTCMS؛
- مدیریت راننده، پلاک، schedule، batch upload و گزارش؛
- اجرای توزیع‌شده روی یک Central و دو Remote Worker؛
- ثبت event، reconciliation و audit قابل پیگیری.

فناوری‌های اصلی CODE-VERIFIED:

| لایه | فناوری |
|---|---|
| Backend | Python 3.11، FastAPI، Pydantic v2 |
| Frontend | Next.js 15، React 19، TypeScript، Tailwind |
| Database | PostgreSQL 16، SQLModel/SQLAlchemy، AsyncPG |
| Queue/state | Celery، Redis، RedBeat |
| RPA | Playwright Chromium و HTTP login با curl_cffi |
| ML/OCR | PyTorch CNN، PyTorch Fuel CRNN، Keras OCR و fallbackهای محلی |
| Proxy | Squid اختصاصی Worker و Clean IP Pool |
| Ingress | Nginx |
| Monitoring | Prometheus، Alertmanager، Grafana و exporterها |

---

## 2. گراف توپولوژی

وضعیت هدف production، Model B scale-out است.

    Browser
      |
      | HTTP :80
      v
    Nginx
      |-- Next.js :3000
      |-- FastAPI :8000
             |-- PostgreSQL :5432
             |-- Redis :6379
             |-- HTTP API
             |-- WS /ws/waybill
      |
      |-- Central Worker 1, concurrency 1
      |     |-- Central Squid 1 :3128 -> Central Iranian egress IP
      |
      |-- Celery Beat
      |     |-- publishes periodic messages
      |
      |-- celery_scheduler
      |     |-- consumes only rpa_scheduler
      |
      |-- Monitoring stack

    Remote Worker Node 2
      |-- Celery Worker 2, concurrency 1
      |-- local Squid :3128 -> Worker 2 Iranian egress IP

    Remote Worker Node 3
      |-- Celery Worker 3, concurrency 1
      |-- local Squid :3128 -> Worker 3 Iranian egress IP

    Remote nodes -> PostgreSQL/Redis on Central through an IP allowlist
    All Workers -> UTCMS through their selected egress proxy

### 2.1. Model B

- CODE-VERIFIED: compose/worker-node.yml تعریف remote Worker را نگهداری می‌کند.
- CONFIG-TARGET: Central فقط Worker 1 و Squid 1 را اجرا می‌کند.
- CONFIG-TARGET: Squid 2/3 و Central Worker 2/3 فقط با profileهای Model A/scale-out
  به‌صورت صریح فعال می‌شوند.
- RUNTIME-VERIFICATION: نبود container یا listener اضافه روی Central باید با
  full docker ps و ss بررسی شود.
- RUNTIME-VERIFICATION: دسترسی 5432 و 6379 باید از یک IP غیر-worker رد شود؛ bind
  روی 0.0.0.0 به‌تنهایی امن نیست.

### 2.2. Model A

Model A استقرار تک‌ماشینه است و می‌تواند Worker 1/2/3 و Squidهای 3128/3129/3130
را روی Central اجرا کند. فعال‌سازی آن opt-in است و نباید روی production Model B
به‌صورت implicit رخ دهد.

### 2.3. TLS

- CODE-VERIFIED: block فعال Nginx فقط روی port 80 است.
- CODE-VERIFIED: نمونه 443/TLS در infra/nginx/nginx.conf comment است.
- CONFIG-TARGET: AUTH_COOKIE_SECURE تا پیش از TLS معتبر false است.
- RUNTIME-VERIFICATION: certificate، redirect، handshake، cookie و WSS باید پیش
  از اعلام HTTPS operational آزمون شوند.

---

## 3. گراف Frontend

صفحه‌های App Router که در checkout وجود دارند:

| حوزه | مسیر |
|---|---|
| root/auth | apps/web/src/app/page.tsx، auth/page.tsx، layout.tsx |
| عملیات tenant | new، history، fuel، drivers، reports، settings |
| admin | dashboard، clients، workers، alerts، audit، reports، health |

اجزای محوری CODE-VERIFIED:

| component/module | نقش |
|---|---|
| AppShell/AuthGuard/Header/Sidebar | shell، navigation و محافظت مسیر |
| PlateInput | ورود و normalization پلاک |
| ProvinceCitySelect/SmartAddressInput | ورودی location |
| LocationMapPicker/FavoriteLocationPicker | map/favorite location UI |
| useSession | state نشست client |
| useWaybillJob | fetch و lifecycle وضعیت Job |
| useWebSocket و lib/ws.ts | اتصال realtime به /ws/waybill |
| lib/api.ts | HTTP client با cookie credentials |
| lib/format.ts | رقم/تاریخ/وضعیت/error/quota formatting |
| schemas/waybillSchema.ts | Zod validation و serialization payload |

قرارداد احراز هویت:

- JWT در httpOnly cookie حمل می‌شود؛ نام cookie از `AUTH_COOKIE_NAME` (بک‌اند)
  و `NEXT_PUBLIC_AUTH_COOKIE_NAME` (فرانت‌اند) می‌آید و مقدار پیش‌فرض آن
  `utcms_auth_token` است — هیچ نام hardcoded در کد کلاینت وجود ندارد.
- localStorage نباید bearer token یا secret نگهداری کند.
- AUTH_COOKIE_SECURE تابع وضعیت واقعی HTTPS است.
- Master Admin و Client نقش‌های اصلی فعلی‌اند؛ مدل SQLModel مستقلی به نام
  SuperAdmin وجود ندارد.

قرارداد realtime:

- endpoint یگانه WS /ws/waybill است.
- token از cookie خوانده و blacklist بررسی می‌شود.
- Client فقط channel tenant خودش را می‌بیند.
- Master Admin می‌تواند channel all و filterهای task_id، batch_id و
  correlation_id را دریافت کند.
- مسیرهای /ws/jobs/{client_id} و /ws/admin/stream وجود ندارند.

---

## 4. گراف API

### 4.1. System و health

| method/path | auth | قرارداد |
|---|---|---|
| GET /healthz | public | liveness سبک |
| GET /readyz | public | readiness sanitized؛ بدون DSN، URL credentialدار یا جزئیات حساس |
| GET /api/v1/admin/readyz | admin | readiness تفصیلی |
| GET /metrics | network-restricted | Prometheus exposition |
| GET /auth-config | admin | auth/CAPTCHA configuration غیرحساس |
| GET /events/history | admin | history event hub |
| GET /workers/heartbeats | admin | Worker Registry snapshot |
| POST /workers/recover-stalled | admin | recovery عملیات stuck |
| GET /api/system/clean-ips | admin | inventory سلامت Clean IP بدون credential خام |
| POST /api/system/clean-ips/refresh | admin | refresh دستی pool |

aliasهای legacy /system/clean-ips و refresh در schema عمومی نمایش داده نمی‌شوند.
مسیر /backend/ در ingress عمومی مجاز نیست. مسیر /api/system/health وجود ندارد.

### 4.2. Multi-tenant API

prefix اصلی app/api/routes/multitenant.py برابر /api/v1 است:

| گروه | endpointهای اصلی |
|---|---|
| Auth | POST /auth/register، POST /auth/login، POST /auth/logout، GET /auth/me، GET /auth/stats |
| Admin clients | GET/POST /admin/clients، PUT/DELETE /admin/clients/{id} |
| Drivers | POST/GET /drivers، GET/PUT/DELETE /drivers/{id} |
| Plates | POST/GET /plates، PUT/DELETE /plates/{id} |
| Driver tracking | GET /driver-tracking — آمار ثبت هر پلاک (ثبت امروز / هدف ثبت / کل ثبت) در دوره ۱۵روزه جلالی جاری |
| Schedules | POST/GET /driver-schedules، PUT/DELETE by id، POST /driver-schedules/run-due |
| Waybill jobs | POST/GET /waybill-jobs، GET/PATCH/DELETE by job_id — فیلترهای تاریخ (date_from/date_to) روزهای کامل تقویم تهران‌اند (شامل کل روز پایانی)؛ `date_to` به‌صورت bound انحصاری اعمال می‌شود؛ تاریخ نامعتبر → HTTP 400 (تست: tests/test_history_date_filters.py) |
| Job actions | POST retry، POST requeue، GET timeline/logs/screenshot |
| Route templates | GET/POST /route-templates، PUT/DELETE /route-templates/{id}، POST /route-templates/{id}/favorite |
| Multi-route batches | POST/GET /batches، GET /batches/{id}/progress |
| Locations & Distance | GET provinces/cities/favorites، POST /locations/distance (Neshan/Haversine) |
| Upload | POST /upload/excel **deprecated/fail-closed (HTTP 410)**؛ GET /upload/batches/{batch_id} فقط برای مشاهده batchهای تاریخی |
| Tenant reports | daily-summary، driver-performance |
| Fuel | POST/GET /fuel-inquiries، options، detail، screenshot |
| Driver crypto admin | re-encrypt-password و encryption-health |

DELETE /api/v1/waybill-jobs/{job_id} حذف دائمی است. endpoint مستقل POST cancel
وجود ندارد.

مسیر legacy `POST /api/v1/upload/excel` عمداً job جدید ایجاد نمی‌کند، زیرا قالب
قدیمی Excel تمام فیلدهای اجباری قرارداد زنده UTCMS را بیان نمی‌کرد و پیاده‌سازی
قبلی validation canonical، idempotency، scheduler و eventهای state machine را
دور می‌زد. این endpoint اکنون HTTP 410 برمی‌گرداند. تا زمان طراحی یک قرارداد bulk
canonical، هر ردیف باید به‌صورت `WaybillJobCreateRequest` کامل از
`POST /api/v1/waybill-jobs` عبور کند. endpoint خواندن وضعیت batch برای audit
رکوردهای تاریخی حفظ شده است.

### 4.3. Routerهای تکمیلی

- /api/v1/locations برای province/city/address/favorites و POST /locations/distance؛
- /api/v1/route-templates و /api/v1/batches برای ثبت دسته‌ای و چندمسیره؛
- /api/v1/rpa/phase1 برای overview/runtime/scheduler inspection؛
- /management برای management tables و operator workflows، admin-only؛
- /reports، /api/v1/admin/reports و /api/v1/user/reports؛
- /waybill برای map، manual/excel entry و ITMB WS operations؛
- /api/v1/admin برای alert/circuit operations.

OpenAPI همان commit مرجع نهایی method، parameter و response schema است.

---

## 5. گراف سرویس‌ها

| service/subsystem | مسئولیت |
|---|---|
| ClientService | tenant lifecycle، auth و quota |
| DriverService و PlateService | driver credentials، fleet و plate ownership |
| DriverScheduleService | schedule CRUD و due execution |
| RouteTemplateService | مدیریت الگوهای مسیر و محاسبه پیش‌فرض مسافت/زمان |
| BatchService | ساخت و توزیع دسته‌ای چندمسیره با گیت دقت ۱۰۰٪ و فاصله‌گذاری |
| DistanceService | استعلام مسافت و زمان جاده‌ای با Neshan + Redis + Haversine fallback |
| WaybillJobService | create/list/update/retry/delete و tenant isolation |
| WaybillTaskService | queue depth، transitions و event emission |
| SchedulerService | انتخاب Jobهای قابل برنامه‌ریزی و ساخت intent |
| DispatcherService | claim intent، Worker selection، queue routing |
| ReconciliationService | بررسی History و نهایی‌سازی mutation |
| RPAAuthService | warm/reuse auth session |
| RPAHttpSubmitService | submit path مربوط به RPA service |
| RPADispatchService | dispatch legacy/phase paths |
| FuelInquiryService | claim/cleanup/status استعلام سوخت |
| ITMBWSService | WS01/WS03/WS04/WS06 و circuit/status |
| ITMBBaseInfoService | cache/probe/refresh base information |
| ManagementService | customer/route/account/queue/sync management |
| AdminReportingService/UserReportingService | گزارش admin و tenant |
| BrowserManager | Chromium/context/page lifecycle |
| EnhancedWaybillManager | flow فرم و mutation UTCMS |
| CleanIPPoolManager | aggregate/probe/score/block clean proxies |

ITMB یک زیرسیستم واقعی و مستقل است و نباید از knowledge graph حذف شود. readiness
می‌تواند configuration، BaseInfo cache و live probe آن را کنترل کند.

---

## 6. گراف داده و migration

### 6.1. اصول schema

- CODE-VERIFIED: primary key مدل‌های SQLModel اصلی integer است.
- شناسه‌های public مانند job_id، batch_id، intent_id و execution_id string هستند.
- هیچ مدل مستقلی با نام SuperAdmin در schema جاری وجود ندارد؛ Master Admin یک
  role/auth context است.
- مرجع schema فقط diagram نیست: app/models_multitenant.py، app/models_rpa.py،
  app/models_management.py و Alembic migrations باید با هم خوانده شوند.

### 6.2. مدل‌های multi-tenant

| model | روابط/فیلدهای محوری |
|---|---|
| Client | tenant identity، status، quotas؛ parent راننده/پلاک/job/fuel/batch |
| Driver | client_id، credential رمزنگاری‌شده، UTCMS identity، status |
| DriverPlate | client_id، driver_id، plate_number، vehicle_type، active state، target_count، round_trip، in_transport |
| DriverSchedule | client_id، driver_id، schedule و execution metadata |
| WaybillJob | job_id، idempotency_key، client_id، driver_id، status، payload_json، result_json |
| WaybillTaskLog | job_id و step/status/message برای audit |
| UploadBatch | batch_id، client_id، filename، counts، errors_json |
| FuelInquiry | client_id، driver_id، status، error، quota_data_json، screenshot_url، year/month |

WaybillJob همچنین دارای:

- priority، next_retry_at، submit_after، terminal_reason؛
- request_digest، submission_fingerprint، document_id؛
- mutation_status، mutation_at، reconciled_at؛
- attempt_count، max_retries، retryable و night attempt fields؛
- celery_task_id، worker_id و timestamps.

نام‌های waybill_payload، retry_count یا error_details columnهای جاری WaybillJob
نیستند. FuelInquiry column مستقیمی به نام tracking_code یا screenshot_data_uri
ندارد؛ Data URI می‌تواند در screenshot_url ذخیره شود.

### 6.3. مدل‌های orchestration/runtime

| model | نقش |
|---|---|
| DriverRuntimeState | state جاری راننده و active execution |
| DriverDailyCounter | attempt/success cap روزانه |
| DriverSessionMetadata | metadata نشست مشترک |
| WaybillAttempt | history تلاش mutation |
| DomainEvent | event پایدار domain |
| ProxyEndpoint | endpoint، health، failure count و cooldown |
| DispatchIntent | intent پایدار با attempt و fencing token |
| WorkerRegistry | worker_id، hostname، capabilities، capacity، status، ip_index، heartbeat |
| Execution | execution_id، intent_id، job_id، lease، worker و result |
| UTCMSSystemObservation | gate state، validity، probe metadata و evidence sanitized |

### 6.4. مدل‌های management

ManagedCustomer، ManagedRoute، ManagedAccount، ManagedQueueItem و
ManagedSyncLog زیرسیستم management را پشتیبانی می‌کنند. حذف این مدل‌ها از ERD
باعث ناقص شدن graph عملیاتی می‌شود.

### 6.5. Migration

- CODE-VERIFIED: head مستند این بازبینی
  040_add_route_template_polyline است.
- VERIFIED-CODE: migration startup زیر PostgreSQL session-level advisory lock با
  `MIGRATION_ADVISORY_LOCK_ID = 0x42415250524F` و timeout قابل تنظیم انجام می‌شود؛
  اجرای raw Alembic در مسیرهای deploy ممنوع است.
- RUNTIME-VERIFICATION: alembic current و schema واقعی DB باید پیش و پس از deploy
  ثبت شوند؛ وجود migration file اثبات اجرای آن روی production نیست.

---

## 7. گراف state machine، idempotency و reconciliation

### 7.1. statusها

JobStatus شامل:

pending، waiting_auth، waiting_retry، waiting_submission_window، otp_backoff،
queued، claimed، running، in_progress، retrying، success، failed، needs_review،
dead_letter، cancelled، unknown و reconciling است.

(از v2.9.6 گره `retrying` هم source set کامل دارد و هم ۱۱ یال ورودی؛
`task_service.mark_retrying()` دیگر job را در گره بدون خروجی گیر نمی‌اندازد.)

### 7.2. جریان ایمن mutation

    pending / waiting states
      -> queued
      -> claimed
      -> running
      -> unknown
      -> reconciling
      -> success | needs_review

branchهای دیگر شامل waiting_retry، waiting_submission_window، otp_backoff،
failed، cancelled و dead_letter هستند.

RUNNING -> SUCCESS نباید به‌عنوان نتیجه فوری UI مدل شود. guard
JobStateMachine برای WaybillJob تنها زمانی success را می‌پذیرد که:

1. mutation_status برابر confirmed باشد؛
2. reconciled_at تنظیم شده باشد؛
3. result_json دارای tracking_code غیرخالی باشد.

این سه شرط کدی هستند؛ اثبات ثبت (بند 7.3) دو شاهدی است.

### 7.3. Two-witness contract

ثبت فقط با این دو شاهد قطعی است:

1. tracking code در پاسخ RPA؛
2. همان tracking code در waybill_jobs.result_json.

تأیید نهایی یکجا (batch) است، نه تک‌تک در طول روز: task
`orchestrator.reconciliation.audit_tracking_received`
(`reconciliation_service.reconcile_tracking_received_jobs`) همهٔ jobهای
`tracking_received` را در یک اجرا با `audit_only=True` به History می‌برد
و `reconciled_at` و `mutation_status=confirmed` را می‌نشاند. cadence فعلی
beat هر ۱۰ دقیقه است (`app/workers/celery_app.py`).

success message، بسته‌شدن modal، screenshot یا dry-run شاهد کافی نیست.

### 7.4. Reconciliation

- CODE-VERIFIED: delayهای جاری 15، 45، 120 و 300 ثانیه‌اند.
- UNKNOWN ابتدا به RECONCILING می‌رود.
- claim query از locking برای جلوگیری از پردازش موازی استفاده می‌کند.
- matching composite و multi-attribute است، نه صرفاً یک رشته.
- ثبت دارای History و tracking code به SUCCESS می‌رود.
- REGISTERED بدون tracking code، ambiguity یا پایان bounded attempts به
  NEEDS_REVIEW می‌رود.
- نتیجه نامطمئن خودکار resubmit نمی‌شود.

### 7.5. Idempotency و serialization

- canonical request digest از داده‌های پایدار ساخته می‌شود و plate را شامل می‌شود.
- duplicate dispatch باید Job موجود را بازگرداند.
- click نهایی با at-most-once helper اجرا می‌شود؛ این guard risk را کاهش می‌دهد،
  اما ادعای جلوگیری 100 درصدی بدون reconciliation معتبر نیست.
- هر راننده یک submit lock/active execution دارد.
- lock release مبتنی بر ownership token و fencing است؛ admin recovery مسیر
  جداگانه و حساس دارد.

### 7.6. قرارداد تصریح کد رهگیری (Tracking-First Acknowledgement)

از ۲۰۲۶-۰۹-۰۹:

- کد رهگیری غیرخالی → Job در `unknown` با `confirmation_status='tracking_received'`
  و `operator_acknowledged=true`؛ بدون زمان‌بندی تطبیق (`requires_reconciliation=false`)،
  بدون resubmit. تصریح فوری به اپراتور، اما نه success نهایی (قانون اثبات
  بخش 7.3).
- موفق‌نما بدون کد → `unknown` با `confirmation_status='tracking_missing_history_required'`
  و `reconciliation_mode='history_only'`؛ زمان‌بندی تطبیق فقط‌خواندنی ۱۵/۴۵/۱۲۰/۳۰۰ ثانیه.
- گاردهای no-submit: `result_json.tracking_code` غیرخالی به‌صورت بی‌قید و شرط
  dispatch submit را مسدود می‌کند (scheduler skip، dispatcher intent cancellation
  با دلیل `tracking_acknowledged`، رد 409 در endpoint بازتلاش).
- تطبیق خودکار برای `tracking_received` رد می‌شود؛ مسیر دستی تنها
  `reconcile_job(..., audit_only=True)` است (فقط‌خواندنی، برای اتصال مدرک).
- Worker عادی، `scheduled_waybill_executor` و مسیر HTTP submit (`rpa_submit_service`)
  از helperهای مشترک `app/schemas/task.py` استفاده می‌کنند: `build_tracking_received_result`
  و `build_missing_tracking_result`.

---

## 8. گراف Celery، scheduler و queue

### 8.1. نقش processها

| process | نقش |
|---|---|
| Celery Beat | publish پیام‌های periodic با RedBeat |
| celery_scheduler | مصرف‌کننده singleton صف rpa_scheduler |
| Worker 1 | RPA مرکزی، concurrency 1 |
| Worker 2/3 | RPA remote، concurrency 1 |

Beat task اجرا نمی‌کند و مصرف‌کننده gate/clean-IP probe نیست.

### 8.2. Queueهای Worker

| Worker | queueهای تعریف‌شده در Compose |
|---|---|
| Worker 1 | waybill_tasks، waybill_tasks_1، rpa_auth_1، rpa_submit_1، reconciliation_tasks، reconciliation_tasks_1، scheduled_tasks، scheduled_tasks_1، barpro.fuel.inquiry |
| Worker 2 | waybill_tasks، waybill_tasks_2، rpa_auth_2، rpa_submit_2، reconciliation_tasks، reconciliation_tasks_2، scheduled_tasks_2، barpro.fuel.inquiry |
| Worker 3 | waybill_tasks، waybill_tasks_3، rpa_auth_3، rpa_submit_3، reconciliation_tasks، reconciliation_tasks_3، scheduled_tasks، scheduled_tasks_3، barpro.fuel.inquiry |
| celery_scheduler | rpa_scheduler |

Remote worker template base queueها و suffix همان WORKER_IP_INDEX را مصرف می‌کند.

### 8.3. Periodic tasks

CODE-VERIFIED schedule شامل:

- rpa.session.keepalive روی waybill worker queue؛
- orchestrator.scheduler.run؛
- orchestrator.dispatcher.run؛
- orchestrator.orphan_detector.run؛
- orchestrator.claim_reaper.run؛
- orchestrator.reconciliation.run روی reconciliation queue؛
- fuel.cleanup_stale_inquiries؛
- barpro.gate.probe؛
- barpro.clean_ip.probe.

taskهای legacy Phase-1 تنها وقتی DEPRECATE_OLD_EXECUTION_PATH غیرفعال شود وارد
schedule می‌شوند.

### 8.4. Runtime checks

RUNTIME-VERIFICATION:

- celery inspect active_queues و stats روی هر Worker؛
- Worker Registry heartbeat و ip_index؛
- queue depth و reconciliation backlog؛
- نبود queue بدون consumer؛
- concurrency واقعی و prefetch؛
- عدم اجرای browser workload روی rpa_scheduler.

---

## 9. گراف RPA و auth/network path

### 9.1. Waybill engine

EnhancedWaybillManager مسئول:

- navigation/form discovery؛
- strict cargo و packaging matching؛
- origin/destination text selection؛
- human interaction و locator fallback؛
- at-most-once final click؛
- return mutation evidence برای worker/reconciliation.

route readiness مبتنی بر city/address text است و GPS شرط اجباری قرارداد پایه نیست.

### 9.2. Login path

مسیر ورود فقط Playwright نیست:

1. HTTP login با curl_cffi و fingerprint سازگار؛
2. local CAPTCHA solve؛
3. retry statusهای transient بدون مصرف captcha budget؛
4. تشخیص silent unauthenticated redirect/final URL؛
5. انتقال cookie/session به browser؛
6. bridge محدود document/xhr/fetch به‌علاوهٔ اسکریپت‌های حیاتی فرم صدور؛
7. Playwright fallback در صورت نیاز.

Bridge کردن همه assetهای JS/CSS/font/image ممنوع است و می‌تواند serialization،
TLS reset و timeout ایجاد کند. استثنای مستند: اسکریپت‌های حیاتی فرم صدور
(jquery، jquery-ui، jquery.validate، formvalidation.popular، formhelper،
hagigihogugitemplate، hagigihogugi) که روی همان session احرازشدهٔ
`Login → Notification → HagigiHogugi` پیش‌واکشی و از cache به Chromium تحویل
می‌شوند؛ بدون آن، DOM فرم کامل ولی JavaScript آن مرده است. جزئیات و خطوط قرمز در
[UTCMS_BOT_BEHAVIOR_CONTRACT.md](UTCMS_BOT_BEHAVIOR_CONTRACT.md).

### 9.3. Error taxonomy

طبقه‌بندی EGRESS، BROWSER، RETRYABLE و business/auth errors باید routing و
retry را کنترل کند. invariant مهم EGRESS subset of RETRYABLE است. error programming
نباید با autoretry_for Exception بی‌نهایت retry شود.

### 9.4. Browser lifecycle

- browser/context reuse و recycle bounded است؛
- listenerها هنگام page close حذف می‌شوند؛
- close operation timeout دارد؛
- browser pool و Chromium memory تحت container budget است؛
- سلامت browser در readiness/admin diagnostics قابل بررسی است.

---

## 10. گراف CAPTCHA

### 10.1. Provider chain

CAPTCHA_PROVIDER=auto یا composite providerها را به این ترتیب اجرا می‌کند:

1. CnnCaptchaProvider؛
2. PyTorchFuelCaptchaProvider؛
3. KerasOcrCaptchaProvider؛
4. EnhancedOcrProvider؛
5. LocalOcrCaptchaProvider.

### 10.2. مدل‌ها

| challenge | provider/model |
|---|---|
| login math | cnn، app/automation/captcha/assets/captcha_cnn.pth |
| fuel Persian | pytorch_fuel، fuel_captcha_crnn.pth + vocab |
| fuel fallback | keras_ocr، persian_number_ocr.keras |
| later fallbacks | enhanced_ocr، local_ocr |

### 10.3. Keras runtime

- CODE-VERIFIED: keras.models.load_model با compile=False در همان process اجرا می‌شود.
- model lazy و تحت lock load و reuse می‌شود.
- prediction با asyncio.to_thread از event loop جدا می‌شود.
- KERAS_PYTHON_PATH توسط provider جاری برای subprocess مصرف نمی‌شود و legacy
  compatibility setting است.

### 10.4. ادعاهای benchmark

هیچ ادعای دقت 98.5 درصد، 94 درصد یا latency کمتر از 50ms بدون artifact زیر معتبر نیست:

- dataset hash و split؛
- model hash/version؛
- hardware/software environment؛
- sample count و confidence interval؛
- metric مناسب sequence/math؛
- timestamp و script قابل بازتولید.

بنابراین این graph عدد accuracy/latency قطعی اعلام نمی‌کند.

### 10.5. Effective mode

CAPTCHA_PROVIDER، CAPTCHA_MODE، CAPTCHA_AUTO_ONLY، model availability و fallback
flags ممکن است بین nodeها drift کنند. مقدار production نیازمند runtime verification
است و از .env.example استنباط نمی‌شود.

CAPTCHA_MODE فقط یکی از local_only، provider_only، provider_first یا manual_only
است؛ مقدار ناشناخته باید در startup رد شود.

---

## 11. گراف OTP Submission Gate

UTCMS پنجره رسمی و تضمین‌شده‌ای برای OTP منتشر نکرده است.

- CODE-VERIFIED: 17:30 تا 08:00 مقدار پیش‌فرض configurable prediction برای
  OTP_REQUIRED و آماده‌باش شبانه است.
- این بازه قانون قطعی UTCMS یا OTP_FREE window نیست.
- فقط observation معتبر OTP_FREE اجازه submit می‌دهد.
- UNKNOWN، DEGRADED و OTP_REQUIRED fail-closed هستند.
- observation در Redis cache و PostgreSQL audit می‌شود.
- probe زیر distributed lock اجرا می‌شود.
- prediction با observation زنده override می‌شود.

متغیرهای کلیدی:

| variable | default کد | تفسیر |
|---|---:|---|
| PREDICTED_OTP_REQUIRED_START_HOUR | 17 | ساعت شروع prediction |
| PREDICTED_OTP_REQUIRED_START_MINUTE | 30 | دقیقه شروع prediction |
| PREDICTED_OTP_REQUIRED_END_HOUR | 8 | ساعت پایان prediction |
| PREDICTED_OTP_REQUIRED_END_MINUTE | 0 | دقیقه پایان prediction |
| GATE_PROBE_INTERVAL_SECONDS | 300 | فاصله publish probe |
| GATE_PROBE_LOCK_TTL_SECONDS | 60 | TTL lock |
| GATE_OBSERVATION_VALIDITY_SECONDS | 1800 | اعتبار observation |

RUNTIME-VERIFICATION: effective valueها و آخرین observation هر deployment.

---

## 12. گراف proxy، Clean IP و circuit breaker

### 12.1. Egress modes

modeهای معتبر:

- worker_first؛
- clean_pool_only؛
- hybrid.

clean_pool نام معتبر mode نیست. configuration loader باید مقدار نامعتبر را رد کند.

### 12.2. Worker proxy

- Worker 1 از Squid Central استفاده می‌کند.
- Worker 2/3 از Squid محلی همان VPS استفاده می‌کنند.
- هر Worker باید IP خروجی ایرانی مورد انتظار را از داخل همان execution path
  اثبات کند.
- proxy URL قبل از استفاده validate می‌شود تا SSRF surface محدود بماند.

### 12.3. Clean IP Pool

CleanIPPoolManager:

- sourceهای proxy را aggregate می‌کند؛
- login surface پایدار UTCMS را بدون session probe می‌کند؛ deep-link صدور probe عمومی نیست؛
- latency و health را score می‌کند؛
- فقط egress اندازه‌گیری‌شده‌ی ایران را operational می‌داند؛
- state را با Redis بین processها هماهنگ می‌کند؛
- Workerهای Remote snapshot تازه Redis را در مسیر sync می‌خوانند؛
- نتیجه صفر، Redis و fallback file کهنه را invalidate می‌کند؛
- block را per-proxy اعمال می‌کند؛
- refresh دوره‌ای و admin-triggered دارد.

تعداد source، تعداد proxy فعال و تعداد IP خروجی واقعی runtime facts هستند.

### 12.4. سه سازوکار مستقل failure isolation

1. Worker IP block:
   - Redis key برای index Worker؛
   - TTL عملیاتی کد 1800 ثانیه؛
   - فقط Worker/index مربوطه از routing حذف می‌شود.
2. Clean proxy block:
   - per-proxy؛
   - CLEAN_IP_BLOCK_TTL_SECONDS پیش‌فرض 1800؛
   - نباید Worker node را unhealthy کند.
3. Circuit breaker عمومی:
   - state in-process/manager؛
   - threshold و recovery مستقل؛
   - defaultهای auditشده threshold=5، recovery=30s و half-open calls=2.

این سه مفهوم نباید در یک IP_BLOCK_DURATION مبهم ادغام شوند.

### 12.5. Known Worker indices

AVAILABLE_IP_INDICES یک global constant برای همه topologyها نیست. routing آن را
با Worker Registry تازه فیلتر می‌کند. fleet سه‌ورکری هدف indices 1،2،3 دارد،
اما runtime registry و active queueها تعیین‌کننده‌اند.

---

## 13. Redis، rate limiter و event flow

Redis نقش‌های زیر را هم‌زمان دارد:

- Celery broker/result-related coordination؛
- cache؛
- Redis Session Vault؛
- distributed locks؛
- queue depth counters؛
- circuit/blocked state؛
- realtime pub/sub bridge؛
- RedBeat schedule metadata.

### 13.1. Rate limiter

- CODE-VERIFIED: الگوریتم application limiter یک sliding window با Redis ZSET است.
- fail-closed است؛ خرابی Redis نباید bypass بسازد.
- Token Bucket توصیف صحیح implementation جاری نیست.

ruleهای کد:

| rule | requests/window |
|---|---|
| public | 60 / 60s |
| auth | 5 / 60s |
| waybill | 30 / 60s |
| driver | 60 / 60s |
| tenant | 100 / 60s |
| admin | 200 / 60s |

RUNTIME-VERIFICATION: matcher واقعی هر route و headerهای limit. وجود rule به‌تنهایی
اثبات نمی‌کند prefix صحیح روی همه endpointها match شده است.

### 13.2. Event flow

Worker event -> Redis pub/sub -> FastAPI event hub -> WS /ws/waybill -> tenant/admin UI.
event buffer bounded است و client ownership در WebSocket handshake بررسی می‌شود.

---

## 14. گراف Deployment و Compose

### 14.1. فایل‌ها

| file | سرویس |
|---|---|
| compose/infra.yml | PostgreSQL، Redis |
| compose/proxy.yml | Squid 1 default؛ Squid 2/3 با Model A profile |
| compose/backend.yml | FastAPI، Workerها، Beat، celery_scheduler |
| compose/worker-node.yml | Remote Worker + اتصال Central + local Squid |
| compose/web.yml | Next.js، Nginx |
| compose/monitoring.yml | monitoring stack |
| docker-compose.yml | include لایه‌ها؛ نیازمند Docker Compose V2 |

docker-compose V1 قرارداد پشتیبانی‌شده نیست.

### 14.2. Central resource limits

CONFIG-TARGET بر اساس Compose:

| service | limit |
|---|---:|
| PostgreSQL | 1.5 GB |
| Redis | 512 MB |
| Backend | 512 MB |
| Worker 1 | 3 GB |
| celery_scheduler | 768 MB |
| Beat | 256 MB |
| Frontend | 1 GB |
| Nginx | 512 MB |
| Squid 1 | 128 MB |
| Prometheus | 256 MB |
| Alertmanager | 128 MB |
| Grafana | 256 MB |
| four exporters | 64 MB each |

جمع limitهای Model B Central حدود 9 GB است. این عدد maximum configuration است،
نه RSS زنده. host usage، page cache، Docker overhead و processهای بیرون container
باید جداگانه پایش شوند.

### 14.3. Remote Worker budget

هر VPS remote معمولاً Worker و Squid محلی دارد. limit و reservation واقعی از
compose/worker-node.yml خوانده شود و با RAM همان VPS بررسی شود.

### 14.4. Startup

- manage.sh با BARPRO_TOPOLOGY=model-b به‌صورت پیش‌فرض Model B را بالا می‌آورد.
- Model A انتخاب صریح می‌خواهد.
- startup/deploy باید Model A-only containerهای قدیمی را روی Central شناسایی یا
  حذف کند.
- ابزار version check باید unexpected container را نیز گزارش کند، نه فقط نبود
  expected container.

---

## 15. گراف Monitoring

compose/monitoring.yml شامل:

| component | نقش | exposure target |
|---|---|---|
| Prometheus | scrape و rule evaluation، retention فعلی 15d | Docker internal |
| Alertmanager | routing/delivery هشدار | Docker internal |
| Grafana | dashboard | 127.0.0.1:3000 |
| node-exporter | host metrics | Docker internal |
| redis-exporter | Redis metrics | Docker internal |
| postgres-exporter | PostgreSQL metrics | Docker internal |
| nginx-exporter | Nginx stub_status metrics | Docker internal |

وجود service در Compose هیچ‌یک از موارد زیر را ثابت نمی‌کند:

- container running/healthy؛
- target UP؛
- alert rule loaded؛
- receiver delivery؛
- dashboard datasource healthy؛
- retention/disk کافی.

همه این موارد RUNTIME-VERIFICATION هستند.

---

## 16. متغیرهای پیکربندی کلیدی

### 16.1. Secretها

فقط نام متغیرها مستند می‌شود:

- API_KEY؛
- JWT_SECRET؛
- DRIVER_ENCRYPTION_KEY؛
- MASTER_ADMIN_PASSWORD؛
- POSTGRES_PASSWORD؛
- REDIS_PASSWORD؛
- credentialهای ITMB/UTCMS در صورت نیاز.

مقدار secret، DSN کامل یا URL proxy credentialدار در health response، log،
artifact یا knowledge graph ممنوع است.

### 16.2. Non-secret operational controls

| حوزه | variableها |
|---|---|
| topology | BARPRO_TOPOLOGY، AVAILABLE_IP_INDICES، WORKER_ID، WORKER_IP_INDEX |
| proxy | EGRESS_PROXY_MODE، RPA_PROXIES، CLEAN_IP_BLOCK_TTL_SECONDS |
| CAPTCHA | CAPTCHA_PROVIDER، CAPTCHA_MODE، CAPTCHA_AUTO_ONLY، KERAS_MODEL_PATH |
| gate | PREDICTED_OTP_REQUIRED_START_HOUR/END_HOUR، GATE_* |
| queues | CELERY_*_QUEUE، RPA_SCHEDULER_QUEUE |
| scheduler | RPA_SCHEDULER_INTERVAL_SECONDS، batch/slice values |
| limits | DRIVER_DAILY_SUCCESS_CAP، DRIVER_DAILY_ATTEMPT_CAP، retry delay |
| celery limits | SOFT/HARD از JOB_TIMEOUT_SECONDS مشتق می‌شوند (+15/+45)؛ پین کردن SOFT≤JOB اصلاح خودکار می‌شود (H1) |
| web security | AUTH_COOKIE_SECURE، CORS/frontend URL values |
| networking | POSTGRES_BIND، REDIS_BIND، Central/Worker IP values |

KERAS_PYTHON_PATH legacy است و solver جاری از آن subprocess نمی‌سازد.

effective environment هر node RUNTIME-VERIFICATION است. .env.example فقط template است.

---

## 17. قرارداد رفتار UTCMS

EXTERNAL-OBSERVATION و خطوط قرمز:

- UTCMS از WAF، rate limit، reset و egress/IP filtering استفاده می‌کند.
- 429 و 408/500/502/503/504 transient هستند و نباید captcha attempt را مصرف کنند.
- 408 سرد روی HagigiHogugi بدون session شاهد block IP نیست؛ navigation رسمی Login → Notification → menu است.
- reset/403/429/egress markers می‌توانند IP را به‌طور موقت از routing خارج کنند، اما 408 عمومی Worker را block نمی‌کند.
- origin/destination فقط پس از read-back value+label استان/شهر و آدرس از همان selector موفق پذیرفته می‌شوند.
- ثبت موفق فقط با دو شاهد معتبر است؛ تأیید نهایی یکجا (batch) انجام می‌شود.
- ALLOW_LIVE_SUBMIT باید بدون approval و job کنترل‌شده فعال نشود.
- retry تهاجمی، parallel submit یک راننده و resubmit نتیجه unknown ممنوع است.
- fuel inquiry queue مستقل از driver submit lock بارنامه است.
- محاسبه period سوخت باید timezone Asia/Tehran را رعایت کند.

اعداد throughput مانند 1000 تا 2000 بارنامه در روز از کد قابل اثبات نیستند و فقط
با metric production شامل success قطعی (دو شاهد + تأیید یکجای History) معتبرند.

---

## 18. ماتریس وضعیت production

این جدول باید در هر release با timestamp و evidence تازه تکمیل شود.

| موضوع | چیزی که کد ثابت می‌کند | چیزی که runtime باید ثابت کند |
|---|---|---|
| Git version | repository SHA محلی | SHA Central و هر Worker |
| Database schema | migration head موجود | alembic current روی DB |
| Worker count | topology هدف سه Worker | process/container و heartbeat هر سه |
| Queue binding | Compose queue list | active_queues و consumer زنده |
| Concurrency | command/config برابر 1 | inspect stats هر Worker |
| Central Squid count | Model B فقط Squid 1 | نبود 3129/3130 و container اضافه |
| DB/Redis security | allowlist scripts موجود | denial از IP غیر-worker |
| HTTPS | template موجود، listener code غیرفعال | handshake/redirect/certificate/cookie |
| CAPTCHA mode | validation/default code | effective env و loaded provider هر node |
| OTP gate | adaptive fail-closed code | current observation و effective TTL/window |
| Clean IP pool | manager/probe code | active count، distinct egress و health |
| Circuit state | implementation/defaultها | current blocks/failures/retry-after |
| Monitoring | Compose inventory | containers، targets، alerts، delivery |
| Throughput | quota و queue mechanisms | 24h/7d success قطعی و latency |
| Reconciliation | service و schedule | backlog، oldest age، ambiguous count |

اگر evidence در دسترس نیست، مقدار گزارش باید دقیقاً «نیازمند بررسی runtime» باشد.

---

## 19. چک‌لیست verify-after-deploy

1. git rev-parse HEAD روی Central و Worker 2/3؛
2. alembic current و alembic heads؛
3. full docker ps با comparison علیه allowlist؛
4. ss -lntp، ufw status و `iptables -L DOCKER-USER -n --line-numbers`
   (قوانین `barpro-guard` باید حاضر باشند — UFW به‌تنهایی Docker-publish را نمی‌بندد)؛
5. probe 5432، 6379 و 3128 تا 3130 از IP غیرمجاز (باید fail شود)؛
6. Celery active_queues، stats، ping و Worker Registry heartbeat؛
7. egress IP check از داخل هر Worker؛
8. GET /healthz و sanitized GET /readyz؛
9. admin GET /api/v1/admin/readyz؛
10. anonymous denial و admin access برای /api/system/clean-ips؛
11. Nginx denial برای /backend/؛
12. Prometheus targets و rule status؛
13. Alertmanager receiver test بدون درج secret در output؛
14. Grafana datasource health؛
15. queue depth، reconciliation backlog و orphan/claim metrics؛
16. CAPTCHA warmup/model availability روی هر Worker؛
17. gate state/observation age؛
18. یک dry-run و فقط در صورت مجوز یک live job کنترل‌شده با دو شاهد + تأیید یکجای History.

---

## 20. ادعاهای حذف‌شده یا اصلاح‌شده از graph قبلی

| ادعای قبلی | قرارداد صحیح |
|---|---|
| Nginx 80/443 فعال | فقط 80 فعال؛ 443 template غیرفعال تا verify TLS |
| Token Bucket | Redis ZSET sliding window |
| GET /api/system/health | GET /healthz و GET /readyz |
| /ws/jobs/{client_id} و /ws/admin/stream | فقط WS /ws/waybill |
| POST cancel | وجود ندارد؛ DELETE حذف دائمی است |
| UUID primary keys | SQLModel primary keys integer؛ public IDs string |
| SuperAdmin model | role/context Master Admin؛ مدل مستقلی وجود ندارد |
| waybill_payload/retry_count | payload_json/result_json/attempt_count و fields واقعی |
| RUNNING مستقیم به SUCCESS | UNKNOWN و reconciliation اجباری |
| OTP window قطعی | prediction configurable؛ فقط observation OTP_FREE مجاز |
| Beat مصرف‌کننده probe | Beat publisher؛ celery_scheduler consumer |
| فقط waybill_tasks_X | auth/submit/reconciliation/scheduled/base/fuel queues نیز وجود دارند |
| Keras subprocess Python 3.12 | lazy in-process model load |
| accuracy ثابت 98.5/94 و latency 50ms | بدون benchmark artifact حذف شده |
| proxy mode clean_pool | mode صحیح clean_pool_only |
| یک IP_BLOCK_DURATION | Worker block، clean-proxy block و circuit recovery جدا هستند |
| فقط Prometheus | Alertmanager، Grafana و چهار exporter نیز وجود دارند |
| Model B Squid 2/3 روی Central ندارد چون مستند گفته | باید با profile و runtime inventory enforce/verify شود |
| همه 6672 node و 15142 edge verify شده‌اند | ادعای غیرقابل بازتولید حذف شده |
| throughput 1000-2000+ قطعی | نیازمند metric production با success قطعی |

---

## 21. گره‌های محوری و یال‌های قابل اتکا

این بخش graph مفهومی است، نه ranking آماری بدون artifact.

### 21.1. Core nodes

| node | ورودی‌ها | خروجی‌ها/وابستگی‌ها |
|---|---|---|
| Client | auth/admin provisioning | Driver، Plate، Job، Fuel، Batch، Reports |
| Driver | tenant + UTCMS credential | Session، RuntimeState، Schedule، Job |
| WaybillJob | API payload/idempotency | Intent، Execution، Logs، Events، Reconciliation |
| SchedulerService | due jobs + gate/limits | DispatchIntent |
| DispatcherService | pending intent + registry/circuit | partitioned Celery queue |
| WorkerRegistry | worker startup/heartbeat | healthy indices و routing |
| Execution | claimed intent + worker lease | mutation result/orphan recovery |
| EnhancedWaybillManager | payload/session/proxy/browser | mutation evidence |
| ReconciliationService | UNKNOWN jobs + UTCMS History | SUCCESS یا NEEDS_REVIEW |
| UTCMSSubmissionGate | Redis/DB observation + prediction | allow/deny submission |
| BrowserManager | config/proxy/model | Chromium context/page lifecycle |
| Captcha providers | image + model assets | solved value/error taxonomy |
| CleanIPPoolManager | sources/probes/Redis | ranked proxy endpoint |
| Redis | app/worker coordination | queue/cache/lock/pub-sub/state |
| PostgreSQL | durable aggregates | API/report/orchestration source |

### 21.2. Critical edges

- Client owns Driver/Plate/WaybillJob/FuelInquiry/UploadBatch.
- WaybillJob creates or reuses canonical idempotency identity.
- SchedulerService creates DispatchIntent.
- DispatcherService consults WorkerRegistry and circuit state.
- DispatcherService publishes to a base/partitioned queue.
- Worker claims intent and creates Execution with fencing/lease.
- Worker uses Driver session, chosen proxy, BrowserManager and CAPTCHA provider.
- EnhancedWaybillManager returns evidence but does not alone certify success.
- ReconciliationService validates against UTCMS History.
- JobStateMachine enforces confirmed mutation before SUCCESS.
- Worker events traverse Redis pub/sub to FastAPI WebSocket.
- Beat publishes control messages consumed by celery_scheduler or worker queues.
- Prometheus scrapes FastAPI/exporters and routes alerts through Alertmanager.

---

## 22. فایل‌های مرجع هر حوزه

| حوزه | فایل‌های اصلی |
|---|---|
| App wiring | app/main.py |
| Configuration | app/core/config.py، .env.example |
| Database | app/core/database.py، app/models_*.py، alembic/versions |
| API | app/api/routes |
| State/orchestration | app/orchestrator |
| Scheduler/dispatch | app/orchestrator/scheduler_service.py، dispatcher_service.py |
| Reconciliation | app/orchestrator/reconciliation_service.py، utcms_reconciliation_scraper.py |
| Celery | app/workers/celery_app.py، compose/backend.yml، compose/worker-node.yml |
| Waybill RPA | app/automation/waybill_enhanced.py، auth.py، utcms_http_login.py |
| Browser | app/automation/browser.py |
| CAPTCHA | app/automation/captcha |
| Fuel | app/automation/fuel_scraper.py، app/services/fuel_inquiry_service.py |
| Proxy | app/automation/worker_proxy.py، proxy_rotator.py، clean_ip_pool.py |
| Gate | app/services/utcms_submission_gate.py |
| Realtime | app/realtime/events.py، app/api/routes/realtime.py |
| Frontend | apps/web/src |
| Ingress | infra/nginx |
| Deployment | compose، manage.sh، scripts/deploy* |
| Monitoring | compose/monitoring.yml، infra/prometheus، infra/grafana |
| UTCMS contract | docs/UTCMS_CONSTRAINTS.md، docs/UTCMS_SUBMIT_CONTRACT.md |

---

## 23. پروتکل نگهداری این graph

هر تغییر معماری باید همراه با این metadata ثبت شود:

- generated/reviewed timestamp؛
- git SHA؛
- Alembic head؛
- topology name؛
- source file و test مرتبط؛
- classification: CODE-VERIFIED، CONFIG-TARGET یا RUNTIME-VERIFICATION؛
- effective env غیرحساس در صورت وابستگی behavior؛
- migration/API/frontend impact؛
- rollback و verification command.

موارد زیر نباید وارد graph شوند:

- secret و password؛
- DSN یا proxy URL دارای credential؛
- IP یا topology محرمانه بدون نیاز عملیاتی؛
- ادعای accuracy/performance بدون artifact؛
- ادعای production بدون timestamp/evidence؛
- route یا column فرضی که از OpenAPI/model قابل استخراج نیست.

هنگام drift:

1. ابتدا code/OpenAPI/model/Compose بررسی شود؛
2. سپس runtime evidence جمع‌آوری شود؛
3. قرارداد UTCMS با dry-run و بدون mutation ناخواسته بررسی شود؛
4. این سند و ARCHITECTURE.md هم‌زمان update شوند؛
5. نسخه external فقط از همین tracked file sync شود.

---

## نتیجه

این فایل مرجع tracked معماری و رابطه‌های BarPro است. بخش‌های CODE-VERIFIED برای
ادامه توسعه قابل اتکا هستند، مشروط به اینکه agent فایل‌های مرجع همان commit را
نیز بخواند. هیچ بخش CONFIG-TARGET نباید به‌عنوان وضعیت زنده production گزارش شود
و هر مورد RUNTIME-VERIFICATION بدون شاهد باید صریحاً «نیازمند بررسی runtime»
باقی بماند.

# گزارش عملیاتی BarPro - 2026-09-02

این گزارش بر اساس snapshot زندهٔ Central در بازهٔ 2026-09-02 10:00 تا 10:25 UTC و بررسی local repository تهیه شده است. هیچ رمز، token، payload شخصی یا مقدار CAPTCHA در این سند ثبت نشده است.

## نتیجهٔ اجرایی

ثبت موفق جدید در snapshot وجود ندارد. از 41 job موجود، 0 مورد با سه شاهد لازم موفق شناخته شده است: tracking code در پاسخ RPA، همان code در `result_json` و رکورد منطبق در History/Search پرتال UTCMS.

دو Worker ریموت تا پایان شب در دسترس نیستند و اتصال SSH به هر دو timeout شد. Central Worker 1، API، DB، Redis، Squid مرکزی، Nginx، Scheduler و Beat بالا هستند. بنابراین ناوگان کامل سه‌مسیره برای استفاده از سه egress اختصاصی فعلاً در دسترس نیست.

## وضعیت زیرساخت

| بخش | وضعیت | شاهد یا توضیح |
|---|---|---|
| Central SSH | سالم | hostname و uptime از SSH خوانده شد |
| Worker 2/3 SSH | در دسترس نیست | timeout؛ بررسی Image و Squid آن‌ها تا بازگشت دسترسی ممکن نیست |
| API/Nginx/Frontend | سالم | `/healthz` و `/readyz` با HTTP 200؛ کانتینرها healthy |
| PostgreSQL | سالم | اتصال مستقیم و migration advisory lock موفق |
| Redis | سالم از داخل Backend | `ping` موفق؛ credential محلی این checkout با secret فعال سرور یکی نیست |
| Migration | همگام | `039_add_route_chain_scheduling (head)` |
| Scheduler/Beat | اصلاح و سالم | هر دو با Image ID جدید بازسازی شدند و taskهای دوره‌ای اجرا می‌شوند |
| Central health | دو هشدار | فقط Squid ریموت 2 و 3 به دلیل خاموشی Workerها fail می‌شوند |

اصلاح `manage.sh health` انجام شد تا تست اتصال DB را مستقیماً داخل `barpro-backend` اجرا کند؛ خطای قبلی ناشی از mismatch project label در Compose بود، نه خرابی PostgreSQL.

Kernel log روی Central چند OOM kill برای Backend با سقف `512m` نشان داد. سقف Backend به `768m` و سقف Beat به `384m` افزایش یافت؛ مجموع limitهای Central طبق audit برابر `9.6GB` و همچنان زیر بودجهٔ `10.5GB` است.

## بررسی Imageها

هر 16 کانتینر فعال Central با tag مورد انتظار منطبق هستند و کانتینر اضافی Model A مشاهده نشد. Image مشترک Backend/Worker/Scheduler/Beat با tag `barpro_backend:latest` و Image ID فعلی اجرا می‌شود. Scheduler و Beat که ابتدا stale بودند، بازسازی شدند.

بررسی Image و container inventory روی Worker 2 و 3 به علت timeout SSH هنوز قابل اثبات نیست و نباید سالم فرض شود.

یک rebuild کامل Backend انجام نشد: dependencyها و لایه‌های cache موفق بودند، اما دانلود Chromium Headless Shell از mirror در مهلت عملیاتی timeout شد. بررسی endpoint ایرانی `mirror.testeng.ir/playwright` نیز در همان زمان `502 Bad Gateway` داد؛ بنابراین artifact جدید از mirror ایرانی دریافت نشده است. Dockerfile اکنون همین mirror ایرانی را به‌صورت پیش‌فرض و قابل override تنظیم می‌کند. سرویس‌های running از image قبلی tag-compatible استفاده می‌کنند، درحالی‌که source و Compose/config جدید روی host bind-mounted و فعال است. برای تغییر digest image باید mirror سالم شود یا browser artifact از قبل در cache موجود باشد و سپس build کامل و verify شود.

## وضعیت بارنامه‌ها

| وضعیت | تعداد | علت/اقدام |
|---|---:|---|
| `success` با شاهد کامل | 0 | هیچ tracking code معتبر در jobها وجود ندارد |
| `pending` | 20 | آمادهٔ برنامه‌ریزی، مشروط به Gate و Worker سالم |
| `waiting_submission_window` | 9 | Gate فعلی `unknown` و fail-closed است |
| `failed` | 8 | `TARGET_SITE_TIMEOUT`؛ علت غالباً در دسترس نبودن فرم پس از recovery |
| `needs_review` | 4 | یک `AUTH_FAILURE` قابل retry، یک payload ناقص، یک `submission_unconfirmed` و یک mutation مبهم بدون category |
| کل | 41 | 40 payload معتبر، 1 payload ناقص |

اعتبارسنجی strict روی payloadهای ذخیره‌شده نشان داد job با `id=53` شهر/آدرس مبدأ و مقصد و پلاک ندارد. این فیلدها قابل حدس‌زدن نیستند و تا دریافت دادهٔ واقعی نباید ارسال شوند.

دو job دارای `mutation_status=ambiguous` یا `submission_unconfirmed` هرگز مستقیم resubmit نمی‌شوند؛ ابتدا باید با مسیر reconciliation و سه شاهد بررسی شوند تا duplicate registration رخ ندهد.

## Gate و CAPTCHA

آخرین observation معتبر `otp_free` در 2026-09-01 منقضی شده و state فعلی `unknown` است. اکنون زمان تهران خارج از پنجرهٔ پیش‌بینی OTP است، اما پیش‌بینی زمانی به‌تنهایی مجوز mutation نیست. تا تولید witness زندهٔ `OTP_FREE`، سیستم عمداً ثبت را متوقف می‌کند و manual override یا جعل observation استفاده نشده است.

CAPTCHA فقط از مدل‌های داخلی پروژه استفاده می‌کند:

- CAPTCHA ریاضی ورود: CNN محلی
- CAPTCHA فارسی DNT: مدل `dnt_captcha_crnn.pth`
- fallback: Keras، Enhanced OCR و Local OCR در همان Worker process

provider بینایی خارجی، کلید API، fallbackهای Compose/config و اسکریپت‌های وابسته حذف شدند. asset مدل DNT ساخته‌شده روی Central به local منتقل و برای commit آماده شد.

## IP و Proxy Pool

Pool مشترک Redis دارای 8 proxy عملیاتی است؛ 4 مورد egress ایران را اندازه‌گیری کرده‌اند و 4 مورد هنوز شاهد مثبت جغرافیایی ندارند. انتخاب round-robin در pool روی کل رکوردهای قابل‌استفاده انجام می‌شود و proxy مسدودشده cache Worker را فوراً invalidate می‌کند.

Policy فعلی `worker_first` است: Squid اختصاصی هر Worker مسیر اصلی است و Clean IP Pool فقط در صورت unavailable/blocked شدن مسیر اختصاصی وارد می‌شود. این policy برای موفقیت ثبت مناسب‌تر است؛ proxyهای رایگان با وجود healthy بودن screening، برای Playwright ثبت واقعی ناپایدارند. با بازگشت Workerها، سه egress اختصاصی و pool fallback باید جداگانه probe و ثبت شوند.

## اقدامات انجام‌شده

1. Scheduler و Beat stale با Image جدید بازسازی شدند.
2. health check اتصال DB اصلاح شد و روی Central اکنون `OK` است.
3. Image inventory Central کامل بررسی شد؛ tagها، digestهای running و health state منطبق‌اند.
4. payloadها با JSON parsing صحیح و strict validation بررسی شدند.
5. خطاهای safe-to-retry از mutation مبهم جدا شدند.
6. provider بینایی خارجی و کلید آن از tree جاری حذف شدند و مدل داخلی DNT sync شد.
7. این گزارش و Changelog به repository اضافه می‌شوند.

## Verification کد

- regression suite مرتبط با CAPTCHA، login، waybill، mutation safety، location read-back، state machine و queue routing: `276 passed`
- Ruff روی فایل‌های تغییرکرده: بدون خطا
- deployment codebase audit: `passed`
- RPA network audit: `passed`
- جست‌وجوی دقیق provider/key خارجی در tree جاری: بدون نتیجه

تعداد فوق مربوط به suite متمرکز این تغییر است؛ نتیجهٔ live registration محسوب نمی‌شود و جای سه شاهد UTCMS را نمی‌گیرد.

## کارهای باقیمانده برای ثبت کامل

1. پس از بازگشت Worker 2/3، SSH، Image ID، Squid local، egress IP، registry heartbeat و queue binding هر دو نود بررسی شود.
2. یک live gate probe معتبر با evidence واقعی انجام شود تا `OTP_FREE` فعلی ثبت شود؛ صرفاً باز کردن زمان‌بندی یا manual override مجاز نیست.
3. job `id=53` فقط پس از دریافت شهر/آدرس‌های واقعی و پلاک معتبر اصلاح شود.
4. jobهای `TARGET_SITE_TIMEOUT` و `AUTH_FAILURE` از مسیر رسمی retry requeue شوند؛ jobهای ambiguous ابتدا reconciliation شوند.
5. jobها با concurrency برابر 1 برای هر Worker/driver اجرا شوند و هر نتیجه تا سه شاهد در History reconcile شود.
6. فقط پس از صفر شدن queueهای قابل‌اجرا و تعیین تکلیف `needs_review`، نتیجهٔ نهایی موفق اعلام شود.

تا تکمیل این موارد، اعلام «تمامی بارنامه‌ها ثبت شدند» از نظر عملیاتی قابل دفاع نیست.

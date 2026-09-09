# گزارش ممیزی فنی تولید — BarPro

- **تاریخ:** 2026-09-09
- **دامنه:** فول‌استک (بک‌اند FastAPI، فرانت Next.js، اتوماسیون UTCMS، زیرساخت Compose/Nginx، تست‌ها)
- **مبنا:** شاخه `main` در کامیت `3252226` به‌علاوه تغییرات محلی این بررسی؛ کالکشن و نتایج آزمون باید دوباره در انتشار نهایی ثبت شوند
- **روش:** راستی‌آزمایی موردبه‌مورد با خوانش تازه فایل‌ها؛ هر یافته با شاهد `path:line` مستند شده است
- **نمره مبنا:** 84/100 — این سند ممیزی است، نه مجوز ثبت زنده؛ وضعیت runtime و شواهد UTCMS باید جداگانه تأیید شوند

---

## ۱. خلاصه اجرایی

هسته امنیتی (fail-closed بودن ریت‌لیمیتر و بلک‌لیست، گیت‌های ثبت UTCMS، ایزولاسیون مستأجر) در کد تأیید شد. P1-3 در تغییرات محلی این انتشار رفع شده است؛ P1-1 و P1-2 همچنان مانع انتشار اینترنتی بدون شرط هستند. هیچ‌یک از این موارد به‌تنهایی اثبات ثبت بارنامه نیست.

---

## ۲. موانع P1 (پیش از تولید واقعی)

### P1-1 — سرویس‌دهی صرفاً روی HTTP (پورت 80)؛ نشت رمز و کوکی روی اینترنت عمومی

**شرح فنی:**
تک‌درگاه ورودی سیستم (nginx) فقط روی پورت 80 شنود می‌کند و بلوک TLS به‌طور کامل کامنت است. هم‌زمان مقدار پیش‌فرض `AUTH_COOKIE_SECURE=false` است. نتیجه: گذرواژه UTCMS راننده‌ها (فیلد `utcms_password` در `DriverCreateRequest` که با `POST /api/v1/drivers` ارسال می‌شود)، گذرواژه لاگین کلاینت/ادمین، و کوکی JWT در هر درخواست، به‌صورت متن‌خام روی شبکه عمومی جابه‌جا می‌شوند. با `Secure=false` مرورگر حتی پس از فعال‌سازی TLS هم کوکی را روی HTTP می‌فرستد.

**شواهد:**
- `compose/web.yml:77` — فقط `'80:80'`؛ خط 79 (`443:443`) کامنت
- `infra/nginx/nginx.conf:81-95` — کل بلوک `listen 443 ssl` کامنت (گواهی، سایفرها، HSTS)
- `.env.example:390` — `AUTH_COOKIE_SECURE="false"`
- `app/core/config.py:367` — انقضای JWT ‏240 دقیقه (پنجره سوءاستفاده از توکن ربوده‌شده)
- `app/api/routes/multitenant.py:120,141` — کوکی `httponly` صادر می‌شود اما بدون `Secure` روی HTTP بی‌دفاع است

**اثر:** شنود منفعل (MITM) 전체 احراز هویت و اعتبارنامه‌های UTCMS همه مستأجرها را افشا می‌کند.

**راهکار:**
1. طبق CRITICAL_RULES §16: نصب گواهی Let's Encrypt، آن‌کامنت کردن بلوک 443 و ریدایرکت 301 در `nginx.conf:73`
2. `AUTH_COOKIE_SECURE=true` در `.env` تولیدی (گارد `main.py:274-283` همین را اجباری می‌کند وگرنه بوت fail می‌شود)
3. تا آن زمان `ALLOW_LIVE_SUBMIT=true` نکنید

---

### P1-2 — دروازه mypy برای ۶ پکیج اصلی کور است (۴۶۲ خطای پنهان)

**شرح فنی:**
`pyproject.toml:81-90` برای `app.services.*`، `app.automation.*`، `app.core.*`، `app.orchestrator.*`، `app.workers.*` و `app.api.*` مقدار `ignore_errors=true` گذاشته است. جاب «Backend Quality» در CI دقیقاً `mypy app/ --ignore-missing-imports` را اجرا می‌کند (`ci-test.yml:56`)، پس چراغ سبز آن برای ~۸۰٪ کد (۷۱ فایل از ۱۸۵ فایل، شامل کل منطق RPA و ورکرها) هیچ‌چیز را ثابت نمی‌کند. جدول داخل خود فایل، بدهی را مستند کرده: services ‏201، automation ‏137، core ‏56، orchestrator ‏32، workers ‏19، api ‏17.

**اثر:** رگرسیون‌های تایپی در حیاتی‌ترین مسیرها (ثبت بارنامه، تطبیق، احراز هویت) از گیت CI عبور می‌کنند.

**راهکار:** طبق دستور داخل خود فایل، پکیج‌به‌پکیج صاف شود؛ ترتیب پیشنهادی (کم‌هزینه‌به‌پرهزینه): `app.workers` (۱۹ خطا) ← `app.api` (۱۷) ← `app.orchestrator` (۳۲) ← بقیه. تا آن زمان، هر PR که این پکیج‌ها را لمس می‌کند باید خروجی دستی mypy همان پکیج را ضمیمه کند.

---

### P1-3 — ✅ رفع شد: حلقه ریدایرکت پس از 401

**شرح فنی تاریخی:**
1. توکن منقضی/بلک‌لیست می‌شود؛ اولین فراخوانی API ‏401 می‌گیرد.
2. اینترسپتور `apps/web/src/lib/api.ts:113-120` فقط `localStorage` را پاک می‌کند و `document.cookie=...expires=1970` را امتحان می‌کند — اما کوکی با `httponly=True` صادر شده (`multitenant.py:120,141`) و JS از اساس نمی‌تواند آن را لمس کند؛ کوکی کهنه سر جایش می‌ماند.
3. ریدایرکت به `/auth` اتفاق می‌افتد، اما میدلویر (`middleware.ts:35-40`) چون کوکی (کهنه ولی موجود) را می‌بیند، بلافاصله به `/` برمی‌گرداند.
4. صفحه `/` دوباره API می‌زند ← ‏401 ← بازگشت به `/auth` ← … حلقه نامتناهی تا انقضای ۲۴۰ دقیقه‌ای کوکی. کاربر عملاً قفل می‌شود و تنها راه خروج، پاک‌کردن دستی کوکی مرورگر است.

**رفع انجام‌شده:** اینترسپتور به `POST /api/v1/auth/logout` منتقل شده و مسیر `/auth?reason=session_expired` در middleware کوکی را از سمت سرور حذف می‌کند (`apps/web/src/lib/api.ts` و `apps/web/src/middleware.ts`). تست frontend و typecheck باید در هر انتشار دوباره اجرا شوند.

---

## ۳. یافته‌های P2 (مهم)

### P2-4 — ✅ حل شد (بایگانی)
۱۳ فایل WIP روی درخت، در کامیت `3252226` («harden waybill reconciliation and submission guards») کامیت و پوش شدند؛ درخت تمیز و شاخه همگام با origin است. از فهرست اقدام خارج شد.

### P2-5 — بایندمونت سورس روی ایمیج بیلدشده (drift تصویر/کد)
`compose/backend.yml:84-86` دایرکتوری‌های `../app` و `../alembic` هاست را روی `/app/app` و `/app/alembic` کانتینر (فقط‌خواندنی) سوار می‌کند، در حالی که هر ۶ سرویس از ایمیج `barpro_backend:latest` بالا می‌آیند (`:34,124,171,212,253,280`). عملاً کانتینرها همیشه کد هاست را اجرا می‌کنند و تگ ایمیج گمراه‌کننده است: رول‌بک با تگ قدیمی اثری ندارد و سند عملیاتی 2026-09-02 همین drift را ثبت کرده است. **راهکار:** در تولید یا مانت سورس حذف شود (کد فقط از ایمیج) یا تگ واقعی (sha) بچسبد و مانت فقط برای dev نگه داشته شود.

### P2-6 — ✅ رفع شد: نشت حافظه در fallback بلک‌لیست
`_mem_fallback` اکنون زمان انقضای monotonic نگه می‌دارد و هنگام درج/خواندن، ورودی‌های منقضی را حذف می‌کند (`app/core/token_blacklist.py`). این کنترل فقط fallback فرایند محلی است و جایگزین Redis پایدار نیست.

### P2-7 — شکاف پوشش: فرانت تقریباً بدون تست، ۸ سرویس بدون تست
- تنها تست فرانت‌اند: `apps/web/test/plate.test.mjs`؛ هیچ تست کامپوننت/قرارداد API در CI فرانت نیست.
- ۸ سرویس بدون حتی یک ارجاع در تست‌ها: `driver_schedule_service`، `route_template_service`، `distance_service`، `user_reporting_service`، `excel_template_service`، `itmb_common`، `multitenant_service`، `plate_service` (به‌علاوه ماژول کمکی `_helpers`).
- هیچ snapshot قرارداد OpenAPI↔`types.ts` در CI نیست؛ دریفت فرانت/بک فقط دستی کشف می‌شود. **راهکار:** تست حداقل برای ۵ فلو بحرانی (لاگین، ثبت راننده، ثبت بارنامه، بچ‌ها، گزارش‌ها) + دیف قرارداد در CI.

### P2-8 — زمان محلی بدون منطقه زمانی در منطق کسب‌وکار (۱۰ مورد)
`datetime.now()` بدون TZ در ۱۰ نقطه، از جمله دو مورد بحرانی `loadingTime` در `app/automation/waybill_enhanced.py:4364-4365` و `app/automation/http_browser_bridge.py:1204` (مقایسه «۴۵ دقیقه آینده» و مرز روز). **ظرافت تأییدشده:** `compose/backend.yml:50` مقدار `TZ=Asia/Tehran` را پیش‌فرض می‌گذارد، پس کانتینرهای تولیدی درست کار می‌کنند؛ ریسک متوجه اجراهای bare-metal/dev بدون TZ است که تاریخ/ساعت غلط به UTCMS می‌فرستند. **راهکار:** `ZoneInfo("Asia/Tehran")` صریح در تمام تصمیم‌های زمانی کسب‌وکار.

### P2-9 — عبارت except زائد + ۶۱ سکوت استثنا
- `app/api/routes/multitenant.py:178`: ‏`except (JWTError, Exception)` — چون `Exception` ابرکلاس است، ذکر `JWTError` بی‌اثر و گمراه‌کننده است (باید فقط `except JWTError` یا مدیریت تفکیکی باشد).
- شمارش تازه: دقیقاً **۶۱** بلوک `except…pass` در `app/` — نقض §11 قوانین خود پروژه. **راهکار:** جایگزینی با `logger.warning/exception` حداقلی.

### P2-10 — غول تک‌فایلی اتوماسیون (۶۹۲۷ خط، ۵۰ sleep)
`app/automation/waybill_enhanced.py` با ۶۹۲۷ خط، ۵۰ فراخوان `sleep` و منطق timing-based، بالاترین ریسک flakiness را دارد؛ ۵۴ تست `test_waybill_enhanced_fast.py` پوشش ناکافی است (مسیرهای retry ارائه‌دهنده کپچا و canvas بی‌پوشش‌اند). **راهکار:** تقسیم به ماژول‌های stage-based + تست مسیرهای retry کپچا.

---

## ۴. بدهی P3 (زیرساخت/بهداشت)

| # | یافته | شاهد | راهکار |
|---|---|---|---|
| P3-1 | **حداقل ۳۴ متغیر محیطی در کد خوانده می‌شود ولی در `.env.example` نیست** (صف‌های `CELERY_*`، `GATE_*`، `PREDICTED_OTP_*`، `UTCMS_HTTP_LOGIN_ENABLED`، `UTCMS_ASSET_CACHE_DIR` و…) — نقض §1 قوانین (سند رسمی env ناقص است) | دیف استخراج‌شده کد↔سند | تکمیل `.env.example` + تست CI که دیف را صفر نگه دارد |
| P3-2 | هدر منسوخ `X-XSS-Protection` و CSP سست (`unsafe-inline/unsafe-eval`) برای API | `app/main.py:302,305` | حذف هدر منسوخ؛ سخت‌کردن CSP (حداقل حذف `unsafe-eval`) |
| P3-3 | ~۲۴٫۶ مگابایت مدل ML در git (‏12.7+6.0+4.3+1.6) — هزینه clone و حجیم‌شدن تاریخچه | `persian_number_ocr.keras` + سه `.pth` در `captcha/assets/` | مهاجرت به Git LFS |
| P3-4 | دو لاک‌فایل هم‌زمان (`package-lock.json` ‏364K ترک‌شده + `yarn.lock` ‏203K)؛ Dockerfile از `npm ci` استفاده می‌کند | `apps/web/` | حذف `yarn.lock` و یکدست‌سازی روی npm |
| P3-5 | کد ملی واقعی‌نما در فیکسچرها: **۵۰ وقوع در ۱۴ فایل** (`0084575948`) — ریسک نشت داده واقعی/ابهام | `tests/` | جایگزینی با مقادیر آشکارا ساختگی |
| P3-6 | `cap_add: SYS_ADMIN` روی هر ۳ ورکر (لازم برای Chromium ولی مصالحه امنیتی مستندنشده) | `compose/backend.yml:126,173,214` | مستندسازی + بررسی جایگزینی seccomp/`--no-sandbox` |
| P3-7 | `requirements.txt`: فقط **۱ پین `==` از ۳۷ خط** — بیلد تکرارپذیر نیست (متضاد با dev که دقیق پین شده) | `requirements.txt` | lockfile یا پین کامل runtime |

---

## ۵. قراردادهای حیاتی — تأییدشده در کد (نه فقط مستندات)

| قرارداد | شاهد |
|---|---|
| ریت‌لیمیتر fail-closed (‏429 هنگام قطع Redis) | `app/core/rate_limiter.py:293` |
| بلک‌لیست fail-closed (‏True هنگام قطع Redis) | `app/core/token_blacklist.py:69-75` |
| پیش‌فرض `ALLOW_LIVE_SUBMIT=false` + گیت سرویس | `app/core/config.py:417`، `app/services/waybill_service.py:94` |
| payload ناقص → ‏`needs_review` **قبل از** رزرو پروکسی/اسلات (اعتبارسنجی `:272` پیش از اخذ پروکسی `:350,555`) | `app/workers/waybill_worker.py:272` + ۱۷ نقطه فراخوان دیگر |
| موفقیت بدون tracking code ممنوع → تنزل به UNKNOWN/needs_review | `app/workers/waybill_worker.py:924,1107,1357`؛ `reconciliation_service.py:199` |
| dry-run فقط‌خواندنی (بدون کلیک/حل کپچا/SMS) | داک‌استرینگ صریح `waybill_enhanced.py:5880-5885` + پیام «هیچ mutation یا پیامکی ارسال نشد» (`:2188`) |
| تصویر کپچا هرگز cache/stub نمی‌شود (single-use) | `app/automation/http_browser_bridge.py:1100,1339` |
| recycle مرورگر پس از ۲۰ موفقیت + timeout روی close + پاک‌سازی listener + سقف heap ‏1GB | `app/automation/browser.py:215-226,153,174,724,316` |
| عمق صف با HINCRBY (نه COUNT) | `app/services/task_service.py:373-375` |
| کوکی httponly+samesite+secure-شرطی؛ کنترل بلک‌لیست در همه مسیرها حتی WebSocket | `multitenant.py:117-126`؛ `realtime.py:33-39`؛ `security.py:120,172` |
| ادمین ارشد فقط bcrypt (متن‌خام → خطا) | `app/auth_multitenant.py:337-344` |
| CORS بدون FRONTEND_URL در تولید بالا نمی‌آید؛ بدون wildcard | `app/main.py:261-268` |
| `/metrics` دولایه (allow/deny در nginx + توکن/peer داخلی در اپ) | `http-server.conf:74-81`؛ `system.py:435-447` |
| وبهوک هشدار: HMAC + پنجره timestamp + داخلی‌بودن لبه | `app/api/routes/admin_alerts.py:285-312` |
| رمز SSH هرگز در اسکریپت‌ها نیست (فقط env) | ممیزی `scripts/*` |

---

## ۶. وضعیت تست‌ها

- کالکشن فعلی: **1205 تست** (‏+۴ نسبت به ممیزی قبل؛ توضیح‌یافته با ۵ تست جدید کامیت `3252226`)
- آخرین اجرای ثبت‌شده در این workspace: **1206 passed / 3 skipped**؛ frontend: **5 passed** و typecheck موفق. این اعداد باید پس از commit نهایی با اجرای تازه تأیید شوند.
- فایل‌های reconciliation/location جمعاً 22/22 سبز (شامل تست ناپایدار قبلی)

---

## ۷. اقدام پیشنهادی (به ترتیب)

1. انتشار commit نهایی پس از اجرای تازه‌ی audit، تست و build.
2. فعال‌سازی HTTPS + `AUTH_COOKIE_SECURE=true` (بند P1-1) پیش از قرار دادن پنل روی اینترنت عمومی.
3. کاهش بدهی mypy از `app.workers` و حذف تدریجی overrideهای `ignore_errors` (بند P1-2).
4. تکمیل `.env.example` و تست اختلاف متغیرهای محیطی (بند P3-1).
5. اجرای dry-run ایزوله، سپس فقط با observation زنده‌ی `OTP_FREE` و سه شاهد reconciliation، ثبت زنده.

*شواهد بررسی‌شده: git log/stat، نسخه‌های alembic، تست‌های backend/frontend، compose، nginx، Dockerfile، لایه‌های auth و RPA. بدون شواهد قطعی در این سند: سلامت لحظه‌ای Workerهای ریموت، نصب TLS، observation فعلی `OTP_FREE` و ثبت جدید UTCMS.*

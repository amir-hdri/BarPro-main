# راستی‌آزمایی ایزوله و یکپارچه‌سازی — ۲۰۲۶-۱۰-۰۶

این سند نتیجهٔ محیط محلی است؛ شاهد اجرای CI، سرور تولید یا ثبت بارنامه در UTCMS نیست.

## نتیجهٔ اجرا

| فرمان / شاهد | نتیجهٔ واقعی |
| --- | --- |
| `pytest tests/test_e2e_bot.py tests/test_fuel_scraper_live.py tests/integration tests/test_integration -q` | **10 passed, 5 skipped in 9.17s**؛ فایل `hermetic-integration-focused.log` |
| `pytest tests/integration tests/test_integration -m integration -q -rs` | **4 passed, 4 skipped in 1.40s**؛ فایل `integration-marker-after.log` |
| Ruff روی همین شش فایل تست و Black `--check` | **All checks passed**؛ شش فایل بدون تغییر قالب‌بندی |

فرمان‌ها با `ENVIRONMENT=test`، `DATABASE_URL=sqlite+aiosqlite:///./test.db`، `REDIS_URL=redis://localhost:6379/0` و `BARPRO_RUN_LIVE_UTCMS=0` اجرا شدند. مقادیر DATABASE_URL/REDIS_URL صرفاً پیکربندی پیش‌فرض اپلیکیشن برای بارگذاری تست هستند؛ fixtureهای integration برای سرویس واقعی به متغیرهای مستقل زیر متکی‌اند.

چهار skip مربوط به PostgreSQL است: `BARPRO_TEST_POSTGRES_DSN` در محیط محلی تنظیم نشده بود. اجرای این چهار تست **تأییدنشده** است و نباید با موفقیت SQLite جایگزین شود. skip پنجم تست اختیاری و فقط خواندنی UTCMS است؛ هیچ تماس زندهٔ UTCMS در این اجرا انجام نشد. گزارش `e2e-hermetic-after.log` اجرای ناموفق قبلی را نگه می‌دارد؛ پس از اصلاح selector صریح فیلد CAPTCHA، نتیجهٔ نهایی در `hermetic-integration-focused.log` ثبت شده است.

## تست مرورگر

`tests/test_e2e_bot.py` یک Chromium واقعی را روی HTML محلیِ route-fulfilled اجرا می‌کند. فقط URL ساختگی `http://barpro-e2e.test/Account/Login` مجاز است؛ سایر درخواست‌های مرورگر abort می‌شوند. DNS و HTTP پایتون، curl_cffi، httpx، aiohttp و Playwright APIRequestContext در تست مسدود هستند. مسیر HTTP-first صریحاً mock و فراخوانی آن بررسی می‌شود. فرم fixture تنها بعد از تطبیق واقعی مقادیر نام کاربری، رمز و CAPTCHA نشان موفقیت می‌سازد. fallback انتخابگر، کلیک و capture/fill CAPTCHA واقعی‌اند؛ تماس با solver جایگزین محلی دارد. زمان کل ۴۰ ثانیه محدود است. نبود Chromium در CI خطا است؛ در محیط محلی skip صریح است.

## قرارداد integration

- Redis: با `BARPRO_TEST_REDIS_URL` به سرویس آزمایشی صریح وصل می‌شود؛ در نبود آن یک فرایند خصوصی `redis-server` با پورت TCP بسته، سوکت Unix با دسترسی `0700`، بدون persistence و پوشهٔ موقت اجرا می‌شود. فقط دو کلید claim متعلق به شناسهٔ UUID همان تست پاک می‌شوند؛ `FLUSHDB` استفاده نمی‌شود. خاموش‌سازی فرایند و پاک‌سازی پوشه حتی در خطای cleanup تضمین شده است. نسخهٔ Redis حداقل ۷ است.
- سه تست Redis، Lua واقعی claim را برای ۲۴ رقیب، expiry واقعی و جلوگیری از حذف مالک جدید توسط release قدیمی، و rollback گرفتن نیمه‌کارهٔ قفل دوکلیدی بررسی می‌کنند.
- PostgreSQL: فقط `BARPRO_TEST_POSTGRES_DSN=postgresql+asyncpg://...` مجاز است. هر تست schema تصادفی مخصوص خود می‌سازد و فقط همان schema را حذف می‌کند؛ حداقل نسخه ۱۶ و timezone جلسه `America/Los_Angeles` است. سرویس باید صرفاً پایگاه آزمایشی باشد.
- چهار تست PostgreSQL مسیر واقعی commit/rollback dependency، یکتایی هویت راننده در هر tenant، یکتایی idempotency بارنامه و صفحه‌بندی fallback با JSONB را بررسی می‌کنند.
- `BARPRO_REQUIRE_PG_INTEGRATION=1` و `BARPRO_REQUIRE_REDIS_INTEGRATION=1` نبود سرویس لازم را در CI به failure تبدیل می‌کنند. placeholder قبلی `assert True` حذف شده است؛ lifecycle واقعی SQLite نیز marker `integration` دارد.

نمونهٔ اجرای CI بعد از فراهم بودن سرویس‌های آزمایشی:

```sh
BARPRO_REQUIRE_PG_INTEGRATION=1 BARPRO_REQUIRE_REDIS_INTEGRATION=1 \
BARPRO_RUN_LIVE_UTCMS=0 \
pytest tests/integration tests/test_integration -m integration -q -rs
```

## تست زندهٔ اختیاری

`tests/test_fuel_scraper_live.py` فقط با `BARPRO_RUN_LIVE_UTCMS=1` به UTCMS دسترسی دارد و پیش از آن باید `curl https://ipinfo.io/country` در محدودیت ۱۰ ثانیه خروج موفق و کشور `IR` بدهد. نتیجهٔ غیرایرانی، خطای شبکه یا نبود فیلد واقعی failure است و به skip پنهان تبدیل نمی‌شود. هیچ login یا ثبت سندی در این تست وجود ندارد. تست‌های parsing و گیت کشور مستقل و بدون شبکه اجرا می‌شوند.

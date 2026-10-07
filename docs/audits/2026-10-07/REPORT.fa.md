# ادامه و بازبینی تغییرات BarPro — ۲۰۲۶-۱۰-۰۷

مبنای بازیابی `main@6c5564ea7483f127f2e23e785148009114bae49b` بود. کاربر تکمیل اصلاحات و ذخیره در GitHub را تأیید کرد؛ سشن قبلی درخواست commit/push روی main داشت. تغییرات باقی‌مانده بررسی و با سه ساب‌ایجنت در حوزه‌های OTP/امنیت، رابط کاربری و حمل/گزارش‌گیری تکمیل شدند. گزارش حاضر شاهد بررسی محلی است؛ وضعیت سرور و ثبت واقعی UTCMS را ثابت نمی‌کند.

## بازیابی سشن و دامنه

- سشن «یک بررسی دقیق و عمیق وتخصصی روی پروژه و همچنین تغییرات جدید…» (`01a110e1-c169-74f1-9f03-92343ab75c08`) پس از اصلاحات اولیه قطع شده بود؛ درخواست‌های ادامه با خطای resource سرویس مدل اجرا نشده بودند. فعالیت‌های security_audit، otp_reliability، frontend_contracts و shipping_reporting_fixes در تاریخچه ثبت شده‌اند. صرف ثبت فعالیت یا پیام اتمام، معیار تأیید کد نشد.
- سشن «Role & Mission: Senior Principal Systems & RPA Architect (B…» (`01a0fa5e-7bf0-73d3-81b3-0786fc32e538`) نیز بررسی شد. مبنای تصمیم‌های فعلی، checkout و تست تازه است، نه شمارش تست یا وضعیت سرور در پیام‌های قدیمی.
- تفکیک AGENTS، پوشهٔ agent-reference و تنظیم Gemini از کار دیگری باقی مانده‌اند؛ فایل‌ها و بخش‌های مستندات مربوط به آن‌ها در این commit وارد نمی‌شوند. فایل‌های runtime، secrets و coverage نیز deliverable مخزن نیستند.
- قواعد مخزن، قراردادهای UTCMS و مهارت‌های دریافت بازبینی، راستی‌آزمایی، عملیات Celery، رابط کاربری و قراردادهای fullstack/fuel در کار به‌کار رفتند.

## اصلاحات بررسی‌شده

| حوزه | رفتار فعلی و شاهد |
|---|---|
| OTP | انتساب به tenant/job/driver معتبر، challenge پایدار، dispatch به ورکر مالک، lease با توکن مالک و تمدید، fence قبل از صدور، بازیابی Stream و ACK براساس نتیجه؛ تست حملهٔ واقعی قبلی با ASGI/SQLite/Redis ایزوله نیز اضافه شد. `tests/test_otp_wakeup_and_lifecycle.py` و `tests/test_otp_reliability_regressions.py` |
| امنیت فورواردر | توکن query پذیرفته نمی‌شود؛ راهنمای تنظیم و readiness حقیقت وضعیت را نمایش می‌دهند. `tests/test_otp_forwarder_hardening.py` |
| تشخیص CAPTCHA | load مدل و ذخیره فایل خصوصی سخت‌گیر شدند؛ پاسخ حل‌شده و عبارت CAPTCHA از metadata و لاگ حذف شدند، تصویر خصوصی و digest/size باقی می‌مانند. `app/automation/captcha/debug_artifacts.py` و `tests/test_security_audit_gates.py` |
| سوابق | فیلتر راننده/روز و صفحه‌بندی؛ هر استعلام سوخت یک رکورد مستقل با زمان و هویت تاریخی است. تغییر نام/پلاک امروز، سوابق قبلی را بازنویسی نمی‌کند. `tests/test_history_identity_contracts.py` |
| نقشه | پاسخ دیررس و آدرس قبلی جای نقطه جدید نمی‌نشینند؛ خطای tile واضح است؛ popup متن را به HTML تبدیل نمی‌کند. مختصات درخواستی و نقطه مؤثر مسیر، جدا نمایش داده می‌شوند. |
| مسیر | نقطهٔ مسیر خودرویی سرویس Neshan با محدودیت جابه‌جایی ۲۵۰ متر و provenance نگهداری می‌شود؛ مختصات malformed/NaN/bool/خارج محدوده و snapshot ناسازگار رد می‌شوند. `app/services/route_authority.py` و `tests/test_gps_map_anchor_audit.py` |
| Android | نشان mock باید به همان provider تعلق داشته باشد؛ `mock=false` و اشارهٔ صرف به نام برنامه شاهد mock نیستند. `app/travel/android_observer.py` و `tests/test_android_observer_identity.py` |
| Dispatcher | مسیر async از `get_routed_queue_async` با await استفاده می‌کند؛ قرارداد بازیابی و صف حفظ شده است. `app/orchestrator/dispatcher_service.py:225` و `tests/test_dispatch_intents.py` |
| helper تأخیر | helper مشترک به‌جای `run_until_complete` روی loop فعال، `asyncio.sleep` را await می‌کند. helper مورد استفادهٔ browser از قبل async بود؛ این نقص به معنی خرابی همه تأخیرهای مرورگر نبود. `app/automation/stealth_common.py:185` و `tests/test_stealth.py` |

«نزدیک‌ترین خیابان قابل‌تردد» در این پیاده‌سازی یعنی endpoint مسیر خودرویی سرویس؛ بررسی محلی نزدیک‌ترین نقطهٔ ممکن در جهان یا مجاز بودن عبور یک کامیون مشخص را اثبات نمی‌کند. دادهٔ شبیه‌سازی‌شده، شاهد حضور فیزیکی خودرو نیست.

## تطبیق گزارش پیوست با کد

| ادعای پیوست | نتیجهٔ بازبینی |
|---|---|
| A1: TTL برابر ۹۰۰ ثانیه، یک حمل موازی و سقف ۱۴۰۰ در روز | استنتاج ظرفیت نادرست است. TTL مربوط به claim هر job است؛ قفل Android فقط بازه apply/readback را محافظت می‌کند و مدت اشغال واقعی اندازه‌گیری نشده است. `gps_shipping_manager.py:578`، `android_bridge/client.py:35`، `controller.py:230` |
| افزودن serial دوم ظرفیت حمل را دو برابر می‌کند | اثبات نشده؛ کلید Redis قفل Android سراسری است و با تغییر serial مستقل نمی‌شود. طراحی مالکیت چنددستگاه و اندازه‌گیری بار لازم است. |
| A2/C1: false بودن پیش‌فرض، وضعیت زنده را ثابت می‌کند؛ true معماری نهایی را فعال می‌کند | false پیش‌فرض کد است، نه مشاهدهٔ production. مسیر فعلی پس از apply/readback هنوز Python RegisterStart/End را فراخوانی می‌کند؛ تعامل ثبت در UI اپ رسمی با تغییر flag ایجاد نمی‌شود. `client.py:50,76` و `shipping_gps.py` |
| A3: اپ رسمی قطعاً در production FakeTraveler را رد می‌کند | یادداشت تحلیل APK سرنخ معتبر است؛ رفتار زنده روی نسخه و پیکربندی فعلی در این کار مشاهده نشد. وجود تابع detectMockLocationApps به‌تنهایی اثبات همهٔ مسیرهای اجرایی نیست. دورزدن آن انجام نشد. |
| A4: هر بار همان ۲٫۱۵ کیلومتر ارسال می‌شود | کد پس از 4012 هدف detour را افزایش می‌دهد. ۲٫۱۵ مقدار شروع trace مصنوعی است، نه حد قطعی قرارداد واقعی و نه مسافت طی‌شدهٔ خودرو. سقف ۸ تلاش نیز برای 4013/429 استثنا دارد. `gps_shipping_manager.py:1721,2077,2098` و `shipping_contract.py:18` |
| A5: ۵ متر و ۲ ثانیه، میانگین ۳–۸ ثانیه و حداکثر ۱۵ ثانیه را ثابت می‌کنند | اولی پارامترهای کنترل‌اند؛ متوسط و سقف کل ADB/network/verification از آن‌ها به‌دست نمی‌آید. هیچ benchmark latency در پیوست ارائه نشده بود. |
| A6: geo به‌تنهایی provider را فعال می‌کند | پیوست درست هشدار می‌دهد که کافی نیست؛ apply و readback لازم‌اند و در controller وجود دارند. |
| A7: تشخیص Mock Providers کاملاً رفع شده | پوشش قدیمی کافی نبود؛ خطای نسبت‌دادن نشان provider دیگر و `mock=false` در این ادامه بازتولید و اصلاح شد. |
| G1: خالی کردن فایل fallback و گیت ایران باید حذف شوند | این‌ها حفاظت عمدی در برابر استفاده از proxy ردشده‌اند؛ تصمیم قبلی کاربر در `ISSUES.md` حفظ شد. خالی بودن pool می‌تواند مسألهٔ عملیاتی باشد و به مشاهدهٔ واقعی نیاز دارد. |
| G3/C3: Redis همگام در dispatcher async | تأیید و اصلاح شد. این اصلاح ادعای حذف تمام I/O همگام از کل برنامه نیست. |
| G4/C2: نبود LIMIT و دو COUNT per tenant؛ افزایش pool به 5/5 | نبود LIMIT و COUNTهای tenant در scheduler فعلی دیده می‌شود. اما 2/2 یک pool در هر process است؛ شش consumer به معنی شش استفاده‌کننده از همان pool نیست. افزایش ثابت بدون بودجهٔ connection/بارسنجی توجیه نشد. LIMIT ساده نیز می‌تواند jobهای قابل‌اجرا را پشت ردیف‌های نامناسب متوقف کند؛ این توصیه به‌عنوان اصلاح اثبات‌شده اعمال نشد. `scheduler_service.py:75-83,157-173` و `database.py:33-46` |
| G5: scan حمل همیشه بدون index | مسیر recovery اکنون pagination با cursor دارد؛ کفایت index به query plan و دادهٔ واقعی PostgreSQL وابسته است. نبود/کفایت index را از شماره خط یا نام JSONB نتیجه نمی‌گیریم. |
| ۴ worker همگی با 3GB حاضرند؛ Redroid حدود 0.5GB limit دارد | فایل backend سه RPA worker دارد؛ `--concurrency=1` چهارم مربوط به scheduler است. workerهای ۲/۳ در profile اختیاری 2.5GB و worker-node برابر 4GB هستند. compose/android.yml اصلاً mem_limit ندارد. جمع 20GB و 12GB آزاد، مصرف اندازه‌گیری‌شده نیست. |
| چهار پاسخ IR یعنی چهار IP مستقل | نادرست؛ کشور باید همراه با IP خروجی هر worker اندازه‌گیری و متمایز بودن بررسی شود. hostname/gateway داخلی، آدرس عمومی خروجی نیست. |
| همهٔ ادعاها با file:line راستی‌آزمایی کامل شده‌اند | شماره خط به‌تنهایی آزمون runtime یا benchmark نیست. جستجوی TODO/secret هم گواه نبود نقص یا افشای داده نیست؛ ادعاها در این گزارش به کد، تست یا وضعیت تأییدنشده تفکیک شدند. |

محاسبهٔ `4 × 86400 / 60 × 0.45 = 2592` و حالت ۴۵ ثانیه `3456` از نظر حساب درست است؛ ۴ worker، زمان ۶۰/۴۵ ثانیه و ضریب موفقیت ۰٫۴۵ ورودی‌های فرضی‌اند. تبدیل آن‌ها به وعدهٔ ظرفیت واقعی، تعداد راننده یا سقف Android مجاز نیست.

## اصلاحات تکمیلی و پاک‌سازی تست‌های قدیمی

- پس از خطای نامعلوم شروع حمل، هر دو مسیر صدور `unknown` و بدون شاهد ثبت مبدأ می‌مانند؛ کد رهگیری صدور حفظ می‌شود. تست‌ها هم پایان خودکار با `force=True` و هم بازپخش صدور را کنترل می‌کنند. [بازبینی حمل](shipping-review.md).
- دو تست writer بدون مصرف‌کنندهٔ OTP و scaffolding بلااستفاده حذف شدند؛ تضمین جداسازی گیرنده و منع کلید global در تست مسیر واقعی HTTP/Lua/Redis حفظ شد. انتظار قدیمی sweep شدن شروع مبهم نیز با تست رفتار فعلی جایگزین شد. تست‌های HTTP/Playwright فعال در مسیر مهاجرت باقی ماندند. [فهرست و دلیل حذف‌ها](obsolete-tests.md).
- refresh پس‌زمینه Clean IP در harness تست ایزوله شد؛ تست‌های اختصاصی refresh مرز شبکه و lock خود را کنترل می‌کنند. اجرای قبلی می‌توانست thread و lock را به تست بعدی نشت دهد؛ اجرای تازهٔ مشترک Clean IP/مرورگر ۱۰۲ passed داشت.
- بررسی تصویری نشان داد CARTO با HTTP 200 تصویر «API KEY REQUIRED» می‌دهد. دو منبع عمومی OpenStreetMap جایگزین شدند و منوی منبع و کش PWA هماهنگ شدند. بررسی نهایی بدون interception، خیابان واقعی را نمایش داد. [گزارش فرانت‌اند](frontend-review.md) و [تصویر موبایل](evidence/shipping-snap-mobile.png).

## شواهد تازهٔ اجرا

[نتایج ساخت‌یافته](verification.json) و [لاگ کامل backend](evidence/backend-full.txt) ثبت شده‌اند. شکست‌های قبلی پنهان نشده‌اند: اجرای اولیهٔ سشن قبل ۲۲۷۸ passed / ۳ failed / ۳ skipped، و اجرای نهاییِ قطع‌شده از نظر گفتگو ۲۳۲۷ passed / ۵ failed / ۲ skipped داشت. اجرای تازه پس از اصلاح جداسازی و تثبیت فایل‌ها:

| بررسی | نتیجهٔ واقعی | شاهد |
|---|---|---|
| تمام backend با coverage | **۲۳۳۴ passed، صفر failed، ۲ skipped، ۲ subtest passed**؛ ۴۱۷٫۸۶ ثانیه | [لاگ](evidence/backend-full.txt) |
| integration با PostgreSQL/Redis واقعی آزمایشی | **۸ passed**؛ ۱٫۲۵ ثانیه | [لاگ](evidence/integration.txt) |
| Ruff | exit 0 | [لاگ](evidence/ruff.txt) |
| Black | ۴۲۶ فایل بدون تغییر، exit 0 | [لاگ](evidence/black.txt) |
| mypy | ۲۱۶ فایل، exit 0 | [لاگ](evidence/mypy.txt) |
| frontend lint / typecheck | هر دو exit 0 | [lint](evidence/frontend-lint.txt)، [typecheck](evidence/frontend-typecheck.txt) |
| frontend tests / build | **۵۵ passed**؛ build موفق، ۲۱ صفحه | [تست](evidence/frontend-test.txt)، [build](evidence/frontend-build.txt) |
| Chrome دسکتاپ و موبایل | همه assertionها موفق؛ `page_errors=[]` | [نتایج](evidence/frontend-browser-final-results.json) |
| migration042 | ارتقای کامل، downgrade به041 و re-upgrade روی PostgreSQL16.15 موفق | [upgrade](evidence/migration-up.txt)، [برگشت](evidence/migration-down.txt)، [اجرای مجدد](evidence/migration-reup.txt) |
| pip-audit با Python3.11 | آسیب‌پذیری شناخته‌شده گزارش نشد، exit 0 | [لاگ](evidence/pip-audit.txt) |
| Bandit `-ll -ii` | صفر Medium/High؛ **۳۰۸ Low خارج این گیت** | [لاگ](evidence/bandit.txt) |
| npm audit کامل | **exit 1؛ ۸ high** در زنجیره braces | [نتایج](evidence/frontend-audit.json) |
| npm audit runtime | صفر آسیب‌پذیری شناخته‌شده، exit 0 | [نتایج](evidence/frontend-audit-runtime.json) |

پوشش statement برابر **۶۵٫۰۲٪** است؛ پاس شدن تست‌ها ادعای نبود هرگونه نقص در پروژه نیست. دو skip عبارت‌اند از probe اختیاری زنده UTCMS بدون opt-in و آزمون OCR نیازمند `KERAS_OCR_SAMPLE_IMAGE`. تست‌های حذف‌شده با skip مخفی نشده‌اند. backend محلی Python3.12 روی macOS است؛ CI Python3.11/Linux باید جداگانه بررسی شود.

Browser از build واقعی وب و API fixture با داده مصنوعی استفاده کرد: ورود از UI، فیلتر راننده و روز تهران، صفحه‌بندی، جلوگیری از پاسخ دیررس timeline، پیام درستِ رد شروع/پایان حمل، مختصات مؤثر مسیر، غیرفعال بودن شروع با مسیر نامعتبر، پاک‌سازی state هنگام تعویض حساب، ۲۰ رکورد مستقل سوخت و نبود overflow موبایل بررسی شدند. این شواهد، عملکرد سرور واقعی یا ثبت UTCMS نیستند.

## محدودیت‌ها و گیت استقرار

1. **آمادگی کامل دیپلوی تأیید نمی‌شود.** advisory [GHSA-vfj7-8cjw-p6xm](https://github.com/advisories/GHSA-vfj7-8cjw-p6xm) همه نسخه‌های braces تا3.0.3 را در بر می‌گیرد و `first_patched_version=null` است؛ آخرین نسخه registry نیز3.0.3 است. ۸ مدخل high مسیرهای وابستگی ابزار build/lint هستند، نه ۸ exploit مستقل. ارتقای شکستن سازگاری یا حذف حفاظت audit برای سبز کردن نتیجه انجام نشد. `ci-cd.yml` این audit را مسدودکننده دارد؛ `ci-test.yml` از قبل این مرحله را continue-on-error اجرا می‌کرد.
2. Docker Desktop محلی راه‌اندازی شد و buildهای Linux/amd64 برای هر دو image اجرا شدند؛ نتیجه در بخش نهایی build تکمیل می‌شود. هیچ container عملیاتی BarPro راه‌اندازی و هیچ deploy انجام نشد.
3. rollout نیازمند migration042 و نسخه هماهنگ API/scheduler/worker است. ورکر قدیمی با صدور inline باید drain شود؛ سند قدیمی بدون challenge معتبر خودکار صادر نمی‌شود. سفر با شروع نامعلوم نیازمند reconciliation/بررسی اپراتور است؛ مسیر خودکار جدید برای رفع آن ادعا نمی‌شود.
4. وضعیت Linux/Android زنده، APK، خروجی ایران، firewall بیرونی و ظرفیت production بررسی نشده‌اند. پیش‌فرض یا گزارش تاریخی جای probe تازه را نمی‌گیرد. `ALLOW_LIVE_SUBMIT` و Android پیش‌فرض ایمن خود را حفظ کردند.
5. HTTPS و تنظیمات cookie باید مطابق استقرار واقعی تأیید شوند. برای ظرفیت باید latency، طول اشغال قفل، retry، نرخ موفقیت، backlog و RSS زیر بار ثبت شوند؛ اعداد فرضی پیوست اندازه‌گیری نیستند.

اسکن مهرشدهٔ امنیتی ۲۰۲۶-۱۰-۰۶ روی مبنای قدیمی حفظ شده است. رگرسیون‌های جدید و گیت‌های این گزارش اسکن کامل تازهٔ امنیتی یا اثبات وضعیت production نیستند. شواهد تفصیلی OTP در [بازبینی امنیت و OTP](otp-security-review.md) آمده‌اند.

## بررسی انتشار

[بررسی secretهای تغییرات](publication-secret-review.md) ۶۸ تطبیق در ۲۶ فایل جدید/تغییرکرده را بررسی کرد؛ اعتبارنامه production شناسایی نشد. ۹۵ تطبیقِ baseline بدون تغییر بازبینی کامل نشده‌اند. نمونه‌های CI و reproduction از قبل آزمایشی و جدا از `.env` هستند. [اثر انگشت فایل‌های منبع](source-fingerprints.json) برای تطبیق نسخه بررسی‌شده ثبت شد.

دو artifact تاریخی، newline انتهایی اضافه دارند؛ محتوای مهرشده برای حفظ hash دست‌نخورده ماند. بررسی whitespace با `git -c core.whitespace=-blank-at-eof diff --cached --check` موفق است؛ این استثنا مربوط به artifact است، نه خطای formatter کد.

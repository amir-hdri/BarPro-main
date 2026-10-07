# ممیزی فرانت‌اند و قراردادهای API — ۲۰۲۶-۱۰-۰۶

مبنای کد: `6c5564e`؛ تغییر UI اخیر: `db3538a`. این ممیزی فقط بررسی و تولید شواهد است؛ هیچ فایل اجرایی برنامه اصلاح نشده، هیچ درخواست UTCMS اجرا نشده و هیچ داده واقعی مستاجر در fixtureها استفاده نشده است.

اسکیل‌های خوانده‌شده: `fullstack-production-audit` و `barpro-ui-ux-guard`؛ مرجع اولیه `docs/BARPRO_KNOWLEDGE_GRAPH.md`. ابزارهای اجرا: npm، Python محیط `.venv`، QueryClient/QueryObserver واقعی نصب‌شده، CUA in-app browser و Chrome DevTools Protocol. سه تلاش اولیه Playwright/رهگیری مرورگر محدودیت ابزار داشتند؛ شواهد نهایی زیر از موارد موفق جدا هستند.

## یافته‌های راستی‌آزمایی‌شده

### F1 — P1: کش فهرست رانندگان به مستاجر مقید نیست و هنگام خروج پاک نمی‌شود

- محل: `apps/web/src/app/drivers/page.tsx:91` (`queryKey: ['drivers']`) و `:99` (`staleTime: 120000`)، `apps/web/src/providers/QueryProvider.tsx:11` (یک QueryClient پایدار)، `apps/web/src/app/layout.tsx:46` (provider در layout ریشه)، `apps/web/src/lib/auth.ts:70` و `:47` (خروج/ورود فقط storage و event را تغییر می‌دهند)، `apps/web/src/components/layout/AppShell.tsx:34` و `apps/web/src/app/auth/page.tsx:37` (ناوبری App Router).
- اثر: در تعویض حساب در همان اپ React، داده tenant قبلی می‌تواند به حساب جدید نمایش داده شود. فهرست رانندگان شامل نام، تلفن، کد ملی و شناسه UTCMS است (`app/schemas/multitenant.py:254`). این یافته درباره کش محلی است؛ عبور از مالکیت backend یا سرقت داده از دستگاه دیگر ادعا نمی‌شود.
- بازتولید: `node docs/audits/2026-10-06/frontend-cache-probe.mjs`، exit 0. QueryClient/QueryObserver واقعی، queryKey و staleTime فعلی را به کار می‌گیرد. خروجی: `signed_in_tenant=B, displayed_cached_tenant=A, api_requests=[A], stale_time_ms=120000`. سپس همین probe در کپی مستقل با `npm ci`، Node **20.20.2** و نسخه دقیق lock یعنی Query **5.100.9** تکرار شد و همان نتیجه را داد (`frontend-clean-cache-probe.log`).
- حد اثبات: سازوکار کتابخانه در runtime + مسیر کد تأیید شد. تعویض حساب end-to-end در مرورگر به دلیل تداخل fixture با RSC نتیجه قطعی نداد و **browser-verified نیست**.
- اقدام پیشنهادی: scope همه queryKeyهای tenant به هویت معتبر مستاجر/role، cancel و clear داده‌های حساس هنگام تغییر نشست، و یک آزمون تعویض حساب واقعی با پاسخ‌های جداگانه API.

### F2 — P2: راهنمای تازه SMS Forwarder مرحله احراز هویت اجباری را حذف کرده است

- محل: `apps/web/src/app/drivers/page.tsx:982` و `:1024` تا `:1033`. راهنما فقط نصب برنامه، فیلتر فرستنده و Webhook POST+URL را می‌دهد. URL هیچ credential ندارد. backend پیش از خواندن body، `_require_webhook_auth` را اجرا می‌کند (`app/api/routes/otp_forwarder.py:212`) و درخواست بدون token را رد می‌کند (`:47` تا `:76`). راهنمای موجود backend برعکس مرحله header را دارد (`:635` و `:659`).
- اثر: کاربر با پیروی دقیق از سه مرحله جدید قادر به تحویل SMS نیست؛ داشتن شماره در URL جایگزین auth نیست.
- بازتولید: modal واقعی در عرض ۱۴۴۰ و ۳۹۰ دیده شد؛ متن کامل در `frontend-browser-evidence.json` و تصویرها ثبت است. `.venv/bin/python docs/audits/2026-10-06/frontend-contract-probes.py` با Request و config مصنوعی روی تابع واقعی: بدون token و secret تنظیم‌شده **401**؛ secret خالی **503**. هیچ تماس Redis/HTTP واقعی انجام نشد.
- اقدام پیشنهادی: UI را به قرارداد یکپارچه setup/config متصل کنید؛ وجود secret، header لازم، قالب payload و تست HEALTH_CHECK را به‌صورت امن و متناسب با مجوز کاربر توضیح دهید. انتشار secret سراسری به همه مستاجرها راه‌حل مناسب این نقص نیست.

### F3 — P2: دکمه «کپی آدرس» جدید در HTTP عادی خطا می‌دهد

- محل: `apps/web/src/app/drivers/page.tsx:989` تا `:995`؛ فراخوانی مستقیم `navigator.clipboard.writeText(url)` بدون تشخیص قابلیت، await یا catch.
- اثر: در HTTP غیر-loopback API clipboard موجود نیست؛ فراخوانی متد روی undefined خطا می‌دهد. در محیط secure هم ردشدن Promise مدیریت نمی‌شود و پیام موفقیت قبل از تأیید copy نمایش داده می‌شود.
- بازتولید: همان build محلی از آدرس HTTP شبکه دستگاه (`http://172.20.10.2:3106`) در CUA بارگذاری شد. CDP واقعی نتیجه داد: `isSecureContext=false`, `clipboardAvailable=undefined`, `writeTextAvailable=undefined`. این بررسی **استقرار production را مشاهده نکرده**؛ قرارداد HTTP مستند پروژه را به‌صورت محلی بازتولید کرده است. خروجی در `frontend-browser-evidence.json`.
- اقدام پیشنهادی: feature detection، مدیریت نتیجه async، و fallback انتخاب/کپی دستی روی HTTP؛ موفقیت را فقط پس از copy موفق اعلام کنید.

### F4 — P2: دو نمایش «آمادگی دریافت OTP» می‌توانند در حالت غیرفعال مثبت باشند

- UI: `apps/web/src/app/history/page.tsx:1805` همواره «دریافت خودکار از فورواردر پیامک فعال است» نشان می‌دهد. هیچ اتصال به `/otp/health`، `/otp/ping`، `/otp/securesms-config`، وضعیت آخرین تحویل یا heartbeat گوشی ندارد. تشکیل پیش‌نویس و نیاز به OTP، سلامت فورواردر را ثابت نمی‌کند.
- API جدید: `app/api/routes/otp_forwarder.py:556` تا `:573` سلامت را فقط به Redis ping می‌بندد. `OTP_WEBHOOK_SECRET` خالی باشد، health همچنان `healthy` می‌دهد، ولی همان سرویس همه intakeها را 503 می‌کند (`:55` تا `:58`).
- بازتولید: `frontend-contract-probes.py` با تابع واقعی health و Redis mock سالم: `secret_configured=false, health_status=healthy, post_intake_status=503`؛ بررسی JSX ثابت و نبود درخواست سلامت نیز assertion دارد. **این آزمون شامل قطع سرویس واقعی یا گوشی واقعی نیست**.
- اقدام پیشنهادی: connectivity، readiness واقعی intake و وضعیت آخرین اتصال/تحویل گوشی را جدا و صریح نمایش دهید؛ readiness secret و وابستگی‌های لازم را بررسی کند؛ UI حالت «نامشخص/پیکربندی نشده» داشته باشد.

### F5 — P2: تست‌های فرانت‌اند در CI اجرا نمی‌شوند و روی Node 20 نیز راه نمی‌افتند

- `apps/web/package.json:13` اسکریپت `npm test` را تعریف می‌کند، اما `.github/workflows/ci-test.yml:130` تا `:167` تنها install/lint/audit/typecheck/build دارد؛ `.github/workflows/ci-cd.yml` نیز `npm test` یا `node --test` ندارد. جستجوی تمام workflowها همین نتیجه را داد.
- خروجی واقعی محلی `npm test`: **35 passed / 0 failed** (`frontend-test.log`). این موفقیت محلی از اجرای تست در CI خبر نمی‌دهد. بخشی از تست‌ها منطق را کپی می‌کنند، برای نمونه `apps/web/test/gps-anchors.test.mjs` و `plate.test.mjs`؛ در مقابل `tracking-ack.test.mjs` و `gps-anchor-parity.test.mjs` فایل واقعی TypeScript را import می‌کنند. این دو دسته وزن اثبات برابر ندارند.
- CI از Node 20 استفاده می‌کند (`ci-test.yml:15`, `ci-cd.yml:18`). پس از `git archive` و `npm ci` در پوشه مستقل، اجرای `npm test` با Node **20.20.2**، **exit 1** داد: `Could not find .../test/**/*.test.mjs` (`frontend-clean-test.log`). اسکریپت discovery فعلی روی این runtime اجرا نمی‌شود.
- برای جداکردن مشکل glob از اجرای واقعی، فایل‌ها صریحاً به `node --test` داده شدند: **11 passed / 2 failed**؛ دو فایل دارای import واقعی `.ts` با `ERR_UNKNOWN_FILE_EXTENSION` برای `src/lib/format.ts` شکست خوردند (`frontend-clean-test-explicit-files.log`). بنابراین اصلاح glob به‌تنهایی کافی نیست.
- اقدام پیشنهادی: اسکریپت discovery و اجرای TypeScript را با Node هدف سازگار کنید یا runtime رسمی پروژه را هماهنگ ارتقا دهید؛ سپس suite واقعی را در CI اجرا کنید. نسخه کپی‌شده helper جایگزین آزمون کد واقعی نیست.

### F6 — P1 برای گیت dependency: npm audit رد می‌شود؛ بهره‌برداری از محصول اثبات نشده است

- در نصب مستقل از lock با `npm ci`، `npm audit --audit-level=moderate` exit **1**: **20 vulnerabilities: 1 critical, 16 high, 3 moderate**. جزئیات و advisory URLها در `frontend-clean-audit.log`. نصب قدیمی workspace تعداد 19 را نشان می‌داد؛ تفاوت، مسیر وابستگی `@eslint/eslintrc → js-yaml` بود. نتیجه clean مبنای نهایی گزارش است.
- نسخه lock و نصب برای موارد اصلی یکسان بود: Next **15.5.23**، Axios **1.18.0**، Sharp **0.35.0** (`frontend-installed-versions.log`). npm audit، Next را critical گزارش می‌کند؛ گزارش شامل advisory مخصوص **Windows hosting** و advisory **AVIF/Image Optimization** است.
- applicability: هدف Docker/Linux پروژه با advisory مخصوص Windows مطابقت ندارد. `apps/web/next.config.mjs:59` مقدار `remotePatterns: []` دارد. مصرف‌های `next/image` در Header، Sidebar، auth و admin layout از لوگوی SVG داخلی استفاده می‌کنند؛ فایل AVIF/HEIC/HEIF در `apps/web/public` یافت نشد. مسیر ورود فایل AVIF تحت کنترل مهاجم در این بررسی اثبات نشد؛ از وجود نسخه آسیب‌پذیر، RCE قابل‌بهره‌برداری فعلی نتیجه نمی‌گیریم.
- Axios advisoryها ترکیبی از adapterهای Node، prototype pollution gadget و proxy/redirect هستند؛ SSRF یا آلودگی prototype از مسیرهای این اپ اثبات نشده است. این موارد **وجود advisory و شکست گیت** را ثابت می‌کنند، نه سوءاستفاده انجام‌شده.
- CI اصلی `ci-cd.yml:68` audit را blocking اجرا می‌کند؛ در `ci-test.yml:156` همان بررسی `continue-on-error: true` است. بنابراین سبزبودن workflow دوم به‌تنهایی عبور گیت امنیت dependency نیست.
- اقدام پیشنهادی: ارتقای کنترل‌شده نسخه‌ها و overrideها با بررسی سازگاری و اجرای مجدد build/tests/audit؛ اجرای کور `npm audit fix --force` مناسب نیست، زیرا خروجی تغییرات شکستن سازگاری Tailwind را نیز پیشنهاد می‌دهد.

## خروجی گیت‌ها و حدود آن‌ها

گیت نهایی زیر در کپی مستقل `git archive HEAD`، پس از `npm ci` موفق، با **Node 20.20.2** و نسخه‌های دقیق lock اجرا شد. مسیر temp و commit در `frontend-clean-environment.json`، نسخه‌ها و exit codeها در `frontend-clean-results.json` ثبت است. کپی اصلی و node_modules آن جایگزین نشد.

| گیت | خروجی واقعی | فایل |
|---|---|---|
| `npm ci` | exit 0؛ 650 بسته نصب شد | `frontend-clean-install.log` |
| `npm run lint` | exit 0 | `frontend-clean-lint.log` |
| `npm run typecheck` | exit 0 | `frontend-clean-typecheck.log` |
| `npm test` | exit 1؛ glob کشف نشد | `frontend-clean-test.log` |
| `node --test` با نام‌های صریح | exit 1؛ 11 passed / 2 failed، import .ts | `frontend-clean-test-explicit-files.log` |
| `npm run build` | exit 0؛ 21 صفحه static؛ Next 15.5.23 | `frontend-clean-build.log` |
| `npm audit --audit-level=moderate` | exit 1؛ 20 advisory package findings | `frontend-clean-audit.log` |
| اسکریپت UI guard | exit 1؛ یک inline style | `frontend-ui-audit.log/json` |
| probe قرارداد OTP | exit 0؛ 4 مشاهده/assertion | `frontend-contract-probes.log` |
| probe کش QueryClient دقیق lock | exit 0؛ داده tenant A در scope B | `frontend-clean-cache-probe.log` |

تخلف UI guard موجود: `apps/web/src/components/DriverTrackingPanel.tsx:111` از `style={{ width: ... }}` استفاده می‌کند. این تخلف استاندارد پروژه است؛ در این ممیزی آن را به‌عنوان خرابی کارکرد یا خطر امنیتی رتبه‌بندی نکردیم.

گیت مرورگر modal رانندگان: viewportهای **1440×1000** و **390×844**، `dir=rtl`، font Vazirmatn، نبود overflow افقی صفحه، input موبایل **16px**. فایل‌ها: `frontend-drivers-desktop.png`, `frontend-drivers-mobile.png`, `frontend-browser-evidence.json`. صفحه‌های محافظت‌شده با پاسخ‌های مصنوعی و cookie آزمایشی دیده شدند؛ این گیت به معنی صحت احراز هویت backend یا اتصال گوشی نیست.

اجرای اولیه workspace با Node **26.10.0** و symlinkهای pnpm بود؛ در آن lint/typecheck/build سبز و تست‌ها **35 passed** بودند (`frontend-{lint,typecheck,build,test}.log`). React/ReactDOM نصب‌شده آن **19.2.8** در برابر lock **19.2.7** و TanStack Query **5.101.4** در برابر lock **5.100.9** بود. به همین دلیل همه گیت‌ها در کپی clean تکرار شدند و نتیجه نهایی بالا جایگزین فرض اولیه شد. تفاوت macOS محلی با Linux runner و npm محلی **11.19.1** با نسخه runner همچنان باقی است؛ اجرای خود GitHub Actions در این ممیزی مشاهده نشده است. `next start` با output standalone هشدار داد، اما سرویس محلی صفحه‌ها را تحویل داد (`frontend-serve.log`) و پس از آزمون متوقف شد.

محدودیت ابزار: Chromium bundled در Playwright Python موجود نبود؛ Chrome نصب‌شده قابل launch بود، اما آزمون UI از CUA/DevTools انجام شد. دو API عمومی CDP درخواست‌شده توسط tool پشتیبانی نشدند؛ فقط APIهای مجاز بعدی استفاده شدند. fixture عمومی اولیه، درخواست RSC را هم پاسخ داد؛ آن آزمون کنار گذاشته شد و هیچ یافته‌ای از آن استخراج نشده است. تب‌های آزمایشی بسته و viewport بازنشانی شد.

## چک‌لیست تحویل

- [x] diff جدید UI، مسیرهای backend OTP و کش‌های حساس با شواهد فایل بررسی شدند.
- [x] گیت‌های npm واقعاً اجرا و خروجی‌ها بدون پنهان‌کردن failure نگهداری شدند.
- [x] نصب clean با lock دقیق و Node 20 در temp مستقل انجام و گیت‌ها تکرار شدند؛ شکست پنهان suite آشکار شد.
- [x] موارد F2/F3/F4 و سازوکار F1 با probe مستقل یا مرورگر محلی راستی‌آزمایی شدند.
- [x] نسخه آسیب‌پذیر از بهره‌برداری اثبات‌شده تفکیک شد.
- [x] شواهد synthetic از وضعیت production جدا برچسب خوردند.
- [x] هیچ فایل اجرایی برنامه یا secret تغییر نکرد؛ فقط artifactهای ممیزی تولید شد.

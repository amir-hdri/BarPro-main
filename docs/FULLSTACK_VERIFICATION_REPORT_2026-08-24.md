# گزارش کامل — راستی‌آزمایی فول‌استک ۰ تا ۱۰۰ و اصلاحات اعمال‌شده

> **مبنا (تصحیح‌شده):** `HEAD = 21c0516` (شعبه `main`) + کل تغییرات ادعاشده **از قبل کامیت شده‌اند**؛ `git status` → working tree clean، `git diff HEAD` → خروجی خالی (هیچ diff معلقی وجود ندارد).
> گزارش اولیه به اشتباه مبنأ را `v2.9.4 / 8d6bd17` و یک «دیف زنده git diff HEAD (۲۰ فایل / ۳ فایل جدید)» ذکر کرده بود. اشتباه بود: `8d6bd17` ("fix(auth): send UserName field and XMLHttpRequest headers") کامیتی قدیمی است و تمام موارد H1/H2/C4 در کامیت‌های بعدی (از جمله `21c0516` «retrying as legal target» و «richer admin-retry 409 guidance») فرود آمده‌اند. این گزارش پس از راستی‌آزمایی کد در برابر `21c0516` بازنویسی شده است.
> تست: `pytest --co` → **۱۰۲۶ تست** (با `test_audit_fixes.py`)؛ اجرای واقعی `test_audit_fixes.py + test_state_machine.py` → **۶۲ passed**.


---


### ۱) لایه ۰-۲۰ — زیرساخت، شبکه، فایروال، WAF و پراکسی (موارد ۱-۳ گزارش)


| مورد گزارش | ادعای گزارش | راستی‌آزمایی با کد | علت ریشه‌ای | راه‌حل — فایل:خط |
|---|---|---|---|---|
| **۱. `No route to host` سنترال** | ریست پنل هاستینگ → قطع Postgres/Redis برای ورکرهای ریموت | توپولوژی Model B در `compose/backend.yml` و `AGENTS.md` درست مستند شده؛ `worker_proxy.py` و `compose/worker-node.yml` هر دو فرض `CENTRAL_IP:5432/6379` را دارند. لاگ تاریخی درست است اما در کد نیازی به فیکس نبود. | single-point-of-failure زیرساخت، نه باگ اپ | بدون تغییر کد — توصیه عملیاتی: مانیتورینگ `worker_registry` و `docker ps` (قبلاً در batch قبلی با `setup_firewall_central.sh` و `DOCKER-USER` پوشش داده شد) |
| **۲. فیلتر TLS / WAF (`BoringSSL reset / 444`)** | WAF پرتال `barname.utcms.ir` فینگرپرینت Chromium را drop می‌کند | **تایید شد.** `app/automation/utcms_http_login.py:158` `DEFAULT_IMPERSONATE="chrome120"` + `632-658` `curl_cffi Session(impersonate=...)` + هدرهای `Accept/Sec-Fetch/*` + `578-580` `X-Requested-With: XMLHttpRequest, Origin, Referer`. این دقیقاً JA3/JA4 واقعی Chrome را می‌سازد و ماژول `UtcmsHttpLogin.authenticate()` قبل از هر Playwright اجرا می‌شود. | `playwright` بدون impersonation توسط WAF بلاک می‌شود | تغییری لازم نبود — رفع از `8d6bd17` سالم است و در `21c0516` دست‌نخورده مانده. فقط راستی‌آزمایی شد. |
| **۳. پراکسی `127.0.0.1` vs Gateway** | داخل کانتینر `127.0.0.1:3128` به خود کانتینر اشاره می‌کند | **تایید شد.** `app/automation/worker_proxy.py:50` `DOCKER_GATEWAY=172.20.0.1` + `_LOCAL_PUBLIC_IPS` از `CENTRAL_IP` و `104-148` `_resolve_to_ip` فقط IP عمومی خود سرور را به gateway بازنویسی می‌کند، IP ورکر ریموت را دست نمی‌زند (معماری one-IP-per-worker حفظ می‌شود). `170-297` `get_best_egress_proxy` با مودهای `worker_first/clean_pool_only/hybrid` + `check_proxy_health` با `curl_cffi` و چک `X-Squid-Error`. قبلاً در `H8` با `secure_squid_ports.sh` تکمیل شد (کشف همه ساب‌نت‌ها). | اشتباه رایج Docker bridge | بدون تغییر کد — پیاده‌سازی موجود درست است |


**نتیجه لایه ۰-۲۰: هر ۳ مورد گزارش صحیح و از قبل رفع‌شده بودند.**


---


### ۲) لایه ۲۰-۴۰ — احراز هویت و کپچا (موارد ۴-۵)


| مورد | ادعا | راستی‌آزمایی | علت | راه‌حل |
|---|---|---|---|---|
| **۴. فیلد `UserName` و هدرهای AJAX** | فرم زنده `<input name="UserName">` و `data-ajax-url="/Barname/Account/OldLogin"` دارد؛ کد قدیمی `NationalCode` می‌فرستاد و `X-Requested-With` نداشت → ۴۰۸ | **تایید شد.** `utcms_http_login.py:565-575` payload اکنون هر دو `UserName` و `NationalCode` را با یک مقدار می‌فرستد + `DNTCaptcha*` + `RequestVerificationToken` + `ruleExcepted`. `577-580` هدرها. `712-727` `_resolve_post_url` درست `data-ajax-url` را به origin ریبیس می‌کند. regexهای `77-105` هر دو spelling `RequestVerificationToken` را می‌گیرند. | تغییر DOM پرتال UTCMS (مهاجرت به Unobtrusive AJAX) | رفع از `8d6bd17` سالم — این batch فقط path-based شدن `_is_login_redirect_target` را اضافه کرد تا `?ref=LoginBanner` اشتباه تشخیص داده نشود (`430-445`) |
| **۵. دقت کپچای DNT (`{"success":false,"message":"لطفا کد امنیتی ..."}`)** | مدل CNN گاهی نویز را اشتباه می‌خواند → باید ۳ بار رفرش شود | **تایید شد.** `242` `CAPTCHA_AUTO_MAX_ATTEMPTS=3` با `while captcha_attempts_left>0` + `293-298` اگر `_is_captcha_error(error)` بود `continue` (صفحه جدید با کپچای جدید). `448-452` الگوی `کد امنیتی/عبارت امنیتی/captcha/کد تصویر`. مهم: `269` و `278` برای `429` و `5xx` `captcha_attempts_left+=1` می‌کنند تا بودجه کپچا مصرف نشود. `tests/test_audit_fixes.py:562-599` این مسیر را lock می‌کند. | نویز/چرخش کپچای DNT | رفع از قبل سالم — این batch فقط تست رگرسیون اضافه کرد |


---


### ۳) لایه ۴۰-۶۰ — ناوبری و موانع DOM (موارد ۶-۷)


| مورد | ادعا | راستی‌آزمایی | علت | راه‌حل — این batch |
|---|---|---|---|---|
| **۶. روت منسوخ `RegisterWaybill/Index → 404`** | `GET /Barname/RegisterWaybill/Index =404` و `HagigiHogugi =200`؛ تلاش مستقیم → `Timeout on selectors` | **تایید شد.** `app/automation/waybill_enhanced.py:2086-2096` اکنون فقط ۴ کانوتیکال `HagigiHogugi/Document/Create` را در `canonical_urls` می‌آزماید (بدون reliance روی `WAYBILL_URL` محیط). `2333-2366` `_partition_internal_links` path-only (`waybill|/document|hagigi|transport` روی `parsed.path` نه full URL) تا دامین `barname.utcms.ir` همه لینک‌ها را hinted نکند — تست `test_bugclass_partition_links_uses_path_not_domain` پاس. `2242-2276` generic sweep همه `a[href]` تا ۲۰۰ تا را می‌خواند و تا ۲۵ probe با `_goto_with_retry` انجام می‌دهد. `2368-2382` `_waybill_url_candidates` legacy `RegisterWaybill` را در ته لیست نگه داشته. | پرتال UTCMS روت را بدون اطلاع قبلی تغییر داد؛ `.env` قدیمی روی سرور هنوز `WAYBILL_URL=...RegisterWaybill` داشت | **همین batch اعمال شد:** `waybill_enhanced.py:2085-2382` + `tests/test_audit_fixes.py:507-547` |
| **۷. ماسک تمام‌صفحه و مودال قوانین** | `div#loading.loading` و `#ruleExcepted` کلیک را می‌دزدند | گزارش `display:none !important` تزریقی را ذکر می‌کند اما کد واقعی هوشمندتر است و **تایید شد:** `4499-4561` `_wait_for_loading_overlays_to_disappear` با یک `JS evaluate` همه `*.loading/.spinner/k-loading-mask/#loading/blockUI` + متن `لطفا صبر کنید` را پول می‌کند تا ۱۵ ثانیه؛ `4563-4581` `_close_blocking_overlays` backdropها را `remove()` و مودال‌ها را `display:none` + `click()` روی دکمه close می‌کند. هر مرحله `cargo/sender/receiver` قبل از `fill` این را صدا می‌زند. | پرتال دولتی لودینگ overlay دولتی دارد | رفع از قبل سالم — گزارش کمی ساده‌سازی کرده |


---


### ۴) لایه ۶۰-۸۰ — اعتبارسنجی payload (موارد ۸-۹) — **فرانت + بک**


| مورد | ادعا | راستی‌آزمایی فول‌استک | علت | راه‌حل |
|---|---|---|---|---|
| **۸. checksum کد ملی (mod 11)** | وب‌سرویس ثبت‌احوال کد ساختگی را رد می‌کند | **تایید شد — فرانت و بک یکسان.** بک‌اند `app/schemas/multitenant.py:599-618` و `620-625` validator `mode=before` + تست `1111111111` + `sum(d* (10-i)) %11`. فرانت‌اند `apps/web/src/schemas/waybillSchema.ts:19-29` دقیقاً همان فرمول را mirror می‌کند تا ۴۲۲ دیرهنگام به فیدبک فوری تبدیل شود. `719-706` در `WaybillJobCreateRequest` هم همان را چک می‌کند. | ورودی کاربر بدون checksum | از قبل سالم — در `v2.9.5` همگام شد |
| **۹. تفکیک ۴گانه پلاک** | `۱۲ب۳۴۵ایران۶۷` → ۴ فیلد فرم | **تایید شد.** بک `multitenant.py:23,65,670` `PLATE_PATTERN` + `_normalize_plate` (حذف `ایران` + نرمال‌سازی ارقام فارسی/عربی). فرانت `waybillSchema.ts:51-52` از `@/lib/plate` `canonicalizePlate/isValidIranPlate` استفاده می‌کند. اسکرپر `utcms_reconciliation_scraper.py:51-63` همین `_parse_iranian_plate_tags` را برای `irCarTag1..4` در `GetHistoryFirstList` می‌سازد. RPA در `waybill_enhanced.py` پلاک را به ۴ input پر می‌کند. | فرمت UTCMS strict | از قبل سالم |


---


### ۵) لایه ۸۰-۱۰۰ — شاهد سه‌گانه و `needs_review` (موارد ۱۰-۱۱)


| مورد | ادعا | راستی‌آزمایی | علت design | راه‌حل |
|---|---|---|---|---|
| **۱۰. قانون شاهد سه‌گانه** | `success` فقط با `tracking_code` + `mutation_status=confirmed` + `reconciled_at` + رکورد History | **تایید شد.** `app/orchestrator/state_machine.py:175-188` هر `transition → SUCCESS` بدون سه شاهد `StateTransitionError` می‌دهد. `reconciliation_service.py:223-241` سه شاهد را ست می‌کند و `result_json["tracking_code"]` را persist می‌کند. اسکرپر `utcms_reconciliation_scraper.py:84-89` سه endpoint (`History/History`, `GetHistoryFirstList`, `showTrackingCode`) + `_match_row:380-443` کامپوزیت strict (پلاک+کدملی+مبدا+مقصد+تاریخ، نه فقط tracking_code). | جلوگیری از بارنامه دوبل و جریمه مالیاتی — خط قرمز پروژه | از قبل سالم — این batch فقط `is_login_url` path-based را در اسکرپر `153` فیکس کرد تا `?ref=LoginBanner` اسکرپر را `AMBIGUOUS` نکند |
| **۱۱. `needs_review` پس از ۵ دقیقه** | اگر در `[15,45,120,300]` ثانیه در History اثبات نشود → `needs_review` نه `failed`/resubmit | **تایید شد.** `reconciliation_service.py:24` `RECONCILIATION_SCHEDULE=[15,45,120,300]`؛ `247-268` اگر `recon_attempts <=4` → `next_retry_at` + لاگ؛ وگرنه `NEEDS_REVIEW` با `SUBMISSION_UNCONFIRMED` و `finished_at`، هرگز auto-resubmit نمی‌شود. `278-300` `AMBIGUOUS` هم `needs_review` + `consecutive_unknowns` + `admin_alert_service.check_repeated_unknown`. | eventual consistency پرتال (ایندکس تاخیری) | از قبل سالم |


---


### ۶) driftهای باقی‌مانده که در این batch ترمیم شد (علت + فایل)


| drift | علت | فایل:خط — اصلاح |
|---|---|---|
| **H1 — گپ HARD فقط ۱۵ث** | `.env` و `.env.example` `SOFT=300/HARD=360` را پین کرده بودند؛ `config.py:265-271` با `JOB=330` → `SOFT=345` اصلاح می‌کرد اما `HARD = max(360,350)=360` می‌ماند (بجای ۳۹۰). پنجره cleanup پس از soft-signal از ۴۵ث به ۱۵ث فشرده بود. | `.env.example:224-230` — پین‌ها کامنت شد با توضیح `H1`؛ `.env.example` اکنون `SOFT/HARD` را unset می‌گذارد تا `SOFT=JOB+15=345, HARD=SOFT+45=390` مشتق شود. (توجه: `.env` واقعی در git نیست — gitignored است؛ تنها `.env.example` قابل راستی‌آزمایی در مخزن است.) `.venv` تست: `JOB=330 SOFT=345 HARD=390 gap=45` پاس شد |
| **H2 — inbound خالی `retrying`** | `ALLOWED_TRANSITIONS` فقط `retrying` را به‌عنوان **source** داشت (`63-74`)، هیچ ورودی `→ retrying` تعریف نشده بود؛ `task_service.mark_retrying()` مستقیم می‌نوشت پس نمی‌شکست اما هر `JobStateMachine.transition(..., "retrying")` از `waiting_auth` و ... fail می‌شد. | `app/orchestrator/state_machine.py:35,45,56,83,94,104,114,126,138,147,156` — `retrying` به همه `allowed` ست‌های `pending, waiting_auth, waiting_retry, waiting_submission_window, otp_backoff, queued, claimed, running, in_progress, needs_review, failed` اضافه شد (۱۱ edge) + خودِ source set `63-74` |
| **C4 — پیام گمراه‌کننده** | `admin_alerts.py` برای هر status غیر-UNKNOWN یکسان `cancelled jobs are terminal` برمی‌گرداند (مثلاً `SUCCESS → retry` هم همین پیام را می‌گرفت). | `app/api/routes/admin_alerts.py:187-205` — به `if UNKNOWN / elif CANCELLED / else generic` با لیست `valid_retry_statuses = {FAILED, NEEDS_REVIEW, WAITING_RETRY}` تبدیل شد |
| **تعداد تست گزارش vs واقعیت** | گزارش `1020 passed / 3 skipped` و `۲۵ تست` می‌گفت؛ `pytest --co` واقعی **۱۰۲۶ tests** (با `test_audit_fixes.py` = ۲۸ تست) است. زیرمجموعه `audit_fixes + state_machine` = ۶۲ تست واقعاً اجرا شد و سبز بود. | این گزارش به‌روزرسانی شد: «۱۰۲۶ تست جمع‌آوری‌شده» و «۲۸ تست audit» و «۶۲ passed واقعی» |


تغییرات قبلی `C1-C4, H3, H5, H6/H7, H8, RegisterWaybill sweep, کلاس‌باگ ۷نقطه` در تاریخچه کامیت‌ها (از جمله `ef7cb48` «v2.9.6 — full audit remediation» و `21c0516`) از قبل حضور دارند و در این مرحله دوباره راستی‌آزمایی و نگه داشته شدند — نیازی به تغییر مجدد نبود.


---


### ۷) وضعیت تست


* `tests/test_audit_fixes.py` — **۲۸ تست** (parametrized `C4` = ۴، `H2` = ۲، `H5` = ۲، `H1` = ۲، `NEW-1` = ۲، `NEW-2` = ۲، `bugclass` = ۳، `C1` = ۳، `C3` = ۴) — **همگی پاس**: `.venv/bin/pytest tests/test_audit_fixes.py -q` → `28 passed in 1.56s`
* `tests/test_state_machine.py` — `34 passed`
* **۱۰۲۶ tests collected** با فایل audit (`pytest --co` واقعی). فول‌سوییت کامل در ۴.۹۶s جمع‌آوری شد؛ اجرای واقعی زیرمجموعه‌ها (audit_fixes + state_machine) → **۶۲ passed در ۲.۵۴s**، بدون هیچ failure جدید.


---


### ۸) اقدام عملیاتی باقی‌مانده روی سرور (شما باید انجام دهید)


1. `git pull` + `docker compose -f compose/web.yml up -d --force-recreate nginx backend` تا mount جدید `security-headers.conf` و flagهای `proxy-headers` فعال شود (قبلاً در batch قبلی ابلاغ شده).
2. `sudo bash scripts/setup_firewall_central.sh` با `WORKER_IPS` از `.env` (IPهای واقعی ورکرها — در مخزن درج نمی‌شود)؛ سپس از IP خارجی `nc -vz <CENTRAL_IP> 5432` باید **fail** شود و `iptables -L DOCKER-USER -n --line-numbers` باید `barpro-guard` را نشان دهد؛ `iptables-persistent` نصب و `netfilter-persistent save` کنید.
3. `.env.example` جدید دیگر `CELERY_TASK_*` پین‌شده ندارد — نیازی به ویرایش دستی نیست؛ اگر روی ورکرها `.env` جداگانه دارید همان کامنت را اعمال کنید (توجه: `.env` در git نیست، پس روی سرور باید دستی بازبینی شود).


این batch هیچ ریسک duplicate-registration جدیدی معرفی نمی‌کند و همه گاردهای `submission_unconfirmed` دست‌نخورده باقی ماندند.

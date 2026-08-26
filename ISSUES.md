# BarPro — وضعیت مشکلات (Issues)
**آخرین بروزرسانی: 2026-08-26 (v2.9.7 — بازسازی Pipeline استخر IP پاک)**

> مرجع وضعیت سامانه و محدودیت‌های مشاهده‌شده: [docs/UTCMS_CONSTRAINTS.md](./docs/UTCMS_CONSTRAINTS.md)

## 🆕 2026-08-26 — ریشه‌یابی زنده: چرا Clean IP Extractor جواب نمی‌داد (v2.9.7)

> راستی‌آزمایی روی سرور مرکزی انجام شد؛ یافته‌ها با کد تطبیق داده شد. مشکل «یک Bug» نبود — ترکیبی از
> selection concentration + probe غیرنماینده + نبود حقیقت جغرافیایی + cache کهنه بود.

| # | یافته (تأیید زنده/کد) | وضعیت | اصلاح |
|---|---|---|---|
| P0-1 | انتخاب همیشه `ips[0]` بود → کل ناوگان از «یک» پروکسی عبور می‌کرد؛ الگویی که کاربر موبایل هرگز تولید نمی‌کند و WAF آن را جریمه می‌کند | ✅ | Round-robin روی کل استخر در `get_clean_ip`/`get_clean_ip_sync` |
| P0-2 | لاگ زنده‌ی Beat: سیکل‌های «verified 0» متناوب با «verified 5»؛ TTL ردیس 3600s → بین سیکل‌های موفق، مسیر Sync به فایل best قدیمی برمی‌گشت | ✅ | `_pool_is_stale` + kick پس‌زمینه‌ی refresh از مسیر Sync (`CLEAN_IP_POOL_MAX_AGE_SECONDS=1800`) |
| P0-3 | پروب با urllib (JA3 پایتون) + UA جعلی Chrome = امضای ناسازگار؛ نتیجه‌اش نماینده ترافیک واقعی (curl_cffi/chromium) نبود | ✅ | پروب با همان `chrome120` مسیر Login/Health-check |
| P0-4 | HTTP 403/429 (ردِ IP توسط UTCMS) با «پروکسی مرده» یکی گرفته می‌شد؛ صفحه‌ی چالش WAF با 200 «سالم» شمرده می‌شد | ✅ | `classify_probe_response`: healthy / waf_challenge / target_rejected / unacceptable با جریمه‌های مجزا |
| P0-5 | کشور از metadata منبع فرض می‌شد (حتی لیست‌های global → `country="IR"` پیش‌فرض!)؛ egress واقعی اندازه گرفته نمی‌شد | ✅ | حذف پیش‌فرض IR + `_verify_egress_country` (اندازه‌گیری GeoIP از داخل تونل) + demote غیرایرانی |
| P1-6 | Dedup روی `ip:port` بود → http و socks5 همان آدرس یکی می‌شدند | ✅ | کلید `protocol://ip:port` |
| P1-7 | SOCKS با urllib قابل verify نبود → حذف کاندیداهای خوب | ✅ | curl_cffi socks4/5 native؛ fallback فقط برای http(s) |
| P1-8 | Block شدن پروکسی، کش 60s ورکر را باطل نمی‌کرد → ورکر به IP بلاک‌شده ادامه می‌داد | ✅ | `mark_blocked` → `invalidate_worker_proxy_cache()` فوری |
| P1-9 | خطای clean-pool بدون شناسه‌ی پروکسی، WORKER_IP_INDEX سالم را 30 دقیقه بلاک می‌کرد | ✅ | گارد early-return در circuit breaker |
| P1-10 | `from_dict` بدون اعتبارسنجی state خراب ردیس/فایل را به runtime برمی‌گرداند | ✅ | validate→normalize→accept |
| LIVE | آمار ۷ روزه: 19 waiting(otp)، 10 needs_review(unconfirmed)، 9 failed(TARGET_SITE_TIMEOUT)، 0 success | ⚠️ | نیازمند deploy این نسخه + پایش |

> ⚠️ **Deploy لازم است:** اصلاحات فوق هنوز فقط روی مخزن محلی است. رمز SSH سرورها در چت به‌صورت plaintext رد و بدل شده — **تغییر رمز** پس از پایان کار توصیه می‌شود.

---

## 🆕 2026-08-24 — امنیت، قفل‌های تجدیدپذیر و پاکسازی کامل ممیزی (v2.9.5 / v2.9.6)

| # | مورد | وضعیت | نتیجه |
|---|---|---|---|
| C1 | orphan-sweep می‌توانست job در حال اجرا با lease زنده را بکشد (ریسک duplicate-submission) | ✅ | گارد lease زنده در `app/orchestrator/orphan_detector.py` + bump `updated_at` روی گذارهای claim |
| C2 | تمام ریکوئست‌ها IP یکسان nginx داشتند → باکت نرخ 5/min لاگین «سراسری» و قفل‌شدن سیستمیک | ✅ | uvicorn `--proxy-headers --forwarded-allow-ips=…` (`compose/backend.yml` + `Dockerfile`) |
| C3 | انقضای قفل راننده (`RPA_LOCK_TTL`) در میانه پنجره RPA → ثبت موازی دوبل | ✅ | `renew_lock()` با Lua compare-and-expire + تمدید دوره‌ای ~30s (`rpa_runtime_service.py`) |
| C4 | retry ادمین از UNKNOWN/CANCELLED خطای HTTP 500 قطعی + پیام یکسان گمراه‌کننده | ✅ | 409 با راهنمای per-status + گارد دسته‌های `submission_unconfirmed` (`admin_alerts.py`) |
| H1 | `SoftTimeLimitExceeded` پیش از هندلر `TimeoutError→unknown/reconcile` اجرا می‌شد | ✅ | حدود Celery از `JOB_TIMEOUT_SECONDS` مشتق می‌شوند: SOFT=+15، HARD=SOFT+45 (`config.py`) |
| H2 | گره `retrying` بدون یال ورودی/خروجی → job برای همیشه گیر می‌کرد | ✅ | source set + ۱۱ یال ورودی در `state_machine.py` |
| H3 | `celery_task_id` کهنه در QUEUED/WAITING_AUTH فقط از مسیر deprecated بازیابی می‌شد | ✅ | پاکسازی اثبات‌شده داخل `plan_due_jobs` (`rpa_scheduler_service.py`) |
| H5 | JWT های blacklisted روی dependencyهای sensitive رد نمی‌شدند | ✅ | چک jti-blacklist در `require_sensitive_auth/admin` (`core/security.py`) |
| H6/H7 | صفحات دارای `add_header` محلی بدون CSP/X-Frame سرو می‌شدند؛ 404 مسیرهای proxies/circuit-breaker | ✅ | include مشترک `infra/nginx/security-headers.conf` + افزودن مسیرها به regex بک‌اند |
| H8 | UFW به‌تنهایی پورت Docker-publish شده را نمی‌بندد (اثبات عملی زنده) | ✅ | قوانین مدیریت‌شده `DOCKER-USER` در سه اسکریپت فایروال + رفع self-DoS اسکوئید host-network |
| NEW-1 | روت منسوخ `/Barname/RegisterWaybill/Index` → 404 و Timeout سلکتورها | ✅ | کاندیدهای کانونی + sweep عمومی لینک‌ها با partition مسیری (`waybill_enhanced.py`) |
| NEW-2 | retry کپچای غلط پس از پاسخ AJAX «لطفا کد امنیتی صحیح…» | ✅ | جریان موجود در `_is_captcha_error` با تست رگرسیون قفل شد |
| BUG-class | classifierهای نشست/لاگین substring روی full-URL بودند → false positive و دومین submit | ✅ | path-parsing در `auth_utils` / `utcms_http_login` / `utcms_reconciliation_scraper` / `waybill_bot_multitenant` |
| INFRA | ~۲۴ branch/PR کهنهٔ Dependabot انبار شده بود | ✅ | `.github/dependabot.yml` حذف شد؛ alert و security-updates از Settings ادامه دارد |

---

## 🆕 2026-08-23 — ثبت چندمسیره، بازتلاش هوشمند خطاهای سامانه و یکپارچگی فول‌استک (v2.9.4)

| # | مورد | وضعیت | نتیجه |
|---|---|---|---|
| H10 | دسته‌بندی ناقص خطاهای بازتلاش در ورکر و عدم پوشش خطاهای تایم‌اوت درگاه | ✅ | اتصال `_is_retryable` به `is_retryable_terminal_category` و اعمال تاخیر نمایی هوشمند |
| H11 | بن‌بست ترنزیشن‌های ماشین وضعیت در فرآیند بازیابی خودکار (Auto-Heal) | ✅ | توسعه `ALLOWED_TRANSITIONS` در `state_machine.py` برای انتقال از `failed` و `needs_review` به وضعیت‌های صف و بازتلاش |
| H12 | خطای `NoReferencedTableError` هنگام بازرسی روابط جداول توسط ورکرها و تسک‌های پس‌زمینه | ✅ | ثبت صریح ایمپورت مدل‌های `WaybillBatch` و `WaybillRouteTemplate` در `app/models_multitenant.py` |
| H13 | عدم وجود لینک‌های دسترسی ثبت دسته‌ای و قالب‌های مسیر در منوی سایدبار و داشبورد | ✅ | افزودن دکمه اکشن سریع به بنر داشبورد (`page.tsx`) و آیتم‌های `/batches` و `/route-templates` به سایدبار کلاینت و ادمین |
| H14 | محاسبه مسافت و زمان جاده‌ای بارنامه و اعتبارسنجی ۱۰۰٪ فرم‌ها | ✅ | سرویس استعلام نشان و کش ردیس + Fallback هاورسین و اعمال گیت اعتبارسنجی کامل فرم‌ها پیش از صف‌بندی |

---

## 🆕 2026-08-20 — راستی‌آزمایی جامع، امنیت و ارتقای چندمستاجری (v2.9.1)

| # | مورد | وضعیت | نتیجه |
|---|---|---|---|
| H1 | بای‌پس اعتبارسنجی Union در `WaybillJobCreateRequest.payload` با `dict[str, Any]` | ✅ | حذف `dict` خام و اعمال اعتبارسنجی دقیق پلاک، وزن مثبت و فیلدهای ضروری با خطای ۴۲۲ |
| H2 | استفاده از `client_id=1` پیش‌فرض در متدها و روت‌های قدیمی | ✅ | الزام استخراج شناسه کلاینت از JWT/API Key و صدور خطای ۴۰۰ در پروداکشن برای موارد نامشخص |
| H3 | مسیریابی fail-open در مدارشکن هنگام قطعی Redis/Registry | ✅ | اعمال رفتار fail-closed با پرتاب `NoHealthyWorkerError` در محیط پروداکشن |
| H4 | دسترسی‌های اضافی کانتینری (`SYS_ADMIN, NET_ADMIN`) در سرویس‌های عمومی بک‌اند | ✅ | حذف از `x-backend-common` و محدودسازی `SYS_ADMIN` منحصراً به کانتینرهای ورکر مرورگر |
| H5 | عدم گارد اجرایی برای `AUTH_COOKIE_SECURE` در پروداکشن با HTTPS | ✅ | افزودن چک استارتاپ اعتبارسنجی در `main.py` |
| H6 | بای‌پس احراز هویت در فرانت‌اند با `pathname.includes('.')` | ✅ | جایگزینی با رجکس دقیق پسوندهای استاتیک (`STATIC_EXT_REGEX`) در `middleware.ts` |
| H7 | استعلام سوخت و خطای Polling/UX و React Hooks | ✅ | ریفکتور با `useCallback`، افزودن پیام‌های Toast خطا و تایم‌اوت در `fuel/page.tsx` |
| H8 | عدم وجود تست‌های واحد فرانت‌اند (`npm test`) | ✅ | راه‌اندازی تست رانر نیتیو Node.js و افزودن تست‌های واحد اعتبارسنجی و نرمال‌سازی پلاک |
| H9 | عدم محدودیت آی‌پی (Zero IP Restriction) و استخر پروکسی پاک | ✅ | راه‌اندازی استخر پروکسی فعال ایرانی و مسیریابی هیبریدی بدون وابستگی به آی‌پی اختصاصی |

---

## 🆕 2026-08-13 — قرارداد فرم و آزمون کنترل‌شده UTCMS

| # | مورد | وضعیت | نتیجه |
|---|---|---|---|
| U1 | UI شامل فیلدهای غیرضروری و payload دارای fallback ساختگی بود | ✅ | فقط فیلدهای اجباری فرم زنده نگه داشته شد؛ fallback تصادفی/ساختگی حذف شد |
| U2 | نوع بسته‌بندی و ارزش بار در قرارداد کامل اجباری نبود | ✅ | validation مشترک UI/Backend/Worker اضافه شد |
| U3 | payload ناقص تا مرحله Worker و browser پیش می‌رفت | ✅ | preflight قبل از proxy، browser، lease و retry؛ نتیجه `needs_review` |
| U4 | نبود Worker سالم می‌توانست به queue/IP خیالی fallback کند | ✅ | routing fail-closed با `NoHealthyWorkerError` و آزادسازی slot |
| U5 | bridge همه assetهای UTCMS را serialize می‌کرد | ✅ | bridge محدود به document/xhr/fetch؛ assetها از Chromium/Squid |
| U6 | پاسخ CAPTCHA در بعضی log/debug metadataها ذخیره می‌شد | ✅ | پاسخ حذف؛ فقط signature غیرحساس ثبت می‌شود |
| U7 | محاسبه دوره سوخت از offset ثابت تهران استفاده می‌کرد | ✅ | `ZoneInfo("Asia/Tehran")` |
| U8 | آزمون کنترل‌شده ثبت نهایی | ⚠️ | ورود موفق، اما DocumentList با TLS reset و timeout؛ tracking code وجود ندارد |
| U9 | Worker 3 از نسخه اصلی عقب و Celery آن خاموش است | ⚠️ | پیش از ورود به routing pool باید sync/recreate و heartbeat آن اثبات شود |

> ✅ = برطرف شده | ⬜ = نیاز به اقدام کاربر روی سرور | ⚠️ = باید انجام شود
> 
> **تغییرات اخیر:** به‌روزرسانی کامل مستندات، اصلاح امنیت، بهینه‌سازی عملکرد، و رفع 164 ایشو شناسایی‌شده

---

## 🆕 2026-08-11 — بازبینی جامع (senior review)

| # | مشکل | وضعیت | یادداشت |
|---|------|--------|---------|
| X12 | `cd-deploy.yml` با `docker-compose` V1 روی فایلِ دارای `include:` | ✅ | مهاجرت کامل به `docker compose` V2 + `exec -T` + رندر squid قبل از deploy |
| X4C | `deploy_single_vm.py` / `deploy_remote.*` / `server_deploy.py` با `sed -i` قالب‌های گیت `squid_1/2/3.conf` را روی سرور مرکزی ویرایش می‌کردند → `git pull` بعدی می‌شکست | ✅ | اسکریپت `render_squid_configs.sh` جدید → رندر به `squid_*.runtime.conf` (mount در `compose/proxy.yml`) |
| R1 | مقادیر هاردکد پروکسی ورکرها، مقادیر `.env` deploy را خنثی می‌کردند | ✅ | همه به `\${WORKER_N_PROXY:-<fallback>}` تبدیل شدند |
| R2 | بسط متغیرهای رندر روی ماشین launcher (نه نود ورکر) | ✅ | escape با `\${...}` + تست دو-فاز رفتاری |
| R3 | رانبوک‌ها `CELERY_BROKER_URL` را روی Redis DB 1/2 و DB نام `barpro` می‌نوشتند؛ `WORKER_EGRESS_IP` تعریف‌نشده در قالب `.env` | ✅ | DB 0 + `utcms_rpa` + `WORKER_EGRESS_IP` + گارد `:?` در رندر |
| IMG | `backend.yml` برای هر سرویس image جداگانه داشت؛ `quick_deploy_central.sh` فقط anchor را build می‌کرد → سرور مرکزی تازه ورکرها را بالا نمی‌آورد | ✅ | یک image یکتا؛ `worker-node.yml` به image منتشرشدهٔ GHCR اشاره می‌کند |
| CD-IMG | `pull` در CD، نام imageهای محلی را از Docker Hub می‌گرفت (ناموجود) | ✅ | `deploy/registry-images.yml` (override GHCR) به همهٔ فراخوانی‌های compose در CD اعمال شد |

---

## 🔴 امنیت

| # | مشکل | وضعیت | یادداشت |
|---|------|--------|---------|
| S1 | رمز SSH لیک شده در کد | ✅ | کد پاک — رمز واقعی سرور را تغییر دهید |
| S2 | فایل `.env` در تاریخچه git | ✅ | `git filter-repo` اجرا شده |
| S3 | `privileged: true` در containers | ✅ | جایگزین: `cap_add + no-new-privileges` |
| S4 | Rate limiter fail-open | ✅ | Fail-closed: HTTP 429 در صورت قطع Redis |
| S5 | X-Forwarded-For spoofing | ✅ | از `request.client.host` استفاده می‌شود |
| S6 | Prometheus port 9090 عمومی | ✅ | تبدیل به `expose` (فقط داخلی) |
| S7 | JWT در localStorage | ✅ | توکن در httpOnly cookie — XSS-safe |
| S8 | Token blacklist fail-open | ✅ | Fail-closed: `True` اگر Redis down باشد |
| S9 | `/auth/login` بدون rate limit | ✅ | پوشش کامل در `app/main.py` |
| S10 | Cookie max_age hardcoded 86400 | ✅ | از `JWT_ACCESS_TOKEN_EXPIRE_MINUTES * 60` |
| S11 | بدون HTTPS | ⬜ | Let's Encrypt نصب کنید؛ سپس `AUTH_COOKIE_SECURE=true` |
| S12 | `network_mode: host` | ⬜ | مسدود: dual-IP routing نیاز دارد — از `secure_squid_ports.sh` استفاده کنید |
| S13 | `/management/*` و `/reports/*` با هر JWT معتبر در دسترس بودند | ✅ | `require_sensitive_admin` جدید — فقط نقش `master_admin` یا API Key |
| S14 | `NameError: 'Any'` در `_is_jwt_valid` | ✅ | `from typing import Any` اضافه شد |
| S15 | حذف `WORKER_STALL_TIMEOUT_SECONDS` تکراری | ✅ | یک تعریف واحد (env-driven) باقی مانده |
| S16 | Proxy health check URL redirect (barname.utcms.ir) | ✅ | تغییر به `https://utcms.ir` — redirect باعث false negative می‌شد |

---

## 🟠 عملکرد

| # | مشکل | وضعیت | یادداشت |
|---|------|--------|---------|
| P1 | `engine.dispose()` per Celery task | ✅ | حذف — فقط در shutdown |
| P2 | `asyncio.new_event_loop()` per task | ✅ | Event loop per-worker-process |
| P3 | `NullPool` برای connection | ✅ | جایگزین: `AsyncAdaptedQueuePool(2,2)` |
| P4 | Full table scan برای queue depth | ✅ | Redis HINCRBY counters |
| P5 | N+1 query در admin job list | ✅ | Bulk fetch با `Client.id.in_(...)` |
| P6 | bcrypt blocking event loop | ✅ | `asyncio.to_thread()` |
| P7 | WebSocket events فقط in-process | ✅ | Redis pub/sub bridge |
| P8 | React re-render در هر WebSocket tick | ✅ | `React.memo` روی table rows |
| P9 | Keras OCR subprocess per captcha | ✅ | In-process lazy load |
| P10 | Chrome per task (no recycle) | ✅ | Recycle بعد از 20 job موفق |
| P11 | Double query در هر status transition | ✅ | `_get_task_status_and_payload` — یک SELECT |
| P12 | Race در claim job توسط reconciler/worker | ✅ | `FOR UPDATE SKIP LOCKED` |
| P13 | `/readyz` سنگین در هر request (browser + captcha warmup) | ✅ | TTL cache 30s (`READYZ_CACHE_TTL_SECONDS`) |
| P14 | الگوی N+1 در admin job list | ✅ | Bulk fetch با `Client.id.in_(...)` |
| P15 | Scheduler FOR UPDATE روی outer join | ✅ | Subquery برای driver-slot check |
| P16 | Proxy health check false positives (redirect) | ✅ | URL تغییر به `utcms.ir` |

---

## 🟡 باگ‌ها

| # | مشکل | وضعیت | یادداشت |
|---|------|--------|---------|
| B1 | `except: pass` در 55+ مکان | ✅ | همه به logging تبدیل شدند |
| B2 | Redis race condition در manager | ✅ | `threading.Lock` |
| B3 | `autoretry_for = (Exception,)` | ✅ | فقط exceptions خاص |
| B4 | Browser listener leak | ✅ | `remove_listener()` در close |
| B5 | Double `json.loads()` روی JSONB | ✅ | SQLAlchemy قبلاً deserialize می‌کند |
| B6 | `json.loads()` روی JSONB result_json | ✅ | برطرف در `rpa_scheduler_service.py` |
| B7 | Session not injected در services | ✅ | از `get_session()` dependency |
| B8 | Migration deadlock on startup | ✅ | PostgreSQL session-level advisory lock |
| B9 | JSONB → SQLite incompatibility | ✅ | `JSON as JSONB` dialect-agnostic |
| B10 | `IntegrityError` در runtime state claim، worker را abort می‌کرد | ✅ | rollback + re-select |
| B11 | Lock بدون امکان release با token | ✅ | `force_release_lock(key, token=None)` — compare-and-delete |

---

## 🔵 تست‌ها

| # | مشکل | وضعیت | یادداشت |
|---|------|--------|---------|
| T1 | 13 تست شکست‌خورده | ✅ | رفع شد — سوئیت الان 646 تست collect می‌کند |
| T2 | `RuntimeWarning: coroutine never awaited` | ✅ | `mock_page.on = MagicMock()` |
| T3 | `InsecureKeyLengthWarning` در JWT test | ✅ | کلید ≥32 بایت در fixtures |
| T4 | SQLModel DeprecationWarning برای DML | ✅ | `session.connection()` برای UPDATE |
| T5 | 4 تست skip | ⬜ | نیاز به PostgreSQL/Redis — روی سرور اجرا شوند |
| T6 | TTL cache در تست‌های readyz نشت می‌کرد | ✅ | `_reset_readyz_cache()` در autouse fixture |

---

## 🔵 اصلاحات امنیتی و عملکردی جدید (2026-08-02)

| # | اصلاح | فایل(ها) | وضعیت |
|---|-------|----------|--------|
| SF1 | اضافه کردن Security Headers به backend FastAPI | `app/main.py` | ✅ |
| SF2 | پیکربندی Redis Connection Pool (timeout, retry) | `app/core/redis.py`, `rate_limiter.py`, `circuit_breaker.py` | ✅ |
| SF3 | رفع hardcoded secrets در GitHub Actions workflows | `.github/workflows/ci-cd.yml` | ✅ |
| SF4 | بهبود CSP Header در Nginx (frame-ancestors, base-uri, form-action) | `infra/nginx/http-server.conf` | ✅ |
| SF5 | اضافه کردن Permissions-Policy header | `infra/nginx/http-server.conf` | ✅ |
| SF6 | پیکربندی DNS Resolver برای upstream های Nginx | `infra/nginx/nginx.conf`, `http-server.conf` | ✅ |
| SF7 | بهبود error messages برای phone validation | `apps/web/src/schemas/waybillSchema.ts` | ✅ |
| SF8 | اضافه کردن logging به exception handler در _helpers.py | `app/services/_helpers.py` | ✅ |

---

## 🔵 اصلاحات جدید (2026-08-10)

| # | اصلاح | فایل(ها) | وضعیت |
|---|-------|----------|--------|
| SF9 | Proxy health check URL از barname.utcms.ir به utcms.ir | `app/api/routes/system.py`, `app/automation/proxy_rotator.py`, `app/automation/worker_proxy.py`, `scripts/verify_system_connections.py` | ✅ |
| SF10 | Scheduler FOR UPDATE SKIP LOCKED روی outer join fix (subquery) | `app/orchestrator/scheduler_service.py` | ✅ |
| SF11 | Test assertions آپدیت برای URL جدید | `tests/test_worker_proxy_health.py` | ✅ |

---

## 🔵 اصلاحات جدید (2026-08-13) — ورژن 2.7.0

| # | اصلاح | فایل(ها) | وضعیت |
|---|-------|----------|--------|
| L1 | WAF fast-fail در Playwright fallback: بعد از شکست HTTP login، Playwright روی صفحه «درخواست مجاز نمی‌باشد» (HTTP 444) ۳ دقیقه گیر می‌کرد | `app/automation/auth.py` | ✅ |
| L2 | بعد از inject کوکی HTTP، Playwright روی `about:blank` می‌ماند — اولین navigation همیشه cold-start بود | `app/automation/auth.py` | ✅ |
| L3 | HTTP 503 → فوری fallback به Playwright WAF-blocked بجای retry | `app/automation/utcms_http_login.py` | ✅ |
| L4 | Session منقضی‌شده بدون 401 (redirect به Login) تشخیص داده نمی‌شد | `app/automation/utcms_http_login.py` | ✅ |
| L5 | HTTP 429 و 5xx بودجه captcha-retry را مصرف می‌کردند | `app/automation/utcms_http_login.py` | ✅ |
| N1 | `RETRYABLE_NETWORK_MARKERS` vs `IP_BLOCK_PATTERNS` drift: ۵ از ۶ egress failure بدون evict IP retry می‌شدند | `app/core/network.py` | ✅ |
| N2 | `RedisConnectionManager` per-thread (نه per-loop) → `RuntimeError: Event loop is closed` در Celery | `app/core/redis.py` | ✅ |
| N3 | `unclosed socket`/`unclosed transport` ResourceWarning در test suite | `app/core/redis.py` | ✅ |

---

## ⬜ اقدامات باقیمانده روی سرور

```bash
# 1. تنظیم متغیرهای محیطی CORS
# FRONTEND_URL و FRONTEND_URLS را حتماً در .env تنظیم کنید تا از RuntimeError جلوگیری شود.

# 2. نصب HTTPS
# Let's Encrypt نصب کنید، سپس:
# - uncomment listen 443 در nginx.conf
# - AUTH_COOKIE_SECURE=true در .env
# - bash manage.sh deploy

# 3. اجرای migrations
bash manage.sh migrate

# 4. ایمن‌سازی Squid
sudo bash scripts/secure_squid_ports.sh

# 5. Crontab برای restart
echo "@reboot sudo bash /opt/barpro/scripts/secure_squid_ports.sh" | crontab -

# 6. Index های PostgreSQL (یک بار)
# ر. CRITICAL_RULES.md بخش 20
```

---

*وضعیت نهایی: 646+ تست collect، 0 failed — آماده production deployment*
*آخرین بروزرسانی: 2026-08-13 — ورژن 2.7.0 deploy شد*

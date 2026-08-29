# گراف دانش مرجع BarPro

> نسخه سند: 2026-08-29 (Unreleased)
>
> commit مبنای audit اولیه: 9c472f1
>
> آخرین commit کد/رابط کاربری: `5d583a1` (`fix(ui): harden multi-route form flows`)
>
> Alembic head مبنا: 039_add_route_chain_scheduling
>
> جایگزین tracked برای knowledge graph خارجی قبلی
>
> این سند هیچ secret، password، DSN کامل یا proxy credential را نگهداری نمی‌کند.

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
| Schedules | POST/GET /driver-schedules، PUT/DELETE by id، POST /driver-schedules/run-due |
| Waybill jobs | POST/GET /waybill-jobs، GET/PATCH/DELETE by job_id |
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
| DriverPlate | client_id، driver_id، plate_number، vehicle_type، active state |
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
  039_add_route_chain_scheduling است.
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

قرارداد UTCMS یک شاهد سوم بیرونی نیز می‌خواهد: رکورد متناظر در History/Search.

### 7.3. Three-witness contract

ثبت فقط با این سه شاهد قطعی است:

1. tracking code در پاسخ RPA؛
2. همان tracking code در waybill_jobs.result_json؛
3. تطبیق History/Search خود UTCMS.

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
- ثبت موفق فقط با سه شاهد معتبر است.
- ALLOW_LIVE_SUBMIT باید بدون approval و job کنترل‌شده فعال نشود.
- retry تهاجمی، parallel submit یک راننده و resubmit نتیجه unknown ممنوع است.
- fuel inquiry queue مستقل از driver submit lock بارنامه است.
- محاسبه period سوخت باید timezone Asia/Tehran را رعایت کند.

اعداد throughput مانند 1000 تا 2000 بارنامه در روز از کد قابل اثبات نیستند و فقط
با metric production شامل success سه‌شاهدی معتبرند.

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
| Throughput | quota و queue mechanisms | 24h/7d success سه‌شاهدی و latency |
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
18. یک dry-run و فقط در صورت مجوز یک live job کنترل‌شده با سه شاهد.

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
| RUNNING مستقیم به SUCCESS | UNKNOWN و reconciliation سه‌شاهدی اجباری |
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
| throughput 1000-2000+ قطعی | نیازمند metric production با success سه‌شاهدی |

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

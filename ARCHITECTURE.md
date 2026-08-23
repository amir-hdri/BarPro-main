# معماری فعلی BarPro

> آخرین هم‌ترازی با کد: 2026-08-23 (v2.9.4)
>
> commit مبنای audit: `90accd3`
>
> این سند قرارداد معماری checkout فعلی است، نه اثبات وضعیت لحظه‌ای سرورها. وضعیت
> containerها، firewall، environment و IP خروجی باید در هر استقرار جداگانه بررسی شود.
> قرارداد رفتاری UTCMS در [`docs/UTCMS_CONSTRAINTS.md`](docs/UTCMS_CONSTRAINTS.md)
> اولویت بالاتری از توضیحات عمومی این سند دارد.

## 1. توپولوژی استقرار

توپولوژی هدف production، **Model B scale-out** است:

```text
Browser
  │ HTTP :80 (HTTPS هنوز فعال نیست)
  ▼
Nginx ──► Next.js :3000
  │
  ├─────► FastAPI :8000
  │          ├── PostgreSQL 16 :5432
  │          ├── Redis 7 :6379 (Celery/cache/pub-sub/locks)
  │          └── WebSocket /ws/waybill
  │
  └── Central services
         ├── Celery Beat (فقط producer زمان‌بندی‌ها)
         ├── celery_scheduler (مصرف‌کننده singleton صف rpa_scheduler)
         ├── Celery Worker 1, concurrency=1
         └── Squid 1 :3128 → IP خروجی Central

Remote Worker 2                    Remote Worker 3
├── Celery Worker, concurrency=1   ├── Celery Worker, concurrency=1
└── Local Squid :3128              └── Local Squid :3128
    → static Iranian IP                → static Iranian IP
       │                                  │
       └──── PostgreSQL/Redis Central ─────┘
```

- Central میزبان API، Web، PostgreSQL، Redis، Worker 1، Beat،
  `celery_scheduler` و monitoring است.
- Workerهای 2 و 3 با [`compose/worker-node.yml`](compose/worker-node.yml) روی VPS
  مستقل اجرا می‌شوند.
- سرویس‌های Central مربوط به Worker/Squid 2 و 3 فقط متعلق به **Model A** هستند و
  نباید بدون profile صریح scale-out روی Model B بالا بیایند.
- PostgreSQL و Redis برای اتصال remote worker ممکن است روی `0.0.0.0` bind شوند؛
  این bind به‌تنهایی امنیت ایجاد نمی‌کند. UFW، firewall ارائه‌دهنده و
  `DOCKER-USER` باید دسترسی را فقط به IPهای Worker محدود کنند.
- تعریف Compose یا گزارش deployment قبلی اثبات firewall و listener زنده نیست؛
  `docker ps`، `ss -lntp` و probe از یک IP غیرمجاز باید در هر release کنترل شوند.

### Model A

Model A استقرار تک‌ماشینه سازگار با توسعه/legacy است و می‌تواند سه Worker و سه
Squid محلی داشته باشد. مقادیر `AVAILABLE_IP_INDICES` و profileهای Compose در این
مدل با Model B یکسان نیستند؛ هیچ مقدار نمونه‌ای نباید بدون تطبیق با Worker Registry
به production منتقل شود.

## 2. ورودی عمومی و TLS

- پیکربندی فعال Nginx فقط `listen 80` دارد؛ production فعلی باید **HTTP-only**
  در نظر گرفته شود.
- block نمونه‌ی `listen 443 ssl` در
  [`infra/nginx/nginx.conf`](infra/nginx/nginx.conf) comment است. وجود template یا
  باز بودن TCP/443 به معنی HTTPS عملیاتی نیست.
- تا قبل از نصب و آزمون certificate، `AUTH_COOKIE_SECURE=false` لازم است. پس از
  فعال شدن redirect و TLS معتبر، این مقدار باید هم‌زمان به `true` تغییر کند.
- مسیرهای canonical مستقیماً از Nginx به FastAPI یا Frontend هدایت می‌شوند. aliasهای
  سازگاری نباید به‌عنوان API عمومی جدید مستند یا مصرف شوند.

## 3. قرارداد API و WebSocket

مسیرهای اصلی از routerهای FastAPI استخراج می‌شوند. OpenAPI همان commit مرجع نهایی
جزئیات request/response است.

| حوزه | مسیر canonical | نکته |
|---|---|---|
| Liveness | `GET /healthz` | probe سبک فرآیند |
| Readiness | `GET /readyz` | DB/browser/config/CAPTCHA/ITMB/queue/circuit؛ پاسخ نباید DSN یا secret بازگرداند |
| Metrics | `GET /metrics` | فقط شبکه داخلی monitoring |
| Authentication | `/api/v1/auth/*`, `/api/v1/admin/login` | JWT در cookie با نام `utcms_auth_token` |
| Tenant resources | `/api/v1/drivers`, `/api/v1/plates`, `/api/v1/driver-schedules` | tenant-scoped |
| Waybill jobs | `/api/v1/waybill-jobs` | create/list/get/patch/delete و زیرمسیرهای retry/requeue/timeline/logs/screenshot |
| Fuel inquiry | `/api/v1/fuel-inquiries` | queue مستقل سوخت |
| Bulk upload | `/api/v1/upload/*` | Excel/batch tracking |
| Locations | `/api/v1/locations/*`, `POST /api/v1/locations/distance` | قرارداد مکان + فاصله/زمان جاده‌ای (Neshan → haversine) |
| Route templates | `/api/v1/route-templates` | قالب مسیر + favorite (tenant-scoped) |
| Multi-route batches | `/api/v1/batches` | ایجاد دستهٔ چندمسیره + پیشرفت؛ idempotent با `X-Idempotency-Key` |
| Phase-1/legacy operations | `/api/v1/rpa/phase1/*`, `/management/*`, `/waybill/*` | سطح دسترسی هر route از dependency کد تعیین می‌شود |
| Clean IP operations | `/api/system/clean-ips`, `/api/system/clean-ips/refresh` | admin-protected و بدون افشای credential |
| Realtime | `WS /ws/waybill` | auth فقط از cookie؛ فیلترهای `task_id`, `batch_id`, `correlation_id` |

مسیرهای `/api/system/health`، `/ws/jobs/{client_id}` و
`/ws/admin/stream` قرارداد فعلی نیستند. همچنین endpoint جداگانه‌ی `POST cancel`
وجود ندارد؛ `DELETE /api/v1/waybill-jobs/{job_id}` حذف دائمی است و نباید با cancel
قابل‌بازیابی اشتباه شود.

## 4. جریان ثبت بارنامه و state machine

```text
POST /api/v1/waybill-jobs
  → validation + tenant/quota/idempotency checks
  → pending / waiting_auth / waiting_submission_window
  → scheduler creates DispatchIntent
  → dispatcher selects healthy registered Worker/IP
  → queued → claimed → running
  → at-most-once UTCMS submit
  → unknown (نتیجه mutation هنوز قطعی نیست)
  → reconciling (UTCMS History/Search)
       ├── سه شاهد معتبر → success
       ├── ambiguous/not found after bounded attempts → needs_review
       └── transient evidence gap → unknown/retry reconciliation
```

`RUNNING → SUCCESS` یک happy-path معتبر برای اعلام فوری موفقیت نیست. guard در
`JobStateMachine` برای `WaybillJob` تنها زمانی `success` را می‌پذیرد که:

1. پاسخ RPA دارای `tracking_code` غیرخالی باشد؛
2. همان کد در `waybill_jobs.result_json` ذخیره شده باشد؛
3. History/Search خود UTCMS رکورد متناظر را تأیید کند و
   `mutation_status=confirmed` و `reconciled_at` ثبت شده باشند.

بسته شدن modal، دریافت پیام success از UI، screenshot یا وجود tracking code بدون
تأیید History به‌تنهایی اثبات ثبت نهایی نیست. Job نامطمئن هرگز خودکار resubmit
نمی‌شود؛ پس از پایان reconciliation محدود به `needs_review` می‌رود.

تاخیرهای فعلی reconciliation برابر `15, 45, 120, 300` ثانیه‌اند و task دوره‌ای
آن از queue reconciliation اجرا می‌شود.

## 5. Submission Gate و OTP

UTCMS پنجره‌ی رسمی و تضمین‌شده‌ای برای OTP منتشر نکرده است. بازه پیش‌فرض
`17:30–08:00` (پیش‌فرض config) فقط **prediction قابل‌تنظیم** برای `OTP_REQUIRED` است، نه قانون
قطعی سامانه.

- فقط observation معتبر `OTP_FREE` اجازه submit می‌دهد.
- `UNKNOWN`، `DEGRADED` و `OTP_REQUIRED` fail-closed هستند.
- state در Redis cache و در `utcms_system_observations` audit می‌شود.
- Beat فقط task `barpro.gate.probe` را publish می‌کند؛ اجرای آن توسط مصرف‌کننده
  `rpa_scheduler` و زیر distributed lock انجام می‌شود.
- مقدارهای effective window، TTL و interval باید از environment همان deployment
  گزارش شوند؛ default کد اثبات مقدار production نیست.

## 6. Celery و صف‌ها

Beat مصرف‌کننده نیست؛ Beat schedule message تولید می‌کند. `celery_scheduler`
مصرف‌کننده singleton control-plane است و RPA browser workload نباید روی آن اجرا شود.

| مصرف‌کننده | صف‌ها |
|---|---|
| Worker 1 | `waybill_tasks`, `waybill_tasks_1`, `rpa_auth_1`, `rpa_submit_1`, `reconciliation_tasks`, `reconciliation_tasks_1`, `scheduled_tasks`, `scheduled_tasks_1`, `barpro.fuel.inquiry` |
| Worker 2 | base queueهای لازم + `*_2`، `scheduled_tasks_2`, `barpro.fuel.inquiry` |
| Worker 3 | base queueهای لازم + `*_3`، `scheduled_tasks_3`, `barpro.fuel.inquiry` |
| `celery_scheduler` | فقط `rpa_scheduler` |

- concurrency مؤثر هر Worker RPA برابر `1` است.
- `AVAILABLE_IP_INDICES` با Worker Registry فیلتر می‌شود؛ index بدون Worker تازه و
  ثبت‌شده مقصد dispatch نیست.
- `barpro.fuel.inquiry` توسط تمام Workerها مصرف می‌شود، اما lock بارنامه‌ی راننده
  را تصاحب نمی‌کند.
- taskهای orchestrator scheduler/dispatcher/orphan detector/claim reaper، cleanup
  سوخت، gate probe و Clean IP probe روی `rpa_scheduler` publish می‌شوند.
- وضعیت واقعی binding و backlog فقط با `celery inspect active_queues` و metrics
  همان deployment قابل اثبات است.

## 7. CAPTCHA و login شبکه‌ای

`CAPTCHA_PROVIDER=auto` providerها را به ترتیب زیر امتحان می‌کند:

1. `cnn` — CAPTCHA ریاضی login؛
2. `pytorch_fuel` — CRNN عبارت فارسی سوخت؛
3. `keras_ocr` — fallback سوخت؛
4. `enhanced_ocr`؛
5. `local_ocr`.

Keras با `keras.models.load_model(..., compile=False)` به‌صورت lazy و thread-safe
در **همان Worker process** load و reuse می‌شود. `KERAS_PYTHON_PATH` قرارداد runtime
solver فعلی نیست و نباید معماری subprocess Python 3.12 از آن استنباط شود.

هیچ عدد accuracy/latency بدون benchmark نسخه‌دار، hash دیتاست، مدل و environment
قابل استناد نیست. mode مؤثر (`CAPTCHA_PROVIDER`, `CAPTCHA_MODE`, `CAPTCHA_AUTO_ONLY`)
ممکن است بین nodeها متفاوت باشد و باید در runtime audit شود.

ورود UTCMS صرفاً Playwright نیست: مسیر اصلی می‌تواند HTTP login با `curl_cffi`،
انتقال cookie/session و bridge محدود `document/xhr/fetch` داشته باشد و در صورت نیاز
به Playwright fallback کند. 429 و 408/5xx transient نباید بودجه CAPTCHA را بسوزانند.

## 8. proxy، circuit breaker و IP isolation

modeهای معتبر egress عبارت‌اند از `worker_first`، `clean_pool_only` و `hybrid`.
نام `clean_pool` معتبر نیست و نباید در runbookها استفاده شود.

سه مفهوم مستقل‌اند:

- block شدن Worker IP در Redis با TTL عملیاتی 30 دقیقه؛
- block شدن یک clean proxy به‌صورت per-proxy با TTL قابل تنظیم؛
- circuit breaker عمومی in-process با threshold و recovery جداگانه.

خطای یک clean proxy نباید `WORKER_IP_INDEX` یا تمام node را مسدود کند. از سوی دیگر
registry یا Redis نامطمئن نباید باعث dispatch fail-open به queue خیالی شود.

## 9. مدل داده

کلیدهای اصلی SQLModel در مدل‌های جاری **integer** هستند. شناسه‌های عمومی مانند
`job_id`، `batch_id`، `intent_id` و `execution_id` string هستند و نباید با UUID
primary key اشتباه شوند.

| aggregate | فیلدها/نقش‌های مهم |
|---|---|
| `Client`, `Driver`, `DriverPlate`, `DriverSchedule` | tenant و fleet ownership |
| `WaybillJob` | `payload_json`, `result_json`, `attempt_count`, `next_retry_at`, `submit_after`, `request_digest`, `mutation_status`, `reconciled_at`, `celery_task_id` + multi-route: `batch_id`, `route_template_id`, `sequence_index`, `distance_km`, `duration_min` |
| `WaybillRouteTemplate` | مسیر ذخیره‌شده مبدأ→مقصد با `distance_km`/`duration_min` پیش‌محاسبه‌شده |
| `WaybillBatch` | دستهٔ چندمسیره: `route_template_ids`, `base_payload_json`, `target_count`, `repeat_mode`, `interval_minutes`, `idempotency_key` |
| `FuelInquiry` | status، `quota_data_json`، `screenshot_url` که می‌تواند Data URI باشد؛ tracking code مستقیم ندارد |
| `UploadBatch` | وضعیت ingest گروهی و خطاهای batch |
| `DispatchIntent` | intent پایدار dispatch، attempt و fencing token |
| `Execution` | lease اجرای Worker و نتیجه execution |
| `WorkerRegistry` | heartbeat، capacity، capabilities و `ip_index` |
| `ProxyEndpoint` | سلامت و cooldown endpointهای proxy |
| `UTCMSSystemObservation` | observation و اعتبار gate |

نمودار یا agent نباید columnهای فرضی مانند `waybill_payload`, `retry_count` یا
`tracking_code` مستقیم روی `FuelInquiry` بسازد. مرجع schema، SQLModelهای
`app/models_multitenant.py` و `app/models_rpa.py` همراه با Alembic head جاری است.

## 10. Redis، rate limit و realtime

Redis هم‌زمان broker/cache/pub-sub/distributed-lock و storage state است. eventهای
Worker از طریق Redis pub/sub به FastAPI و سپس `WS /ws/waybill` bridge می‌شوند.

rate limiter برنامه sliding-window مبتنی بر Redis ZSET و fail-closed است؛ Token
Bucket نیست. حدود ثبت‌شده در کد عبارت‌اند از public=60، auth=5، waybill=30،
driver=60، tenant=100 و admin=200 درخواست در 60 ثانیه. تطبیق prefix هر route باید
با test قرارداد کنترل شود و صرف وجود rule اثبات اعمال آن روی همه مسیرها نیست.

## 11. Monitoring

لایه [`compose/monitoring.yml`](compose/monitoring.yml) فقط Prometheus نیست:

- Prometheus با retention فعلی 15 روز؛
- Alertmanager؛
- Grafana؛
- node-exporter؛
- redis-exporter؛
- postgres-exporter؛
- nginx-exporter.

Prometheus، Alertmanager و exporterها فقط روی شبکه Docker `barpro_platform` expose
می‌شوند. Grafana روی `127.0.0.1:3000` bind شده و برای دسترسی راه دور به tunnel یا
reverse proxy امن نیاز دارد. presence در Compose اثبات اجرای زنده یا delivery
هشدار نیست؛ container health، scrape targets و receiverها باید پس از deploy بررسی شوند.

## 12. قواعد اعتبارسنجی production

پیش از اعلام هم‌راستایی مستندات و سرور، حداقل این شواهد ثبت شوند:

1. git SHA و Alembic head هر سه node؛
2. full `docker ps` شامل کشف container اضافه، نه فقط expected list؛
3. active queueها، worker concurrency، registry heartbeat و queue depth؛
4. listenerها و firewall از داخل و یک IP غیرمجاز؛
5. egress IP واقعی هر Worker از مسیر Squid؛
6. effective env غیرحساس شامل OTP/CAPTCHA/proxy/circuit settings؛
7. TLS handshake و cookie flags؛
8. Prometheus targets، alert rules و Alertmanager delivery؛
9. throughput و SLO از metrics/log، نه از quota یا default کد.

هر مورد فاقد این شواهد باید با عبارت «نیازمند بررسی runtime» گزارش شود و نباید از
نمونه `.env.example` یا وضعیت یک checkout محلی نتیجه‌گیری شود.

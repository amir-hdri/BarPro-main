# راهنمای استقرار production بارپرو

> نسخه مستندات: 2026-08-20
>
> توپولوژی پیش‌فرض: Model B scale-out
>
> این سند checklist استقرار است. هیچ مقدار نمونه، Compose file یا گزارش قدیمی
> به‌تنهایی اثبات وضعیت زنده‌ی سرور نیست.

## 1. توپولوژی

### Model B — پیش‌فرض production

- Central: PostgreSQL، Redis، FastAPI، Next.js، Nginx، Worker 1،
  celery_scheduler، Beat، Squid 1 و monitoring.
- Remote Worker 2/3: هر کدام Celery Worker با concurrency=1 و Squid محلی روی
  پورت 3128 و IP استاتیک ایرانی.
- Worker/Squid 2 و 3 مرکزی نباید در این مدل اجرا شوند.
- BARPRO_TOPOLOGY=model-b مقدار پیش‌فرض manage.sh است.

### Model A — opt-in

استقرار تک‌سرور با Worker/Squid 2 و 3 فقط با انتخاب صریح انجام می‌شود:

    BARPRO_TOPOLOGY=model-a bash manage.sh start

این mode برای production Model B استفاده نشود.

## 2. پیش‌نیاز و secretها

- Ubuntu 22.04 یا جدیدتر، Docker Engine و Docker Compose V2.
- checkout معمول Central در /opt/barpro.
- .env از .env.example ساخته شود، اما secret واقعی هرگز commit نشود.
- حداقل secretهای لازم: API_KEY, JWT_SECRET, POSTGRES_PASSWORD,
  REDIS_PASSWORD, DRIVER_ENCRYPTION_KEY, MASTER_ADMIN_USERNAME و
  MASTER_ADMIN_PASSWORD.
- مقدارهای POSTGRES_BIND=0.0.0.0 و REDIS_BIND=0.0.0.0 فقط در صورت نیاز
  remote worker مجازند و باید با UFW، firewall ارائه‌دهنده و DOCKER-USER
  محدود شوند.
- تا وقتی TLS فعال و verify نشده است، AUTH_COOKIE_SECURE=false باقی بماند.
- AVAILABLE_IP_INDICES باید با Worker Registry همان fleet هم‌راستا باشد؛ fleet
  سه‌ورکری مورد انتظار از 1,2,3 استفاده می‌کند.

## 3. assetهای CAPTCHA

این فایل‌ها باید داخل image/checkout قابل خواندن باشند:

- persian_number_ocr.keras
- app/automation/captcha/assets/captcha_cnn.pth
- app/automation/captcha/assets/fuel_captcha_crnn.pth
- app/automation/captcha/assets/fuel_captcha_vocab.json

ترتیب CAPTCHA_PROVIDER=auto برابر CNN → Fuel CRNN → Keras → Enhanced → Local
است. Keras داخل همان Worker process lazy-load می‌شود؛ KERAS_PYTHON_PATH مسیر
subprocess فعال نیست. mode مؤثر هر node باید پس از deploy گزارش شود.

## 4. راه‌اندازی Central

    git clone <repo-url> /opt/barpro
    cd /opt/barpro
    cp .env.example .env
    # secretها و مقادیر topology را خارج از Git تنظیم کنید
    BARPRO_TOPOLOGY=model-b bash manage.sh start

لایه‌ها:

1. compose/infra.yml — PostgreSQL و Redis؛
2. compose/proxy.yml — فقط Squid 1 در Model B؛
3. compose/backend.yml — API، Worker 1، Beat و celery_scheduler؛
4. compose/web.yml — Next.js و Nginx؛
5. compose/monitoring.yml — Prometheus، Alertmanager، Grafana و exporterها.

Workerهای remote با compose/worker-node.yml و runbookهای
docs/runbook_scale_out.md و docs/runbook_worker_registration.md مستقر شوند.

## 5. مهاجرت و دستورات عملیات

    bash manage.sh start
    bash manage.sh status
    bash manage.sh health
    bash manage.sh deploy
    bash manage.sh migrate
    bash manage.sh backup
    bash manage.sh stop

Alembic head مورد انتظار این checkout:

    036_management_tables_and_activity_logs_fix

مهاجرت‌ها زیر PostgreSQL session-level advisory lock اجرا می‌شوند. تمام مسیرهای
deploy باید `app.core.database.run_migrations()` را فراخوانی کنند و از Alembic خام
عبور نکنند. قبل از deploy دارای schema change، backup قابل‌بازیابی الزامی است.

## 6. قرارداد queue بعد از deploy

- Worker 1: base queues، صف‌های دارای suffix شماره 1، reconciliation/scheduled
  base و barpro.fuel.inquiry.
- Worker 2/3: صف‌های متناظر suffix شماره 2 یا 3 و fuel queue.
- celery_scheduler: فقط rpa_scheduler.
- Beat فقط producer periodic taskهاست.
- concurrency هر Worker RPA برابر 1 است.

این موارد با inspect زنده بررسی شوند:

    docker exec barpro-celery-worker-1 celery -A app.workers.celery_app inspect active_queues
    docker exec barpro-celery-worker-1 celery -A app.workers.celery_app inspect stats

نام دقیق container remote ممکن است متفاوت باشد؛ فرمان را روی هر node با نام
container همان deployment اجرا کنید.

## 7. اعتبارسنجی پس از deploy

    bash manage.sh status
    bash manage.sh health
    docker compose -f compose/backend.yml config
    docker compose -f compose/web.yml config
    docker compose -f compose/monitoring.yml config
    docker ps
    ss -lntp

سپس موارد زیر ثبت شوند:

1. git SHA و alembic current روی Central و هر Worker؛
2. نبود celery_worker_2/3 و squid_2/3 روی Central Model B؛
3. heartbeat و ip_indexهای Worker Registry؛
4. active queueها و concurrency واقعی هر Worker؛
5. egress IP واقعی هر Squid؛
6. دسترسی نداشتن یک IP غیر-worker به 5432/6379/3128–3130؛
7. پاسخ GET /healthz و پاسخ sanitized مسیر GET /readyz بدون URL یا credential؛
8. دسترسی admin به GET /api/v1/admin/readyz و /api/system/clean-ips؛
9. Prometheus targets، Alertmanager و health Grafana/exporterها؛
10. backlog reconciliation و successهای دارای سه شاهد.

هر موردی که اجرا نشده است با «نیازمند بررسی runtime» گزارش شود.

## 8. HTTPS

در checkout فعلی block مربوط به 443 در Nginx غیرفعال است. عبارت «HTTPS ready»
به معنی TLS عملیاتی نیست. برای فعال‌سازی:

1. certificate و private key با permission مناسب نصب شوند؛
2. volume certificate و block listen 443 ssl فعال شوند؛
3. nginx -t و TLS handshake بیرونی موفق باشند؛
4. redirect از HTTP به HTTPS فعال و آزمون شود؛
5. AUTH_COOKIE_SECURE=true تنظیم و login/logout/WebSocket تست شود.

تا تکمیل هر پنج مرحله، deployment باید HTTP-only مستند شود.

## 9. Monitoring

compose/monitoring.yml شامل Prometheus، Alertmanager، Grafana و exporterهای
node، Redis، PostgreSQL و Nginx است. Prometheus/Alertmanager/exporterها فقط داخل
شبکه Docker expose می‌شوند و Grafana روی loopback bind است. وجود service در
Compose اثبات running بودن، scrape موفق یا delivery هشدار نیست.

## 10. معیار موفقیت ثبت

هیچ smoke test نباید نتیجه RPA را مستقیماً success اعلام کند. موفقیت production
تنها با سه شاهد قرارداد UTCMS معتبر است:

1. tracking code در پاسخ RPA؛
2. همان code در waybill_jobs.result_json؛
3. رکورد متناظر در History/Search UTCMS.

جریان ایمن running → unknown → reconciling → success یا needs_review است.

## 11. rollback

- commit قبلی و backup دیتابیس پیش از deploy ثبت شوند.
- rollback کد با عملیات Git قابل‌بازبینی و سپس bash manage.sh deploy انجام شود.
- downgrade schema تنها با بررسی migration و طرح restore انجام شود.
- از git reset --hard و پاک‌سازی destructive در runbook عادی استفاده نشود.

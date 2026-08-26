# Runbook: Scale-out مدل B

این سند خلاصه‌ی canonical افزودن Remote Workerهای 2 و 3 به Central است. جزئیات ثبت هر node در `runbook_worker_registration.md` قرار دارد.

## Central

1. `AVAILABLE_IP_INDICES` را فقط به indexهایی محدود کنید که Worker Registry تازه دارند.
2. IP هر Worker را با `scripts/add_worker_firewall.sh` به UFW و `DOCKER-USER` اضافه کنید.
3. Redis و Postgres روی Central در DB canonical (`redis /0`, `utcms_rpa`) باقی می‌مانند.

## Worker template

برای هر Worker یک `.env` مستقل بسازید:

```bash
cat > /opt/barpro/.env << 'EOF'
ENVIRONMENT=production
WORKER_ID=2
WORKER_IP_INDEX=2
CENTRAL_IP=<CENTRAL_IP>
WORKER_EGRESS_IP=<WORKER_PUBLIC_IP>
DATABASE_URL=postgresql+asyncpg://barpro_worker:<DB_PASSWORD>@<CENTRAL_IP>:5432/utcms_rpa
REDIS_URL=redis://:<REDIS_PASSWORD>@<CENTRAL_IP>:6379/0
CELERY_BROKER_URL=redis://:<REDIS_PASSWORD>@<CENTRAL_IP>:6379/0
CELERY_RESULT_BACKEND=redis://:<REDIS_PASSWORD>@<CENTRAL_IP>:6379/0
WORKER_PROXY_PORT=3128
CAPTCHA_PROVIDER=auto
HEADLESS=true
QUEUE_ENABLED=true
QUEUE_INLINE_FALLBACK=false
EOF
```

Squid runtime config:

```bash
cd /opt/barpro
set -a; source .env; set +a
sed -e "s/__WORKER_EGRESS_IP__/${WORKER_EGRESS_IP:?WORKER_EGRESS_IP is required in .env}/g" \
    -e "s/__CENTRAL_IP__/${CENTRAL_IP:?CENTRAL_IP is required in .env}/g" \
    infra/squid/squid_worker.conf > infra/squid/squid_worker.runtime.conf
```

Start:

```bash
cd /opt/barpro
docker compose --env-file .env -f compose/worker-node.yml up -d
```

## Fleet acceptance

- Central فقط Worker 1 و Squid 1 را محلی اجرا می‌کند؛ Worker 2/3 روی VPSهای خود هستند.
- هر Worker concurrency مؤثر 1 و proxy محلی 3128 دارد.
- Worker Registry، active queues و Git HEAD هر سه node همگام‌اند.
- Clean IP Pool snapshot تازه از Redis مشترک خوانده می‌شود و فقط egress اندازه‌گیری‌شده‌ی ایران انتخاب می‌شود.
- سلامت tunnel با login surface سنجیده می‌شود؛ آمادگی صدور با flow احرازشده Login → Notification → menu و dry-run تصویری.

# Runbook: ثبت Worker جدید

این runbook قرارداد عملیاتی ثبت یک Remote Worker در توپولوژی Model B است. هیچ secret واقعی در سند قرار ندهید.

## 1. Central preflight

روی Central، IP ثابت Worker را به UFW و `DOCKER-USER` اضافه کنید:

```bash
sudo bash scripts/add_worker_firewall.sh <WORKER_IP> <WORKER_IP_INDEX>
```

## 2. Worker environment

روی Worker، repository را در `/opt/barpro` قرار دهید و template زیر را با secretهای vault تکمیل کنید:

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

## 3. Render Squid config

قالب tracked را ویرایش نکنید؛ runtime copy بسازید:

```bash
cd /opt/barpro
set -a; source .env; set +a
sed -e "s/__WORKER_EGRESS_IP__/${WORKER_EGRESS_IP:?WORKER_EGRESS_IP is required in .env}/g" \
    -e "s/__CENTRAL_IP__/${CENTRAL_IP:?CENTRAL_IP is required in .env}/g" \
    infra/squid/squid_worker.conf > infra/squid/squid_worker.runtime.conf
```

## 4. Start and verify

```bash
cd /opt/barpro
docker compose --env-file .env -f compose/worker-node.yml up -d
docker compose --env-file .env -f compose/worker-node.yml ps
```

روی Central، `worker_registry` باید heartbeat تازه، `status=active` و `ip_index` درست نشان دهد. سپس active queues، egress IP از داخل Worker، و دسترسی login UTCMS از Squid محلی را بررسی کنید. درخواست مستقیم به `HagigiHogugi` تست معتبر IP نیست.

## 5. Acceptance gate

- Git HEAD Worker با release هدف یکسان باشد.
- فقط `barpro-squid-worker` و `barpro-celery-worker` برای نقش Worker اجرا شوند.
- Redis/Postgres فقط از IP allowlisted Worker قابل دسترس باشند.
- صف‌های suffixدار همان `WORKER_IP_INDEX` مصرف شوند.
- egress واقعی ایران و read-back dry-run مبدا/مقصد اثبات شود.

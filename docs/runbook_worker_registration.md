# Runbook: Worker Registration

This runbook guides operators on how to register and onboard a new Celery worker node into the BarPro platform.

---

## 1. Prerequisites
- **Target Node**: A fresh Linux VPS with an Iranian static IP address.
- **Docker**: Must be installed on the worker node.
- **Network**: SSH access to both the central server and the new worker node.

---

## 2. Onboarding Procedure

### Step 1: Open Port Allowlist on Central Server
On the central server, add firewall entries to allow database (5432) and Redis (6379) traffic from the new worker IP.
```bash
sudo bash /opt/barpro/scripts/add_worker_firewall.sh <NEW_WORKER_IP> <WORKER_ID>
```

### Step 2: Configure Database Credentials
Ensure the worker database user role has been created with low-privilege access (read and write only, no drop or delete permissions):
```bash
docker exec -i barpro-postgres psql -U postgres -d barpro \
  -v WORKER_DB_PASSWORD="<strong-password>" \
  -f /opt/barpro/scripts/create_worker_db_role.sql
```

### Step 3: Clone Code and Populate environment variables
On the new worker node, clone the repository and configure `.env`:
```bash
git clone https://github.com/amir-hdri/BarPro-main.git /opt/barpro
cd /opt/barpro

cat > /opt/barpro/.env << 'EOF'
WORKER_IP_INDEX=4 # Numeric IP index (WORKER_ID is derived from it)
CENTRAL_IP=<YOUR_CENTRAL_SERVER_IP>
# Database name must match the Central server's POSTGRES_DB (default utcms_rpa)
DATABASE_URL=postgresql+asyncpg://barpro_worker:<WORKER_DB_PASSWORD>@<YOUR_CENTRAL_SERVER_IP>:5432/utcms_rpa
# ⚠️ CELERY_BROKER_URL MUST use Redis DB 0 — the Central server publishes all
# tasks on DB 0. DB 1/2 (as in older revisions of this runbook) silently break
# task delivery: the worker registers, but no task ever reaches it.
REDIS_URL=redis://:<REDIS_PASSWORD>@<YOUR_CENTRAL_SERVER_IP>:6379/0
CELERY_BROKER_URL=redis://:<REDIS_PASSWORD>@<YOUR_CENTRAL_SERVER_IP>:6379/0
CELERY_RESULT_BACKEND=redis://:<REDIS_PASSWORD>@<YOUR_CENTRAL_SERVER_IP>:6379/0
WORKER_PROXY_PORT=3128
# This VPS's own public IP — Squid tcp_outgoing_address (egress to UTCMS)
WORKER_EGRESS_IP=<THIS_VPS_PUBLIC_IP>
CAPTCHA_PROVIDER=auto
HEADLESS=true
QUEUE_ENABLED=true
EOF
```

### Step 4: Render the Squid template
`compose/worker-node.yml` mounts `infra/squid/squid_worker.runtime.conf` (NOT the
git template). Render it once before the first start — never `sed -i` the
tracked template, or the next `git pull` fails to apply cleanly. Replace every
placeholder in `.env` with real values FIRST, then load it into the shell:
```bash
cd /opt/barpro
set -a; source .env; set +a
sed -e "s/__WORKER_EGRESS_IP__/${WORKER_EGRESS_IP:?WORKER_EGRESS_IP is required in .env}/g" \
    -e "s/__CENTRAL_IP__/${CENTRAL_IP:?CENTRAL_IP is required in .env}/g" \
    infra/squid/squid_worker.conf > infra/squid/squid_worker.runtime.conf
```

### Step 5: Start the worker node
Deploy the Docker stack on the worker node:
```bash
# --env-file .env: compose interpolation must read /opt/barpro/.env, not
# ./compose/.env — otherwise WORKER_IP_INDEX/CENTRAL_IP break (X5).
docker compose --env-file .env -f compose/worker-node.yml up -d
```

### Step 6: Verification
Query the registered workers from the central API to verify:
```bash
curl -s http://<YOUR_CENTRAL_SERVER_IP>/api/v1/admin/workers/heartbeats \
  -H "Authorization: Bearer <ADMIN_TOKEN>"
```
The new worker should appear in the `active` registry list with `"status": "active"`.

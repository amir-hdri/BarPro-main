# Runbook: Scaling Out Worker Nodes

This runbook guides operators on how to scale out the capacity of the BarPro platform by adding new worker nodes.

---

## 1. Capacity Architecture
BarPro uses a central scheduler model. Worker nodes run Celery consumer processes that fetch tasks from the central Redis broker.
Adding a new worker node **does not require** restarting or changing any configuration on the central server. The worker will register itself automatically in the database on startup.

---

## 2. Step-by-Step Scale-Out

### Step 1: Provision Worker VPS
- Get a new Iranian VPS with a static IP.
- Ensure Docker and Docker Compose are installed.

### Step 2: Firewall Authorization (On Central Server)
Allow the new worker IP to access Postgres (5432) and Redis (6379):
```bash
sudo bash /opt/barpro/scripts/add_worker_firewall.sh <NEW_WORKER_IP> <WORKER_ID>
```

### Step 3: Configure Worker Node
On the new worker, clone the codebase and set up `.env`:
```bash
git clone https://github.com/amir-hdri/BarPro-main.git /opt/barpro
cd /opt/barpro

cat > .env << 'EOF'
WORKER_IP_INDEX=5 # Numeric IP index (WORKER_ID is derived from it)
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

### Step 5: Deploy Worker Services
Run the worker node stack:
```bash
# --env-file .env: compose interpolation must read /opt/barpro/.env, not
# ./compose/.env — otherwise WORKER_IP_INDEX/CENTRAL_IP break (X5).
docker compose --env-file .env -f compose/worker-node.yml up -d
```
This starts Celery worker and the local Squid proxy container.

---

## 3. Verification & Scaling Validation
1. Verify the worker is registered in the database:
   ```bash
   docker exec -it barpro-postgres psql -U postgres -d barpro -c "SELECT * FROM worker_registry;"
   ```
2. Verify the worker receives and processes tasks from the queue by watching the Celery logs:
   ```bash
   docker compose -f compose/worker-node.yml logs -f worker
   ```

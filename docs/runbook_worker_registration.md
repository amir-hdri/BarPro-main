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
WORKER_ID=worker_4
CENTRAL_IP=<YOUR_CENTRAL_SERVER_IP>
DATABASE_URL=postgresql+asyncpg://barpro_worker:<WORKER_DB_PASSWORD>@<YOUR_CENTRAL_SERVER_IP>:5432/barpro
REDIS_URL=redis://:<REDIS_PASSWORD>@<YOUR_CENTRAL_SERVER_IP>:6379/0
CELERY_BROKER_URL=redis://:<REDIS_PASSWORD>@<YOUR_CENTRAL_SERVER_IP>:6379/1
CELERY_RESULT_BACKEND=redis://:<REDIS_PASSWORD>@<YOUR_CENTRAL_SERVER_IP>:6379/2
WORKER_PROXY_PORT=3128
CAPTCHA_PROVIDER=auto
HEADLESS=true
QUEUE_ENABLED=true
EOF
```

### Step 4: Start the worker node
Deploy the Docker stack on the worker node:
```bash
docker compose -f compose/worker-node.yml up -d
```

### Step 5: Verification
Query the registered workers from the central API to verify:
```bash
curl -s http://<YOUR_CENTRAL_SERVER_IP>/api/v1/admin/workers/heartbeats \
  -H "Authorization: Bearer <ADMIN_TOKEN>"
```
The new worker should appear in the `active` registry list with `"status": "active"`.

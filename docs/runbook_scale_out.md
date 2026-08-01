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
WORKER_ID=worker_5 # Unique worker identifier
CENTRAL_IP=<YOUR_CENTRAL_SERVER_IP>
DATABASE_URL=postgresql+asyncpg://barpro_worker:<WORKER_DB_PASSWORD>@<YOUR_CENTRAL_SERVER_IP>:5432/barpro
REDIS_URL=redis://:<REDIS_PASSWORD>@<YOUR_CENTRAL_SERVER_IP>:6379/0
CELERY_BROKER_URL=redis://:<REDIS_PASSWORD>@<YOUR_CENTRAL_SERVER_IP>:6379/1
CELERY_RESULT_BACKEND=redis://:<REDIS_PASSWORD>@<YOUR_CENTRAL_SERVER_IP>:6379/2
WORKER_PROXY_PORT=3128
CAPTCHA_PROVIDER=auto
HEADLESS=true
EOF
```

### Step 4: Deploy Worker Services
Run the worker node stack:
```bash
docker compose -f compose/worker-node.yml up -d
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

#!/usr/bin/env bash
# =============================================================================
# add_worker_firewall.sh — Add a new Remote Worker to the Central firewall
# =============================================================================
# Run on the CENTRAL server when adding a new Worker node.
#
# Usage:
#   sudo bash scripts/add_worker_firewall.sh <WORKER_IP> <WORKER_ID>
#
# Example:
#   sudo bash scripts/add_worker_firewall.sh 185.1.2.3 2
#
# WORKER_ID must be the numeric IP index (2 or 3) matching AVAILABLE_IP_INDICES
# on the Central server — Celery queue suffixes (waybill_tasks_2, ...) and the
# worker registry key are derived from it.
#
# What this script does:
#   1. Adds UFW rules to allow WORKER_IP → PostgreSQL (5432) and Redis (6379)
#   2. Prints the .env values that must be set on the new Worker server
#   3. Prints the docker compose command to run on the Worker server
# =============================================================================

set -euo pipefail

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
BOLD='\033[1m'
NC='\033[0m'

log_info()  { echo -e "${GREEN}[INFO]${NC}  $*"; }
log_warn()  { echo -e "${YELLOW}[WARN]${NC}  $*"; }
log_step()  { echo -e "${CYAN}${BOLD}──── $* ────${NC}"; }

WORKER_IP="${1:-}"
WORKER_ID="${2:-}"

if [[ -z "$WORKER_IP" || -z "$WORKER_ID" ]]; then
    echo "Usage: sudo bash $0 <WORKER_IP> <WORKER_ID>"
    echo "Example: sudo bash $0 185.1.2.3 worker_4"
    exit 1
fi

# Validate IP format
if ! echo "$WORKER_IP" | grep -qE '^([0-9]{1,3}\.){3}[0-9]{1,3}$'; then
    echo -e "${RED}[ERROR]${NC} Invalid IP address: $WORKER_IP"
    exit 1
fi

# ── Step 1: UFW rules ────────────────────────────────────────────────────────
log_step "Step 1: Adding UFW rules on Central server"

if ! command -v ufw &>/dev/null; then
    log_warn "ufw not found. Run setup_firewall_central.sh first."
    exit 1
fi

ufw allow from "$WORKER_IP" to any port 5432 comment "PostgreSQL - $WORKER_ID ($WORKER_IP)"
ufw allow from "$WORKER_IP" to any port 6379 comment "Redis - $WORKER_ID ($WORKER_IP)"

log_info "UFW rules added for $WORKER_ID ($WORKER_IP)"
ufw status | grep "$WORKER_IP" || true

# ── Step 2: Print instructions for the Worker server ─────────────────────────
CENTRAL_IP=$(hostname -I | awk '{print $1}')

log_step "Step 2: Configure the new Worker server ($WORKER_IP)"

cat <<EOF

${BOLD}On the Worker server ($WORKER_IP), run these commands:${NC}

${CYAN}# 1. Install Docker${NC}
curl -fsSL https://get.docker.com | bash

${CYAN}# 2. Clone the repo (or copy the compose file)${NC}
git clone https://github.com/amir-hdri/BarPro-main.git /opt/barpro
cd /opt/barpro

${CYAN}# 3. Create .env file${NC}
cat > /opt/barpro/.env << 'ENVEOF'
# Numeric IP index — MUST be in AVAILABLE_IP_INDICES on the Central server
# (first remote worker = 2, second remote worker = 3)
WORKER_ID=${WORKER_ID}
WORKER_IP_INDEX=${WORKER_ID}

CENTRAL_IP=${CENTRAL_IP}

# Database — uses barpro_worker role (least privilege)
# Replace <WORKER_DB_PASSWORD> with the password from create_worker_db_role.sql
DATABASE_URL=postgresql+asyncpg://barpro_worker:<WORKER_DB_PASSWORD>@${CENTRAL_IP}:5432/utcms_rpa

# Redis — use the same password as the Central server's REDIS_PASSWORD
# ⚠️ CELERY_BROKER_URL MUST use DB 0 (Central publishes tasks on DB 0)
REDIS_URL=redis://:<REDIS_PASSWORD>@${CENTRAL_IP}:6379/0
CELERY_BROKER_URL=redis://:<REDIS_PASSWORD>@${CENTRAL_IP}:6379/0
CELERY_RESULT_BACKEND=redis://:<REDIS_PASSWORD>@${CENTRAL_IP}:6379/0

WORKER_PROXY_PORT=3128
# This VPS's own public IP — for Squid tcp_outgoing_address (egress to UTCMS)
WORKER_EGRESS_IP=${WORKER_IP}
CAPTCHA_PROVIDER=auto
HEADLESS=true
ENVEOF

${CYAN}# 4. Render the Squid template before first run${NC}
# Never sed -i the git template (infra/squid/squid_worker.conf) — it would
# corrupt the tracked file for every future git pull. compose/worker-node.yml
# mounts the rendered copy infra/squid/squid_worker.runtime.conf instead (X4).
cd /opt/barpro
sed -e "s/__WORKER_EGRESS_IP__/${WORKER_IP}/g" \
    -e "s/__CENTRAL_IP__/${CENTRAL_IP}/g" \
    infra/squid/squid_worker.conf > infra/squid/squid_worker.runtime.conf

${CYAN}# 5. Start the Worker${NC}
# --env-file .env: compose interpolation must read /opt/barpro/.env, not
# ./compose/.env — otherwise WORKER_IP_INDEX/CENTRAL_IP placeholders break (X5).
docker compose --env-file .env -f compose/worker-node.yml up -d

${CYAN}# 6. Verify registration (run on Central server)${NC}
# The worker should appear in worker_registry within 30 seconds of startup.
# docker exec barpro-backend python -c "
# import asyncio
# from app.core.database import async_session_factory
# from app.models_rpa import WorkerRegistry
# from sqlmodel import select
# async def check():
#     async with async_session_factory() as s:
#         r = await s.exec(select(WorkerRegistry))
#         for w in r.all():
#             print(w.worker_id, w.status, w.last_heartbeat_at)
# asyncio.run(check())
# "

EOF

log_info "✅ Done! Worker $WORKER_ID ($WORKER_IP) can now reach PostgreSQL and Redis."
log_warn "   Don't forget to:"
log_warn "   1. Run scripts/create_worker_db_role.sql on PostgreSQL"
log_warn "   2. Set the actual passwords in the Worker's .env file"

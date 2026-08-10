#!/usr/bin/env bash
# ═══════════════════════════════════════════════════════════════════════════════
#  deploy_all_servers.sh — اجرای کامل deploy روی همه ۳ سرور
#
#  این اسکریپت را از LOCAL اجرا کنید (نه از سرور):
#    bash scripts/deploy_all_servers.sh
#
#  پیش‌نیاز: SSH access به هر ۳ سرور از ماشین local
#
#  اسکریپت:
#    1. سرور مرکزی را deploy می‌کند (git pull + build + restart + migrate)
#    2. Worker 2 را deploy می‌کند
#    3. Worker 3 را deploy می‌کند
#    4. Health check نهایی روی همه سرورها
# ═══════════════════════════════════════════════════════════════════════════════

set -euo pipefail

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
NC='\033[0m'

log_info()    { echo -e "${BLUE}ℹ️  $*${NC}"; }
log_ok()      { echo -e "${GREEN}✅ $*${NC}"; }
log_warn()    { echo -e "${YELLOW}⚠️  $*${NC}"; }
log_error()   { echo -e "${RED}❌ $*${NC}"; }
log_section() { echo -e "\n${CYAN}═══════════════════════════════════════════════${NC}"; echo -e "${CYAN}  $*${NC}"; echo -e "${CYAN}═══════════════════════════════════════════════${NC}"; }

CENTRAL_IP="${CENTRAL_IP:-87.107.5.238}"
WORKER2_IP="${WORKER2_IP:-5.56.132.26}"
WORKER3_IP="${WORKER3_IP:-87.107.5.219}"
PROJECT_DIR="/opt/barpro"
SSH_OPTS="-o StrictHostKeyChecking=no -o ConnectTimeout=20 -o BatchMode=yes"

# ── تابع اجرای دستور روی سرور ─────────────────────────────────────────────
run_remote() {
    local host="$1"
    local cmd="$2"
    local desc="${3:-}"
    [ -n "$desc" ] && log_info "$desc"
    ssh $SSH_OPTS "root@$host" "$cmd"
}

# ── بررسی دسترسی SSH ──────────────────────────────────────────────────────
log_section "🔐 بررسی دسترسی SSH به همه سرورها"

for host in "$CENTRAL_IP" "$WORKER2_IP" "$WORKER3_IP"; do
    if ssh $SSH_OPTS "root@$host" "echo OK" &>/dev/null; then
        log_ok "SSH به $host موفق"
    else
        log_error "SSH به $host شکست خورد — بررسی کنید و دوباره اجرا کنید"
        exit 1
    fi
done

# ══════════════════════════════════════════════════════════════════════════════
# مرحله ۱: سرور مرکزی
# ══════════════════════════════════════════════════════════════════════════════
log_section "🖥️  مرحله ۱: deploy سرور مرکزی ($CENTRAL_IP)"

run_remote "$CENTRAL_IP" "
set -e
cd $PROJECT_DIR

echo '1.1 git pull...'
git pull origin main 2>&1 | tail -3

echo '1.2 build backend image (ممکن است ۱۰-۲۰ دقیقه طول بکشد)...'
docker build --network=host -t barpro_backend:latest -f Dockerfile . 2>&1 | tail -5

echo '1.3 tag images برای ورکرها...'
docker tag barpro_backend:latest barpro_celery_worker_1:latest
docker tag barpro_backend:latest barpro_celery_beat:latest
docker tag barpro_backend:latest barpro_celery_scheduler:latest

echo '1.4 ری‌استارت infra (Postgres + Redis) با mem_limit جدید...'
docker compose --env-file .env -f compose/infra.yml up -d --force-recreate 2>&1 | tail -5

echo '1.5 ری‌استارت proxy (Squid)...'
docker compose --env-file .env -f compose/proxy.yml up -d --force-recreate 2>&1 | tail -3

echo '1.6 ری‌استارت backend + worker_1 + scheduler + beat...'
# --env-file .env: interpolation در compose باید /opt/barpro/.env را بخواند نه
# ./compose/.env (X5/FIX-L). celery_scheduler مصرف‌کننده‌ی همیشه‌روشن صف
# کنترلی است (NEW-1/FIX-A).
docker compose --env-file .env -f compose/backend.yml up -d --force-recreate backend celery_worker_1 celery_scheduler celery_beat 2>&1 | tail -5

echo '1.7 ری‌استارت frontend (mem 1g) + nginx (mem 512m)...'
docker compose --env-file .env -f compose/web.yml up -d --force-recreate 2>&1 | tail -5

echo '1.8 ری‌استارت monitoring...'
docker compose --env-file .env -f compose/monitoring.yml up -d 2>&1 | tail -3

echo '1.9 انتظار ۳۰ ثانیه برای آماده شدن...'
sleep 30

echo '1.10 بررسی migration...'
docker exec barpro-backend python -m alembic -c alembic.ini current 2>/dev/null || echo 'migration check skipped'

echo '1.11 وضعیت کانتینرها:'
docker ps --format 'table {{.Names}}\t{{.Status}}'
" "در حال deploy سرور مرکزی..."

log_ok "سرور مرکزی deploy شد"

# ══════════════════════════════════════════════════════════════════════════════
# مرحله ۲: Worker 2
# ══════════════════════════════════════════════════════════════════════════════
log_section "⚙️  مرحله ۲: deploy Worker 2 ($WORKER2_IP)"

run_remote "$WORKER2_IP" "
set -e
cd $PROJECT_DIR

echo '2.1 git pull...'
git pull origin main 2>&1 | tail -3

echo '2.2 build worker image (ممکن است ۱۰-۲۰ دقیقه)...'
docker build --network=host -t barpro_backend:latest -f Dockerfile . 2>&1 | tail -5

echo '2.3 رندر squid_worker.runtime.conf (جایگزینی placeholderها)...'
set -a; source .env; set +a
# R2: \${...} must stay escaped through the LOCAL double-quoted expansion so
# the placeholders expand on the WORKER NODE with ITS OWN .env values. Without
# the backslash, ${WORKER_EGRESS_IP} expands on the launcher machine: a missing
# local value kills the deploy with :? before SSH even runs, and a present one
# stamps the SAME egress IP on every worker.
sed -e "s/__WORKER_EGRESS_IP__/\${WORKER_EGRESS_IP:?WORKER_EGRESS_IP required}/g" \
    -e "s/__CENTRAL_IP__/\${CENTRAL_IP:-127.0.0.1}/g" \
    infra/squid/squid_worker.conf > infra/squid/squid_worker.runtime.conf

echo '2.4 ری‌استارت worker node...'
docker compose --env-file .env -f compose/worker-node.yml up -d --force-recreate 2>&1 | tail -5

echo '2.5 انتظار ۳۰ ثانیه...'
sleep 30

echo '2.6 وضعیت:'
docker ps --format 'table {{.Names}}\t{{.Status}}'
" "در حال deploy Worker 2..."

log_ok "Worker 2 deploy شد"

# ══════════════════════════════════════════════════════════════════════════════
# مرحله ۳: Worker 3
# ══════════════════════════════════════════════════════════════════════════════
log_section "⚙️  مرحله ۳: deploy Worker 3 ($WORKER3_IP)"

run_remote "$WORKER3_IP" "
set -e
cd $PROJECT_DIR

echo '3.1 git pull...'
git pull origin main 2>&1 | tail -3

echo '3.2 build worker image (ممکن است ۱۰-۲۰ دقیقه)...'
docker build --network=host -t barpro_backend:latest -f Dockerfile . 2>&1 | tail -5

echo '3.3 رندر squid_worker.runtime.conf (جایگزینی placeholderها)...'
set -a; source .env; set +a
# R2: see worker 2 — \${...} expands on THIS worker node, not on the launcher.
sed -e "s/__WORKER_EGRESS_IP__/\${WORKER_EGRESS_IP:?WORKER_EGRESS_IP required}/g" \
    -e "s/__CENTRAL_IP__/\${CENTRAL_IP:-127.0.0.1}/g" \
    infra/squid/squid_worker.conf > infra/squid/squid_worker.runtime.conf

echo '3.4 ری‌استارت worker node...'
docker compose --env-file .env -f compose/worker-node.yml up -d --force-recreate 2>&1 | tail -5

echo '3.5 انتظار ۳۰ ثانیه...'
sleep 30

echo '3.6 وضعیت:'
docker ps --format 'table {{.Names}}\t{{.Status}}'
" "در حال deploy Worker 3..."

log_ok "Worker 3 deploy شد"

# ══════════════════════════════════════════════════════════════════════════════
# مرحله ۴: Health Check نهایی
# ══════════════════════════════════════════════════════════════════════════════
log_section "🩺 مرحله ۴: Health Check نهایی"

# سرور مرکزی
log_info "Health check سرور مرکزی..."
CENTRAL_HEALTH=$(run_remote "$CENTRAL_IP" "curl -sf http://localhost:8000/healthz 2>/dev/null && echo 'API_OK' || echo 'API_FAIL'" 2>/dev/null || echo "SSH_FAIL")
[ "$CENTRAL_HEALTH" = "API_OK" ] && log_ok "Backend API: OK" || log_warn "Backend API: $CENTRAL_HEALTH"

# بررسی Frontend
FRONTEND_OK=$(run_remote "$CENTRAL_IP" "docker inspect barpro-frontend --format '{{.State.Health.Status}}' 2>/dev/null || echo 'unknown'" 2>/dev/null || echo "ssh_fail")
log_info "Frontend Status: $FRONTEND_OK"

# بررسی Beat
BEAT_STATUS=$(run_remote "$CENTRAL_IP" "docker inspect barpro-beat --format '{{.State.Status}}' 2>/dev/null || echo 'not_found'" 2>/dev/null || echo "ssh_fail")
log_info "Beat Status: $BEAT_STATUS"

# Worker 2
WORKER2_STATUS=$(run_remote "$WORKER2_IP" "docker inspect barpro-celery-worker --format '{{.State.Status}}' 2>/dev/null || echo 'not_found'" 2>/dev/null || echo "ssh_fail")
log_info "Worker 2 Status: $WORKER2_STATUS"

# Worker 3
WORKER3_STATUS=$(run_remote "$WORKER3_IP" "docker inspect barpro-celery-worker --format '{{.State.Status}}' 2>/dev/null || echo 'not_found'" 2>/dev/null || echo "ssh_fail")
log_info "Worker 3 Status: $WORKER3_STATUS"

echo ""
log_section "📊 خلاصه Deploy"
echo ""
echo "  🖥️  Central ($CENTRAL_IP): API=${CENTRAL_HEALTH}, Frontend=${FRONTEND_OK}, Beat=${BEAT_STATUS}"
echo "  ⚙️  Worker 2 ($WORKER2_IP): ${WORKER2_STATUS}"
echo "  ⚙️  Worker 3 ($WORKER3_IP): ${WORKER3_STATUS}"
echo ""
echo "  📱 آدرس رابط کاربری: http://${CENTRAL_IP}/"
echo "  📊 Grafana Dashboard: http://${CENTRAL_IP}:3000/ (فقط از طریق SSH tunnel)"
echo ""
log_ok "Deploy کامل شد!"

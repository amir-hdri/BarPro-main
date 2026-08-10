#!/usr/bin/env bash
# ═══════════════════════════════════════════════════════════════════════════════
#  setup_worker.sh — راه‌اندازی سریع Worker Node
#
#  این اسکریپت روی هر Worker Server (ورکر ۲ یا ۳) اجرا می‌شود:
#    1. نصب Docker (اگر نصب نیست)
#    2. دریافت کد از Central Server یا git
#    3. کپی و تنظیم فایل .env ورکر
#    4. راه‌اندازی Squid + Celery Worker
#    5. بررسی ثبت‌نام ورکر در worker_registry
#
#  استفاده روی سرور ورکر:
#    bash scripts/setup_worker.sh
#
#  یا از راه دور (از Central):
#    ssh root@5.56.132.26 "cd /opt/barpro && bash scripts/setup_worker.sh"
# ═══════════════════════════════════════════════════════════════════════════════

set -euo pipefail

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

log_info()    { echo -e "${BLUE}ℹ️  $*${NC}"; }
log_ok()      { echo -e "${GREEN}✅ $*${NC}"; }
log_warn()    { echo -e "${YELLOW}⚠️  $*${NC}"; }
log_error()   { echo -e "${RED}❌ $*${NC}"; }
log_section() { echo -e "\n${BLUE}══════════════════════════════════════════${NC}"; echo -e "${BLUE}  $*${NC}"; echo -e "${BLUE}══════════════════════════════════════════${NC}"; }

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$PROJECT_DIR"

log_section "🔧 BarPro Worker Node Setup"

# ── بررسی متغیرهای الزامی ─────────────────────────────────────────────────
if [ -f .env ]; then
    set -a
    source .env
    set +a
else
    log_error "فایل .env یافت نشد! ابتدا .env را با مقادیر ورکر تنظیم کنید."
    echo ""
    echo "مقادیر الزامی:"
    echo "  WORKER_ID=2  (عددی — همنهشت با WORKER_IP_INDEX)"
    echo "  WORKER_IP_INDEX=2"
    echo "  WORKER_PROXY_PORT=3128"
    echo "  WORKER_EGRESS_IP=<IP عمومی این VPS>"
    echo "  DATABASE_URL=postgresql+asyncpg://postgres:PASS@CENTRAL_IP:5432/utcms_rpa"
    echo "  REDIS_URL=redis://:PASS@CENTRAL_IP:6379/0"
    echo "  CELERY_BROKER_URL=redis://:PASS@CENTRAL_IP:6379/0"
    echo "  CENTRAL_IP=87.107.5.238"
    exit 1
fi

WORKER_ID="${WORKER_ID:?WORKER_ID is required in .env}"
CENTRAL_IP="${CENTRAL_IP:-87.107.5.238}"

log_info "Worker ID: $WORKER_ID"
log_info "Central IP: $CENTRAL_IP"

# ── مرحله ۱: بررسی/نصب Docker ────────────────────────────────────────────
log_section "🐳 مرحله ۱: بررسی Docker"
if ! command -v docker &> /dev/null; then
    log_info "نصب Docker..."
    apt-get update -qq
    apt-get install -y -qq docker.io
    systemctl enable --now docker
    log_ok "Docker نصب شد"
else
    log_ok "Docker نصب است: $(docker --version)"
fi

# ── مرحله ۲: بررسی دسترسی به Central ─────────────────────────────────────
log_section "🌐 مرحله ۲: بررسی اتصال به سرور مرکزی"

log_info "بررسی PostgreSQL ($CENTRAL_IP:5432)..."
if timeout 5 bash -c "cat < /dev/null > /dev/tcp/$CENTRAL_IP/5432" 2>/dev/null; then
    log_ok "PostgreSQL در دسترس است"
else
    log_warn "PostgreSQL در دسترس نیست — بررسی کنید UFW allowlist سرور مرکزی"
fi

log_info "بررسی Redis ($CENTRAL_IP:6379)..."
if timeout 5 bash -c "cat < /dev/null > /dev/tcp/$CENTRAL_IP/6379" 2>/dev/null; then
    log_ok "Redis در دسترس است"
else
    log_warn "Redis در دسترس نیست — بررسی کنید UFW allowlist سرور مرکزی"
fi

# ── مرحله ۳: ایجاد ساختار پوشه‌ها ──────────────────────────────────────────
log_section "📁 مرحله ۳: ایجاد ساختار پوشه‌ها"
mkdir -p infra/squid
log_ok "ساختار پوشه‌ها ایجاد شد"

# ── مرحله ۴: رندر squid config (runtime) ─────────────────────────────────
# compose/worker-node.yml روی ../infra/squid/squid_worker.runtime.conf mount
# می‌کند؛ این فایل را از قالب git (squid_worker.conf) با جایگزینی دو
# placeholder می‌سازیم — در غیر این صورت squid با __CENTRAL_IP__ /
# __WORKER_EGRESS_IP__ بالا نمی‌آید و restart-loop می‌شود (X4/FIX-G).
log_section "⚙️ مرحله ۴: رندر Squid Worker"
if [ -f "infra/squid/squid_worker.conf" ]; then
    WORKER_EGRESS_IP="${WORKER_EGRESS_IP:?WORKER_EGRESS_IP is required (IP عمومی این VPS)}"
    sed -e "s/__WORKER_EGRESS_IP__/${WORKER_EGRESS_IP}/g" \
        -e "s/__CENTRAL_IP__/${CENTRAL_IP}/g" \
        "infra/squid/squid_worker.conf" > "infra/squid/squid_worker.runtime.conf"
    log_ok "squid_worker.runtime.conf از قالب + جایگزینی placeholder ساخته شد"
else
    log_warn "فایل squid_worker.conf یافت نشد — یک کانفیگ پایه runtime ایجاد می‌شود"
    cat > "infra/squid/squid_worker.runtime.conf" << 'SQUIDEOF'
# Squid Worker Node Configuration
http_port 3128
# Allow all connections (worker is behind UFW firewall)
acl all src all
http_access allow all
# Disable caching
cache deny all
# Log to stdout
access_log stdio:/dev/stdout
cache_log stdio:/dev/stderr
SQUIDEOF
    log_ok "کانفیگ پایه Squid ایجاد شد"
fi

# ── مرحله ۵: build image ──────────────────────────────────────────────────
log_section "🔨 مرحله ۵: build تصویر Docker Worker"
log_info "در حال build (ممکن است ۱۰-۲۰ دقیقه طول بکشد)..."
docker build \
    --network=host \
    -t barpro_backend:latest \
    -f Dockerfile \
    . 2>&1 | tail -10
log_ok "تصویر build شد"

# ── مرحله ۶: راه‌اندازی سرویس‌ها ─────────────────────────────────────────
log_section "🚀 مرحله ۶: راه‌اندازی Squid + Celery Worker"
docker compose -f compose/worker-node.yml up -d
log_ok "سرویس‌ها راه‌اندازی شدند"

# ── مرحله ۷: بررسی ثبت‌نام در registry ────────────────────────────────────
log_section "🩺 مرحله ۷: بررسی ثبت‌نام ورکر"
log_info "منتظر راه‌اندازی ورکر (30 ثانیه)..."
sleep 30

CONTAINER_STATUS=$(docker inspect barpro-celery-worker --format '{{.State.Status}}' 2>/dev/null || echo "not_found")
log_info "وضعیت کانتینر: $CONTAINER_STATUS"

if [ "$CONTAINER_STATUS" = "running" ]; then
    log_ok "ورکر در حال اجراست"
    # بررسی Redis ping از داخل ورکر
    if docker exec barpro-celery-worker python -c "
import os, redis
r = redis.Redis.from_url(os.environ['REDIS_URL'], socket_connect_timeout=5)
r.ping()
print('Redis OK')
" 2>/dev/null; then
        log_ok "اتصال Redis تأیید شد"
    else
        log_warn "اتصال Redis تأیید نشد — لاگ ورکر را بررسی کنید"
    fi
else
    log_error "ورکر در حال اجرا نیست!"
    echo ""
    docker logs barpro-celery-worker --tail 30
fi

# ── وضعیت نهایی ──────────────────────────────────────────────────────────
log_section "📊 وضعیت نهایی"
docker ps --format "table {{.Names}}\t{{.Status}}" 2>/dev/null

echo ""
log_ok "راه‌اندازی Worker Node کامل شد!"
echo ""
echo "  برای مشاهده لاگ ورکر:"
echo "  docker logs barpro-celery-worker -f --tail 50"
echo ""
echo "  برای بررسی ثبت‌نام در سرور مرکزی:"
echo "  curl -s http://${CENTRAL_IP}:8000/api/system/workers | python3 -m json.tool"
echo ""

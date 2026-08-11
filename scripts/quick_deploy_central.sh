#!/usr/bin/env bash
# ═══════════════════════════════════════════════════════════════════════════════
#  quick_deploy_central.sh — استقرار سریع روی سرور مرکزی BarPro
#
#  این اسکریپت تمام مراحل استقرار را روی سرور مرکزی (87.107.5.238) انجام می‌دهد:
#    1. git pull (دریافت آخرین کد)
#    2. docker compose build (build بک‌اند + فرانت‌اند)
#    3. restart celery_beat (رفع OOM با mem_limit جدید 256MB)
#    4. docker compose web.yml up (Nginx + Frontend)
#    5. docker compose monitoring.yml up (Prometheus + Grafana)
#    6. alembic upgrade head (migration اگر لازم باشد)
#    7. بررسی سلامت کلی
#
#  استفاده (روی سرور مرکزی از /opt/barpro):
#    bash scripts/quick_deploy_central.sh
#
#  یا از راه دور:
#    ssh root@87.107.5.238 "cd /opt/barpro && git pull && bash scripts/quick_deploy_central.sh"
# ═══════════════════════════════════════════════════════════════════════════════

set -euo pipefail

# ── رنگ‌ها برای خروجی ────────────────────────────────────────────────────────
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

log_info()    { echo -e "${BLUE}ℹ️  $*${NC}"; }
log_ok()      { echo -e "${GREEN}✅ $*${NC}"; }
log_warn()    { echo -e "${YELLOW}⚠️  $*${NC}"; }
log_error()   { echo -e "${RED}❌ $*${NC}"; }
log_section() { echo -e "\n${BLUE}══════════════════════════════════════════${NC}"; echo -e "${BLUE}  $*${NC}"; echo -e "${BLUE}══════════════════════════════════════════${NC}"; }

# ── تنظیمات ──────────────────────────────────────────────────────────────────
PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$PROJECT_DIR"

# بارگذاری متغیرهای محیطی
if [ -f .env ]; then
    set -a
    source .env
    set +a
fi

log_section "🚀 BarPro Central Server — Quick Deploy"
echo "  مسیر پروژه: $PROJECT_DIR"
echo "  زمان: $(date '+%Y-%m-%d %H:%M:%S')"

# ── مرحله ۱: git pull ─────────────────────────────────────────────────────
log_section "📥 مرحله ۱: دریافت آخرین کد از git"
git pull origin main || log_warn "git pull failed (ممکن است local changes داشته باشید)"
log_ok "کد به‌روز شد"

# ── مرحله ۱.۵: رندر کانفیگ‌های Squid ─────────────────────────────────────
# قالب‌های گیت (squid_1/2/3.conf) هرگز نباید sed -i شوند — این اسکریپت آن‌ها را
# به squid_<N>.runtime.conf رندر می‌کند که compose/proxy.yml mount می‌کند.
# بدون این مرحله، بعد از git pull فایل‌های runtime قدیمی می‌مانند و pullهای بعدی
# با درخت کثیف شکست می‌خورند (X4 — سمت مرکزی).
log_section "🦑 مرحله ۱.۵: رندر کانفیگ‌های Squid"
bash scripts/render_squid_configs.sh
log_ok "کانفیگ‌های Squid رندر شدند (egress از .env)"

# ── مرحله ۲: اطمینان از وجود شبکه ──────────────────────────────────────────
log_section "🌐 مرحله ۲: بررسی Docker network"
if ! docker network inspect barpro_platform > /dev/null 2>&1; then
    log_info "ایجاد شبکه barpro_platform..."
    docker network create --subnet=172.20.0.0/16 barpro_platform
    log_ok "شبکه ایجاد شد"
else
    log_ok "شبکه barpro_platform موجود است"
fi

# ── مرحله ۳: build تصاویر ──────────────────────────────────────────────────
log_section "🔨 مرحله ۳: build تصاویر Docker"
log_info "در حال build بک‌اند (ممکن است ۱۰-۲۰ دقیقه طول بکشد)..."
docker compose -f compose/backend.yml build backend 2>&1 | tail -5
log_ok "build بک‌اند کامل شد"

log_info "در حال build فرانت‌اند..."
docker compose -f compose/web.yml build frontend 2>&1 | tail -5
log_ok "build فرانت‌اند کامل شد"

# ── مرحله ۴: restart بک‌اند ────────────────────────────────────────────────
log_section "🔄 مرحله ۴: restart سرویس‌های بک‌اند"
docker compose -f compose/backend.yml up -d
log_ok "بک‌اند، ورکر ۱ و Beat راه‌اندازی شدند"

# ── مرحله ۵: restart خاص Beat (رفع OOM) ────────────────────────────────────
log_section "🔄 مرحله ۵: restart ویژه Celery Beat (mem_limit=256MB)"
log_info "force-recreate Beat با تنظیمات جدید حافظه..."
docker compose -f compose/backend.yml up -d --no-deps --force-recreate celery_beat
log_ok "Beat با mem_limit=256m راه‌اندازی شد"

# ── مرحله ۶: web.yml (Nginx + Frontend) ────────────────────────────────────
log_section "🌍 مرحله ۶: راه‌اندازی Nginx + Frontend"
docker compose -f compose/web.yml up -d
log_ok "Nginx و Frontend راه‌اندازی شدند"

# ── مرحله ۷: monitoring.yml ────────────────────────────────────────────────
log_section "📊 مرحله ۷: راه‌اندازی Monitoring (Prometheus + Grafana)"

# ایجاد volume‌های لازم اگر وجود ندارند
docker volume create barpro_prometheus_data 2>/dev/null || true
docker volume create barpro_grafana_data 2>/dev/null || true

docker compose -f compose/monitoring.yml up -d
log_ok "Prometheus و Grafana راه‌اندازی شدند"

# ── مرحله ۸: migration ──────────────────────────────────────────────────────
log_section "🗄️ مرحله ۸: Alembic migration"
log_info "منتظر راه‌اندازی backend (15 ثانیه)..."
sleep 15

MIGRATION_CURRENT=$(docker exec barpro-backend alembic current 2>/dev/null || echo "unknown")
log_info "version فعلی: $MIGRATION_CURRENT"

if echo "$MIGRATION_CURRENT" | grep -q "(head)"; then
    log_ok "دیتابیس در آخرین version است — migration نیاز ندارد"
else
    log_info "در حال اجرای migrations..."
    docker exec barpro-backend alembic upgrade head
    log_ok "migrations با موفقیت اجرا شدند"
fi

# ── مرحله ۹: بررسی حجم حافظه ───────────────────────────────────────────────
log_section "💾 مرحله ۹: بررسی مصرف حافظه"
echo ""
docker stats --no-stream --format "table {{.Name}}\t{{.CPUPerc}}\t{{.MemUsage}}\t{{.MemPerc}}" 2>/dev/null | head -20

# ── مرحله ۱۰: بررسی وضعیت کانتینرها ─────────────────────────────────────
log_section "🩺 مرحله ۱۰: وضعیت نهایی کانتینرها"
echo ""
docker ps --format "table {{.Names}}\t{{.Status}}\t{{.Ports}}" 2>/dev/null

# ── خلاصه ────────────────────────────────────────────────────────────────────
log_section "✅ استقرار کامل شد!"
echo ""

# بررسی سریع سلامت
BACKEND_HEALTH=$(curl -sf http://localhost:8000/healthz 2>/dev/null | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('status','?'))" 2>/dev/null || echo "N/A")
NGINX_HTTP=$(curl -s -o /dev/null -w "%{http_code}" http://localhost:80 2>/dev/null || echo "FAIL")

echo "  Backend healthz:  $BACKEND_HEALTH"
echo "  Nginx HTTP:       $NGINX_HTTP"

BEAT_STATUS=$(docker inspect barpro-beat --format '{{.State.Status}}' 2>/dev/null || echo "unknown")
echo "  Celery Beat:      $BEAT_STATUS"

echo ""
echo "  🌐 Frontend:   http://87.107.5.238"
echo "  📊 Prometheus: http://87.107.5.238:9090 (internal)"
echo ""
echo "  برای بررسی لاگ Beat:"
echo "  docker logs barpro-beat --tail 50"
echo ""

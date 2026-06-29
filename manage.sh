#!/usr/bin/env bash
# ═══════════════════════════════════════════════════════════════════════════════
#  BarPro — Management Script v2.0
#  مدیریت کامل پروژه با ساختار لایه‌بندی شده
#
#  استفاده:
#    bash manage.sh <دستور> [لایه]
#
#  دستورات کلی:
#    start           راه‌اندازی کل پروژه (همه لایه‌ها)
#    stop            توقف کل پروژه
#    restart         ری‌استارت کل پروژه
#    status          نمایش وضعیت همه سرویس‌ها
#    health          بررسی سلامت سرویس‌ها
#    logs [سرویس]   نمایش لاگ‌ها
#    build           ساخت دوباره ایمیج‌های Docker
#    deploy          بیلد + ری‌استارت (برای انتشار نسخه جدید)
#    backup          گرفتن نسخه پشتیبان از پایگاه داده
#
#  دستورات لایه‌ای (برای دیباگ):
#    start infra     فقط PostgreSQL + Redis
#    start proxy     فقط Squid Proxies
#    start backend   فقط بک‌اند + ورکرها
#    start web       فقط فرانت‌اند + Nginx
#    start mon       فقط Prometheus
#    stop backend    توقف فقط بک‌اند
#    restart web     ری‌استارت فقط وب
#    logs backend    لاگ‌های لایه بک‌اند
#
#  دستورات دیباگ:
#    shell <سرویس>  باز کردن shell داخل کانتینر
#    inspect         بررسی کامل سیستم
#    netcheck        بررسی ارتباط بین کانتینرها
# ═══════════════════════════════════════════════════════════════════════════════

set -euo pipefail

# ── رنگ‌ها ─────────────────────────────────────────────────────────────────────
RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'
BLUE='\033[0;34m'; CYAN='\033[0;36m'; BOLD='\033[1m'; RESET='\033[0m'

# ── مسیرها ─────────────────────────────────────────────────────────────────────
DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
COMPOSE_DIR="$DIR/compose"

# ── تعریف لایه‌ها ──────────────────────────────────────────────────────────────
declare -A LAYER_FILES=(
  [infra]="$COMPOSE_DIR/infra.yml"
  [proxy]="$COMPOSE_DIR/proxy.yml"
  [backend]="$COMPOSE_DIR/backend.yml"
  [web]="$COMPOSE_DIR/web.yml"
  [mon]="$COMPOSE_DIR/monitoring.yml"
)

declare -A LAYER_NAMES=(
  [infra]="🗄️  زیرساخت (PostgreSQL + Redis)"
  [proxy]="🔁  پروکسی‌ها (Squid 1/2/3)"
  [backend]="⚙️  بک‌اند (FastAPI + Celery Workers + Beat)"
  [web]="🌐  وب (Next.js + Nginx)"
  [mon]="📊  مانیتورینگ (Prometheus)"
)

# ترتیب راه‌اندازی لایه‌ها
LAYER_ORDER=(infra proxy backend web mon)

# ── توابع کمکی ─────────────────────────────────────────────────────────────────
log_info()    { echo -e "${BLUE}ℹ️  $*${RESET}"; }
log_ok()      { echo -e "${GREEN}✅  $*${RESET}"; }
log_warn()    { echo -e "${YELLOW}⚠️  $*${RESET}"; }
log_error()   { echo -e "${RED}❌  $*${RESET}"; }
log_section() { echo -e "\n${BOLD}${CYAN}── $* ──────────────────────────────────────────${RESET}"; }

# بررسی وجود Docker
check_docker() {
  if ! command -v docker &>/dev/null; then
    log_error "Docker نصب نیست!"; exit 1
  fi
  if ! docker compose version &>/dev/null; then
    log_error "Docker Compose V2 نصب نیست!"; exit 1
  fi
}

# بررسی وجود فایل .env
check_env() {
  if [[ ! -f "$DIR/.env" ]]; then
    log_error "فایل .env یافت نشد!"
    log_info  "نمونه: cp $DIR/.env.example $DIR/.env"
    exit 1
  fi
}

# اجرای دستور docker compose برای یک لایه
layer_compose() {
  local layer="$1"; shift
  local file="${LAYER_FILES[$layer]}"
  if [[ ! -f "$file" ]]; then
    log_error "فایل لایه $layer یافت نشد: $file"
    exit 1
  fi
  docker compose \
    --project-name barpro \
    --project-directory "$COMPOSE_DIR" \
    --env-file "$DIR/.env" \
    -f "$file" \
    "$@"
}

# ── دستورات اصلی ───────────────────────────────────────────────────────────────

cmd_start() {
  local target="${1:-all}"
  check_docker; check_env

  # ایجاد شبکه اگر وجود نداشت
  docker network inspect barpro_platform &>/dev/null 2>&1 || \
    docker network create barpro_platform

  if [[ "$target" == "all" ]]; then
    log_section "🚀 راه‌اندازی کل پروژه"
    for layer in "${LAYER_ORDER[@]}"; do
      echo -e "\n${BOLD}${LAYER_NAMES[$layer]}${RESET}"
      layer_compose "$layer" up -d
      # صبر برای سرویس‌های حساس
      case "$layer" in
        infra)
          log_info "انتظار برای سلامت پایگاه داده..."
          sleep 5
          ;;
        backend)
          log_info "انتظار برای راه‌اندازی بک‌اند (این ممکن است ۱-۲ دقیقه طول بکشد)..."
          sleep 10
          ;;
      esac
    done
    log_ok "همه سرویس‌ها راه‌اندازی شدند!"
    cmd_status
  else
    if [[ -z "${LAYER_FILES[$target]+_}" ]]; then
      log_error "لایه '$target' وجود ندارد. لایه‌های موجود: ${!LAYER_FILES[*]}"
      exit 1
    fi
    log_section "🚀 راه‌اندازی لایه: ${LAYER_NAMES[$target]}"
    layer_compose "$target" up -d
    log_ok "لایه $target راه‌اندازی شد!"
  fi
}

cmd_stop() {
  local target="${1:-all}"
  check_docker

  if [[ "$target" == "all" ]]; then
    log_section "🛑 توقف کل پروژه"
    for layer in "${LAYER_ORDER[@]}"; do
      echo -e "  توقف: ${LAYER_NAMES[$layer]}"
      layer_compose "$layer" down 2>/dev/null || true
    done
    log_ok "همه سرویس‌ها متوقف شدند!"
  else
    log_section "🛑 توقف لایه: ${LAYER_NAMES[$target]}"
    layer_compose "$target" down
    log_ok "لایه $target متوقف شد!"
  fi
}

cmd_restart() {
  local target="${1:-all}"
  if [[ "$target" == "all" ]]; then
    cmd_stop all
    sleep 3
    cmd_start all
  else
    log_section "🔄 ری‌استارت لایه: ${LAYER_NAMES[$target]}"
    layer_compose "$target" down
    layer_compose "$target" up -d
    if [[ "$target" == "backend" || "$target" == "web" ]]; then
      log_info "ری‌استارت پروکسی Nginx جهت اعمال کش DNS..."
      layer_compose "web" restart nginx 2>/dev/null || true
    fi
    log_ok "لایه $target ری‌استارت شد!"
  fi
}

cmd_status() {
  log_section "📊 وضعیت سرویس‌ها"
  docker ps -a \
    --filter "network=barpro_platform" \
    --format "table {{.Names}}\t{{.Status}}\t{{.Ports}}"

  echo ""
  echo -e "${BOLD}  💾 دیسک:${RESET} $(df -h / | awk 'NR==2{print $3 " از " $2 " استفاده شده (" $4 " آزاد)"}')"
  echo -e "${BOLD}  🧠 RAM :${RESET} $(free -h | awk '/^Mem:/{print $3 " از " $2 " استفاده شده"}')"
  echo ""
}

cmd_health() {
  log_section "🏥 بررسی سلامت سرویس‌ها"

  # بررسی هر سرویس
  local services=(
    "nginx:barpro-nginx:80:http://localhost"
    "backend:barpro-backend:8000:http://localhost/healthz"
    "postgres:barpro-postgres::pg_isready"
    "redis:barpro-redis::redis_ping"
    "frontend:barpro-frontend:3000:http://localhost:3000"
    "prometheus:barpro-prometheus:9090:http://localhost:9090/-/healthy"
  )

  for entry in "${services[@]}"; do
    IFS=':' read -r name container port url <<< "$entry"
    if docker inspect "$container" &>/dev/null; then
      status=$(docker inspect --format='{{.State.Status}}' "$container" 2>/dev/null)
      health=$(docker inspect --format='{{if .State.Health}}{{.State.Health.Status}}{{else}}N/A{{end}}' "$container" 2>/dev/null)
      if [[ "$status" == "running" ]]; then
        printf "  ${GREEN}✓${RESET}  %-20s  وضعیت: %-10s  سلامت: %s\n" "$name" "$status" "$health"
      else
        printf "  ${RED}✗${RESET}  %-20s  وضعیت: %-10s  سلامت: %s\n" "$name" "$status" "$health"
      fi
    else
      printf "  ${YELLOW}?${RESET}  %-20s  ${YELLOW}کانتینر وجود ندارد${RESET}\n" "$name"
    fi
  done
  echo ""
}

cmd_logs() {
  local target="${1:-all}"
  local follow="${2:--f}"

  if [[ "$target" == "all" ]]; then
    docker compose --env-file "$DIR/.env" \
      -f "$COMPOSE_DIR/infra.yml" \
      -f "$COMPOSE_DIR/proxy.yml" \
      -f "$COMPOSE_DIR/backend.yml" \
      -f "$COMPOSE_DIR/web.yml" \
      -f "$COMPOSE_DIR/monitoring.yml" \
      logs -f --tail=50
  elif [[ -n "${LAYER_FILES[$target]+_}" ]]; then
    log_section "📋 لاگ‌های لایه: ${LAYER_NAMES[$target]}"
    layer_compose "$target" logs -f --tail=100
  else
    # اگر نام سرویس مستقیم داده شده باشد
    log_section "📋 لاگ‌های سرویس: $target"
    docker logs "$target" -f --tail=100
  fi
}

cmd_build() {
  local target="${1:-all}"
  check_docker; check_env

  if [[ "$target" == "all" ]]; then
    log_section "🔨 ساخت همه ایمیج‌ها"
    for layer in backend web; do
      echo -e "\n${BOLD}بیلد لایه: ${LAYER_NAMES[$layer]}${RESET}"
      layer_compose "$layer" build --no-cache
    done
    log_ok "همه ایمیج‌ها ساخته شدند!"
  else
    log_section "🔨 ساخت ایمیج‌های لایه: ${LAYER_NAMES[$target]}"
    layer_compose "$target" build --no-cache
    log_ok "ایمیج‌های لایه $target ساخته شدند!"
  fi
}

cmd_deploy() {
  log_section "🚀 استقرار نسخه جدید"
  check_docker; check_env

  log_info "بیلد ایمیج‌های backend..."
  layer_compose backend build

  log_info "بیلد ایمیج فرانت‌اند..."
  layer_compose web build

  log_info "اعمال تغییرات با zero-downtime..."
  layer_compose backend up -d --remove-orphans
  layer_compose web up -d --remove-orphans

  log_ok "استقرار با موفقیت انجام شد!"
  cmd_status
}

cmd_backup() {
  local ts; ts=$(date +%Y%m%d_%H%M%S)
  local backup_dir="$DIR/output/backups"
  mkdir -p "$backup_dir"

  log_section "💾 پشتیبان‌گیری"
  log_info "در حال گرفتن پشتیبان از پایگاه داده..."

  docker exec barpro-postgres pg_dump \
    -U postgres "${POSTGRES_DB:-utcms_rpa}" \
    | gzip > "$backup_dir/db_backup_$ts.sql.gz"

  log_ok "پشتیبان ذخیره شد: $backup_dir/db_backup_$ts.sql.gz"
}

cmd_shell() {
  local service="${1:-}"
  if [[ -z "$service" ]]; then
    log_error "نام سرویس را وارد کنید."
    echo "  مثال: bash manage.sh shell barpro-backend"
    exit 1
  fi
  log_section "🖥️  Shell سرویس: $service"
  docker exec -it "$service" /bin/bash 2>/dev/null || docker exec -it "$service" /bin/sh
}

cmd_netcheck() {
  log_section "🔌 بررسی ارتباط بین کانتینرها"

  echo -e "\n${BOLD}بررسی ارتباط backend → postgres:${RESET}"
  docker exec barpro-backend python -c \
    "import asyncio, asyncpg, os; url=os.environ.get('DATABASE_URL', '').replace('+asyncpg', ''); asyncio.run(asyncpg.connect(url))" \
    2>/dev/null && log_ok "backend → postgres: متصل" || log_warn "backend → postgres: قطع"

  echo -e "\n${BOLD}بررسی ارتباط backend → redis:${RESET}"
  docker exec barpro-backend python -c \
    "import redis, os; r=redis.from_url(os.environ.get('REDIS_URL', 'redis://redis:6379/0')); r.ping()" \
    2>/dev/null && log_ok "backend → redis: متصل" || log_warn "backend → redis: قطع"

  echo -e "\n${BOLD}بررسی ارتباط nginx → backend:${RESET}"
  docker exec barpro-nginx wget -qO- http://barpro-backend:8000/healthz \
    2>/dev/null && log_ok "nginx → backend: متصل" || log_warn "nginx → backend: قطع"

  echo -e "\n${BOLD}بررسی ارتباط nginx → frontend:${RESET}"
  docker exec barpro-nginx wget -qO/dev/null http://barpro-frontend:3000 \
    2>/dev/null && log_ok "nginx → frontend: متصل" || log_warn "nginx → frontend: قطع"

  echo -e "\n${BOLD}بررسی ارتباط worker → squid:${RESET}"
  docker exec barpro-worker-1 curl -sx http://barpro-squid-1:3128 http://httpbin.org/ip \
    2>/dev/null | grep -q origin && log_ok "worker_1 → squid_1: متصل" || log_warn "worker_1 → squid_1: قطع"
}

cmd_inspect() {
  log_section "🔍 بررسی کامل سیستم"
  cmd_status
  cmd_health
  echo ""
  echo -e "${BOLD}📦 ایمیج‌های Docker:${RESET}"
  docker images --filter "reference=barpro*" --format "table {{.Repository}}\t{{.Tag}}\t{{.Size}}\t{{.CreatedAt}}"
  echo ""
  echo -e "${BOLD}💽 والیوم‌های Docker:${RESET}"
  docker volume ls --filter "name=barpro*"
  echo ""
  echo -e "${BOLD}🌐 شبکه‌های Docker:${RESET}"
  docker network ls --filter "name=barpro*"
}

# ── پردازش دستورات ──────────────────────────────────────────────────────────────
CMD="${1:-help}"
ARG2="${2:-all}"

case "$CMD" in
  start)   cmd_start   "$ARG2" ;;
  stop)    cmd_stop    "$ARG2" ;;
  restart) cmd_restart "$ARG2" ;;
  status)  cmd_status          ;;
  health)  cmd_health          ;;
  logs)    cmd_logs    "$ARG2" ;;
  build)   cmd_build   "$ARG2" ;;
  deploy)  cmd_deploy          ;;
  backup)  cmd_backup          ;;
  shell)   cmd_shell   "$ARG2" ;;
  netcheck) cmd_netcheck       ;;
  inspect) cmd_inspect         ;;
  help|*)
    echo -e "${BOLD}${CYAN}"
    echo "  BarPro Management Script v2.0"
    echo -e "${RESET}"
    echo -e "${BOLD}دستورات کلی:${RESET}"
    echo "  bash manage.sh start            راه‌اندازی کل پروژه"
    echo "  bash manage.sh stop             توقف کل پروژه"
    echo "  bash manage.sh restart          ری‌استارت کل پروژه"
    echo "  bash manage.sh status           وضعیت سرویس‌ها"
    echo "  bash manage.sh health           بررسی سلامت"
    echo "  bash manage.sh logs [سرویس]     نمایش لاگ‌ها"
    echo "  bash manage.sh deploy           استقرار نسخه جدید"
    echo "  bash manage.sh backup           پشتیبان‌گیری"
    echo ""
    echo -e "${BOLD}دستورات لایه‌ای (برای دیباگ):${RESET}"
    echo "  bash manage.sh start infra      فقط PostgreSQL + Redis"
    echo "  bash manage.sh start proxy      فقط Squid Proxies"
    echo "  bash manage.sh start backend    فقط بک‌اند + ورکرها"
    echo "  bash manage.sh start web        فقط فرانت‌اند + Nginx"
    echo "  bash manage.sh start mon        فقط Prometheus"
    echo "  bash manage.sh stop backend     توقف لایه بک‌اند"
    echo "  bash manage.sh restart web      ری‌استارت لایه وب"
    echo ""
    echo -e "${BOLD}دستورات دیباگ:${RESET}"
    echo "  bash manage.sh shell barpro-backend   ورود به shell بک‌اند"
    echo "  bash manage.sh shell barpro-postgres  ورود به shell DB"
    echo "  bash manage.sh netcheck               بررسی ارتباط بین سرویس‌ها"
    echo "  bash manage.sh inspect                بررسی کامل سیستم"
    ;;
esac

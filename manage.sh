#!/usr/bin/env bash
# ═══════════════════════════════════════════════════════════════════════════
#  BarPro — مدیریت سرور  (manage.sh)
#  مکان: /opt/barpro/manage.sh
#  استفاده: bash /opt/barpro/manage.sh <دستور>
# ═══════════════════════════════════════════════════════════════════════════
set -euo pipefail

DIR="/opt/barpro"
cd "$DIR"

GR='\033[92m'; RD='\033[91m'; YL='\033[93m'; CY='\033[96m'
BL='\033[94m'; RS='\033[0m';  BD='\033[1m'
ok()  { echo -e "  ${GR}✓${RS}  $*"; }
err() { echo -e "  ${RD}✗${RS}  ${RD}$*${RS}"; exit 1; }
inf() { echo -e "  ${CY}→${RS}  $*"; }
warn(){ echo -e "  ${YL}⚠${RS}  ${YL}$*${RS}"; }
hdr() { echo -e "\n${BD}${BL}── $* ────────────────────────────────────────${RS}"; }

DC="docker compose"
$DC version &>/dev/null || DC="docker-compose"

cmd_status() {
    hdr "📊  وضعیت سرویس‌ها"
    $DC ps --format "table {{.Name}}\t{{.Status}}\t{{.Ports}}"
    echo
    df -h / | awk 'NR>1{printf "  💾 دیسک: %s از %s استفاده شده (%s آزاد)\n",$3,$2,$4}'
    free -h | awk '/Mem:/{printf "  🧠 RAM : %s از %s استفاده شده\n",$3,$2}'
}

cmd_health() {
    hdr "🏥  بررسی سلامت"
    curl -sf http://localhost/ -o /dev/null      && ok "Nginx/Frontend" || warn "Nginx/Frontend — مشکل دارد"
    curl -sf http://localhost/healthz -o /dev/null 2>/dev/null \
      || curl -sf http://localhost:8000/healthz -o /dev/null 2>/dev/null \
      && ok "Backend API" || warn "Backend API — مشکل دارد"
    $DC exec -T postgres pg_isready -U postgres &>/dev/null && ok "PostgreSQL" || warn "PostgreSQL"
    $DC exec -T redis redis-cli -a "${REDIS_PASSWORD:-redis}" ping 2>/dev/null | grep -q PONG && ok "Redis" || warn "Redis"
}

cmd_logs() {
    local svc="${1:-}"
    if [ -n "$svc" ]; then
        $DC logs -f --tail=100 "$svc"
    else
        $DC logs --tail=50
    fi
}

cmd_ip_status() {
    hdr "🌐  وضعیت IP‌ها"
    for ip_info in "188.121.123.16:IP اصلی" "95.38.233.90:IP ثانویه"; do
        local ip="${ip_info%%:*}" label="${ip_info##*:}"
        if curl -sf --interface "$ip" --max-time 5 https://api.ipify.org &>/dev/null; then
            ok "$label ($ip) — فعال"
        else
            warn "$label ($ip) — قابل دسترس نیست"
        fi
    done
    echo
    for s in squid_1 squid_2 squid_3; do
        $DC ps "$s" 2>/dev/null | grep -q "Up" && ok "$s" || warn "$s متوقف"
    done
}

# ── آپدیت هوشمند ──────────────────────────────────────────────────────────

cmd_update_ui() {
    hdr "🎨  آپدیت فرانت‌اند — بدون از دست رفتن داده"
    inf "نصب پکیج‌های npm..."
    cd "$DIR/apps/web"
    npm install --prefer-offline 2>&1 | tail -3
    inf "بیلد Next.js..."
    NODE_ENV=production NEXT_PUBLIC_API_URL="http://188.121.123.16/api" npm run build 2>&1 | tail -10
    cd "$DIR"
    inf "فقط کانتینر frontend rebuild می‌شود..."
    $DC up -d --build --no-deps frontend
    ok "✅ فرانت‌اند آپدیت شد — بقیه سرویس‌ها و داده‌ها دست‌نخورده‌اند"
}

cmd_update_api() {
    hdr "⚙️  آپدیت بک‌اند — بدون از دست رفتن داده"
    $DC up -d --build --no-deps backend celery_worker_1 celery_worker_2 celery_worker_3 celery_beat
    sleep 5
    $DC exec -T backend alembic upgrade head 2>&1 || warn "مایگریشن — خطا"
    ok "✅ بک‌اند آپدیت شد — داده‌ها دست‌نخورده‌اند"
}

cmd_update_all() {
    hdr "🔄  آپدیت کامل — داده‌ها حفظ می‌شوند"
    warn "Postgres و Redis volume هرگز حذف نمی‌شوند"
    read -r -p "  ادامه؟ [y/N] " c; [[ "$c" =~ ^[Yy]$ ]] || return
    $DC up -d --build --remove-orphans
    sleep 5; $DC exec -T backend alembic upgrade head 2>&1 || true
    ok "✅ همه سرویس‌ها آپدیت شدند"
}

# ── GitHub ────────────────────────────────────────────────────────────────

cmd_git_setup() {
    hdr "🔗  اتصال به GitHub"
    if [ -d "$DIR/.git" ]; then ok "Git از قبل تنظیم شده"; git remote -v; return; fi

    read -r -p "  آدرس repo (مثال: https://github.com/user/BarPro-main.git): " repo_url
    read -r -p "  GitHub username: " gh_user
    read -r -s -p "  Personal Access Token: " gh_token; echo

    git config --global credential.helper store
    echo "https://$gh_user:$gh_token@github.com" > ~/.git-credentials
    git init; git remote add origin "$repo_url"
    git fetch origin
    git checkout -b main origin/main 2>/dev/null || git checkout -b master origin/master
    ok "✅ Git راه‌اندازی شد — از این پس: bash manage.sh deploy"
}

cmd_pull() {
    hdr "📥  دریافت از GitHub"
    [ -d "$DIR/.git" ] || { warn "Git تنظیم نشده. اجرا کنید: bash manage.sh git-setup"; return 1; }
    git stash --include-untracked 2>/dev/null || true
    local before; before=$(git rev-parse HEAD)
    git pull origin main 2>&1 || git pull origin master 2>&1
    git stash pop 2>/dev/null || true
    local after; after=$(git rev-parse HEAD)
    if [ "$before" = "$after" ]; then ok "سرور به‌روز است"; return 1; fi
    git log --oneline "$before..$after" | head -5
    return 0
}

cmd_deploy() {
    hdr "🚀  Deploy هوشمند از GitHub"
    cmd_pull || return 0  # اگر تغییری نبود، خارج شو

    local web_ch api_ch
    web_ch=$(git diff --name-only HEAD~1 HEAD -- apps/web/ 2>/dev/null | wc -l)
    api_ch=$(git diff --name-only HEAD~1 HEAD -- app/ Dockerfile requirements.txt 2>/dev/null | wc -l)

    if   [ "$web_ch" -gt 0 ] && [ "$api_ch" -gt 0 ]; then cmd_update_all
    elif [ "$web_ch" -gt 0 ]; then cmd_update_ui
    elif [ "$api_ch" -gt 0 ]; then cmd_update_api
    else $DC restart; ok "کانفیگ آپدیت شد"
    fi
}

# ── بکاپ ─────────────────────────────────────────────────────────────────

cmd_backup_db() {
    hdr "💾  بکاپ دیتابیس"
    local f="$DIR/output/backups/backup_$(date +%Y%m%d_%H%M%S).sql.gz"
    mkdir -p "$DIR/output/backups"
    $DC exec -T postgres pg_dump -U postgres utcms_rpa | gzip > "$f"
    ok "بکاپ: $f  ($(du -sh "$f" | cut -f1))"
}

cmd_restore_db() {
    local file="${1:-}"; [ -n "$file" ] || err "مسیر فایل بکاپ را وارد کنید"
    [ -f "$file" ] || err "فایل پیدا نشد: $file"
    warn "دیتابیس فعلی جایگزین می‌شود!"
    read -r -p "  ادامه؟ [y/N] " c; [[ "$c" =~ ^[Yy]$ ]] || return
    gunzip -c "$file" | $DC exec -T postgres psql -U postgres utcms_rpa
    ok "✅ دیتابیس بازیابی شد"
}

# ── Main ──────────────────────────────────────────────────────────────────

case "${1:-help}" in
    status)      cmd_status ;;
    health)      cmd_health ;;
    logs)        cmd_logs "${2:-}" ;;
    ip-status)   cmd_ip_status ;;
    update-ui)   cmd_update_ui ;;
    update-api)  cmd_update_api ;;
    update-all)  cmd_update_all ;;
    git-setup)   cmd_git_setup ;;
    pull)        cmd_pull ;;
    deploy)      cmd_deploy ;;
    backup-db)   cmd_backup_db ;;
    restore-db)  cmd_restore_db "${2:-}" ;;
    migrate)     $DC exec -T backend alembic upgrade head && ok "مایگریشن انجام شد" ;;
    restart)     $DC restart "${2:-}" && ok "ری‌استارت انجام شد" ;;
    stop)        $DC stop && ok "متوقف شد (داده‌ها حفظ‌اند)" ;;
    start)       $DC up -d && ok "شروع شد" ;;
    *)
        echo -e "${BD}${BL}"
        cat << 'HELP'
╔══════════════════════════════════════════════════════════════╗
║             BarPro Server Manager  🛠️                        ║
╠══════════════════════════════════════════════════════════════╣
║  status         — وضعیت سرویس‌ها + منابع                    ║
║  health         — بررسی سلامت همه سرویس‌ها                  ║
║  logs [svc]     — مشاهده لاگ (nginx/backend/frontend/...)    ║
║  ip-status      — وضعیت هر دو IP                            ║
╠══════════════════════════════════════════════════════════════╣
║  update-ui      — ⚡ آپدیت فرانت‌اند (سریع، بدون rebuild)   ║
║  update-api     — آپدیت بک‌اند + مایگریشن                   ║
║  update-all     — آپدیت کامل (داده حفظ می‌شود)              ║
╠══════════════════════════════════════════════════════════════╣
║  git-setup      — اتصال سرور به GitHub                       ║
║  pull           — دریافت آخرین کد از GitHub                  ║
║  deploy         — 🚀 pull + rebuild هوشمند                   ║
╠══════════════════════════════════════════════════════════════╣
║  backup-db      — بکاپ دیتابیس                              ║
║  restore-db <f> — بازیابی دیتابیس                           ║
║  migrate        — اجرای مایگریشن Alembic                     ║
║  restart [svc]  — ری‌استارت (بدون rebuild)                   ║
║  stop / start   — توقف / شروع                               ║
╚══════════════════════════════════════════════════════════════╝
HELP
        echo -e "${RS}" ;;
esac

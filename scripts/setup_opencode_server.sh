#!/usr/bin/env bash
# ═══════════════════════════════════════════════════════════════════════════════
#  setup_opencode_server.sh — راه‌اندازی و پیکربندی خودکار سرور OpenCode برای BarPro
#
#  این اسکریپت روی سرور مرکزی (Central Server) اجرا می‌شود و:
#    1. ابزار OpenCode CLI را در صورت نیاز نصب می‌کند.
#    2. رمز عبور امن برای اتصال ایجاد یا دریافت می‌کند.
#    3. سرویس ماندگار systemd با نام opencode.service می‌سازد.
#    4. پورت 4096 را در فایروال UFW باز می‌کند.
#    5. اطلاعات کامل و کپی‌پذیر برای ورود به OpenCode را چاپ می‌کند.
#
#  نحوه اجرا روی سرور:
#    sudo bash scripts/setup_opencode_server.sh [رمز_عبور_دلخواه]
# ═══════════════════════════════════════════════════════════════════════════════

set -euo pipefail

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
NC='\033[0m' # No Color

log_info()    { echo -e "${BLUE}ℹ️  $*${NC}"; }
log_ok()      { echo -e "${GREEN}✅ $*${NC}"; }
log_warn()    { echo -e "${YELLOW}⚠️  $*${NC}"; }
log_error()   { echo -e "${RED}❌ $*${NC}"; }
log_section() { echo -e "\n${CYAN}══════════════════════════════════════════════════════════════${NC}"; echo -e "${CYAN}  $*${NC}"; echo -e "${CYAN}══════════════════════════════════════════════════════════════${NC}"; }

# تشخیص مسیر پروژه
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"

# اگر مسیر پروژه تشخیص داده نشد، پیش‌فرض /opt/barpro
if [ ! -f "$PROJECT_DIR/manage.sh" ]; then
    if [ -d "/opt/barpro" ]; then
        PROJECT_DIR="/opt/barpro"
    fi
fi

log_section "🚀 راه‌اندازی سرور OpenCode برای پروژه BarPro"
echo "  مسیر پروژه: $PROJECT_DIR"

# بررسی دسترسی روت
if [ "$(id -u)" -ne 0 ]; then
    log_error "این اسکریپت باید با دسترسی sudo یا کاربر root اجرا شود."
    exit 1
fi

# ── مرحله ۱: نصب OpenCode ───────────────────────────────────────────────────
log_section "📦 مرحله ۱: بررسی و نصب OpenCode"

OPENCODE_BIN=""
if command -v opencode >/dev/null 2>&1; then
    OPENCODE_BIN="$(command -v opencode)"
    log_ok "OpenCode از قبل نصب شده است: $OPENCODE_BIN"
elif [ -f "/root/.local/bin/opencode" ]; then
    OPENCODE_BIN="/root/.local/bin/opencode"
    log_ok "OpenCode در مسیر کاربر روت یافت شد: $OPENCODE_BIN"
elif [ -f "/usr/local/bin/opencode" ]; then
    OPENCODE_BIN="/usr/local/bin/opencode"
    log_ok "OpenCode در /usr/local/bin یافت شد: $OPENCODE_BIN"
else
    log_info "در حال نصب OpenCode از طریق اسکریپت رسمی..."
    curl -fsSL https://opencode.ai/install | bash || {
        log_warn "اسکریپت curl با خطا مواجه شد؛ تلاش برای نصب از طریق npm..."
        if command -v npm >/dev/null 2>&1; then
            npm install -g opencode-ai
        else
            log_error "امکان نصب خودکار OpenCode وجود ندارد. لطفاً ابتدا Node.js یا curl را بررسی کنید."
            exit 1
        fi
    }

    if [ -f "/root/.local/bin/opencode" ]; then
        OPENCODE_BIN="/root/.local/bin/opencode"
    elif command -v opencode >/dev/null 2>&1; then
        OPENCODE_BIN="$(command -v opencode)"
    elif [ -f "/usr/local/bin/opencode" ]; then
        OPENCODE_BIN="/usr/local/bin/opencode"
    fi
fi

if [ -z "$OPENCODE_BIN" ] || [ ! -x "$OPENCODE_BIN" ]; then
    log_error "فایل اجرایی OpenCode پیدا نشد."
    exit 1
fi

log_ok "فایل اجرایی OpenCode: $OPENCODE_BIN"

# ── مرحله ۲: تنظیم رمز عبور ─────────────────────────────────────────────────
log_section "🔑 مرحله ۲: تعیین رمز عبور امن"

SERVER_PASSWORD="${1:-}"
if [ -z "$SERVER_PASSWORD" ]; then
    if [ -n "${OPENCODE_SERVER_PASSWORD:-}" ]; then
        SERVER_PASSWORD="$OPENCODE_SERVER_PASSWORD"
    else
        # تولید رمز عبور تصادفی قوی
        SERVER_PASSWORD=$(openssl rand -hex 12 2>/dev/null || tr -dc A-Za-z0-9 </dev/urandom | head -c 20)
    fi
fi

SERVER_USERNAME="${OPENCODE_SERVER_USERNAME:-opencode}"
SERVER_PORT=4096

log_ok "نام کاربری: $SERVER_USERNAME"
log_ok "رمز عبور تنظیم شد."

# ── مرحله ۳: ایجاد سرویس systemd ───────────────────────────────────────────
log_section "⚙️  مرحله ۳: ساخت سرویس Systemd (opencode.service)"

SERVICE_FILE="/etc/systemd/system/opencode.service"

cat <<SERVICE_EOF > "$SERVICE_FILE"
[Unit]
Description=OpenCode Remote Server for BarPro
After=network.target

[Service]
Type=simple
User=root
WorkingDirectory=$PROJECT_DIR
Environment="OPENCODE_SERVER_USERNAME=$SERVER_USERNAME"
Environment="OPENCODE_SERVER_PASSWORD=$SERVER_PASSWORD"
ExecStart=$OPENCODE_BIN serve --port $SERVER_PORT --hostname 0.0.0.0
Restart=always
RestartSec=5
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
SERVICE_EOF

log_ok "فایل سرویس در $SERVICE_FILE ایجاد شد."

systemctl daemon-reload
systemctl enable opencode.service
systemctl restart opencode.service
sleep 2

if systemctl is-active --quiet opencode.service; then
    log_ok "سرویس opencode با موفقیت راه‌اندازی شد و در حال اجراست."
else
    log_error "سرویس opencode فعال نشد. لاگ‌ها:"
    journalctl -u opencode.service -n 20 --no-pager
    exit 1
fi

# ── مرحله ۴: باز کردن پورت فایروال ──────────────────────────────────────────
log_section "🛡️ مرحله ۴: تنظیم فایروال UFW"

if command -v ufw >/dev/null 2>&1; then
    if ufw status | grep -q "Status: active"; then
        ufw allow $SERVER_PORT/tcp comment 'OpenCode Server' >/dev/null || true
        log_ok "پورت $SERVER_PORT/tcp در UFW باز شد."
    else
        log_info "UFW غیرفعال است؛ نیازی به تغییر نیست."
    fi
fi

# ── مرحله ۵: دریافت IP عمومی و چاپ اطلاعات اتصال ─────────────────────────────
log_section "📋 مرحله ۵: اطلاعات اتصال به OpenCode"

# NOTE: never hardcode the production IP here (repo hygiene rule) — resolve it
# live; if both services fail, print a placeholder and let the operator fill in.
SERVER_IP="$(curl -s4 https://api.ipify.org 2>/dev/null || curl -s4 https://ifconfig.me 2>/dev/null || echo "<SERVER_PUBLIC_IP>")"

echo ""
echo -e "${GREEN}==============================================================${NC}"
echo -e "${GREEN}  🎉 سرور OpenCode با موفقیت روی سرور مرکزی بارپرو راه‌اندازی شد!${NC}"
echo -e "${GREEN}==============================================================${NC}"
echo ""
echo -e "این مشخصات را در پنجره ${YELLOW}Add Server${NC} در نرم‌افزار OpenCode وارد کنید:"
echo ""
echo -e "  📌 ${CYAN}Server address:${NC}         http://${SERVER_IP}:${SERVER_PORT}"
echo -e "  📌 ${CYAN}Server name (optional):${NC} BarPro-Central"
echo -e "  📌 ${CYAN}Username (optional):${NC}    ${SERVER_USERNAME}"
echo -e "  📌 ${CYAN}Password (optional):${NC}    ${SERVER_PASSWORD}"
echo ""
echo -e "${GREEN}==============================================================${NC}"
echo -e "💡 مدیریت سرویس روی سرور:"
echo -e "   مشاهده وضعیت:  sudo systemctl status opencode"
echo -e "   مشاهده لاگ‌ها:   sudo journalctl -u opencode -f"
echo -e "   ری‌استارت:     sudo systemctl restart opencode"
echo -e "   توقف سرویس:    sudo systemctl stop opencode"
echo -e "${GREEN}==============================================================${NC}"
echo ""

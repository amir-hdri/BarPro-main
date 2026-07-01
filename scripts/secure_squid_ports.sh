#!/usr/bin/env bash
# ═══════════════════════════════════════════════════════════════════════════════
#  secure_squid_ports.sh — مسدودسازی پورت‌های Squid از دسترسی خارجی
#
#  مشکل: Squid 2 (3129) و Squid 3 (3130) از IP ثانویه (95.38.233.90)
#  خارج سرویس می‌دهند و باید فقط از لوکال‌هاست و شبکه Docker قابل دسترسی باشند.
#  از آنجا که `network_mode: host` برای مسیریابی dual-IP لازم است،
#  از iptables برای محدود کردن دسترسی استفاده می‌کنیم.
#
#  استفاده:
#    sudo bash scripts/secure_squid_ports.sh
#
#  بررسی:
#    sudo iptables -L INPUT -n | grep "dpt:312"
# ═══════════════════════════════════════════════════════════════════════════════

set -euo pipefail

RULES_APPLIED=0
# Detect Docker bridge subnet automatically
DOCKER_BRIDGE=$(docker network inspect bridge --format '{{range .IPAM.Config}}{{.Subnet}}{{end}}' 2>/dev/null || echo "172.17.0.0/16")

log_info()  { echo -e "\033[1;34mℹ️  $*\033[0m"; }
log_ok()    { echo -e "\033[1;32m✅  $*\033[0m"; }
log_warn()  { echo -e "\033[1;33m⚠️  $*\033[0m"; }
log_error() { echo -e "\033[1;31m❌  $*\033[0m"; }

# بررسی دسترسی root
if [[ $EUID -ne 0 ]]; then
  log_error "این اسکریپت نیاز به دسترسی root دارد. با sudo اجرا کنید."
  exit 1
fi

# بررسی وجود iptables
if ! command -v iptables &>/dev/null; then
  log_error "iptables نصب نیست."
  exit 1
fi

log_section() {
  echo -e "\n\033[1;36m── $* ──────────────────────────────────────────\033[0m"
}

log_section "🔒 مسدودسازی پورت‌های Squid از دسترسی خارجی"

_apply_squid_rule() {
  local port=$1
  if iptables -C INPUT -p tcp --dport "$port" -j DROP 2>/dev/null; then
    log_info "قانون $port قبلاً اعمال شده است."
    return
  fi
  # Accept from localhost
  iptables -A INPUT -p tcp --dport "$port" -s 127.0.0.1 -j ACCEPT 2>/dev/null || true
  # Accept from Docker bridge
  iptables -A INPUT -p tcp --dport "$port" -s "$DOCKER_BRIDGE" -j ACCEPT 2>/dev/null || true
  # Drop everything else
  iptables -A INPUT -p tcp --dport "$port" -j DROP
  log_ok "پورت $port: فقط localhost + Docker bridge مجاز شد."
  RULES_APPLIED=$((RULES_APPLIED + 1))
}

_apply_squid_rule 3128
_apply_squid_rule 3129
_apply_squid_rule 3130

log_section "📋 خلاصه"
if [[ $RULES_APPLIED -gt 0 ]]; then
  log_ok "$RULES_APPLIED قانون iptables اعمال شد."
else
  log_info "همه قوانین قبلاً اعمال شده‌اند."
fi

echo ""
echo -e "\033[1mقوانین فعلی:\033[0m"
iptables -L INPUT -n | grep "dpt:312" || echo "(هیچ قانونی برای پورت‌های 312x یافت نشد)"

echo ""
log_warn "توجه: قوانین iptables پس از ری‌استارت سرور از بین می‌روند."
log_info "برای ماندگاری، بسته به سیستم‌عامل یکی از دستورات زیر را اجرا کنید:"
echo "  Ubuntu/Debian: sudo apt install iptables-persistent && sudo netfilter-persistent save"
echo "  CentOS/RHEL:   sudo service iptables save"
echo "  Alpine:        sudo rc-update add iptables"

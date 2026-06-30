#!/usr/bin/env bash
# ═══════════════════════════════════════════════════════════════════════════════
#  secure_squid_ports.sh — مسدودسازی پورت‌های Squid از دسترسی خارجی
#
#  مشکل: Squid 2 (3129) و Squid 3 (3130) از IP ثانویه (95.38.233.90)
# 向外 سرویس می‌دهند و باید فقط از لوکال‌هاست قابل دسترسی باشند.
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

# Squid 2 (3129) — فقط localhost
if iptables -C INPUT -p tcp --dport 3129 ! -s 127.0.0.1 -j DROP 2>/dev/null; then
  log_info "قانون 3129 قبلاً اعمال شده است."
else
  iptables -A INPUT -p tcp --dport 3129 ! -s 127.0.0.1 -j DROP
  log_ok "پورت 3129: فقط localhost مجاز شد."
  RULES_APPLIED=$((RULES_APPLIED + 1))
fi

# Squid 3 (3130) — فقط localhost
if iptables -C INPUT -p tcp --dport 3130 ! -s 127.0.0.1 -j DROP 2>/dev/null; then
  log_info "قانون 3130 قبلاً اعمال شده است."
else
  iptables -A INPUT -p tcp --dport 3130 ! -s 127.0.0.1 -j DROP
  log_ok "پورت 3130: فقط localhost مجاز شد."
  RULES_APPLIED=$((RULES_APPLIED + 1))
fi

# Squid 1 (3128) — اگر در معرض اینترنت است، محدود کنید
# (فقط در صورتی که Worker 1 نیاز به دسترسی خارجی ندارد)
# iptables -A INPUT -p tcp --dport 3128 ! -s 127.0.0.1 -j DROP

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

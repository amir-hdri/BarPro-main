#!/usr/bin/env bash
# ═══════════════════════════════════════════════════════════════════════════════
#  secure_squid_ports.sh — Restrict Squid ports to localhost + Docker networks
#
#  Squid proxies must never be reachable from the public internet:
#    - Squid 1 (3128) is used by Worker 1 from the barpro_platform bridge
#      (NOT the default bridge — the platform subnet may be 172.20.x, so this
#      script enumerates EVERY Docker network subnet automatically).
#    - Squid 2/3 (3129/3130) are Model A only and likewise internal-only.
#
#  Traffic from containers to a host-published port terminates on the host,
#  so the INPUT chain governs it (no DOCKER-USER involvement here).
#
#  Usage:
#    sudo bash scripts/secure_squid_ports.sh
#
#  Verify:
#    sudo iptables -L INPUT -n --line-numbers | grep "dpt:312"
#    nc -vz <CENTRAL_IP> 3128   # from outside — must FAIL
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

# ── Enumerate ALL Docker network subnets (default bridge + named bridges) ────
# Worker 1 reaches Squid 1 through barpro_platform (e.g. 172.20.0.0/16), so
# allowlisting ONLY the default bridge (172.17) silently cuts worker egress.
DOCKER_SUBNETS=""
if command -v docker &>/dev/null; then
  DOCKER_SUBNETS=$(docker network ls --format '{{.Name}}' 2>/dev/null | while read -r net; do
    docker network inspect "$net" --format '{{range .IPAM.Config}}{{.Subnet}}{{end}}' 2>/dev/null
  done | grep -E '^[0-9]+\.[0-9]+\.[0-9]+\.[0-9]+/[0-9]+$' | sort -u || true)
fi
if [[ -z "$DOCKER_SUBNETS" ]]; then
  # Fallback when docker CLI/networks are unavailable: cover the RFC1918
  # ranges Docker actually assigns (bridge defaults + custom pools).
  log_warn "دکر در دسترس نیست؛ از محدوده‌های پیش‌فرض 172.16.0.0/12 استفاده می‌شود."
  DOCKER_SUBNETS="172.16.0.0/12"
fi

log_section() {
  echo -e "\n\033[1;36m── $* ──────────────────────────────────────────\033[0m"
}

log_section "🔒 مسدودسازی پورت‌های Squid از دسترسی خارجی"
log_info "زیرشبکه‌های Docker مجاز: $DOCKER_SUBNETS"

_apply_squid_rule() {
  local port=$1
  if iptables -C INPUT -p tcp --dport "$port" -j DROP 2>/dev/null; then
    log_info "قانون DROP پورت $port قبلاً اعمال شده است."
  else
    # Accept rules first (appended before the DROP below)
    iptables -I INPUT 1 -p tcp --dport "$port" -s 127.0.0.1 -j ACCEPT 2>/dev/null || true
    while read -r subnet; do
      [[ -z "$subnet" ]] && continue
      # Replace an older narrow rule for the same port+subnet if present
      iptables -D INPUT -p tcp --dport "$port" -s "$subnet" -j ACCEPT 2>/dev/null || true
      iptables -I INPUT 1 -p tcp --dport "$port" -s "$subnet" -j ACCEPT
    done <<< "$DOCKER_SUBNETS"
    # Drop everything else — appended AFTER the accepts inserted above
    iptables -A INPUT -p tcp --dport "$port" -j DROP
    RULES_APPLIED=$((RULES_APPLIED + 1))
    local subnets_display
    subnets_display=$(echo "$DOCKER_SUBNETS" | tr '\n' ',' | sed 's/,$//')
    log_ok "پورت $port: فقط localhost + [$subnets_display] مجاز شد."
  fi
  # Ensure every docker subnet is accepted even if the DROP already existed
  while read -r subnet; do
    [[ -z "$subnet" ]] && continue
    if ! iptables -C INPUT -p tcp --dport "$port" -s "$subnet" -j ACCEPT 2>/dev/null; then
      iptables -I INPUT 1 -p tcp --dport "$port" -s "$subnet" -j ACCEPT
      log_ok "پورت $port: زیرشبکه $subnet اضافه شد (قبلاً جا مانده بود)."
    fi
  done <<< "$DOCKER_SUBNETS"
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
echo ""
log_warn "تأیید نهایی: از یک IP خارجی اجرا کنید →  nc -vz <CENTRAL_IP> 3128   (باید fail شود)"

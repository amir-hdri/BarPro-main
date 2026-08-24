#!/usr/bin/env bash
# =============================================================================
# setup_firewall_central.sh — Firewall rules for BarPro Central Server
# =============================================================================
# Run this on the CENTRAL server after adding Worker IPs.
#
# Usage:
#   sudo bash scripts/setup_firewall_central.sh
#
# Environment variables (read from .env or export before running):
#   WORKER_IPS  — space-separated list of Worker server IPs
#                 e.g. export WORKER_IPS="185.x.x.1 185.x.x.2"
#
# What this script does:
#   1. UFW: allows PostgreSQL (5432) and Redis (6379) ONLY from known Worker IPs
#   2. DOCKER-USER (iptables): the AUTHORITATIVE layer for Docker-published
#      ports. UFW alone CANNOT block Docker-published ports because that
#      traffic traverses the FORWARD/DOCKER chains, which bypass UFW's INPUT
#      chain entirely (verified live: Postgres/Redis were reachable from a
#      foreign network while `ufw deny 5432/6379` was active).
#   3. Keeps port 80 (Nginx) and 22 (SSH) open
#   4. Idempotent: safe to run multiple times (rules are comment-managed)
#
# Verification after running (from a NON-worker external IP):
#   nc -vz <CENTRAL_IP> 5432   # must FAIL (timeout/refused)
#   nc -vz <CENTRAL_IP> 6379   # must FAIL
# =============================================================================

set -euo pipefail

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

log_info()  { echo -e "${GREEN}[INFO]${NC}  $*"; }
log_warn()  { echo -e "${YELLOW}[WARN]${NC}  $*"; }
log_error() { echo -e "${RED}[ERROR]${NC} $*"; }

GUARD_COMMENT="barpro-guard"

# ── Load WORKER_IPS from .env if not already set ────────────────────────────
if [[ -z "${WORKER_IPS:-}" ]]; then
    ENV_FILE="$(dirname "$0")/../.env"
    if [[ -f "$ENV_FILE" ]]; then
        # shellcheck disable=SC1090
        WORKER_IPS=$(grep -E '^WORKER_IPS=' "$ENV_FILE" | cut -d= -f2- | tr -d '"' || true)
    fi
fi

if [[ -z "${WORKER_IPS:-}" ]]; then
    log_error "WORKER_IPS is not set. Example:"
    log_error "  export WORKER_IPS=\"185.x.x.1 185.x.x.2\""
    log_error "  sudo bash scripts/setup_firewall_central.sh"
    exit 1
fi

# ═════════════════════════════════════════════════════════════════════════════
# Layer 1 — DOCKER-USER (authoritative for Docker-published ports)
# ═════════════════════════════════════════════════════════════════════════════
log_info "Configuring DOCKER-USER chain (Docker-published ports)..."

if ! command -v iptables &>/dev/null; then
    log_error "iptables is not installed. Run: apt-get install -y iptables"
    exit 1
fi

# Ensure the DOCKER-USER chain exists (Docker creates it; recreate if missing)
if ! iptables -L DOCKER-USER >/dev/null 2>&1; then
    iptables -N DOCKER-USER
    log_warn "DOCKER-USER chain was missing — created it (is Docker running?)"
fi

# Remove previous barpro-guard rules so this script is idempotent and never
# accumulates stale Worker IP entries.
while iptables -S DOCKER-USER | grep -q "$GUARD_COMMENT"; do
    RULE_TO_DELETE=$(iptables -S DOCKER-USER | grep "$GUARD_COMMENT" | head -n1 | sed 's/^-A //')
    # shellcheck disable=SC2086
    iptables -D DOCKER-USER $RULE_TO_DELETE 2>/dev/null || break
done

# Insert order matters: we insert at position 1 repeatedly, so build in
# REVERSE — final top-down order becomes:
#   1. ACCEPT worker_ip → 5432 / 6379   (per worker, inserted last = on top)
#   2. DROP everyone else → 5432 / 6379
# Docker's implicit RETURN at the end of DOCKER-USER stays untouched.
iptables -I DOCKER-USER 1 -p tcp --dport 5432 -m comment --comment "$GUARD_COMMENT" -j DROP
iptables -I DOCKER-USER 1 -p tcp --dport 6379 -m comment --comment "$GUARD_COMMENT" -j DROP

for WORKER_IP in $WORKER_IPS; do
    if ! echo "$WORKER_IP" | grep -qE '^([0-9]{1,3}\.){3}[0-9]{1,3}$'; then
        log_error "Invalid IP '$WORKER_IP' in WORKER_IPS — skipping."
        continue
    fi
    iptables -I DOCKER-USER 1 -s "$WORKER_IP" -p tcp --dport 5432 -m comment --comment "$GUARD_COMMENT" -j ACCEPT
    iptables -I DOCKER-USER 1 -s "$WORKER_IP" -p tcp --dport 6379 -m comment --comment "$GUARD_COMMENT" -j ACCEPT
    log_info "  DOCKER-USER allow: $WORKER_IP → 5432/6379"
done

log_ok_docker() { echo -e "${GREEN}[INFO]${NC}  DOCKER-USER guard installed (Postgres/Redis reachable only from: ${WORKER_IPS})"; }
log_ok_docker

log_warn "Persisting DOCKER-USER rules across reboots:"
log_warn "  Ubuntu/Debian: apt-get install -y iptables-persistent && netfilter-persistent save"
log_warn "  NOTE: Docker recreates DOCKER-USER on restart; re-run this script after docker restart if persistence is not installed."

# ═════════════════════════════════════════════════════════════════════════════
# Layer 2 — UFW (host INPUT chain; SSH/HTTP + defense-in-depth)
# ═════════════════════════════════════════════════════════════════════════════
log_info "Installing/enabling UFW..."
if ! command -v ufw &>/dev/null; then
    apt-get install -y ufw
fi

# ── Default policy ───────────────────────────────────────────────────────────
log_info "Setting default policies..."
ufw default deny incoming
ufw default allow outgoing

# ── Allow SSH (keep this FIRST to avoid lockout) ────────────────────────────
log_info "Allowing SSH (port 22)..."
ufw allow 22/tcp comment 'SSH'

# ── Allow HTTP (Nginx) ───────────────────────────────────────────────────────
log_info "Allowing HTTP (port 80)..."
ufw allow 80/tcp comment 'Nginx HTTP'

# ── PostgreSQL and Redis: allow ONLY from Worker IPs ────────────────────────
# NOTE: these UFW rules are defense-in-depth only. The authoritative block
# for Docker-published ports is DOCKER-USER above.
log_info "Configuring Worker IP allowlist for PostgreSQL + Redis (UFW layer)..."
for WORKER_IP in $WORKER_IPS; do
    ufw allow from "$WORKER_IP" to any port 5432 comment "PostgreSQL - $WORKER_IP" >/dev/null || true
    ufw allow from "$WORKER_IP" to any port 6379 comment "Redis - $WORKER_IP" >/dev/null || true
done

# ── Block public access to PostgreSQL and Redis (host INPUT path) ───────────
ufw deny 5432/tcp comment 'Block public PostgreSQL' >/dev/null || true
ufw deny 6379/tcp comment 'Block public Redis' >/dev/null || true

# ── Squid proxy ports (3128, 3129, 3130) — no public exposure ───────────────
ufw deny 3128/tcp comment 'Block public Squid-1' >/dev/null || true
ufw deny 3129/tcp comment 'Block public Squid-2' >/dev/null || true
ufw deny 3130/tcp comment 'Block public Squid-3' >/dev/null || true

# ── Enable UFW ───────────────────────────────────────────────────────────────
log_info "Enabling UFW..."
ufw --force enable

log_info "UFW status:"
ufw status numbered

echo ""
log_info "✅ Firewall configured successfully (DOCKER-USER + UFW)."
log_info "   PostgreSQL/Redis now reachable ONLY from: ${WORKER_IPS}"
echo ""
log_warn "⚠️  MANDATORY VERIFICATION — from an EXTERNAL non-worker IP run:"
log_warn "     nc -vz <CENTRAL_IP> 5432   # must fail"
log_warn "     nc -vz <CENTRAL_IP> 6379   # must fail"
echo ""
log_warn "To add a new Worker IP later, run:"
log_warn "  sudo bash scripts/add_worker_firewall.sh <NEW_WORKER_IP> <WORKER_ID>"

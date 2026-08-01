#!/usr/bin/env bash
# =============================================================================
# setup_firewall_central.sh — UFW rules for BarPro Central Server
# =============================================================================
# Run this on the CENTRAL server after adding Worker IPs.
#
# Usage:
#   sudo bash scripts/setup_firewall_central.sh
#
# Environment variables (read from .env or export before running):
#   WORKER_IPS  — space-separated list of Worker server IPs
#                 e.g. export WORKER_IPS="185.x.x.1 185.x.x.2 185.x.x.3"
#
# What this script does:
#   1. Allows PostgreSQL (5432) and Redis (6379) ONLY from known Worker IPs
#   2. Blocks those ports from all other sources
#   3. Keeps port 80 (Nginx) open for all
#   4. Idempotent: safe to run multiple times
# =============================================================================

set -euo pipefail

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

log_info()  { echo -e "${GREEN}[INFO]${NC}  $*"; }
log_warn()  { echo -e "${YELLOW}[WARN]${NC}  $*"; }
log_error() { echo -e "${RED}[ERROR]${NC} $*"; }

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

log_info "Installing/enabling UFW..."
if ! command -v ufw &>/dev/null; then
    apt-get install -y ufw
fi

# ── Default policy ───────────────────────────────────────────────────────────
log_info "Setting default policies..."
ufw --force reset  >/dev/null 2>&1 || true
ufw default deny incoming
ufw default allow outgoing

# ── Allow SSH (keep this FIRST to avoid lockout) ────────────────────────────
log_info "Allowing SSH (port 22)..."
ufw allow 22/tcp comment 'SSH'

# ── Allow HTTP (Nginx) ───────────────────────────────────────────────────────
log_info "Allowing HTTP (port 80)..."
ufw allow 80/tcp comment 'Nginx HTTP'

# ── PostgreSQL and Redis: allow ONLY from Worker IPs ────────────────────────
log_info "Configuring Worker IP allowlist for PostgreSQL + Redis..."
for WORKER_IP in $WORKER_IPS; do
    log_info "  Allowing Worker IP: $WORKER_IP"
    ufw allow from "$WORKER_IP" to any port 5432 comment "PostgreSQL - $WORKER_IP"
    ufw allow from "$WORKER_IP" to any port 6379 comment "Redis - $WORKER_IP"
done

# ── Block public access to PostgreSQL and Redis ──────────────────────────────
log_info "Blocking public access to PostgreSQL (5432) and Redis (6379)..."
ufw deny 5432/tcp comment 'Block public PostgreSQL'
ufw deny 6379/tcp comment 'Block public Redis'

# ── Squid proxy ports (3129, 3130) — localhost only ─────────────────────────
log_info "Blocking public Squid ports (3129, 3130)..."
ufw deny 3129/tcp comment 'Block public Squid-2'
ufw deny 3130/tcp comment 'Block public Squid-3'

# ── Enable UFW ───────────────────────────────────────────────────────────────
log_info "Enabling UFW..."
ufw --force enable

log_info "UFW status:"
ufw status numbered

echo ""
log_info "✅ Firewall configured successfully!"
log_info "   PostgreSQL and Redis are now accessible only from: ${WORKER_IPS}"
log_warn "   To add a new Worker IP later, run:"
log_warn "   sudo bash scripts/add_worker_firewall.sh <NEW_WORKER_IP> <WORKER_ID>"

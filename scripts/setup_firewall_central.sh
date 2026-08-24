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
#   WORKER_IPS  — space- or comma-separated list of Worker server IPs
#                 e.g. export WORKER_IPS="185.x.x.1 185.x.x.2"
#
# Design notes:
#   - IPv4-ONLY by project policy (no ip6tables rules are installed).
#   - Squid 1 runs with `network_mode: host` (compose/proxy.yml), so its port
#     3128 is a REAL host socket: container→172.20.0.1:3128 traverses the
#     INPUT chain, NOT FORWARD/DOCKER-USER. Therefore enabling UFW with
#     default-deny would silently cut Worker 1 / backend healthcheck egress —
#     this script auto-discovers every Docker subnet and allows them to 3128.
#   - Postgres/Redis are published per POSTGRES_BIND/REDIS_BIND (.env).
#     Model B requires 0.0.0.0 for remote workers → the DOCKER-USER layer
#     below is what actually keeps them private. With the repo default
#     127.0.0.1 (single-box Model A) they are never publicly exposed at all;
#     the guard stays harmless belt-and-braces.
#
# What this script does:
#   1. UFW: allows PostgreSQL (5432) and Redis (6379) ONLY from known Worker IPs
#   2. DOCKER-USER (iptables): the AUTHORITATIVE layer for Docker-published
#      ports. UFW alone CANNOT block Docker-published ports because that
#      traffic traverses the FORWARD/DOCKER chains, which bypass UFW's INPUT
#      chain entirely (verified live: Postgres/Redis were reachable from a
#      foreign network while `ufw deny 5432/6379` was active).
#   3. Keeps port 80 (Nginx) and rate-limited SSH open; keeps Docker-subnet
#      access to Squid-1 (3128) and host-gateway DB/Redis paths alive.
#   4. Idempotent: safe to run multiple times (rules are comment-managed)
#
# Verification after running (from a NON-worker external IP):
#   nc -vz <CENTRAL_IP> 5432   # must FAIL (timeout/refused)
#   nc -vz <CENTRAL_IP> 6379   # must FAIL
#   nc -vz <CENTRAL_IP> 3128   # must FAIL
# And from inside a container (must still SUCCEED):
#   docker exec barpro-worker-1 curl -sx http://172.20.0.1:3128 \
#     -o /dev/null -w '%{http_code}\n' https://utcms.ir --max-time 10
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
        WORKER_IPS=$(grep -E '^WORKER_IPS=' "$ENV_FILE" | cut -d= -f2- | tr -d '"' | tr ',' ' ' || true)
    fi
fi
# Normalize commas to spaces so "1.2.3.4,5.6.7.8" and "1.2.3.4 5.6.7.8" both work.
WORKER_IPS="${WORKER_IPS//,/ }"

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

# ── Rate-limited SSH (keep FIRST to avoid lockout; throttles brute-force) ───
log_info "Applying rate-limited SSH rule..."
ufw limit 22/tcp comment 'SSH rate-limited' >/dev/null || ufw allow 22/tcp comment 'SSH'

# ── Allow HTTP (Nginx) ───────────────────────────────────────────────────────
log_info "Allowing HTTP (port 80)..."
ufw allow 80/tcp comment 'Nginx HTTP'

# ════════════════════════════════════════════════════════════════════════════
# CRITICAL: keep INTERNAL container traffic alive once UFW goes default-deny.
#
# Squid 1 runs with network_mode: host (compose/proxy.yml) → port 3128 is a
# real host socket reached through the INPUT chain, NOT FORWARD/DOCKER-USER.
# Worker 1 and the backend healthcheck connect to it at the bridge gateway
# (e.g. http://172.20.0.1:3128). Without explicit allows below, enabling UFW
# here would DROP those packets and silently kill central RPA egress.
# ════════════════════════════════════════════════════════════════════════════
log_info "Discovering Docker network subnets (for internal INPUT allows)..."

discover_docker_subnets() {
    if command -v docker &>/dev/null; then
        docker network ls --format '{{.Name}}' 2>/dev/null | while read -r net; do
            docker network inspect "$net" --format '{{range .IPAM.Config}}{{.Subnet}}{{end}}' 2>/dev/null
        done | grep -E '^[0-9]+\.[0-9]+\.[0-9]+\.[0-9]+/[0-9]+$' | sort -u
    fi
}

DOCKER_SUBNETS="$(discover_docker_subnets)"
if [[ -z "$DOCKER_SUBNETS" ]]; then
    log_warn "docker CLI/networks unavailable — falling back to 172.16.0.0/12."
    DOCKER_SUBNETS="172.16.0.0/12"
fi
log_info "Internal Docker subnets: $(echo "$DOCKER_SUBNETS" | tr '\n' ' ')"

log_info "Allowing localhost + Docker subnets → Squid-1 (3128)..."
ufw allow from 127.0.0.1 to any port 3128 proto tcp comment 'Squid-1 loopback' >/dev/null || true
while read -r subnet; do
    [[ -z "$subnet" ]] && continue
    ufw allow from "$subnet" to any port 3128 proto tcp comment "Squid-1 from $subnet" >/dev/null || true
done <<< "$DOCKER_SUBNETS"

log_info "Allowing Docker subnets → host-gateway PostgreSQL/Redis (INPUT-path parity)..."
while read -r subnet; do
    [[ -z "$subnet" ]] && continue
    ufw allow from "$subnet" to any port 5432 proto tcp comment "PG host-gw $subnet" >/dev/null || true
    ufw allow from "$subnet" to any port 6379 proto tcp comment "Redis host-gw $subnet" >/dev/null || true
done <<< "$DOCKER_SUBNETS"

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
log_warn "     nc -vz <CENTRAL_IP> 3128   # must fail"
echo ""
log_warn "⚠️  AND verify the INTERNAL path still works (Worker-1 → Squid-1):"
log_warn "     docker exec barpro-worker-1 curl -sx http://172.20.0.1:3128 -o /dev/null \\"
log_warn "       -w '%{http_code}\\n' https://utcms.ir --max-time 10   # expect 200"
echo ""
log_warn "To add a new Worker IP later, run:"
log_warn "  sudo bash scripts/add_worker_firewall.sh <NEW_WORKER_IP> <WORKER_ID>"

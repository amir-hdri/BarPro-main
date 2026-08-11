#!/usr/bin/env bash
# ═══════════════════════════════════════════════════════════════════════════════
#  render_squid_configs.sh — Render central Squid templates to *.runtime.conf
# ═══════════════════════════════════════════════════════════════════════════════
#  The central Squid configs (infra/squid/squid_1/2/3.conf) carry a
#  commented-out egress line (`# tcp_outgoing_address __EGRESS_IP__`) as a safe
#  local-development default. Production deploys must enable it with the
#  server's real public IPs — but NEVER by sed -i'ing the tracked templates:
#  that dirties the git tree on the server and breaks the next `git pull`
#  (same class of bug as X4 on the worker side).
#
#  This script renders each template, idempotently and from the pristine
#  template, into infra/squid/squid_<N>.runtime.conf — the file that
#  compose/proxy.yml actually mounts.
#
#  Usage (run from anywhere in the repo):
#    bash scripts/render_squid_configs.sh                 # read IPs from .env
#    bash scripts/render_squid_configs.sh <PRIMARY_IP> <SECONDARY_IP>
#    bash scripts/render_squid_configs.sh --dev           # egress disabled
#
#  IP sources:
#    PRIMARY_IP   → squid_1 egress  (CENTRAL_IP in .env)
#    SECONDARY_IP → squid_2/3 egress (SECONDARY_EGRESS_IP in .env)
#  When no IP is available the egress line stays commented (default route),
#  which is the safe development default.
# ═══════════════════════════════════════════════════════════════════════════════

set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")/.."

PRIMARY_IP="${1:-}"
SECONDARY_IP="${2:-}"

if [ "$PRIMARY_IP" = "--dev" ]; then
    PRIMARY_IP=""
    SECONDARY_IP=""
elif [ -z "$PRIMARY_IP" ]; then
    # No CLI args — load the deploy-time values from .env (if present).
    # NOTE: never `source .env` here — bcrypt MASTER_ADMIN_PASSWORD ($2b$12$…)
    # expands under bash and aborts with "unbound variable" under set -u.
    # Only CENTRAL_IP / SECONDARY_EGRESS_IP are read, via plain grep.
    if [ -f .env ]; then
        while IFS='=' read -r k v; do
            v="${v%\"}"; v="${v#\"}"
            case "$k" in
                CENTRAL_IP) PRIMARY_IP="$v" ;;
                SECONDARY_EGRESS_IP) SECONDARY_IP="$v" ;;
            esac
        done < <(grep -E '^(CENTRAL_IP|SECONDARY_EGRESS_IP)=' .env)
    fi
fi

render() {
    local src="infra/squid/$1"
    local dst="infra/squid/$2"
    local egress="$3"

    if [ ! -f "$src" ]; then
        echo "WARN: $src not found — skipping" >&2
        return 0
    fi

    if [ -n "$egress" ]; then
        # Uncomment the egress line and bind it to the server's public IP.
        # Rendered from the pristine template, so re-running is idempotent.
        sed -E "s|^#[[:space:]]*tcp_outgoing_address __EGRESS_IP__|tcp_outgoing_address ${egress}|" "$src" > "$dst"
    else
        # Safe default: keep the line commented (egress via default route).
        cp "$src" "$dst"
    fi
    echo "rendered $dst (egress: ${egress:-disabled})"
}

render squid_1.conf squid_1.runtime.conf "$PRIMARY_IP"
render squid_2.conf squid_2.runtime.conf "$SECONDARY_IP"
render squid_3.conf squid_3.runtime.conf "$SECONDARY_IP"

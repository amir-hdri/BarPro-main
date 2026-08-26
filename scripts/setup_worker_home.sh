#!/usr/bin/env bash
# =============================================================================
# BarPro — Home/mobile-class Worker 4 bootstrap (run ON THE HOME BOX)
# =============================================================================
# Prereqs (done from Central first):
#   scripts/setup_wireguard_central.sh   -> produces /root/barpro-worker4/worker4.conf
#   scp that file to THIS box as /root/worker4.conf  (chmod 600)
#
# This script: installs Docker+WireGuard, brings up the tunnel (control-plane
# only), clones BarPro, renders .env for WORKER_IP_INDEX=4 with DB/Redis over
# the tunnel (10.8.0.1), and starts compose/worker-node.yml.
# UTCMS egress = this box's own home ISP line (NOT the tunnel).
# =============================================================================
set -euo pipefail

WG_CONF_SRC="${1:-/root/worker4.conf}"
APP_DIR="/opt/barpro"
REPO_URL="${REPO_URL:-https://github.com/amir-hdri/BarPro-main.git}"
CENTRAL_WG_IP="10.8.0.1"

[[ $EUID -eq 0 ]] || { echo "ERROR: run as root"; exit 1; }
[[ -f "$WG_CONF_SRC" ]] || { echo "ERROR: $WG_CONF_SRC missing — scp worker4.conf from Central first"; exit 1; }

echo "[1/6] packages + docker"
export DEBIAN_FRONTEND=noninteractive
apt-get update -qq
apt-get install -y -qq wireguard qrencode git curl >/dev/null
if ! command -v docker >/dev/null 2>&1; then
  curl -fsSL https://get.docker.com | sh >/dev/null
fi

echo "[2/6] WireGuard tunnel (control-plane only)"
install -m 600 "$WG_CONF_SRC" /etc/wireguard/wg0.conf
systemctl enable wg-quick@wg0 >/dev/null 2>&1 || true
wg-quick down wg0 >/dev/null 2>&1 || true
wg-quick up wg0
sleep 2
ping -c1 -W3 "$CENTRAL_WG_IP" >/dev/null || { echo "ERROR: no tunnel to ${CENTRAL_WG_IP}"; exit 1; }
echo "    tunnel OK (${CENTRAL_WG_IP} reachable) — egress IP for RPA stays: $(curl -s -m 8 http://api.ipify.org || echo '?')"

echo "[3/6] clone / update repo"
mkdir -p "$APP_DIR"
if [[ ! -d "$APP_DIR/.git" ]]; then
  git clone --depth 1 "$REPO_URL" "$APP_DIR"
fi
cd "$APP_DIR"
git pull --ff-only origin main

echo "[4/6] render .env (fetch fresh secrets from Central via scp by OPERATOR)"
if [[ ! -f .env ]]; then
  cat <<'NOTE'
ERROR: /opt/barpro/.env not found.
Operator must copy the real env from Central ONCE and adjust hosts:
  scp root@<central>:/opt/barpro/.env /opt/barpro/.env
Then re-run this script (it will rewrite hosts to the tunnel below).
NOTE
  exit 1
fi
# Deterministic rewrite: DB/Redis hosts -> tunnel IP; identity -> index 4.
sed -i -E \
  -e "s|@[^@\":]*:5432|@${CENTRAL_WG_IP}:5432|" \
  -e "s|@[^\"]*:6379|@${CENTRAL_WG_IP}:6379|" \
  -e "s|^WORKER_ID=.*|WORKER_ID=4|" \
  -e "s|^WORKER_IP_INDEX=.*|WORKER_IP_INDEX=4|" \
  -e "s|^ENVIRONMENT=.*|ENVIRONMENT=production|" \
  .env
grep -qE '^WORKER_ID=' .env || echo "WORKER_ID=4" >> .env
grep -qE '^WORKER_IP_INDEX=' .env || echo "WORKER_IP_INDEX=4" >> .env
echo "    DB/Redis hosts forced to ${CENTRAL_WG_IP}; identity set to index 4"

echo "[5/6] start worker stack"
docker compose -f compose/worker-node.yml up -d

echo "[6/6] verify"
sleep 20
docker ps --format '{{.Names}}\t{{.Status}}' | grep barpro || true
docker logs --tail 6 barpro-celery-worker 2>&1 | tail -6
cat <<'NEXT'

NEXT STEPS (on Central):
  1) confirm registry row:  SELECT * FROM worker_registry WHERE worker_id='4';
  2) widen routing fleet:   .env -> AVAILABLE_IP_INDICES="1,2,3,4"  (+ redeploy backend)
NEXT

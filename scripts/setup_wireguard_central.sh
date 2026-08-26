#!/usr/bin/env bash
# =============================================================================
# BarPro — WireGuard control-plane provisioner (run ON THE CENTRAL SERVER)
# =============================================================================
# Adds a WireGuard listener so a home/mobile-class "Worker 4" can reach
# Postgres/Redis over a stable private tunnel (10.8.0.0/24) WITHOUT pinning
# its dynamic home IP in UFW. RPA egress of that node stays on its own ISP.
#
# Idempotent: safe to re-run. Secrets stay on-box (chmod 600), never printed.
#
# After running: hand /root/barpro-worker4/worker4.conf to the home box
# (scp over SSH) and run scripts/setup_worker_home.sh there.
# =============================================================================
set -euo pipefail

WG_IFACE="wg0"
WG_SUBNET="10.8.0.0/24"
WG_PORT="51820"
CENTRAL_WG_IP="10.8.0.1"
WORKER4_WG_IP="10.8.0.2"
APP_DIR="/opt/barpro"

[[ $EUID -eq 0 ]] || { echo "ERROR: run as root"; exit 1; }

echo "[1/7] packages"
export DEBIAN_FRONTEND=noninteractive
apt-get update -qq
apt-get install -y -qq wireguard qrencode >/dev/null

echo "[2/7] keys (server + worker4 peer)"
mkdir -p /etc/wireguard /root/barpro-worker4
[[ -f /etc/wireguard/server.key ]] || wg genkey | tee /etc/wireguard/server.key | wg pubkey > /etc/wireguard/server.pub
chmod 600 /etc/wireguard/server.key
if [[ ! -f /root/barpro-worker4/worker4.key ]]; then
  wg genkey | tee /root/barpro-worker4/worker4.key | wg pubkey > /root/barpro-worker4/worker4.pub
fi
chmod 600 /root/barpro-worker4/worker4.key
SERVER_PUB=$(cat /etc/wireguard/server.pub)
WORKER4_PUB=$(cat /root/barpro-worker4/worker4.pub)

echo "[3/7] render ${APP_DIR}/infra/wireguard templates -> /etc/wireguard/${WG_IFACE}.conf"
sed -e "s|{{SERVER_PRIVATE_KEY}}|$(cat /etc/wireguard/server.key)|" \
    -e "s|{{WORKER4_PUBLIC_KEY}}|${WORKER4_PUB}|" \
    "${APP_DIR}/infra/wireguard/wg0-server.conf.template" > "/etc/wireguard/${WG_IFACE}.conf"
chmod 600 "/etc/wireguard/${WG_IFACE}.conf"

echo "[4/7] sysctl forwarding (wg0 -> docker nets only, no internet NAT)"
sysctl -qw net.ipv4.ip_forward=1
cat > /etc/sysctl.d/99-barpro-wg.conf <<EOF
net.ipv4.ip_forward = 1
EOF

echo "[5/7] bring up ${WG_IFACE}"
systemctl enable "wg-quick@${WG_IFACE}" >/dev/null 2>&1 || true
wg-quick down "$WG_IFACE" >/dev/null 2>&1 || true
wg-quick up "$WG_IFACE"

echo "[6/7] firewall — UFW + DOCKER-USER (comment-managed, idempotent)"
ufw allow "${WG_PORT}/udp" comment 'barpro-wg-control-plane' >/dev/null
for port in 5432 6379; do
  ufw allow from "$WG_SUBNET" to any port "$port" comment 'barpro-wg-dbredis' >/dev/null 2>&1 || true
done
# Forwarded traffic wg0 -> docker bridge must pass DOCKER-USER
while iptables -C DOCKER-USER -i "$WG_IFACE" -s "$WG_SUBNET" -j ACCEPT -m comment --comment barpro-wg 2>/dev/null; do
  iptables -D DOCKER-USER -i "$WG_IFACE" -s "$WG_SUBNET" -j ACCEPT -m comment --comment barpro-wg
done
iptables -I DOCKER-USER 1 -i "$WG_IFACE" -s "$WG_SUBNET" -j ACCEPT -m comment --comment barpro-wg
# Persist DOCKER-USER rule across restarts alongside existing barpro rules
CAT=/etc/iptables/barpro-wg.rules
mkdir -p /etc/iptables
iptables-save | grep barpro-wg > "$CAT" || true
cat > /etc/network/if-pre-up.d/barpro-wg-dockeruser <<'EOF'
#!/bin/sh
[ -f /etc/iptables/barpro-wg.rules ] && iptables-restore -n /etc/iptables/barpro-wg.rules || true
EOF
chmod +x /etc/network/if-pre-up.d/barpro-wg-dockeruser 2>/dev/null || true

echo "[7/7] render client config for the home box"
CENTRAL_IP=$(grep -E '^CENTRAL_IP=' "${APP_DIR}/.env" | cut -d'"' -f2 | cut -d"=" -f2- | tr -d '"' | head -1)
[[ -n "$CENTRAL_IP" ]] || { echo "ERROR: CENTRAL_IP not found in ${APP_DIR}/.env"; exit 1; }
sed -e "s|{{WORKER4_PRIVATE_KEY}}|$(cat /root/barpro-worker4/worker4.key)|" \
    -e "s|{{SERVER_PUBLIC_KEY}}|${SERVER_PUB}|" \
    -e "s|{{CENTRAL_IP}}|${CENTRAL_IP}|" \
    "${APP_DIR}/infra/wireguard/wg-worker4-client.conf.template" > /root/barpro-worker4/worker4.conf
chmod 600 /root/barpro-worker4/*

echo
echo "✅ WireGuard ready."
wg show "$WG_IFACE" | sed 's/private key:.*/private key: <hidden>/'
echo
echo "Next steps:"
echo "  1) scp root@<central>:/root/barpro-worker4/worker4.conf  <home-box>:/etc/wireguard/wg0.conf"
echo "  2) on the home box run:  bash ${APP_DIR}/scripts/setup_worker_home.sh"
echo "  3) after heartbeat appears, set AVAILABLE_IP_INDICES=1,2,3,4 in central .env and redeploy routing consumers"

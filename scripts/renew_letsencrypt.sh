#!/bin/bash
# ═══════════════════════════════════════════════════════════════════
#  renew_letsencrypt.sh — تمدید گواهی + انتشار در کانتینر nginx
#
#  چرا یک اسکریپت جدا لازم است: install_letsencrypt.sh گواهی را از
#  /etc/letsencrypt به infra/nginx/ssl/ *کپی* می‌کند (چون آن مسیر در
#  کانتینر مونت است). `certbot renew` به‌خودی‌خود فقط /etc/letsencrypt
#  را تازه می‌کند؛ بدون کپی مجدد، کانتینر تا ۶۰-۹۰ روز بعد با گواهی
#  منقضی سرو می‌دهد. این اسکریپت هر دو کار را با هم انجام می‌دهد.
#
#  استفاده در crontab (یک‌بار):
#    15 3 * * * /bin/bash /opt/barpro/scripts/renew_letsencrypt.sh your-domain.com >>/var/log/barpro-le-renew.log 2>&1
#  (مسیر repo را با محل واقعی checkout جایگزین کنید؛ اسکریپت خودش
#  BASE_DIR را از محل خودش تشخیص می‌دهد.)
# ═══════════════════════════════════════════════════════════════════

set -euo pipefail

DOMAIN="${1:-}"
BASE_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SSL_DIR="$BASE_DIR/infra/nginx/ssl"

log() { echo "[LE-RENEW $(date '+%F %T')] $*"; }
err() { echo "[LE-RENEW $(date '+%F %T')] [ERROR] $*" >&2; }

if [[ -z "$DOMAIN" ]]; then
  err "دامنه لازم است: renew_letsencrypt.sh your-domain.com"
  exit 1
fi

log "تمدید گواهی برای $DOMAIN ..."
certbot renew --cert-name "$DOMAIN" --quiet

log "انتشار گواهی تازه به $SSL_DIR ..."
CERT_DIR="/etc/letsencrypt/live/$DOMAIN"
cp "$CERT_DIR/fullchain.pem" "$SSL_DIR/fullchain.pem"
cp "$CERT_DIR/privkey.pem" "$SSL_DIR/privkey.pem"
cp "$CERT_DIR/chain.pem" "$SSL_DIR/chain.pem" 2>/dev/null || true
chmod 644 "$SSL_DIR/fullchain.pem"
chmod 600 "$SSL_DIR/privkey.pem"

if docker inspect barpro-nginx >/dev/null 2>&1; then
  docker exec barpro-nginx nginx -s reload
  log "nginx reload شد."
else
  err "کانتینر barpro-nginx در حال اجرا نیست — reload انجام نشد."
  exit 1
fi

code="$(curl -s -m 10 -o /dev/null -w '%{http_code}' "https://$DOMAIN/" || true)"
log "سلامت https://$DOMAIN → HTTP $code"

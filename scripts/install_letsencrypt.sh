#!/bin/bash
# ═══════════════════════════════════════════════════════════════════
#  install_letsencrypt.sh — نصب خودکار HTTPS برای BarPro (Let's Encrypt)
#
#  پیش‌نیازها:
#    1. یک دامنهٔ واقعی با A record → <CENTRAL_IP> (87.107.5.238)
#    2. پورت 80 از اینترنت قابل‌دسترسی باشد (HTTP-01 challenge)
#
#  نحوهٔ استفاده:
#    sudo bash scripts/install_letsencrypt.sh your-domain.com
#
#  چه کاری انجام می‌دهد:
#    1. نصب certbot + بسته‌های وابسته
#    2. صدور گواهی با webroot روی دایرکتوری nginx (بدون قطع سرویس)
#    3. کپی گواهی به infra/nginx/ssl/ (مونت‌شده در container nginx)
#    4. فعال‌سازی listen 443 + redirect HTTP→HTTPS در nginx.conf
#    5. مونت ssl volume و پورت 443 در compose/web.yml
#    6. rebuild نرم nginx + تأیید سلامت
#    7. راهنمای فعال‌سازی AUTH_COOKIE_SECURE=true
# ═══════════════════════════════════════════════════════════════════

set -euo pipefail

DOMAIN="${1:-}"
CENTRAL_IP="${CENTRAL_IP:-87.107.5.238}"
BASE_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
WEBROOT_DIR="/opt/barpro/acme-challenge"
SSL_DIR="$BASE_DIR/infra/nginx/ssl"
NGINX_CONF="$BASE_DIR/infra/nginx/nginx.conf"
WEB_YML="$BASE_DIR/compose/web.yml"

log() { echo -e "\033[1;34m[LE]\033[0m $*"; }
err() { echo -e "\033[1;31m[ERROR]\033[0m $*" >&2; }

if [[ -z "$DOMAIN" ]]; then
  err "دامنه را به عنوان آرگومان اول پاس دهید:"
  err "  sudo bash scripts/install_letsencrypt.sh your-domain.com"
  exit 1
fi

if ! command -v docker >/dev/null 2>&1; then
  err "docker در دسترس نیست — این اسکریپت باید روی سرور مرکزی اجرا شود."
  exit 1
fi

# ── 0) اعتبارسنجی A record ─────────────────────────────────────────
log "اعتبارسنجی A record برای $DOMAIN → $CENTRAL_IP ..."
resolved_ip="$(dig +short "$DOMAIN" A 2>/dev/null | head -1 || true)"
if [[ -z "$resolved_ip" ]]; then
  err "A record برای $DOMAIN یافت نشد (dig خالی برگرداند)."
  err "ابتدا در DNS هاست خود: A record → $CENTRAL_IP"
  exit 1
fi
if [[ "$resolved_ip" != "$CENTRAL_IP" ]]; then
  err "A record $DOMAIN → $resolved_ip ولی سرور مرکزی $CENTRAL_IP است."
  err "لطفاً A record را اصلاح کنید و دوباره اجرا کنید."
  exit 1
fi
log "A record تأیید شد ($resolved_ip)."

# ── 1) نصب certbot ──────────────────────────────────────────────────
log "نصب certbot ..."
if command -v certbot >/dev/null 2>&1; then
  log "certbot از قبل نصب است."
else
  if command -v apt-get >/dev/null 2>&1; then
    apt-get update -qq
    apt-get install -y -qq certbot
  elif command -v dnf >/dev/null 2>&1; then
    dnf install -y -qq certbot
  else
    err "مدیر بستهٔ شناخته‌شده یافت نشد — certbot را دستی نصب کنید."
    exit 1
  fi
fi

# ── 2) دایرکتوری webroot (روی هاست، مونت‌شده در nginx) ─────────────
mkdir -p "$WEBROOT_DIR"
chmod 755 "$WEBROOT_DIR"

log "صدور گواهی با webroot در $WEBROOT_DIR ..."
certbot certonly --webroot \
  --webroot-path "$WEBROOT_DIR" \
  -d "$DOMAIN" \
  --non-interactive \
  --agree-tos \
  --register-unsafely-without-email \
  --keep-until-expiring

# ── 3) کپی گواهی به infra/nginx/ssl ─────────────────────────────────
log "کپی گواهی به $SSL_DIR ..."
mkdir -p "$SSL_DIR"
CERT_DIR="/etc/letsencrypt/live/$DOMAIN"
cp "$CERT_DIR/fullchain.pem" "$SSL_DIR/fullchain.pem"
cp "$CERT_DIR/privkey.pem" "$SSL_DIR/privkey.pem"
cp "$CERT_DIR/chain.pem" "$SSL_DIR/chain.pem" 2>/dev/null || true
chmod 644 "$SSL_DIR/fullchain.pem"
chmod 600 "$SSL_DIR/privkey.pem"
log "گواهی در $SSL_DIR ذخیره شد."

# ── 4) فعال‌سازی listen 443 در nginx.conf ───────────────────────────
log "فعال‌سازی HTTPS در $NGINX_CONF ..."
python3 - <<PYEOF
import re

path = "$NGINX_CONF"
with open(path) as f:
    src = f.read()

# uncomment listen 80 server → redirect 301
src = src.replace(
    "    # بعد از نصب گواهی: خط زیر را برای ریدایرکت HTTP→HTTPS 301 فعال کنید\n    # return 301 https://\$host\$request_uri;",
    "    # بعد از نصب گواهی: خط زیر را برای ریدایرکت HTTP→HTTPS 301 فعال کنید\n    return 301 https://\$host\$request_uri;",
)

# uncomment the whole HTTPS server block
https_block = '''  # ── HTTPS — بعد از نصب گواهی Let's Encrypt فعال کنید ───────────
  # server {
  #   listen 443 ssl;
  #   server_name _;
  # 
  #   ssl_certificate     /etc/nginx/ssl/fullchain.pem;
  #   ssl_certificate_key /etc/nginx/ssl/privkey.pem;
  #   ssl_protocols TLSv1.2 TLSv1.3;
  #   ssl_ciphers ECDHE-ECDSA-AES128-GCM-SHA256:ECDHE-RSA-AES128-GCM-SHA256:ECDHE-ECDSA-AES256-GCM-SHA384:ECDHE-RSA-AES256-GCM-SHA384;
  #   ssl_prefer_server_ciphers on;
  #   ssl_session_cache shared:SSL:50m;
  #   ssl_session_timeout 1d;
  #   ssl_session_tickets off;
  #   add_header Strict-Transport-Security "max-age=63072000; includeSubDomains; preload" always;
  # 
  #   include /etc/nginx/http-server.conf;
  # }'''

active_block = '''  # ── HTTPS — فعال (Let's Encrypt) ──────────────────────────────
  server {
    listen 443 ssl;
    server_name $DOMAIN;

    ssl_certificate     /etc/nginx/ssl/fullchain.pem;
    ssl_certificate_key /etc/nginx/ssl/privkey.pem;
    ssl_protocols TLSv1.2 TLSv1.3;
    ssl_ciphers ECDHE-ECDSA-AES128-GCM-SHA256:ECDHE-RSA-AES128-GCM-SHA256:ECDHE-ECDSA-AES256-GCM-SHA384:ECDHE-RSA-AES256-GCM-SHA384;
    ssl_prefer_server_ciphers on;
    ssl_session_cache shared:SSL:50m;
    ssl_session_timeout 1d;
    ssl_session_tickets off;
    add_header Strict-Transport-Security "max-age=63072000; includeSubDomains; preload" always;

    include /etc/nginx/http-server.conf;
  }'''

if "# server {" in src and "listen 443 ssl" in src:
    src = src.replace(https_block, active_block)
else:
    err("block HTTPS در nginx.conf یافت نشد — الگوی فایل تغییر کرده است.")
    raise SystemExit(1)

with open(path, "w") as f:
    f.write(src)
log("nginx.conf به‌روز شد (443 + redirect).")
PYEOF

# ── 5) فعال‌سازی ssl volume و پورت 443 در compose/web.yml ───────────
log "فعال‌سازی ssl volume و پورت 443 در compose/web.yml ..."
python3 - <<PYEOF
path = "$WEB_YML"
with open(path) as f:
    src = f.read()

src = src.replace(
    "    # بعد از نصب گواهی HTTPS: خط زیر را uncomment کنید\n    # - ../infra/nginx/ssl:/etc/nginx/ssl:ro",
    "    - ../infra/nginx/ssl:/etc/nginx/ssl:ro",
)
src = src.replace(
    "    # بعد از نصب گواهی HTTPS: خط زیر را uncomment کنید\n    # - '443:443'",
    "    - '443:443'",
)

with open(path, "w") as f:
    f.write(src)
log("compose/web.yml به‌روز شد (ssl volume + 443).")
PYEOF

# ── 6) اعمال و ری‌استارت نرم nginx ──────────────────────────────────
log "بررسی پیکربندی nginx ..."
if ! docker exec barpro-nginx nginx -t >/dev/null 2>&1; then
  docker restart barpro-nginx >/dev/null 2>&1 || true
fi
if ! docker inspect barpro-nginx >/dev/null 2>&1; then
  log "nginx در حال اجرا نیست — با compose بالا می‌آوریم ..."
  (cd "$BASE_DIR" && docker compose -f compose/web.yml up -d nginx)
else
  docker compose -f compose/web.yml -f - up -d nginx 2>/dev/null \
    || (cd "$BASE_DIR" && docker compose -f compose/web.yml up -d nginx)
fi

sleep 5
log "تأیید HTTPS ..."
code="$(curl -s -m 10 -o /dev/null -w '%{http_code}' "https://$DOMAIN/" || true)"
if [[ "$code" == "200" || "$code" == "307" || "$code" == "301" ]]; then
  log "✅ HTTPS فعال است: https://$DOMAIN → HTTP $code"
else
  err "پاسخ غیرمنتظره از https://$DOMAIN → HTTP $code"
  err "لاگ nginx را بررسی کنید: docker logs --tail 50 barpro-nginx"
fi

# ── 7) یادآوری AUTH_COOKIE_SECURE ───────────────────────────────────
log ""
log "──────────────────────────────────────────────────────────────"
log "قدم‌های پایانی (دستی):"
log "  1. در .env مقدار زیر را تغییر دهید و deploy کنید:"
log "       AUTH_COOKIE_SECURE=true"
log "       FRONTEND_URL=https://$DOMAIN"
log "       FRONTEND_URLS=https://$DOMAIN"
log "  2. bash manage.sh deploy"
log "  3. تمدید خودکار گواهی (crontab):"
log "       15 3 * * * certbot renew --quiet --deploy-hook \"docker exec barpro-nginx nginx -s reload\""
log "──────────────────────────────────────────────────────────────"

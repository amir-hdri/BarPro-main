#!/bin/bash
# ═══════════════════════════════════════════════════════════════════
#  install_letsencrypt.sh — نصب خودکار HTTPS برای BarPro (Let's Encrypt)
#
#  پیش‌نیازها:
#    1. یک دامنهٔ واقعی با A record → <CENTRAL_IP> (87.107.5.238)
#    2. پورت 80 از اینترنت قابل‌دسترسی باشد (HTTP-01 challenge)
#
#  نحوهٔ استفاده (روی سرور مرکزی):
#    sudo bash scripts/install_letsencrypt.sh your-domain.com
#
#  چه کاری انجام می‌دهد:
#    1. صدور گواهی با webroot روی دایرکتوری repo-local
#       (infra/nginx/acme-challenge — همان چیزی که nginx در
#       location /.well-known/acme-challenge/ سرو می‌کند؛ بدون قطع سرویس)
#    2. کپی گواهی به infra/nginx/ssl/ (مونت‌شده در container nginx؛
#       طبق .gitignore هرگز کامیت نمی‌شود)
#    3. تبدیل سرور پورت 80 به ریدایرکت 301 (داخل location / تا
#       exemption مربوط به ACME دست‌نخورده بماند) + فعال‌سازی listen 443
#    4. مونت ssl volume و پورت 443 در compose/web.yml
#    5. بازسازی nginx + تأیید سلامت روی https://
#    6. به‌روزرسانی خودکار .env (با بکاپ): AUTH_COOKIE_SECURE=true و
#       FRONTEND_URL(S)=https://domain
# ═══════════════════════════════════════════════════════════════════

set -euo pipefail

DOMAIN="${1:-}"
CENTRAL_IP="${CENTRAL_IP:-87.107.5.238}"
BASE_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
WEBROOT_DIR="$BASE_DIR/infra/nginx/acme-challenge"
SSL_DIR="$BASE_DIR/infra/nginx/ssl"
NGINX_CONF="$BASE_DIR/infra/nginx/nginx.conf"
WEB_YML="$BASE_DIR/compose/web.yml"
ENV_FILE="$BASE_DIR/.env"

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
if command -v dig >/dev/null 2>&1; then
  resolved_ip="$(dig +short "$DOMAIN" A 2>/dev/null | head -1 || true)"
else
  resolved_ip="$(getent ahostsv4 "$DOMAIN" 2>/dev/null | awk '{print $1; exit}' || true)"
fi
if [[ -z "$resolved_ip" ]]; then
  err "A record برای $DOMAIN یافت نشد."
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

# ── 2) صدور گواهی (دایرکتوری repo-local که nginx هم‌اکنون سرو می‌کند) ──
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
log "گواهی در $SSL_DIR ذخیره شد (gitignored — هرگز کامیت نمی‌شود)."

# ── 4) فعال‌سازی 443 + ریدایرکت در nginx.conf ───────────────────────
# NOTE: heredoc عمداً quoted است (<<'PYEOF') تا $host و $request_uri توسط
# shell expand نشوند — همین باگ قبلاً ریدایرکت را بی‌صدا از کار انداخته بود.
log "فعال‌سازی HTTPS در $NGINX_CONF ..."
export LE_BASE_DIR="$BASE_DIR" LE_DOMAIN="$DOMAIN"
python3 - <<'PYEOF'
import os
import re
import sys

base = os.environ["LE_BASE_DIR"]
path = base + "/infra/nginx/nginx.conf"
with open(path) as f:
    src = f.read()

REDIRECT_MARK = "# LE-HTTPS-REDIRECT (install_letsencrypt.sh)"

# 4a) سرور پورت 80: include عمومی → ریدایرکت 301 داخل location /.
#     عمداً return سطح-server گذاشته نشد: return سطح-server همه locationها
#     (از جمله exemption مربوط به ACME) را override می‌کند و renewal را می‌شکند.
# NOTE: تطبیق عمداً ساختاری است (regex روی include با ایندنت دقیق)، نه روی
# متن فارسی کامنت‌ها — در کامنت‌ها نیم‌فاصله نامرئی (U+200C) هست که تطبیق
# رشته‌ای را شکننده می‌کند. include چهاراسپیسی فقط یک‌بار (سرور پورت 80)
# وجود دارد؛ نسخه داخل بلوک 443 شش‌اسپیسی و کامنت است.
if REDIRECT_MARK not in src:
    pat = re.compile(
        r"(?:    # [^\n]*\n)?"  # خط کامنت اختیاریِ درست قبل از include
        r"    include /etc/nginx/http-server\.conf;\n"
        r"  \}\n\n  # ── HTTPS"
    )
    matches = pat.findall(src)
    if len(matches) != 1:
        sys.stderr.write(
            "ERROR: expected exactly one active http-server.conf include "
            "(port-80 server); found %d — file layout changed, aborting.\n" % len(matches)
        )
        raise SystemExit(1)
    new_block = (
        "    location / {\n"
        "      " + REDIRECT_MARK + "\n"
        "      return 301 https://$host$request_uri;\n"
        "    }\n"
        "  }\n\n  # ── HTTPS"
    )
    src = pat.sub(new_block, src)
    print("port-80 server switched to 301 redirect (ACME location preserved).")
else:
    print("port-80 redirect already active, skipping.")

# 4b) فعال‌سازی بلوک 443.
# NOTE: مقایسه با rstrip سطر‌به‌سطر انجام می‌شود تا trailing-spaceهای
# نامرئی (ویرایشگرها معمولاً پاکشان می‌کنند) تطبیق را نشکند.
if "  server {\n    listen 443 ssl;" in src:
    print("443 server block already active, skipping.")
else:
    expected_commented = [
        "  # ── HTTPS — بعد از نصب گواهی Let's Encrypt فعال کنید ───────────",
        "  # server {",
        "  #   listen 443 ssl;",
        "  #   server_name _;",
        "  #",
        "  #   ssl_certificate     /etc/nginx/ssl/fullchain.pem;",
        "  #   ssl_certificate_key /etc/nginx/ssl/privkey.pem;",
        "  #   ssl_protocols TLSv1.2 TLSv1.3;",
        "  #   ssl_ciphers ECDHE-ECDSA-AES128-GCM-SHA256:ECDHE-RSA-AES128-GCM-SHA256:ECDHE-ECDSA-AES256-GCM-SHA384:ECDHE-RSA-AES256-GCM-SHA384;",
        "  #   ssl_prefer_server_ciphers on;",
        "  #   ssl_session_cache shared:SSL:50m;",
        "  #   ssl_session_timeout 1d;",
        "  #   ssl_session_tickets off;",
        '  #   add_header Strict-Transport-Security "max-age=63072000; includeSubDomains; preload" always;',
        "  #",
        "  #   include /etc/nginx/http-server.conf;",
        "  # }",
    ]
    file_lines = src.splitlines(keepends=True)
    start = next(
        (i for i, ln in enumerate(file_lines) if ln.rstrip("\n") == expected_commented[0]),
        None,
    )
    if start is None or any(
        file_lines[start + k].rstrip("\n").rstrip() != expected_commented[k].rstrip()
        for k in range(len(expected_commented))
    ):
        sys.stderr.write(
            "ERROR: commented HTTPS block not found in nginx.conf — "
            "layout changed, aborting (no changes written).\n"
        )
        raise SystemExit(1)
    domain = os.environ["LE_DOMAIN"]
    active_block = """  # ── HTTPS — فعال (Let's Encrypt) ──────────────────────────────
  server {
    listen 443 ssl;
    server_name DOMAIN_PLACEHOLDER;

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
  }""".replace("DOMAIN_PLACEHOLDER", domain)
    file_lines[start : start + len(expected_commented)] = [active_block + "\n"]
    src = "".join(file_lines)
    print("443 server block activated for %s." % domain)

with open(path, "w") as f:
    f.write(src)
print("nginx.conf updated.")
PYEOF
log "nginx.conf به‌روز شد (443 + redirect)."

# ── 5) فعال‌سازی ssl volume و پورت 443 در compose/web.yml ───────────
log "فعال‌سازی ssl volume و پورت 443 در compose/web.yml ..."
LE_BASE_DIR="$BASE_DIR" python3 - <<'PYEOF'
import os
import sys

path = os.environ["LE_BASE_DIR"] + "/compose/web.yml"
with open(path) as f:
    src = f.read()

pairs = [
    (
        "    # بعد از نصب گواهی HTTPS: خط زیر را uncomment کنید\n"
        "    # - ../infra/nginx/ssl:/etc/nginx/ssl:ro",
        "    - ../infra/nginx/ssl:/etc/nginx/ssl:ro",
    ),
    (
        "    # بعد از نصب گواهی HTTPS: خط زیر را uncomment کنید\n"
        "    # - '443:443'",
        "    - '443:443'",
    ),
]
for old, new in pairs:
    n = src.count(old)
    if n == 1:
        src = src.replace(old, new)
        print("activated: %s" % new.strip())
    elif new in src:
        print("already active: %s" % new.strip())
    else:
        sys.stderr.write("ERROR: pattern not found once (found %d): %r\n" % (n, old[:60]))
        raise SystemExit(1)

with open(path, "w") as f:
    f.write(src)
print("compose/web.yml updated.")
PYEOF
log "compose/web.yml به‌روز شد (ssl volume + 443)."

# ── 6) بازسازی nginx + تأیید سلامت ──────────────────────────────────
log "بازسازی nginx با پیکربندی جدید ..."
(cd "$BASE_DIR" && docker compose -f compose/web.yml up -d nginx)

log "بررسی پیکربندی داخل کانتینر ..."
docker exec barpro-nginx nginx -t

sleep 5
log "تأیید HTTPS ..."
code="$(curl -s -m 10 -o /dev/null -w '%{http_code}' "https://$DOMAIN/" || true)"
if [[ "$code" == "200" || "$code" == "307" || "$code" == "301" ]]; then
  log "✅ HTTPS فعال است: https://$DOMAIN → HTTP $code"
else
  err "پاسخ غیرمنتظره از https://$DOMAIN → HTTP $code"
  err "لاگ nginx را بررسی کنید: docker logs --tail 50 barpro-nginx"
  exit 1
fi

# ریدایرکت HTTP→HTTPS نباید مسیر ACME را ببلعد (حیاتی برای renewal).
acme_code="$(curl -s -m 10 -o /dev/null -w '%{http_code}' "http://$DOMAIN/.well-known/acme-challenge/__le_probe__" || true)"
if [[ "$acme_code" == "404" ]]; then
  log "✅ مسیر ACME از ریدایرکت مستثناست (404 مورد انتظار برای probe ناموجود)."
else
  err "هشدار: مسیر ACME کد $acme_code برگرداند (انتظار: 404، نه 301) — renewal ممکن است بشکند."
fi

# ── 7) به‌روزرسانی خودکار .env (با بکاپ) ────────────────────────────
log "به‌روزرسانی .env (AUTH_COOKIE_SECURE + FRONTEND_URL) ..."
LE_BASE_DIR="$BASE_DIR" LE_DOMAIN="$DOMAIN" python3 - <<'PYEOF'
import datetime
import os
import shutil
import sys

path = os.environ["LE_BASE_DIR"] + "/.env"
domain = os.environ["LE_DOMAIN"]
if not os.path.exists(path):
    sys.stderr.write("ERROR: %s not found — cannot set AUTH_COOKIE_SECURE.\n" % path)
    raise SystemExit(1)

backup = "%s.bak-%s" % (path, datetime.datetime.now().strftime("%Y%m%d-%H%M%S"))
shutil.copy2(path, backup)
print("backup written: %s" % backup)

with open(path) as f:
    lines = f.read().splitlines()

wanted = {
    "AUTH_COOKIE_SECURE": "true",
    "FRONTEND_URL": "https://%s" % domain,
    "FRONTEND_URLS": "https://%s" % domain,
}
seen = set()
out = []
for line in lines:
    stripped = line.strip()
    if stripped and not stripped.startswith("#") and "=" in stripped:
        key = stripped.split("=", 1)[0].strip()
        if key in wanted:
            out.append('%s="%s"' % (key, wanted[key]))
            seen.add(key)
            continue
    out.append(line)
for key, value in wanted.items():
    if key not in seen:
        out.append('%s="%s"' % (key, value))

with open(path, "w") as f:
    f.write("\n".join(out) + "\n")

# verify by re-reading
with open(path) as f:
    content = f.read()
for key, value in wanted.items():
    if ('%s="%s"' % (key, value)) not in content and ("%s=%s" % (key, value)) not in content:
        sys.stderr.write("ERROR: failed to persist %s in .env\n" % key)
        raise SystemExit(1)
print(".env updated: AUTH_COOKIE_SECURE=true, FRONTEND_URL(S)=https://%s" % domain)
PYEOF

log ""
log "──────────────────────────────────────────────────────────────"
log "قدم‌های پایانی:"
log "  1. بک‌اند را با env جدید deploy کنید (گارد بوت، Secure+HTTPS را چک می‌کند):"
log "       bash manage.sh deploy"
log "  2. تمدید خودکار گواهی (یک‌بار در crontab):"
log "       15 3 * * * /bin/bash $BASE_DIR/scripts/renew_letsencrypt.sh $DOMAIN >>/var/log/barpro-le-renew.log 2>&1"
log "──────────────────────────────────────────────────────────────"

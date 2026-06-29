#!/usr/bin/env bash
# ═══════════════════════════════════════════════════════════════════
#  BarPro — استقرار کامل روی سرور (server-side)
#  اجرا: bash /opt/barpro/deploy.sh 2>&1 | tee /opt/barpro/deploy.log
# ═══════════════════════════════════════════════════════════════════
set -euo pipefail

DIR="/opt/barpro"
WEB_DIR="$DIR/apps/web"
PRIMARY_IP="188.121.123.16"
DB_NAME="utcms_rpa"
LOG="$DIR/deploy.log"

GR='\033[92m'; RD='\033[91m'; YL='\033[93m'; CY='\033[96m'; BL='\033[94m'; RS='\033[0m'; BD='\033[1m'
ok()  { echo -e "  ${GR}✓${RS}  $*"; }
err() { echo -e "  ${RD}✗${RS}  ${RD}$*${RS}"; }
inf() { echo -e "  ${CY}→${RS}  $*"; }
hdr() { echo -e "\n${BD}${BL}──────────────────────────────────────────────────────────────${RS}\n${BD}${BL}  $*${RS}\n${BD}${BL}──────────────────────────────────────────────────────────────${RS}"; }

echo -e "${BD}${BL}"
echo "╔══════════════════════════════════════════════════════════════╗"
echo "║       BarPro — استقرار کامل روی سرور  🚀                   ║"
echo "╚══════════════════════════════════════════════════════════════╝"
echo -e "${RS}"

# ───────────────────────────────────────────────────────────────────
hdr "قدم ۱ — بررسی ابزارهای لازم"
# ───────────────────────────────────────────────────────────────────
node --version && ok "Node: $(node --version)" || { err "Node نصب نیست"; exit 1; }
npm  --version && ok "npm : $(npm  --version)" || { err "npm نصب نیست";  exit 1; }
docker --version       && ok "Docker موجود است" || { err "Docker نصب نیست"; exit 1; }
ls "$WEB_DIR/package.json" &>/dev/null && ok "پوشه وب موجود است" || { err "پوشه $WEB_DIR پیدا نشد"; exit 1; }

# ───────────────────────────────────────────────────────────────────
hdr "قدم ۲ — نصب پکیج‌های npm (در سرور، بدون Docker)"
# ───────────────────────────────────────────────────────────────────
cd "$WEB_DIR"
inf "رجیستری npm را روی registry.npmjs.org تنظیم می‌کنیم..."
npm config set registry https://registry.npmjs.org
npm config set strict-ssl true

inf "در حال اجرای npm install..."
if ! npm install --prefer-offline 2>&1; then
  inf "تلاش با --legacy-peer-deps..."
  npm install --legacy-peer-deps 2>&1
fi
ok "npm install موفق بود"

# ───────────────────────────────────────────────────────────────────
hdr "قدم ۳ — بیلد Next.js (روی سرور)"
# ───────────────────────────────────────────────────────────────────
cd "$WEB_DIR"
inf "بیلد Next.js..."
NODE_ENV=production \
  NEXT_PUBLIC_API_URL="/api" \
  npm run build 2>&1

if [ -d "$WEB_DIR/.next/standalone" ]; then
  ok "بیلد موفق — .next/standalone ایجاد شد"
else
  err "بیلد شکست خورد — .next/standalone پیدا نشد"
  exit 1
fi

# ───────────────────────────────────────────────────────────────────
hdr "قدم ۴ — تصحیح فایل‌های کانفیگ"
# ───────────────────────────────────────────────────────────────────
cd "$DIR"
sed -i "s/IP_ADDRESS_1/$PRIMARY_IP/g"   infra/squid/squid_1.conf 2>/dev/null || true
sed -i "s/IP_ADDRESS_2/95.38.233.90/g"  infra/squid/squid_2.conf 2>/dev/null || true
sed -i "s/IP_ADDRESS_3/95.38.233.90/g"  infra/squid/squid_3.conf 2>/dev/null || true
sed -i 's/host\.docker\.internal:8000/backend:8000/g' infra/prometheus/prometheus.yml 2>/dev/null || true
ok "کانفیگ‌ها اصلاح شدند"

# ───────────────────────────────────────────────────────────────────
hdr "قدم ۵ — ساخت و راه‌اندازی Docker Compose"
# ───────────────────────────────────────────────────────────────────
cd "$DIR"

# تشخیص docker compose
if docker compose version &>/dev/null; then
  COMPOSE="docker compose"
else
  COMPOSE="docker-compose"
fi
inf "استفاده از: $COMPOSE"

# Pull ایمیج‌های خارجی
inf "دریافت ایمیج‌های پایه..."
$COMPOSE pull --quiet postgres redis nginx prometheus 2>&1 || true

# بیلد و راه‌اندازی
inf "ساخت و راه‌اندازی تمام سرویس‌ها..."
$COMPOSE up -d --build --remove-orphans 2>&1
ok "Docker Compose راه‌اندازی شد"

# ───────────────────────────────────────────────────────────────────
hdr "قدم ۶ — مایگریشن دیتابیس"
# ───────────────────────────────────────────────────────────────────
inf "انتظار برای آماده شدن PostgreSQL..."
for i in $(seq 1 30); do
  if $COMPOSE exec -T postgres pg_isready -U postgres -d "$DB_NAME" &>/dev/null; then
    ok "PostgreSQL آماده است"
    break
  fi
  printf "\r  → انتظار... %d/30" "$i"
  sleep 4
done
echo

inf "اجرای مایگریشن Alembic..."
$COMPOSE exec -T backend alembic upgrade head 2>&1 || true
ok "مایگریشن انجام شد"

# ───────────────────────────────────────────────────────────────────
hdr "قدم ۷ — بررسی وضعیت نهایی"
# ───────────────────────────────────────────────────────────────────
sleep 5
$COMPOSE ps 2>&1
echo
inf "بررسی healthcheck..."
curl -sf "http://localhost/api/healthz" && ok "API آماده است" || inf "API در حال راه‌اندازی..."
curl -sI "http://localhost/" 2>&1 | head -3 || inf "Frontend در حال راه‌اندازی..."

echo -e "\n${BD}${GR}"
echo "╔══════════════════════════════════════════════════════════════╗"
echo "║           ✅  استقرار با موفقیت تکمیل شد                   ║"
echo "╠══════════════════════════════════════════════════════════════╣"
echo "║  Backend : http://$PRIMARY_IP/api                          ║"
echo "║  Frontend: http://$PRIMARY_IP                              ║"
echo "╚══════════════════════════════════════════════════════════════╝"
echo -e "${RS}"

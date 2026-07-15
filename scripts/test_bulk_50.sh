#!/bin/bash
# ════════════════════════════════════════════════════════════════════
# BarPro — تست Bulk بزرگ: 50 Waybill + 50 Fuel
# ════════════════════════════════════════════════════════════════════
# این اسکریپت برای تست stability و scale testing است
# ════════════════════════════════════════════════════════════════════

set -e

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
NC='\033[0m'
BOLD='\033[1m'

log_header() {
    echo ""
    echo -e "${BOLD}${CYAN}═══════════════════════════════════════════════════════════════${NC}"
    echo -e "${BOLD}${CYAN}  $1${NC}"
    echo -e "${BOLD}${CYAN}═══════════════════════════════════════════════════════════════${NC}"
}

log_info() { echo -e "${CYAN}→${NC} $1"; }
log_ok() { echo -e "${GREEN}✓${NC} $1"; }
log_warn() { echo -e "${YELLOW}⚠${NC} $1"; }
log_err() { echo -e "${RED}✗${NC} $1"; }

# ════════════════════════════════════════════════════════════════════
# تنظیمات
# ════════════════════════════════════════════════════════════════════

API_KEY="utcms_5e128ee6c4c1d5fddb498e956afc0ee6d12ae12af03e99827dcc8de5cb596a50"
API_URL="http://localhost"

# دریافت Client ID و Driver ID
log_header "آماده‌سازی تست Bulk"

CLIENT_DRIVER=$(docker exec barpro-postgres psql -U barpro_user -d barpro_db -t -c "
SELECT c.id, d.id 
FROM clients c 
JOIN drivers d ON d.client_id = c.id 
WHERE c.active = true AND d.active = true 
LIMIT 1;
" | tr -d ' ' | head -n1)

if [ -z "$CLIENT_DRIVER" ]; then
    log_err "هیچ client/driver فعالی یافت نشد!"
    exit 1
fi

CLIENT_ID=$(echo "$CLIENT_DRIVER" | cut -d'|' -f1)
DRIVER_ID=$(echo "$CLIENT_DRIVER" | cut -d'|' -f2)

log_info "استفاده از Client ID: $CLIENT_ID, Driver ID: $DRIVER_ID"

# ════════════════════════════════════════════════════════════════════
# تمیز کردن jobs قدیمی
# ════════════════════════════════════════════════════════════════════

log_info "تمیز کردن jobs قدیمی..."
docker exec barpro-postgres psql -U barpro_user -d barpro_db -c "
DELETE FROM waybill_jobs WHERE created_at < NOW() - INTERVAL '30 minutes';
DELETE FROM fuel_inquiries WHERE created_at < NOW() - INTERVAL '30 minutes';
" > /dev/null

# ════════════════════════════════════════════════════════════════════
# ارسال 50 Waybill Jobs
# ════════════════════════════════════════════════════════════════════

log_header "ارسال 50 Waybill Jobs"

WAYBILL_IDS=()
WAYBILL_START=$(date +%s)

ORIGINS=("تهران" "اصفهان" "مشهد" "شیراز" "تبریز")
DESTINATIONS=("اصفهان" "شیراز" "تهران" "کرج" "قم")
PRODUCTS=("سیمان" "آهن" "مواد غذایی" "لوازم" "نفت")

for i in {1..50}; do
    ORIGIN=${ORIGINS[$((i % 5))]}
    DEST=${DESTINATIONS[$((i % 5))]}
    PRODUCT=${PRODUCTS[$((i % 5))]}
    WEIGHT=$((20000 + i * 500))
    
    RESP=$(curl -s -X POST "$API_URL/api/waybill/submit" \
      -H "Content-Type: application/json" \
      -H "X-API-Key: $API_KEY" \
      -d "{
        \"client_id\": $CLIENT_ID,
        \"driver_id\": $DRIVER_ID,
        \"origin\": \"$ORIGIN\",
        \"destination\": \"$DEST\",
        \"product\": \"$PRODUCT\",
        \"weight\": $WEIGHT
      }")
    
    JOB_ID=$(echo "$RESP" | grep -o '"id":[0-9]*' | head -1 | cut -d':' -f2)
    
    if [ -n "$JOB_ID" ]; then
        WAYBILL_IDS+=("$JOB_ID")
        echo -ne "\r  ${GREEN}✓${NC} Waybill $i/50 ایجاد شد (ID: $JOB_ID)    "
    else
        log_err "Waybill $i شکست خورد"
    fi
    
    # Rate limiting: 100ms delay
    sleep 0.1
done

WAYBILL_END=$(date +%s)
WAYBILL_SUBMIT_TIME=$((WAYBILL_END - WAYBILL_START))

echo ""
log_ok "50 Waybill job ارسال شد در ${WAYBILL_SUBMIT_TIME}s"

# ════════════════════════════════════════════════════════════════════
# ارسال 50 Fuel Inquiries
# ════════════════════════════════════════════════════════════════════

log_header "ارسال 50 Fuel Inquiries"

FUEL_IDS=()
FUEL_START=$(date +%s)

for i in {1..50}; do
    PLATE_NUM=$((10 + i))
    PLATE_LETTER=$(printf "\u0635")  # ص
    PLATE="${PLATE_NUM}${PLATE_LETTER}123-45"
    
    RESP=$(curl -s -X POST "$API_URL/api/fuel/inquiry" \
      -H "Content-Type: application/json" \
      -H "X-API-Key: $API_KEY" \
      -d "{
        \"client_id\": $CLIENT_ID,
        \"driver_id\": $DRIVER_ID,
        \"vehicle_plate\": \"$PLATE\"
      }")
    
    FUEL_ID=$(echo "$RESP" | grep -o '"id":[0-9]*' | head -1 | cut -d':' -f2)
    
    if [ -n "$FUEL_ID" ]; then
        FUEL_IDS+=("$FUEL_ID")
        echo -ne "\r  ${GREEN}✓${NC} Fuel $i/50 ایجاد شد (ID: $FUEL_ID)    "
    else
        log_err "Fuel $i شکست خورد"
    fi
    
    sleep 0.1
done

FUEL_END=$(date +%s)
FUEL_SUBMIT_TIME=$((FUEL_END - FUEL_START))

echo ""
log_ok "50 Fuel inquiry ارسال شد در ${FUEL_SUBMIT_TIME}s"

# ════════════════════════════════════════════════════════════════════
# مانیتور پیشرفت (max 15 دقیقه)
# ════════════════════════════════════════════════════════════════════

log_header "مانیتور پیشرفت (max 15 دقیقه)"

MONITOR_START=$(date +%s)
MONITOR_TIMEOUT=900  # 15 دقیقه

PREV_W_COMPLETED=0
PREV_F_COMPLETED=0

while true; do
    ELAPSED=$(($(date +%s) - MONITOR_START))
    
    if [ $ELAPSED -gt $MONITOR_TIMEOUT ]; then
        log_warn "Timeout بعد از 15 دقیقه"
        break
    fi
    
    # شمارش وضعیت‌ها
    STATS=$(docker exec barpro-postgres psql -U barpro_user -d barpro_db -t -c "
    SELECT 
      (SELECT COUNT(*) FROM waybill_jobs WHERE id IN ($(IFS=,; echo "${WAYBILL_IDS[*]}"))) as w_total,
      (SELECT COUNT(*) FROM waybill_jobs WHERE id IN ($(IFS=,; echo "${WAYBILL_IDS[*]}")) AND status='completed') as w_completed,
      (SELECT COUNT(*) FROM waybill_jobs WHERE id IN ($(IFS=,; echo "${WAYBILL_IDS[*]}")) AND status='failed') as w_failed,
      (SELECT COUNT(*) FROM waybill_jobs WHERE id IN ($(IFS=,; echo "${WAYBILL_IDS[*]}")) AND status IN ('queued','waiting_auth','processing')) as w_pending,
      (SELECT COUNT(*) FROM fuel_inquiries WHERE id IN ($(IFS=,; echo "${FUEL_IDS[*]}"))) as f_total,
      (SELECT COUNT(*) FROM fuel_inquiries WHERE id IN ($(IFS=,; echo "${FUEL_IDS[*]}")) AND status='completed') as f_completed,
      (SELECT COUNT(*) FROM fuel_inquiries WHERE id IN ($(IFS=,; echo "${FUEL_IDS[*]}")) AND status='failed') as f_failed,
      (SELECT COUNT(*) FROM fuel_inquiries WHERE id IN ($(IFS=,; echo "${FUEL_IDS[*]}")) AND status IN ('queued','waiting_auth','processing')) as f_pending;
    ")
    
    W_COMPLETED=$(echo "$STATS" | awk '{print $3}' | tr -d ' ')
    W_FAILED=$(echo "$STATS" | awk '{print $5}' | tr -d ' ')
    W_PENDING=$(echo "$STATS" | awk '{print $7}' | tr -d ' ')
    
    F_COMPLETED=$(echo "$STATS" | awk '{print $11}' | tr -d ' ')
    F_FAILED=$(echo "$STATS" | awk '{print $13}' | tr -d ' ')
    F_PENDING=$(echo "$STATS" | awk '{print $15}' | tr -d ' ')
    
    TOTAL_DONE=$((W_COMPLETED + W_FAILED + F_COMPLETED + F_FAILED))
    
    # محاسبه rate (jobs/min)
    if [ $ELAPSED -gt 10 ]; then
        W_RATE=$(( (W_COMPLETED - PREV_W_COMPLETED) * 60 / 10 ))
        F_RATE=$(( (F_COMPLETED - PREV_F_COMPLETED) * 60 / 10 ))
    else
        W_RATE=0
        F_RATE=0
    fi
    
    PREV_W_COMPLETED=$W_COMPLETED
    PREV_F_COMPLETED=$F_COMPLETED
    
    # نمایش پیشرفت
    echo -ne "\r  ${CYAN}→${NC} "
    echo -ne "Waybill: ${GREEN}${W_COMPLETED}✓${NC} ${RED}${W_FAILED}✗${NC} ${YELLOW}${W_PENDING}⏳${NC} (${W_RATE}/min) | "
    echo -ne "Fuel: ${GREEN}${F_COMPLETED}✓${NC} ${RED}${F_FAILED}✗${NC} ${YELLOW}${F_PENDING}⏳${NC} (${F_RATE}/min) | "
    echo -ne "Elapsed: ${ELAPSED}s / 900s   "
    
    # اگر همه تمام شدند
    if [ $TOTAL_DONE -ge 100 ]; then
        break
    fi
    
    sleep 10
done

echo ""

MONITOR_END=$(date +%s)
TOTAL_TIME=$((MONITOR_END - MONITOR_START))

# ════════════════════════════════════════════════════════════════════
# نتایج نهایی
# ════════════════════════════════════════════════════════════════════

log_header "نتایج نهایی"

# جمع‌آوری آمار نهایی
FINAL_STATS=$(docker exec barpro-postgres psql -U barpro_user -d barpro_db -t -c "
SELECT 
  'Waybill' as type,
  COUNT(*) as total,
  SUM(CASE WHEN status='completed' THEN 1 ELSE 0 END) as completed,
  SUM(CASE WHEN status='failed' THEN 1 ELSE 0 END) as failed,
  SUM(CASE WHEN status IN ('queued','waiting_auth','processing') THEN 1 ELSE 0 END) as pending
FROM waybill_jobs 
WHERE id IN ($(IFS=,; echo "${WAYBILL_IDS[*]}"))
UNION ALL
SELECT 
  'Fuel' as type,
  COUNT(*) as total,
  SUM(CASE WHEN status='completed' THEN 1 ELSE 0 END) as completed,
  SUM(CASE WHEN status='failed' THEN 1 ELSE 0 END) as failed,
  SUM(CASE WHEN status IN ('queued','waiting_auth','processing') THEN 1 ELSE 0 END) as pending
FROM fuel_inquiries 
WHERE id IN ($(IFS=,; echo "${FUEL_IDS[*]}"));
")

echo "$FINAL_STATS" | while read -r line; do
    echo "  $line"
done

# محاسبه success rate
W_SUCCESS=$(echo "$FINAL_STATS" | grep Waybill | awk '{print $5}' | tr -d ' ')
W_TOTAL=$(echo "$FINAL_STATS" | grep Waybill | awk '{print $3}' | tr -d ' ')
F_SUCCESS=$(echo "$FINAL_STATS" | grep Fuel | awk '{print $5}' | tr -d ' ')
F_TOTAL=$(echo "$FINAL_STATS" | grep Fuel | awk '{print $3}' | tr -d ' ')

TOTAL_SUCCESS=$((W_SUCCESS + F_SUCCESS))
SUCCESS_RATE=$(( TOTAL_SUCCESS * 100 / 100 ))

echo ""
log_info "زمان کل: ${TOTAL_TIME}s ($(( TOTAL_TIME / 60 )) دقیقه)"
log_info "متوسط زمان هر job: $(( TOTAL_TIME / 100 ))s"
log_info "Throughput: $(( 100 * 60 / TOTAL_TIME )) jobs/min"
echo ""
echo -e "${BOLD}Success Rate: ${SUCCESS_RATE}%${NC}"

# تعیین وضعیت
if [ $SUCCESS_RATE -eq 100 ]; then
    echo ""
    echo -e "${BOLD}${GREEN}╔═══════════════════════════════════════════════════════════════╗${NC}"
    echo -e "${BOLD}${GREEN}║  🎉 عالی! تست Bulk با 100% موفقیت تمام شد!              ║${NC}"
    echo -e "${BOLD}${GREEN}╚═══════════════════════════════════════════════════════════════╝${NC}"
    exit 0
elif [ $SUCCESS_RATE -ge 90 ]; then
    echo ""
    echo -e "${BOLD}${GREEN}╔═══════════════════════════════════════════════════════════════╗${NC}"
    echo -e "${BOLD}${GREEN}║  ✓ خوب! تست Bulk با ${SUCCESS_RATE}% موفقیت (≥90%)                 ║${NC}"
    echo -e "${BOLD}${GREEN}╚═══════════════════════════════════════════════════════════════╝${NC}"
    exit 0
elif [ $SUCCESS_RATE -ge 80 ]; then
    echo ""
    echo -e "${BOLD}${YELLOW}╔═══════════════════════════════════════════════════════════════╗${NC}"
    echo -e "${BOLD}${YELLOW}║  ⚠️  قابل قبول: تست Bulk با ${SUCCESS_RATE}% موفقیت (≥80%)      ║${NC}"
    echo -e "${BOLD}${YELLOW}╚═══════════════════════════════════════════════════════════════╝${NC}"
    exit 0
else
    echo ""
    echo -e "${BOLD}${RED}╔═══════════════════════════════════════════════════════════════╗${NC}"
    echo -e "${BOLD}${RED}║  ❌ نیاز به بهبود: Success Rate فقط ${SUCCESS_RATE}%             ║${NC}"
    echo -e "${BOLD}${RED}╚═══════════════════════════════════════════════════════════════╝${NC}"
    
    # لیست failed jobs
    log_warn "لیست 10 job شکست خورده:"
    docker exec barpro-postgres psql -U barpro_user -d barpro_db -c "
    SELECT 'Waybill' as type, id, error_message 
    FROM waybill_jobs 
    WHERE status='failed' AND id IN ($(IFS=,; echo "${WAYBILL_IDS[*]}"))
    LIMIT 10
    UNION ALL
    SELECT 'Fuel' as type, id, error_message 
    FROM fuel_inquiries 
    WHERE status='failed' AND id IN ($(IFS=,; echo "${FUEL_IDS[*]}"))
    LIMIT 10;
    "
    
    exit 1
fi

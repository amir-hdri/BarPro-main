#!/bin/bash
# ════════════════════════════════════════════════════════════════════
# BarPro — اسکریپت تست کامل و رسیدن به 100% موفقیت
# ════════════════════════════════════════════════════════════════════
# این اسکریپت باید مستقیماً روی سرور مرکزی اجرا شود
# 
# Usage:
#   bash test_100_percent.sh
# ════════════════════════════════════════════════════════════════════

set -e  # Exit on error

# رنگ‌ها
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
NC='\033[0m' # No Color
BOLD='\033[1m'

# توابع کمکی
log_header() {
    echo ""
    echo -e "${BOLD}${BLUE}═══════════════════════════════════════════════════════════════${NC}"
    echo -e "${BOLD}${BLUE}  $1${NC}"
    echo -e "${BOLD}${BLUE}═══════════════════════════════════════════════════════════════${NC}"
}

log_info() {
    echo -e "${CYAN}→${NC} $1"
}

log_ok() {
    echo -e "${GREEN}✓${NC} $1"
}

log_warn() {
    echo -e "${YELLOW}⚠${NC} $1"
}

log_err() {
    echo -e "${RED}✗${NC} $1"
}

# متغیرهای شمارش
TOTAL_TESTS=0
PASSED_TESTS=0
FAILED_TESTS=0

# لیست مشکلات
declare -a ISSUES

# ════════════════════════════════════════════════════════════════════
# Task 1: بررسی وضعیت Containers
# ════════════════════════════════════════════════════════════════════
log_header "Task 1: بررسی وضعیت Containers"

log_info "بررسی وضعیت containers..."
CONTAINERS=(
    "barpro-postgres"
    "barpro-redis"
    "barpro-backend"
    "barpro-celery-worker-1"
    "barpro-celery-worker-2"
    "barpro-celery-worker-3"
    "barpro-celery-beat"
    "barpro-nginx"
    "barpro-frontend"
)

ALL_HEALTHY=true
for container in "${CONTAINERS[@]}"; do
    if docker ps --format '{{.Names}}' | grep -q "^${container}$"; then
        STATUS=$(docker inspect --format='{{.State.Status}}' "$container")
        if [ "$STATUS" = "running" ]; then
            log_ok "$container: running"
        else
            log_err "$container: $STATUS"
            ALL_HEALTHY=false
            ISSUES+=("Container $container در وضعیت $STATUS")
        fi
    else
        log_err "$container: not found"
        ALL_HEALTHY=false
        ISSUES+=("Container $container وجود ندارد")
    fi
done

if [ "$ALL_HEALTHY" = true ]; then
    log_ok "تمام containers healthy هستند"
    ((PASSED_TESTS++))
else
    log_err "برخی containers مشکل دارند"
    ((FAILED_TESTS++))
fi
((TOTAL_TESTS++))

# بررسی Chromium در workers
log_info "بررسی Chromium در workers..."
for i in 1 2 3; do
    CHROMIUM_VERSION=$(docker exec "barpro-celery-worker-$i" /usr/bin/chromium --version 2>/dev/null || echo "NOT FOUND")
    if [[ "$CHROMIUM_VERSION" == *"97"* ]]; then
        log_ok "Worker $i: $CHROMIUM_VERSION"
    else
        log_warn "Worker $i: $CHROMIUM_VERSION"
        ISSUES+=("Worker $i: Chromium 97 نیست")
    fi
done

# ════════════════════════════════════════════════════════════════════
# Task 2: تست Auth یک Driver
# ════════════════════════════════════════════════════════════════════
log_header "Task 2: تست Auth یک Driver"

log_info "بررسی clients و drivers موجود..."
CLIENT_DRIVER=$(docker exec barpro-postgres psql -U barpro_user -d barpro_db -t -c "
SELECT c.id, d.id 
FROM clients c 
JOIN drivers d ON d.client_id = c.id 
WHERE c.active = true AND d.active = true 
LIMIT 1;
" | tr -d ' ' | head -n1)

if [ -z "$CLIENT_DRIVER" ]; then
    log_err "هیچ client/driver فعالی یافت نشد!"
    log_warn "ایجاد client و driver نمونه..."
    
    # ایجاد client نمونه
    docker exec barpro-postgres psql -U barpro_user -d barpro_db -c "
    INSERT INTO clients (name, active, created_at, updated_at) 
    VALUES ('تست کلاینت', true, NOW(), NOW()) 
    ON CONFLICT DO NOTHING;
    "
    
    # ایجاد driver نمونه
    docker exec barpro-postgres psql -U barpro_user -d barpro_db -c "
    INSERT INTO drivers (client_id, name, username, password_encrypted, active, created_at, updated_at)
    SELECT id, 'راننده تست', 'test_driver', 'encrypted_pass', true, NOW(), NOW()
    FROM clients WHERE name = 'تست کلاینت' LIMIT 1
    ON CONFLICT DO NOTHING;
    "
    
    CLIENT_DRIVER=$(docker exec barpro-postgres psql -U barpro_user -d barpro_db -t -c "
    SELECT c.id, d.id 
    FROM clients c 
    JOIN drivers d ON d.client_id = c.id 
    WHERE c.active = true AND d.active = true 
    LIMIT 1;
    " | tr -d ' ' | head -n1)
fi

CLIENT_ID=$(echo "$CLIENT_DRIVER" | cut -d'|' -f1)
DRIVER_ID=$(echo "$CLIENT_DRIVER" | cut -d'|' -f2)

log_info "استفاده از Client ID: $CLIENT_ID, Driver ID: $DRIVER_ID"

# تمیز کردن auth sessions قبلی
log_info "تمیز کردن auth sessions قبلی..."
docker exec barpro-postgres psql -U barpro_user -d barpro_db -c "
DELETE FROM auth_sessions WHERE driver_id = $DRIVER_ID AND created_at < NOW() - INTERVAL '1 hour';
"

log_info "ارسال Auth task..."
AUTH_TASK_ID=$(docker exec barpro-celery-worker-1 python3 -c "
import sys
sys.path.insert(0, '/opt/barpro')
from app.workers.celery_app import celery_app

result = celery_app.send_task(
    'phase1.auth.process',
    args=[$CLIENT_ID, $DRIVER_ID, 'test_100_percent'],
    queue='rpa_auth_1'
)
print(result.id)
" 2>/dev/null)

if [ -z "$AUTH_TASK_ID" ]; then
    log_err "ارسال Auth task شکست خورد"
    ISSUES+=("Auth task ارسال نشد")
    ((FAILED_TESTS++))
    ((TOTAL_TESTS++))
else
    log_ok "Auth task ارسال شد: $AUTH_TASK_ID"
    
    log_info "منتظر اتمام Auth (max 60 ثانیه)..."
    
    AUTH_SUCCESS=false
    for i in {1..30}; do
        sleep 2
        
        AUTH_STATUS=$(docker exec barpro-postgres psql -U barpro_user -d barpro_db -t -c "
        SELECT status FROM auth_sessions 
        WHERE driver_id = $DRIVER_ID 
        ORDER BY created_at DESC 
        LIMIT 1;
        " | tr -d ' ')
        
        if [ "$AUTH_STATUS" = "active" ]; then
            log_ok "Auth موفق: status = active"
            AUTH_SUCCESS=true
            ((PASSED_TESTS++))
            break
        elif [ "$AUTH_STATUS" = "failed" ]; then
            log_err "Auth شکست خورد: status = failed"
            ISSUES+=("Auth task با status failed تمام شد")
            ((FAILED_TESTS++))
            break
        else
            echo -ne "\r  ${CYAN}→${NC} Auth status: ${AUTH_STATUS:-pending} ... ($i/30)"
        fi
    done
    echo ""
    
    if [ "$AUTH_SUCCESS" = false ] && [ "$AUTH_STATUS" != "failed" ]; then
        log_warn "Auth timeout شد (60 ثانیه)"
        ISSUES+=("Auth task timeout بعد از 60 ثانیه")
        ((FAILED_TESTS++))
    fi
    
    ((TOTAL_TESTS++))
fi

# بررسی logs برای errors
log_info "بررسی logs worker برای errors..."
AUTH_ERRORS=$(docker logs --since 2m barpro-celery-worker-1 2>&1 | grep -i "error\|exception\|crash" | grep -i "auth" | tail -5)
if [ -n "$AUTH_ERRORS" ]; then
    log_warn "Errors در logs Auth:"
    echo "$AUTH_ERRORS" | while read -r line; do
        echo "    $line"
    done
fi

# ════════════════════════════════════════════════════════════════════
# Task 3: تست ثبت بارنامه
# ════════════════════════════════════════════════════════════════════
log_header "Task 3: تست ثبت بارنامه"

log_info "تمیز کردن waybill jobs قدیمی..."
docker exec barpro-postgres psql -U barpro_user -d barpro_db -c "
DELETE FROM waybill_jobs WHERE created_at < NOW() - INTERVAL '1 hour';
"

log_info "ارسال Waybill job..."
WAYBILL_RESPONSE=$(curl -s -X POST http://localhost/api/waybill/submit \
  -H "Content-Type: application/json" \
  -H "X-API-Key: utcms_5e128ee6c4c1d5fddb498e956afc0ee6d12ae12af03e99827dcc8de5cb596a50" \
  -d "{
    \"client_id\": $CLIENT_ID,
    \"driver_id\": $DRIVER_ID,
    \"origin\": \"تهران\",
    \"destination\": \"اصفهان\",
    \"product\": \"سیمان\",
    \"weight\": 25000
  }")

WAYBILL_JOB_ID=$(echo "$WAYBILL_RESPONSE" | grep -o '"id":[0-9]*' | head -1 | cut -d':' -f2)

if [ -z "$WAYBILL_JOB_ID" ]; then
    log_err "ارسال Waybill job شکست خورد"
    log_warn "Response: $WAYBILL_RESPONSE"
    ISSUES+=("Waybill job ارسال نشد")
    ((FAILED_TESTS++))
    ((TOTAL_TESTS++))
else
    log_ok "Waybill job ایجاد شد: ID = $WAYBILL_JOB_ID"
    
    log_info "منتظر اتمام Waybill (max 120 ثانیه)..."
    
    WAYBILL_SUCCESS=false
    for i in {1..60}; do
        sleep 2
        
        WAYBILL_STATUS=$(docker exec barpro-postgres psql -U barpro_user -d barpro_db -t -c "
        SELECT status FROM waybill_jobs 
        WHERE id = $WAYBILL_JOB_ID;
        " | tr -d ' ')
        
        if [ "$WAYBILL_STATUS" = "completed" ]; then
            log_ok "Waybill موفق: status = completed"
            WAYBILL_SUCCESS=true
            ((PASSED_TESTS++))
            break
        elif [ "$WAYBILL_STATUS" = "failed" ]; then
            log_err "Waybill شکست خورد: status = failed"
            
            ERROR_MSG=$(docker exec barpro-postgres psql -U barpro_user -d barpro_db -t -c "
            SELECT error_message FROM waybill_jobs WHERE id = $WAYBILL_JOB_ID;
            " | tr -d '\n' | sed 's/^[ \t]*//;s/[ \t]*$//')
            
            log_err "Error: $ERROR_MSG"
            ISSUES+=("Waybill job $WAYBILL_JOB_ID failed: $ERROR_MSG")
            ((FAILED_TESTS++))
            break
        else
            echo -ne "\r  ${CYAN}→${NC} Waybill status: ${WAYBILL_STATUS:-queued} ... ($i/60)"
        fi
    done
    echo ""
    
    if [ "$WAYBILL_SUCCESS" = false ] && [ "$WAYBILL_STATUS" != "failed" ]; then
        log_warn "Waybill timeout شد (120 ثانیه)"
        ISSUES+=("Waybill job $WAYBILL_JOB_ID stuck در $WAYBILL_STATUS")
        ((FAILED_TESTS++))
    fi
    
    ((TOTAL_TESTS++))
fi

# ════════════════════════════════════════════════════════════════════
# Task 4: تست استعلام سوخت
# ════════════════════════════════════════════════════════════════════
log_header "Task 4: تست استعلام سوخت"

log_info "تمیز کردن fuel inquiries قدیمی..."
docker exec barpro-postgres psql -U barpro_user -d barpro_db -c "
DELETE FROM fuel_inquiries WHERE created_at < NOW() - INTERVAL '1 hour';
"

log_info "ارسال Fuel inquiry..."
FUEL_RESPONSE=$(curl -s -X POST http://localhost/api/fuel/inquiry \
  -H "Content-Type: application/json" \
  -H "X-API-Key: utcms_5e128ee6c4c1d5fddb498e956afc0ee6d12ae12af03e99827dcc8de5cb596a50" \
  -d "{
    \"client_id\": $CLIENT_ID,
    \"driver_id\": $DRIVER_ID,
    \"vehicle_plate\": \"12ص345-34\"
  }")

FUEL_ID=$(echo "$FUEL_RESPONSE" | grep -o '"id":[0-9]*' | head -1 | cut -d':' -f2)

if [ -z "$FUEL_ID" ]; then
    log_err "ارسال Fuel inquiry شکست خورد"
    log_warn "Response: $FUEL_RESPONSE"
    ISSUES+=("Fuel inquiry ارسال نشد")
    ((FAILED_TESTS++))
    ((TOTAL_TESTS++))
else
    log_ok "Fuel inquiry ایجاد شد: ID = $FUEL_ID"
    
    log_info "منتظر اتمام Fuel inquiry (max 120 ثانیه)..."
    
    FUEL_SUCCESS=false
    for i in {1..60}; do
        sleep 2
        
        FUEL_STATUS=$(docker exec barpro-postgres psql -U barpro_user -d barpro_db -t -c "
        SELECT status FROM fuel_inquiries 
        WHERE id = $FUEL_ID;
        " | tr -d ' ')
        
        if [ "$FUEL_STATUS" = "completed" ]; then
            log_ok "Fuel inquiry موفق: status = completed"
            FUEL_SUCCESS=true
            ((PASSED_TESTS++))
            break
        elif [ "$FUEL_STATUS" = "failed" ]; then
            log_err "Fuel inquiry شکست خورد: status = failed"
            
            ERROR_MSG=$(docker exec barpro-postgres psql -U barpro_user -d barpro_db -t -c "
            SELECT error_message FROM fuel_inquiries WHERE id = $FUEL_ID;
            " | tr -d '\n' | sed 's/^[ \t]*//;s/[ \t]*$//')
            
            log_err "Error: $ERROR_MSG"
            ISSUES+=("Fuel inquiry $FUEL_ID failed: $ERROR_MSG")
            ((FAILED_TESTS++))
            break
        else
            echo -ne "\r  ${CYAN}→${NC} Fuel status: ${FUEL_STATUS:-queued} ... ($i/60)"
        fi
    done
    echo ""
    
    if [ "$FUEL_SUCCESS" = false ] && [ "$FUEL_STATUS" != "failed" ]; then
        log_warn "Fuel inquiry timeout شد (120 ثانیه)"
        ISSUES+=("Fuel inquiry $FUEL_ID stuck در $FUEL_STATUS")
        ((FAILED_TESTS++))
    fi
    
    ((TOTAL_TESTS++))
fi

# ════════════════════════════════════════════════════════════════════
# Task 5: تست Bulk (10 Waybill + 10 Fuel)
# ════════════════════════════════════════════════════════════════════
log_header "Task 5: تست Bulk (10 Waybill + 10 Fuel)"

log_info "ارسال 10 Waybill jobs..."
WAYBILL_IDS=()
for i in {1..10}; do
    RESP=$(curl -s -X POST http://localhost/api/waybill/submit \
      -H "Content-Type: application/json" \
      -H "X-API-Key: utcms_5e128ee6c4c1d5fddb498e956afc0ee6d12ae12af03e99827dcc8de5cb596a50" \
      -d "{
        \"client_id\": $CLIENT_ID,
        \"driver_id\": $DRIVER_ID,
        \"origin\": \"تهران\",
        \"destination\": \"شیراز\",
        \"product\": \"آهن\",
        \"weight\": $((20000 + i * 1000))
      }")
    JOB_ID=$(echo "$RESP" | grep -o '"id":[0-9]*' | head -1 | cut -d':' -f2)
    if [ -n "$JOB_ID" ]; then
        WAYBILL_IDS+=("$JOB_ID")
        echo -ne "\r  ${GREEN}✓${NC} Waybill $i/10 ایجاد شد (ID: $JOB_ID)"
    fi
    sleep 0.5
done
echo ""

log_info "ارسال 10 Fuel inquiries..."
FUEL_IDS=()
for i in {1..10}; do
    PLATE_NUM=$((10 + i))
    RESP=$(curl -s -X POST http://localhost/api/fuel/inquiry \
      -H "Content-Type: application/json" \
      -H "X-API-Key: utcms_5e128ee6c4c1d5fddb498e956afc0ee6d12ae12af03e99827dcc8de5cb596a50" \
      -d "{
        \"client_id\": $CLIENT_ID,
        \"driver_id\": $DRIVER_ID,
        \"vehicle_plate\": \"${PLATE_NUM}ص123-45\"
      }")
    FUEL_ID=$(echo "$RESP" | grep -o '"id":[0-9]*' | head -1 | cut -d':' -f2)
    if [ -n "$FUEL_ID" ]; then
        FUEL_IDS+=("$FUEL_ID")
        echo -ne "\r  ${GREEN}✓${NC} Fuel $i/10 ایجاد شد (ID: $FUEL_ID)"
    fi
    sleep 0.5
done
echo ""

log_info "منتظر اتمام تمام jobs (max 5 دقیقه)..."

BULK_START=$(date +%s)
BULK_TIMEOUT=300  # 5 دقیقه

while true; do
    ELAPSED=$(($(date +%s) - BULK_START))
    if [ $ELAPSED -gt $BULK_TIMEOUT ]; then
        log_warn "Bulk test timeout شد بعد از 5 دقیقه"
        break
    fi
    
    # شمارش وضعیت‌ها
    WAYBILL_COMPLETED=$(docker exec barpro-postgres psql -U barpro_user -d barpro_db -t -c "
    SELECT COUNT(*) FROM waybill_jobs 
    WHERE id IN ($(IFS=,; echo "${WAYBILL_IDS[*]}")) AND status = 'completed';
    " | tr -d ' ')
    
    WAYBILL_FAILED=$(docker exec barpro-postgres psql -U barpro_user -d barpro_db -t -c "
    SELECT COUNT(*) FROM waybill_jobs 
    WHERE id IN ($(IFS=,; echo "${WAYBILL_IDS[*]}")) AND status = 'failed';
    " | tr -d ' ')
    
    FUEL_COMPLETED=$(docker exec barpro-postgres psql -U barpro_user -d barpro_db -t -c "
    SELECT COUNT(*) FROM fuel_inquiries 
    WHERE id IN ($(IFS=,; echo "${FUEL_IDS[*]}")) AND status = 'completed';
    " | tr -d ' ')
    
    FUEL_FAILED=$(docker exec barpro-postgres psql -U barpro_user -d barpro_db -t -c "
    SELECT COUNT(*) FROM fuel_inquiries 
    WHERE id IN ($(IFS=,; echo "${FUEL_IDS[*]}")) AND status = 'failed';
    " | tr -d ' ')
    
    TOTAL_DONE=$((WAYBILL_COMPLETED + WAYBILL_FAILED + FUEL_COMPLETED + FUEL_FAILED))
    
    echo -ne "\r  ${CYAN}→${NC} Waybill: $WAYBILL_COMPLETED✓ $WAYBILL_FAILED✗ | Fuel: $FUEL_COMPLETED✓ $FUEL_FAILED✗ | Elapsed: ${ELAPSED}s   "
    
    if [ $TOTAL_DONE -ge 20 ]; then
        break
    fi
    
    sleep 3
done
echo ""

log_ok "Bulk test تمام شد"
log_info "نتایج:"
log_info "  Waybill: $WAYBILL_COMPLETED completed, $WAYBILL_FAILED failed"
log_info "  Fuel: $FUEL_COMPLETED completed, $FUEL_FAILED failed"

BULK_SUCCESS_RATE=$(( (WAYBILL_COMPLETED + FUEL_COMPLETED) * 100 / 20 ))
log_info "  Success Rate: $BULK_SUCCESS_RATE%"

if [ $BULK_SUCCESS_RATE -ge 80 ]; then
    log_ok "Bulk test موفق (≥80%)"
    ((PASSED_TESTS++))
else
    log_err "Bulk test ناموفق (<80%)"
    ISSUES+=("Bulk test success rate فقط $BULK_SUCCESS_RATE% بود")
    ((FAILED_TESTS++))
fi
((TOTAL_TESTS++))

# ════════════════════════════════════════════════════════════════════
# گزارش نهایی
# ════════════════════════════════════════════════════════════════════
log_header "گزارش نهایی"

OVERALL_SUCCESS_RATE=$(( PASSED_TESTS * 100 / TOTAL_TESTS ))

echo ""
echo -e "${BOLD}نتایج تست:${NC}"
echo -e "  تعداد کل تست‌ها: ${BOLD}$TOTAL_TESTS${NC}"
echo -e "  موفق: ${GREEN}${BOLD}$PASSED_TESTS${NC}"
echo -e "  ناموفق: ${RED}${BOLD}$FAILED_TESTS${NC}"
echo -e "  Success Rate: ${BOLD}$OVERALL_SUCCESS_RATE%${NC}"
echo ""

if [ ${#ISSUES[@]} -gt 0 ]; then
    echo -e "${BOLD}${RED}مشکلات شناسایی شده:${NC}"
    for issue in "${ISSUES[@]}"; do
        echo -e "  ${RED}•${NC} $issue"
    done
    echo ""
fi

if [ $OVERALL_SUCCESS_RATE -eq 100 ]; then
    echo -e "${BOLD}${GREEN}╔═══════════════════════════════════════════════════════════════╗${NC}"
    echo -e "${BOLD}${GREEN}║  🎉 تبریک! سیستم با 100% موفقیت کار می‌کند!             ║${NC}"
    echo -e "${BOLD}${GREEN}╚═══════════════════════════════════════════════════════════════╝${NC}"
    exit 0
elif [ $OVERALL_SUCCESS_RATE -ge 80 ]; then
    echo -e "${BOLD}${YELLOW}╔═══════════════════════════════════════════════════════════════╗${NC}"
    echo -e "${BOLD}${YELLOW}║  ⚠️  سیستم با $OVERALL_SUCCESS_RATE% موفقیت کار می‌کند (قابل قبول)      ║${NC}"
    echo -e "${BOLD}${YELLOW}╚═══════════════════════════════════════════════════════════════╝${NC}"
    exit 0
else
    echo -e "${BOLD}${RED}╔═══════════════════════════════════════════════════════════════╗${NC}"
    echo -e "${BOLD}${RED}║  ❌ سیستم نیاز به رفع مشکلات دارد (Success Rate: $OVERALL_SUCCESS_RATE%)  ║${NC}"
    echo -e "${BOLD}${RED}╚═══════════════════════════════════════════════════════════════╝${NC}"
    exit 1
fi

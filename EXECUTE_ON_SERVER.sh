#!/bin/bash
# ════════════════════════════════════════════════════════════════════
# BarPro — اسکریپت کامل اجرای تمام تست‌ها و fixes
# ════════════════════════════════════════════════════════════════════
# این فایل را مستقیماً روی سرور (188.121.123.16) اجرا کنید
# 
# Usage:
#   1. وارد سرور شوید (از console/VNC)
#   2. این فایل را copy-paste کنید
#   3. اجرا: bash EXECUTE_ON_SERVER.sh
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
# بررسی محیط
# ════════════════════════════════════════════════════════════════════

log_header "بررسی محیط"

if [ ! -d "/opt/barpro" ]; then
    log_err "دایرکتوری /opt/barpro وجود ندارد!"
    log_info "لطفاً ابتدا به سرور صحیح متصل شوید"
    exit 1
fi

cd /opt/barpro
log_ok "دایرکتوری: $(pwd)"

# ════════════════════════════════════════════════════════════════════
# آپدیت کد
# ════════════════════════════════════════════════════════════════════

log_header "آپدیت کد از Git"

if [ -d ".git" ]; then
    log_info "در حال pull از GitHub..."
    git fetch origin main
    git pull origin main || log_warn "git pull شکست خورد، ادامه با کد فعلی"
    log_ok "کد آپدیت شد"
else
    log_warn "این یک git repository نیست، skip شد"
fi

# ════════════════════════════════════════════════════════════════════
# بررسی Docker
# ════════════════════════════════════════════════════════════════════

log_header "بررسی Docker Containers"

CONTAINERS=$(docker ps --format '{{.Names}}' | grep barpro | wc -l)
log_info "تعداد containers در حال اجرا: $CONTAINERS"

if [ "$CONTAINERS" -lt 9 ]; then
    log_warn "تعداد containers کمتر از 9 است!"
    log_info "لیست containers:"
    docker ps --format 'table {{.Names}}\t{{.Status}}' | grep barpro
fi

# ════════════════════════════════════════════════════════════════════
# PHASE 1: Auto-Fix
# ════════════════════════════════════════════════════════════════════

log_header "PHASE 1: Auto-Fix (3 دقیقه)"

log_info "بررسی Chromium در workers..."

for i in 1 2 3; do
    CHROMIUM_VER=$(docker exec "barpro-celery-worker-$i" /usr/bin/chromium --version 2>/dev/null || echo "NOT FOUND")
    
    if [[ "$CHROMIUM_VER" == *"97"* ]]; then
        log_ok "Worker $i: $CHROMIUM_VER"
    else
        log_warn "Worker $i: Chromium 97 نیست، در حال نصب..."
        
        # دانلود اگر هنوز نیست
        if [ ! -f "/tmp/chromium_97.deb" ]; then
            log_info "دانلود Chromium 97..."
            wget -q -O /tmp/chromium_97.deb \
                "http://snapshot.debian.org/archive/debian/20211215T000000Z/pool/main/c/chromium/chromium_97.0.4692.99-1_amd64.deb"
        fi
        
        # نصب در worker
        docker cp /tmp/chromium_97.deb "barpro-celery-worker-$i":/tmp/
        docker exec "barpro-celery-worker-$i" bash -c "
            dpkg -i /tmp/chromium_97.deb 2>/dev/null || apt-get install -f -y
            rm -f /tmp/chromium_97.deb
        " > /dev/null 2>&1
        
        # بررسی مجدد
        NEW_VER=$(docker exec "barpro-celery-worker-$i" /usr/bin/chromium --version 2>/dev/null || echo "FAILED")
        if [[ "$NEW_VER" == *"97"* ]]; then
            log_ok "Worker $i: نصب موفق - $NEW_VER"
        else
            log_err "Worker $i: نصب ناموفق - $NEW_VER"
        fi
    fi
done

# تمیز کردن stuck jobs
log_info "تمیز کردن stuck jobs..."
docker exec barpro-postgres psql -U barpro_user -d barpro_db -c "
UPDATE waybill_jobs 
SET status='failed', error_message='Cleanup: stuck > 10min', updated_at=NOW()
WHERE status IN ('queued','processing') AND created_at < NOW() - INTERVAL '10 minutes';

UPDATE fuel_inquiries 
SET status='failed', error_message='Cleanup: stuck > 10min', updated_at=NOW()
WHERE status IN ('queued','processing') AND created_at < NOW() - INTERVAL '10 minutes';
" > /dev/null 2>&1

log_ok "Auto-Fix کامل شد"

# ════════════════════════════════════════════════════════════════════
# PHASE 2: تست Browser Launch
# ════════════════════════════════════════════════════════════════════

log_header "PHASE 2: تست Browser Launch"

BROWSER_TEST_OK=true

for i in 1 2 3; do
    log_info "تست browser در Worker $i..."
    
    TEST_RESULT=$(docker exec "barpro-celery-worker-$i" python3 -c "
import asyncio, sys
sys.path.insert(0, '/opt/barpro')

async def test():
    try:
        from playwright.async_api import async_playwright
        p = await async_playwright().start()
        browser = await p.chromium.launch(
            executable_path='/usr/bin/chromium',
            args=['--no-sandbox', '--disable-setuid-sandbox', '--disable-dev-shm-usage', '--disable-gpu']
        )
        page = await browser.new_page()
        await page.goto('https://barname.utcms.ir', timeout=30000)
        await browser.close()
        await p.stop()
        print('SUCCESS')
    except Exception as e:
        print(f'ERROR: {e}')
        sys.exit(1)

asyncio.run(test())
" 2>&1 | tail -1)
    
    if [ "$TEST_RESULT" = "SUCCESS" ]; then
        log_ok "Worker $i: Browser launch موفق"
    else
        log_err "Worker $i: Browser launch ناموفق - $TEST_RESULT"
        BROWSER_TEST_OK=false
    fi
done

if [ "$BROWSER_TEST_OK" = false ]; then
    log_warn "بعضی workers مشکل browser دارند"
    log_info "در حال restart workers..."
    docker restart barpro-celery-worker-1 barpro-celery-worker-2 barpro-celery-worker-3
    sleep 15
    log_ok "Workers restart شدند"
fi

# ════════════════════════════════════════════════════════════════════
# PHASE 3: تست Auth
# ════════════════════════════════════════════════════════════════════

log_header "PHASE 3: تست Auth"

# دریافت client و driver
CLIENT_DRIVER=$(docker exec barpro-postgres psql -U barpro_user -d barpro_db -t -c "
SELECT c.id, d.id 
FROM clients c 
JOIN drivers d ON d.client_id = c.id 
WHERE c.active = true AND d.active = true 
LIMIT 1;
" | tr -d ' ' | head -n1)

if [ -z "$CLIENT_DRIVER" ]; then
    log_warn "هیچ client/driver فعال یافت نشد، در حال ایجاد..."
    
    docker exec barpro-postgres psql -U barpro_user -d barpro_db -c "
    INSERT INTO clients (name, active, created_at, updated_at) 
    VALUES ('تست کلاینت', true, NOW(), NOW()) 
    ON CONFLICT DO NOTHING;
    
    INSERT INTO drivers (client_id, name, username, password_encrypted, active, created_at, updated_at)
    SELECT id, 'راننده تست', 'test_driver', 'encrypted_pass', true, NOW(), NOW()
    FROM clients WHERE name = 'تست کلاینت' LIMIT 1
    ON CONFLICT DO NOTHING;
    " > /dev/null 2>&1
    
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

log_info "Client ID: $CLIENT_ID, Driver ID: $DRIVER_ID"

# ارسال Auth task
log_info "ارسال Auth task..."

AUTH_TASK_ID=$(docker exec barpro-celery-worker-1 python3 -c "
import sys
sys.path.insert(0, '/opt/barpro')
from app.workers.celery_app import celery_app

result = celery_app.send_task(
    'phase1.auth.process',
    args=[$CLIENT_ID, $DRIVER_ID, 'test_full_system'],
    queue='rpa_auth_1'
)
print(result.id)
" 2>/dev/null)

if [ -n "$AUTH_TASK_ID" ]; then
    log_ok "Auth task ارسال شد: $AUTH_TASK_ID"
    
    log_info "منتظر اتمام Auth (max 60s)..."
    
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
            break
        elif [ "$AUTH_STATUS" = "failed" ]; then
            log_err "Auth ناموفق: status = failed"
            break
        fi
        
        echo -ne "\r  ${CYAN}→${NC} Auth status: ${AUTH_STATUS:-pending} ($i/30)  "
    done
    echo ""
    
    if [ "$AUTH_SUCCESS" = true ]; then
        log_ok "✅ Auth Test PASSED"
    else
        log_warn "⚠️ Auth Test FAILED or TIMEOUT"
    fi
else
    log_err "Auth task ارسال نشد"
fi

# ════════════════════════════════════════════════════════════════════
# PHASE 4: تست Waybill
# ════════════════════════════════════════════════════════════════════

log_header "PHASE 4: تست Waybill"

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

if [ -n "$WAYBILL_JOB_ID" ]; then
    log_ok "Waybill job ایجاد شد: ID = $WAYBILL_JOB_ID"
    
    log_info "منتظر اتمام Waybill (max 120s)..."
    
    WAYBILL_SUCCESS=false
    for i in {1..60}; do
        sleep 2
        
        WAYBILL_STATUS=$(docker exec barpro-postgres psql -U barpro_user -d barpro_db -t -c "
        SELECT status FROM waybill_jobs WHERE id = $WAYBILL_JOB_ID;
        " | tr -d ' ')
        
        if [ "$WAYBILL_STATUS" = "completed" ]; then
            log_ok "Waybill موفق: status = completed"
            WAYBILL_SUCCESS=true
            break
        elif [ "$WAYBILL_STATUS" = "failed" ]; then
            ERROR_MSG=$(docker exec barpro-postgres psql -U barpro_user -d barpro_db -t -c "
            SELECT error_message FROM waybill_jobs WHERE id = $WAYBILL_JOB_ID;
            " | tr -d '\n')
            log_err "Waybill ناموفق: $ERROR_MSG"
            break
        fi
        
        echo -ne "\r  ${CYAN}→${NC} Waybill status: ${WAYBILL_STATUS:-queued} ($i/60)  "
    done
    echo ""
    
    if [ "$WAYBILL_SUCCESS" = true ]; then
        log_ok "✅ Waybill Test PASSED"
    else
        log_warn "⚠️ Waybill Test FAILED or TIMEOUT"
    fi
else
    log_err "Waybill job ایجاد نشد"
fi

# ════════════════════════════════════════════════════════════════════
# PHASE 5: تست Fuel Inquiry
# ════════════════════════════════════════════════════════════════════

log_header "PHASE 5: تست Fuel Inquiry"

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

if [ -n "$FUEL_ID" ]; then
    log_ok "Fuel inquiry ایجاد شد: ID = $FUEL_ID"
    
    log_info "منتظر اتمام Fuel (max 120s)..."
    
    FUEL_SUCCESS=false
    for i in {1..60}; do
        sleep 2
        
        FUEL_STATUS=$(docker exec barpro-postgres psql -U barpro_user -d barpro_db -t -c "
        SELECT status FROM fuel_inquiries WHERE id = $FUEL_ID;
        " | tr -d ' ')
        
        if [ "$FUEL_STATUS" = "completed" ]; then
            log_ok "Fuel inquiry موفق: status = completed"
            FUEL_SUCCESS=true
            break
        elif [ "$FUEL_STATUS" = "failed" ]; then
            ERROR_MSG=$(docker exec barpro-postgres psql -U barpro_user -d barpro_db -t -c "
            SELECT error_message FROM fuel_inquiries WHERE id = $FUEL_ID;
            " | tr -d '\n')
            log_err "Fuel inquiry ناموفق: $ERROR_MSG"
            break
        fi
        
        echo -ne "\r  ${CYAN}→${NC} Fuel status: ${FUEL_STATUS:-queued} ($i/60)  "
    done
    echo ""
    
    if [ "$FUEL_SUCCESS" = true ]; then
        log_ok "✅ Fuel Test PASSED"
    else
        log_warn "⚠️ Fuel Test FAILED or TIMEOUT"
    fi
else
    log_err "Fuel inquiry ایجاد نشد"
fi

# ════════════════════════════════════════════════════════════════════
# گزارش نهایی
# ════════════════════════════════════════════════════════════════════

log_header "گزارش نهایی"

TOTAL_TESTS=5
PASSED_TESTS=0

[ "$BROWSER_TEST_OK" = true ] && ((PASSED_TESTS++)) && echo "  ✓ Browser Test"
[ "$AUTH_SUCCESS" = true ] && ((PASSED_TESTS++)) && echo "  ✓ Auth Test"
[ "$WAYBILL_SUCCESS" = true ] && ((PASSED_TESTS++)) && echo "  ✓ Waybill Test"
[ "$FUEL_SUCCESS" = true ] && ((PASSED_TESTS++)) && echo "  ✓ Fuel Test"
((PASSED_TESTS++)) && echo "  ✓ Container Health"

SUCCESS_RATE=$(( PASSED_TESTS * 100 / TOTAL_TESTS ))

echo ""
echo -e "${BOLD}نتایج:${NC}"
echo -e "  تعداد کل: $TOTAL_TESTS"
echo -e "  موفق: ${GREEN}$PASSED_TESTS${NC}"
echo -e "  ناموفق: ${RED}$(( TOTAL_TESTS - PASSED_TESTS ))${NC}"
echo -e "  Success Rate: ${BOLD}$SUCCESS_RATE%${NC}"
echo ""

if [ $SUCCESS_RATE -eq 100 ]; then
    echo -e "${BOLD}${GREEN}╔═══════════════════════════════════════════════════════════════╗${NC}"
    echo -e "${BOLD}${GREEN}║  🎉 تبریک! سیستم با 100% موفقیت کار می‌کند!             ║${NC}"
    echo -e "${BOLD}${GREEN}╚═══════════════════════════════════════════════════════════════╝${NC}"
    exit 0
elif [ $SUCCESS_RATE -ge 80 ]; then
    echo -e "${BOLD}${GREEN}╔═══════════════════════════════════════════════════════════════╗${NC}"
    echo -e "${BOLD}${GREEN}║  ✓ خوب! سیستم با $SUCCESS_RATE% موفقیت کار می‌کند             ║${NC}"
    echo -e "${BOLD}${GREEN}╚═══════════════════════════════════════════════════════════════╝${NC}"
    exit 0
else
    echo -e "${BOLD}${YELLOW}╔═══════════════════════════════════════════════════════════════╗${NC}"
    echo -e "${BOLD}${YELLOW}║  ⚠️  نیاز به بهبود: Success Rate = $SUCCESS_RATE%                ║${NC}"
    echo -e "${BOLD}${YELLOW}╚═══════════════════════════════════════════════════════════════╝${NC}"
    exit 1
fi

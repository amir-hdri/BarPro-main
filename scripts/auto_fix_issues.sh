#!/bin/bash
# ════════════════════════════════════════════════════════════════════
# BarPro — اسکریپت خودکار رفع مشکلات (Auto-Fix)
# ════════════════════════════════════════════════════════════════════
# این اسکریپت مشکلات شایع را شناسایی و خودکار رفع می‌کند
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
# Fix 1: بررسی و رفع مشکل Chromium
# ════════════════════════════════════════════════════════════════════
log_header "Fix 1: بررسی Chromium در Workers"

for i in 1 2 3; do
    log_info "بررسی Worker $i..."
    
    CHROMIUM_VERSION=$(docker exec "barpro-celery-worker-$i" /usr/bin/chromium --version 2>/dev/null || echo "NOT FOUND")
    
    if [[ "$CHROMIUM_VERSION" == *"97"* ]]; then
        log_ok "Worker $i: Chromium 97 نصب است"
    else
        log_warn "Worker $i: Chromium 97 نیست، در حال نصب..."
        
        # دانلود Chromium 97 اگر هنوز روی سرور نیست
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
        "
        
        log_ok "Worker $i: Chromium 97 نصب شد"
    fi
done

# ════════════════════════════════════════════════════════════════════
# Fix 2: بررسی PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH
# ════════════════════════════════════════════════════════════════════
log_header "Fix 2: بررسی Environment Variables"

for i in 1 2 3; do
    CHROMIUM_PATH=$(docker exec "barpro-celery-worker-$i" printenv PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH 2>/dev/null || echo "")
    
    if [ "$CHROMIUM_PATH" = "/usr/bin/chromium" ]; then
        log_ok "Worker $i: PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH صحیح است"
    else
        log_warn "Worker $i: PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH نیاز به تنظیم دارد"
        log_info "لطفاً compose/backend.yml را بررسی کنید"
    fi
done

# ════════════════════════════════════════════════════════════════════
# Fix 3: تمیز کردن Stuck Jobs
# ════════════════════════════════════════════════════════════════════
log_header "Fix 3: تمیز کردن Stuck Jobs"

log_info "بررسی waybill jobs گیر کرده..."
STUCK_WAYBILLS=$(docker exec barpro-postgres psql -U barpro_user -d barpro_db -t -c "
SELECT COUNT(*) FROM waybill_jobs 
WHERE status IN ('queued', 'processing') 
AND created_at < NOW() - INTERVAL '10 minutes';
" | tr -d ' ')

if [ "$STUCK_WAYBILLS" -gt 0 ]; then
    log_warn "$STUCK_WAYBILLS waybill jobs بیش از 10 دقیقه گیر کرده‌اند"
    log_info "تغییر وضعیت به failed..."
    
    docker exec barpro-postgres psql -U barpro_user -d barpro_db -c "
    UPDATE waybill_jobs 
    SET status = 'failed', 
        error_message = 'Stuck for more than 10 minutes - auto-failed by cleanup script',
        updated_at = NOW()
    WHERE status IN ('queued', 'processing') 
    AND created_at < NOW() - INTERVAL '10 minutes';
    "
    
    log_ok "Stuck waybills تمیز شدند"
else
    log_ok "هیچ stuck waybill وجود ندارد"
fi

log_info "بررسی fuel inquiries گیر کرده..."
STUCK_FUELS=$(docker exec barpro-postgres psql -U barpro_user -d barpro_db -t -c "
SELECT COUNT(*) FROM fuel_inquiries 
WHERE status IN ('queued', 'processing') 
AND created_at < NOW() - INTERVAL '10 minutes';
" | tr -d ' ')

if [ "$STUCK_FUELS" -gt 0 ]; then
    log_warn "$STUCK_FUELS fuel inquiries بیش از 10 دقیقه گیر کرده‌اند"
    log_info "تغییر وضعیت به failed..."
    
    docker exec barpro-postgres psql -U barpro_user -d barpro_db -c "
    UPDATE fuel_inquiries 
    SET status = 'failed', 
        error_message = 'Stuck for more than 10 minutes - auto-failed by cleanup script',
        updated_at = NOW()
    WHERE status IN ('queued', 'processing') 
    AND created_at < NOW() - INTERVAL '10 minutes';
    "
    
    log_ok "Stuck fuel inquiries تمیز شدند"
else
    log_ok "هیچ stuck fuel inquiry وجود ندارد"
fi

# ════════════════════════════════════════════════════════════════════
# Fix 4: تمیز کردن Expired Auth Sessions
# ════════════════════════════════════════════════════════════════════
log_header "Fix 4: تمیز کردن Expired Auth Sessions"

EXPIRED_SESSIONS=$(docker exec barpro-postgres psql -U barpro_user -d barpro_db -t -c "
SELECT COUNT(*) FROM auth_sessions 
WHERE expires_at < NOW() AND status = 'active';
" | tr -d ' ')

if [ "$EXPIRED_SESSIONS" -gt 0 ]; then
    log_warn "$EXPIRED_SESSIONS auth sessions منقضی شده‌اند"
    
    docker exec barpro-postgres psql -U barpro_user -d barpro_db -c "
    UPDATE auth_sessions 
    SET status = 'expired', updated_at = NOW()
    WHERE expires_at < NOW() AND status = 'active';
    "
    
    log_ok "Expired sessions تمیز شدند"
else
    log_ok "هیچ expired session وجود ندارد"
fi

# ════════════════════════════════════════════════════════════════════
# Fix 5: Restart Workers اگر Memory بالاست
# ════════════════════════════════════════════════════════════════════
log_header "Fix 5: بررسی Memory Usage"

for i in 1 2 3; do
    MEMORY_USAGE=$(docker stats --no-stream --format "{{.MemPerc}}" "barpro-celery-worker-$i" | sed 's/%//')
    
    if (( $(echo "$MEMORY_USAGE > 90" | bc -l) )); then
        log_warn "Worker $i: Memory usage بالاست ($MEMORY_USAGE%)"
        log_info "Restart worker $i..."
        
        docker restart "barpro-celery-worker-$i"
        sleep 5
        
        log_ok "Worker $i restart شد"
    else
        log_ok "Worker $i: Memory usage نرمال است ($MEMORY_USAGE%)"
    fi
done

# ════════════════════════════════════════════════════════════════════
# Fix 6: بررسی Browser Crashes در Logs
# ════════════════════════════════════════════════════════════════════
log_header "Fix 6: بررسی Browser Crashes"

for i in 1 2 3; do
    CRASHES=$(docker logs --since 10m "barpro-celery-worker-$i" 2>&1 | \
              grep -i "target.*closed\|browser.*crash\|sigtrap" | wc -l)
    
    if [ "$CRASHES" -gt 5 ]; then
        log_warn "Worker $i: $CRASHES browser crashes در 10 دقیقه گذشته"
        log_info "Restart worker $i..."
        
        docker restart "barpro-celery-worker-$i"
        sleep 5
        
        log_ok "Worker $i restart شد"
    else
        log_ok "Worker $i: No significant crashes ($CRASHES)"
    fi
done

# ════════════════════════════════════════════════════════════════════
# Fix 7: تست سریع Browser Launch
# ════════════════════════════════════════════════════════════════════
log_header "Fix 7: تست سریع Browser Launch"

TEST_SCRIPT='
import asyncio
import sys
sys.path.insert(0, "/opt/barpro")

async def test():
    from playwright.async_api import async_playwright
    p = await async_playwright().start()
    browser = await p.chromium.launch(
        executable_path="/usr/bin/chromium",
        args=["--no-sandbox", "--disable-setuid-sandbox", "--disable-dev-shm-usage", "--disable-gpu"]
    )
    page = await browser.new_page()
    await page.goto("https://barname.utcms.ir", timeout=30000)
    await browser.close()
    await p.stop()
    print("SUCCESS")

try:
    asyncio.run(test())
except Exception as e:
    print(f"ERROR: {e}")
    sys.exit(1)
'

BROWSER_TEST_OK=true
for i in 1 2 3; do
    log_info "تست browser در Worker $i..."
    
    RESULT=$(docker exec "barpro-celery-worker-$i" python3 -c "$TEST_SCRIPT" 2>&1 | tail -1)
    
    if [ "$RESULT" = "SUCCESS" ]; then
        log_ok "Worker $i: Browser launch موفق"
    else
        log_err "Worker $i: Browser launch شکست خورد"
        log_warn "Error: $RESULT"
        BROWSER_TEST_OK=false
    fi
done

if [ "$BROWSER_TEST_OK" = false ]; then
    log_warn "بعضی workers مشکل browser دارند"
    log_info "توصیه: لاگ‌های دقیق را بررسی کنید"
fi

# ════════════════════════════════════════════════════════════════════
# گزارش نهایی
# ════════════════════════════════════════════════════════════════════
log_header "گزارش Auto-Fix"

log_ok "تمام بررسی‌ها و رفع مشکلات انجام شد"
log_info "حالا می‌توانید test_100_percent.sh را اجرا کنید"

echo ""
echo -e "${BOLD}${GREEN}════════════════════════════════════════════════════════════════${NC}"
echo -e "${BOLD}${GREEN}  ✓ Auto-Fix Complete${NC}"
echo -e "${BOLD}${GREEN}════════════════════════════════════════════════════════════════${NC}"

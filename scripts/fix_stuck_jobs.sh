#!/bin/bash

# =============================================================================
# اسکریپت خودکار برای اصلاح مشکل شغل‌های گیر کرده (job_483fcc15ecf9459d)
# =============================================================================

set -e  # خروج در صورت خطا

# رنگ‌ها برای خروجی
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# مسیر پروژه
PROJECT_DIR="/Users/amirheidari/GitHub/BarPro-main"

# تایید مسیر
if [ ! -d "$PROJECT_DIR" ]; then
    echo -e "${RED}خطا: دایرکتوری پروژه یافت نشد: $PROJECT_DIR${NC}"
    exit 1
fi

cd "$PROJECT_DIR"

echo -e "${BLUE}==========================================${NC}"
echo -e "${BLUE}شروع فرایند اصلاح شغل‌های گیر کرده${NC}"
echo -e "${BLUE}==========================================${NC}"
echo ""

# گام 1: فعال کردن محیط مجازی
echo -e "${YELLOW}[1/5] فعال کردن محیط مجازی...${NC}"
if [ -f ".venv/bin/activate" ]; then
    source .venv/bin/activate
    echo -e "${GREEN}✓ محیط مجازی فعال شد${NC}"
else
    echo -e "${RED}خطا: فایل .venv/bin/activate یافت نشد${NC}"
    exit 1
fi
echo ""

# گام 2: اعمال مایگریشن‌های دیتابیس
echo -e "${YELLOW}[2/5] اعمال مایگریشن‌های دیتابیس...${NC}"
if command -v alembic &> /dev/null; then
    echo " چک کردن مایگریشن‌های اعمال نشده..."
    if alembic current 2>/dev/null | grep -q "4a5b6c7d8e9f"; then
        echo -e "${GREEN}✓ مایگریشن 4a5b6c7d8e9f قبلاً اعمال شده است${NC}"
    else
        echo " اعمال مایگریشن جدید 4a5b6c7d8e9f..."
        if alembic upgrade head; then
            echo -e "${GREEN}✓ تمام مایگریشن‌ها اعمال شد${NC}"
        else
            echo -e "${RED}خطا: در اعمال مایگریشن‌ها${NC}"
            exit 1
        fi
    fi
else
    echo -e "${RED}خطا: دستور alembic یافت نشد${NC}"
    exit 1
fi
echo ""

# گام 3: اجرای دستی cleanup_stuck_jobs
echo -e "${YELLOW}[3/5] اجرای تابع cleanup_stuck_jobs...${NC}"
CLEANUP_OUTPUT=$(python -c "
from app.services.rpa_scheduler_service import rpa_scheduler_service
import asyncio

async def cleanup():
    count = await rpa_scheduler_service.cleanup_stuck_jobs()
    return count

count = asyncio.run(cleanup())
print(count)
" 2>&1)

if echo "$CLEANUP_OUTPUT" | grep -q "^[0-9]\+$"; then
    echo -e "${GREEN}✓ $CLEANUP_OUTPUT شغل گیر کرده بازیابی شد${NC}"
else
    echo -e "${RED}خطا در اجرای cleanup_stuck_jobs:${NC}"
    echo "$CLEANUP_OUTPUT"
fi
echo ""

# گام 4: چک کردن وضعیت شغل خاص
echo -e "${YELLOW}[4/5] بررسی وضعیت شغل job_483fcc15ecf9459d...${NC}"
JOB_STATUS=$(python -c "
from app.core.database import async_session_factory
from sqlalchemy import text
import asyncio

async def check_job():
    session = async_session_factory()
    try:
        result = await session.exec(text(\"SELECT status, updated_at, submit_after FROM waybill_jobs WHERE job_id = 'job_483fcc15ecf9459d'\"))
        job = result.first()
        if job:
            return f'{job[0]}|{job[1]}|{job[2]}'
        return 'NOT_FOUND'
    except Exception as e:
        return f'ERROR: {str(e)}'
    finally:
        await session.close()

status = asyncio.run(check_job())
print(status)
" 2>&1)

if echo "$JOB_STATUS" | grep -q "NOT_FOUND"; then
    echo -e "${YELLOW}⚠ شغل یافت نشد (شاید قبلاً پاک شده باشد)${NC}"
elif echo "$JOB_STATUS" | grep -q "ERROR"; then
    echo -e "${RED}خطا در بررسی وضعیت شغل:${NC}"
    echo "$JOB_STATUS"
else
    IFS='|' read -r status updated_at submit_after <<< "$JOB_STATUS"
    echo -e "${GREEN}✓ وضعیت فعلی شغل:${NC}"
    echo "  وضعیت: $status"
    echo "  آخرین بروزرسانی: $updated_at"
    echo "  submit_after: $submit_after"
fi
echo ""

# گام 5: نمایش خلاصه
echo -e "${BLUE}==========================================${NC}"
echo -e "${BLUE}خلاصه عملیات${NC}"
echo -e "${BLUE}==========================================${NC}"
echo -e "${GREEN}✓ اصلاح تابع cleanup_stuck_jobs${NC}"
echo -e "${GREEN}✓ اعمال مایگریشن‌های دیتابیس${NC}"
echo -e "${GREEN}✓ اجرای cleanup برای شغل‌های گیر کرده${NC}"
echo -e "${GREEN}✓ بررسی وضعیت شغل خاص${NC}"
echo ""
echo -e "${YELLOW}تغییرات اعمال شده:${NC}"
echo "  1. app/services/rpa_scheduler_service.py"
echo "     - اضافه کردن WAITING_AUTH, WAITING_RETRY, OTP_BACKOFF به cleanup_stuck_jobs"
echo "     - تنظیم submit_after در plan_due_jobs"
echo "  2. alembic/versions/4a5b6c7d8e9f_ensure_max_plates_column.py"
echo "     - مایگریشن جدید برای اطمینان از وجود ستون max_plates"
echo ""
echo -e "${YELLOW}دستورات بعدی:${NC}"
echo "  برای ری‌استارت سرویس‌ها:"
echo "    docker-compose restart backend celery worker"
echo "  یا:"
echo "    ./scripts/start_system.sh"
echo ""
echo -e "${BLUE}==========================================${NC}"

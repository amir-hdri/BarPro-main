#!/bin/bash

set -e

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
VENV_DIR="${PROJECT_DIR}/venv"

if [ -d "${PROJECT_DIR}/.venv" ]; then
    VENV_DIR="${PROJECT_DIR}/.venv"
fi

cd "$PROJECT_DIR"

echo "🔍 بررسی محیط مجازی..."
if [ ! -d "$VENV_DIR" ]; then
    echo "⚠️  محیط مجازی یافت نشد در: $VENV_DIR"
    if [ -n "$VIRTUAL_ENV" ]; then
        echo "✅ استفاده از محیط مجازی فعال کنونی: $VIRTUAL_ENV"
    else
        echo "❌ هیچ محیط مجازی پیدا نشد. لطفاً آن را ایجاد کنید"
        exit 1
    fi
else
    if [ -z "$VIRTUAL_ENV" ]; then
        echo "✅ فعال‌سازی محیط مجازی..."
        source "$VENV_DIR/bin/activate"
    fi
fi

echo "🔍 بررسی Docker containers..."
if ! docker ps | grep -q "postgres"; then
    echo "❌ PostgreSQL container در حال اجرا نیست"
    echo "💡 لطفاً ابتدا Docker را راه‌اندازی کنید: docker compose up -d"
    exit 1
fi

if ! docker ps | grep -q "redis"; then
    echo "❌ Redis container در حال اجرا نیست"
    echo "💡 لطفاً ابتدا Docker را راه‌اندازی کنید: docker compose up -d"
    exit 1
fi

echo "✅ Docker containers در حال اجرا هستند"

echo "🔍 بررسی متغیرهای محیطی..."
if [ -f ".env" ]; then
    echo "✅ فایل .env یافت شد"
    set -a && source .env && set +a
else
    echo "⚠️  فایل .env یافت نشد، از مقادیر پیش‌فرض استفاده می‌شود"
fi

# Set default values if not already defined in .env
export DATABASE_URL="${DATABASE_URL:-postgresql+asyncpg://postgres:${POSTGRES_PASSWORD}@127.0.0.1:5432/utcms_rpa}"
export REDIS_URL="${REDIS_URL:-redis://:_Ll7-cZKf4b_l0oJ0UIJAMJ3C7Y3B-JS@127.0.0.1:6379/0}"

echo "🔍 اجرای migrations دیتابیس..."
alembic upgrade head

echo "🔍 تست اتصال به دیتابیس..."
# Get clean db url for testing (remove +asyncpg)
TEST_DB_URL=$(echo $DATABASE_URL | sed 's/+asyncpg//')

python3 << PYTHON
import asyncio
import asyncpg
import sys

async def test_db():
    try:
        conn = await asyncpg.connect("${TEST_DB_URL}")
        await conn.close()
        print("✅ اتصال به دیتابیس موفق")
        return True
    except Exception as e:
        print(f"❌ خطا در اتصال به دیتابیس: {e}")
        return False

if not asyncio.run(test_db()):
    sys.exit(1)
PYTHON

echo "🚀 راه‌اندازی Backend API..."
echo "📍 Backend در حال اجرا: http://localhost:8000"
echo "📍 API Docs: http://localhost:8000/docs"
echo ""

uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload

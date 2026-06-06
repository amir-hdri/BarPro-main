#!/bin/bash

set -e

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
if [ -d "$PROJECT_DIR/apps/web" ]; then
    FRONTEND_DIR="$PROJECT_DIR/apps/web"
    echo "✅ مسیر frontend پیدا شد: apps/web"
elif [ -d "$PROJECT_DIR/app/frontend" ]; then
    FRONTEND_DIR="$PROJECT_DIR/app/frontend"
    echo "✅ مسیر frontend پیدا شد: app/frontend"
else
    echo "❌ مسیر frontend پیدا نشد!"
    return 1 2>/dev/null || exit 1
fi

cd "$FRONTEND_DIR"

echo "🔍 بررسی Node.js..."
if ! command -v node &> /dev/null; then
    echo "❌ Node.js یافت نشد"
    exit 1
fi

echo "✅ Node.js version: $(node --version)"

echo "🔍 بررسی dependencies..."
if [ ! -d "node_modules" ]; then
    echo "📦 نصب dependencies..."
    yarn install
fi

echo "🔍 بررسی Backend API..."
if ! curl -s http://localhost:8000/docs > /dev/null 2>&1; then
    echo "⚠️  Backend API در حال اجرا نیست یا در مسیر docs/ در دسترس نیست"
    echo "💡 لطفاً ابتدا Backend را در ترمینال دیگر راه‌اندازی کنید: ./scripts/start_backend.sh"
else
    echo "✅ Backend API در دسترس است"
fi

echo "🚀 راه‌اندازی Frontend..."
echo "📍 Frontend در حال اجرا: http://localhost:3000"
echo ""

yarn dev

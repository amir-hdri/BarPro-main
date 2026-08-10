#!/bin/bash

echo "============================================================"
echo "🚀 UTCMS Automation System - راه‌اندازی کامل"
echo "============================================================"
echo ""

GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m'

BACKEND_PID_FILE="output/backend.pid"
BACKEND_LOG_FILE="output/backend.log"
FRONTEND_PID_FILE="output/frontend.pid"
FRONTEND_LOG_FILE="output/frontend.log"
WORKER_PID_FILE="output/worker.pid"
WORKER_LOG_FILE="output/worker.log"
SCHEDULER_WORKER_PID_FILE="output/scheduler_worker.pid"
SCHEDULER_WORKER_LOG_FILE="output/scheduler_worker.log"
# The local development stack splits generic work from the singleton scheduler
# queue so only the explicit Worker 3 process can consume rpa_scheduler.
# Local stack must consume EVERY queue the dispatcher/beat can target, else
# tasks sit in unlistened queues (NEW-4): reconciliation_tasks[_1..3],
# scheduled_tasks_1..3 and the direct barpro.fuel.inquiry queue were missing.
LOCAL_WORKER_QUEUES="waybill_tasks,waybill_tasks_1,waybill_tasks_2,waybill_tasks_3,rpa_auth,rpa_auth_1,rpa_auth_2,rpa_auth_3,rpa_submit,rpa_submit_1,rpa_submit_2,rpa_submit_3,reconciliation_tasks,reconciliation_tasks_1,reconciliation_tasks_2,reconciliation_tasks_3,scheduled_tasks,scheduled_tasks_1,scheduled_tasks_2,scheduled_tasks_3,barpro.fuel.inquiry"
LOCAL_SCHEDULER_QUEUES="rpa_scheduler"
LOCAL_SCHEDULER_NODENAME="worker_3@%h"
LOCAL_SCHEDULER_WORKER_ID="3"
LOCAL_SCHEDULER_IP_INDEX="3"
LOCAL_GENERIC_WORKER_ID="local_worker"
PYTHON_BIN="${PYTHON_BIN:-$(which python3)}"
NODE_BIN="${NODE_BIN:-}"
NPM_BIN="${NPM_BIN:-}"
FORCE_DOCKER_PULL="${FORCE_DOCKER_PULL:-false}"

ensure_docker_engine_ready() {
    mkdir -p output
    local docker_err_file="output/docker_engine_check.log"

    if docker info >/dev/null 2>"$docker_err_file"; then
        rm -f "$docker_err_file"
        return 0
    fi

    if grep -qi "manually paused" "$docker_err_file" 2>/dev/null; then
        echo -e "${RED}❌ Docker Desktop در وضعیت pause است${NC}"
        echo "Docker Desktop را از Whale menu یا Dashboard از حالت Pause خارج کنید و دوباره تلاش کنید."
    else
        echo -e "${RED}❌ Docker engine در دسترس نیست${NC}"
        echo "جزئیات خطا:"
        cat "$docker_err_file"
    fi

    return 1
}

retry_command() {
    local description="$1"
    local attempts="$2"
    shift 2
    local try=1

    while [ "$try" -le "$attempts" ]; do
        echo "🔄 ${description} (تلاش ${try}/${attempts})..."
        if "$@"; then
            return 0
        fi

        if [ "$try" -lt "$attempts" ]; then
            echo -e "${YELLOW}⚠️  ${description} ناموفق بود؛ 10 ثانیه بعد دوباره تلاش می‌شود${NC}"
            sleep 10
        fi
        try=$((try + 1))
    done

    return 1
}

wait_for_http() {
    local url="$1"
    local attempts="${2:-30}"
    local delay="${3:-2}"
    local try=1

    while [ "$try" -le "$attempts" ]; do
        if curl -fsS -o /dev/null --max-time 5 "$url"; then
            return 0
        fi
        sleep "$delay"
        try=$((try + 1))
    done

    return 1
}

wait_for_port_owner() {
    local port="$1"
    local expected_pid="$2"
    local attempts="${3:-20}"
    local delay="${4:-1}"
    local try=1

    while [ "$try" -le "$attempts" ]; do
        local owner_pid
        owner_pid=$(lsof -tiTCP:"$port" -sTCP:LISTEN 2>/dev/null | head -n 1)
        if [ -n "$owner_pid" ] && [ "$owner_pid" = "$expected_pid" ]; then
            return 0
        fi
        sleep "$delay"
        try=$((try + 1))
    done

    return 1
}

ensure_port_free() {
    local port="$1"
    local label="$2"
    local owner_pid

    owner_pid=$(lsof -tiTCP:"$port" -sTCP:LISTEN 2>/dev/null | head -n 1)
    if [ -z "$owner_pid" ]; then
        return 0
    fi

    echo -e "${RED}❌ پورت ${port} برای ${label} آزاد نیست (PID: ${owner_pid})${NC}"
    echo "ابتدا ./scripts/stop_system.sh را اجرا کنید یا پردازش مزاحم را متوقف کنید."
    return 1
}

all_runtime_images_cached() {
   local images=(
       "postgres:16-alpine"
       "redis:7-alpine"
       "prom/prometheus:v2.54.1"
   )

    local image
    for image in "${images[@]}"; do
        if ! docker image inspect "$image" >/dev/null 2>&1; then
            return 1
        fi
    done

    return 0
}

stop_pid_file() {
    local pid_file="$1"
    local label="$2"

    if [ -f "$pid_file" ]; then
        local pid
        pid=$(cat "$pid_file" 2>/dev/null)
        if [ -n "$pid" ] && kill -0 "$pid" 2>/dev/null; then
            echo "🛑 توقف ${label} قبلی (PID: $pid)..."
            kill "$pid" 2>/dev/null || true
            sleep 2
            if kill -0 "$pid" 2>/dev/null; then
                kill -9 "$pid" 2>/dev/null || true
            fi
        fi
        rm -f "$pid_file"
    fi
}

stop_local_backend() {
    stop_pid_file "$BACKEND_PID_FILE" "backend محلی"
}

stop_local_frontend() {
    stop_pid_file "$FRONTEND_PID_FILE" "frontend محلی"
}

stop_local_worker() {
    stop_pid_file "$SCHEDULER_WORKER_PID_FILE" "worker زمان‌بند محلی (Worker 3)"
    stop_pid_file "$WORKER_PID_FILE" "worker محلی"
}

ensure_python_ready() {
    if [ ! -x "$PYTHON_BIN" ]; then
        echo -e "${RED}❌ Python مورد نیاز برای backend پیدا نشد: $PYTHON_BIN${NC}"
        return 1
    fi

    if ! "$PYTHON_BIN" -c "import fastapi, uvicorn, playwright, torch, cv2, redis, asyncpg" >/dev/null 2>&1; then
        echo -e "${RED}❌ وابستگی‌های Python برای backend کامل نیستند${NC}"
        echo "برای نصب، این دستور را اجرا کنید:"
        echo "  "$PYTHON_BIN" -m pip install -r requirements.txt"
        return 1
    fi

    return 0
}

ensure_node_ready() {
    if [ -z "$NODE_BIN" ]; then
        if [ -x "/opt/node/bin/node" ]; then
            NODE_BIN="/opt/node/bin/node"
        elif command -v node >/dev/null 2>&1; then
            NODE_BIN="$(command -v node)"
        fi
    fi

    if [ -z "$NPM_BIN" ]; then
        if [ -x "/opt/node/bin/npm" ]; then
            NPM_BIN="/opt/node/bin/npm"
        elif command -v npm >/dev/null 2>&1; then
            NPM_BIN="$(command -v npm)"
        fi
    fi

    if [ -z "$NODE_BIN" ] || [ ! -x "$NODE_BIN" ]; then
        echo -e "${RED}❌ Node.js برای frontend پیدا نشد${NC}"
        echo "NODE_BIN را تنظیم کنید یا Node.js را در PATH قرار دهید."
        return 1
    fi

    if [ -z "$NPM_BIN" ] || [ ! -x "$NPM_BIN" ]; then
        echo -e "${RED}❌ npm برای frontend پیدا نشد${NC}"
        echo "NPM_BIN را تنظیم کنید یا npm را در PATH قرار دهید."
        return 1
    fi

    return 0
}

start_local_backend() {
    mkdir -p output
    : >"$BACKEND_LOG_FILE"

    echo "🚀 اجرای backend به صورت محلی..."
    ensure_python_ready || return 1

    export DATABASE_URL="postgresql+asyncpg://postgres:${POSTGRES_PASSWORD:-postgres}@127.0.0.1:5432/${POSTGRES_DB:-utcms_rpa}"
    export REDIS_URL="redis://:${REDIS_PASSWORD}@127.0.0.1:6379/0"
    export REDIS_PASSWORD="${REDIS_PASSWORD}"
    export PORT=8000
    export HEADLESS="${HEADLESS:-true}"

    ensure_port_free 8000 "backend" || return 1

    echo "🔄 Initializing database..."
    if ! "$PYTHON_BIN" scripts/init_database.py; then
        echo -e "${RED}❌ Database initialization failed${NC}"
        echo "💡 Try: scripts/reset_database.sh to reset database"
        return 1
    fi

    # Start backend in background with proper detachment
    nohup "$PYTHON_BIN" -m uvicorn app.main:app --host 0.0.0.0 --port 8000 >"$BACKEND_LOG_FILE" 2>&1 </dev/null &
    local pid=$!
    echo "$pid" >"$BACKEND_PID_FILE"

    if ! kill -0 "$pid" 2>/dev/null; then
        echo -e "${RED}❌ اجرای backend محلی ناموفق بود${NC}"
        echo "لاگ backend: $BACKEND_LOG_FILE"
        tail -50 "$BACKEND_LOG_FILE"
        return 1
    fi

    if ! wait_for_port_owner 8000 "$pid" 15 1; then
        echo -e "${RED}❌ پردازش backend روی پورت 8000 مالک listener نشد${NC}"
        echo "لاگ backend: $BACKEND_LOG_FILE"
        tail -50 "$BACKEND_LOG_FILE"
        return 1
    fi

    if ! wait_for_http "http://127.0.0.1:8000/docs" 45 2; then
        echo -e "${RED}❌ Backend محلی روی پورت 8000 در دسترس نشد${NC}"
        echo "لاگ backend: $BACKEND_LOG_FILE"
        echo ""
        echo "📋 آخرین خطاها:"
        tail -50 "$BACKEND_LOG_FILE"
        return 1
    fi

    echo -e "${GREEN}✅ Backend محلی اجرا شد${NC}"
    return 0
}

start_local_frontend() {
    mkdir -p output
    : >"$FRONTEND_LOG_FILE"

    echo "🚀 build و اجرای frontend به صورت محلی..."
    ensure_node_ready || return 1

    if [ ! -d "apps/web/node_modules" ]; then
        echo -e "${RED}❌ وابستگی‌های frontend در apps/web/node_modules موجود نیست${NC}"
        echo "در مسیر apps/web این دستور را اجرا کنید:"
        echo "  $NPM_BIN install"
        return 1
    fi

    # Add Node.js to PATH
    export PATH="/opt/node/bin:$PATH"
    lsof -ti:3000 | xargs -r kill -9 2>/dev/null || true
    ensure_port_free 3000 "frontend" || return 1

    (
        cd apps/web || exit 1
        NEXT_PUBLIC_API_URL="http://127.0.0.1:8000/api" "yarn" run build
        mkdir -p .next/standalone/.next
        rm -rf .next/standalone/.next/static .next/standalone/public
        cp -R .next/static .next/standalone/.next/static
        cp -R public .next/standalone/public
    ) >"$FRONTEND_LOG_FILE" 2>&1
    if [ $? -ne 0 ]; then
        echo -e "${RED}❌ build محلی frontend ناموفق بود${NC}"
        echo "لاگ frontend: $FRONTEND_LOG_FILE"
        tail -50 "$FRONTEND_LOG_FILE"
        return 1
    fi

    # For standalone output, we must use node .next/standalone/server.js directly
    local frontend_pid
    frontend_pid=$(
        "$PYTHON_BIN" - <<PY
import os
import subprocess

log_path = os.path.abspath("$FRONTEND_LOG_FILE")
env = dict(os.environ)
env["PORT"] = "3000"
env["HOSTNAME"] = "0.0.0.0"
env["NEXT_PUBLIC_API_URL"] = "http://127.0.0.1:8000/api"

with open(log_path, "ab", buffering=0) as log_file:
    process = subprocess.Popen(
        ["$NODE_BIN", ".next/standalone/server.js"],
        cwd=os.path.abspath("apps/web"),
        stdout=log_file,
        stderr=subprocess.STDOUT,
        stdin=subprocess.DEVNULL,
        start_new_session=True,
        env=env,
    )
    print(process.pid)
PY
    )
    echo "$frontend_pid" >"$FRONTEND_PID_FILE"

    local pid
    pid=$(cat "$FRONTEND_PID_FILE" 2>/dev/null)
    if [ -z "$pid" ] || ! kill -0 "$pid" 2>/dev/null; then
        echo -e "${RED}❌ اجرای frontend محلی ناموفق بود${NC}"
        echo "لاگ frontend: $FRONTEND_LOG_FILE"
        return 1
    fi

    if ! wait_for_port_owner 3000 "$pid" 20 1; then
        echo -e "${RED}❌ پردازش frontend روی پورت 3000 مالک listener نشد${NC}"
        echo "لاگ frontend: $FRONTEND_LOG_FILE"
        tail -50 "$FRONTEND_LOG_FILE"
        return 1
    fi

    if ! wait_for_http "http://127.0.0.1:3000" 45 2; then
        echo -e "${RED}❌ Frontend محلی روی پورت 3000 در دسترس نشد${NC}"
        echo "لاگ frontend: $FRONTEND_LOG_FILE"
        return 1
    fi

    echo -e "${GREEN}✅ Frontend محلی اجرا شد${NC}"
    return 0
}

configure_local_celery_environment() {
    export REDIS_URL="redis://:${REDIS_PASSWORD}@127.0.0.1:6379/0"
    export CELERY_BROKER_URL="$REDIS_URL"
    export CELERY_RESULT_BACKEND="$REDIS_URL"
    export HEADLESS="${HEADLESS:-true}"
}

wait_for_local_celery_worker() {
    local pid="$1"
    local log_file="$2"
    local label="$3"

    echo "⏳ منتظر آماده‌سازی ${label} (حداکثر 20 ثانیه)..."
    for i in {1..20}; do
        if ! kill -0 "$pid" 2>/dev/null; then
            echo -e "${RED}❌ فرآیند ${label} متوقف شد${NC}"
            echo "لاگ ${label}: $log_file"
            tail -80 "$log_file"
            return 1
        fi

        # Check this process's own log instead of a cluster-wide inspect ping;
        # a second local worker may already answer ping while this one failed.
        if grep -qi "ready\." "$log_file"; then
            echo -e "${GREEN}✅ ${label} با موفقیت آماده شد${NC}"
            return 0
        fi

        sleep 1
    done

    if kill -0 "$pid" 2>/dev/null; then
        echo -e "${YELLOW}⚠️  ${label} هنوز پیام ready ثبت نکرده، اما فرآیند در حال اجراست${NC}"
        return 0
    fi

    echo -e "${RED}❌ ${label} آماده پاسخ‌گویی نشد${NC}"
    echo "لاگ ${label}: $log_file"
    tail -80 "$log_file"
    return 1
}

start_local_celery_worker() {
    local label="$1"
    local queues="$2"
    local node_name="$3"
    local include_beat="$4"
    local pid_file="$5"
    local log_file="$6"
    local worker_id="$7"
    local worker_ip_index="$8"

    mkdir -p output
    : >"$log_file"

    echo "🚀 اجرای ${label} به صورت محلی..."
    ensure_python_ready || return 1
    configure_local_celery_environment

    local worker_pid
    worker_pid=$( \
        LOCAL_CELERY_QUEUE_LIST="$queues" \
        LOCAL_CELERY_NODE_NAME="$node_name" \
        LOCAL_CELERY_INCLUDE_BEAT="$include_beat" \
        LOCAL_CELERY_LOG_FILE="$log_file" \
        LOCAL_CELERY_WORKER_ID="$worker_id" \
        LOCAL_CELERY_WORKER_IP_INDEX="$worker_ip_index" \
        "$PYTHON_BIN" - <<'PY'
import os
import subprocess
import sys

log_path = os.path.abspath(os.environ["LOCAL_CELERY_LOG_FILE"])
queue_list = os.environ["LOCAL_CELERY_QUEUE_LIST"]
node_name = os.environ["LOCAL_CELERY_NODE_NAME"]
include_beat = os.environ["LOCAL_CELERY_INCLUDE_BEAT"] == "true"
worker_id = os.environ["LOCAL_CELERY_WORKER_ID"]
worker_ip_index = os.environ["LOCAL_CELERY_WORKER_IP_INDEX"].strip()
env = dict(os.environ)
# Do not inherit a remote node's identity from .env: scheduler work must be
# registered and routed as Worker 3, while the generic local worker has none.
env["WORKER_ID"] = worker_id
if worker_ip_index:
    env["WORKER_IP_INDEX"] = worker_ip_index
else:
    env.pop("WORKER_IP_INDEX", None)
for key in (
    "LOCAL_CELERY_QUEUE_LIST",
    "LOCAL_CELERY_NODE_NAME",
    "LOCAL_CELERY_INCLUDE_BEAT",
    "LOCAL_CELERY_LOG_FILE",
    "LOCAL_CELERY_WORKER_ID",
    "LOCAL_CELERY_WORKER_IP_INDEX",
):
    env.pop(key, None)

command = [
    sys.executable,
    "-m",
    "celery",
    "-A",
    "app.workers.phase1_tasks:celery_app",
    "worker",
    "-Q",
    queue_list,
    "-n",
    node_name,
    "-l",
    "info",
]
if include_beat:
    command.append("-B")
command.extend(["--pool", "solo"])

with open(log_path, "ab", buffering=0) as log_file:
    process = subprocess.Popen(
        command,
        cwd=os.path.abspath("."),
        stdout=log_file,
        stderr=subprocess.STDOUT,
        stdin=subprocess.DEVNULL,
        start_new_session=True,
        env=env,
    )
    print(process.pid)
PY
    )
    echo "$worker_pid" >"$pid_file"

    local pid
    pid=$(cat "$pid_file" 2>/dev/null)
    if [ -z "$pid" ] || ! kill -0 "$pid" 2>/dev/null; then
        echo -e "${RED}❌ اجرای ${label} ناموفق بود${NC}"
        echo "لاگ ${label}: $log_file"
        tail -50 "$log_file"
        return 1
    fi

    wait_for_local_celery_worker "$pid" "$log_file" "$label"
}

start_local_scheduler_worker() {
    # Keep the singleton control queue on an explicit Worker 3 process even in
    # the all-in-one development stack.
    start_local_celery_worker \
        "worker زمان‌بند محلی (Worker 3)" \
        "$LOCAL_SCHEDULER_QUEUES" \
        "$LOCAL_SCHEDULER_NODENAME" \
        "false" \
        "$SCHEDULER_WORKER_PID_FILE" \
        "$SCHEDULER_WORKER_LOG_FILE" \
        "$LOCAL_SCHEDULER_WORKER_ID" \
        "$LOCAL_SCHEDULER_IP_INDEX"
}

start_local_worker() {
    # Beat publishes scheduler work, while this generic worker deliberately
    # does not consume rpa_scheduler.
    start_local_celery_worker \
        "worker محلی" \
        "$LOCAL_WORKER_QUEUES" \
        "local_worker@%h" \
        "true" \
        "$WORKER_PID_FILE" \
        "$WORKER_LOG_FILE" \
        "$LOCAL_GENERIC_WORKER_ID" \
        ""
}

check_final_health() {
    echo ""
    echo "🔍 بررسی سلامت نهایی سرویس‌ها..."

    local failed=0

    if wait_for_http "http://127.0.0.1:8000/docs" 3 1; then
        echo -e "${GREEN}✅ Backend روی 8000 در دسترس است${NC}"
    else
        echo -e "${RED}❌ Backend روی 8000 در دسترس نیست${NC}"
        failed=1
    fi

    if wait_for_http "http://127.0.0.1:3000" 3 1; then
        echo -e "${GREEN}✅ Frontend روی 3000 در دسترس است${NC}"
    else
        echo -e "${RED}❌ Frontend روی 3000 در دسترس نیست${NC}"
        failed=1
    fi

    if wait_for_http "http://127.0.0.1:9090/-/healthy" 3 1; then
        echo -e "${GREEN}✅ Prometheus روی 9090 در دسترس است${NC}"
    else
        echo -e "${RED}❌ Prometheus روی 9090 در دسترس نیست${NC}"
        failed=1
    fi

    return "$failed"
}

echo "🔍 بررسی Docker..."
if ! docker --version &> /dev/null; then
    echo -e "${RED}❌ Docker نصب نیست!${NC}"
    echo "لطفاً Docker را از https://www.docker.com/products/docker-desktop نصب کنید."
    exit 1
fi

if ! docker compose version &> /dev/null; then
    echo -e "${RED}❌ Docker Compose نصب نیست!${NC}"
    exit 1
fi

echo -e "${GREEN}✅ Docker نصب است${NC}"
if ! ensure_docker_engine_ready; then
    exit 1
fi
echo ""

echo "🔍 بررسی فایل .env..."
if [ ! -f .env ]; then
    echo -e "${RED}❌ فایل .env وجود ندارد!${NC}"
    echo "در حال کپی از .env.example..."
    cp .env.example .env
    echo -e "${YELLOW}⚠️  لطفاً فایل .env را ویرایش کنید و کلیدهای امنیتی را تنظیم کنید${NC}"
    exit 1
fi

echo -e "${GREEN}✅ فایل .env موجود است${NC}"
set -a
source .env
set +a
echo ""

echo "🛑 توقف containers قبلی (در صورت وجود)..."
docker compose down 2>/dev/null || true
stop_local_backend
stop_local_frontend
stop_local_worker
echo ""

echo "🧹 پاکسازی cache files..."
find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null
find . -name "*.pyc" -delete 2>/dev/null
echo -e "${GREEN}✅ Cache پاک شد${NC}"
echo ""

echo "🏗️  اجرای سرویس‌های زیرساخت و اپلیکیشن..."
echo "این ممکن است چند دقیقه طول بکشد..."
echo ""

if all_runtime_images_cached && [ "$FORCE_DOCKER_PULL" != "true" ]; then
    echo -e "${GREEN}✅ imageهای زیرساخت در cache موجود هستند؛ pull تکراری را رد می‌کنیم${NC}"
elif retry_command "دریافت imageهای زیرساخت" 3 docker compose pull postgres redis prometheus; then
    :
elif all_runtime_images_cached; then
    echo -e "${YELLOW}⚠️  pull ناموفق بود، اما imageهای لازم از قبل در cache موجود هستند؛ ادامه می‌دهیم${NC}"
else
    echo -e "${YELLOW}⚠️  pull ناموفق بود. به دلیل محدودیت rate limit تلاش می‌کنیم ادامه دهیم...${NC}"
fi

if ! retry_command "اجرای containers زیرساخت" 2 docker compose up -d postgres redis prometheus; then
    echo ""
    echo -e "${RED}❌ خطا در اجرای سرویس‌های زیرساخت${NC}"
    echo "لاگ‌ها را بررسی کنید: docker compose logs"
    exit 1
fi

if ! wait_for_http "http://127.0.0.1:9090/-/healthy" 45 2; then
    echo -e "${RED}❌ Prometheus روی 9090 آماده نشد${NC}"
    exit 1
fi

if ! start_local_backend; then
    exit 1
fi

if ! start_local_scheduler_worker; then
    exit 1
fi

if ! start_local_worker; then
    stop_local_worker
    exit 1
fi

if ! start_local_frontend; then
    exit 1
fi

if ! check_final_health; then
    echo ""
    echo -e "${RED}❌ برخی سرویس‌ها هنوز در دسترس نیستند${NC}"
    exit 1
fi

echo ""
echo "🔍 بررسی وضعیت containers..."
docker compose ps || true

echo ""
echo "============================================================"
echo "✅ سیستم با موفقیت راه‌اندازی شد!"
echo "============================================================"
echo ""
echo "🌐 دسترسی به سرویس‌ها:"
echo "   - Frontend:    http://localhost:3000"
echo "   - Backend API: http://localhost:8000/"
echo "   - API Docs:    http://localhost:8000/docs"
echo "   - Prometheus:  http://localhost:9090"
echo ""
echo "📋 دستورات مفید:"
echo "   - مشاهده لاگ‌ها:           docker compose logs -f"
echo "   - مشاهده لاگ backend محلی: tail -f $BACKEND_LOG_FILE"
echo "   - مشاهده لاگ worker زمان‌بند: tail -f $SCHEDULER_WORKER_LOG_FILE"
echo "   - مشاهده لاگ worker محلی:  tail -f $WORKER_LOG_FILE"
echo "   - مشاهده لاگ frontend محلی: tail -f $FRONTEND_LOG_FILE"
echo "   - توقف سیستم:             docker compose down && pkill -F $BACKEND_PID_FILE && pkill -F $SCHEDULER_WORKER_PID_FILE && pkill -F $WORKER_PID_FILE && pkill -F $FRONTEND_PID_FILE"
echo ""
echo "============================================================"

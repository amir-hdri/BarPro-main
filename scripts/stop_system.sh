#!/bin/bash
 # Stop all system components gracefully
 
 set -e
 
 GREEN='\033[0;32m'
 RED='\033[0;31m'
 YELLOW='\033[1;33m'
 NC='\033[0m'
 
echo "🛑 Stopping UTCMS Automation System"
echo "===================================="
echo ""

stop_port_processes() {
    local port="$1"
    local label="$2"
    local pids

    pids=$(lsof -tiTCP:"$port" -sTCP:LISTEN 2>/dev/null || true)
    if [ -z "$pids" ]; then
        return 0
    fi

    echo "🛑 پاکسازی پردازش‌های باقی‌مانده ${label} روی پورت ${port}..."
    for pid in $pids; do
        kill "$pid" 2>/dev/null || true
    done
    sleep 2

    pids=$(lsof -tiTCP:"$port" -sTCP:LISTEN 2>/dev/null || true)
    if [ -n "$pids" ]; then
        for pid in $pids; do
            kill -9 "$pid" 2>/dev/null || true
        done
    fi
}
 
 # Stop local backend
 if [ -f "output/backend.pid" ]; then
     PID=$(cat output/backend.pid)
     if kill -0 "$PID" 2>/dev/null; then
         echo "🛑 Stopping backend (PID: $PID)..."
         kill "$PID" 2>/dev/null || true
         sleep 2
         if kill -0 "$PID" 2>/dev/null; then
             echo "⚠️  Force killing backend..."
             kill -9 "$PID" 2>/dev/null || true
         fi
         echo -e "${GREEN}✅ Backend stopped${NC}"
     fi
     rm -f output/backend.pid
else
    echo "ℹ️  Backend PID file not found"
fi
stop_port_processes 8000 "backend"
 
# Stop local frontend
if [ -f "output/frontend.pid" ]; then
     PID=$(cat output/frontend.pid)
     if kill -0 "$PID" 2>/dev/null; then
         echo "🛑 Stopping frontend (PID: $PID)..."
         kill "$PID" 2>/dev/null || true
         sleep 2
         if kill -0 "$PID" 2>/dev/null; then
             echo "⚠️  Force killing frontend..."
             kill -9 "$PID" 2>/dev/null || true
         fi
         echo -e "${GREEN}✅ Frontend stopped${NC}"
     fi
     rm -f output/frontend.pid
else
    echo "ℹ️  Frontend PID file not found"
fi
stop_port_processes 3000 "frontend"

# Stop the dedicated local scheduler worker (Worker 3) before the generic worker.
if [ -f "output/scheduler_worker.pid" ]; then
    PID=$(cat output/scheduler_worker.pid)
    if kill -0 "$PID" 2>/dev/null; then
        echo "🛑 Stopping scheduler worker 3 (PID: $PID)..."
        kill "$PID" 2>/dev/null || true
        sleep 2
        if kill -0 "$PID" 2>/dev/null; then
            echo "⚠️  Force killing scheduler worker 3..."
            kill -9 "$PID" 2>/dev/null || true
        fi
        echo -e "${GREEN}✅ Scheduler worker 3 stopped${NC}"
    fi
    rm -f output/scheduler_worker.pid
else
    echo "ℹ️  Scheduler worker 3 PID file not found"
fi

# Stop local generic worker
if [ -f "output/worker.pid" ]; then
    PID=$(cat output/worker.pid)
    if kill -0 "$PID" 2>/dev/null; then
        echo "🛑 Stopping worker (PID: $PID)..."
        kill "$PID" 2>/dev/null || true
        sleep 2
        if kill -0 "$PID" 2>/dev/null; then
            echo "⚠️  Force killing worker..."
            kill -9 "$PID" 2>/dev/null || true
        fi
        echo -e "${GREEN}✅ Worker stopped${NC}"
    fi
    rm -f output/worker.pid
else
    echo "ℹ️  Worker PID file not found"
fi
 
 # Stop Docker services
 echo ""
 echo "🐳 Stopping Docker services..."
 if docker compose down 2>/dev/null; then
     echo -e "${GREEN}✅ Docker services stopped${NC}"
 else
     echo -e "${YELLOW}⚠️  Docker services may not be running${NC}"
 fi
 
 echo ""
 echo "===================================="
 echo "✅ System stopped successfully"
 echo ""
 echo "To start again: ./scripts/start_system.sh"

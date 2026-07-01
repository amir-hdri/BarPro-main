#!/bin/bash

# Simple script to stop backend, frontend, and inspector services
# Run this script directly in your terminal: ./stop_services.sh

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$PROJECT_DIR"

echo "Stopping services gracefully..."

# 1. Stop via PIDs if available
if [ -f "$PROJECT_DIR/output/rpa_inspector.pid" ]; then
    INSPECTOR_PID=$(cat "$PROJECT_DIR/output/rpa_inspector.pid")
    echo "Stopping RPA Inspector (PID: $INSPECTOR_PID)..."
    kill -TERM "$INSPECTOR_PID" 2>/dev/null
    # Allow some time for the inspector to write its final JSON report
    sleep 2
    rm "$PROJECT_DIR/output/rpa_inspector.pid"
fi

if [ -f "$PROJECT_DIR/output/backend.pid" ]; then
    BACKEND_PID=$(cat "$PROJECT_DIR/output/backend.pid")
    echo "Stopping Backend (PID: $BACKEND_PID)..."
    kill -TERM "$BACKEND_PID" 2>/dev/null
    rm "$PROJECT_DIR/output/backend.pid"
fi

if [ -f "$PROJECT_DIR/output/frontend.pid" ]; then
    FRONTEND_PID=$(cat "$PROJECT_DIR/output/frontend.pid")
    echo "Stopping Frontend (PID: $FRONTEND_PID)..."
    kill -TERM "$FRONTEND_PID" 2>/dev/null
    rm "$PROJECT_DIR/output/frontend.pid"
fi

# 2. Sweep/Clean up using PID files first
if [ -f /tmp/uvicorn.pid ]; then
    UVI_PID=$(cat /tmp/uvicorn.pid)
    echo "Stopping uvicorn (PID: $UVI_PID)..."
    kill "$UVI_PID" 2>/dev/null || true
    rm -f /tmp/uvicorn.pid
fi

if [ -f /tmp/next-server.pid ]; then
    NEXT_PID=$(cat /tmp/next-server.pid)
    echo "Stopping next-server (PID: $NEXT_PID)..."
    kill "$NEXT_PID" 2>/dev/null || true
    rm -f /tmp/next-server.pid
fi

# 3. Fallback: sweep remaining orphaned processes
echo "Sweeping any remaining orphaned processes on port 8000 and 3000..."
pkill -f "uvicorn" 2>/dev/null || true
pkill -f "next-server" 2>/dev/null || true
pkill -f "next dev" 2>/dev/null || true
pkill -f "yarn dev" 2>/dev/null || true
pkill -f "node.*next" 2>/dev/null || true
pkill -f "ms-playwright" 2>/dev/null || true

echo "All services stopped successfully."

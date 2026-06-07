#!/bin/bash

# Simple script to stop backend, frontend, and inspector services
# Run this script directly in your terminal: ./stop_services.sh

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$PROJECT_DIR"

echo "Stopping services gracefully..."

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

echo "All services stopped successfully."

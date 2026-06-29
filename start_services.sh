#!/bin/bash

# Simple wrapper to start backend, frontend, and inspector services
# Run this script directly in your terminal: ./start_services.sh

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$PROJECT_DIR"

if [ "$PROJECT_DIR" = "/opt/barpro" ]; then
    echo "=================================================="
    echo "⚠️  WARNING: Production Environment Detected ⚠️ "
    echo "=================================================="
    echo "Do NOT run start_services.sh on the production server."
    echo "This script is for local development without Docker."
    echo ""
    echo "Please use the Docker setup via manage.sh:"
    echo "👉 bash manage.sh start"
    echo "=================================================="
    exit 1
fi

# Export HEADLESS=false to run browsers in headful mode (visible) when starting services
export HEADLESS=false

# Create output dir if it doesn't exist
mkdir -p "$PROJECT_DIR/output"

echo "Starting backend..."
"$PROJECT_DIR/scripts/start_backend.sh" > "$PROJECT_DIR/output/backend.log" 2>&1 &
BACKEND_PID=$!
echo $BACKEND_PID > "$PROJECT_DIR/output/backend.pid"
echo "Backend started with PID: $BACKEND_PID"

sleep 5

echo "Starting frontend..."
"$PROJECT_DIR/scripts/start_frontend.sh" > "$PROJECT_DIR/output/frontend.log" 2>&1 &
FRONTEND_PID=$!
echo $FRONTEND_PID > "$PROJECT_DIR/output/frontend.pid"
echo "Frontend started with PID: $FRONTEND_PID"

sleep 2

# Detect virtual environment python
VENV_PYTHON="python3"
if [ -d "$PROJECT_DIR/.venv" ]; then
    VENV_PYTHON="$PROJECT_DIR/.venv/bin/python"
elif [ -d "$PROJECT_DIR/venv" ]; then
    VENV_PYTHON="$PROJECT_DIR/venv/bin/python"
fi

echo "Starting RPA Inspector Daemon..."
"$VENV_PYTHON" "$PROJECT_DIR/scripts/rpa_inspector.py" --daemon --headless > "$PROJECT_DIR/output/rpa_inspector.log" 2>&1 &
INSPECTOR_PID=$!
echo $INSPECTOR_PID > "$PROJECT_DIR/output/rpa_inspector.pid"
echo "RPA Inspector started with PID: $INSPECTOR_PID"

echo ""
echo "=================================================="
echo "               All Services Started!              "
echo "=================================================="
echo "- Backend API:        http://localhost:8000/docs"
echo "- Frontend UI:        http://localhost:3000"
echo "- Backend logs:       tail -f output/backend.log"
echo "- Frontend logs:      tail -f output/frontend.log"
echo "- RPA Inspector logs: tail -f output/rpa_inspector.log"
echo "=================================================="
echo "To stop all services and generate reports:"
echo "👉  ./stop_services.sh"
echo "=================================================="
echo ""

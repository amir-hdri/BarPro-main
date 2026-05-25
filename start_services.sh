#!/bin/bash

# Simple wrapper to start backend and frontend services
# Run this script directly in your terminal: ./start_services.sh

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$PROJECT_DIR"

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

echo ""
echo "Services started!"
echo "- Backend logs: tail -f output/backend.log"
echo "- Frontend logs: tail -f output/frontend.log"
echo ""
echo "- Backend API:  http://localhost:8000/docs"
echo "- Frontend UI:  http://localhost:3000"
echo ""
echo "To stop services: pkill -F output/backend.pid 2>/dev/null; pkill -F output/frontend.pid 2>/dev/null; echo 'Services stopped.'"

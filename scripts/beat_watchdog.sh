#!/bin/bash
# scripts/beat_watchdog.sh — هر دقیقه از crontab اجرا می‌شود
CONTAINER_NAME="barpro-beat"

# Log configuration
LOG_DIR="/var/log/barpro"
LOG_FILE="${LOG_DIR}/beat_watchdog.log"

# Fallback to local logs if /var/log is not writable
if [ ! -w "$LOG_DIR" ]; then
    LOG_DIR="$(pwd)"
    LOG_FILE="${LOG_DIR}/beat_watchdog.log"
fi

if ! docker inspect --format='{{.State.Running}}' "$CONTAINER_NAME" 2>/dev/null | grep -q "true"; then
    echo "$(date): Beat container down, restarting..." >> "$LOG_FILE"
    docker start "$CONTAINER_NAME"
fi

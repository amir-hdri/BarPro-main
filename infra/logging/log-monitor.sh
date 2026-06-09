#!/bin/bash
# Log Monitoring Script for BarPro
# Monitors log directory sizes and sends alerts when thresholds are exceeded

set -euo pipefail

# Configuration
LOG_DIR="/var/log/barpro"
MAX_SIZE_GB=5  # Alert when log directory exceeds 5GB
MAX_FILE_SIZE_MB=100  # Alert when individual log file exceeds 100MB
ALERT_EMAIL="admin@barpro.com"  # Change to your admin email
ALERT_WEBHOOK=""  # Optional: Discord/Slack webhook URL

# Colors for output
RED='\033[0;31m'
YELLOW='\033[1;33m'
GREEN='\033[0;32m'
NC='\033[0m' # No Color

# Functions
log_info() {
    echo -e "${GREEN}[INFO]${NC} $1"
}

log_warn() {
    echo -e "${YELLOW}[WARN]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# Check if log directory exists
if [ ! -d "$LOG_DIR" ]; then
    log_warn "Log directory $LOG_DIR does not exist. Creating..."
    mkdir -p "$LOG_DIR"
    chown appuser:appuser "$LOG_DIR" 2>/dev/null || true
fi

# Get total log directory size in bytes
TOTAL_SIZE=$(du -sb "$LOG_DIR" 2>/dev/null | awk '{print $1}') || TOTAL_SIZE=0
TOTAL_SIZE_GB=$(echo "scale=2; $TOTAL_SIZE / (1024*1024*1024)" | bc 2>/dev/null || echo "0")

# Get largest log files
LARGEST_FILES=$(find "$LOG_DIR" -type f -name "*.log" -exec ls -lhS {} + 2>/dev/null | head -10)

# Check for old log files
OLD_FILES=$(find "$LOG_DIR" -type f -name "*.log.*" -mtime +30 2>/dev/null | wc -l)

# Check for uncompressed log files
UNCOMPRESSED=$(find "$LOG_DIR" -type f -name "*.log" ! -name "*.gz" 2>/dev/null | wc -l)

# Output
log_info "=== BarPro Log Monitor Report ==="
log_info "Date: $(date)"
log_info "Log Directory: $LOG_DIR"
log_info "Total Size: ${TOTAL_SIZE_GB}GB"
log_info ""

# Check total size
echo "--- Size Check ---"
if (( $(echo "$TOTAL_SIZE_GB > $MAX_SIZE_GB" | bc -l 2>/dev/null) )); then
    log_error "Log directory exceeds ${MAX_SIZE_GB}GB threshold: ${TOTAL_SIZE_GB}GB"
    ALERT_NEEDED=true
else
    log_info "Total size OK: ${TOTAL_SIZE_GB}GB (threshold: ${MAX_SIZE_GB}GB)"
fi

# Check individual file sizes
echo ""
echo "--- Largest Log Files ---"
if [ -n "$LARGEST_FILES" ]; then
    echo "$LARGEST_FILES"
    
    # Check each file size
    while IFS= read -r line; do
        if [ -n "$line" ]; then
            FILE_SIZE_MB=$(echo "$line" | awk '{print $5}')
            # Extract numeric value (remove 'M' or 'G' suffix)
            FILE_SIZE_NUM=$(echo "$FILE_SIZE_MB" | sed 's/[MG]//g')
            FILE_NAME=$(echo "$line" | awk '{print $9}')
            
            if [ "$FILE_SIZE_MB" != "" ] && (( $(echo "$FILE_SIZE_NUM > $MAX_FILE_SIZE_MB" | bc -l 2>/dev/null) )); then
                log_warn "Large file: $FILE_NAME ($FILE_SIZE_MB)"
                ALERT_NEEDED=true
            fi
        fi
    done <<< "$LARGEST_FILES"
else
    log_info "No log files found"
fi

# Check for old files
echo ""
echo "--- Old Files Check ---"
if [ "$OLD_FILES" -gt 0 ]; then
    log_warn "Found $OLD_FILES old rotated log files (>30 days)"
    log_info "Consider reducing retention period or cleaning up old logs"
fi

# Check logrotate status
echo ""
echo "--- Logrotate Status ---"
if command -v logrotate &>/dev/null; then
    log_info "logrotate is installed"
    if [ -f "/etc/logrotate.d/barpro" ]; then
        log_info "BarPro logrotate configuration exists"
        LAST_ROTATE=$(stat -c %y /etc/logrotate.d/barpro 2>/dev/null | awk '{print $1}')
        log_info "Last configuration update: $LAST_ROTATE"
    else
        log_warn "BarPro logrotate configuration not found at /etc/logrotate.d/barpro"
        ALERT_NEEDED=true
    fi
else
    log_error "logrotate is NOT installed"
    ALERT_NEEDED=true
fi

# Summary
echo ""
log_info "=== Summary ==="
if [ "${ALERT_NEEDED:-false}" = true ]; then
    log_error "ALERT: Log issues detected! Please investigate."
    exit 1
else
    log_info "All log checks passed."
    exit 0
fi

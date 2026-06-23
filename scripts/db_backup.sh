#!/bin/bash
# BarPro Database Backup Script
# Scheduled daily via cron at 3:00 AM.
# Compresses PostgreSQL database and uploads to Google Drive via rclone.

# Get the script directory and navigate to the project root
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" &> /dev/null && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
cd "$PROJECT_ROOT"

# Load environment variables
if [ -f .env ]; then
    export $(grep -v '^#' .env | xargs)
fi

DB_NAME="${POSTGRES_DB:-utcms_rpa}"
BACKUP_DIR="${PROJECT_ROOT}/output/backups"
TIMESTAMP=$(date +"%Y%m%d_%H%M%S")
BACKUP_FILE="${BACKUP_DIR}/barpro_backup_${TIMESTAMP}.sql.gz"

# Ensure local backup directory exists
mkdir -p "$BACKUP_DIR"

echo "[$(date)] Starting PostgreSQL database backup for '${DB_NAME}'..."

# Execute pg_dump inside the container and compress it
docker compose exec -T postgres pg_dump -U postgres -d "${DB_NAME}" | gzip > "${BACKUP_FILE}"

if [ ${PIPESTATUS[0]} -eq 0 ] && [ -f "${BACKUP_FILE}" ]; then
    echo "[$(date)] Backup created successfully: ${BACKUP_FILE} ($(du -sh ${BACKUP_FILE} | cut -f1))"
    
    # Check if rclone is configured
    if command -v rclone &> /dev/null; then
        echo "[$(date)] Uploading backup to Google Drive remote 'gdrive'..."
        rclone copy "${BACKUP_FILE}" gdrive:barpro_backups/
        
        if [ $? -eq 0 ]; then
            echo "[$(date)] Backup uploaded to Google Drive successfully."
            
            # Enforce 30-day retention policy on Google Drive
            echo "[$(date)] Cleaning up backups older than 30 days from Google Drive..."
            rclone delete --min-age 30d gdrive:barpro_backups/
        else
            echo "❌ Error: Failed to upload backup to Google Drive via rclone."
        fi
    else
        echo "⚠️ Warning: 'rclone' is not installed. Backup remains local-only."
    fi
    
    # Enforce 30-day local retention policy
    echo "[$(date)] Cleaning up local backups older than 30 days..."
    find "${BACKUP_DIR}" -type f -name "barpro_backup_*.sql.gz" -mtime +30 -delete
    
else
    echo "❌ Error: pg_dump backup failed."
    exit 1
fi

echo "[$(date)] Backup process completed."

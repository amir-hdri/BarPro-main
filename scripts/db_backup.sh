#!/bin/bash
# BarPro Database Backup Script
# Scheduled daily via cron at 3:00 AM.
# Compresses PostgreSQL database and uploads to Google Drive via rclone.

set -euo pipefail

# Get the script directory and navigate to the project root
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" &> /dev/null && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
cd "$PROJECT_ROOT"

# Load environment variables without expanding '$' in bcrypt or other secrets.
# shellcheck source=scripts/load_env.sh
source scripts/load_env.sh
load_dotenv .env

DB_NAME="${POSTGRES_DB:-utcms_rpa}"
BACKUP_DIR="${PROJECT_ROOT}/output/backups"
TIMESTAMP=$(date +"%Y%m%d_%H%M%S")
BACKUP_FILE="${BACKUP_DIR}/barpro_backup_${TIMESTAMP}.sql.gz"
TEMP_FILE="${BACKUP_FILE}.tmp"

# Ensure local backup directory exists
mkdir -p "$BACKUP_DIR"

echo "[$(date)] Starting PostgreSQL database backup for '${DB_NAME}'..."

# Execute pg_dump inside the container and compress it
rm -f "$TEMP_FILE"
trap 'rm -f "$TEMP_FILE"' EXIT
docker compose -f compose/infra.yml exec -T postgres pg_dump -U postgres -d "${DB_NAME}" | gzip -c > "$TEMP_FILE"
test -s "$TEMP_FILE"
gzip -t "$TEMP_FILE"
chmod 600 "$TEMP_FILE"
mv "$TEMP_FILE" "$BACKUP_FILE"
trap - EXIT

if [ -s "${BACKUP_FILE}" ]; then
    echo "[$(date)] Backup created and verified: ${BACKUP_FILE} ($(du -sh "${BACKUP_FILE}" | cut -f1))"
    
    # Check if rclone is configured
    if command -v rclone &> /dev/null; then
        echo "[$(date)] Uploading backup to Google Drive remote 'gdrive'..."
        if rclone copy "${BACKUP_FILE}" gdrive:barpro_backups/; then
            echo "[$(date)] Backup uploaded to Google Drive successfully."
            
            # Enforce 30-day retention policy on Google Drive
            echo "[$(date)] Cleaning up backups older than 30 days from Google Drive..."
            rclone delete --min-age 30d gdrive:barpro_backups/
        else
            echo "❌ Error: Failed to upload backup to Google Drive via rclone."
            exit 2
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

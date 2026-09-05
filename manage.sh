#!/bin/bash
# BarPro Platform Management Script

set -e
set -o pipefail

# Load environment variables if present
if [ -f .env ]; then
    # shellcheck source=scripts/load_env.sh
    source scripts/load_env.sh
    load_dotenv .env
fi

COMPOSE_FILES="-f compose/infra.yml -f compose/proxy.yml -f compose/backend.yml -f compose/web.yml -f compose/monitoring.yml"

# Production defaults to Model B: one Central Squid/worker plus remote worker
# nodes. Model A is intentionally opt-in because enabling its local Squid 2/3
# on Central exposes ports 3129/3130 and duplicates the remote worker slots.
BARPRO_TOPOLOGY="${BARPRO_TOPOLOGY:-model-b}"
case "$BARPRO_TOPOLOGY" in
    model-a|model-b) ;;
    *)
        echo "ERROR: BARPRO_TOPOLOGY must be 'model-b' (default) or 'model-a'." >&2
        exit 2
        ;;
esac

remove_model_a_services_from_central() {
    echo "Removing Model A-only services from the Model B Central host..."
    # Drain Celery before removing the local proxies it depends on.
    docker compose -f compose/backend.yml --profile scale-out stop celery_worker_2 celery_worker_3 > /dev/null 2>&1 || true
    docker compose -f compose/backend.yml --profile scale-out rm -f celery_worker_2 celery_worker_3 > /dev/null 2>&1 || true
    docker compose -f compose/proxy.yml --profile model-a stop squid_2 squid_3 > /dev/null 2>&1 || true
    docker compose -f compose/proxy.yml --profile model-a rm -f squid_2 squid_3 > /dev/null 2>&1 || true
}

create_verified_backup() {
    local backup_dir="output/backups"
    local db_name="${POSTGRES_DB:-utcms_rpa}"
    local timestamp backup_file temp_file
    timestamp="$(date +%Y%m%d_%H%M%S)"
    backup_file="$backup_dir/barpro_backup_${timestamp}.sql.gz"
    temp_file="${backup_file}.tmp"

    mkdir -p "$backup_dir"
    rm -f "$temp_file"
    trap 'rm -f "$temp_file"' RETURN

    echo "Creating verified PostgreSQL backup..."
    docker compose -f compose/infra.yml exec -T postgres \
        pg_dump -U postgres -d "$db_name" | gzip -c > "$temp_file"
    test -s "$temp_file"
    gzip -t "$temp_file"
    chmod 600 "$temp_file"
    mv "$temp_file" "$backup_file"
    trap - RETURN
    echo "Verified backup written to $backup_file"
}

# Ensure the shared docker network exists with the expected subnet.
# Workers reach host Squid proxies via the bridge gateway 172.20.0.1.
ensure_network() {
    if ! docker network inspect barpro_platform > /dev/null 2>&1; then
        echo "Creating docker network barpro_platform (172.20.0.0/16)..."
        docker network create --subnet=172.20.0.0/16 barpro_platform
    fi
}

# Block until Postgres accepts connections.
#
# WHY: `compose/backend.yml` declares no depends_on, and `docker compose up -d`
# returns as soon as containers are created — not when they are usable. Postgres'
# healthcheck has interval 10s, so on a cold start the migration runner used to
# run while Postgres was still initialising, exit non-zero, and — because this
# script runs under `set -e` — abort `manage.sh start` outright. The backend came
# up but nginx, the frontend and Prometheus were never started, i.e. containers
# running yet the site down. Wait explicitly instead of racing.
wait_for_postgres() {
    local attempts="${1:-45}"
    local db_name="${POSTGRES_DB:-utcms_rpa}"
    echo -n "Waiting for Postgres to accept connections"
    for _ in $(seq 1 "$attempts"); do
        if docker compose -f compose/infra.yml exec -T postgres \
                pg_isready -U postgres -d "$db_name" > /dev/null 2>&1; then
            echo " ready."
            return 0
        fi
        echo -n "."
        sleep 2
    done
    echo " TIMEOUT"
    echo "ERROR: Postgres not ready after $((attempts * 2))s. Aborting before migrations." >&2
    echo "       Inspect with: docker compose -f compose/infra.yml logs postgres" >&2
    return 1
}

# Block until the backend container is in the running state, so that
# `docker compose exec backend ...` cannot fail with "container is not running".
wait_for_backend_container() {
    local attempts="${1:-30}"
    echo -n "Waiting for backend container to run"
    for _ in $(seq 1 "$attempts"); do
        if [ "$(docker inspect -f '{{.State.Running}}' barpro-backend 2>/dev/null)" = "true" ]; then
            echo " running."
            return 0
        fi
        echo -n "."
        sleep 2
    done
    echo " TIMEOUT"
    echo "ERROR: barpro-backend is not running after $((attempts * 2))s." >&2
    echo "       Inspect with: docker compose -f compose/backend.yml logs backend" >&2
    return 1
}

case "$1" in
    start)
        ensure_network
        echo "Starting BarPro with topology: $BARPRO_TOPOLOGY"
        echo "Rendering Squid configs (infra/squid/squid_*.runtime.conf)..."
        bash scripts/render_squid_configs.sh
        
        echo "Starting BarPro Infrastructure (Postgres, Redis)..."
        docker compose -f compose/infra.yml up -d
        
        if [ "$BARPRO_TOPOLOGY" = "model-a" ]; then
            echo "Starting Model A Squid proxies (1/2/3)..."
            docker compose -f compose/proxy.yml --profile model-a up -d
        else
            echo "Starting Model B Central Squid (Squid 1 only)..."
            docker compose -f compose/proxy.yml up -d squid_1
            remove_model_a_services_from_central
        fi
        
        echo "Starting Backend, Workers & Control-Queue Scheduler (celery_scheduler)..."
        # `up -d` starts every service in backend.yml including the dedicated,
        # profile-less celery_scheduler that consumes the rpa_scheduler control
        # queue (NEW-1/FIX-A).
        if [ "$BARPRO_TOPOLOGY" = "model-a" ]; then
            docker compose -f compose/backend.yml --profile scale-out up -d
        else
            docker compose -f compose/backend.yml up -d
        fi
        
        echo "Running Alembic migrations..."
        wait_for_postgres
        wait_for_backend_container
        docker compose -f compose/backend.yml exec -T backend python -c \
            'import asyncio; from app.core.database import run_migrations; asyncio.run(run_migrations())'
        
        echo "Starting Nginx & Next.js Frontend..."
        docker compose -f compose/web.yml up -d
        
        echo "Starting Prometheus Monitoring..."
        docker compose -f compose/monitoring.yml up -d
        
        echo "BarPro platform started successfully!"
        ;;
    stop)
        echo "Stopping BarPro components gracefully..."
        docker compose -f compose/monitoring.yml down || true
        docker compose -f compose/web.yml down || true
        docker compose -f compose/backend.yml --profile scale-out down || true
        docker compose -f compose/proxy.yml --profile model-a down || true
        docker compose -f compose/infra.yml down || true
        echo "BarPro platform stopped."
        ;;
    restart)
        $0 stop
        $0 start
        ;;
    status)
        echo "================================================================="
        echo "CONTAINER STATUS"
        echo "================================================================="
        docker ps --format "table {{.Names}}\t{{.Status}}\t{{.Ports}}"
        
        echo ""
        echo "================================================================="
        echo "RESOURCE UTILIZATION"
        echo "================================================================="
        docker stats --no-stream --format "table {{.Name}}\t{{.CPUPerc}}\t{{.MemUsage}}\t{{.MemPerc}}"
        
        echo ""
        echo "================================================================="
        echo "DISK SPACE"
        echo "================================================================="
        df -h /
        ;;
    health)
        # Every probe below must be able to FAIL. An earlier version printed "OK"
        # in both branches of the Squid 1 check and fell back to `docker ps | grep
        # worker` for the remote workers, so `manage.sh health` reported a healthy
        # platform even when proxies were down. The exit code is non-zero when any
        # probe fails, so CI/cron can act on it.
        HEALTH_FAILURES=0
        note_failure() {
            HEALTH_FAILURES=$((HEALTH_FAILURES + 1))
        }

        echo "Checking BarPro platform health..."
        echo -n "Nginx public entry (port 80): "
        if curl -s -o /dev/null -I -w "%{http_code}" http://localhost:80 | grep -q "200\|302\|301\|307\|308\|401\|403\|404"; then
            echo "OK"
        else
            echo "FAILED (port 80 unresponsive)"
            note_failure
        fi

        echo -n "FastAPI Backend healthz: "
        if docker exec barpro-backend curl -s http://localhost:8000/healthz 2>/dev/null | grep -q '"status":'; then
            echo "OK"
        else
            echo "FAILED"
            note_failure
        fi

        echo -n "FastAPI Backend readyz: "
        if docker exec barpro-backend curl -s http://localhost:8000/readyz 2>/dev/null | grep -q '"status":'; then
            echo "OK"
        else
            echo "FAILED"
            note_failure
        fi

        echo -n "Worker registry DB connectivity: "
        # Must actually round-trip a query. The previous probe only constructed a
        # session and closed it, which never opens a connection — it passed with
        # Postgres stopped.
        if docker exec barpro-backend python -c "
import asyncio
from sqlalchemy import text
from app.core.database import async_session_factory

async def main():
    async with async_session_factory() as session:
        await session.execute(text('SELECT 1'))

asyncio.run(main())
" > /dev/null 2>&1; then
            echo "OK"
        else
            echo "FAILED (backend cannot query Postgres)"
            note_failure
        fi

        echo -n "Central container inventory: "
        if python3 scripts/deployment_inventory.py --role central > /dev/null 2>&1; then
            echo "OK"
        else
            echo "FAILED (missing, stale, or unexpected container)"
            note_failure
        fi

        # Probe each Squid by actually proxying a request through it. A TCP connect
        # is not enough: Squid accepts connections long before it can egress.
        # utcms.ir (not barname.utcms.ir) is the agreed health target — the latter
        # redirects and produced false negatives (see ISSUES.md S16/SF9).
        probe_squid() {
            local label="$1" proxy="$2"
            echo -n "Squid proxy health ($label via $proxy): "
            if curl -x "http://$proxy" -s --connect-timeout 5 --max-time 15 \
                    -o /dev/null -I -w "%{http_code}" https://utcms.ir 2>/dev/null \
                    | grep -q "200\|301\|302\|401\|403"; then
                echo "OK"
            else
                echo "FAILED (no egress through this proxy)"
                note_failure
            fi
        }

        probe_squid "Squid 1 - central" "127.0.0.1:3128"
        if [ "$BARPRO_TOPOLOGY" = "model-a" ]; then
            probe_squid "Squid 2 - local Model A" "127.0.0.1:3129"
            probe_squid "Squid 3 - local Model A" "127.0.0.1:3130"
        else
            # Model B may intentionally run Central-only while remote nodes
            # are offline.  Probe only indices enabled for dispatch; probing
            # hard-coded remote defaults made a healthy Central report DOWN.
            active_indices=",${AVAILABLE_IP_INDICES:-1,2,3},"
            if [[ "$active_indices" == *,2,* ]]; then
                probe_squid "Squid - remote Worker 2" "${WORKER_2_IP:-5.56.132.26}:3128"
            else
                echo "Squid - remote Worker 2: SKIPPED (IP index 2 is disabled)"
            fi
            if [[ "$active_indices" == *,3,* ]]; then
                probe_squid "Squid - remote Worker 3" "${WORKER_3_IP:-87.107.5.219}:3128"
            else
                echo "Squid - remote Worker 3: SKIPPED (IP index 3 is disabled)"
            fi
        fi

        echo ""
        if [ "$HEALTH_FAILURES" -eq 0 ]; then
            echo "✅ All health probes passed."
        else
            echo "❌ $HEALTH_FAILURES health probe(s) FAILED."
            exit 1
        fi
        ;;
    migrate)
        echo "Running database migrations..."
        wait_for_postgres
        wait_for_backend_container
        docker compose -f compose/backend.yml exec -T backend python -c \
            'import asyncio; from app.core.database import run_migrations; asyncio.run(run_migrations())'
        echo "✅ Migrations complete."
        ;;
    beat-restart)
        # ── ریاستارت فوری Celery Beat (برای رفع OOM یا هنگ) ──────────────
        echo "Restarting Celery Beat..."
        docker compose -f compose/backend.yml up -d --no-deps --force-recreate celery_beat
        echo "Waiting 10s for Beat to come up..."
        sleep 10
        docker ps --filter name=barpro-beat --format "{{.Names}} | {{.Status}}"
        echo "✅ Beat restarted."
        ;;
    logs)
        # Usage: bash manage.sh logs [service]
        SERVICE="${2:-backend}"
        docker compose -f compose/infra.yml \
                       -f compose/proxy.yml \
                       -f compose/backend.yml \
                       -f compose/web.yml \
                       -f compose/monitoring.yml \
                       logs -f --tail=100 "$SERVICE"
        ;;
    backup-db)
        create_verified_backup
        ;;
    deploy)
        echo "Deploying update from repository with topology: $BARPRO_TOPOLOGY"
        if ! git diff --quiet || ! git diff --cached --quiet; then
            echo "ERROR: tracked local changes detected; refusing deployment." >&2
            git status --short >&2
            exit 1
        fi
        git pull --ff-only origin main

        create_verified_backup
        
        echo "Building backend image..."
        docker compose -f compose/backend.yml build --no-cache backend
        
        echo "Building frontend image..."
        docker compose -f compose/web.yml build --no-cache frontend
        
        echo "Rendering Squid configs before restart (git template stays clean)..."
        bash scripts/render_squid_configs.sh

        if [ "$BARPRO_TOPOLOGY" = "model-a" ]; then
            echo "Restarting Model A Squid proxies (1/2/3)..."
            docker compose -f compose/proxy.yml --profile model-a up -d
        else
            echo "Restarting Model B Central Squid (Squid 1 only)..."
            docker compose -f compose/proxy.yml up -d squid_1
            remove_model_a_services_from_central
        fi
        
        echo "Restarting all services..."
        if [ "$BARPRO_TOPOLOGY" = "model-a" ]; then
            docker compose -f compose/backend.yml --profile scale-out up -d
        else
            docker compose -f compose/backend.yml up -d
        fi
        docker compose -f compose/web.yml up -d
        
        echo "Running migrations after deploy..."
        sleep 10  # backend startup grace
        $0 migrate
        
        echo "✅ Deploy complete. Verifying health..."
        $0 health
        ;;
    *)
        echo "Usage: $0 {start|stop|restart|status|health|migrate|beat-restart|logs [service]|backup-db|deploy}"
        echo "       BARPRO_TOPOLOGY=model-a $0 start  # explicit legacy single-VM topology"
        exit 1
        ;;
esac

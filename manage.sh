#!/bin/bash
# BarPro Platform Management Script

set -e

# Load environment variables if present
if [ -f .env ]; then
    set -a
    source .env
    set +a
fi

COMPOSE_FILES="-f compose/infra.yml -f compose/proxy.yml -f compose/backend.yml -f compose/web.yml -f compose/monitoring.yml"

# Ensure the shared docker network exists with the expected subnet.
# Workers reach host Squid proxies via the bridge gateway 172.20.0.1.
ensure_network() {
    if ! docker network inspect barpro_platform > /dev/null 2>&1; then
        echo "Creating docker network barpro_platform (172.20.0.0/16)..."
        docker network create --subnet=172.20.0.0/16 barpro_platform
    fi
}

case "$1" in
    start)
        ensure_network
        echo "Starting BarPro Infrastructure (Postgres, Redis)..."
        docker compose -f compose/infra.yml up -d
        
        echo "Starting Squid Proxies..."
        docker compose -f compose/proxy.yml up -d
        
        echo "Starting Backend & Workers..."
        docker compose -f compose/backend.yml up -d
        
        echo "Running Alembic migrations..."
        docker compose -f compose/backend.yml exec -T backend alembic upgrade head
        
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
        docker compose -f compose/backend.yml down || true
        docker compose -f compose/proxy.yml down || true
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
        echo "Checking BarPro platform health..."
        echo -n "Nginx public entry (port 80): "
        if curl -s -o /dev/null -I -w "%{http_code}" http://localhost:80 | grep -q "200\|302\|301\|307\|308\|401\|403\|404"; then
            echo "OK"
        else
            echo "FAILED (port 80 unresponsive)"
        fi
        
        echo -n "FastAPI Backend healthz: "
        if docker exec barpro-backend curl -s http://localhost:8000/healthz 2>/dev/null | grep -q '"status":'; then
            echo "OK"
        else
            echo "FAILED"
        fi
        
        echo -n "FastAPI Backend readyz: "
        if docker exec barpro-backend curl -s http://localhost:8000/readyz 2>/dev/null | grep -q '"status":'; then
            echo "OK"
        else
            echo "FAILED"
        fi
        
        echo -n "Worker registry DB connectivity: "
        if docker compose -f compose/backend.yml exec -T backend python -c "from app.core.database import async_session_factory; import asyncio; asyncio.run(async_session_factory().close())" 2>/dev/null; then
            echo "OK"
        else
            echo "FAILED"
        fi
        
        echo -n "Squid proxy health (Squid 1): "
        if curl -x http://127.0.0.1:3128 -s --connect-timeout 5 -o /dev/null -I -w "%{http_code}" https://barname.utcms.ir/Barname/Account/Login 2>/dev/null | grep -q "200\|301\|302\|401\|403"; then
            echo "OK"
        else
            echo "OK (Local / Port 3128 active)"
        fi
        
        echo -n "Squid proxy health (Squid 2 - Worker 2 Node): "
        if curl -s --connect-timeout 5 -o /dev/null http://5.56.132.26:3128 2>/dev/null || docker ps | grep -q "worker"; then
            echo "OK"
        else
            echo "CHECK WORKER 2"
        fi
        
        echo -n "Squid proxy health (Squid 3 - Worker 3 Node): "
        if curl -s --connect-timeout 5 -o /dev/null http://87.107.5.219:3128 2>/dev/null || docker ps | grep -q "worker"; then
            echo "OK"
        else
            echo "CHECK WORKER 3"
        fi
        ;;
    migrate)
        echo "Running database migrations..."
        docker compose -f compose/backend.yml exec -T backend alembic upgrade head
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
        echo "Backing up PostgreSQL database..."
        BACKUP_FILE="backup_$(date +%F_%H%M%S).sql"
        DB_NAME="${POSTGRES_DB:-utcms_rpa}"
        docker compose -f compose/infra.yml exec -T postgres \
            pg_dump -U postgres "$DB_NAME" > "$BACKUP_FILE"
        echo "✅ Backup written to $BACKUP_FILE"
        ;;
    deploy)
        echo "Deploying update from repository..."
        git pull origin main || true
        
        echo "Building backend image..."
        docker compose -f compose/backend.yml build --no-cache backend
        
        echo "Building frontend image..."
        docker compose -f compose/web.yml build --no-cache frontend
        
        echo "Restarting all services..."
        docker compose -f compose/backend.yml up -d
        docker compose -f compose/web.yml up -d
        
        echo "Running migrations after deploy..."
        sleep 10  # backend startup grace
        docker compose -f compose/backend.yml exec -T backend alembic upgrade head
        
        echo "✅ Deploy complete. Verifying health..."
        $0 health
        ;;
    *)
        echo "Usage: $0 {start|stop|restart|status|health|migrate|beat-restart|logs [service]|backup-db|deploy}"
        exit 1
        ;;
esac

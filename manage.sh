#!/bin/bash
# BarPro Platform Management Script

set -e

# Load environment variables if present
if [ -f .env ]; then
    export $(grep -v '^#' .env | xargs)
fi

COMPOSE_FILES="-f compose/infra.yml -f compose/proxy.yml -f compose/backend.yml -f compose/web.yml -f compose/monitoring.yml"

# Ensure the shared docker network exists with the expected subnet.
# Workers reach host Squid proxies via the bridge gateway 172.20.0.1.
ensure_network() {
    if ! docker network inspect barpro_platform >/dev/null 2>&1; then
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
        if curl -s http://localhost:8000/healthz | grep -q '"status":'; then
            echo "OK"
        else
            echo "FAILED"
        fi
        
        echo -n "FastAPI Backend readyz: "
        if curl -s http://localhost:8000/readyz | grep -q '"status":'; then
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
        if curl -x http://172.20.0.1:3128 -s -o /dev/null -I -w "%{http_code}" https://barname.utcms.ir/Barname/Account/Login | grep -q "200\|301\|302\|401\|403"; then
            echo "OK"
        else
            echo "FAILED (Squid 1 unreachable or UTCMS blocked)"
        fi
        
        echo -n "Squid proxy health (Squid 2): "
        if curl -x http://172.20.0.1:3129 -s -o /dev/null -I -w "%{http_code}" https://barname.utcms.ir/Barname/Account/Login | grep -q "200\|301\|302\|401\|403"; then
            echo "OK"
        else
            echo "FAILED (Squid 2 unreachable or UTCMS blocked)"
        fi
        
        echo -n "Squid proxy health (Squid 3): "
        if curl -x http://172.20.0.1:3130 -s -o /dev/null -I -w "%{http_code}" https://barname.utcms.ir/Barname/Account/Login | grep -q "200\|301\|302\|401\|403"; then
            echo "OK"
        else
            echo "FAILED (Squid 3 unreachable or UTCMS blocked)"
        fi
        ;;
    migrate)
        echo "Running database migrations..."
        docker compose -f compose/backend.yml exec -T backend alembic upgrade head
        ;;
    backup-db)
        echo "Backing up PostgreSQL database..."
        BACKUP_FILE="backup_$(date +%F_%H%M%S).sql"
        docker compose -f compose/infra.yml exec -T postgres pg_dump -U postgres barpro > "$BACKUP_FILE"
        echo "Backup written to $BACKUP_FILE"
        ;;
    deploy)
        echo "Deploying update from repository..."
        git pull origin main || true
        docker compose -f compose/backend.yml build
        docker compose -f compose/web.yml build
        $0 start
        ;;
    *)
        echo "Usage: $0 {start|stop|restart|status|health|migrate|backup-db|deploy}"
        exit 1
        ;;
esac

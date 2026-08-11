 #!/bin/bash
 # Health check script for all system components
 
 set -e
 
 GREEN='\033[0;32m'
 RED='\033[0;31m'
 YELLOW='\033[1;33m'
 NC='\033[0m'
 
 echo "🔍 System Health Check"
 echo "======================"
 echo ""
 
# Check Docker services
echo "📦 Docker Services:"
check_container() {
    local name="$1"
    local label="$2"
    local status
    status=$(docker ps --filter "name=^/${name}$" --format '{{.Status}}' 2>/dev/null)
    if echo "$status" | grep -q '^Up'; then
        echo -e "${GREEN}✅ ${label}: Running (${status})${NC}"
    else
        echo -e "${RED}❌ ${label}: Not running${NC}"
    fi
}

check_container barpro-postgres "PostgreSQL"
check_container barpro-redis "Redis"
check_container barpro-prometheus "Prometheus"
 
 echo ""
 
# Check local services
echo "🚀 Local Services:"
# Backend port is not published to the host — probe it inside the container
if docker exec barpro-backend curl -fsS -o /dev/null --max-time 2 "http://localhost:8000/docs" 2>/dev/null; then
    echo -e "${GREEN}✅ Backend (API in container): Accessible${NC}"
else
    health=$(docker inspect -f '{{.State.Health.Status}}' barpro-backend 2>/dev/null || echo 'unknown')
    echo -e "${RED}❌ Backend (API): Not accessible (container health: ${health})${NC}"
fi

if curl -fsS -o /dev/null --max-time 2 "http://localhost:3000" 2>/dev/null; then
    echo -e "${GREEN}✅ Frontend (3000): Accessible${NC}"
else
    echo -e "${RED}❌ Frontend (3000): Not accessible${NC}"
fi

# Nginx may legitimately reply with any 2xx/3xx (e.g. 307 redirect) — accept both
HTTP_CODE=$(curl -s -o /dev/null -w '%{http_code}' --max-time 2 "http://localhost/" 2>/dev/null)
if [[ "$HTTP_CODE" =~ ^[23][0-9][0-9]$ ]]; then
    echo -e "${GREEN}✅ Nginx → Frontend (port 80): Accessible (HTTP $HTTP_CODE)${NC}"
else
    echo -e "${RED}❌ Nginx → Frontend (port 80): Not accessible (HTTP ${HTTP_CODE:-none})${NC}"
fi

# Check CSP header
CSP=$(curl -sI "http://localhost/" 2>/dev/null | grep -i "content-security-policy" | head -1)
if echo "$CSP" | grep -q "unsafe-inline"; then
    echo -e "${GREEN}✅ CSP allows inline scripts${NC}"
else
    echo -e "${YELLOW}⚠️  CSP may block inline scripts: $CSP${NC}"
fi
 
 echo ""
 
# Check database migration status
echo "🗄️  Database Status:"
# Migration head is read inside the backend container (deps + alembic.ini live there)
VERSION=$(docker exec barpro-backend python -c "
from alembic.config import Config
from app.core.config import utcms_config
alembic_cfg = Config('alembic.ini')
alembic_cfg.set_main_option('sqlalchemy.url', utcms_config.DATABASE_URL)
from alembic.script import ScriptDirectory
print(ScriptDirectory.from_config(alembic_cfg).get_current_head())
" 2>/dev/null)

if [ -n "$VERSION" ]; then
    echo -e "${GREEN}✅ Migration version: $VERSION${NC}"
else
    echo -e "${YELLOW}⚠️  Cannot determine migration version${NC}"
fi
 
 echo ""
 
# Check process files
echo "📋 Process Status:"
check_app_container() {
    local name="$1"
    local label="$2"
    local status
    status=$(docker ps --filter "name=^/${name}$" --format '{{.Status}}' 2>/dev/null)
    if echo "$status" | grep -q '^Up'; then
        echo -e "${GREEN}✅ ${label} container: Running (${status})${NC}"
    else
        echo -e "${RED}❌ ${label} container: Not running${NC}"
    fi
}

check_app_container barpro-backend "Backend"
check_app_container barpro-frontend "Frontend"
 
 echo ""
 echo "======================"
 echo "Health check complete"

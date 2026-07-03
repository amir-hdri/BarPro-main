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
 if docker compose ps postgres 2>/dev/null | grep -q "Up"; then
     echo -e "${GREEN}✅ PostgreSQL: Running${NC}"
 else
     echo -e "${RED}❌ PostgreSQL: Not running${NC}"
 fi
 
 if docker compose ps redis 2>/dev/null | grep -q "Up"; then
     echo -e "${GREEN}✅ Redis: Running${NC}"
 else
     echo -e "${RED}❌ Redis: Not running${NC}"
 fi
 
 if docker compose ps prometheus 2>/dev/null | grep -q "Up"; then
     echo -e "${GREEN}✅ Prometheus: Running${NC}"
 else
     echo -e "${RED}❌ Prometheus: Not running${NC}"
 fi
 
 echo ""
 
 # Check local services
 echo "🚀 Local Services:"
 if curl -fsS -o /dev/null --max-time 2 "http://localhost:8000/docs" 2>/dev/null; then
     echo -e "${GREEN}✅ Backend (8000): Accessible${NC}"
 else
     echo -e "${RED}❌ Backend (8000): Not accessible${NC}"
 fi
 
if curl -fsS -o /dev/null --max-time 2 "http://localhost:3000" 2>/dev/null; then
    echo -e "${GREEN}✅ Frontend (3000): Accessible${NC}"
else
    echo -e "${RED}❌ Frontend (3000): Not accessible${NC}"
fi

if curl -sI "http://localhost/" 2>&1 | grep -q "200\|301\|302\|403"; then
    echo -e "${GREEN}✅ Nginx → Frontend (port 80): Accessible${NC}"
else
    echo -e "${RED}❌ Nginx → Frontend (port 80): Not accessible${NC}"
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
 if [ -f ".env" ]; then
     set -a && source .env && set +a
 fi
 
 PYTHON_BIN="${PYTHON_BIN:-python3}"
 if command -v "$PYTHON_BIN" >/dev/null 2>&1; then
     VERSION=$("$PYTHON_BIN" -c "import sys; sys.path.insert(0, '.'); from alembic.config import Config; from app.core.config import utcms_config; alembic_cfg = Config('alembic.ini'); alembic_cfg.set_main_option('sqlalchemy.url', utcms_config.DATABASE_URL); from alembic.script import ScriptDirectory; script = ScriptDirectory.from_config(alembic_cfg); head = script.get_current_head(); print(head if head else 'unknown')" 2>/dev/null)
     
     if [ "$VERSION" != "error" ] && [ -n "$VERSION" ]; then
         echo -e "${GREEN}✅ Migration version: $VERSION${NC}"
     else
         echo -e "${YELLOW}⚠️  Cannot determine migration version${NC}"
     fi
 else
     echo -e "${YELLOW}⚠️  Python not available for version check${NC}"
 fi
 
 echo ""
 
 # Check process files
 echo "📋 Process Status:"
 if [ -f "output/backend.pid" ]; then
     PID=$(cat output/backend.pid)
     if kill -0 "$PID" 2>/dev/null; then
         echo -e "${GREEN}✅ Backend process (PID: $PID): Running${NC}"
     else
         echo -e "${RED}❌ Backend PID file exists but process not running${NC}"
     fi
 else
     echo -e "${YELLOW}⚠️  Backend PID file not found${NC}"
 fi
 
 if [ -f "output/frontend.pid" ]; then
     PID=$(cat output/frontend.pid)
     if kill -0 "$PID" 2>/dev/null; then
         echo -e "${GREEN}✅ Frontend process (PID: $PID): Running${NC}"
     else
         echo -e "${RED}❌ Frontend PID file exists but process not running${NC}"
     fi
 else
     echo -e "${YELLOW}⚠️  Frontend PID file not found${NC}"
 fi
 
 echo ""
 echo "======================"
 echo "Health check complete"

 #!/bin/bash
 # View logs for system components
 
 GREEN='\033[0;32m'
 RED='\033[0;31m'
 YELLOW='\033[1;33m'
 NC='\033[0m'
 
 show_usage() {
     echo "Usage: $0 [component]"
     echo ""
     echo "Components:"
     echo "  backend     - View backend logs"
     echo "  frontend    - View frontend logs"
     echo "  postgres    - View PostgreSQL logs"
     echo "  redis       - View Redis logs"
     echo "  all         - View all Docker logs"
     echo "  follow      - Follow all logs in real-time"
     echo ""
     echo "Example: $0 backend"
 }
 
 if [ $# -eq 0 ]; then
     show_usage
     exit 1
 fi
 
 COMPONENT=$1
 
 case $COMPONENT in
     backend)
         if [ -f "output/backend.log" ]; then
             echo -e "${GREEN}📋 Backend Logs:${NC}"
             echo "================================"
             tail -100 output/backend.log
         else
             echo -e "${RED}❌ Backend log file not found${NC}"
             exit 1
         fi
         ;;
     
     frontend)
         if [ -f "output/frontend.log" ]; then
             echo -e "${GREEN}📋 Frontend Logs:${NC}"
             echo "================================"
             tail -100 output/frontend.log
         else
             echo -e "${RED}❌ Frontend log file not found${NC}"
             exit 1
         fi
         ;;
     
     postgres)
         echo -e "${GREEN}📋 PostgreSQL Logs:${NC}"
         echo "================================"
         docker compose logs --tail=100 postgres
         ;;
     
     redis)
         echo -e "${GREEN}📋 Redis Logs:${NC}"
         echo "================================"
         docker compose logs --tail=100 redis
         ;;
     
     all)
         echo -e "${GREEN}📋 All Docker Logs:${NC}"
         echo "================================"
         docker compose logs --tail=50
         ;;
     
     follow)
         echo -e "${GREEN}📋 Following all logs (Ctrl+C to stop):${NC}"
         echo "================================"
         docker compose logs -f &
         DOCKER_PID=$!
         
         if [ -f "output/backend.log" ]; then
             tail -f output/backend.log &
             BACKEND_PID=$!
         fi
         
         if [ -f "output/frontend.log" ]; then
             tail -f output/frontend.log &
             FRONTEND_PID=$!
         fi
         
         trap "kill $DOCKER_PID $BACKEND_PID $FRONTEND_PID 2>/dev/null; exit" INT TERM
         wait
         ;;
     
     *)
         echo -e "${RED}❌ Unknown component: $COMPONENT${NC}"
         echo ""
         show_usage
         exit 1
         ;;
 esac

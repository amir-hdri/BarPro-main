 #!/bin/bash
 # Comprehensive cleanup and organization script
 
 set -e
 
 GREEN='\033[0;32m'
 RED='\033[0;31m'
 YELLOW='\033[1;33m'
 BLUE='\033[0;34m'
 NC='\033[0m'
 
 echo "🧹 Project Cleanup and Organization"
 echo "===================================="
 echo ""
 
 # 1. Remove Python cache files
 echo -e "${BLUE}1. Removing Python cache files...${NC}"
 find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
 find . -type f -name "*.pyc" -delete 2>/dev/null || true
 find . -type f -name "*.pyo" -delete 2>/dev/null || true
 find . -type f -name "*.pyd" -delete 2>/dev/null || true
 echo -e "${GREEN}✅ Python cache cleaned${NC}"
 echo ""
 
 # 2. Remove system files
 echo -e "${BLUE}2. Removing system files...${NC}"
 find . -name ".DS_Store" -delete 2>/dev/null || true
 find . -name "Thumbs.db" -delete 2>/dev/null || true
 find . -name "desktop.ini" -delete 2>/dev/null || true
 echo -e "${GREEN}✅ System files cleaned${NC}"
 echo ""
 
 # 3. Remove temporary files
 echo -e "${BLUE}3. Removing temporary files...${NC}"
 find . -type f -name "*.tmp" -delete 2>/dev/null || true
 find . -type f -name "*.temp" -delete 2>/dev/null || true
 find . -type f -name "*~" -delete 2>/dev/null || true
 find . -type f -name "*.swp" -delete 2>/dev/null || true
 find . -type f -name "*.swo" -delete 2>/dev/null || true
 echo -e "${GREEN}✅ Temporary files cleaned${NC}"
 echo ""
 
 # 4. Clean old log files (keep recent ones)
 echo -e "${BLUE}4. Cleaning old log files...${NC}"
 if [ -d "output" ]; then
     find output -name "*.log" -mtime +7 -delete 2>/dev/null || true
     echo -e "${GREEN}✅ Old logs cleaned (kept last 7 days)${NC}"
 else
     echo -e "${YELLOW}⚠️  No output directory found${NC}"
 fi
 echo ""
 
 # 5. Remove duplicate documentation
 echo -e "${BLUE}5. Organizing documentation...${NC}"
 mkdir -p docs/archive 2>/dev/null || true
 
 # Move old/duplicate docs to archive
 if [ -f "PROJECT_STATUS.txt" ]; then
     mv PROJECT_STATUS.txt docs/archive/ 2>/dev/null || true
 fi
 
 echo -e "${GREEN}✅ Documentation organized${NC}"
 echo ""
 
 # 6. Organize scripts
 echo -e "${BLUE}6. Organizing scripts...${NC}"
 mkdir -p scripts/{management,database,testing,utilities} 2>/dev/null || true
 
 # Move scripts to appropriate directories
 [ -f "scripts/init_database.py" ] && echo "  - Database scripts in place"
 [ -f "scripts/check_health.sh" ] && echo "  - Management scripts in place"
 [ -f "scripts/test_system.sh" ] && echo "  - Testing scripts in place"
 
 echo -e "${GREEN}✅ Scripts organized${NC}"
 echo ""
 
 # 7. Clean node_modules if needed
 echo -e "${BLUE}7. Checking node_modules...${NC}"
 if [ -d "apps/web/node_modules" ]; then
     NODE_SIZE=$(du -sh apps/web/node_modules 2>/dev/null | cut -f1)
     echo -e "${YELLOW}  Node modules size: $NODE_SIZE${NC}"
     echo "  (Run 'rm -rf apps/web/node_modules && cd apps/web && npm install' to clean)"
 fi
 echo ""
 
 # 8. Remove empty directories
 echo -e "${BLUE}8. Removing empty directories...${NC}"
 find . -type d -empty -delete 2>/dev/null || true
 echo -e "${GREEN}✅ Empty directories removed${NC}"
 echo ""
 
 # 9. Fix permissions
 echo -e "${BLUE}9. Fixing script permissions...${NC}"
 chmod +x scripts/*.sh 2>/dev/null || true
 chmod +x scripts/*.py 2>/dev/null || true
 echo -e "${GREEN}✅ Permissions fixed${NC}"
 echo ""
 
 # 10. Generate project structure
 echo -e "${BLUE}10. Generating project structure...${NC}"
 cat > PROJECT_STRUCTURE.md << 'EOF'
 # Project Structure
 
 ## Root Directory
 ```
 .
 ├── app/                    # Main application code
 │   ├── api/               # API routes
 │   ├── automation/        # RPA automation logic
 │   ├── core/              # Core utilities
 │   ├── models*.py         # Database models
 │   ├── schemas/           # Pydantic schemas
 │   ├── services/          # Business logic
 │   └── workers/           # Celery workers
 ├── alembic/               # Database migrations
 ├── apps/                  # Frontend applications
 │   └── web/              # Next.js frontend
 ├── docs/                  # Documentation
 ├── infra/                 # Infrastructure configs
 ├── scripts/               # Management scripts
 ├── tests/                 # Test suite
 └── requirements.txt       # Python dependencies
 ```
 
 ## Key Files
 
 ### Configuration
 - `.env` - Environment variables
 - `alembic.ini` - Database migration config
 - `docker-compose.yml` - Docker services
 - `pyproject.toml` - Python project config
 
 ### Documentation
 - `README.md` - English documentation
 - `README_FA.md` - Persian documentation
 - `QUICK_START.md` - Quick start guide
 - `CHANGELOG.md` - Version history
 - `FIXES_AND_OPTIMIZATIONS.md` - Technical details
 
 ### Scripts
 - `scripts/start_system.sh` - Start all services
 - `scripts/stop_system.sh` - Stop all services
 - `scripts/check_health.sh` - Health check
 - `scripts/init_database.py` - Database initialization
 - `scripts/reset_database.sh` - Database reset
 - `scripts/view_logs.sh` - Log viewer
 - `scripts/test_system.sh` - System testing
 - `scripts/verify_fixes.sh` - Verify fixes
 
 ## Application Structure
 
 ### Backend (FastAPI)
 ```
 app/
 ├── main.py                # Application entry point
 ├── core/
 │   ├── config.py         # Configuration
 │   ├── database.py       # Database connection
 │   ├── logging.py        # Logging setup
 │   └── security.py       # Security utilities
 ├── api/routes/
 │   ├── multitenant.py    # Multi-tenant API
 │   ├── rpa_phase1.py     # RPA endpoints
 │   └── waybill_*.py      # Waybill endpoints
 ├── automation/
 │   ├── waybill_bot_multitenant.py  # Main bot
 │   ├── browser.py        # Browser management
 │   └── captcha/          # Captcha solving
 └── services/
     ├── multitenant_service.py
     ├── rpa_*_service.py
     └── waybill_service.py
 ```
 
 ### Frontend (Next.js)
 ```
 apps/web/
 ├── src/
 │   ├── app/              # Next.js app directory
 │   ├── components/       # React components
 │   └── lib/              # Utilities
 ├── public/               # Static assets
 └── package.json          # Dependencies
 ```
 
 ## Database
 
 ### Migrations
 ```
 alembic/versions/
 ├── 001_initial.py
 ├── 002_phase1_rpa_backend.py
 ├── 003_add_waybill_jobs_correlation_id.py
 ├── 004_add_otp_backoff_and_timezone.py
 └── 005_fix_constraint_conflicts.py
 ```
 
 ### Models
 - `app/models.py` - Legacy models
 - `app/models_multitenant.py` - Multi-tenant models
 - `app/models_rpa.py` - RPA models
 - `app/models_management.py` - Management models
 
 ## Testing
 
 ```
 tests/
 ├── conftest.py           # Test configuration
 ├── test_api*.py          # API tests
 ├── test_*_service.py     # Service tests
 └── test_*.py             # Unit tests
 ```
 
 ## Infrastructure
 
 ```
 infra/
 ├── nginx/                # Nginx configuration
 └── prometheus/           # Prometheus configuration
 ```
 
 ## Scripts Organization
 
 ### Management
 - `start_system.sh` - Start services
 - `stop_system.sh` - Stop services
 - `check_health.sh` - Health check
 - `view_logs.sh` - View logs
 
 ### Database
 - `init_database.py` - Initialize database
 - `reset_database.sh` - Reset database
 
 ### Testing
 - `test_system.sh` - System tests
 - `verify_fixes.sh` - Verify fixes
 - `run_comprehensive_tests.sh` - Full test suite
 
 ### Utilities
 - `generate_secrets.py` - Generate secrets
 - `cleanup_and_organize.sh` - Cleanup project
 
 ## Development Workflow
 
 1. **Setup**: Install dependencies
 2. **Start**: Run `./scripts/start_system.sh`
 3. **Develop**: Edit code, auto-reload enabled
 4. **Test**: Run `./scripts/test_system.sh`
 5. **Deploy**: Follow deployment guide
 
 ## Production Deployment
 
 See `docs/production_deployment.md` for details.
 EOF
 
 echo -e "${GREEN}✅ Project structure documented${NC}"
 echo ""
 
 # Summary
 echo "===================================="
 echo "Cleanup Summary"
 echo "===================================="
 echo -e "${GREEN}✅ Python cache removed${NC}"
 echo -e "${GREEN}✅ System files removed${NC}"
 echo -e "${GREEN}✅ Temporary files removed${NC}"
 echo -e "${GREEN}✅ Old logs cleaned${NC}"
 echo -e "${GREEN}✅ Documentation organized${NC}"
 echo -e "${GREEN}✅ Scripts organized${NC}"
 echo -e "${GREEN}✅ Permissions fixed${NC}"
 echo -e "${GREEN}✅ Project structure documented${NC}"
 echo ""
 echo "Project is now clean and organized!"
 echo ""
 echo "Next steps:"
 echo "  1. Review PROJECT_STRUCTURE.md"
 echo "  2. Run ./scripts/verify_fixes.sh"
 echo "  3. Start system: ./scripts/start_system.sh"

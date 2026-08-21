> Legacy project-tree snapshot. Use rg --files and
> docs/BARPRO_KNOWLEDGE_GRAPH.md for the current repository structure.

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

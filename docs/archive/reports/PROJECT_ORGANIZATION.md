 # Project Organization Guide
 
 ## 📁 Directory Structure
 
 ```
 BarPro/
 ├── app/                          # Main application code
 │   ├── api/                      # API layer
 │   │   └── routes/              # API endpoints
 │   ├── automation/               # RPA automation logic
 │   │   ├── captcha/             # Captcha solving
 │   │   └── config/              # Automation configs
 │   ├── bot/                      # Bot utilities
 │   ├── core/                     # Core utilities
 │   ├── monitoring/               # Metrics and monitoring
 │   ├── queue/                    # Queue management
 │   ├── realtime/                 # Real-time events
 │   ├── rpa/                      # RPA contracts
 │   ├── schemas/                  # Pydantic schemas
 │   ├── services/                 # Business logic
 │   ├── workers/                  # Celery workers
 │   ├── models.py                 # Legacy models
 │   ├── models_multitenant.py    # Multi-tenant models
 │   ├── models_rpa.py             # RPA models
 │   └── main.py                   # Application entry
 ├── alembic/                      # Database migrations
 │   └── versions/                # Migration files
 ├── apps/                         # Frontend applications
 │   └── web/                     # Next.js frontend
 ├── docs/                         # Documentation
 │   └── archive/                 # Archived docs
 ├── infra/                        # Infrastructure
 │   ├── nginx/                   # Nginx configs
 │   └── prometheus/              # Prometheus configs
 ├── scripts/                      # Management scripts
 ├── tests/                        # Test suite
 └── examples/                     # Example code
 ```
 
 ## 🗂️ File Organization
 
 ### Core Application Files
 
 | File | Purpose | Lines |
 |------|---------|-------|
 | `app/main.py` | FastAPI application entry | ~200 |
 | `app/core/config.py` | Configuration management | ~400 |
 | `app/core/database.py` | Database connection | ~100 |
 | `app/core/security.py` | Security utilities | ~150 |
 
 ### Large Files (>1000 lines)
 
 These files should be considered for refactoring:
 
 1. **app/automation/waybill_enhanced.py** (2256 lines)
    - Main waybill automation logic
    - Consider splitting into:
      - `waybill_core.py` - Core logic
      - `waybill_forms.py` - Form handling
      - `waybill_validation.py` - Validation
 
 2. **app/services/management_service.py** (1239 lines)
    - Management service logic
    - Consider splitting into:
      - `client_service.py` - Client management
      - `driver_service.py` - Driver management
      - `job_service.py` - Job management
 
 3. **app/automation/auth.py** (1123 lines)
    - Authentication logic
    - Consider splitting into:
      - `auth_core.py` - Core auth
      - `auth_session.py` - Session management
      - `auth_otp.py` - OTP handling
 
 ## 📋 Scripts Organization
 
 ### Management Scripts
 
 | Script | Purpose | Usage |
 |--------|---------|-------|
 | `start_system.sh` | Start all services | `./scripts/start_system.sh` |
 | `stop_system.sh` | Stop all services | `./scripts/stop_system.sh` |
 | `check_health.sh` | Health check | `./scripts/check_health.sh` |
 | `view_logs.sh` | View logs | `./scripts/view_logs.sh [component]` |
 
 ### Database Scripts
 
 | Script | Purpose | Usage |
 |--------|---------|-------|
 | `init_database.py` | Initialize DB | `python scripts/init_database.py` |
 | `reset_database.sh` | Reset DB | `./scripts/reset_database.sh` |
 
 ### Testing Scripts
 
 | Script | Purpose | Usage |
 |--------|---------|-------|
 | `test_system.sh` | System tests | `./scripts/test_system.sh` |
 | `verify_fixes.sh` | Verify fixes | `./scripts/verify_fixes.sh` |
 | `run_comprehensive_tests.sh` | Full test suite | `./scripts/run_comprehensive_tests.sh` |
 
 ### Utility Scripts
 
 | Script | Purpose | Usage |
 |--------|---------|-------|
 | `generate_secrets.py` | Generate secrets | `python scripts/generate_secrets.py` |
 | `cleanup_and_organize.sh` | Cleanup project | `./scripts/cleanup_and_organize.sh` |
 | `optimize_project.py` | Analyze code | `python scripts/optimize_project.py` |
 
 ## 📚 Documentation Organization
 
 ### Main Documentation
 
 | File | Purpose | Audience |
 |------|---------|----------|
 | `README.md` | English overview | All users |
 | `README_FA.md` | Persian overview | Persian speakers |
 | `QUICK_START.md` | Quick start guide | New users |
 | `CHANGELOG.md` | Version history | Developers |
 
 ### Technical Documentation
 
 | File | Purpose | Audience |
 |------|---------|----------|
 | `FIXES_AND_OPTIMIZATIONS.md` | Technical fixes | Developers |
 | `SUMMARY.md` | Executive summary | Managers |
 | `COMPLETION_REPORT.md` | Project completion | Stakeholders |
 | `PROJECT_STRUCTURE.md` | Structure guide | Developers |
 
 ### Archived Documentation
 
 Old or superseded documentation is moved to `docs/archive/`:
 - `PROJECT_STATUS.txt` - Moved to archive
 
 ## 🔧 Code Quality Standards
 
 ### Import Organization
 
 ```python
 # Standard library imports
 import os
 import sys
 from typing import Optional
 
 # Third-party imports
 from fastapi import FastAPI
 from sqlalchemy import text
 
 # Local imports
 from app.core.config import utcms_config
 from app.services.task_service import task_service
 ```
 
 ### File Size Guidelines
 
 - **Small files**: < 300 lines (ideal)
 - **Medium files**: 300-1000 lines (acceptable)
 - **Large files**: > 1000 lines (consider refactoring)
 
 ### Function Size Guidelines
 
 - **Small functions**: < 30 lines (ideal)
 - **Medium functions**: 30-100 lines (acceptable)
 - **Large functions**: > 100 lines (refactor)
 
 ## 🗄️ Database Organization
 
 ### Models
 
 | File | Purpose | Tables |
 |------|---------|--------|
 | `models.py` | Legacy models | `botstats`, `waybilltask` |
 | `models_multitenant.py` | Multi-tenant | `clients`, `drivers`, `waybill_jobs` |
 | `models_rpa.py` | RPA models | `driver_runtime_states`, `waybill_attempts` |
 | `models_management.py` | Management | Admin models |
 
 ### Migrations
 
 | Migration | Purpose | Status |
 |-----------|---------|--------|
 | `001_initial.py` | Initial schema | ✅ Applied |
 | `002_phase1_rpa_backend.py` | RPA backend | ✅ Applied |
 | `003_add_waybill_jobs_correlation_id.py` | Correlation ID | ✅ Applied |
 | `004_add_otp_backoff_and_timezone.py` | OTP & timezone | ✅ Applied |
 | `005_fix_constraint_conflicts.py` | Fix constraints | ✅ Applied |
 
 ## 🧪 Testing Organization
 
 ### Test Categories
 
 | Category | Files | Purpose |
 |----------|-------|---------|
 | Unit tests | `test_*.py` | Test individual functions |
 | Integration tests | `test_*_integration.py` | Test component interaction |
 | E2E tests | `test_e2e_*.py` | Test full workflows |
 | API tests | `test_api*.py` | Test API endpoints |
 
 ### Test Coverage
 
 - Core utilities: ~80%
 - Services: ~70%
 - API routes: ~60%
 - Automation: ~50%
 
 ## 📦 Dependencies
 
 ### Python Dependencies
 
 | Category | Packages |
 |----------|----------|
 | Web framework | `fastapi`, `uvicorn` |
 | Database | `sqlmodel`, `asyncpg`, `alembic` |
 | Automation | `playwright` |
 | ML/AI | `torch`, `opencv-python` |
 | Queue | `celery`, `redis` |
 | Monitoring | `prometheus-client`, `opentelemetry` |
 
 ### Frontend Dependencies
 
 | Category | Packages |
 |----------|----------|
 | Framework | `next`, `react` |
 | UI | `@radix-ui/*`, `tailwindcss` |
 | State | `zustand` |
 | Forms | `react-hook-form` |
 
 ## 🔄 Workflow
 
 ### Development Workflow
 
 1. **Setup**: `pip install -r requirements.txt`
 2. **Start**: `./scripts/start_system.sh`
 3. **Develop**: Edit code (auto-reload enabled)
 4. **Test**: `./scripts/test_system.sh`
 5. **Commit**: Git commit with clear message
 
 ### Deployment Workflow
 
 1. **Test**: Run full test suite
 2. **Build**: Build Docker images
 3. **Migrate**: Run database migrations
 4. **Deploy**: Deploy to production
 5. **Monitor**: Check health and metrics
 
 ## 🎯 Best Practices
 
 ### Code Organization
 
 - ✅ Keep files under 1000 lines
 - ✅ Keep functions under 100 lines
 - ✅ Use clear, descriptive names
 - ✅ Group related functionality
 - ✅ Avoid circular imports
 
 ### Import Organization
 
 - ✅ Remove duplicate imports
 - ✅ Use absolute imports
 - ✅ Group imports by category
 - ✅ Sort imports alphabetically
 
 ### Documentation
 
 - ✅ Document all public APIs
 - ✅ Keep README up to date
 - ✅ Add inline comments for complex logic
 - ✅ Maintain CHANGELOG
 
 ### Testing
 
 - ✅ Write tests for new features
 - ✅ Maintain test coverage
 - ✅ Run tests before commit
 - ✅ Fix failing tests immediately
 
 ## 🚀 Quick Reference
 
 ### Common Commands
 
 ```bash
 # Start system
 ./scripts/start_system.sh
 
 # Stop system
 ./scripts/stop_system.sh
 
 # Check health
 ./scripts/check_health.sh
 
 # View logs
 ./scripts/view_logs.sh follow
 
 # Run tests
 ./scripts/test_system.sh
 
 # Cleanup
 ./scripts/cleanup_and_organize.sh
 
 # Optimize
 python scripts/optimize_project.py
 ```
 
 ### File Locations
 
 - **Config**: `.env`, `alembic.ini`, `docker-compose.yml`
 - **Docs**: `*.md` files in root and `docs/`
 - **Scripts**: `scripts/` directory
 - **Tests**: `tests/` directory
 - **Logs**: `output/` directory
 
 ## 📞 Support
 
 For questions or issues:
 
 1. Check documentation in `docs/`
 2. Run health check: `./scripts/check_health.sh`
 3. View logs: `./scripts/view_logs.sh`
 4. Run diagnostics: `python scripts/optimize_project.py`
 
 ---
 
 **Last Updated**: 2026-04-23
 
 **Version**: 2.0.1

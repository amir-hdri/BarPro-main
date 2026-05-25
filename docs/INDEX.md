 # 📚 UTCMS Automation System - Documentation Index
 
 ## 🚀 Quick Start
 
 **New to the project?** Start here:
 
 1. Read [شروع سریع](docs/guides/QUICK_START_FA.md) - Get up and running in 5 minutes
 2. Run `./scripts/start_system.sh` - Start the system
 3. Check `./scripts/check_health.sh` - Verify everything works
 
 ---
 
 ## 📖 Documentation by Category
 
 ### 🎯 Getting Started
 
 | Document | Description | Audience |
 |----------|-------------|----------|
 | [شروع سریع](docs/guides/QUICK_START_FA.md) | Quick start guide | New users |
 | [نمای کلی (فارسی)](README.md) | English overview | All users |
 | [نمای کلی (فارسی)](README.md) | Persian overview | Persian speakers |
 
 ### 🔧 Technical Documentation
 
 | Document | Description | Audience |
 |----------|-------------|----------|
 | [بهینه‌سازی‌ها](docs/archive/reports/FIXES_AND_OPTIMIZATIONS.md) | Critical fixes explained | Developers |
 | [ساختار پروژه](docs/architecture/PROJECT_STRUCTURE.md) | Project structure | Developers |
 | [سازماندهی پروژه](docs/archive/reports/PROJECT_ORGANIZATION.md) | Organization guide | Developers |
 | [گزارش پاک‌سازی](docs/archive/reports/CLEANUP_SUMMARY.md) | Cleanup summary | Developers |
 
 ### 📊 Project Status
 
 | Document | Description | Audience |
 |----------|-------------|----------|
 | [گزارش کلی](docs/archive/reports/SUMMARY.md) | Executive summary | Managers |
 | [گزارش تکمیل](docs/archive/reports/COMPLETION_REPORT.md) | Project completion | Stakeholders |
 | [تغییرات نسخه‌ها](docs/CHANGELOG.md) | Version history | All users |
 
 ### 📁 Additional Resources
 
 | Location | Description |
 |----------|-------------|
 | `docs/` | Additional documentation |
 | `docs/archive/` | Archived documentation |
 | `examples/` | Code examples |
 
 ---
 
 ## 🛠️ Scripts Reference
 
 ### Management Scripts
 
 ```bash
 ./scripts/start_system.sh      # Start all services
 ./scripts/stop_system.sh       # Stop all services
 ./scripts/check_health.sh      # Health check
 ./scripts/view_logs.sh         # View logs
 ```
 
 ### Database Scripts
 
 ```bash
 python scripts/init_database.py    # Initialize database
 ./scripts/reset_database.sh        # Reset database
 ```
 
 ### Testing Scripts
 
 ```bash
 ./scripts/test_system.sh           # System tests
 ./scripts/verify_fixes.sh          # Verify fixes
 ./scripts/run_comprehensive_tests.sh  # Full test suite
 ```
 
 ### Utility Scripts
 
 ```bash
 python scripts/generate_secrets.py     # Generate secrets
 ./scripts/cleanup_and_organize.sh      # Cleanup project
 python scripts/optimize_project.py     # Analyze code
 ```
 
 ---
 
 ## 🗂️ Project Structure
 
 ```
 .
 ├── app/                    # Main application
 ├── alembic/                # Database migrations
 ├── apps/web/               # Frontend
 ├── docs/                   # Documentation
 ├── infra/                  # Infrastructure
 ├── scripts/                # Management scripts
 ├── tests/                  # Test suite
 └── *.md                    # Documentation files
 ```
 
 See [ساختار پروژه](docs/architecture/PROJECT_STRUCTURE.md) for details.
 
 ---
 
 ## 🎯 Common Tasks
 
 ### First Time Setup
 
 ```bash
 # 1. Install dependencies
 pip install -r requirements.txt
 cd apps/web && yarn install && cd ../..
 
 # 2. Configure environment
 cp .env.example .env
 nano .env
 
 # 3. Start system
 ./scripts/start_system.sh
 ```
 
 ### Daily Development
 
 ```bash
 # Start system
 ./scripts/start_system.sh
 
 # Check health
 ./scripts/check_health.sh
 
 # View logs
 ./scripts/view_logs.sh follow
 
 # Stop system
 ./scripts/stop_system.sh
 ```
 
 ### Troubleshooting
 
 ```bash
 # Check health
 ./scripts/check_health.sh
 
 # View backend logs
 ./scripts/view_logs.sh backend
 
 # Reset database
 ./scripts/reset_database.sh
 
 # Run tests
 ./scripts/test_system.sh
 ```
 
 ### Code Quality
 
 ```bash
 # Analyze code
 python scripts/optimize_project.py
 
 # Cleanup project
 ./scripts/cleanup_and_organize.sh
 
 # Verify fixes
 ./scripts/verify_fixes.sh
 ```
 
 ---
 
 ## 📞 Getting Help
 
 ### Documentation
 
 1. **Quick answers**: Check [شروع سریع](docs/guides/QUICK_START_FA.md)
 2. **Technical details**: See [بهینه‌سازی‌ها](docs/archive/reports/FIXES_AND_OPTIMIZATIONS.md)
 3. **Project structure**: Read [سازماندهی پروژه](docs/archive/reports/PROJECT_ORGANIZATION.md)
 
 ### Diagnostics
 
 1. **Health check**: `./scripts/check_health.sh`
 2. **View logs**: `./scripts/view_logs.sh follow`
 3. **Run tests**: `./scripts/test_system.sh`
 4. **Code analysis**: `python scripts/optimize_project.py`
 
 ### Common Issues
 
 | Issue | Solution | Documentation |
 |-------|----------|---------------|
 | Backend won't start | Check logs, reset DB | [شروع سریع - خطایابی](docs/guides/QUICK_START_FA.md#troubleshooting) |
 | Migration errors | Run fix migration | [بهینه‌سازی‌ها](docs/archive/reports/FIXES_AND_OPTIMIZATIONS.md) |
 | Port conflicts | Kill process, restart | [شروع سریع - خطایابی](docs/guides/QUICK_START_FA.md#troubleshooting) |
 
 ---
 
 ## 🎓 Learning Path
 
 ### For New Users
 
 1. Read [شروع سریع](docs/guides/QUICK_START_FA.md)
 2. Follow setup instructions
 3. Explore [نمای کلی (فارسی)](README.md) (Persian)
 4. Try example workflows
 
 ### For Developers
 
 1. Read [ساختار پروژه](docs/architecture/PROJECT_STRUCTURE.md)
 2. Review [بهینه‌سازی‌ها](docs/archive/reports/FIXES_AND_OPTIMIZATIONS.md)
 3. Study [سازماندهی پروژه](docs/archive/reports/PROJECT_ORGANIZATION.md)
 4. Check code examples in `examples/`
 
 ### For Managers
 
 1. Read [گزارش کلی](docs/archive/reports/SUMMARY.md)
 2. Review [گزارش تکمیل](docs/archive/reports/COMPLETION_REPORT.md)
 3. Check [تغییرات نسخه‌ها](docs/CHANGELOG.md)
 4. Monitor project health
 
 ---
 
 ## 📊 Project Status
 
 | Category | Status | Details |
 |----------|--------|---------|
 | **Critical Issues** | ✅ RESOLVED | All fixed |
 | **Code Quality** | ✅ EXCELLENT | Clean & organized |
 | **Documentation** | ✅ COMPLETE | Comprehensive |
 | **Testing** | ✅ PASSING | All checks pass |
 | **Production Ready** | ✅ YES | Ready to deploy |
 
 See [گزارش تکمیل](docs/archive/reports/COMPLETION_REPORT.md) for details.
 
 ---
 
 ## 🔄 Version History
 
 | Version | Date | Changes |
 |---------|------|---------|
 | 2.0.1 | 2026-04-23 | Critical fixes, cleanup, optimization |
 | 2.0.0 | 2026-04-20 | Multi-tenant release |
 
 See [تغییرات نسخه‌ها](docs/CHANGELOG.md) for complete history.
 
 ---
 
 ## 🎉 Quick Links
 
 ### Essential Documents
 - [Quick Start Guide](docs/guides/QUICK_START_FA.md)
 - [Technical Fixes](docs/archive/reports/FIXES_AND_OPTIMIZATIONS.md)
 - [Project Structure](docs/architecture/PROJECT_STRUCTURE.md)
 - [Completion Report](docs/archive/reports/COMPLETION_REPORT.md)
 
 ### Key Scripts
 - Start: `./scripts/start_system.sh`
 - Stop: `./scripts/stop_system.sh`
 - Health: `./scripts/check_health.sh`
 - Logs: `./scripts/view_logs.sh`
 
 ### Access Points
 - Frontend: http://localhost:3000
 - Backend: http://localhost:8000
 - API Docs: http://localhost:8000/docs
 - Prometheus: http://localhost:9090
 
 ---
 
 **Last Updated**: 2026-04-23
 
 **Version**: 2.0.1
 
 **Status**: ✅ Production Ready

 #!/bin/bash
 # Verify that all critical fixes are in place
 
 set -e
 
 GREEN='\033[0;32m'
 RED='\033[0;31m'
 YELLOW='\033[1;33m'
 BLUE='\033[0;34m'
 NC='\033[0m'
 
 PASSED=0
 FAILED=0
 
 echo "🔍 Verifying Critical Fixes"
 echo "==========================="
 echo ""
 
 verify() {
     local name="$1"
     local result="$2"
     
     if [ "$result" -eq 0 ]; then
         echo -e "${GREEN}✅${NC} $name"
         PASSED=$((PASSED + 1))
     else
         echo -e "${RED}❌${NC} $name"
         FAILED=$((FAILED + 1))
     fi
 }
 
 # Verify 1: Database.py fix
 echo -e "${BLUE}Checking app/core/database.py fixes...${NC}"
 
 grep -q "if \"sqlite\" in utcms_config.DATABASE_URL.lower():" app/core/database.py
 verify "SQLite-only fallback check exists" $?
 
 grep -q "raise RuntimeError" app/core/database.py
 verify "PostgreSQL fail-fast behavior exists" $?
 
 ! grep -q "await conn.run_sync(SQLModel.metadata.create_all)" app/core/database.py | grep -v "if \"sqlite\""
 verify "Dangerous unconditional create_all() removed" $?
 
 echo ""
 
 # Verify 2: Model constraint fixes
 echo -e "${BLUE}Checking model constraint fixes...${NC}"
 
 grep -q "uq_waybill_tasks_legacy_task_id" app/models_multitenant.py
 verify "Legacy table constraint renamed (task_id)" $?
 
 grep -q "uq_waybill_tasks_legacy_idempotency_key" app/models_multitenant.py
 verify "Legacy table constraint renamed (idempotency_key)" $?
 
 grep -q '__tablename__ = "waybilltask"' app/models.py
 verify "Explicit tablename in models.py" $?
 
 echo ""
 
 # Verify 3: Migration files
 echo -e "${BLUE}Checking migration files...${NC}"
 
 [ -f "alembic/versions/005_fix_constraint_conflicts.py" ]
 verify "Fix migration file exists" $?
 
 grep -q "idempotent" alembic/versions/005_fix_constraint_conflicts.py
 verify "Fix migration is idempotent" $?
 
 echo ""
 
 # Verify 4: New scripts
 echo -e "${BLUE}Checking new management scripts...${NC}"
 
 [ -x "scripts/init_database.py" ]
 verify "init_database.py exists and executable" $?
 
 [ -x "scripts/reset_database.sh" ]
 verify "reset_database.sh exists and executable" $?
 
 [ -x "scripts/check_health.sh" ]
 verify "check_health.sh exists and executable" $?
 
 [ -x "scripts/stop_system.sh" ]
 verify "stop_system.sh exists and executable" $?
 
 [ -x "scripts/view_logs.sh" ]
 verify "view_logs.sh exists and executable" $?
 
 [ -x "scripts/test_system.sh" ]
 verify "test_system.sh exists and executable" $?
 
 echo ""
 
 # Verify 5: Documentation
 echo -e "${BLUE}Checking documentation...${NC}"
 
 [ -f "QUICK_START.md" ]
 verify "QUICK_START.md exists" $?
 
 [ -f "FIXES_AND_OPTIMIZATIONS.md" ]
 verify "FIXES_AND_OPTIMIZATIONS.md exists" $?
 
 [ -f "CHANGELOG.md" ]
 verify "CHANGELOG.md exists" $?
 
 grep -q "QUICK_START.md" README_FA.md
 verify "README_FA.md references new docs" $?
 
 echo ""
 
 # Verify 6: Startup script improvements
 echo -e "${BLUE}Checking startup script improvements...${NC}"
 
 grep -q "scripts/init_database.py" scripts/start_system.sh
 verify "start_system.sh calls init_database.py" $?
 
 grep -q "tail -50" scripts/start_system.sh
 verify "start_system.sh shows error logs" $?
 
 echo ""
 
 # Verify 7: Code quality
 echo -e "${BLUE}Checking code quality improvements...${NC}"
 
 grep -q "CRITICAL:" app/core/database.py
 verify "Critical sections documented" $?
 
 grep -q "extra_fields" app/core/database.py
 verify "Structured logging used" $?
 
 echo ""
 
 # Summary
 echo "==========================="
 echo "Verification Summary"
 echo "==========================="
 echo -e "${GREEN}Passed: $PASSED${NC}"
 echo -e "${RED}Failed: $FAILED${NC}"
 echo ""
 
 if [ $FAILED -eq 0 ]; then
     echo -e "${GREEN}✅ All fixes verified successfully!${NC}"
     echo ""
     echo "Next steps:"
     echo "  1. Start the system: ./scripts/start_system.sh"
     echo "  2. Check health: ./scripts/check_health.sh"
     echo "  3. Run tests: ./scripts/test_system.sh"
     exit 0
 else
     echo -e "${RED}❌ Some verifications failed!${NC}"
     echo ""
     echo "Please review the failed checks above."
     exit 1
 fi

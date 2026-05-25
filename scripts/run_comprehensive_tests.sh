#!/bin/bash

echo "🧪 Running Comprehensive Test Suite"
echo "=" | awk '{for(i=0;i<80;i++)printf "="; printf "\n"}'

# Colors
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Test categories
CRITICAL_TESTS=(
    "test_barname_ml_solver.py"
    "test_captcha_cnn_only.py"
    "test_config_validation.py"
    "test_config_bootstrap.py"
)

INTEGRATION_TESTS=(
    "test_auth.py"
    "test_browser_manager.py"
    "test_map_automation.py"
    "test_map_click_integration.py"
)

UNIT_TESTS=(
    "test_api.py"
    "test_api_auth.py"
    "test_validation.py"
    "test_error_handler.py"
)

run_test_category() {
    local category=$1
    shift
    local tests=("$@")
    
    echo ""
    echo "📋 Running $category Tests..."
    echo "-" | awk '{for(i=0;i<80;i++)printf "-"; printf "\n"}'
    
    local passed=0
    local failed=0
    
    for test in "${tests[@]}"; do
        if [ -f "tests/$test" ]; then
            echo -n "  Testing $test ... "
            if pytest "tests/$test" -q --tb=no > /dev/null 2>&1; then
                echo -e "${GREEN}✓ PASSED${NC}"
                ((passed++))
            else
                echo -e "${RED}✗ FAILED${NC}"
                ((failed++))
            fi
        else
            echo -e "  ${YELLOW}⊘ SKIPPED${NC} (file not found): $test"
        fi
    done
    
    echo ""
    echo "  Results: ${GREEN}$passed passed${NC}, ${RED}$failed failed${NC}"
    
    return $failed
}

# Run test categories
total_failed=0

run_test_category "Critical" "${CRITICAL_TESTS[@]}"
total_failed=$((total_failed + $?))

run_test_category "Integration" "${INTEGRATION_TESTS[@]}"
total_failed=$((total_failed + $?))

run_test_category "Unit" "${UNIT_TESTS[@]}"
total_failed=$((total_failed + $?))

# Summary
echo ""
echo "=" | awk '{for(i=0;i<80;i++)printf "="; printf "\n"}'
if [ $total_failed -eq 0 ]; then
    echo -e "${GREEN}✅ All test categories passed!${NC}"
    exit 0
else
    echo -e "${RED}❌ $total_failed test(s) failed${NC}"
    exit 1
fi

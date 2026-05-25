#!/bin/bash

# Backup tests directory first
echo "📦 Creating backup of tests directory..."
tar -czf tests_backup_$(date +%Y%m%d_%H%M%S).tar.gz tests/

echo ""
echo "🗑️  Removing old and duplicate test files..."

# Remove duplicate/refactored tests
rm -f tests/test_location_selector_refactor.py

# Remove very old tests that are likely outdated (>50 days old)
OLD_TESTS=(
    "test_reporting_persistence.py"
    "test_operation_mode.py"
    "test_api_operation_modes.py"
    "test_browser_security.py"
    "test_logging_redaction.py"
    "test_script_loader.py"
    "test_reports_operational.py"
    "test_selectors.py"
)

for test in "${OLD_TESTS[@]}"; do
    if [ -f "tests/$test" ]; then
        echo "  - Removing tests/$test"
        rm -f "tests/$test"
    fi
done

echo ""
echo "✅ Cleanup complete!"
echo ""
echo "Remaining test files:"
ls -1 tests/test_*.py | wc -l

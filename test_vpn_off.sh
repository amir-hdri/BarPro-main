#!/usr/bin/env bash
# ==============================================================================
# BarPro - Run Network & Proxy Test When VPN is OFF
# ==============================================================================
set -e

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$PROJECT_DIR"

if [ -f ".venv/bin/python" ]; then
    PYTHON_BIN=".venv/bin/python"
elif command -v python3 >/dev/null 2>&1; then
    PYTHON_BIN="python3"
else
    echo "Python 3 not found!"
    exit 1
fi

exec "$PYTHON_BIN" scripts/test_when_vpn_off.py "$@"

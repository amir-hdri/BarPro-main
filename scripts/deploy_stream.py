#!/usr/bin/env python3
"""Deprecated unsafe deployment entry point; fail closed for compatibility."""

import sys

print(
    "ERROR: scripts/deploy_stream.py is retired. Use "
    "scripts/deploy_and_verify_all.py with SSH_KNOWN_HOSTS configured.",
    file=sys.stderr,
)
raise SystemExit(2)

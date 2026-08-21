#!/usr/bin/env python3
"""Deprecated unsafe cluster deployment entry point; fail closed."""

import sys

print(
    "ERROR: scripts/deploy_cluster.py is retired. Use "
    "scripts/deploy_and_verify_all.py with SSH_KNOWN_HOSTS configured.",
    file=sys.stderr,
)
raise SystemExit(2)

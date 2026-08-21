#!/usr/bin/env python3
"""Retired ad-hoc cross-node probe; fail closed for compatibility."""

import sys

print(
    "ERROR: scripts/test_cross_node_conn.py is retired. Use the read-only "
    "deployment-ops preflight with SSH_KNOWN_HOSTS configured.",
    file=sys.stderr,
)
raise SystemExit(2)

#!/usr/bin/env python3
"""Retired mutable cluster-audit helper; fail closed for compatibility."""

import sys

print(
    "ERROR: scripts/audit_cluster.py is retired. Use the read-only "
    "deployment-ops deploy_cli.py/server_ssh.py tools with SSH_KNOWN_HOSTS "
    "configured.",
    file=sys.stderr,
)
raise SystemExit(2)

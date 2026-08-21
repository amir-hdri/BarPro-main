#!/usr/bin/env python3
"""Retired two-node deployment path; fail closed for compatibility."""

import sys

print(
    "ERROR: scripts/deploy_remote.py is retired because it used TOFU SSH, "
    "Compose V1 fallbacks, and copied the full production environment. Use "
    "scripts/deploy_and_verify_all.py with SSH_KNOWN_HOSTS configured.",
    file=sys.stderr,
)
raise SystemExit(2)

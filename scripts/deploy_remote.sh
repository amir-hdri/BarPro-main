#!/usr/bin/env bash
# Retired two-node deployment path. The former implementation used unverified
# SSH host keys, exposed a public Squid port, and supported Compose V1.
set -euo pipefail

echo "ERROR: scripts/deploy_remote.sh is retired and must not be used for production." >&2
echo "Use scripts/deploy_all_servers.sh or scripts/deploy_and_verify_all.py with SSH_KNOWN_HOSTS configured." >&2
exit 2

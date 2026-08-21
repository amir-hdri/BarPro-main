"""Expected Docker inventory for BarPro deployment roles.

The production fleet hosts are treated as dedicated BarPro nodes. A running
container outside the role allowlist is therefore an error unless an operator
explicitly supplies its exact name through ``ALLOWED_EXTRA_CONTAINERS``.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from collections.abc import Iterable, Mapping
from typing import Any

CENTRAL_EXPECTED_CONTAINERS = {
    "barpro-postgres": "postgres:16.4",
    "barpro-redis": "redis:7.2.5-alpine",
    "barpro-squid-1": "ubuntu/squid:latest",
    "barpro-backend": "barpro_backend:latest",
    "barpro-worker-1": "barpro_backend:latest",
    "barpro-scheduler": "barpro_backend:latest",
    "barpro-beat": "barpro_backend:latest",
    "barpro-frontend": "barpro-frontend:latest",
    "barpro-nginx": "nginx:1.27.0-alpine",
    "barpro-prometheus": "prom/prometheus:v2.53.0",
    "barpro-alertmanager": "prom/alertmanager:v0.27.0",
    "barpro-node-exporter": "prom/node-exporter:v1.8.2",
    "barpro-redis-exporter": "oliver006/redis_exporter:v1.60.0",
    "barpro-postgres-exporter": "prometheuscommunity/postgres-exporter:v0.15.0",
    "barpro-nginx-exporter": "nginx/nginx-prometheus-exporter:1.3.0",
    "barpro-grafana": "grafana/grafana:11.0.0",
}

WORKER_EXPECTED_CONTAINERS = {
    "barpro-squid-worker": "ubuntu/squid:latest",
    "barpro-celery-worker": "ghcr.io/amir-hdri/barpro-main/barpro-backend:latest",
}


def expected_containers(role: str) -> dict[str, str]:
    """Return the effective role inventory, honoring deployed image overrides."""
    if role == "central":
        expected = CENTRAL_EXPECTED_CONTAINERS.copy()
        backend_image = os.environ.get("BACKEND_IMAGE")
        frontend_image = os.environ.get("FRONTEND_IMAGE")
        if backend_image:
            for name in ("barpro-backend", "barpro-worker-1", "barpro-scheduler", "barpro-beat"):
                expected[name] = backend_image
        if frontend_image:
            expected["barpro-frontend"] = frontend_image
        return expected

    expected = WORKER_EXPECTED_CONTAINERS.copy()
    backend_image = os.environ.get("BACKEND_IMAGE")
    if backend_image:
        expected["barpro-celery-worker"] = backend_image
    return expected


def image_tag_matches(actual: str, expected: str) -> bool:
    """Allow registry-qualified BarPro images while pinning third-party tags."""
    if actual == expected:
        return True
    if expected == "barpro_backend:latest":
        return actual.endswith("/barpro-backend:latest") or actual.endswith("/barpro_backend:latest")
    if expected == "barpro-frontend:latest":
        return actual.endswith("/barpro-frontend:latest")
    return False


def audit_container_inventory(
    running: Mapping[str, str],
    expected: Mapping[str, str],
    allowed_extra: Iterable[str] = (),
) -> dict[str, Any]:
    """Compare running ``container -> image`` values with a role allowlist."""
    allowed_extra_names = {name.strip() for name in allowed_extra if name.strip()}
    missing = sorted(set(expected) - set(running))
    unexpected = sorted(set(running) - set(expected) - allowed_extra_names)
    image_mismatches = [
        {
            "name": name,
            "actual": running[name],
            "expected": expected[name],
        }
        for name in sorted(set(running) & set(expected))
        if not image_tag_matches(running[name], expected[name])
    ]
    return {
        "status": "passed" if not (missing or unexpected or image_mismatches) else "failed",
        "missing": missing,
        "unexpected": unexpected,
        "image_mismatches": image_mismatches,
        "allowed_extra": sorted(allowed_extra_names),
    }


def inspect_running_containers() -> dict[str, str]:
    """Read the local Docker daemon without shell interpolation."""
    ps = subprocess.run(
        ["docker", "ps", "-q"],
        check=True,
        capture_output=True,
        text=True,
    )
    container_ids = [container_id for container_id in ps.stdout.splitlines() if container_id]
    if not container_ids:
        return {}
    inspected = subprocess.run(
        [
            "docker",
            "inspect",
            "--format",
            "{{.Name}}|{{.Config.Image}}",
            *container_ids,
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    running = {}
    for line in inspected.stdout.splitlines():
        name, separator, image = line.partition("|")
        if separator:
            running[name.lstrip("/")] = image
    return running


def main() -> int:
    parser = argparse.ArgumentParser(description="Audit the local BarPro Docker container inventory.")
    parser.add_argument("--role", choices=("central", "worker"), required=True)
    parser.add_argument("--output", help="Optional JSON output path")
    args = parser.parse_args()

    allowed_extra = {name.strip() for name in os.environ.get("ALLOWED_EXTRA_CONTAINERS", "").split(",") if name.strip()}
    try:
        running = inspect_running_containers()
    except (OSError, subprocess.CalledProcessError) as exc:
        print(f"ERROR: could not inspect Docker containers: {exc}", file=sys.stderr)
        return 2

    result = {
        "role": args.role,
        "running": running,
        **audit_container_inventory(
            running,
            expected_containers(args.role),
            allowed_extra=allowed_extra,
        ),
    }
    rendered = json.dumps(result, indent=2, sort_keys=True)
    if args.output:
        with open(args.output, "w", encoding="utf-8") as output_file:
            output_file.write(rendered + "\n")
    print(rendered)
    return 0 if result["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())

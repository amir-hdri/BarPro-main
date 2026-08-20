#!/usr/bin/env python3
"""
scripts/render_worker_squid.py
Safely render infra/squid/squid_worker.runtime.conf on Worker nodes.
"""
from __future__ import annotations

import os
from pathlib import Path


def main():
    root = Path(__file__).resolve().parent.parent
    os.chdir(root)

    env_vals = {}
    env_file = root / ".env"
    if env_file.exists():
        with open(env_file, encoding="utf-8", errors="ignore") as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    k, v = line.split("=", 1)
                    k = k.strip()
                    v = v.strip().strip('"').strip("'")
                    env_vals[k] = v

    egress = env_vals.get("WORKER_EGRESS_IP")
    if not egress:
        egress = os.environ.get("WORKER_EGRESS_IP", "127.0.0.1")

    central = env_vals.get("CENTRAL_IP", os.environ.get("CENTRAL_IP", "87.107.5.238"))

    template_file = root / "infra" / "squid" / "squid_worker.conf"
    runtime_file = root / "infra" / "squid" / "squid_worker.runtime.conf"

    if not template_file.exists():
        print(f"ERROR: {template_file} does not exist", flush=True)
        return 1

    content = template_file.read_text(encoding="utf-8")
    rendered = content.replace("__WORKER_EGRESS_IP__", egress).replace("__CENTRAL_IP__", central)
    runtime_file.write_text(rendered, encoding="utf-8")

    print(f"SUCCESS: Rendered {runtime_file.name} (egress={egress}, central={central})", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

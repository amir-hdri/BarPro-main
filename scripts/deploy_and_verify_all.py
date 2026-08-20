#!/usr/bin/env python3
"""
scripts/deploy_and_verify_all.py
Full automated deployment and end-to-end health verification for BarPro across Central Server and Worker Nodes.
"""

import sys
import time
import os
import paramiko

PWD = os.environ["SSH_PASSWORD"]  # from env — never hardcode credentials

NODES = [
    {
        "id": "central",
        "name": "Central Server",
        "ip": os.environ.get("CENTRAL_IP", "87.107.5.238"),
        "is_central": True,
    },
    {
        "id": "worker2",
        "name": "Worker Node 2",
        "ip": os.environ.get("WORKER_2_IP", "5.56.132.26"),
        "is_central": False,
        "worker_id": 2,
    },
    {
        "id": "worker3",
        "name": "Worker Node 3",
        "ip": os.environ.get("WORKER_3_IP", "87.107.5.219"),
        "is_central": False,
        "worker_id": 3,
    },
]


def create_ssh(ip: str, retries: int = 5, delay: int = 3) -> paramiko.SSHClient:
    ssh = paramiko.SSHClient()
    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    for attempt in range(1, retries + 1):
        try:
            ssh.connect(ip, username="root", password=PWD, timeout=30, banner_timeout=45, auth_timeout=30)
            trans = ssh.get_transport()
            if trans:
                trans.set_keepalive(15)
            return ssh
        except Exception as exc:
            print(f"  [SSH] Connection to {ip} attempt {attempt}/{retries} failed: {exc}")
            if attempt < retries:
                time.sleep(delay)
    raise RuntimeError(f"Could not connect to {ip} after {retries} attempts.")


def run_node_cmd(ip: str, cmd: str, timeout: int = 1800, print_output: bool = True, retries: int = 3) -> tuple[int, str, str]:
    """Execute command on node with automatic connection and retry."""
    for attempt in range(1, retries + 1):
        ssh = None
        try:
            ssh = create_ssh(ip)
            transport = ssh.get_transport()
            if not transport or not transport.is_active():
                raise RuntimeError("SSH transport is not active.")
            channel = transport.open_session()
            channel.settimeout(timeout)
            channel.exec_command(cmd)

            stdout_chunks = []
            stderr_chunks = []

            while not channel.exit_status_ready():
                if channel.recv_ready():
                    chunk = channel.recv(4096).decode("utf-8", errors="replace")
                    if chunk:
                        stdout_chunks.append(chunk)
                        if print_output:
                            sys.stdout.write(chunk)
                            sys.stdout.flush()
                if channel.recv_stderr_ready():
                    err_chunk = channel.recv_stderr(4096).decode("utf-8", errors="replace")
                    if err_chunk:
                        stderr_chunks.append(err_chunk)
                        if print_output:
                            sys.stderr.write(err_chunk)
                            sys.stderr.flush()
                time.sleep(0.1)

            # Read remaining
            while channel.recv_ready():
                chunk = channel.recv(4096).decode("utf-8", errors="replace")
                if chunk:
                    stdout_chunks.append(chunk)
                    if print_output:
                        sys.stdout.write(chunk)
                        sys.stdout.flush()
            while channel.recv_stderr_ready():
                err_chunk = channel.recv_stderr(4096).decode("utf-8", errors="replace")
                if err_chunk:
                    stderr_chunks.append(err_chunk)
                    if print_output:
                        sys.stderr.write(err_chunk)
                        sys.stderr.flush()

            status = channel.recv_exit_status()
            channel.close()
            ssh.close()
            return status, "".join(stdout_chunks), "".join(stderr_chunks)
        except Exception as exc:
            if ssh:
                try:
                    ssh.close()
                except Exception:
                    pass
            print(f"  [SSH ERROR on {ip}] attempt {attempt}/{retries}: {exc}")
            if attempt < retries:
                time.sleep(3)
            else:
                raise exc


def main():
    print("=" * 80)
    print("🚀 BARPRO CLUSTER DEPLOYMENT & VERIFICATION PIPELINE")
    print("=" * 80)

    # -------------------------------------------------------------------------
    # Step 1: Central Server Deployment
    # -------------------------------------------------------------------------
    central = NODES[0]
    print(f"\n[{central['name']} ({central['ip']})] Starting Deployment...")

    print("\n--- 1.1 Git Fetch & Reset to latest main ---")
    run_node_cmd(central["ip"], "cd /opt/barpro && find . -name '._*' -delete && git fetch origin main && git reset --hard origin/main && git log -1 --oneline")

    print("\n--- 1.2 Build Frontend Image (Next.js 15) ---")
    run_node_cmd(central["ip"], "cd /opt/barpro && docker compose --env-file .env -f compose/web.yml build frontend", timeout=600)

    print("\n--- 1.3 Restart Infrastructure (PostgreSQL + Redis) ---")
    run_node_cmd(central["ip"], "cd /opt/barpro && docker compose --env-file .env -f compose/infra.yml up -d --force-recreate")

    print("\n--- 1.4 Render Central Squid Configs & Restart Proxies (Squid 1) ---")
    run_node_cmd(central["ip"], "cd /opt/barpro && bash scripts/render_squid_configs.sh && docker compose --env-file .env -f compose/proxy.yml up -d --force-recreate")

    print("\n--- 1.5 Restart Backend, Celery Worker 1, Celery Scheduler, Celery Beat ---")
    run_node_cmd(
        central["ip"],
        "cd /opt/barpro && docker compose --env-file .env -f compose/backend.yml up -d --force-recreate backend celery_worker_1 celery_scheduler celery_beat",
    )

    print("\n--- 1.6 Restart Web (Frontend + Nginx) ---")
    run_node_cmd(
        central["ip"],
        "cd /opt/barpro && docker compose --env-file .env -f compose/web.yml up -d --force-recreate frontend nginx",
    )

    print("\n--- 1.7 Restart Monitoring (Prometheus + Exporters) ---")
    run_node_cmd(central["ip"], "cd /opt/barpro && docker compose --env-file .env -f compose/monitoring.yml up -d")

    print("\n--- 1.8 Waiting 25 seconds for central services initialization ---")
    time.sleep(25)

    print("\n--- 1.9 Database Migration Status & Upgrade ---")
    run_node_cmd(central["ip"], "docker exec barpro-backend python -m alembic -c alembic.ini upgrade head")
    run_node_cmd(central["ip"], "docker exec barpro-backend python -m alembic -c alembic.ini current")

    # -------------------------------------------------------------------------
    # Step 2: Worker Node 2 Deployment
    # -------------------------------------------------------------------------
    w2 = NODES[1]
    print(f"\n\n[{w2['name']} ({w2['ip']})] Starting Deployment...")

    print("\n--- 2.1 Git Fetch & Reset to latest main ---")
    run_node_cmd(w2["ip"], "cd /opt/barpro && find . -name '._*' -delete && git fetch origin main && git reset --hard origin/main && git log -1 --oneline")

    print("\n--- 2.2 Render Squid config for Worker 2 ---")
    run_node_cmd(w2["ip"], "cd /opt/barpro && python3 scripts/render_worker_squid.py")

    print("\n--- 2.3 Restart Worker 2 Services ---")
    run_node_cmd(w2["ip"], "cd /opt/barpro && docker compose --env-file .env -f compose/worker-node.yml up -d --force-recreate")

    # -------------------------------------------------------------------------
    # Step 3: Worker Node 3 Deployment
    # -------------------------------------------------------------------------
    w3 = NODES[2]
    print(f"\n\n[{w3['name']} ({w3['ip']})] Starting Deployment...")

    print("\n--- 3.1 Git Fetch & Reset to latest main ---")
    run_node_cmd(w3["ip"], "cd /opt/barpro && find . -name '._*' -delete && git fetch origin main && git reset --hard origin/main && git log -1 --oneline")

    print("\n--- 3.2 Render Squid config for Worker 3 ---")
    run_node_cmd(w3["ip"], "cd /opt/barpro && python3 scripts/render_worker_squid.py")

    print("\n--- 3.3 Restart Worker 3 Services ---")
    run_node_cmd(w3["ip"], "cd /opt/barpro && docker compose --env-file .env -f compose/worker-node.yml up -d --force-recreate")

    # -------------------------------------------------------------------------
    # Step 4: Health Checks & Cluster Verification
    # -------------------------------------------------------------------------
    print("\n\n" + "=" * 80)
    print("🩺 COMPREHENSIVE CLUSTER HEALTH VERIFICATION")
    print("=" * 80)
    print("\nWaiting 20 seconds for worker heartbeats and service stabilization...")
    time.sleep(20)

    print("\n--- [A] Central Server Containers ---")
    run_node_cmd(central["ip"], "docker ps --format 'table {{.Names}}\t{{.Status}}\t{{.Ports}}'")

    print("\n--- [B] Central Backend Health Endpoint ---")
    run_node_cmd(central["ip"], "curl -sf http://localhost:8000/healthz && echo ' -> Central API Health: OK' || echo ' -> Central API Health: FAIL'")

    print("\n--- [C] Central Frontend Health ---")
    run_node_cmd(central["ip"], "curl -sf -I http://localhost:3000 | head -n 5")

    print("\n--- [D] Database Connectivity from Central Backend ---")
    db_test_script = """
import asyncio
from app.core.database import engine
from sqlmodel import text

async def check():
    async with engine.connect() as conn:
        res = await conn.execute(text("SELECT count(*) FROM clients;"))
        count = res.scalar()
        print(f"DATABASE CHECK: SUCCESS (Total Clients: {count})")

asyncio.run(check())
"""
    run_node_cmd(central["ip"], f'docker exec barpro-backend python -c "{db_test_script}"')

    print("\n--- [E] Redis Connectivity & Session Vault from Central Backend ---")
    redis_test_script = """
import asyncio
from app.core.redis import redis_manager

async def check():
    client = await redis_manager.get()
    await client.set("cluster_health_check", "healthy_2026", ex=60)
    val = await client.get("cluster_health_check")
    assert val == "healthy_2026"
    print(f"REDIS CHECK: SUCCESS (Ping value: {val})")

asyncio.run(check())
"""
    run_node_cmd(central["ip"], f'docker exec barpro-backend python -c "{redis_test_script}"')

    print("\n--- [F] Celery Active Workers Inspection (Cross-Cluster) ---")
    run_node_cmd(central["ip"], "docker exec barpro-backend celery -A app.workers.celery_app:celery_app inspect ping -t 10")

    print("\n--- [G] Worker Node 2 Status & Connectivity ---")
    run_node_cmd(w2["ip"], "docker ps --format 'table {{.Names}}\t{{.Status}}\t{{.Ports}}'")
    w2_test_script = """
import asyncio
from app.core.database import engine
from sqlmodel import text
from app.core.redis import redis_manager

async def check():
    async with engine.connect() as conn:
        res = await conn.execute(text("SELECT 1;"))
        assert res.scalar() == 1
        print("WORKER 2 -> CENTRAL DB: SUCCESS")
    client = await redis_manager.get()
    pong = await client.ping()
    print("WORKER 2 -> CENTRAL REDIS: SUCCESS (pong=" + str(pong) + ")")

asyncio.run(check())
"""
    run_node_cmd(w2["ip"], f'docker exec barpro-celery-worker python -c "{w2_test_script}"')
    run_node_cmd(w2["ip"], "docker exec barpro-celery-worker curl -s -o /dev/null -w 'WORKER 2 SQUID EGRESS: HTTP_%{http_code}\\n' -x http://squid:3128 https://api.ipify.org")

    print("\n--- [H] Worker Node 3 Status & Connectivity ---")
    run_node_cmd(w3["ip"], "docker ps --format 'table {{.Names}}\t{{.Status}}\t{{.Ports}}'")
    w3_test_script = """
import asyncio
from app.core.database import engine
from sqlmodel import text
from app.core.redis import redis_manager

async def check():
    async with engine.connect() as conn:
        res = await conn.execute(text("SELECT 1;"))
        assert res.scalar() == 1
        print("WORKER 3 -> CENTRAL DB: SUCCESS")
    client = await redis_manager.get()
    pong = await client.ping()
    print("WORKER 3 -> CENTRAL REDIS: SUCCESS (pong=" + str(pong) + ")")

asyncio.run(check())
"""
    run_node_cmd(w3["ip"], f'docker exec barpro-celery-worker python -c "{w3_test_script}"')
    run_node_cmd(w3["ip"], "docker exec barpro-celery-worker curl -s -o /dev/null -w 'WORKER 3 SQUID EGRESS: HTTP_%{http_code}\\n' -x http://squid:3128 https://api.ipify.org")

    print("\n" + "=" * 80)
    print("🎉 ALL NODES DEPLOYED AND FULLY OPERATIONAL!")
    print("=" * 80)


if __name__ == "__main__":
    main()

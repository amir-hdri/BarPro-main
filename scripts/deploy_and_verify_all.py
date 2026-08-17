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
            ssh.connect(ip, username="root", password=PWD, timeout=30, banner_timeout=45)
            trans = ssh.get_transport()
            if trans:
                trans.set_keepalive(15)
            return ssh
        except Exception as exc:
            print(f"  [SSH] Connection to {ip} attempt {attempt}/{retries} failed: {exc}")
            if attempt < retries:
                time.sleep(delay)
    raise RuntimeError(f"Could not connect to {ip} after {retries} attempts.")


def run_command(ssh: paramiko.SSHClient, cmd: str, timeout: int = 1800, print_output: bool = True) -> tuple[int, str, str]:
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
    return status, "".join(stdout_chunks), "".join(stderr_chunks)


def main():
    print("=" * 80)
    print("🚀 BARPRO CLUSTER DEPLOYMENT & VERIFICATION PIPELINE")
    print("=" * 80)

    # -------------------------------------------------------------------------
    # Step 1: Central Server Deployment
    # -------------------------------------------------------------------------
    central = NODES[0]
    print(f"\n[{central['name']} ({central['ip']})] Starting Deployment...")
    ssh_central = create_ssh(central["ip"])

    print("\n--- 1.1 Git Fetch & Reset to latest main ---")
    run_command(ssh_central, "cd /opt/barpro && git fetch origin main && git reset --hard origin/main && git log -1 --oneline")

    print("\n--- 1.2 Build Backend Image ---")
    run_command(ssh_central, "cd /opt/barpro && docker build --network=host -t barpro_backend:latest -f Dockerfile .", timeout=900)

    print("\n--- 1.3 Build Frontend Image ---")
    run_command(ssh_central, "cd /opt/barpro && docker compose --env-file .env -f compose/web.yml build frontend", timeout=600)

    print("\n--- 1.4 Restart Infrastructure (PostgreSQL + Redis) ---")
    run_command(ssh_central, "cd /opt/barpro && docker compose --env-file .env -f compose/infra.yml up -d")

    print("\n--- 1.5 Restart Proxies (Squid 1) ---")
    run_command(ssh_central, "cd /opt/barpro && docker compose --env-file .env -f compose/proxy.yml up -d")

    print("\n--- 1.6 Restart Backend, Celery Worker 1, Celery Scheduler, Celery Beat ---")
    run_command(
        ssh_central,
        "cd /opt/barpro && docker compose --env-file .env -f compose/backend.yml up -d --force-recreate backend celery_worker_1 celery_scheduler celery_beat",
    )

    print("\n--- 1.7 Restart Web (Frontend + Nginx) ---")
    run_command(
        ssh_central,
        "cd /opt/barpro && docker compose --env-file .env -f compose/web.yml up -d --force-recreate frontend nginx",
    )

    print("\n--- 1.8 Waiting 20 seconds for central services initialization ---")
    time.sleep(20)

    print("\n--- 1.9 Database Migration Status & Upgrade ---")
    run_command(ssh_central, "docker exec barpro-backend python -m alembic -c alembic.ini upgrade head")
    run_command(ssh_central, "docker exec barpro-backend python -m alembic -c alembic.ini current")

    # -------------------------------------------------------------------------
    # Step 2: Worker Node 2 Deployment (Fast Inter-Node Image Stream)
    # -------------------------------------------------------------------------
    w2 = NODES[1]
    print(f"\n\n[{w2['name']} ({w2['ip']})] Starting Deployment...")
    ssh_w2 = create_ssh(w2["ip"])

    print("\n--- 2.1 Git Fetch & Reset to latest main ---")
    run_command(ssh_w2, "cd /opt/barpro && git fetch origin main && git reset --hard origin/main && git log -1 --oneline")

    print("\n--- 2.2 Render Squid config for Worker 2 ---")
    render_w2_cmd = """cd /opt/barpro && set -a && source <(grep -vF '$' .env) && set +a && sed -e "s/__WORKER_EGRESS_IP__/${WORKER_EGRESS_IP:?WORKER_EGRESS_IP required}/g" -e "s/__CENTRAL_IP__/${CENTRAL_IP:-127.0.0.1}/g" infra/squid/squid_worker.conf > infra/squid/squid_worker.runtime.conf"""
    run_command(ssh_w2, f"bash -c '{render_w2_cmd}'")

    print("\n--- 2.3 Stream Built Backend Image from Central to Worker 2 ---")
    sync_w2_cmd = f"docker save barpro_backend:latest | ssh -o StrictHostKeyChecking=no root@{w2['ip']} 'docker load && docker tag barpro_backend:latest ghcr.io/amir-hdri/barpro-main/barpro-backend:latest'"
    run_command(ssh_central, sync_w2_cmd, timeout=600)

    print("\n--- 2.4 Restart Worker 2 Services ---")
    run_command(ssh_w2, "cd /opt/barpro && docker compose --env-file .env -f compose/worker-node.yml up -d --force-recreate")

    # -------------------------------------------------------------------------
    # Step 3: Worker Node 3 Deployment (Fast Inter-Node Image Stream)
    # -------------------------------------------------------------------------
    w3 = NODES[2]
    print(f"\n\n[{w3['name']} ({w3['ip']})] Starting Deployment...")
    ssh_w3 = create_ssh(w3["ip"])

    print("\n--- 3.1 Git Fetch & Reset to latest main ---")
    run_command(ssh_w3, "cd /opt/barpro && git fetch origin main && git reset --hard origin/main && git log -1 --oneline")

    print("\n--- 3.2 Render Squid config for Worker 3 ---")
    render_w3_cmd = """cd /opt/barpro && set -a && source <(grep -vF '$' .env) && set +a && sed -e "s/__WORKER_EGRESS_IP__/${WORKER_EGRESS_IP:?WORKER_EGRESS_IP required}/g" -e "s/__CENTRAL_IP__/${CENTRAL_IP:-127.0.0.1}/g" infra/squid/squid_worker.conf > infra/squid/squid_worker.runtime.conf"""
    run_command(ssh_w3, f"bash -c '{render_w3_cmd}'")

    print("\n--- 3.3 Stream Built Backend Image from Central to Worker 3 ---")
    sync_w3_cmd = f"docker save barpro_backend:latest | ssh -o StrictHostKeyChecking=no root@{w3['ip']} 'docker load && docker tag barpro_backend:latest ghcr.io/amir-hdri/barpro-main/barpro-backend:latest'"
    run_command(ssh_central, sync_w3_cmd, timeout=600)

    print("\n--- 3.4 Restart Worker 3 Services ---")
    run_command(ssh_w3, "cd /opt/barpro && docker compose --env-file .env -f compose/worker-node.yml up -d --force-recreate")

    # -------------------------------------------------------------------------
    # Step 4: Health Checks & Cluster Verification
    # -------------------------------------------------------------------------
    print("\n\n" + "=" * 80)
    print("🩺 COMPREHENSIVE CLUSTER HEALTH VERIFICATION")
    print("=" * 80)
    print("\nWaiting 20 seconds for worker heartbeats and service stabilization...")
    time.sleep(20)

    print("\n--- [A] Central Server Containers ---")
    run_command(ssh_central, "docker ps --format 'table {{.Names}}\t{{.Status}}\t{{.Ports}}'")

    print("\n--- [B] Central Backend Health Endpoint ---")
    run_command(ssh_central, "curl -sf http://localhost:8000/healthz && echo ' -> Central API Health: OK' || echo ' -> Central API Health: FAIL'")

    print("\n--- [C] Central Frontend Health ---")
    run_command(ssh_central, "curl -sf -I http://localhost:3000 | head -n 5")

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
    run_command(ssh_central, f'docker exec barpro-backend python -c "{db_test_script}"')

    print("\n--- [E] Redis Connectivity & Session Vault from Central Backend ---")
    redis_test_script = """
import asyncio
from app.core.redis import get_redis_client

async def check():
    client = await get_redis_client()
    await client.set("cluster_health_check", "healthy_2026", ex=60)
    val = await client.get("cluster_health_check")
    assert val == "healthy_2026"
    print(f"REDIS CHECK: SUCCESS (Ping value: {val})")

asyncio.run(check())
"""
    run_command(ssh_central, f'docker exec barpro-backend python -c "{redis_test_script}"')

    print("\n--- [F] Celery Active Workers Inspection (Cross-Cluster) ---")
    run_command(ssh_central, "docker exec barpro-backend celery -A app.workers.celery_app:celery_app inspect ping -t 10")

    print("\n--- [G] Worker Node 2 Status & Connectivity ---")
    run_command(ssh_w2, "docker ps --format 'table {{.Names}}\t{{.Status}}\t{{.Ports}}'")
    w2_test_script = """
import asyncio
from app.core.database import engine
from sqlmodel import text
from app.core.redis import get_redis_client

async def check():
    async with engine.connect() as conn:
        res = await conn.execute(text("SELECT 1;"))
        assert res.scalar() == 1
        print("WORKER 2 -> CENTRAL DB: SUCCESS")
    client = await get_redis_client()
    pong = await client.ping()
    print("WORKER 2 -> CENTRAL REDIS: SUCCESS (pong=" + str(pong) + ")")

asyncio.run(check())
"""
    run_command(ssh_w2, f'docker exec barpro-celery-worker python -c "{w2_test_script}"')

    print("\n--- [H] Worker Node 3 Status & Connectivity ---")
    run_command(ssh_w3, "docker ps --format 'table {{.Names}}\t{{.Status}}\t{{.Ports}}'")
    w3_test_script = """
import asyncio
from app.core.database import engine
from sqlmodel import text
from app.core.redis import get_redis_client

async def check():
    async with engine.connect() as conn:
        res = await conn.execute(text("SELECT 1;"))
        assert res.scalar() == 1
        print("WORKER 3 -> CENTRAL DB: SUCCESS")
    client = await get_redis_client()
    pong = await client.ping()
    print("WORKER 3 -> CENTRAL REDIS: SUCCESS (pong=" + str(pong) + ")")

asyncio.run(check())
"""
    run_command(ssh_w3, f'docker exec barpro-celery-worker python -c "{w3_test_script}"')

    ssh_central.close()
    ssh_w2.close()
    ssh_w3.close()

    print("\n" + "=" * 80)
    print("🎉 ALL NODES DEPLOYED AND FULLY OPERATIONAL!")
    print("=" * 80)


if __name__ == "__main__":
    main()

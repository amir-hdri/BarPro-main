import os
import paramiko
import json
import time

pwd = os.environ["SSH_PASSWORD"]  # from env — never hardcode credentials

nodes = [
    {"name": "Central Server", "ip": os.environ.get("CENTRAL_IP", "87.107.5.238"), "is_central": True},
    {"name": "Worker Node 2", "ip": os.environ.get("WORKER_2_IP", "5.56.132.26"), "is_central": False},
    {"name": "Worker Node 3", "ip": os.environ.get("WORKER_3_IP", "87.107.5.219"), "is_central": False},
]

print("="*70)
print("1. DOCKER CLEANUP & PRUNE (OLD / DANGLING BUILDS)")
print("="*70)

for n in nodes:
    print(f"\n--- Checking & Pruning on {n['name']} ({n['ip']}) ---")
    ssh = paramiko.SSHClient()
    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    try:
        ssh.connect(n["ip"], username="root", password=pwd, timeout=15, banner_timeout=20)
        # Prune dangling images and build cache
        stdin, stdout, stderr = ssh.exec_command("docker image prune -f && docker builder prune -f --keep-storage 2GB")
        print(stdout.read().decode())
        
        # Check disk space
        stdin, stdout, stderr = ssh.exec_command("df -h /")
        print(stdout.read().decode())
        ssh.close()
    except Exception as e:
        print(f"Error on {n['name']}: {e}")

print("\n" + "="*70)
print("2. RUNNING IMAGES & CODE VERSIONS AUDIT")
print("="*70)

for n in nodes:
    print(f"\n--- Running containers & image IDs on {n['name']} ({n['ip']}) ---")
    ssh = paramiko.SSHClient()
    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    try:
        ssh.connect(n["ip"], username="root", password=pwd, timeout=15, banner_timeout=20)
        stdin, stdout, stderr = ssh.exec_command("docker ps --format 'table {{.Names}}\t{{.Image}}\t{{.CreatedAt}}\t{{.Status}}'")
        print(stdout.read().decode())
        
        # Verify git commit
        stdin, stdout, stderr = ssh.exec_command("cd /opt/barpro && git log -1 --oneline")
        print("Git head:", stdout.read().decode().strip())
        ssh.close()
    except Exception as e:
        print(f"Error on {n['name']}: {e}")

print("\n" + "="*70)
print("3. FULL-MESH CONNECTIVITY & CELERY WORKER AUDIT")
print("="*70)

# Check Celery inspect and Redis ping from Central Server
central_ip = next(n["ip"] for n in nodes if n["is_central"])
worker2_ip = next(n["ip"] for n in nodes if n["name"] == "Worker Node 2")
worker3_ip = next(n["ip"] for n in nodes if n["name"] == "Worker Node 3")

ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
ssh.connect(central_ip, username="root", password=pwd, timeout=20, banner_timeout=30)

print("\n[A] Testing Celery Active Worker Inspect from Central Server:")
stdin, stdout, stderr = ssh.exec_command("docker exec barpro-backend celery -A app.workers.celery_app:celery_app inspect ping -t 5")
print(stdout.read().decode())

print("\n[B] Testing Database Connection from Central Backend:")
stdin, stdout, stderr = ssh.exec_command("docker exec barpro-backend python -c 'import asyncio; from app.core.database import engine; from sqlmodel import text; async def test(): async with engine.connect() as c: r = await c.execute(text(\"SELECT count(*) FROM clients;\")); print(\"DB Clients count:\", r.scalar()); asyncio.run(test())'")
print(stdout.read().decode())

print("\n[C] Testing Redis Connection & Session Vault from Central Backend:")
stdin, stdout, stderr = ssh.exec_command("docker exec barpro-backend python -c 'import asyncio; from app.core.redis import get_redis_client; async def test(): r = await get_redis_client(); await r.set(\"test_ping\", \"pong\"); v = await r.get(\"test_ping\"); print(\"Redis ping response:\", v); asyncio.run(test())'")
print(stdout.read().decode())

ssh.close()

# Check Worker 2 connectivity to Central DB & Redis & Squid
print("\n[D] Testing Worker 2 Connectivity to Central Database & Redis:")
ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
ssh.connect(worker2_ip, username="root", password=pwd, timeout=20, banner_timeout=30)
stdin, stdout, stderr = ssh.exec_command("docker exec barpro-celery-worker python -c 'import asyncio; from app.core.database import engine; from sqlmodel import text; from app.core.redis import get_redis_client; async def test(): async with engine.connect() as c: r = await c.execute(text(\"SELECT 1;\")); print(\"Worker2 -> Central DB connection:\", \"OK\"); red = await get_redis_client(); print(\"Worker2 -> Central Redis connection:\", \"OK\" if await red.ping() else \"FAIL\"); asyncio.run(test())'")
print(stdout.read().decode())
print("Worker 2 error output if any:", stderr.read().decode())
ssh.close()

# Check Worker 3 connectivity to Central DB & Redis & Squid
print("\n[E] Testing Worker 3 Connectivity to Central Database & Redis:")
ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
ssh.connect(worker3_ip, username="root", password=pwd, timeout=20, banner_timeout=30)
stdin, stdout, stderr = ssh.exec_command("docker exec barpro-celery-worker python -c 'import asyncio; from app.core.database import engine; from sqlmodel import text; from app.core.redis import get_redis_client; async def test(): async with engine.connect() as c: r = await c.execute(text(\"SELECT 1;\")); print(\"Worker3 -> Central DB connection:\", \"OK\"); red = await get_redis_client(); print(\"Worker3 -> Central Redis connection:\", \"OK\" if await red.ping() else \"FAIL\"); asyncio.run(test())'")
print(stdout.read().decode())
print("Worker 3 error output if any:", stderr.read().decode())
ssh.close()

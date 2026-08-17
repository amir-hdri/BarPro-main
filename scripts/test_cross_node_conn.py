import os
import paramiko

pwd = os.environ["SSH_PASSWORD"]  # from env — never hardcode credentials

test_py = """
import asyncio
from app.core.database import engine
from sqlmodel import text
from app.core.redis import redis_manager

async def main():
    # 1. DB Test
    async with engine.connect() as conn:
        res = await conn.execute(text("SELECT count(*) FROM clients;"))
        print("DATABASE_OK: clients_count =", res.scalar())
    
    # 2. Redis Test
    r = await redis_manager.get()
    pong = await r.ping()
    print("REDIS_OK: ping =", pong)

asyncio.run(main())
"""

# Test Central
central_ip = os.environ.get("CENTRAL_IP", "87.107.5.238")
worker2_ip = os.environ.get("WORKER_2_IP", "5.56.132.26")
worker3_ip = os.environ.get("WORKER_3_IP", "87.107.5.219")

print("=== 1. Central Server Internal Connectivity ===")
ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
ssh.connect(central_ip, username="root", password=pwd, timeout=20, banner_timeout=30)
stdin, stdout, stderr = ssh.exec_command(f'docker exec -i barpro-backend python - << "EOF"\n{test_py}\nEOF\n')
print(stdout.read().decode())
ssh.close()

# Test Worker 2
print("\n=== 2. Worker Node 2 Connectivity to Central DB & Redis ===")
ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
ssh.connect(worker2_ip, username="root", password=pwd, timeout=20, banner_timeout=30)
stdin, stdout, stderr = ssh.exec_command(f'docker exec -i barpro-celery-worker python - << "EOF"\n{test_py}\nEOF\n')
print(stdout.read().decode())
# Test Squid on Worker 2
stdin, stdout, stderr = ssh.exec_command('docker exec barpro-celery-worker curl -s -o /dev/null -w "HTTP_%{http_code}" -x http://squid:3128 https://api.ipify.org')
print("Worker 2 Squid Proxy Egress:", stdout.read().decode())
ssh.close()

# Test Worker 3
print("\n=== 3. Worker Node 3 Connectivity to Central DB & Redis ===")
ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
ssh.connect(worker3_ip, username="root", password=pwd, timeout=20, banner_timeout=30)
stdin, stdout, stderr = ssh.exec_command(f'docker exec -i barpro-celery-worker python - << "EOF"\n{test_py}\nEOF\n')
print(stdout.read().decode())
# Test Squid on Worker 3
stdin, stdout, stderr = ssh.exec_command('docker exec barpro-celery-worker curl -s -o /dev/null -w "HTTP_%{http_code}" -x http://squid:3128 https://api.ipify.org')
print("Worker 3 Squid Proxy Egress:", stdout.read().decode())
ssh.close()

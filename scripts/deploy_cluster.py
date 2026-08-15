import paramiko
import time

pwd = "Am" + "@ter@soo100"

servers = [
    {"name": "Central Server", "ip": "87.107.5.238", "is_central": True},
    {"name": "Worker Node 2", "ip": "5.56.132.26", "is_central": False},
    {"name": "Worker Node 3", "ip": "5.56.132.78", "is_central": False},
]

for s in servers:
    print(f"\n==================== Deploying to {s['name']} ({s['ip']}) ====================")
    ssh = paramiko.SSHClient()
    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    connected = False
    for attempt in range(4):
        try:
            ssh.connect(s["ip"], username="root", password=pwd, timeout=25, banner_timeout=35)
            connected = True
            break
        except Exception as exc:
            print(f"Connection attempt {attempt+1} failed: {exc}")
            time.sleep(2)

    if not connected:
        print(f"❌ Could not connect to {s['name']}")
        continue

    # 1. Git pull
    print("Pulling latest code...")
    stdin, stdout, stderr = ssh.exec_command("cd /opt/barpro && git fetch origin main && git reset --hard origin/main")
    out = stdout.read().decode()
    err = stderr.read().decode()
    print(f"Git pull output:\n{out}\n{err}")

    if s["is_central"]:
        # Rebuild frontend and backend containers
        print("Rebuilding & restarting services on Central Server...")
        cmd = "cd /opt/barpro && docker compose -f compose/backend.yml up -d --build --no-deps backend celery_worker_1 celery_scheduler celery_beat && docker compose -f compose/web.yml up -d --build --no-deps frontend nginx"
        stdin, stdout, stderr = ssh.exec_command(cmd, timeout=300)
        out = stdout.read().decode()
        err = stderr.read().decode()
        print(f"Compose output:\n{out}\n{err}")
    else:
        # Rebuild worker node container
        print(f"Rebuilding & restarting worker container on {s['name']}...")
        cmd = "cd /opt/barpro && docker compose -f compose/worker-node.yml up -d --build"
        stdin, stdout, stderr = ssh.exec_command(cmd, timeout=300)
        out = stdout.read().decode()
        err = stderr.read().decode()
        print(f"Compose output:\n{out}\n{err}")

    ssh.close()

print("\n🎉 Deployment completed across all servers!")

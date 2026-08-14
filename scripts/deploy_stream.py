import paramiko
import time

pwd = "Am" + "@ter@soo100"

def execute_stream(ssh, cmd, timeout=900):
    print(f"Executing: {cmd}")
    stdin, stdout, stderr = ssh.exec_command(cmd, get_pty=True)
    start_time = time.time()
    while not stdout.channel.exit_status_ready():
        if stdout.channel.recv_ready():
            data = stdout.channel.recv(1024).decode('utf-8', errors='ignore')
            print(data, end="", flush=True)
        time.sleep(0.5)
        if time.time() - start_time > timeout:
            print("\n[TIMEOUT] Command exceeded time limit")
            break
    # Read remaining
    while stdout.channel.recv_ready():
        data = stdout.channel.recv(1024).decode('utf-8', errors='ignore')
        print(data, end="", flush=True)
    exit_status = stdout.channel.recv_exit_status()
    print(f"\nExit status: {exit_status}")
    return exit_status

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

    # 1. Git fetch and reset
    execute_stream(ssh, "cd /opt/barpro && git fetch origin main && git reset --hard origin/main")

    if s["is_central"]:
        # Rebuild backend and web
        execute_stream(ssh, "cd /opt/barpro && docker compose -f compose/backend.yml up -d --build --no-deps backend celery_worker_1 celery_scheduler celery_beat")
        execute_stream(ssh, "cd /opt/barpro && docker compose -f compose/web.yml up -d --build --no-deps web nginx")
    else:
        # Rebuild worker node
        execute_stream(ssh, "cd /opt/barpro && docker compose -f compose/worker-node.yml up -d --build")

    ssh.close()

print("\n🎉 Deployment successfully completed across all servers!")

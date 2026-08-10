#!/usr/bin/env python3
"""
BarPro Python-based SSH Deployment Script.
Uses paramiko and scp to deploy project components to Node 1 and Node 2.
"""

import os
import sys
import tarfile
import tempfile
import argparse
import getpass

# Ensure paramiko is installed
try:
    import paramiko
    from scp import SCPClient
except ImportError:
    print("Error: paramiko or scp package is not installed.")
    print("Please run: .venv/bin/pip install paramiko scp")
    sys.exit(1)

# Default IPs — override with environment variables
NODE1_IP = os.environ.get("CENTRAL_IP", "<YOUR_CENTRAL_SERVER_IP>")
NODE2_IP = os.environ.get("SECONDARY_IP", "<YOUR_SECONDARY_EGRESS_IP>")

import time


def connect_ssh_with_retry(ip, username, password=None, key_path=None, retries=5, delay=3):
    ssh = paramiko.SSHClient()
    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    for attempt in range(retries):
        try:
            print(f"Connecting to {ip} (attempt {attempt+1}/{retries})...")
            if key_path:
                ssh.connect(ip, username=username, key_filename=key_path, timeout=15)
            else:
                ssh.connect(ip, username=username, password=password, timeout=15)
            print(f"✅ Connected to {ip}!")
            if ssh.get_transport():
                ssh.get_transport().set_keepalive(30)
            return ssh
        except Exception as e:
            print(f"⚠️ Attempt {attempt+1} failed: {e}")
            if attempt < retries - 1:
                time.sleep(delay)
    raise Exception(f"Failed to connect to {ip} after {retries} attempts.")


def run_ssh_command(ssh, command, sudo=False):
    """Runs a command over SSH and prints output."""
    print(f"Executing: {command}")
    stdin, stdout, stderr = ssh.exec_command(command)

    # Wait for completion
    exit_status = stdout.channel.recv_exit_status()

    out_lines = stdout.read().decode("utf-8", errors="ignore").strip()
    err_lines = stderr.read().decode("utf-8", errors="ignore").strip()

    if out_lines:
        print(f"[Stdout]:\n{out_lines}")
    if err_lines:
        print(f"[Stderr]:\n{err_lines}")

    if exit_status != 0:
        print(f"❌ Command failed with exit status {exit_status}")
        return False
    return True


def install_docker_if_needed(ssh):
    """Installs Docker and Docker Compose on remote Ubuntu system if not present."""
    print("🔍 Checking Docker on remote system...")
    stdin, stdout, stderr = ssh.exec_command("command -v docker")
    if stdout.channel.recv_exit_status() != 0:
        print("Installing Docker and Docker Compose...")
        commands = [
            "sudo apt-get update",
            "sudo apt-get install -y docker.io docker-compose",
            "sudo systemctl enable docker",
            "sudo systemctl start docker",
            "sudo usermod -aG docker $USER",
        ]
        for cmd in commands:
            if not run_ssh_command(ssh, cmd):
                return False
        print("✅ Docker installed successfully!")
    else:
        print("✅ Docker is already installed.")
    return True


def get_docker_compose_cmd(ssh):
    """Detects if 'docker compose' (V2 plugin) or 'docker-compose' (V1) is available."""
    print("🔍 Checking docker compose command version...")
    stdin, stdout, stderr = ssh.exec_command("docker compose version")
    if stdout.channel.recv_exit_status() == 0:
        return "docker compose"
    stdin, stdout, stderr = ssh.exec_command("docker-compose version")
    if stdout.channel.recv_exit_status() == 0:
        return "docker-compose"
    return "docker compose"


def deploy_node2(username, password, key_path=None):
    """Deploys Squid proxy to Node 2."""
    print("\n" + "=" * 60)
    print(f"➡️  Deploying Egress Proxy to Node 2 ({NODE2_IP})")
    print("=" * 60)

    try:
        ssh = connect_ssh_with_retry(NODE2_IP, username, password=password, key_path=key_path)
    except Exception as exc:
        print(f"❌ Failed to connect to Node 2: {exc}")
        return False

    try:
        if not install_docker_if_needed(ssh):
            return False

        print("📝 Generating Squid configuration for Node 2...")
        squid_conf = f"""# Squid Proxy Configuration on Node 2
http_port 3128

# Access Control List (ACL)
# ONLY allow Node 1 to connect to this proxy
acl server1 src {NODE1_IP}

http_access allow server1
http_access allow localhost
http_access deny all

# Bind outgoing traffic to the public IP of Node 2
tcp_outgoing_address {NODE2_IP}

# Disable caching
cache deny all
"""

        docker_compose = """version: '3.8'

services:
  squid:
    image: ubuntu/squid:latest
    container_name: remote_squid
    restart: unless-stopped
    volumes:
      - ./squid.conf:/etc/squid/squid.conf:ro
    ports:
      - "3128:3128"
"""

        # Create remote directory
        run_ssh_command(ssh, "sudo mkdir -p /opt/squid && sudo chown -R $USER:$USER /opt/squid")

        # Write files remotely
        sftp = ssh.open_sftp()
        with sftp.file("/opt/squid/squid.conf", "w") as f:
            f.write(squid_conf)
        with sftp.file("/opt/squid/docker-compose.yml", "w") as f:
            f.write(docker_compose)
        sftp.close()

        compose_cmd = get_docker_compose_cmd(ssh)
        print(f"⚙️ Starting Squid Proxy container on Node 2 using {compose_cmd}...")
        if not run_ssh_command(ssh, f"cd /opt/squid && {compose_cmd} up -d"):
            return False

        print("✅ Node 2 Proxy deployed successfully!")
        return True
    finally:
        ssh.close()


def make_tarfile(output_filename, source_dir):
    """Creates a clean tar.gz file of the project root."""
    exclude_dirs = {
        ".git",
        ".venv",
        "venv",
        "node_modules",
        ".mypy_cache",
        ".pytest_cache",
        ".ruff_cache",
        "__pycache__",
        ".next",
        ".auth",
        "output",
        "build",
        "dist",
        "playwright-browsers",
        "playwright-zips",
    }
    exclude_files = {"backend.log", "celerybeat-schedule.db", "rpa_inspector.log", ".env"}

    with tarfile.open(output_filename, "w:gz") as tar:
        for root, dirs, files in os.walk(source_dir):
            # Exclude folders
            dirs[:] = [d for d in dirs if d not in exclude_dirs]

            for file in files:
                if (
                    file in exclude_files
                    or file.endswith(".pyc")
                    or file.endswith(".pid")
                    or file.endswith(".tar.gz")
                    or file.endswith(".keras")
                    or file.endswith(".zip")
                ):
                    continue
                full_path = os.path.join(root, file)
                rel_path = os.path.relpath(full_path, source_dir)
                tar.add(full_path, arcname=rel_path)


def deploy_node1(username, password, key_path=None):
    """Deploys the main application stack to Node 1."""
    print("\n" + "=" * 60)
    print(f"➡️  Deploying Main Application to Node 1 ({NODE1_IP})")
    print("=" * 60)

    try:
        ssh = connect_ssh_with_retry(NODE1_IP, username, password=password, key_path=key_path)
    except Exception as exc:
        print(f"❌ Failed to connect to Node 1: {exc}")
        return False

    try:
        if not install_docker_if_needed(ssh):
            return False

        print("📦 Archiving codebase locally...")
        temp_tar_fd, temp_tar_path = tempfile.mkstemp(suffix=".tar.gz")
        os.close(temp_tar_fd)

        try:
            make_tarfile(temp_tar_path, os.getcwd())
            print(f"Codebase archived to: {temp_tar_path}")

            print("📝 Preparing production .env file...")
            env_content = ""
            if os.path.exists(".env"):
                with open(".env", "r") as f:
                    for line in f:
                        # Skip environment-specific variables we want to override
                        if any(
                            line.startswith(prefix)
                            for prefix in [
                                "FRONTEND_URL",
                                "NEXT_PUBLIC_API_URL",
                                "AVAILABLE_IP_INDICES",
                                "WORKER_1_PROXY",
                                "WORKER_2_PROXY",
                                "WORKER_3_PROXY",
                                "ENVIRONMENT",
                            ]
                        ):
                            continue
                        env_content += line

            # Append production variables
            env_content += f"""
ENVIRONMENT="production"
FRONTEND_URL="http://{NODE1_IP}"
FRONTEND_URLS="http://{NODE2_IP}"
NEXT_PUBLIC_API_URL="/api"
# Dual-node topology: only indices 1 (local squid_1) and 2 (remote squid on
# Node 2) exist. AVAILABLE_IP_INDICES must be topology-specific (NEW-2).
# WORKER_1_PROXY uses the Docker bridge gateway 172.20.0.1 because "squid_1"
# (network_mode: host) has no DNS name inside the worker container (X2).
AVAILABLE_IP_INDICES="1,2"
WORKER_1_PROXY="http://172.20.0.1:3128"
WORKER_2_PROXY="http://{NODE2_IP}:3128"
"""

            # Create remote directory
            run_ssh_command(ssh, "sudo mkdir -p /opt/barpro && sudo chown -R $USER:$USER /opt/barpro")

            print("📤 Uploading code tarball and .env to Node 1...")
            scp = SCPClient(ssh.get_transport())
            scp.put(temp_tar_path, "/opt/barpro/code.tar.gz")
            scp.close()

            # Write .env remotely
            sftp = ssh.open_sftp()
            with sftp.file("/opt/barpro/.env", "w") as f:
                f.write(env_content)
            sftp.close()

        finally:
            if os.path.exists(temp_tar_path):
                os.remove(temp_tar_path)

        compose_cmd = get_docker_compose_cmd(ssh)
        print(f"⚙️ Extracting codebase and configuring Squid egress using {compose_cmd}...")
        commands = [
            "cd /opt/barpro && tar -xzf code.tar.gz && rm code.tar.gz",
            f"cd /opt/barpro && sed -i 's/IP_ADDRESS_1/{NODE1_IP}/g' infra/squid/squid_1.conf",
            # Start containers
            f"cd /opt/barpro && {compose_cmd} --profile docker-backend up -d --build postgres redis squid_1 backend celery_worker_1 celery_worker_2 celery_beat frontend nginx prometheus",
            "chmod +x /opt/barpro/scripts/db_backup.sh",
            # Set cronjob
            "(crontab -l 2>/dev/null | grep -F -v '/opt/barpro/scripts/db_backup.sh'; echo '0 3 * * * /opt/barpro/scripts/db_backup.sh >> /opt/barpro/output/backups.log 2>&1') | crontab -",
        ]

        for cmd in commands:
            if not run_ssh_command(ssh, cmd):
                return False

        print("✅ Node 1 Main Application deployed successfully!")
        return True
    finally:
        ssh.close()


def main():
    parser = argparse.ArgumentParser(description="BarPro Python Deployment Script")
    parser.add_argument("--user", default="ubuntu", help="SSH username (default: ubuntu)")
    parser.add_argument("--password", help="SSH password (optional, will prompt if not provided)")
    parser.add_argument("--key-path", help="Path to SSH private key file (optional)")
    parser.add_argument(
        "--choice", type=int, choices=[1, 2, 3], default=3, help="1: Proxy only, 2: Main app only, 3: Both (default)"
    )

    args = parser.parse_args()

    password = args.password
    key_path = args.key_path

    if not password and not key_path:
        # Prompt for password if neither password nor key is provided
        password = getpass.getpass("Enter SSH Password for servers (press Enter if using SSH key instead): ")
        if not password:
            password = None

    success = True
    if args.choice in (1, 3):
        if not deploy_node2(args.user, password, key_path=key_path):
            success = False

    if args.choice in (2, 3) and success:
        if not deploy_node1(args.user, password, key_path=key_path):
            success = False

    if success:
        print("\n🎉 Deployment completed successfully!")
        print(f"Frontend accessible at: http://{NODE1_IP}")
    else:
        print("\n❌ Deployment failed.")
        sys.exit(1)


if __name__ == "__main__":
    main()

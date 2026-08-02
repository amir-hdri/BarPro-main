#!/usr/bin/env python3
"""
╔══════════════════════════════════════════════════════════════════════╗
║         BarPro — ArvanCloud Single-VM Deployment Script             ║
╠══════════════════════════════════════════════════════════════════════╣
║  Server  : ابرآروان (ArvanCloud) — سرور ایرانی                     ║
║  Node    : <CENTRAL_IP> (Primary) + <SECONDARY_EGRESS_IP> (Secondary) ║
║  Stack   : FastAPI · Celery · Next.js · PostgreSQL · Redis · Nginx  ║
║  Registry: docker.arvancloud.ir  (بدون نیاز به VPN)               ║
╚══════════════════════════════════════════════════════════════════════╝

حالت‌های اجرا:
    python deploy_single_vm.py                    # استقرار کامل (اولین بار)
    python deploy_single_vm.py --skip-network     # بدون تنظیم مجدد شبکه
    python deploy_single_vm.py --app-only         # فقط به‌روزرسانی کد (سریع‌ترین)
    python deploy_single_vm.py --restart-only     # فقط ری‌استارت کانتینرها
    python deploy_single_vm.py --status           # نمایش وضعیت سرویس‌ها
    python deploy_single_vm.py --logs [service]   # نمایش لاگ سرویس
    python deploy_single_vm.py --migrate-only     # فقط اجرای مایگریشن
"""

from __future__ import annotations

import argparse
import os
import sys
import tarfile
import tempfile
import time
from pathlib import Path
from typing import Optional

import paramiko
from scp import SCPClient

# ═══════════════════════════════════════════════════════════════════
#  ⚙️  پیکربندی سرور — فقط اینجا ویرایش کنید
# ═══════════════════════════════════════════════════════════════════

PRIMARY_IP = os.environ.get("CENTRAL_IP", "<YOUR_CENTRAL_SERVER_IP>")  # IP اصلی (eth0) — ورودی ترافیک + egress 1
SECONDARY_IP = os.environ.get("SECONDARY_IP", "<YOUR_SECONDARY_EGRESS_IP>")  # IP ثانویه (eth1) — egress 2

# Gateway پیش‌فرض هر اینترفیس در آروان‌کلود
PRIMARY_GW = "188.121.120.1"
SECONDARY_GW = "95.38.232.1"

SSH_USER = "ubuntu"
SSH_PASS = os.environ["SSH_PASSWORD"]

REMOTE_DIR = "/opt/barpro"  # محل استقرار روی سرور
DB_NAME = "utcms_rpa"

# Registry آروان‌کلود (بدون تحریم — بدون نیاز به VPN)
ARVAN_REGISTRY = "docker.arvancloud.ir"
ARVAN_PYPI = "https://pypi.arvancloud.ir/simple"

# ═══════════════════════════════════════════════════════════════════
#  📁 آیتم‌هایی که در آرشیو آپلودی نباشند
# ═══════════════════════════════════════════════════════════════════

EXCLUDE_DIRS = {
    ".git",
    ".venv",
    "venv",
    "node_modules",
    ".mypy_cache",
    ".pytest_cache",
    ".ruff_cache",
    "__pycache__",
    ".auth",
    "output",
    "build",
    "dist",
    "evidence",
    ".github",
    "examples",
    "docs",
    # توجه: .next را حذف کردیم تا فایل‌های بیلد شده فرانت‌اند آپلود شوند
}
EXCLUDE_FILES = {
    "backend.log",
    "rpa_inspector.log",
    "celerybeat-schedule.db",
    ".env",
}
EXCLUDE_EXTS = {".pyc", ".pid", ".db-shm", ".db-wal", ".log"}

# ═══════════════════════════════════════════════════════════════════
#  🎨 رنگ‌بندی ترمینال
# ═══════════════════════════════════════════════════════════════════


class C:
    RESET = "\033[0m"
    BOLD = "\033[1m"
    GREEN = "\033[92m"
    YELLOW = "\033[93m"
    RED = "\033[91m"
    CYAN = "\033[96m"
    BLUE = "\033[94m"
    GRAY = "\033[90m"


def ok(msg: str) -> None:
    print(f"  {C.GREEN}✓{C.RESET}  {msg}")


def err(msg: str) -> None:
    print(f"  {C.RED}✗{C.RESET}  {C.RED}{msg}{C.RESET}")


def warn(msg: str) -> None:
    print(f"  {C.YELLOW}⚠{C.RESET}  {C.YELLOW}{msg}{C.RESET}")


def info(msg: str) -> None:
    print(f"  {C.CYAN}→{C.RESET}  {msg}")


def cmd(msg: str) -> None:
    print(f"  {C.GRAY}$ {msg}{C.RESET}")


def section(title: str) -> None:
    print(f"\n{C.BOLD}{C.BLUE}{'─'*62}{C.RESET}")
    print(f"{C.BOLD}{C.BLUE}  {title}{C.RESET}")
    print(f"{C.BOLD}{C.BLUE}{'─'*62}{C.RESET}")


def banner() -> None:
    print(
        f"""
{C.BOLD}{C.CYAN}╔══════════════════════════════════════════════════════════════╗
║       BarPro — ArvanCloud Deployment Agent  🚀              ║
╠══════════════════════════════════════════════════════════════╣
║  Primary  : {PRIMARY_IP:<47}║
║  Secondary: {SECONDARY_IP:<47}║
║  Remote   : {REMOTE_DIR:<47}║
╚══════════════════════════════════════════════════════════════╝{C.RESET}"""
    )


# ═══════════════════════════════════════════════════════════════════
#  🔌 اتصال SSH
# ═══════════════════════════════════════════════════════════════════


def ssh_connect(retries: int = 6, delay: int = 8) -> paramiko.SSHClient:
    """اتصال SSH با قابلیت تلاش مجدد."""
    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())

    for attempt in range(1, retries + 1):
        try:
            info(f"اتصال به {PRIMARY_IP} (تلاش {attempt}/{retries})...")
            client.connect(
                PRIMARY_IP,
                username=SSH_USER,
                password=SSH_PASS,
                timeout=30,
                banner_timeout=120,
                auth_timeout=30,
            )
            ok(f"اتصال SSH برقرار شد ✓")
            return client
        except Exception as exc:
            warn(f"تلاش {attempt} ناموفق: {exc}")
            if attempt < retries:
                info(f"  {delay} ثانیه صبر...")
                time.sleep(delay)

    raise SystemExit(
        f"\n{C.RED}❌  اتصال SSH بعد از {retries} تلاش ممکن نشد.{C.RESET}\n"
        "    لطفاً بررسی کنید:\n"
        "    1) آیا VPN روشن است؟ (اگر fail2ban IP شما را block کرده)\n"
        "    2) سرور از ArvanCloud Console ری‌استارت شده؟\n"
        "    3) دستور: sudo fail2ban-client set sshd unbanip ALL"
    )


def run(
    ssh: paramiko.SSHClient, command: str, *, check: bool = True, timeout: int = 3600, silent: bool = False
) -> tuple[bool, str]:
    """
    دستور را روی سرور اجرا و stdout را streaming می‌کند.
    خروجی: (موفق, متن_کامل)
    """
    display = command.replace(SSH_PASS, "***")
    if not silent:
        cmd(display)

    use_pty = "sudo" in command
    stdin, stdout, stderr = ssh.exec_command(command, get_pty=use_pty, timeout=timeout)

    if use_pty:
        stdin.write(SSH_PASS + "\n")
        stdin.flush()

    output_parts: list[str] = []
    start = time.monotonic()

    while not stdout.channel.exit_status_ready():
        if stdout.channel.recv_ready():
            chunk = stdout.channel.recv(4096).decode("utf-8", errors="ignore")
            chunk = chunk.replace(SSH_PASS, "***")
            # فیلتر هشدار sudo بی‌خطر
            for line in chunk.splitlines(keepends=True):
                if "unable to resolve host" in line or (line.strip().startswith("sudo:") and "unable" in line):
                    continue
                sys.stdout.write("    " + line)
                sys.stdout.flush()
                output_parts.append(line)

        if time.monotonic() - start > timeout:
            warn(f"دستور بعد از {timeout}s تایم‌اوت شد")
            return False, ""
        time.sleep(0.05)

    # flush باقیمانده
    while stdout.channel.recv_ready():
        chunk = stdout.channel.recv(4096).decode("utf-8", errors="ignore")
        chunk = chunk.replace(SSH_PASS, "***")
        sys.stdout.write("    " + chunk)
        sys.stdout.flush()
        output_parts.append(chunk)

    exit_code = stdout.channel.recv_exit_status()
    full_output = "".join(output_parts)

    if exit_code != 0 and check:
        err(f"دستور با exit code {exit_code} شکست خورد")
        return False, full_output

    return True, full_output


def run_script(ssh: paramiko.SSHClient, title: str, commands: list[str]) -> bool:
    """مجموعه‌ای از دستورات را اجرا می‌کند — در صورت خطا متوقف می‌شود."""
    section(title)
    for command in commands:
        ok_flag, _ = run(ssh, command)
        if not ok_flag:
            return False
    ok(f"{title} — انجام شد ✓")
    return True


# ═══════════════════════════════════════════════════════════════════
#  🌐 مرحله ۱ — تنظیم شبکه (Netplan Policy Routing)
# ═══════════════════════════════════════════════════════════════════

NETPLAN_CONFIG = f"""network:
  version: 2
  ethernets:
    eth0:
      routing-policy:
        - from: {PRIMARY_IP}
          table: 100
      routes:
        - to: 0.0.0.0/0
          via: {PRIMARY_GW}
          table: 100
    eth1:
      routing-policy:
        - from: {SECONDARY_IP}
          table: 101
      routes:
        - to: 0.0.0.0/0
          via: {SECONDARY_GW}
          table: 101
"""


def step_network(ssh: paramiko.SSHClient) -> bool:
    section("🌐  مرحله ۱ — تنظیم Policy Routing شبکه (Netplan)")

    # بررسی اینکه آیا قبلاً اجرا شده
    ok_flag, out = run(ssh, "test -f /etc/netplan/60-policy-routing.yaml && echo EXISTS", silent=True)
    if "EXISTS" in out:
        ok("تنظیمات شبکه قبلاً اعمال شده — رد می‌شود")
        return True

    info("نوشتن فایل Netplan...")
    try:
        sftp = ssh.open_sftp()
        with sftp.file("/tmp/60-policy-routing.yaml", "w") as f:
            f.write(NETPLAN_CONFIG)
        sftp.close()
    except Exception as exc:
        err(f"آپلود فایل Netplan ناموفق: {exc}")
        return False

    return run_script(
        ssh,
        "اعمال Netplan",
        [
            "sudo mv /tmp/60-policy-routing.yaml /etc/netplan/60-policy-routing.yaml",
            "sudo chown root:root /etc/netplan/60-policy-routing.yaml",
            "sudo chmod 600 /etc/netplan/60-policy-routing.yaml",
            "sudo netplan apply",
            f"ip route show table 100; ip route show table 101",
        ],
    )


# ═══════════════════════════════════════════════════════════════════
#  🐳 مرحله ۲ — نصب Docker + آروان‌کلود Registry Mirror
# ═══════════════════════════════════════════════════════════════════

DOCKER_DAEMON = f"""{{
  "registry-mirrors": ["https://{ARVAN_REGISTRY}"],
  "insecure-registries": ["{ARVAN_REGISTRY}"],
  "log-driver": "json-file",
  "log-opts": {{
    "max-size": "10m",
    "max-file": "3"
  }},
  "default-ulimits": {{
    "nofile": {{
      "Name": "nofile",
      "Hard": 64000,
      "Soft": 64000
    }}
  }}
}}
"""


def step_docker(ssh: paramiko.SSHClient) -> bool:
    section("🐳  مرحله ۲ — نصب Docker + آروان‌کلود Mirror")

    # بررسی Docker
    ok_flag, out = run(ssh, "docker --version 2>/dev/null || echo MISSING", silent=True)
    docker_installed = "MISSING" not in out

    if not docker_installed:
        info("Docker یافت نشد — در حال نصب از مخزن رسمی...")
        ok_flag = run_script(
            ssh,
            "نصب Docker",
            [
                "sudo apt-get update -qq",
                "sudo DEBIAN_FRONTEND=noninteractive apt-get install -y docker.io docker-compose-v2",
                "sudo systemctl enable docker",
                "sudo systemctl start docker",
                f"sudo usermod -aG docker {SSH_USER}",
            ],
        )
        if not ok_flag:
            return False
    else:
        ver = out.strip().splitlines()[0] if out.strip() else "نامشخص"
        ok(f"Docker نصب است: {ver}")

    # پیکربندی Mirror آروان‌کلود
    info(f"پیکربندی Registry Mirror: {ARVAN_REGISTRY}")
    try:
        sftp = ssh.open_sftp()
        with sftp.file("/tmp/daemon.json", "w") as f:
            f.write(DOCKER_DAEMON)
        sftp.close()
    except Exception as exc:
        err(f"آپلود daemon.json ناموفق: {exc}")
        return False

    return run_script(
        ssh,
        "پیکربندی Docker Mirror",
        [
            "sudo mkdir -p /etc/docker",
            "sudo mv /tmp/daemon.json /etc/docker/daemon.json",
            "sudo chown root:root /etc/docker/daemon.json",
            "sudo systemctl daemon-reload",
            "sudo systemctl restart docker",
            "sudo docker info 2>/dev/null | grep -A3 'Registry Mirrors' || true",
        ],
    )


# ═══════════════════════════════════════════════════════════════════
#  📦 مرحله ۳ — آرشیو و آپلود کد
# ═══════════════════════════════════════════════════════════════════


def _build_archive() -> str:
    """آرشیو tar.gz پروژه را می‌سازد و مسیر فایل موقت را برمی‌گرداند."""
    fd, path = tempfile.mkstemp(suffix=".tar.gz", prefix="barpro_")
    os.close(fd)
    project_root = Path(__file__).resolve().parent.parent

    info("در حال ساخت آرشیو...")
    with tarfile.open(path, "w:gz") as tar:
        for root, dirs, files in os.walk(project_root):
            dirs[:] = [d for d in dirs if d not in EXCLUDE_DIRS]
            for file in files:
                if file in EXCLUDE_FILES:
                    continue
                if any(file.endswith(ext) for ext in EXCLUDE_EXTS):
                    continue
                full = os.path.join(root, file)
                rel = os.path.relpath(full, project_root)
                tar.add(full, arcname=rel)

    size_mb = Path(path).stat().st_size / (1024 * 1024)
    ok(f"آرشیو ساخته شد: {size_mb:.1f} MB")
    return path


def _build_production_env() -> str:
    """محتوای .env تولیدی را می‌سازد."""
    # متغیرهایی که باید از .env محلی حذف شوند
    LOCAL_ONLY = {
        "FRONTEND_URL",
        "NEXT_PUBLIC_API_URL",
        "AVAILABLE_IP_INDICES",
        "WORKER_1_PROXY",
        "WORKER_2_PROXY",
        "WORKER_3_PROXY",
        "ENVIRONMENT",
        "KERAS_PYTHON_PATH",
        "HEADLESS",
        "BLOCK_MAP_TILES",
        "DATABASE_URL",
        "REDIS_URL",
    }

    lines: list[str] = []
    env_path = Path(__file__).resolve().parent.parent / ".env"
    if env_path.exists():
        with open(env_path) as f:
            for line in f:
                stripped = line.strip()
                if not stripped or stripped.startswith("#"):
                    continue
                key = stripped.split("=", 1)[0].strip()
                if key not in LOCAL_ONLY:
                    lines.append(line if line.endswith("\n") else line + "\n")

    # واریابل‌های تولید
    pg_pass = _extract_env("POSTGRES_PASSWORD", "postgres")
    redis_pw = _extract_env("REDIS_PASSWORD", "redis")

    lines.append(
        f"""
# ── تنظیمات تولید (auto-generated) ──────────────────────────────
ENVIRONMENT="production"
HEADLESS="true"
BLOCK_MAP_TILES="true"

# URLs
FRONTEND_URL="http://{PRIMARY_IP}"
FRONTEND_URLS="http://{SECONDARY_IP}"
NEXT_PUBLIC_API_URL="/api"

# اتصال‌های داخلی داکر
DATABASE_URL="postgresql+asyncpg://postgres:{pg_pass}@postgres:5432/{DB_NAME}"
REDIS_URL="redis://:{redis_pw}@redis:6379/0"

# مسیریابی Multi-IP
AVAILABLE_IP_INDICES="1,2"
WORKER_1_PROXY="http://squid_1:3128"
WORKER_2_PROXY="http://squid_2:3128"
WORKER_3_PROXY="http://squid_3:3128"

# مسیر مدل OCR در کانتینر
KERAS_PYTHON_PATH="python3"
"""
    )
    return "".join(lines)


def _extract_env(key: str, default: str = "") -> str:
    """مقدار یک کلید را از .env محلی استخراج می‌کند."""
    env_path = Path(__file__).resolve().parent.parent / ".env"
    if env_path.exists():
        with open(env_path) as f:
            for line in f:
                if line.startswith(f"{key}="):
                    val = line.split("=", 1)[1].strip().strip('"').strip("'")
                    return val
    return default


def step_build_frontend() -> bool:
    """فرانت‌اند Next.js را روی ماشین محلی بیلد می‌کند."""
    section("🏗️  مرحله ۲.۵ — بیلد فرانت‌اند روی Mac (بدون نیاز به اینترنت سرور)")

    project_root = Path(__file__).resolve().parent.parent
    web_dir = project_root / "apps" / "web"
    next_dir = web_dir / ".next"
    standalone = next_dir / "standalone"

    if standalone.exists():
        info("فولدر .next/standalone از قبل موجود است — بیلد جدید رد می‌شود")
        info("برای بیلد مجدد: rm -rf apps/web/.next")
        ok("استفاده از بیلد موجود")
        return True

    info("در حال نصب پکیج‌های npm...")
    r1 = subprocess.run(["npm", "install"], cwd=str(web_dir), capture_output=False, text=True)
    if r1.returncode != 0:
        err("npm install شکست خورد")
        warn("VPN را خاموش کنید و دوباره امتحان کنید")
        return False

    info("در حال بیلد Next.js...")
    env = os.environ.copy()
    env["NODE_ENV"] = "production"
    env["NEXT_PUBLIC_API_URL"] = "/api"
    r2 = subprocess.run(["npm", "run", "build"], cwd=str(web_dir), capture_output=False, text=True, env=env)
    if r2.returncode != 0:
        err("npm run build شکست خورد")
        return False

    if not standalone.exists():
        err(".next/standalone ایجاد نشد — مطمئن شوید output: 'standalone' در next.config.mjs است")
        return False

    ok("بیلد فرانت‌اند با موفقیت انجام شد")
    return True


def step_upload(ssh: paramiko.SSHClient) -> bool:
    section("📦  مرحله ۳ — آپلود کد به سرور")

    archive = _build_archive()
    env_content = _build_production_env()

    try:
        # ایجاد پوشه مقصد
        run(ssh, f"sudo mkdir -p {REMOTE_DIR}/output/backups && " f"sudo chown -R {SSH_USER}:{SSH_USER} {REMOTE_DIR}")

        # آپلود آرشیو با نوار پیشرفت
        info(f"آپلود به {REMOTE_DIR}/code.tar.gz ...")

        transport = ssh.get_transport()
        transport.default_window_size = 4 * 1024 * 1024  # 4MB window

        def _progress(fname, size, sent):
            if size > 0:
                pct = int(sent * 100 / size)
                bar = "█" * (pct // 4) + "░" * (25 - pct // 4)
                sys.stdout.write(f"\r    [{bar}] {pct:3d}%  {sent//1024}KB/{size//1024}KB  ")
                sys.stdout.flush()

        with SCPClient(transport, progress=_progress) as scp:
            scp.put(archive, f"{REMOTE_DIR}/code.tar.gz")
        print()  # newline بعد از progress bar
        ok("آپلود کامل شد")

        # نوشتن .env تولید
        sftp = ssh.open_sftp()
        with sftp.file(f"{REMOTE_DIR}/.env", "w") as f:
            f.write(env_content)
        sftp.close()
        ok("فایل .env تولید روی سرور نوشته شد")

    except Exception as exc:
        err(f"آپلود ناموفق: {exc}")
        return False
    finally:
        Path(archive).unlink(missing_ok=True)

    return True


# ═══════════════════════════════════════════════════════════════════
#  🔧 مرحله ۴ — استقرار و راه‌اندازی سرویس‌ها
# ═══════════════════════════════════════════════════════════════════


def _get_compose_cmd(ssh: paramiko.SSHClient) -> str:
    ok_flag, _ = run(ssh, "docker compose version", silent=True)
    return "docker compose" if ok_flag else "docker-compose"


def step_deploy(ssh: paramiko.SSHClient) -> bool:
    section("🔧  مرحله ۴ — راه‌اندازی سرویس‌ها با Docker Compose")

    compose = _get_compose_cmd(ssh)
    info(f"دستور Compose: {compose}")

    # دستوراتی که روی سرور اجرا می‌شوند
    commands = [
        # استخراج آرشیو
        f"cd {REMOTE_DIR} && tar -xzf code.tar.gz --overwrite && rm -f code.tar.gz",
        # جایگزینی placeholder های IP در کانفیگ Squid
        f"cd {REMOTE_DIR} && sed -i 's/IP_ADDRESS_1/{PRIMARY_IP}/g'   infra/squid/squid_1.conf",
        f"cd {REMOTE_DIR} && sed -i 's/IP_ADDRESS_2/{SECONDARY_IP}/g' infra/squid/squid_2.conf",
        f"cd {REMOTE_DIR} && sed -i 's/IP_ADDRESS_3/{SECONDARY_IP}/g' infra/squid/squid_3.conf",
        # تصحیح Prometheus — از backend:8000 به جای host.docker.internal استفاده می‌کنیم
        f"cd {REMOTE_DIR} && sed -i "
        f"'s/host.docker.internal:8000/backend:8000/g' "
        f"infra/prometheus/prometheus.yml",
        # نصب پکیج‌های Node و بیلد فرانت‌اند روی سرور (npm از طریق apt نصب شده)
        f"cd {REMOTE_DIR}/apps/web && npm install --prefer-offline 2>&1 | tail -5 || npm install 2>&1 | tail -5",
        f"cd {REMOTE_DIR}/apps/web && NODE_ENV=production NEXT_PUBLIC_API_URL=/api npm run build 2>&1 | tail -20",
        # Pull ایمیج‌های بدون build (سریع‌تر از wait کردن در build)
        f"cd {REMOTE_DIR} && {compose} pull --quiet postgres redis nginx prometheus || true",
        # Build و راه‌اندازی همه سرویس‌ها (با --profile docker-backend)
        f"cd {REMOTE_DIR} && {compose} --profile docker-backend " f"up -d --build --remove-orphans " f"--timeout 300",
        # اجرایی کردن اسکریپت بکاپ
        f"chmod +x {REMOTE_DIR}/scripts/db_backup.sh",
        # تنظیم cron بکاپ روزانه ساعت ۳ صبح
        f"(crontab -l 2>/dev/null | grep -Fv '{REMOTE_DIR}/scripts/db_backup.sh' ; "
        f"echo '0 3 * * * {REMOTE_DIR}/scripts/db_backup.sh >> "
        f"{REMOTE_DIR}/output/backups/backup.log 2>&1') | crontab -",
    ]

    return run_script(ssh, "راه‌اندازی سرویس‌ها", commands)


# ═══════════════════════════════════════════════════════════════════
#  🗄️ مرحله ۵ — مایگریشن دیتابیس (Alembic)
# ═══════════════════════════════════════════════════════════════════


def step_migrate(ssh: paramiko.SSHClient) -> bool:
    section("🗄️   مرحله ۵ — مایگریشن دیتابیس (Alembic)")

    compose = _get_compose_cmd(ssh)

    # صبر برای آماده شدن PostgreSQL
    info("صبر برای آماده شدن PostgreSQL...")
    for i in range(40):
        ok_flag, _ = run(
            ssh,
            f"cd {REMOTE_DIR} && {compose} exec -T postgres " f"pg_isready -U postgres -d {DB_NAME} 2>/dev/null",
            silent=True,
            check=False,
        )
        if ok_flag:
            ok("PostgreSQL آماده است")
            break
        sys.stdout.write(f"\r    انتظار... {i+1}/40")
        sys.stdout.flush()
        time.sleep(4)
    else:
        warn("PostgreSQL در زمان مناسب آماده نشد — مایگریشن رد می‌شود")
        return True  # fatal نیست

    print()
    ok_flag, _ = run(
        ssh,
        f"cd {REMOTE_DIR} && {compose} exec -T backend " f"alembic upgrade head",
        timeout=120,
    )

    if not ok_flag:
        warn("مایگریشن ناموفق بود — ممکن است قبلاً اجرا شده باشد")
        return True  # ادامه می‌دهیم

    ok("مایگریشن‌های دیتابیس اعمال شدند")
    return True


# ═══════════════════════════════════════════════════════════════════
#  🔍 وضعیت و لاگ‌ها
# ═══════════════════════════════════════════════════════════════════


def cmd_status(ssh: paramiko.SSHClient) -> None:
    section("📊  وضعیت سرویس‌ها")
    compose = _get_compose_cmd(ssh)
    run(ssh, f"cd {REMOTE_DIR} && {compose} ps", check=False)

    section("📈  مصرف منابع")
    run(
        ssh,
        "docker stats --no-stream --format " "'table {{.Name}}\t{{.CPUPerc}}\t{{.MemUsage}}\t{{.MemPerc}}'",
        check=False,
    )

    section("🌐  وضعیت شبکه")
    run(ssh, f"ip addr show eth0 | grep 'inet ' ; ip addr show eth1 | grep 'inet '", check=False)
    run(ssh, "ip route show table 100 2>/dev/null || true", check=False)
    run(ssh, "ip route show table 101 2>/dev/null || true", check=False)


def cmd_logs(ssh: paramiko.SSHClient, service: Optional[str] = None) -> None:
    compose = _get_compose_cmd(ssh)
    svc = service or ""
    section(f"📋  لاگ‌ها: {svc or 'همه'}")
    run(ssh, f"cd {REMOTE_DIR} && {compose} logs --tail=100 --no-color {svc}", check=False, timeout=60)


def cmd_restart(ssh: paramiko.SSHClient) -> None:
    section("🔄  ری‌استارت سرویس‌ها")
    compose = _get_compose_cmd(ssh)
    run(ssh, f"cd {REMOTE_DIR} && {compose} --profile docker-backend restart", check=False)
    ok("همه سرویس‌ها ری‌استارت شدند")


# ═══════════════════════════════════════════════════════════════════
#  🩺 بررسی نهایی سلامت
# ═══════════════════════════════════════════════════════════════════


def final_health_check(ssh: paramiko.SSHClient) -> None:
    section("🩺  بررسی سلامت نهایی")

    compose = _get_compose_cmd(ssh)

    # وضعیت کانتینرها
    info("کانتینرهای در حال اجرا:")
    run(ssh, "docker ps --format 'table {{.Names}}\t{{.Status}}\t{{.Ports}}'", check=False)

    # تست HTTP
    info("تست دسترسی HTTP...")
    time.sleep(5)  # کمی صبر برای راه‌اندازی کامل
    run(
        ssh,
        f"curl -s -o /dev/null -w 'HTTP Status: %{{http_code}}\\n' " f"http://localhost/api/healthz || true",
        check=False,
        timeout=15,
    )
    run(
        ssh,
        f"curl -s -o /dev/null -w 'Frontend Status: %{{http_code}}\\n' " f"http://localhost/ || true",
        check=False,
        timeout=15,
    )

    # نمایش کانتینرهای ناموفق
    run(
        ssh,
        "docker ps --filter 'status=exited' " "--format 'table {{.Names}}\t{{.Status}}' 2>/dev/null || true",
        check=False,
    )


# ═══════════════════════════════════════════════════════════════════
#  🚀 نقطه ورود اصلی
# ═══════════════════════════════════════════════════════════════════


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="BarPro ArvanCloud Deployment Script",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
مثال‌ها:
  اولین استقرار کامل:
    python deploy_single_vm.py

  به‌روزرسانی سریع کد (بدون تنظیم شبکه/داکر):
    python deploy_single_vm.py --app-only

  نمایش وضعیت سرویس‌ها:
    python deploy_single_vm.py --status

  نمایش لاگ backend:
    python deploy_single_vm.py --logs backend
        """,
    )

    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--app-only", action="store_true", help="فقط آپلود کد و restart کانتینرها (سریع‌ترین حالت)")
    mode.add_argument("--restart-only", action="store_true", help="فقط ری‌استارت کانتینرها")
    mode.add_argument("--status", action="store_true", help="نمایش وضعیت سرویس‌ها و مصرف منابع")
    mode.add_argument("--migrate-only", action="store_true", help="فقط اجرای مایگریشن Alembic")
    mode.add_argument(
        "--logs", metavar="SERVICE", nargs="?", const="", help="نمایش لاگ (اختیاری: نام سرویس مثلاً backend)"
    )

    parser.add_argument("--skip-network", action="store_true", help="رد کردن تنظیم Netplan (اگر قبلاً انجام شده)")
    parser.add_argument("--skip-docker-setup", action="store_true", help="رد کردن نصب/تنظیم Docker")
    parser.add_argument("--skip-migrate", action="store_true", help="رد کردن مایگریشن Alembic")

    return parser.parse_args()


def main() -> None:
    banner()
    args = parse_args()

    # ── اتصال SSH ──────────────────────────────────────────────────
    ssh = ssh_connect()

    # Fix hostname (suppress sudo warnings)
    run(
        ssh,
        r"sudo sh -c 'HN=$(hostname); grep -q $HN /etc/hosts || " r"echo \"127.0.1.1 $HN\" >> /etc/hosts'",
        check=False,
        silent=True,
    )

    try:
        # ── حالت‌های اجرایی ──────────────────────────────────────

        if args.status:
            cmd_status(ssh)
            return

        if args.logs is not None:
            cmd_logs(ssh, args.logs if args.logs else None)
            return

        if args.restart_only:
            cmd_restart(ssh)
            final_health_check(ssh)
            return

        if args.migrate_only:
            step_migrate(ssh)
            return

        # ── حالت app-only: فقط آپلود و restart ──────────────────
        if args.app_only:
            if not step_upload(ssh):
                sys.exit(1)
            if not step_deploy(ssh):
                sys.exit(1)
            final_health_check(ssh)

        else:
            # ── استقرار کامل ─────────────────────────────────────

            # مرحله ۱: شبکه
            if not args.skip_network:
                if not step_network(ssh):
                    warn("تنظیم شبکه ناموفق بود — ادامه می‌دهیم (ممکن است قبلاً انجام شده)")

            # مرحله ۲: Docker
            if not args.skip_docker_setup:
                if not step_docker(ssh):
                    sys.exit(1)

            # مرحله ۳: آپلود
            if not step_upload(ssh):
                sys.exit(1)

            # مرحله ۴: استقرار
            if not step_deploy(ssh):
                sys.exit(1)

            # مرحله ۵: مایگریشن
            if not args.skip_migrate:
                step_migrate(ssh)

            # بررسی نهایی
            final_health_check(ssh)

    except KeyboardInterrupt:
        print(f"\n\n{C.YELLOW}⚠️  توسط کاربر متوقف شد.{C.RESET}\n")
        sys.exit(1)
    finally:
        ssh.close()

    # ── خروجی موفق ────────────────────────────────────────────────
    print(
        f"""
{C.BOLD}{C.GREEN}╔══════════════════════════════════════════════════════════════╗
║                   🎉  استقرار موفق  🎉                       ║
╠══════════════════════════════════════════════════════════════╣
║  Frontend : http://{PRIMARY_IP:<42}║
║  API Docs : http://{PRIMARY_IP}/api/docs{" "*25}║
║  Metrics  : http://{PRIMARY_IP}:9090{" "*27}║
╚══════════════════════════════════════════════════════════════╝{C.RESET}
"""
    )


if __name__ == "__main__":
    main()

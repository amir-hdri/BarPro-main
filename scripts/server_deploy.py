#!/usr/bin/env python3
"""
╔══════════════════════════════════════════════════════════════════════╗
║         BarPro — اسکریپت استقرار مرحله‌ای روی سرور (Step-by-Step)   ║
╠══════════════════════════════════════════════════════════════════════╣
║  امکان اجرای انتخابی هر مرحله برای جلوگیری از آپلود و بیلد تکراری  ║
║  Server: configured via CENTRAL_IP env var or prompt               ║
╚══════════════════════════════════════════════════════════════════════╝
"""

from __future__ import annotations

import os
import sys
import time
import tarfile
import tempfile
import argparse
from pathlib import Path
import paramiko
from scp import SCPClient

# ═══════════════════════════════════════════════════════════════════
DEFAULT_IP = os.environ.get("CENTRAL_IP", "<YOUR_CENTRAL_SERVER_IP>")
SSH_USER = os.environ.get("DEPLOY_USER", "ubuntu")
SSH_KNOWN_HOSTS = os.environ.get("SSH_KNOWN_HOSTS", os.path.expanduser("~/.ssh/known_hosts"))
REMOTE_DIR = "/opt/barpro"
DB_NAME = "utcms_rpa"

# فایل‌ها و پوشه‌های مستثنی شده برای آپلود سبک (حذف فایل‌های سنگین مدل و پکیج‌ها)
EXCLUDE_DIRS = {
    ".git",
    ".venv",
    "venv",
    "node_modules",
    "__pycache__",
    ".next",
    ".auth",
    "output",
    "build",
    "dist",
    "evidence",
    ".github",
    "examples",
    "docs",
    ".mypy_cache",
    ".pytest_cache",
    ".ruff_cache",
    ".temp_playwright",
    ".agents",
    "playwright-browsers",
    "playwright-zips",
}
EXCLUDE_EXTS = {".pyc", ".log", ".pid", ".tar.gz", ".zip", ".save", ".keras", ".pth"}
EXCLUDE_FILES = {".env", "backend.log", "celerybeat-schedule.db", "rpa_inspector.log"}
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


def ok(m):
    print(f"  {C.GREEN}✓{C.RESET}  {m}")


def err(m):
    print(f"  {C.RED}✗{C.RESET}  {C.RED}{m}{C.RESET}")


def warn(m):
    print(f"  {C.YELLOW}⚠{C.RESET}  {C.YELLOW}{m}{C.RESET}")


def info(m):
    print(f"  {C.CYAN}→{C.RESET}  {m}")


def hdr(t):
    print(f"\n{C.BOLD}{C.BLUE}{'─'*62}{C.RESET}")
    print(f"{C.BOLD}{C.BLUE}  {t}{C.RESET}")
    print(f"{C.BOLD}{C.BLUE}{'─'*62}{C.RESET}")


def ssh_connect(ip: str, user: str, password: str) -> paramiko.SSHClient:
    hdr("🔗  اتصال SSH به سرور")
    info(f"اتصال به {user}@{ip} ...")
    if not os.path.isfile(SSH_KNOWN_HOSTS) or not os.access(SSH_KNOWN_HOSTS, os.R_OK):
        err(f"SSH known_hosts file is missing or unreadable: {SSH_KNOWN_HOSTS}")
        sys.exit(1)
    ssh = paramiko.SSHClient()
    ssh.load_system_host_keys()
    ssh.load_host_keys(SSH_KNOWN_HOSTS)
    ssh.set_missing_host_key_policy(paramiko.RejectPolicy())
    for attempt in range(5):
        try:
            ssh.connect(
                ip,
                username=user,
                password=password,
                timeout=30,
                banner_timeout=120,
                auth_timeout=30,
                allow_agent=False,
                look_for_keys=False,
            )
            ok("اتصال برقرار شد")
            return ssh
        except Exception as e:
            warn(f"تلاش {attempt+1}/5 ناموفق: {e}")
            time.sleep(3)
    err("اتصال SSH برقرار نشد")
    sys.exit(1)


def run_cmd(
    ssh: paramiko.SSHClient, cmd: str, title: str = "", timeout: int = 3600, check: bool = True
) -> tuple[bool, str]:
    if title:
        info(title)
    print(f"  {C.GRAY}$ {cmd[:120]}{'...' if len(cmd)>120 else ''}{C.RESET}")
    _, stdout, stderr = ssh.exec_command(cmd, get_pty=True, timeout=timeout)
    out_lines = []
    try:
        for line in iter(stdout.readline, ""):
            line = line.rstrip("\n")
            out_lines.append(line)
            print(f"    {line}")
    except Exception:
        pass
    rc = stdout.channel.recv_exit_status()
    success = rc == 0
    if check and not success:
        err(f"دستور با exit code {rc} شکست خورد")
    return success, "\n".join(out_lines)


def build_local_archive() -> str:
    info("ساخت آرشیو کدهای محلی (سبک و فشرده)...")
    root = Path(__file__).resolve().parent.parent
    fd, path = tempfile.mkstemp(suffix=".tar.gz", prefix="barpro_update_")
    os.close(fd)

    with tarfile.open(path, "w:gz") as tar:
        for r, dirs, files in os.walk(root):
            # نادیده گرفتن پوشه‌های مستثنی شده
            dirs[:] = [d for d in dirs if d not in EXCLUDE_DIRS]
            for f in files:
                if f.startswith("._") or f in EXCLUDE_FILES:
                    continue
                if any(f.endswith(ext) for ext in EXCLUDE_EXTS):
                    continue
                full = os.path.join(r, f)
                rel = os.path.relpath(full, root)
                tar.add(full, arcname=rel)

    size = Path(path).stat().st_size / 1024 / 1024
    ok(f"آرشیو ساخته شد: {size:.2f} MB (حجم بهینه)")
    return path


def main():
    parser = argparse.ArgumentParser(description="BarPro Step-by-Step Deployment Tool")
    parser.add_argument(
        "--steps",
        default="1,3,4,5",
        help="مراحل اجرای استقرار (کاما جدا شده). مثال: 1,3,4,5\n"
        "1: آپلود کدهای جدید\n"
        "2: نصب پکیج‌ها و بیلد فرانت‌اند (زمان‌بر)\n"
        "3: ساخت ایمیج‌ها و اجرای داکر کانتینرها\n"
        "4: اجرای مایگریشن‌های دیتابیس\n"
        "5: تست سلامت و وضعیت نهایی",
    )
    parser.add_argument("--ip", default=DEFAULT_IP, help="IP آدرس سرور")
    parser.add_argument("--user", default=SSH_USER, help="نام کاربری SSH")
    parser.add_argument(
        "--password", help="رمز عبور SSH (در صورت عدم ارائه، از متغیر محیطی SSH_PASSWORD خوانده می‌شود)"
    )

    args = parser.parse_args()

    # تعیین رمز عبور
    password = args.password
    if not password:
        password = os.environ.get("SSH_PASSWORD")
    if not password:
        err("خطا: رمز عبور SSH مشخص نشده است. لطفا از --password یا متغیر محیطی SSH_PASSWORD استفاده کنید.")
        sys.exit(1)

    # پارس کردن مراحل
    step_list = []
    for s in args.steps.split(","):
        s = s.strip()
        if s.isdigit():
            step_list.append(int(s))
        elif s == "upload":
            step_list.append(1)
        elif s == "build-ui":
            step_list.append(2)
        elif s == "docker":
            step_list.append(3)
        elif s == "migrate":
            step_list.append(4)
        elif s == "health":
            step_list.append(5)

    step_list = sorted(list(set(step_list)))

    print(f"""
{C.BOLD}{C.BLUE}╔══════════════════════════════════════════════════════════════╗
║      BarPro — ابزار مدیریت استقرار سرور                      ║
╠══════════════════════════════════════════════════════════════╣
║  سرور  : {args.ip:<50}║
║  مراحل : {str(step_list):<50}║
╚══════════════════════════════════════════════════════════════╝{C.RESET}
""")

    ssh = ssh_connect(args.ip, args.user, password)

    try:
        # ──────────────────────────────────────────────────────────────
        # مرحله ۱: آپلود کدهای جدید
        # ──────────────────────────────────────────────────────────────
        if 1 in step_list:
            hdr("🟢  مرحله ۱ — آپلود و استخراج کدهای جدید")
            local_archive = build_local_archive()

            info("در حال آپلود آرشیو کدهای جدید...")
            transport = ssh.get_transport()
            transport.default_window_size = 4 * 1024 * 1024

            def progress_bar(filename, size_sent, size_total):
                percent = int(size_sent / size_total * 100) if size_total > 0 else 0
                sys.stdout.write(f"\r  آپلود: {percent}% [{size_sent/1024/1024:.2f}/{size_total/1024/1024:.2f} MB]")
                sys.stdout.flush()

            with SCPClient(transport, progress=progress_bar) as scp:
                scp.put(local_archive, f"{REMOTE_DIR}/update.tar.gz")
            print()
            os.unlink(local_archive)
            ok("آپلود کدهای جدید به سرور با موفقیت انجام شد")

            run_cmd(
                ssh,
                f"cd {REMOTE_DIR} && find . -name '._*' -delete && tar -xzf update.tar.gz --overwrite && rm -f update.tar.gz",
                "حذف فایل‌های فراداده مک و استخراج کدهای جدید روی سرور",
            )

            # اطمینان از دسترسی‌های اسکریپت‌ها
            run_cmd(
                ssh, f"chmod +x {REMOTE_DIR}/manage.sh && chmod +x {REMOTE_DIR}/scripts/*.sh", "تنظیم دسترسی اسکریپت‌ها"
            )
            ok("مرحله ۱ با موفقیت پایان یافت.")

        # ──────────────────────────────────────────────────────────────
        # مرحله ۲: نصب پکیج‌ها و بیلد فرانت‌اند
        # ──────────────────────────────────────────────────────────────
        if 2 in step_list:
            hdr("🌐  مرحله ۲ — نصب پکیج‌ها و بیلد فرانت‌اند Next.js روی سرور")

            # بررسی وجود npm
            ok_npm, _ = run_cmd(ssh, "which npm", check=False)
            if not ok_npm:
                info("نصب npm روی سرور...")
                run_cmd(
                    ssh,
                    "sudo apt-get update -qq && sudo DEBIAN_FRONTEND=noninteractive apt-get install -y npm 2>&1 | tail -5",
                )

            # نصب پکیج‌های فرانت‌اند
            info("نصب پکیج‌های npm فرانت‌اند...")
            ok_install, _ = run_cmd(
                ssh,
                f"cd {REMOTE_DIR}/apps/web && npm install --legacy-peer-deps 2>&1 | tail -10",
                timeout=600,
                check=False,
            )
            if not ok_install:
                err("خطا در نصب پکیج‌های npm فرانت‌اند")
                sys.exit(1)

            # بیلد Next.js
            run_cmd(
                ssh,
                f"cd {REMOTE_DIR}/apps/web && " f"NODE_ENV=production NEXT_PUBLIC_API_URL=/api " f"npm run build 2>&1",
                "بیلد Next.js فرانت‌اند (این کار ممکن است حافظه سرور را تحت فشار قرار دهد)",
                timeout=900,
            )
            ok("مرحله ۲ با موفقیت پایان یافت.")

        # ──────────────────────────────────────────────────────────────
        # مرحله ۳: داکر کمپوز
        # ──────────────────────────────────────────────────────────────
        if 3 in step_list:
            hdr("🐳  مرحله ۳ — راه‌اندازی و بیلد داکر کانتینرها")

            # رندر کانفیگ‌های Squid: squid_1 → DEFAULT_IP، squid_2/3 → secondary IP
            # (یک فراخوانی؛ هیچ sed -i روی قالب‌های گیت — X4).
            run_cmd(
                ssh,
                f"cd {REMOTE_DIR} && bash scripts/render_squid_configs.sh {DEFAULT_IP} "
                f"{os.environ.get('SECONDARY_IP', '')}",
                check=False,
            )

            # Compose V2 is required because the repository uses `include:`.
            ok_dc, _ = run_cmd(ssh, "docker compose version", check=False)
            if not ok_dc:
                err("Docker Compose V2 is required; refusing the unsupported V1 fallback.")
                sys.exit(1)
            compose = "docker compose"
            # پاک‌سازی کانتینرهای متداخل هم‌نام
            run_cmd(
                ssh,
                "docker ps --format 'table {{.Names}}\\t{{.Status}}'",
                "بررسی کانتینرهای فعلی (بدون حذف خودکار)",
            )
            # This legacy step-by-step deploy renders a secondary egress IP, so
            # it is the single-VM Model A path. Both local Squid and worker
            # profiles must be explicit; production Model B uses the fleet
            # deployment scripts instead.
            success, _ = run_cmd(
                ssh,
                f"cd {REMOTE_DIR} && {compose} --profile docker-backend --profile model-a --profile scale-out "
                f"up -d --build --remove-orphans --timeout 300 2>&1",
                "اجرای docker compose build & up",
                timeout=2400,
                check=False,
            )
            if not success:
                err("راه‌اندازی داکر با خطا مواجه شد. لطفا لاگ‌ها را بررسی کنید.")
                sys.exit(1)
            ok("کانتینرهای داکر با موفقیت بالا آمدند.")

        # ──────────────────────────────────────────────────────────────
        # مرحله ۴: مایگریشن دیتابیس
        # ──────────────────────────────────────────────────────────────
        if 4 in step_list:
            hdr("🗄️  مرحله ۴ — مایگریشن دیتابیس (Alembic)")

            ok_dc, _ = run_cmd(ssh, "docker compose version", check=False)
            if not ok_dc:
                err("Docker Compose V2 is required; refusing the unsupported V1 fallback.")
                sys.exit(1)
            compose = "docker compose"

            info("صبر برای آماده شدن PostgreSQL...")
            pg_ready = False
            for i in range(15):
                ok_pg, _ = run_cmd(
                    ssh,
                    f"cd {REMOTE_DIR} && {compose} exec -T postgres pg_isready -U postgres -d {DB_NAME} 2>/dev/null",
                    check=False,
                )
                if ok_pg:
                    ok("PostgreSQL آماده اتصال است")
                    pg_ready = True
                    break
                print(f"\r    انتظار برای دیتابیس... {i+1}/15", end="", flush=True)
                time.sleep(4)
            print()

            if pg_ready:
                run_cmd(
                    ssh,
                    f"cd {REMOTE_DIR} && {compose} exec -T backend python -c "
                    "'import asyncio; from app.core.database import run_migrations; asyncio.run(run_migrations())'",
                    "اجرای migration تحت PostgreSQL advisory lock",
                )
                ok("مایگریشن دیتابیس با موفقیت اعمال شد.")
            else:
                err("مایگریشن اعمال نشد چون دیتابیس آماده نبود.")
                sys.exit(1)

        # ──────────────────────────────────────────────────────────────
        # مرحله ۵: تست سلامت و گزارش نهایی
        # ──────────────────────────────────────────────────────────────
        if 5 in step_list:
            hdr("📊  مرحله ۵ — بررسی وضعیت نهایی و تست سلامت")

            ok_dc, _ = run_cmd(ssh, "docker compose version", check=False)
            if not ok_dc:
                err("Docker Compose V2 is required.")
                sys.exit(1)
            compose = "docker compose"

            run_cmd(ssh, f"cd {REMOTE_DIR} && {compose} ps 2>&1", "وضعیت کانتینرها", check=False)

            print()
            run_cmd(
                ssh,
                f"curl -fsS http://localhost/healthz 2>&1",
                "تست بک‌اند",
                check=True,
                timeout=15,
            )
            run_cmd(
                ssh,
                f"curl -fsSI http://localhost/ 2>&1 | head -5",
                "تست فرانت‌اند",
                check=True,
                timeout=15,
            )

            print(f"""
{C.BOLD}{C.GREEN}╔══════════════════════════════════════════════════════════════╗
║              🎉  وضعیت نهایی استقرار                         ║
╠══════════════════════════════════════════════════════════════╣
║  Backend API : http://{args.ip}/api                      ║
║  Frontend    : http://{args.ip}                          ║
║  Prometheus  : http://{args.ip}:9090                     ║
╚══════════════════════════════════════════════════════════════╝{C.RESET}
""")

    finally:
        ssh.close()
        ok("اتصال SSH بسته شد.")


if __name__ == "__main__":
    main()

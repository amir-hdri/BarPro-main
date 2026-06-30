#!/usr/bin/env python3
"""
╔══════════════════════════════════════════════════════════════════════╗
║         BarPro — اسکریپت استقرار کامل روی سرور (Server-Side)      ║
╠══════════════════════════════════════════════════════════════════════╣
║  همه مراحل روی سرور انجام می‌شود — بدون نیاز به بیلد محلی         ║
║  Server: 188.121.123.16                                             ║
╚══════════════════════════════════════════════════════════════════════╝
"""
from __future__ import annotations

import sys
import time
import paramiko

# ═══════════════════════════════════════════════════════════════════
PRIMARY_IP   = "188.121.123.16"
SSH_USER     = "ubuntu"
SSH_PASS     = "PLACEHOLDER_SSH_PASSWORD"
REMOTE_DIR   = "/opt/barpro"
DB_NAME      = "utcms_rpa"
# ═══════════════════════════════════════════════════════════════════

class C:
    RESET  = "\033[0m"; BOLD = "\033[1m"; GREEN = "\033[92m"
    YELLOW = "\033[93m"; RED  = "\033[91m"; CYAN = "\033[96m"
    BLUE   = "\033[94m"; GRAY = "\033[90m"

def ok(m):   print(f"  {C.GREEN}✓{C.RESET}  {m}")
def err(m):  print(f"  {C.RED}✗{C.RESET}  {C.RED}{m}{C.RESET}")
def warn(m): print(f"  {C.YELLOW}⚠{C.RESET}  {C.YELLOW}{m}{C.RESET}")
def info(m): print(f"  {C.CYAN}→{C.RESET}  {m}")
def hdr(t):
    print(f"\n{C.BOLD}{C.BLUE}{'─'*62}{C.RESET}")
    print(f"{C.BOLD}{C.BLUE}  {t}{C.RESET}")
    print(f"{C.BOLD}{C.BLUE}{'─'*62}{C.RESET}")

def ssh_connect() -> paramiko.SSHClient:
    hdr("🔗  اتصال SSH به سرور")
    info(f"اتصال به {SSH_USER}@{PRIMARY_IP} ...")
    ssh = paramiko.SSHClient()
    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    for attempt in range(5):
        try:
            ssh.connect(
                PRIMARY_IP, username=SSH_USER, password=SSH_PASS,
                timeout=30, banner_timeout=120, auth_timeout=30,
                allow_agent=False, look_for_keys=False,
            )
            ok("اتصال برقرار شد")
            return ssh
        except Exception as e:
            warn(f"تلاش {attempt+1}/5 ناموفق: {e}")
            time.sleep(3)
    err("اتصال SSH برقرار نشد")
    sys.exit(1)

def run(ssh: paramiko.SSHClient, cmd: str, title: str = "",
        timeout: int = 3600, check: bool = True) -> tuple[bool, str]:
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
    success = (rc == 0)
    if check and not success:
        err(f"دستور با exit code {rc} شکست خورد")
    return success, "\n".join(out_lines)

def main():
    print(f"""
{C.BOLD}{C.BLUE}╔══════════════════════════════════════════════════════════════╗
║      BarPro — استقرار کامل روی سرور  🚀                     ║
╠══════════════════════════════════════════════════════════════╣
║  سرور  : {PRIMARY_IP:<50}║
║  دایرکتوری: {REMOTE_DIR:<48}║
╚══════════════════════════════════════════════════════════════╝{C.RESET}
""")
    ssh = ssh_connect()

    # ──────────────────────────────────────────────────────────────
    hdr("📋  بررسی وضعیت اولیه سرور")
    # ──────────────────────────────────────────────────────────────
    run(ssh, "node --version 2>/dev/null || echo 'Node not found'", "نسخه Node", check=False)
    run(ssh, "npm --version 2>/dev/null || echo 'npm not found'", "نسخه npm", check=False)
    run(ssh, "docker --version", "نسخه Docker", check=False)
    run(ssh, f"ls {REMOTE_DIR}/apps/web/ 2>/dev/null || echo 'پوشه پیدا نشد'", "پوشه وب", check=False)

    # ──────────────────────────────────────────────────────────────
    hdr("🟢  قدم ۱ — اطمینان از نصب npm")
    # ──────────────────────────────────────────────────────────────
    ok_npm, _ = run(ssh, "which npm", check=False)
    if not ok_npm:
        warn("npm نصب نیست، در حال نصب از Ubuntu apt...")
        run(ssh, "sudo apt-get update -qq && sudo DEBIAN_FRONTEND=noninteractive apt-get install -y npm 2>&1 | tail -5")
        ok("npm نصب شد")
    else:
        ok("npm از قبل نصب است")

    # ──────────────────────────────────────────────────────────────
    hdr("📦  قدم ۲ — نصب پکیج‌های Node.js")
    # ──────────────────────────────────────────────────────────────
    ok_install, _ = run(
        ssh,
        f"cd {REMOTE_DIR}/apps/web && npm install 2>&1 | tail -10",
        "نصب پکیج‌های npm",
        timeout=600,
        check=False
    )
    if not ok_install:
        warn("npm install با خطا مواجه شد — سعی با --legacy-peer-deps")
        run(
            ssh,
            f"cd {REMOTE_DIR}/apps/web && npm install --legacy-peer-deps 2>&1 | tail -10",
            timeout=600
        )

    # ──────────────────────────────────────────────────────────────
    hdr("🔨  قدم ۳ — بیلد فرانت‌اند Next.js")
    # ──────────────────────────────────────────────────────────────
    run(
        ssh,
        f"cd {REMOTE_DIR}/apps/web && "
        f"NODE_ENV=production NEXT_PUBLIC_API_URL=/api "
        f"npm run build 2>&1",
        "بیلد Next.js",
        timeout=900
    )

    # بررسی موفقیت بیلد
    ok_build, _ = run(ssh, f"test -d {REMOTE_DIR}/apps/web/.next/standalone && echo OK", check=False)
    if not ok_build:
        err("پوشه .next/standalone ایجاد نشد!")
        warn("بررسی کنید که 'output: standalone' در next.config.mjs باشد")
        sys.exit(1)
    ok("بیلد Next.js موفق بود")

    # ──────────────────────────────────────────────────────────────
    hdr("🐳  قدم ۴ — ساخت و راه‌اندازی Docker Compose")
    # ──────────────────────────────────────────────────────────────
    # تصحیح کانفیگ‌ها
    run(ssh, f"cd {REMOTE_DIR} && sed -i 's/IP_ADDRESS_1/188.121.123.16/g' infra/squid/squid_1.conf 2>/dev/null || true", check=False)
    run(ssh, f"cd {REMOTE_DIR} && sed -i 's/IP_ADDRESS_2/95.38.233.90/g' infra/squid/squid_2.conf 2>/dev/null || true", check=False)
    run(ssh, f"cd {REMOTE_DIR} && sed -i 's/IP_ADDRESS_3/95.38.233.90/g' infra/squid/squid_3.conf 2>/dev/null || true", check=False)
    run(ssh, f"cd {REMOTE_DIR} && sed -i 's/host.docker.internal:8000/backend:8000/g' infra/prometheus/prometheus.yml 2>/dev/null || true", check=False)

    # تشخیص docker compose یا docker-compose
    ok_dc, _ = run(ssh, "docker compose version", check=False)
    compose = "docker compose" if ok_dc else "docker-compose"
    info(f"دستور Compose: {compose}")

    # Pull ایمیج‌های خارجی از آروان
    run(ssh, f"cd {REMOTE_DIR} && {compose} pull --quiet postgres redis nginx prometheus 2>&1 | tail -5 || true", check=False, timeout=300)

    # Build و up
    run(
        ssh,
        f"cd {REMOTE_DIR} && {compose} --profile docker-backend "
        f"up -d --build --remove-orphans --timeout 300 2>&1",
        "راه‌اندازی Docker Compose",
        timeout=1800,
    )

    # ──────────────────────────────────────────────────────────────
    hdr("🗄️  قدم ۵ — مایگریشن دیتابیس")
    # ──────────────────────────────────────────────────────────────
    info("صبر برای آماده شدن PostgreSQL...")
    for i in range(30):
        ok_pg, _ = run(
            ssh,
            f"cd {REMOTE_DIR} && {compose} exec -T postgres pg_isready -U postgres -d {DB_NAME} 2>/dev/null",
            check=False
        )
        if ok_pg:
            ok("PostgreSQL آماده است")
            break
        print(f"\r    انتظار... {i+1}/30", end="", flush=True)
        time.sleep(4)
    else:
        warn("PostgreSQL آماده نشد")

    run(
        ssh,
        f"cd {REMOTE_DIR} && {compose} exec -T backend alembic upgrade head 2>&1",
        "مایگریشن Alembic",
        timeout=120,
        check=False
    )

    # ──────────────────────────────────────────────────────────────
    hdr("📊  قدم ۶ — بررسی وضعیت نهایی")
    # ──────────────────────────────────────────────────────────────
    run(ssh, f"cd {REMOTE_DIR} && {compose} ps 2>&1", check=False)

    print()
    run(ssh, f"curl -sf http://localhost/api/healthz 2>&1 || curl -sf http://localhost:8000/healthz 2>&1 || echo 'Healthcheck در حال آماده‌سازی'", check=False, timeout=15)
    run(ssh, f"curl -sI http://localhost/ 2>&1 | head -5 || echo 'Frontend در حال آماده‌سازی'", check=False, timeout=15)

    print(f"""
{C.BOLD}{C.GREEN}╔══════════════════════════════════════════════════════════════╗
║              ✅  استقرار تکمیل شد                            ║
╠══════════════════════════════════════════════════════════════╣
║  Backend API : http://{PRIMARY_IP}/api                      ║
║  Frontend    : http://{PRIMARY_IP}                          ║
║  Prometheus  : http://{PRIMARY_IP}:9090                     ║
╚══════════════════════════════════════════════════════════════╝{C.RESET}
""")
    ssh.close()

if __name__ == "__main__":
    main()

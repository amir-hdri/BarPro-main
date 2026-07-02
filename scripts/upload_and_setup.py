#!/usr/bin/env python3
"""
آپلود کد جدید + نصب manage.sh روی سرور
"""
import os, sys, tarfile, tempfile, time
from pathlib import Path
import paramiko
from scp import SCPClient

HOST = "188.121.123.16"
USER = "ubuntu"
PASS = os.environ.get("SSH_PASSWORD", "")
REMOTE = "/opt/barpro"

EXCLUDE = {".git",".venv","venv","node_modules","__pycache__",".next",
           ".auth","output","build","dist","evidence",".github","examples","docs",
           ".mypy_cache",".pytest_cache",".ruff_cache",".temp_playwright",".agents"}

GR="\033[92m"; RD="\033[91m"; CY="\033[96m"; RS="\033[0m"; BD="\033[1m"
ok  = lambda m: print(f"  {GR}✓{RS}  {m}")
err = lambda m: print(f"  {RD}✗{RS}  {RD}{m}{RS}")
inf = lambda m: print(f"  {CY}→{RS}  {m}")

def connect():
    inf(f"اتصال به {HOST}...")
    ssh = paramiko.SSHClient()
    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    for i in range(5):
        try:
            ssh.connect(HOST, username=USER, password=PASS,
                        timeout=30, banner_timeout=60,
                        allow_agent=False, look_for_keys=False)
            ok("اتصال برقرار شد")
            return ssh
        except Exception as e:
            print(f"\r  تلاش {i+1}/5: {e}", end=""); time.sleep(3)
    sys.exit(1)

def run(ssh, cmd, timeout=300):
    _, out, _ = ssh.exec_command(cmd, get_pty=True, timeout=timeout)
    result = ""
    for line in iter(out.readline, ""):
        line = line.rstrip()
        print(f"    {line}")
        result += line + "\n"
    rc = out.channel.recv_exit_status()
    return rc == 0, result

def build_archive():
    inf("ساخت آرشیو...")
    root = Path(__file__).resolve().parent.parent
    fd, path = tempfile.mkstemp(suffix=".tar.gz", prefix="barpro_update_")
    os.close(fd)
    with tarfile.open(path, "w:gz") as tar:
        for r, dirs, files in os.walk(root):
            dirs[:] = [d for d in dirs if d not in EXCLUDE]
            for f in files:
                if f in {".env","backend.log","celerybeat-schedule.db"}: continue
                if any(f.endswith(e) for e in {".pyc",".log",".pid",".tar.gz",".zip",".save",".keras",".pth"}): continue
                full = os.path.join(r, f)
                rel  = os.path.relpath(full, root)
                tar.add(full, arcname=rel)
    size = Path(path).stat().st_size / 1024 / 1024
    ok(f"آرشیو: {size:.1f} MB")
    return path

def main():
    print(f"\n{BD}🚀  آپلود و راه‌اندازی BarPro{RS}\n")
    ssh = connect()
    
    # آرشیو
    archive = build_archive()
    
    # آپلود
    inf(f"آپلود به سرور...")
    transport = ssh.get_transport()
    transport.default_window_size = 4 * 1024 * 1024
    with SCPClient(transport, progress=lambda f,s,t: print(f"\r  {int(s/t*100)}%" if t > 0 else "", end="", flush=True)) as scp:
        scp.put(archive, f"{REMOTE}/update.tar.gz")
    print()
    os.unlink(archive)
    ok("آپلود انجام شد")

    # استخراج
    inf("استخراج فایل‌ها...")
    run(ssh, f"cd {REMOTE} && tar -xzf update.tar.gz --overwrite && rm -f update.tar.gz")
    ok("فایل‌ها استخراج شدند")

    # نصب manage.sh
    inf("نصب manage.sh...")
    run(ssh, f"chmod +x {REMOTE}/manage.sh && ln -sf {REMOTE}/manage.sh /usr/local/bin/barpro 2>/dev/null || true")
    ok("manage.sh نصب شد")
    
    # نمایش راهنما
    print(f"\n{BD}📋  دستورات مدیریت سرور:{RS}")
    print(f"  bash {REMOTE}/manage.sh status      — وضعیت")
    print(f"  bash {REMOTE}/manage.sh update-ui   — آپدیت فرانت‌اند")
    print(f"  bash {REMOTE}/manage.sh deploy       — deploy از GitHub")
    print(f"  bash {REMOTE}/manage.sh health       — بررسی سلامت")
    print(f"\n  یا کوتاه‌تر: barpro status  (اگر /usr/local/bin/ در PATH باشد)")
    
    ssh.close()

if __name__ == "__main__":
    main()

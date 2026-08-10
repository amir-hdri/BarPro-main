import os
import signal
import subprocess
import time

import psutil
import requests

# Ensure paths are correct
PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.chdir(PROJECT_DIR)


def clean_all_leftovers():
    print("🧹 Pre-cleanup: Killing any left-over processes...")
    # Find and kill any processes containing project markers
    for proc in psutil.process_iter(["pid", "name", "cmdline"]):
        try:
            cmdline = proc.info.get("cmdline") or []
            cmdline_str = " ".join(cmdline).lower()
            name = proc.info.get("name") or ""

            # Match uvicorn, next, celery, playwright, chromium
            is_match = False
            if "uvicorn" in cmdline_str or "app.main:app" in cmdline_str:
                is_match = True
            elif "celery" in cmdline_str and "app.workers" in cmdline_str:
                is_match = True
            elif "next-server" in cmdline_str or "node" in name.lower() and ".next/standalone" in cmdline_str:
                is_match = True
            elif "next dev" in cmdline_str or "yarn dev" in cmdline_str:
                is_match = True
            elif "playwright" in cmdline_str or "chromium" in name.lower() or "ms-playwright" in cmdline_str:
                is_match = True
            elif "rpa_inspector.py" in cmdline_str:
                is_match = True

            if is_match and proc.pid != os.getpid():
                print(f"  Killing leftover process PID {proc.pid}: {name} ({cmdline_str[:60]})")
                proc.kill()
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            pass
    # Sleep to allow processes to die
    time.sleep(2)


def find_active_processes():
    """Returns a list of processes matching our stack."""
    results = []
    for proc in psutil.process_iter(["pid", "name", "cmdline", "ppid"]):
        try:
            cmdline = proc.info.get("cmdline") or []
            cmdline_str = " ".join(cmdline).lower()
            name = proc.info.get("name") or ""
            ppid = proc.info.get("ppid")

            p_type = None
            if "uvicorn" in cmdline_str or "app.main:app" in cmdline_str:
                p_type = "uvicorn"
            elif "celery" in cmdline_str and "app.workers" in cmdline_str:
                p_type = "celery"
            elif (
                "next-server" in cmdline_str
                or ("node" in name.lower() and ".next/standalone" in cmdline_str)
                or ("node" in name.lower() and "server.js" in cmdline_str)
            ):
                p_type = "node/next"
            elif "next dev" in cmdline_str or "yarn dev" in cmdline_str:
                p_type = "node/next-dev"
            elif (
                "playwright" in cmdline_str
                or "chromium" in name.lower()
                or "ms-playwright" in cmdline_str
                or "chrome-mac" in cmdline_str
            ):
                p_type = "playwright/chromium"
            elif "rpa_inspector.py" in cmdline_str:
                p_type = "rpa_inspector"

            if p_type:
                results.append({"pid": proc.pid, "ppid": ppid, "name": name, "type": p_type, "cmdline": cmdline_str})
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            pass
    return results


def print_active_processes(label="Active project processes"):
    procs = find_active_processes()
    print(f"\n--- {label} (Count: {len(procs)}) ---")
    for p in procs:
        print(f"  PID: {p['pid']}, PPID: {p['ppid']}, Type: {p['type']}, Name: {p['name']}, Cmd: {p['cmdline'][:100]}")
    print("-" * 40)
    return procs


def run_script(path):
    print(f"🎬 Running script: {path}")
    res = subprocess.run([path], capture_output=True, text=True)
    print(f"Stdout:\n{res.stdout}")
    if res.stderr:
        print(f"Stderr:\n{res.stderr}")
    return res


def test_rapid_restarts():
    print("\n==========================================")
    print("🧪 TEST 1: Rapid Restart Stress Test")
    print("==========================================")

    delays = [0.5, 1.0, 2.0, 3.0]
    for i, delay in enumerate(delays):
        print(f"\n🔄 Cycle {i+1}/{len(delays)}: Start system, wait {delay}s, and stop services...")
        clean_all_leftovers()

        # Start via start_services.sh
        subprocess.Popen(["./start_services.sh"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        time.sleep(delay)

        # Stop services
        run_script("./stop_services.sh")

        # Check if anything is left
        leftovers = find_active_processes()
        if leftovers:
            print(f"❌ FAIL: Found {len(leftovers)} dangling processes after rapid restart with delay {delay}s!")
            for p in leftovers:
                print(f"    - Dangling PID: {p['pid']} ({p['type']}): {p['cmdline'][:80]}")
        else:
            print(f"✅ PASS: Clean shutdown after rapid restart with delay {delay}s.")

    clean_all_leftovers()


def test_graceful_cleanup_readyz():
    print("\n==========================================")
    print("🧪 TEST 2: Graceful Cleanup under Active Browser usage")
    print("==========================================")
    clean_all_leftovers()

    # Start using scripts/start_system.sh
    print("Starting system via scripts/start_system.sh...")
    # Clean output files
    for f in ["backend.pid", "frontend.pid", "scheduler_worker.pid", "worker.pid"]:
        path = f"output/{f}"
        if os.path.exists(path):
            os.remove(path)

    # We set environment variables to ensure local execution is correct
    env = os.environ.copy()
    env["HEADLESS"] = "true"

    p = subprocess.Popen(
        ["scripts/start_system.sh"], env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True
    )

    # Wait for backend and frontend ports to be active
    backend_up = False
    frontend_up = False
    for _ in range(60):
        time.sleep(1)
        # Check backend
        try:
            r = requests.get("http://localhost:8000/healthz", timeout=1)
            if r.status_code == 200:
                backend_up = True
        except Exception:
            pass

        # Check frontend
        try:
            r = requests.get("http://localhost:3000", timeout=1)
            if r.status_code in [200, 304]:
                frontend_up = True
        except Exception:
            pass

        if backend_up and frontend_up:
            break

    print(f"System status: Backend up={backend_up}, Frontend up={frontend_up}")

    # Trigger /readyz to initialize browser
    print("Triggering /readyz to spawn Playwright Chromium processes...")
    try:
        r = requests.get("http://localhost:8000/readyz", timeout=15)
        print(f"/readyz response: {r.status_code}, body status: {r.json().get('status')}")
    except Exception as e:
        print(f"Failed to hit /readyz: {e}")

    # List active processes before stop
    print_active_processes("Active processes during normal execution")

    # Now stop the system using scripts/stop_system.sh
    print("Stopping system via scripts/stop_system.sh...")
    run_script("scripts/stop_system.sh")

    # Check for leftovers
    leftovers = find_active_processes()
    if leftovers:
        print(f"❌ FAIL: Found {len(leftovers)} dangling processes after graceful stop!")
        for p in leftovers:
            print(f"    - Dangling PID: {p['pid']} ({p['type']}): {p['cmdline'][:80]}")
    else:
        print("✅ PASS: Clean graceful stop. No dangling processes left.")

    clean_all_leftovers()


def test_unexpected_crash_recovery():
    print("\n==========================================")
    print("🧪 TEST 3: Unexpected Crash / Hard Kill Leak Test")
    print("==========================================")
    clean_all_leftovers()

    # Start using scripts/start_system.sh
    print("Starting system via scripts/start_system.sh...")
    env = os.environ.copy()
    env["HEADLESS"] = "true"

    subprocess.Popen(["scripts/start_system.sh"], env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    # Wait for startup
    backend_up = False
    for _ in range(40):
        time.sleep(1)
        try:
            r = requests.get("http://localhost:8000/healthz", timeout=1)
            if r.status_code == 200:
                backend_up = True
                break
        except Exception:
            pass

    if not backend_up:
        print("❌ System failed to start. Aborting Test 3.")
        return

    # Trigger /readyz to initialize browser
    print("Triggering /readyz to spawn Playwright Chromium processes...")
    try:
        r = requests.get("http://localhost:8000/readyz", timeout=15)
        print(f"/readyz response: {r.json().get('status')}")
    except Exception as e:
        print(f"Failed to hit /readyz: {e}")

    active_procs = print_active_processes("Active processes before crash simulation")

    # We will simulate a hard crash (kill -9) on the primary processes:
    # 1. FastAPI (uvicorn)
    # 2. Next.js (node)
    # 3. Celery worker (celery)

    pids_to_kill = []
    for p in active_procs:
        if p["type"] in ["uvicorn", "node/next", "node/next-dev", "celery"]:
            pids_to_kill.append(p["pid"])

    print(f"Simulating unexpected crash (kill -9) on PIDs: {pids_to_kill}")
    for pid in pids_to_kill:
        try:
            os.kill(pid, signal.SIGKILL)
            print(f"  Killed PID {pid}")
        except ProcessLookupError:
            pass

    # Sleep to let OS process table update
    time.sleep(3)

    # List active processes (we expect Playwright's Chromium/node driver to be orphaned now)
    print_active_processes("Orphaned processes after crash")

    # Now run stop_services.sh and scripts/stop_system.sh to see if they can sweep the orphans
    print("Running stop_services.sh to perform orphaned sweep...")
    run_script("./stop_services.sh")

    # Running scripts/stop_system.sh as well
    print("Running scripts/stop_system.sh to perform system stop...")
    run_script("scripts/stop_system.sh")

    # Check for remaining leftovers
    remaining = find_active_processes()
    if remaining:
        print(f"❌ FAIL: Found {len(remaining)} dangling/orphaned processes after crash cleanup!")
        for p in remaining:
            print(f"    - Dangling PID: {p['pid']} ({p['type']}): {p['cmdline'][:80]}")
    else:
        print("✅ PASS: Cleanup scripts successfully swept all orphaned/dangling processes after crash.")

    clean_all_leftovers()


if __name__ == "__main__":
    print("🚀 Starting Process Management Stress & Failure Verification...")
    test_rapid_restarts()
    test_graceful_cleanup_readyz()
    test_unexpected_crash_recovery()
    print("🏁 Stress test run complete.")

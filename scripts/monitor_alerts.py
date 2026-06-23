#!/usr/bin/env python3
"""
System Monitor Daemon with Telegram Alerting.
Monitors memory utilization and Redis circuit breaker state (blocked IPs).
"""

import os
import sys
import time
import json
import urllib.request
import urllib.parse
import redis

# Add project root to path for configuration loading
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.append(project_root)

# Load configuration values directly from environment or defaults
REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0").strip()
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "").strip()

ALERT_COOLDOWN_SECONDS = 1800  # 30 minutes cooldown for RAM alerts
CHECK_INTERVAL_SECONDS = 15     # Check every 15 seconds

def get_ram_usage_percent() -> float:
    """Reads /proc/meminfo to calculate memory usage on Linux, or falls back."""
    try:
        with open("/proc/meminfo", "r") as f:
            lines = f.readlines()
        mem_info = {}
        for line in lines:
            parts = line.split(":")
            if len(parts) == 2:
                mem_info[parts[0].strip()] = int(parts[1].replace("kB", "").strip())
        
        total = mem_info.get("MemTotal", 1)
        free = mem_info.get("MemFree", 0)
        buffers = mem_info.get("Buffers", 0)
        cached = mem_info.get("Cached", 0)
        
        # Calculate used RAM like the free command
        used = total - free - buffers - cached
        percent = (used / total) * 100.0
        return percent
    except Exception:
        # Fallback for non-Linux or test environments
        try:
            import psutil
            return psutil.virtual_memory().percent
        except ImportError:
            return 50.0  # Dummy value

def send_telegram_alert(message: str):
    """Sends an alert message to the configured Telegram channel."""
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        print(f"[Alert (Skipped - Token/ChatID not set)]: {message}")
        return

    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": message,
        "parse_mode": "HTML"
    }
    
    try:
        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            url, 
            data=data, 
            headers={"Content-Type": "application/json"}
        )
        with urllib.request.urlopen(req, timeout=10) as response:
            res_data = json.loads(response.read().decode())
            if not res_data.get("ok"):
                print(f"Telegram error response: {res_data}")
    except Exception as exc:
        print(f"Failed to send Telegram alert: {exc}")

def main():
    print("Starting BarPro System Monitor Daemon...")
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        print("⚠️ Warning: TELEGRAM_BOT_TOKEN or TELEGRAM_CHAT_ID is not configured in the environment.")
        print("Telegram alerts will be printed to stdout instead.")

    # Initialize state
    last_ram_alert_time = 0.0
    blocked_ips_state = {1: False, 2: False, 3: False}

    try:
        r = redis.Redis.from_url(REDIS_URL, decode_responses=True)
        r.ping()
        print(f"Successfully connected to Redis at {REDIS_URL}")
    except Exception as e:
        print(f"❌ Error: Cannot connect to Redis: {e}")
        sys.exit(1)

    while True:
        try:
            # 1. Check RAM usage
            ram_percent = get_ram_usage_percent()
            current_time = time.time()
            
            if ram_percent > 85.0:
                if (current_time - last_ram_alert_time) > ALERT_COOLDOWN_SECONDS:
                    alert_msg = (
                        f"🚨 <b>BarPro Host Alert</b> 🚨\n\n"
                        f"⚠️ High Memory Usage detected on server!\n"
                        f"📊 <b>RAM Used:</b> {ram_percent:.1f}%\n"
                        f"Please inspect the server processes."
                    )
                    send_telegram_alert(alert_msg)
                    last_ram_alert_time = current_time

            # 2. Check Circuit Breaker Blocked IPs in Redis
            for i in [1, 2, 3]:
                key = f"utcms:circuit_breaker:blocked:{i}"
                is_blocked_now = bool(r.exists(key))
                
                # Check for state transitions
                if is_blocked_now and not blocked_ips_state[i]:
                    ttl = r.ttl(key)
                    alert_msg = (
                        f"🛡️ <b>Circuit Breaker Triggered</b> 🛡️\n\n"
                        f"🚫 <b>IP Index {i}</b> has been BLOCKED!\n"
                        f"⏳ <b>Bypass duration:</b> 30 minutes\n"
                        f"⏱️ <b>Remaining time:</b> {ttl // 60}m {ttl % 60}s\n"
                        f"Traffic is being routed to other healthy IPs."
                    )
                    send_telegram_alert(alert_msg)
                    blocked_ips_state[i] = True
                    
                elif not is_blocked_now and blocked_ips_state[i]:
                    alert_msg = (
                        f"✅ <b>Circuit Breaker Recovered</b> ✅\n\n"
                        f"🔓 <b>IP Index {i}</b> is now UNBLOCKED!\n"
                        f"Traffic is again routed through IP Index {i}."
                    )
                    send_telegram_alert(alert_msg)
                    blocked_ips_state[i] = False

        except Exception as e:
            print(f"Error in monitor loop: {e}")

        time.sleep(CHECK_INTERVAL_SECONDS)

if __name__ == "__main__":
    main()

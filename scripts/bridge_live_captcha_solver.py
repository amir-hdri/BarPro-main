#!/usr/bin/env python3
"""Local bridge to solve live UTCMS captchas from Central Server using NVIDIA NIM.

Uses fast SSH base64 streaming without scp to eliminate hangs.
"""

import base64
import os
import subprocess
import sys
import time
from pathlib import Path

# Add project root
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from scripts.label_with_nvidia_nim import label_single_image

SERVER_HOST = "root@87.107.5.238"
CONTAINER_NAME = "barpro-backend"
NVIDIA_API_KEY = os.getenv("NVIDIA_API_KEY", "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")


def run_ssh(cmd: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["ssh", "-o", "BatchMode=yes", "-o", "ConnectTimeout=8", SERVER_HOST, cmd],
        capture_output=True,
        text=True,
    )


def main():
    print(f"[*] Starting Ultra-Fast Captcha Bridge for {SERVER_HOST} ({CONTAINER_NAME})...")
    local_img = Path("/tmp/live_captcha.png")

    while True:
        # Check if container has signal
        check = run_ssh(f"docker exec {CONTAINER_NAME} test -f /tmp/captcha_signal.txt")
        if check.returncode == 0:
            print("[+] Detected captcha_signal.txt on server!")

            # 1. Fetch image via base64 stream over SSH
            b64_res = run_ssh(f"docker exec {CONTAINER_NAME} base64 /tmp/live_captcha.png")
            if b64_res.returncode != 0 or not b64_res.stdout.strip():
                print("[-] Failed to stream image from container:", b64_res.stderr)
                time.sleep(1)
                continue

            try:
                img_data = base64.b64decode(b64_res.stdout.strip())
                local_img.write_bytes(img_data)
                print(f"[+] Downloaded captcha image via base64 ({len(img_data)} bytes)")
            except Exception as b64_err:
                print("[-] Decode error:", b64_err)
                time.sleep(1)
                continue

            # 2. Solve using NVIDIA NIM Vision
            try:
                res = label_single_image(local_img, api_key=NVIDIA_API_KEY)
                answer = str(res.get("answer", "")).strip()
                expr = res.get("expression", "")
                print(f"[+] Solved via NVIDIA NIM: {expr} = {answer}")
            except Exception as e:
                print("[-] NIM solving error:", e)
                time.sleep(1)
                continue

            if not answer:
                print("[-] Empty answer from NIM!")
                time.sleep(1)
                continue

            # 3. Write answer into container and remove signal
            write_res = run_ssh(f"docker exec {CONTAINER_NAME} sh -c 'echo \"{answer}\" > /tmp/captcha_answer.txt'")
            if write_res.returncode == 0:
                print(f"[+] Successfully wrote answer '{answer}' to /tmp/captcha_answer.txt")
                run_ssh(f"docker exec {CONTAINER_NAME} rm -f /tmp/captcha_signal.txt")
                print("[+] Signal cleared.")
            else:
                print("[-] Failed to write answer:", write_res.stderr)

        time.sleep(1)


if __name__ == "__main__":
    main()

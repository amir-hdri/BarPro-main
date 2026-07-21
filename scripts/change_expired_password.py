#!/usr/bin/env python3
"""
⚠️  SECURITY WARNING ⚠️
This script was previously hardcoded with production SSH passwords.
All credentials have been replaced with environment variable references.
Usage: SSH_PASSWORD="your-old-password" SSH_NEW_PASSWORD="your-new-password" python3 scripts/change_expired_password.py
"""

import os
import paramiko

old_password = os.environ.get("SSH_PASSWORD", "")
new_password = os.environ.get("SSH_NEW_PASSWORD", "")
ip = os.environ.get("SSH_HOST", "188.121.123.16")
username = os.environ.get("SSH_USER", "ubuntu")


def handler(title, instructions, prompt_list):
    print("--- auth_interactive handler ---")
    print("Title:", title)
    print("Instructions:", instructions)
    print("Prompt list:", prompt_list)
    answers = []
    for prompt, echo in prompt_list:
        prompt_text = prompt.lower()
        if "current" in prompt_text or ("password" in prompt_text and "new" not in prompt_text):
            print("Replying old password")
            answers.append(old_password)
        elif "new" in prompt_text:
            print("Replying new password")
            answers.append(new_password)
        elif "retype" in prompt_text or "verify" in prompt_text or "confirm" in prompt_text or "type" in prompt_text:
            print("Replying new password (confirm)")
            answers.append(new_password)
        else:
            print("Unknown prompt, replying empty")
            answers.append("")
    return answers


try:
    print(f"Connecting to {ip}...")
    transport = paramiko.Transport((ip, 22))
    transport.start_client()
    print("Client started, authenticating...")
    transport.auth_interactive(username, handler)
    if transport.is_authenticated():
        print("🎉 SUCCESS! Password changed and authenticated successfully!")
    else:
        print("❌ FAILED: Authentication did not succeed.")
except Exception as e:
    print("❌ ERROR:", e)
finally:
    try:
        transport.close()
    except Exception:
        pass  # Transport may already be closed

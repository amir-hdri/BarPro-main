#!/usr/bin/env python3
import paramiko
import sys

old_password = "vvlwrOyBWm"
new_password = "giItT1WQy@!-/#"
ip = "188.121.123.16"
username = "ubuntu"

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
    except:
        pass

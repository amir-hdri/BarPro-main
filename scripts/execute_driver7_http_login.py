import asyncio
import json
import os
import re
import sys
import time
from pathlib import Path
from urllib.parse import urljoin
from curl_cffi import requests

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from app.core.database import async_session_factory
from app.models_multitenant import Driver
from app.auth_multitenant import decrypt_driver_password
from app.automation.worker_proxy import get_worker_proxy_url
from app.automation.utcms_http_login import UtcmsHttpLogin
from sqlmodel import select

async def get_credentials():
    async with async_session_factory() as session:
        stmt = select(Driver).where(Driver.id == 7)
        driver = (await session.execute(stmt)).scalar_one_or_none()
        username = driver.utcms_username
        enc_pass = driver.utcms_password_encrypted or getattr(driver, "encrypted_password", None)
        password = decrypt_driver_password(enc_pass)
        return username, password

async def main():
    username, password = await get_credentials()
    print(f"Driver 7: username={username}")
    proxy = get_worker_proxy_url()
    print(f"Using proxy: {proxy}")
    proxies = {"http": proxy, "https": proxy} if proxy else {}

    session = requests.Session(impersonate="chrome120", proxies=proxies)
    login_url = "https://barname.utcms.ir/Account/Login"
    resp = session.get(login_url, timeout=20)
    print(f"GET {login_url} -> {resp.status_code}")
    html = resp.text

    # Extract tokens
    token_m = re.search(r'<input[^>]+name=["\']DNTCaptchaToken["\'][^>]*value=["\']([^"\']*)["\']', html)
    token = token_m.group(1) if token_m else ""

    text_m = re.search(r'<input[^>]+name=["\']DNTCaptchaText["\'][^>]*value=["\']([^"\']*)["\']', html)
    captcha_text = text_m.group(1) if text_m else ""

    anti_m = re.search(r'<input[^>]+name=["\']_*RequestVerificationToken["\'][^>]*value=["\']([^"\']*)["\']', html)
    antiforgery = anti_m.group(1) if anti_m else ""

    ajax_m = re.search(r'<form[^>]+data-ajax-url=["\']([^"\']+)["\']', html)
    ajax_url = ajax_m.group(1) if ajax_m else "/Barname/Account/OldLogin"
    post_url = urljoin(login_url, ajax_url)

    img_m = re.search(r'<img[^>]+src=["\']([^"\']*captcha[^"\']*)["\']', html, re.IGNORECASE)
    if not img_m:
        print("Captcha image not found in HTML!")
        return

    captcha_img_url = urljoin(login_url, img_m.group(1).replace("&amp;", "&"))
    print(f"Downloading captcha: {captcha_img_url}")
    img_resp = session.get(captcha_img_url, timeout=10)
    captcha_file = "/tmp/driver7_current_captcha.png"
    with open(captcha_file, "wb") as f:
        f.write(img_resp.content)
    print(f"Saved captcha image to {captcha_file} ({len(img_resp.content)} bytes)")

    # Clean previous solution file
    sol_file = "/tmp/captcha_solution.txt"
    if os.path.exists(sol_file):
        os.remove(sol_file)

    print("Waiting for captcha solution in /tmp/captcha_solution.txt...")
    solution = None
    for _ in range(60):
        if os.path.exists(sol_file):
            with open(sol_file, "r", encoding="utf-8") as sf:
                val = sf.read().strip()
                if val:
                    solution = val
                    break
        await asyncio.sleep(1)

    if not solution:
        print("❌ Timed out waiting for captcha solution.")
        return

    print(f"Submitting login with solution: {solution}")
    payload = {
        "UserName": username,
        "NationalCode": username,
        "Password": password,
        "DNTCaptchaInputText": solution,
        "DNTCaptchaToken": token,
        "DNTCaptchaText": captcha_text,
        "CapType": "1",
        "RequestVerificationToken": antiforgery,
        "__RequestVerificationToken": antiforgery,
        "ruleExcepted": "true",
    }

    headers = {
        "Referer": login_url,
        "Origin": "https://barname.utcms.ir",
        "X-Requested-With": "XMLHttpRequest",
    }

    post_resp = session.post(post_url, data=payload, headers=headers, timeout=25)
    print(f"POST {post_url} -> Status {post_resp.status_code}")
    print(f"Headers: {post_resp.headers}")
    print(f"Response: {post_resp.text[:500]}")

    login_helper = UtcmsHttpLogin()
    eval_res = login_helper._evaluate_post_response(post_resp)
    print(f"Evaluation result: success={eval_res.success}, error={eval_res.error}, cookies_count={len(eval_res.cookies)}")

    if eval_res.success:
        print("🎉 LOGIN SUCCESSFUL! Saving session state...")
        state_data = {
            "saved_at": time.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "url": "https://barname.utcms.ir/Barname/Notification/Notification",
            "cookies": eval_res.cookies,
        }
        # Save to both paths
        paths = ["/tmp/utcms_state.json", "/app/runtime/utcms_state.json", "utcms_state.json"]
        for p in paths:
            try:
                os.makedirs(os.path.dirname(os.path.abspath(p)), exist_ok=True)
                with open(p, "w", encoding="utf-8") as f:
                    json.dump(state_data, f, indent=2)
                print(f"Saved state to {p}")
            except Exception as e:
                print(f"Could not save to {p}: {e}")
    else:
        print(f"❌ Login failed: {eval_res.error}")

if __name__ == "__main__":
    asyncio.run(main())

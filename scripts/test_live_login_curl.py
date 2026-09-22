import re
import sys
from urllib.parse import urljoin
from curl_cffi import requests

from app.automation.worker_proxy import get_worker_proxy_url

def main():
    proxy = get_worker_proxy_url()
    print("Using proxy:", proxy)
    proxies = {"http": proxy, "https": proxy} if proxy else {}
    session = requests.Session(impersonate="chrome120", proxies=proxies)
    r = session.get("https://barname.utcms.ir/Account/Login", timeout=20)
    print("Status:", r.status_code)
    html = r.text
    print("Length:", len(html))

    cap_type = re.findall(r'name=["\']CapType["\'][^>]*value=["\']([^"\']*)["\']', html)
    print("CapType:", cap_type)

    token = re.findall(r'name=["\']DNTCaptchaToken["\'][^>]*value=["\']([^"\']*)["\']', html)
    print("DNTCaptchaToken:", token)

    text = re.findall(r'name=["\']DNTCaptchaText["\'][^>]*value=["\']([^"\']*)["\']', html)
    print("DNTCaptchaText:", text)

    imgs = re.findall(r'<img[^>]+src=["\']([^"\']*)["\']', html)
    print("Images:", imgs)

    captcha_url = None
    for img in imgs:
        if "captcha" in img.lower():
            captcha_url = img
            break

    if captcha_url:
        full_url = urljoin("https://barname.utcms.ir/Account/Login", captcha_url)
        print("Downloading captcha from:", full_url)
        img_resp = session.get(full_url, timeout=10)
        with open("/tmp/current_login_captcha.png", "wb") as f:
            f.write(img_resp.content)
        print("Saved to /tmp/current_login_captcha.png, size:", len(img_resp.content))

if __name__ == "__main__":
    main()

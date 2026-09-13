import re

with open("app/automation/utcms_mobile_client.py", "r") as f:
    content = f.read()

# Replace import httpx with from curl_cffi import requests as cc_requests
content = content.replace("import httpx", "from curl_cffi import requests as cc_requests")

# Replace httpx.AsyncClient instantiation
client_inst = 'client = cc_requests.AsyncSession(proxies={"http": self.proxy_url, "https": self.proxy_url} if self.proxy_url else None, timeout=self.timeout, allow_redirects=False, impersonate="chrome120")'
cap_client_inst = 'client = cc_requests.AsyncSession(proxies={"http": self.proxy_url, "https": self.proxy_url} if self.proxy_url else None, timeout=utcms_config.UTCMS_CAPTCHA_POW_TIMEOUT_SECONDS, allow_redirects=False, impersonate="chrome120")'

content = re.sub(r'client = httpx\.AsyncClient\(proxy=self\.proxy_url, timeout=self\.timeout, follow_redirects=False\)', client_inst, content)
content = re.sub(r'client = httpx\.AsyncClient\(proxy=self\.proxy_url, timeout=utcms_config\.UTCMS_CAPTCHA_POW_TIMEOUT_SECONDS\)', cap_client_inst, content)

# Replace exceptions
content = content.replace("httpx.HTTPError", "cc_requests.errors.RequestsError")

with open("app/automation/utcms_mobile_client.py", "w") as f:
    f.write(content)

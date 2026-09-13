import re

with open("tests/test_utcms_mobile_contract.py", "r") as f:
    content = f.read()

content = content.replace("proxy=proxy", "proxies={'http': proxy, 'https': proxy}")
content = content.replace("follow_redirects=False", "allow_redirects=False, impersonate='chrome120'")

with open("tests/test_utcms_mobile_contract.py", "w") as f:
    f.write(content)

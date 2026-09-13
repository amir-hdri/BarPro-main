import glob
import re

configs = glob.glob("infra/squid/*.conf")
for conf in configs:
    with open(conf, "r") as f:
        content = f.read()
    
    # Remove existing forwarded_for if any
    content = re.sub(r'forwarded_for.*\n', '', content)
    content = re.sub(r'via off\n', '', content)
    content = re.sub(r'request_header_access X-Forwarded-For deny all\n', '', content)
    
    content += "\n# --- WAF Anonymization ---\n"
    content += "forwarded_for delete\n"
    content += "via off\n"
    content += "request_header_access X-Forwarded-For deny all\n"
    
    with open(conf, "w") as f:
        f.write(content)

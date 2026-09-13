with open("docs/UTCMS_BOT_BEHAVIOR_CONTRACT.md", "r") as f:
    content = f.read()

waf_section = """
## 12. شبکه، اثرانگشت (TLS Fingerprint) و عبور از WAF

پرتال UTCMS مجهز به یک WAF سخت‌گیرانه (احتمالاً ArvanCloud) است که به اثرانگشت TLS (شناسه‌های JA3/JA4) و هدرهای غیراستاندارد حساس است:

1. **مدیریت TLS (جلوگیری از خطای 444):** 
   به هیچ عنوان نباید از `httpx`، `requests` یا `aiohttp` برای اتصال به endpointهای موبایل استفاده شود. تمامی ارتباطات باید از طریق کتابخانه `curl_cffi` (همگام/ناهمگام) با متد `impersonate="chrome120"` (یا معادل آن) صورت پذیرد تا سایفرها و پروفایل HTTP/2 دقیقاً مشابه یک مرورگر کرومِ اندرویدی جعل شود.
2. **پنهان‌سازی پراکسی (Elite Proxying):** 
   پراکسی‌های Squid باید کاملاً استتار شوند. در تمامی فایل‌های `squid.conf` دستورات `forwarded_for delete`، `via off` و `request_header_access X-Forwarded-For deny all` الزامی است. تزریق هرگونه IP کلاینت در هدرها به معنای مسدودسازی فوری توسط WAF است.
3. **ساختار هدرها:**
   هدرهای `User-Agent`، `Accept-Encoding: gzip, deflate, br` و `Sec-Ch-Ua` به صورت اتوماتیک توسط لایه `curl_cffi` تنظیم می‌شوند تا هیچ‌گونه ناهنجاری (Anomaly) در لاگ‌های WAF ثبت نشود.
"""

content += waf_section

with open("docs/UTCMS_BOT_BEHAVIOR_CONTRACT.md", "w") as f:
    f.write(content)

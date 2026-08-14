import asyncio
from curl_cffi import requests as cc_requests
from app.automation.utcms_http_login import UtcmsHttpLogin
from app.models_multitenant import Driver
from app.core.database import async_session_factory
from sqlmodel import select

async def main():
    async with async_session_factory() as session:
        driver = (await session.exec(select(Driver))).first()
        print(f"Driver: {driver.driver_national_code} {driver.full_name}")

    login_client = UtcmsHttpLogin(proxy_url="http://172.20.0.1:3128")
    login_res = await login_client.authenticate(driver.utcms_username, driver.utcms_password_encrypted)
    print("Login success:", login_res.success, "error:", login_res.error, "final_url:", login_res.final_url, "cookies count:", len(login_res.cookies))
    for c in login_res.cookies:
        print(f"  Cookie: {c.get('name')} = {str(c.get('value'))[:20]}")

    if not login_res.success:
        print("Login failed, aborting URL tests.")
        return

    # Now make GET requests with curl_cffi using these cookies
    session = cc_requests.Session(
        impersonate="chrome120",
        proxies={"http": "http://172.20.0.1:3128", "https": "http://172.20.0.1:3128"},
        verify=False,
    )
    for c in login_res.cookies:
        session.cookies.set(c["name"], c["value"], domain="barname.utcms.ir", path="/")

    urls = [
        "https://barname.utcms.ir/barname/Document/HagigiHogugi",
        "https://barname.utcms.ir/Barname/Document/HagigiHogugi",
        "https://barname.utcms.ir/barname/Home/Index",
        "https://barname.utcms.ir/Barname/Home/Index",
        "https://barname.utcms.ir/barname/DocumentList/Index",
        "https://barname.utcms.ir/Barname/DocumentList/Index",
    ]

    for u in urls:
        try:
            r = session.get(u, timeout=15.0, allow_redirects=False)
            print(f"\n--- URL: {u} ---")
            print(f"Status: {r.status_code}, Length: {len(r.text)}")
            if "location" in r.headers:
                print(f"Location: {r.headers['location']}")
            print(f"Body preview: {r.text[:350].replace(chr(10), ' ')}")
        except Exception as e:
            print(f"\n--- URL: {u} --- ERROR: {e}")

if __name__ == "__main__":
    asyncio.run(main())

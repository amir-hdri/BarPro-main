import asyncio
import httpx
from app.automation.utcms_mobile_client import UtcmsMobileClient

async def test_live():
    print("Testing connection directly...")
    async with httpx.AsyncClient(verify=False) as c:
        try:
            r = await c.get("https://cptch.utcms.ir/")
            print(r.status_code)
        except Exception as e:
            print(e)
            
    print("Testing through client...")
    client = UtcmsMobileClient() # no proxy
    try:
        site_key = await client.get_cap_site_key()
        print(f"Site Key: {site_key}")
        redeem_token = await client.solve_cap_pow(site_key)
        print(f"Redeem: {redeem_token[:20]}...")
    except Exception as e:
        print(e)

asyncio.run(test_live())

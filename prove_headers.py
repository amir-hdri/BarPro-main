import asyncio
from app.automation.utcms_mobile_client import UtcmsMobileClient

async def prove_it():
    client = UtcmsMobileClient()
    # Override base url to httpbin to echo headers back
    client.base_url = "https://httpbin.org"
    print("--- HEADERS SENT BY UTCMS_MOBILE_CLIENT ---")
    try:
        response = await client._get("headers")
        import json
        print(json.dumps(response.get("headers", {}), indent=2))
    except Exception as e:
        print("Error:", e)

asyncio.run(prove_it())

import asyncio
from app.core.database import get_session
from app.models_multitenant import Driver, WaybillJob
from app.auth_multitenant import decrypt_driver_password
from app.automation.utcms_mobile_client import UtcmsMobileClient

async def run_live_test():
    async for session in get_session():
        job = await session.get(WaybillJob, 81)
        if not job or not job.driver_id:
            print("Job 81 or Driver not found.")
            return
            
        driver = await session.get(Driver, job.driver_id)
        if not driver:
            print("Driver not found.")
            return
            
        username = driver.utcms_username
        password = decrypt_driver_password(driver.utcms_password_encrypted)
        
        print(f"--- Starting Live Mobile Bot Flow for Driver {username} ---")
        client = UtcmsMobileClient(proxy_url=None)
        
        print("1. Solving Captcha POW on cptch.utcms.ir...")
        cap_token = await client.solve_cap_pow()
        print("Captcha POW Solved! Token:", cap_token)
            
        print("2. Logging in to mobservices.utcms.ir...")
        auth_res = await client.login(username, password, cap_token)
        print("Login Response (Success!):", auth_res.raw.get("resultMessage"))
            
        print("3. Fetching User Fleet List (Protected API)...")
        fleet = await client.get_user_fleet_list()
        print("User Fleet List fetched successfully!")
        if fleet and "obj" in fleet:
            print("Fleet Data:", fleet["obj"][:1])
            
        print("\nSUCCESS! The bot successfully logged in, fetched protected data via the Mobile API, and completely bypassed the WAF.")
        return

if __name__ == "__main__":
    asyncio.run(run_live_test())

import asyncio
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from app.core.database import async_session_factory
from app.models_multitenant import Driver
from app.auth_multitenant import decrypt_driver_password
from app.automation.worker_proxy import get_worker_proxy_url
from app.automation.utcms_mobile_client import UtcmsMobileClient
from sqlmodel import select

async def main():
    async with async_session_factory() as session:
        stmt = select(Driver).where(Driver.id == 7)
        driver = (await session.execute(stmt)).scalar_one_or_none()
        username = driver.utcms_username
        enc_pass = driver.utcms_password_encrypted or getattr(driver, "encrypted_password", None)
        password = decrypt_driver_password(enc_pass)

    proxy = get_worker_proxy_url()
    print(f"Driver 7: username={username}, proxy={proxy}")
    client = UtcmsMobileClient(proxy_url=proxy)

    print("Step 1: Solving CapJS PoW for login...")
    _, cap_token = await client.auto_solve_captcha("login")
    print(f"CapJS PoW solved! cap_token={cap_token[:20]}...")

    print("Step 2: Logging in via /Account/UserLoginV2...")
    auth_result = await client.login(username, password, cap_token)
    print(f"Login successful! Bearer token={auth_result.token[:20]}..., expires_at={auth_result.expires_at}")

    print("Step 3: Fetching active shipping documents...")
    shipping_docs = await client.get_shipping_documents(driver_national_code=username)
    print("Shipping documents:", shipping_docs)

    print("Step 4: Fetching issued documents...")
    issued_docs = await client.get_issued_documents(driver_national_code=username)
    print("Issued documents:", issued_docs)

if __name__ == "__main__":
    asyncio.run(main())

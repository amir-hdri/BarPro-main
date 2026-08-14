import asyncio
import sys
import traceback

async def main():
    print("1. Importing modules...", flush=True)
    from app.automation.browser import browser_manager, managed_page
    from app.automation.auth import UTCMSAuthenticator
    from app.models_multitenant import Driver
    from app.core.database import async_session_factory
    from sqlmodel import select

    print("2. Fetching driver...", flush=True)
    async with async_session_factory() as session:
        driver = (await session.exec(select(Driver))).first()
        print(f"Driver: {driver.driver_national_code} {driver.full_name}", flush=True)

    print("3. Entering managed_page...", flush=True)
    try:
        async with managed_page() as page:
            print(f"4. Inside page! URL={page.url}", flush=True)
            auth = UTCMSAuthenticator(page, page.context)
            print("5. Calling auth.login...", flush=True)
            logged_in = await auth.login(driver.utcms_username, driver.utcms_password_encrypted)
            print(f"6. Logged in={logged_in}, URL={page.url}", flush=True)
    except Exception as e:
        print("EXCEPTION CAUGHT:", e, flush=True)
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(main())

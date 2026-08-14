import asyncio
from app.automation.utcms_http_login import UtcmsHttpLogin
from app.models_multitenant import Driver
from app.core.database import async_session_factory
from sqlmodel import select

async def main():
    async with async_session_factory() as session:
        drivers = (await session.exec(select(Driver).order_by(Driver.id))).all()
        print(f"Total drivers to test: {len(drivers)}")

    login_client = UtcmsHttpLogin(proxy_url="http://172.20.0.1:3128")

    print("\n" + "="*80)
    print(f"{'ID':<4} | {'Driver Name':<22} | {'National Code':<12} | {'Login OK':<10} | {'Error / Portal Message'}")
    print("="*80)

    for d in drivers:
        try:
            res = await login_client.authenticate(d.utcms_username, d.utcms_password_encrypted)
            err_msg = res.error or "Authenticated successfully" if res.success else (res.error or "Unknown error")
            print(f"{d.id:<4} | {d.full_name:<22} | {d.driver_national_code:<12} | {str(res.success):<10} | {err_msg}")
        except Exception as e:
            print(f"{d.id:<4} | {d.full_name:<22} | {d.driver_national_code:<12} | False      | Exception: {str(e)[:50]}")
        await asyncio.sleep(1.0)

if __name__ == "__main__":
    asyncio.run(main())

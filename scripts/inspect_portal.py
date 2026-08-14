import asyncio
import traceback
from app.automation.browser import managed_page
from app.automation.auth import UTCMSAuthenticator
from app.models_multitenant import Driver
from app.core.database import async_session_factory
from sqlmodel import select

async def inspect():
    try:
        async with async_session_factory() as session:
            driver = (await session.exec(select(Driver))).first()
            print(f"Driver: {driver.driver_national_code} {driver.full_name}")

        async with managed_page() as page:
            print("Page created, starting auth...")
            auth = UTCMSAuthenticator(page, page.context)
            logged_in = await auth.login(driver.utcms_username, driver.utcms_password_encrypted)
            print("Login status:", logged_in)
            print("Current URL:", page.url)
            print("Title:", await page.title())

            # Extract interactive elements
            links = await page.evaluate('''() => {
                return Array.from(document.querySelectorAll('a, button, li, input, div')).map(e => ({
                    tag: e.tagName,
                    text: (e.innerText || '').trim(),
                    href: e.getAttribute('href') || '',
                    id: e.id || '',
                    name: e.getAttribute('name') || '',
                    class: e.className || '',
                    onclick: e.getAttribute('onclick') || ''
                })).filter(x => (x.text && x.text.length < 50) || x.href || x.id || x.name);
            }''')
            print(f"Total interactive elements: {len(links)}")
            for l in links[:50]:
                print(f"  [{l['tag']}] text='{l['text']}' href='{l['href']}' id='{l['id']}' name='{l['name']}' onclick='{l['onclick']}'")
    except Exception as e:
        print("ERROR IN INSPECT:", e)
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(inspect())

import asyncio
from playwright.async_api import async_playwright

async def verify():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        # Mobile viewport (iPhone 14 / Pixel 7: 390x844)
        context = await browser.new_context(
            viewport={'width': 390, 'height': 844},
            user_agent='Mozilla/5.0 (iPhone; CPU iPhone OS 16_5 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.5 Mobile/15E148 Safari/604.1',
            is_mobile=True,
            has_touch=True
        )
        token = 'eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIxIiwiY2xpZW50X2NvZGUiOiJhMSIsImVtYWlsIjoiaGFtaWRAZ21haWwuY29tIiwicm9sZSI6ImNsaWVudCIsImlhdCI6MTc5MDc5OTMzNCwiZXhwIjoxNzkwODEzNzM0LCJqdGkiOiJjNDY2ZDMwZWU3NjM0MDY4OGYwNGJhMWY4YTE4ZTdkZCJ9._r_mjL18s5vcdgeqF9JELgxoYspuuwqYIMZ2wPiPjaY'
        await context.add_cookies([
            {'name': 'token', 'value': token, 'domain': 'frontend', 'path': '/'},
            {'name': 'access_token', 'value': token, 'domain': 'frontend', 'path': '/'},
        ])
        page = await context.new_page()
        res = await page.goto('http://frontend:3000/new', wait_until='networkidle')
        print(f'HTTP Status: {res.status}')
        print(f'Page URL: {page.url}')
        
        await page.wait_for_timeout(1000)
        
        # Select first driver if available
        driver_select = await page.query_selector('select')
        if driver_select:
            options = await page.query_selector_all('select option')
            if len(options) > 1:
                val = await options[1].get_attribute('value')
                if val:
                    await driver_select.select_option(val)
                    print(f'Selected driver: {val}')
                    await page.wait_for_timeout(500)
        
        # Click Next Step to reach Step 2 (مبدا)
        next_btn = await page.query_selector("button:has-text('مرحله بعد')")
        if next_btn:
            print('Clicking Next Step button...')
            await next_btn.click()
            await page.wait_for_timeout(2000)
        else:
            print('Next Step button not found')
        
        # Inspect Step 2 DOM
        current_step_heading = await page.query_selector("h2, h3")
        if current_step_heading:
            print(f'Heading: {await current_step_heading.text_content()}')
        
        map_region = await page.query_selector('[role="region"][aria-label*="نقشه تعاملی"]')
        leaflet_container = await page.query_selector('.leaflet-container')
        tiles = await page.query_selector_all('.leaflet-tile')
        map_visible = await map_region.is_visible() if map_region else False
        leaflet_visible = await leaflet_container.is_visible() if leaflet_container else False
        
        print(f'Map Region present: {map_region is not None}, visible: {map_visible}')
        print(f'Leaflet Container present: {leaflet_container is not None}, visible: {leaflet_visible}')
        print(f'Loaded tile count: {len(tiles)}')
        
        # Check tile image sources
        if tiles:
            sample_src = await tiles[0].get_attribute('src')
            print(f'Sample tile src: {sample_src}')
            
        await page.screenshot(path='/tmp/mobile_map_verified.png', full_page=True)
        print('Screenshot saved successfully to /tmp/mobile_map_verified.png')
        await browser.close()

if __name__ == '__main__':
    asyncio.run(verify())

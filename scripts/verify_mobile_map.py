import asyncio
import os
import sys
from datetime import timedelta
from playwright.async_api import async_playwright

# Ensure app is in python path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.auth_multitenant import create_access_token

async def verify_mobile_map():
    # 1. Generate fresh valid JWT token
    token = create_access_token(
        client_id=1,
        client_code="a1",
        email="hamid@gmail.com",
        expires_delta=timedelta(hours=4)
    )
    print(f"Generated fresh JWT: {token[:25]}... (valid 4h)")

    results = {
        "status_code": None,
        "page_url": None,
        "step2_heading": None,
        "step2_map_visible_by_default": False,
        "leaflet_container_present": False,
        "tile_network_responses": [],
        "dom_tile_count": 0,
        "sample_tile_url": None,
        "pin_placed_on_touch": False,
        "step3_heading": None,
        "step3_map_visible_by_default": False,
        "console_errors": [],
        "csp_violations": [],
    }

    async with async_playwright() as p:
        chromium_path = "/usr/bin/chromium" if os.path.exists("/usr/bin/chromium") else None
        launch_args = [
            "--no-sandbox",
            "--disable-setuid-sandbox",
            "--disable-dev-shm-usage",
            "--disable-gpu",
            "--disable-crashpad",
            "--disable-crash-reporter",
            "--disable-dbus",
        ]
        fallback_home = "/tmp/.playwright-home"
        os.makedirs(fallback_home, exist_ok=True)
        launch_env = os.environ.copy()
        launch_env["HOME"] = fallback_home

        browser = await p.chromium.launch(
            executable_path=chromium_path,
            headless=True,
            args=launch_args,
            env=launch_env,
            ignore_default_args=["--enable-automation"]
        )

        # Emulate standard Mobile Viewport (iPhone 14 / Pixel 7: 390x844)
        context = await browser.new_context(
            viewport={"width": 390, "height": 844},
            user_agent="Mozilla/5.0 (iPhone; CPU iPhone OS 16_5 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.5 Mobile/15E148 Safari/604.1",
            is_mobile=True,
            has_touch=True,
            geolocation={"latitude": 35.6892, "longitude": 51.3890},
            permissions=["geolocation"]
        )

        # Set cookies for the target host
        target_host = os.environ.get("TARGET_HOST", "87.107.5.238")
        target_url = f"http://{target_host}/new"

        await context.add_cookies([
            {"name": "utcms_auth_token", "value": token, "domain": target_host, "path": "/"},
            {"name": "token", "value": token, "domain": target_host, "path": "/"},
            {"name": "access_token", "value": token, "domain": target_host, "path": "/"},
            {"name": "utcms_auth_token", "value": token, "domain": "barpro-nginx", "path": "/"},
        ])

        # Pre-populate client in localStorage so AuthGuard immediately authenticates
        import json
        client_json = json.dumps({
            "id": 1,
            "name": "شرکت حمل و نقل بارپرو",
            "email": "hamid@gmail.com",
            "client_code": "a1",
            "role": "client"
        })
        await context.add_init_script(f"""
            window.localStorage.setItem('utcms_auth_client', '{client_json}');
        """)

        page = await context.new_page()

        # Capture console events
        def on_console(msg):
            text = msg.text
            if msg.type in ["error", "warning"] or "violates" in text.lower() or "csp" in text.lower():
                print(f"[BROWSER {msg.type.upper()}] {text}")
                if "violates" in text.lower() or "csp" in text.lower():
                    results["csp_violations"].append(text)
                elif msg.type == "error":
                    results["console_errors"].append(text)

        page.on("console", on_console)
        page.on("pageerror", lambda err: results["console_errors"].append(str(err)))

        # Track network tile requests
        def on_response(response):
            url = response.url
            if "google.com/vt/lyrs" in url or "openstreetmap" in url or "cartocdn" in url:
                results["tile_network_responses"].append({
                    "url": url,
                    "status": response.status,
                    "content_type": response.headers.get("content-type", "")
                })

        page.on("response", on_response)

        print(f"Navigating to {target_url} with mobile touch viewport (390x844)...")
        res = await page.goto(target_url, wait_until="networkidle", timeout=30000)
        results["status_code"] = res.status if res else None
        results["page_url"] = page.url
        print(f"HTTP Status: {results['status_code']} | URL: {results['page_url']}")

        await page.wait_for_timeout(1000)

        # Step 1: Select Driver if present and go to Step 2
        driver_select = await page.query_selector("select")
        if driver_select:
            options = await page.query_selector_all("select option")
            if len(options) > 1:
                val = await options[1].get_attribute("value")
                if val:
                    await driver_select.select_option(val)
                    print(f"Selected driver: {val}")
                    await page.wait_for_timeout(500)

        next_btn = await page.query_selector("button:has-text('مرحله بعد')")
        if next_btn:
            print("Clicking 'مرحله بعد' to reach Step 2 (اطلاعات مبدا)...")
            await next_btn.click()
            await page.wait_for_timeout(1500)

        # Step 2: Verify Origin Map
        step2_header = await page.query_selector("h2:has-text('مرحله ۲: اطلاعات مبدا'), h3:has-text('مرحله ۲')")
        if step2_header:
            results["step2_heading"] = await step2_header.text_content()
            print(f"Heading confirmed: {results['step2_heading']}")

        map_region = await page.query_selector('[role="region"][aria-label*="نقشه تعاملی"]')
        leaflet_container = await page.query_selector(".leaflet-container")

        results["step2_map_visible_by_default"] = await map_region.is_visible() if map_region else False
        results["leaflet_container_present"] = await leaflet_container.is_visible() if leaflet_container else False

        print(f"Step 2 Map visible by default (WITHOUT clicking expand): {results['step2_map_visible_by_default']}")
        print(f"Leaflet container rendered: {results['leaflet_container_present']}")

        # Wait for tiles to render
        await page.wait_for_timeout(2000)

        tiles = await page.query_selector_all(".leaflet-tile")
        results["dom_tile_count"] = len(tiles)
        print(f"Rendered leaflet tiles in DOM: {results['dom_tile_count']}")

        if tiles:
            sample_src = await tiles[0].get_attribute("src")
            results["sample_tile_url"] = sample_src
            print(f"Sample tile src: {sample_src}")

        # Simulate mobile touch / click on map to place pin
        if leaflet_container:
            box = await leaflet_container.bounding_box()
            if box:
                click_x = box["x"] + box["width"] / 2
                click_y = box["y"] + box["height"] / 2
                print(f"Tapping map center at ({click_x:.1f}, {click_y:.1f}) to place location pin...")
                await page.mouse.click(click_x, click_y)
                await page.wait_for_timeout(1000)

                marker = await page.query_selector(".leaflet-marker-icon")
                results["pin_placed_on_touch"] = marker is not None
                print(f"Marker pin placed on touch: {results['pin_placed_on_touch']}")

        screenshot_s2 = "/tmp/mobile_step2_origin_map.png"
        await page.screenshot(path=screenshot_s2, full_page=True)
        print(f"Step 2 Mobile Screenshot saved: {screenshot_s2}")

        # Fill Step 2 required fields to proceed to Step 3
        # Select province/city if inputs exist
        inputs = await page.query_selector_all("input")
        for inp in inputs:
            name = await inp.get_attribute("name") or ""
            val = await inp.input_value()
            if not val and ("address" in name.lower() or "آدرس" in str(await inp.get_attribute("placeholder"))):
                await inp.fill("میدان انقلاب، انبار شماره ۱")

        # Click next to Step 3
        next_btn = await page.query_selector("button:has-text('مرحله بعد')")
        if next_btn:
            print("Clicking 'مرحله بعد' to reach Step 3 (اطلاعات مقصد)...")
            await next_btn.click()
            await page.wait_for_timeout(1500)

            step3_header = await page.query_selector("h2:has-text('مرحله ۳: اطلاعات مقصد'), h3:has-text('مرحله ۳')")
            if step3_header:
                results["step3_heading"] = await step3_header.text_content()
                print(f"Step 3 Heading: {results['step3_heading']}")

            s3_map = await page.query_selector('[role="region"][aria-label*="نقشه تعاملی"]')
            results["step3_map_visible_by_default"] = await s3_map.is_visible() if s3_map else False
            print(f"Step 3 Map visible by default: {results['step3_map_visible_by_default']}")

            screenshot_s3 = "/tmp/mobile_step3_dest_map.png"
            await page.screenshot(path=screenshot_s3, full_page=True)
            print(f"Step 3 Mobile Screenshot saved: {screenshot_s3}")

        await browser.close()

    print("\n" + "="*50)
    print("=== MOBILE MAP VERIFICATION SUMMARY ===")
    print("="*50)
    print(f"Target URL: {target_url}")
    print(f"HTTP Status: {results['status_code']}")
    print(f"CSP Violations: {len(results['csp_violations'])}")
    print(f"Console Errors: {len(results['console_errors'])}")
    print(f"Step 2 Map Visible by Default: {results['step2_map_visible_by_default']}")
    print(f"Leaflet Container Rendered: {results['leaflet_container_present']}")
    print(f"DOM Leaflet Tiles Count: {results['dom_tile_count']}")
    print(f"Network Tile Responses: {len(results['tile_network_responses'])}")
    if results["tile_network_responses"]:
        ok_count = sum(1 for r in results["tile_network_responses"] if r["status"] == 200)
        print(f"Google Maps Tiles with HTTP 200 OK: {ok_count} / {len(results['tile_network_responses'])}")
    print(f"Sample Tile Source: {results['sample_tile_url']}")
    print(f"Pin Marker Placed on Touch: {results['pin_placed_on_touch']}")
    print(f"Step 3 Map Visible by Default: {results['step3_map_visible_by_default']}")
    print("="*50)

    # Assertions
    assert results["status_code"] == 200, f"Expected HTTP 200, got {results['status_code']}"
    assert len(results["csp_violations"]) == 0, f"CSP Violations detected: {results['csp_violations']}"
    assert results["step2_map_visible_by_default"], "Step 2 map was NOT visible by default!"
    assert results["leaflet_container_present"], "Leaflet container was NOT rendered in DOM!"
    assert results["dom_tile_count"] > 0, "No leaflet tiles were rendered!"
    assert len(results["tile_network_responses"]) > 0, "No tile network requests received!"
    assert any("google.com" in r["url"] and r["status"] == 200 for r in results["tile_network_responses"]), "Google Maps tiles did not return HTTP 200!"
    print("\n>> ALL ASSERTIONS PASSED WITH CONCRETE PROOF! <<\n")

if __name__ == "__main__":
    asyncio.run(verify_mobile_map())

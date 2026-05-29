"""
Complete Anti-Detection Automation Example
===========================================
Demonstrates the full anti-detection system with:
- Browser fingerprint management
- Proxy rotation with health checks
- HTTP header building
- Human-like behavior
- Stealth browser automation
"""

import asyncio
import logging
from datetime import datetime

from app.automation import (
    BrowserManager,
    get_header_builder,
    get_proxy_rotator,
)

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s - %(message)s",
)
logger = logging.getLogger(__name__)


async def example_1_basic_stealth_browser():
    """Example 1: Basic stealth browser with fingerprint"""
    logger.info("=" * 60)
    logger.info("Example 1: Basic Stealth Browser")
    logger.info("=" * 60)

    browser_manager = BrowserManager()

    try:
        # Initialize browser
        await browser_manager.initialize()

        # Create context with random fingerprint
        session_id, context = await browser_manager.create_context()

        # Create new page
        page = await browser_manager.new_page(context)

        # Apply stealth
        from app.automation.stealth import apply_stealth_mode

        await apply_stealth_mode(page)

        # Navigate to a test site
        await page.goto("https://whatismybrowser.com/detect/user-agent", wait_until="load")

        # Take screenshot
        await page.screenshot(path=f"output/example1_screenshot_{datetime.now():%Y%m%d_%H%M%S}.png")

        logger.info("✅ Basic stealth browser example completed")

        # Cleanup
        await browser_manager.close_context(session_id)

    except Exception as e:
        logger.error(f"❌ Error: {e}")
    finally:
        await browser_manager.cleanup()


async def example_2_proxy_rotation():
    """Example 2: Proxy rotation with health checking"""
    logger.info("=" * 60)
    logger.info("Example 2: Proxy Rotation with Health Check")
    logger.info("=" * 60)

    # Initialize proxy rotator
    rotator = get_proxy_rotator()

    # Load proxies from list
    proxy_urls = [
        "http://proxy1.example.com:8080",
        "http://proxy2.example.com:3128",
        "socks5://proxy3.example.com:1080",
    ]

    rotator.load_from_list(proxy_urls)

    logger.info(f"✅ Loaded {len(rotator.proxies)} proxies")

    # Get stats
    stats = rotator.get_stats()
    logger.info(f"📊 Proxy pool stats: {stats}")

    # Simulate proxy usage
    for i in range(3):
        proxy = await rotator.get_next()
        if proxy:
            logger.info(f"🌐 Using proxy {i+1}: {proxy.url[:50]}...")
            # Simulate request
            await asyncio.sleep(0.1)
        else:
            logger.warning("⚠️ No available proxy")

    logger.info("✅ Proxy rotation example completed")


async def example_3_header_building():
    """Example 3: Building realistic HTTP headers"""
    logger.info("=" * 60)
    logger.info("Example 3: HTTP Header Builder")
    logger.info("=" * 60)

    builder = get_header_builder()

    # Build headers for different browsers
    browsers = [
        {
            "name": "Chrome Windows",
            "user_agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/124.0.0.0 Safari/537.36",
            "platform": "Win32",
        },
        {
            "name": "Firefox Windows",
            "user_agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:125.0) Gecko/20100101 Firefox/125.0",
            "platform": "Win32",
        },
        {
            "name": "Chrome macOS",
            "user_agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) Chrome/124.0.0.0 Safari/537.36",
            "platform": "MacIntel",
        },
    ]

    for browser in browsers:
        headers = builder.build(
            user_agent=browser["user_agent"],
            platform=browser["platform"],
            language="en-US",
            referer="",
        )

        logger.info(f"\n🔹 {browser['name']}:")
        logger.info(f"   User-Agent: {headers['User-Agent'][:60]}...")
        logger.info(f"   Accept: {headers['Accept'][:50]}...")
        logger.info(f"   Accept-Language: {headers['Accept-Language']}")

        if "Sec-CH-UA" in headers:
            logger.info(f"   Sec-CH-UA: {headers['Sec-CH-UA'][:50]}...")

    # Build API headers
    api_headers = builder.build_api_headers(
        user_agent="Chrome/124.0",
        content_type="application/json",
    )

    logger.info("\n🔹 API Request Headers:")
    logger.info(f"   Content-Type: {api_headers['Content-Type']}")
    logger.info(f"   X-Requested-With: {api_headers.get('X-Requested-With')}")

    logger.info("✅ Header building example completed")


async def example_4_human_behavior():
    """Example 4: Human-like behavior simulation"""
    logger.info("=" * 60)
    logger.info("Example 4: Human Behavior Simulation")
    logger.info("=" * 60)

    from app.automation import click_with_human_movement, human_type, wait_like_human

    browser_manager = BrowserManager()

    try:
        await browser_manager.initialize()
        session_id, context = await browser_manager.create_context()
        page = await browser_manager.new_page(context)

        # Apply stealth
        from app.automation.stealth import apply_stealth_mode

        await apply_stealth_mode(page)

        # Navigate to a form
        await page.goto("https://the-internet.herokuapp.com/login", wait_until="load")

        logger.info("🤖 Simulating human-like typing...")

        # Human-like typing
        await human_type(
            page=page,
            selector="input[name='username']",
            text="testuser",
            add_typos=False,
        )

        # Add delay between fields
        await wait_like_human(0.5, 1.5)

        # Human-like typing for password
        await human_type(
            page=page,
            selector="input[name='password']",
            text="testpassword",
        )

        # Add delay before click
        await wait_like_human(1.0, 2.0)

        # Human-like click
        success = await click_with_human_movement(
            page=page,
            selector="button[type='submit']",
            wait_for_navigation=True,
        )

        if success:
            logger.info("✅ Human behavior simulation completed")
        else:
            logger.warning("⚠️ Click may have failed")

        # Take screenshot
        await page.screenshot(path=f"output/example4_human_behavior_{datetime.now():%Y%m%d_%H%M%S}.png")

        await browser_manager.close_context(session_id)

    except Exception as e:
        logger.error(f"❌ Error: {e}")
    finally:
        await browser_manager.cleanup()


async def example_5_complete_workflow():
    """Example 5: Complete anti-detection workflow"""
    logger.info("=" * 60)
    logger.info("Example 5: Complete Anti-Detection Workflow")
    logger.info("=" * 60)

    # 1. Initialize components
    browser_manager = BrowserManager()
    # rotator = get_proxy_rotator()
    builder = get_header_builder()

    # 2. Setup proxy (optional)
    # rotator.add_proxy(ProxyConfig(url="http://your-proxy.com:8080"))

    # 3. Initialize browser
    await browser_manager.initialize()

    try:
        # 4. Create context with fingerprint
        session_id, context = await browser_manager.create_context()
        page = await browser_manager.new_page(context)

        # 5. Apply stealth
        from app.automation.stealth import apply_stealth_mode

        await apply_stealth_mode(page)

        # 6. Build headers
        headers = builder.build(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/124.0",
            platform="Win32",
            language="en-US",
        )

        logger.info(f"🔧 Headers prepared: {len(headers)} headers")

        # 7. Navigate with human-like behavior
        await page.goto("https://httpbin.org/ip", wait_until="domcontentloaded")

        # Wait like human
        await asyncio.sleep(1.5)

        # Get current IP
        ip_data = await page.evaluate("() => fetch('/ip').then(r => r.json())")
        logger.info(f"🌐 Current IP: {ip_data.get('origin')}")

        # 8. Take fingerprint
        fingerprint = await page.evaluate("""
            () => ({
                userAgent: navigator.userAgent,
                platform: navigator.platform,
                language: navigator.language,
                pixelRatio: window.devicePixelRatio,
                screenResolution: `${screen.width}x${screen.height}`,
                webgl: navigator.webdriver === undefined ? 'masked' : 'detected'
            })
        """)

        logger.info("🔍 Fingerprint:")
        logger.info(f"   User Agent: {fingerprint['userAgent'][:50]}...")
        logger.info(f"   Platform: {fingerprint['platform']}")
        logger.info(f"   Language: {fingerprint['language']}")
        logger.info(f"   WebGL: {fingerprint['webgl']}")

        # 9. Screenshot
        await page.screenshot(path=f"output/example5_workflow_{datetime.now():%Y%m%d_%H%M%S}.png")

        logger.info("✅ Complete workflow completed successfully")

        # Cleanup
        await browser_manager.close_context(session_id)

    except Exception as e:
        logger.error(f"❌ Error: {e}")
        import traceback

        traceback.print_exc()
    finally:
        await browser_manager.cleanup()


async def main():
    """Run all examples"""
    logger.info("\n" + "=" * 60)
    logger.info("ANTI-DETECTION AUTOMATION - COMPLETE EXAMPLES")
    logger.info("=" * 60 + "\n")

    examples = [
        ("Basic Stealth Browser", example_1_basic_stealth_browser),
        ("Proxy Rotation", example_2_proxy_rotation),
        ("Header Building", example_3_header_building),
        ("Human Behavior", example_4_human_behavior),
        ("Complete Workflow", example_5_complete_workflow),
    ]

    for name, example_func in examples:
        try:
            await example_func()
            logger.info("")
        except Exception as e:
            logger.error(f"❌ {name} failed: {e}")
            logger.error(f"   {type(e).__name__}: {e}")
            logger.info("")

    logger.info("=" * 60)
    logger.info("ALL EXAMPLES COMPLETED")
    logger.info("=" * 60)


if __name__ == "__main__":
    # Create output directory
    import os

    os.makedirs("output", exist_ok=True)

    # Run examples
    asyncio.run(main())

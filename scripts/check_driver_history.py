#!/usr/bin/env python3
"""Check driver UTCMS waybill history directly to verify if a waybill exists."""

import asyncio
import json
import logging
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from sqlmodel import select
from app.core.database import async_session_factory
from app.models_multitenant import Driver
from app.auth_multitenant import decrypt_driver_password
from app.automation.browser import browser_manager
from app.automation.auth import UTCMSAuthenticator
from app.automation.worker_proxy import get_playwright_proxy
from app.orchestrator.utcms_reconciliation_scraper import reconciliation_scraper, _parse_iranian_plate_tags

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("check_driver_history")


async def main():
    driver_id = 7
    async with async_session_factory() as session:
        stmt = select(Driver).where(Driver.id == driver_id)
        driver = (await session.execute(stmt)).scalar_one_or_none()
        if not driver:
            logger.error("Driver %s not found", driver_id)
            return

        username = driver.utcms_username
        enc_pass = driver.utcms_password_encrypted or getattr(driver, "encrypted_password", None)
        password = decrypt_driver_password(enc_pass)

    logger.info("Found driver: %s %s (%s)", getattr(driver, "first_name", ""), getattr(driver, "last_name", ""), username)

    proxy_dict = get_playwright_proxy()
    logger.info("Using proxy: %s", proxy_dict)

    session_id, context = await browser_manager.create_context(proxy_dict=proxy_dict)
    page = await browser_manager.new_page(context)

    try:
        authenticator = UTCMSAuthenticator(page=page, context=context)
        logged_in = await authenticator.login(username=username, password=password)
        if not logged_in:
            logger.error("Failed to login to UTCMS")
            return

        logger.info("Login successful. Navigating to History page...")
        await page.goto("https://barname.utcms.ir/Barname/History/History", wait_until="domcontentloaded", timeout=45000)
        await asyncio.sleep(2)

        await page.screenshot(path="/tmp/driver7_history.png", full_page=True)
        logger.info("Saved history screenshot to /tmp/driver7_history.png")

        # Query recent waybills for this driver
        tag1, tag2, tag3, tag4 = _parse_iranian_plate_tags("78ع96523")
        post_filter = {
            "fromDate": "",
            "toDate": "",
            "senderName": "",
            "reciverName": "",
            "driverName": "",
            "driverNationalCode": username,
            "sourceAddress": "",
            "destAddress": "",
            "docNo": "",
            "type": 0,
            "irCarTag1": tag1 or "",
            "irCarTag2": tag2 or "",
            "irCarTag3": tag3 or "",
            "irCarTag4": tag4 or "",
            "freeZoneId": "",
            "freeZoneTwoDigit": "",
            "freeZoneNo": "",
            "HasFreezone": True,
        }

        fetch_script = f"""
        async () => {{
            try {{
                const formData = new URLSearchParams();
                formData.append('draw', '1');
                formData.append('start', '0');
                formData.append('length', '20');
                formData.append('search[value]', '');
                formData.append('search[regex]', 'false');
                formData.append('function', 'GetHistoryFirstList');
                formData.append('data', JSON.stringify([{json.dumps(post_filter)}]));

                const res = await fetch('/Barname/History/GetHistoryFirstList', {{
                    method: 'POST',
                    headers: {{
                        'Content-Type': 'application/x-www-form-urlencoded; charset=UTF-8',
                        'X-Requested-With': 'XMLHttpRequest'
                    }},
                    body: formData.toString()
                }});
                if (!res.ok) return {{ status: res.status, error: await res.text() }};
                return await res.json();
            }} catch (err) {{
                return {{ error: String(err) }};
            }}
        }}
        """

        result = await page.evaluate(fetch_script)
        logger.info("History API result: %s", json.dumps(result, ensure_ascii=False, indent=2))

    finally:
        await browser_manager.close_context(session_id=session_id)


if __name__ == "__main__":
    asyncio.run(main())

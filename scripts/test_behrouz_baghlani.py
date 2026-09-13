#!/usr/bin/env python3
"""
Test runner for waybill registration of driver Behrouz Baghlani (id=3, plate: 82ع338ایران24).
Matches the failed payload of job_f63a804546bb42bd and confirmed reference job_86447859944d459f.

Captures step-by-step screenshots at EVERY stage and saves them to /app/runtime/screenshots/test_baghlani/.

Usage:
    # Phase 1: Dry-Run (Full form entry up to final submit gate, with screenshots)
    docker exec barpro-worker-1 python scripts/test_behrouz_baghlani.py

    # Phase 2: Live submit (Exact 1 real submission after dry-run passes)
    docker exec barpro-worker-1 python scripts/test_behrouz_baghlani.py --live
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import os
import sys
import time
from pathlib import Path

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger("test_baghlani")

SCREENSHOT_DIR = Path("/app/runtime/screenshots/test_baghlani")

# Confirmed payload for Behrouz Baghlani from job_f63a804546bb42bd / job_86447859944d459f
PAYLOAD = {
    "sender": {
        "name": "جواد سمیرات",
        "phone": "09123150212",
        "national_code": "",
        "address": "اهواز",
    },
    "receiver": {
        "name": "علی مومنی",
        "phone": "09123150212",
        "national_code": "",
        "address": "اهواز",
    },
    "origin": {
        "province": "خوزستان",
        "city": "اهواز",
        "district": "",
        "address": "اهواز",
        "coordinates": None,
    },
    "destination": {
        "province": "خوزستان",
        "city": "اهواز",
        "district": "",
        "address": "اهواز",
        "coordinates": None,
    },
    "cargo": {
        "type": "آجر",
        "packaging": "فله",
        "weight": "4",
        "count": "1",
        "description": "",
        "value": "35000000",
    },
    "vehicle": {
        "driver_national_code": "1810364371",
        "driver_phone": "09160652050",
        "plate": "82ع338ایران24",
        "type": "کامیون",
        "driver_name": "بهروز بغلانی",
    },
    "financial": {"cost": 5000000, "fare": 5000000, "payment_method": None},
    "shipping_options": {
        "two_way": False,
        "time_limit": None,
        "end_shipping": None,
        "otp": None,
    },
}


async def _load_credentials() -> tuple[str, str, dict[str, str]]:
    from sqlmodel import select
    from app.auth_multitenant import decrypt_driver_password
    from app.core.database import async_session_factory
    from app.models_multitenant import Driver

    def _digits(value: str) -> str:
        return "".join(ch for ch in str(value or "") if ch.isdigit())

    wanted_phone = _digits(PAYLOAD["vehicle"].get("driver_phone", ""))
    wanted_nc = _digits(PAYLOAD["vehicle"].get("driver_national_code", ""))

    async with async_session_factory() as s:
        candidates = [d for d in (await s.exec(select(Driver))).all() if d.status == "active" and d.utcms_username]
        chosen = None
        for driver in candidates:
            if wanted_nc and _digits(driver.driver_national_code) == wanted_nc:
                chosen = driver
                break
            if wanted_phone and _digits(driver.phone) == wanted_phone:
                chosen = driver
                break

        if chosen is None:
            raise RuntimeError("Driver Behrouz Baghlani not found in database or inactive")

        identity = {
            "driver_national_code": str(chosen.driver_national_code or ""),
            "driver_name": str(chosen.full_name or ""),
            "driver_phone": str(chosen.phone or ""),
            "plate": "82ع338ایران24",
        }
        return chosen.utcms_username, decrypt_driver_password(chosen.utcms_password_encrypted), identity


async def run(live: bool, job_id: str) -> dict:
    from app.automation.browser import browser_manager
    from app.automation.multitenant_payload_adapter import (
        build_enhanced_waybill_payload,
        validate_live_waybill_payload,
    )
    from app.automation.utcms_http_login import UtcmsHttpLogin
    from app.automation.waybill_enhanced import EnhancedWaybillManager
    from app.automation.worker_proxy import get_worker_proxy_url
    from app.automation.captcha.dnt_captcha_solver import DntCaptchaProvider

    proxy_url = get_worker_proxy_url()
    username, password, identity = await _load_credentials()
    logger.info("Driver matched: %s (user: ***%s, plate: %s)", identity["driver_name"], username[-4:], identity["plate"])

    for key, value in identity.items():
        if value:
            PAYLOAD["vehicle"][key] = value

    normalized_payload = build_enhanced_waybill_payload(PAYLOAD)
    payload_errors = validate_live_waybill_payload(
        normalized_payload,
        expected_driver_national_code=PAYLOAD["vehicle"].get("driver_national_code"),
        expected_plate=identity.get("plate"),
        expected_driver_mobile=identity.get("driver_phone"),
    )
    if payload_errors:
        logger.error("Payload validation failed: %s", payload_errors)
        return {
            "success": False,
            "status": "needs_review",
            "error_category": "payload_validation_failed",
            "errors": payload_errors,
        }

    SCREENSHOT_DIR.mkdir(parents=True, exist_ok=True)
    screenshots = {}

    # Step 1: HTTP Login
    t0 = time.monotonic()
    login = UtcmsHttpLogin(proxy_url=proxy_url)
    auth_res = await login.authenticate(username, password)
    if not auth_res.success:
        raise RuntimeError(f"HTTP login failed: {auth_res.error}")
    logger.info("HTTP login successful in %.1fs. Cookies: %s", time.monotonic() - t0, [c["name"] for c in auth_res.cookies])

    # Step 2: Browser context and cookie injection
    session_id, ctx = await browser_manager.create_context(proxy_dict={"server": proxy_url} if proxy_url else None)
    try:
        if not await login.inject_cookies_into_context_async(auth_res, ctx):
            raise RuntimeError("Failed to inject auth cookies into Playwright context")
        page = await browser_manager.new_page(ctx)

        page.on("pageerror", lambda exc: logger.error("Page JS Error: %s", str(exc)[:300]))
        page.on(
            "console",
            lambda msg: (
                logger.warning("Browser Console [%s]: %s", msg.type, msg.text[:300])
                if msg.type in ("error", "warning")
                else None
            ),
        )

        from app.automation.http_browser_bridge import ensure_utcms_http_browser_bridge

        bridge = await ensure_utcms_http_browser_bridge(page)
        if bridge is not None:
            await bridge.adopt_authenticated_session(login.take_authenticated_session(), auth_res.cookies)

        logger.info("Navigating to UTCMS Home...")
        await page.goto("https://barname.utcms.ir/Barname/Home", timeout=90000)
        await page.wait_for_timeout(2000)
        body = await page.content()
        if not ("خروج" in body or "logout" in body.lower()):
            raise RuntimeError("Playwright session is not authenticated on UTCMS Home")
        logger.info("Playwright authenticated successfully on UTCMS Home.")

        # Screenshot 1: Home page authenticated
        p1 = str(SCREENSHOT_DIR / "01_home_authenticated.png")
        await page.screenshot(path=p1)
        screenshots["01_home_authenticated"] = p1
        logger.info("Saved screenshot: %s", p1)

        # Custom manager to capture screenshots during form steps
        class StepScreenshotWaybillManager(EnhancedWaybillManager):
            async def _fill_sender_info(self, sender_data):
                p = str(SCREENSHOT_DIR / "02_form_opened.png")
                await self.page.screenshot(path=p)
                screenshots["02_form_opened"] = p
                logger.info("Saved screenshot: %s", p)
                res = await super()._fill_sender_info(sender_data)
                p = str(SCREENSHOT_DIR / "03_sender_filled.png")
                await self.page.screenshot(path=p)
                screenshots["03_sender_filled"] = p
                logger.info("Saved screenshot: %s", p)
                return res

            async def _fill_receiver_info(self, receiver_data):
                res = await super()._fill_receiver_info(receiver_data)
                p = str(SCREENSHOT_DIR / "04_receiver_filled.png")
                await self.page.screenshot(path=p)
                screenshots["04_receiver_filled"] = p
                logger.info("Saved screenshot: %s", p)
                return res

            async def _fill_vehicle_info(self, vehicle_data):
                res = await super()._fill_vehicle_info(vehicle_data)
                p = str(SCREENSHOT_DIR / "05_vehicle_filled.png")
                await self.page.screenshot(path=p)
                screenshots["05_vehicle_filled"] = p
                logger.info("Saved screenshot: %s", p)
                return res

            async def _fill_cargo_info(self, cargo_data):
                res = await super()._fill_cargo_info(cargo_data)
                p = str(SCREENSHOT_DIR / "06_cargo_filled.png")
                await self.page.screenshot(path=p)
                screenshots["06_cargo_filled"] = p
                logger.info("Saved screenshot: %s", p)
                return res

            async def _fill_location_info_with_map(self, origin, destination, shipping_options=None):
                res = await super()._fill_location_info_with_map(origin, destination, shipping_options)
                p = str(SCREENSHOT_DIR / "07_location_map_filled.png")
                await self.page.screenshot(path=p)
                screenshots["07_location_map_filled"] = p
                logger.info("Saved screenshot: %s", p)
                return res

            async def _inspect_final_submission_stage(self):
                p = str(SCREENSHOT_DIR / "08_final_stage_ready.png")
                await self.page.screenshot(path=p)
                screenshots["08_final_stage_ready"] = p
                logger.info("Saved screenshot: %s", p)
                return await super()._inspect_final_submission_stage()

        mgr = StepScreenshotWaybillManager(page, ctx)
        t_form = time.monotonic()
        result = await mgr.create_waybill_with_map(PAYLOAD, dry_run=not live, job_id=job_id)
        result["elapsed_seconds"] = round(time.monotonic() - t_form, 1)

        # Captcha screenshot and diagnostic
        captcha_img_loc = page.locator("#DNTCaptchaImg, img[id*='DNTCaptcha'], img[src*='DNTCaptchaImage']").first
        if await captcha_img_loc.is_visible(timeout=2000):
            p_cap = str(SCREENSHOT_DIR / "09_captcha_element.png")
            await captcha_img_loc.screenshot(path=p_cap)
            screenshots["09_captcha_element"] = p_cap
            logger.info("Saved captcha element screenshot: %s", p_cap)

        if not live:
            logger.info("--- DRY-RUN CAPTCHA SOLVER TEST ---")
            captcha_b64 = await mgr._extract_captcha_image_base64("input[name='DNTCaptchaInputText']")
            if captcha_b64:
                dnt_solver = DntCaptchaProvider()
                dnt_res = await dnt_solver.solve_text_captcha(captcha_b64)
                logger.info("DntCaptchaProvider result: solved=%s, value='%s', error='%s'", dnt_res.solved, dnt_res.value, dnt_res.error)
                result["captcha_diagnostic"] = {
                    "solved": dnt_res.solved,
                    "value": dnt_res.value,
                    "provider": dnt_res.provider,
                    "error": dnt_res.error,
                }
            else:
                result["captcha_diagnostic"] = {"error": "captcha_image_not_found"}

        result["screenshots"] = screenshots
        return result
    finally:
        try:
            await browser_manager.close_context(session_id)
        except Exception:
            logger.debug("Context close error", exc_info=True)


def main() -> int:
    parser = argparse.ArgumentParser(description="Test waybill registration for driver Behrouz Baghlani")
    parser.add_argument("--live", action="store_true", help="Execute real final submit (Live submission)")
    parser.add_argument("--job-id", default=None, help="Job ID to use")
    args = parser.parse_args()

    job_id = args.job_id or (f"live-baghlani-{int(time.time())}" if args.live else f"dryrun-baghlani-{int(time.time())}")
    logger.info("Starting test with job_id=%s, live=%s", job_id, args.live)

    try:
        result = asyncio.run(run(live=args.live, job_id=job_id))
    except Exception as exc:
        logger.error("Execution failed with exception: %s", exc, exc_info=True)
        return 1

    print("\n" + "=" * 30 + " WAYBILL TEST RESULT " + "=" * 30)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    print("=" * 81 + "\n")

    if result.get("success"):
        return 0
    return 2 if result.get("status") == "needs_review" else 1


if __name__ == "__main__":
    sys.exit(main())

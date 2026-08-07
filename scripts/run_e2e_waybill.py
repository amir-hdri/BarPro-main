#!/usr/bin/env python3
"""E2E waybill submission with automatic UTCMS-outage recovery.

Usage (inside a worker container):
    python /app/scripts/run_e2e_waybill.py            # full submission
    python /app/scripts/run_e2e_waybill.py --dry-run  # only verify login+form reachability
    python /app/scripts/run_e2e_waybill.py --wait-min 180   # poll up to 180 min for UTCMS

Flow:
  1. Poll the login page (HTTP, curl_cffi) until UTCMS answers 200.
  2. HTTP login → real Chrome-fingerprinted session.
  3. Verify the waybill form page reachability over HTTP (uses the
     new fetch_authenticated() recovery pattern).
  4. If reachable and not --dry-run: inject cookies into Playwright and
     run EnhancedWaybillManager.create_waybill_with_map() with the real
     payload; print the tracking result.
"""

from __future__ import annotations

import argparse
import asyncio
import datetime
import json
import logging
import sys
import time

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(message)s")
logger = logging.getLogger("e2e_waybill")

PAYLOAD = {
    "sender": {
        "name": "بهروز بغلانی",
        "phone": "09165437654",
        "national_code": "",
        "address": "",
    },
    "receiver": {
        "name": "علی کوچکی",
        "phone": "093562618730",
        "national_code": "",
        "address": "",
    },
    "origin": {
        "province": "خوزستان",
        "city": "ماهشهر",
        "district": "",
        "address": "",
        "coordinates": None,
    },
    "destination": {
        "province": "خوزستان",
        "city": "ماهشهر",
        "district": "",
        "address": "",
        "coordinates": None,
    },
    "cargo": {
        "type": "مصالح",
        "weight": "3",
        "count": "1000",
        "description": "",
        "value": "123456789",
    },
    "vehicle": {
        "driver_national_code": "",
        "driver_phone": "09160652050",
        "plate": "82ع338ایران24",
        "type": "6 تنی",
        "driver_name": "بهروز بغلانی",
    },
    "financial": {"cost": None, "payment_method": None},
    "shipping_options": {
        "two_way": False,
        "time_limit": None,
        "end_shipping": None,
        "otp": None,
    },
}

FORM_URL = "https://barname.utcms.ir/barname/Document/HagigiHogugi"
LOGIN_URL = "https://barname.utcms.ir/Barname/Account/Login"


async def wait_until_utcms_up(proxy_url: str, max_minutes: float, poll_seconds: int = 60) -> None:
    """Poll the UTCMS login page over HTTP until it answers 200."""
    from curl_cffi import requests as cc

    deadline = datetime.datetime.now() + datetime.timedelta(minutes=max_minutes)
    attempt = 0
    while datetime.datetime.now() < deadline:
        attempt += 1
        try:
            sess = cc.Session(impersonate="chrome120", proxies={"http": proxy_url, "https": proxy_url}, timeout=30)
            try:
                r = sess.get(LOGIN_URL, timeout=30)
            finally:
                sess.close()
            if r.status_code == 200:
                logger.info("utcms_up after %s attempts", attempt)
                return
            logger.info(
                "utcms_down attempt=%s status=%s len=%s",
                attempt,
                r.status_code,
                len(r.text or ""),
            )
        except Exception as exc:  # noqa: BLE001
            logger.info("utcms_poll_err attempt=%s err=%s", attempt, str(exc)[:80])
        await asyncio.sleep(poll_seconds)
    raise RuntimeError(f"UTCMS did not come back within {max_minutes} minutes")


async def check_form_over_http(login, username: str, password: str) -> dict:
    """Probe the waybill form page via the HTTP session (no Chromium).

    Returns {"status": int, "is_form": bool} — is_form is True when the
    response contains waybill form markers (200 only makes sense).
    """
    resp, _ = await login.fetch_authenticated(
        FORM_URL,
        username=username,
        password=password,
        max_attempts=3,
        backoff_seconds=5.0,
    )
    body = resp.text or ""
    form_markers = ("txtSenderFirstName", "senderSelectType", "btnGoLVL2", "بارنامه")
    is_form = resp.status_code == 200 and any(m in body for m in form_markers)
    return {"status": resp.status_code, "is_form": is_form, "len": len(body)}


async def submit_via_playwright(
    proxy_url: str, username: str, password: str, payload: dict
) -> dict:
    """Inject HTTP-obtained cookies into a Playwright context and run the
    real 5-step waybill form (EnhancedWaybillManager)."""
    from app.automation.browser import browser_manager
    from app.automation.utcms_http_login import UtcmsHttpLogin
    from app.automation.waybill_enhanced import EnhancedWaybillManager

    login = UtcmsHttpLogin(proxy_url=proxy_url)
    res = await login.authenticate(username, password)
    if not res.success:
        raise RuntimeError(f"login failed: {res.error}")

    session_id, ctx = await browser_manager.create_context(
        proxy_dict={"server": proxy_url} if proxy_url else None
    )
    try:
        ok = await login.inject_cookies_into_context_async(res, ctx)
        logger.info("cookies injected=%s count=%s", ok, len(res.cookies))
        if not ok:
            raise RuntimeError("cookie injection failed")
        page = await ctx.new_page()
        await page.goto("https://barname.utcms.ir/Barname/Home", timeout=60000)
        await page.wait_for_timeout(2000)
        body = await page.content()
        logged = "خروج" in body or "logout" in body.lower()
        logger.info("home_logged_in=%s", logged)
        if not logged:
            raise RuntimeError("Playwright session not authenticated after injection")

        mgr = EnhancedWaybillManager(page, ctx)
        t0 = time.monotonic()
        result = await mgr.create_waybill_with_map(payload, dry_run=False, job_id="e2e-manual")
        result["elapsed_seconds"] = round(time.monotonic() - t0, 1)
        return result
    finally:
        try:
            await browser_manager.close_context(session_id)
        except Exception:  # noqa: BLE001
            pass


async def main() -> int:
    parser = argparse.ArgumentParser(description="E2E waybill submission with UTCMS recovery")
    parser.add_argument("--dry-run", action="store_true", help="only verify login+form reachability")
    parser.add_argument("--wait-min", type=float, default=60.0, help="max minutes to wait for UTCMS")
    parser.add_argument("--poll-sec", type=int, default=60, help="poll interval seconds")
    args = parser.parse_args()

    from sqlmodel import select

    from app.auth_multitenant import decrypt_driver_password
    from app.automation.utcms_http_login import UtcmsHttpLogin
    from app.automation.worker_proxy import get_worker_proxy_url
    from app.core.database import async_session_factory
    from app.models_multitenant import Driver

    proxy_url = get_worker_proxy_url()
    logger.info("proxy=%s wait_min=%.0f dry_run=%s", proxy_url, args.wait_min, args.dry_run)

    username = password = None
    async with async_session_factory() as s:
        for d in (await s.exec(select(Driver))).all():
            if d.status == "active" and d.utcms_username:
                username = d.utcms_username
                password = decrypt_driver_password(d.utcms_password_encrypted)
                break
    if not username or not password:
        logger.error("no active driver with utcms credentials in DB")
        return 2
    logger.info("creds loaded user=***%s pw_len=%d", username[-4:], len(password))

    # 1) Wait for UTCMS to come back (the current 408 outage).
    await wait_until_utcms_up(proxy_url, max_minutes=args.wait_min, poll_seconds=args.poll_sec)

    # 2) HTTP login.
    login = UtcmsHttpLogin(proxy_url=proxy_url)
    res = await login.authenticate(username, password)
    if not res.success:
        logger.error("login failed: %s", res.error)
        return 3
    logger.info("login ok cookies=%s", [c["name"] for c in res.cookies])

    # 3) Verify the form is reachable over HTTP before touching Chromium.
    probe = await check_form_over_http(login, username, password)
    logger.info("form probe: %s", probe)
    if probe["status"] != 200:
        logger.error("waybill form not reachable yet (status=%s) — retry later", probe["status"])
        return 4
    if not probe["is_form"]:
        logger.warning("form returned 200 but no form markers found — page may have changed")

    if args.dry_run:
        logger.info("DRY-RUN: login+form OK — skipping actual submission")
        return 0

    # 4) Real submission through Playwright with injected cookies.
    logger.info("starting real submission ...")
    result = await submit_via_playwright(proxy_url, username, password, PAYLOAD)
    print("=== WAYBILL RESULT ===")
    print(json.dumps(result, ensure_ascii=False, indent=2)[:3000])
    return 0


if __name__ == "__main__":
    try:
        sys.exit(asyncio.run(main()))
    except KeyboardInterrupt:
        sys.exit(130)

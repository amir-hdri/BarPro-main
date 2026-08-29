#!/usr/bin/env python3
"""Drive ONE real UTCMS waybill through the full 5-step form.

Defaults to dry_run=True, which runs every stage -- including the stage-06
runtime XHR (KalaSearch / Captcha / fillStates) that the thread-local curl
handle bug was breaking -- and stops before the final submit POST.

    python /app/scripts/run_waybill_job21.py            # dry run, no submit
    python /app/scripts/run_waybill_job21.py --live      # ONE real submit

``--live`` is deliberately awkward: it submits exactly once, with no retry and
no fallback, and must never be used on a job that already has a document_id.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import sys
import time

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(message)s")
logger = logging.getLogger("waybill_job21")

# Real waybill data supplied by the operator.  No placeholder values: UTCMS
# fields must never be filled with invented data.
PAYLOAD = {
    "sender": {
        "name": "بهروز بغلانی",
        "phone": "09184110414",
        "national_code": "",
        "address": "",
    },
    "receiver": {
        "name": "علی کوچکی",
        "phone": "09379944450",
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
        "type": "سیمان",
        "packaging": "کیسه",
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


async def _load_credentials() -> tuple[str, str, dict[str, str]]:
    """Pick the driver the payload is actually about -- not just the first active one.

    Run 3 (2026-08-28) logged in as a different driver's UTCMS account than the
    one named in the payload, so the tajmi fleet list it saw belonged to someone
    else and no driver in it could ever match.  The account must be the one whose
    fleet contains this plate, so the driver is matched on the payload's mobile
    (the identity key the operator supplies) and then on the name.
    """
    from sqlmodel import select

    from app.auth_multitenant import decrypt_driver_password
    from app.core.database import async_session_factory
    from app.models_multitenant import Driver

    def _digits(value: str) -> str:
        return "".join(ch for ch in str(value or "") if ch.isdigit())

    wanted_phone = _digits(PAYLOAD["vehicle"].get("driver_phone", ""))
    wanted_name = str(PAYLOAD["vehicle"].get("driver_name", "") or "").strip()

    async with async_session_factory() as s:
        candidates = [d for d in (await s.exec(select(Driver))).all() if d.status == "active" and d.utcms_username]
        chosen = None
        for driver in candidates:
            if wanted_phone and _digits(driver.phone) == wanted_phone:
                chosen = driver
                break
        if chosen is None and wanted_name:
            for driver in candidates:
                if str(driver.full_name or "").strip() == wanted_name:
                    chosen = driver
                    break
        if chosen is None:
            raise RuntimeError(
                "the payload's driver has no active UTCMS account in the database; "
                "registering under a different driver's account is never correct"
            )
        # The driver's identity comes from the database record, never from a
        # literal in this file: the tajmi driver list is matched on the national
        # code first, and inventing one would put a stranger on the waybill.
        identity = {
            "driver_national_code": str(chosen.driver_national_code or ""),
            "driver_name": str(chosen.full_name or ""),
            "driver_phone": str(chosen.phone or ""),
            "plate": str(getattr(chosen, "plate_number", "") or ""),
        }
        return chosen.utcms_username, decrypt_driver_password(chosen.utcms_password_encrypted), identity


async def run(live: bool, job_id: str) -> dict:
    from app.automation.browser import browser_manager
    from app.automation.utcms_http_login import UtcmsHttpLogin
    from app.automation.waybill_enhanced import EnhancedWaybillManager
    from app.automation.worker_proxy import get_worker_proxy_url

    proxy_url = get_worker_proxy_url()
    username, password, identity = await _load_credentials()
    for key, value in identity.items():
        if not value:
            continue
        current = PAYLOAD["vehicle"].get(key) or ""
        if current and current != value:
            logger.info("vehicle.%s: keeping operator value, db has a different one", key)
            continue
        PAYLOAD["vehicle"][key] = value
    if not PAYLOAD["vehicle"]["driver_national_code"]:
        raise RuntimeError("driver national code is unknown; the tajmi driver list cannot be matched")
    logger.info("proxy=%s user=***%s live=%s", proxy_url, username[-4:], live)

    login = UtcmsHttpLogin(proxy_url=proxy_url)
    res = await login.authenticate(username, password)
    if not res.success:
        raise RuntimeError(f"HTTP login failed: {res.error}")
    logger.info("login ok cookies=%s", [c["name"] for c in res.cookies])

    session_id, ctx = await browser_manager.create_context(proxy_dict={"server": proxy_url} if proxy_url else None)
    try:
        if not await login.inject_cookies_into_context_async(res, ctx):
            raise RuntimeError("cookie injection into Playwright failed")
        page = await ctx.new_page()

        # Every symptom so far -- no cargo autocomplete, no fillBoxType, no
        # GETUserFleetListTajmi, no plate change handler -- points at the form's
        # own script failing to initialise rather than at four separate bugs.
        # Surface the page's JS errors so that can be confirmed or ruled out.
        page.on(
            "pageerror",
            lambda exc: logger.error("pageerror %s", str(exc).replace("\n", " | ")[:600]),
        )
        page.on(
            "console",
            lambda msg: (
                logger.warning("console[%s] %s", msg.type, msg.text.replace("\n", " | ")[:400])
                if msg.type in ("error", "warning")
                else None
            ),
        )
        page.on(
            "requestfailed",
            lambda req: logger.warning("requestfailed %s %s", req.resource_type, req.url[:160]),
        )

        # The bridge is what carries the authenticated curl session -- and, with
        # use_thread_local_curl=False, its warm TLS connection -- into the form.
        from app.automation.http_browser_bridge import ensure_utcms_http_browser_bridge

        bridge = await ensure_utcms_http_browser_bridge(page)
        if bridge is not None:
            await bridge.adopt_authenticated_session(login.take_authenticated_session(), res.cookies)

        await page.goto("https://barname.utcms.ir/Barname/Home", timeout=90000)
        await page.wait_for_timeout(2000)
        body = await page.content()
        if not ("خروج" in body or "logout" in body.lower()):
            raise RuntimeError("Playwright session is not authenticated after injection")
        logger.info("home authenticated")

        mgr = EnhancedWaybillManager(page, ctx)
        t0 = time.monotonic()
        result = await mgr.create_waybill_with_map(PAYLOAD, dry_run=not live, job_id=job_id)
        result["elapsed_seconds"] = round(time.monotonic() - t0, 1)
        return result
    finally:
        try:
            await browser_manager.close_context(session_id)
        except Exception:  # noqa: BLE001
            logger.debug("context close failed", exc_info=True)


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--live", action="store_true", help="perform the ONE real submit")
    p.add_argument("--job-id", default="job21-dryrun")
    args = p.parse_args()

    try:
        result = asyncio.run(run(args.live, args.job_id))
    except Exception as exc:  # noqa: BLE001
        logger.error("run failed: %s", exc, exc_info=True)
        return 1
    print("=== WAYBILL RESULT ===")
    print(json.dumps(result, ensure_ascii=False, indent=2)[:6000])
    return 0


if __name__ == "__main__":
    sys.exit(main())

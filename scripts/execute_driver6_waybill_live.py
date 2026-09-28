"""Execute a live waybill for Driver 6 (محمود کریمی) on barname.utcms.ir.

Monitors every step:
1. Driver authentication and token acquisition.
2. RouteAuthority distance & polyline calculation.
3. Waybill document issuance on UTCMS (InsertDocumentHagigiV3).
4. Tracking code extraction.
5. Immediate RegisterStartOfShipping with origin coordinates.
6. Verification against UTCMS get_document.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import sys
import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

if Path("/app/app").exists():
    PROJECT_ROOT = Path("/app")
else:
    PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from sqlmodel import select

from app.auth_multitenant import decrypt_driver_password
from app.automation.waybill_bot_multitenant import WaybillAutomationBot
from app.automation.worker_proxy import get_worker_proxy_url
from app.core.config import utcms_config
from app.core.database import async_session_factory
from app.models_multitenant import Driver, DriverPlate, TaskStatus, WaybillJob
from app.services.route_authority import resolve_route

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger("live_waybill_driver6")


def _utcnow_naive() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


async def main() -> None:
    logger.info("==================================================================")
    logger.info("   🚀 LIVE WAYBILL REGISTRATION & MONITORING — DRIVER 6          ")
    logger.info("==================================================================")

    proxy_url = get_worker_proxy_url()
    logger.info("Proxy Egress: %s", proxy_url)
    os.environ["ALLOW_LIVE_SUBMIT"] = "true"
    utcms_config.ALLOW_LIVE_SUBMIT = True

    async with async_session_factory() as session:
        driver = await session.get(Driver, 6)
        if not driver:
            raise RuntimeError("Driver 6 not found in DB")
        client_id = driver.client_id
        username = driver.utcms_username or driver.driver_national_code
        nat_code = driver.driver_national_code
        enc_pass = driver.utcms_password_encrypted
        password = decrypt_driver_password(enc_pass)

        # Get active plate
        plate_stmt = select(DriverPlate).where(
            (DriverPlate.driver_id == driver.id) & (DriverPlate.status == "active")
        )
        plate_obj = (await session.exec(plate_stmt)).first()
        plate_number = plate_obj.plate_number if plate_obj else "55ع322ایران36"

    logger.info("Driver: %s (NationalCode: %s)", driver.full_name, nat_code)
    logger.info("Plate: %s", plate_number)

    # Origin: Kashmar, Montazeri 25 (35.2415, 58.4655)
    # Destination: Kashmar, Moallem Blvd (35.2320, 58.4780)
    origin_lat = 35.2415
    origin_lng = 58.4655
    dest_lat = 35.2320
    dest_lng = 58.4780

    logger.info("Computing authoritative route from RouteAuthority...")
    route_plan = await resolve_route(
        origin_lat=origin_lat,
        origin_lng=origin_lng,
        dest_lat=dest_lat,
        dest_lng=dest_lng,
    )
    logger.info(
        "Route resolved: distance=%.2f km, duration=%.1f s, source=%s, polyline_pts=%d",
        route_plan.get("distance_km", 0.0),
        route_plan.get("duration_s", 0.0),
        route_plan.get("source"),
        len(route_plan.get("points") or []),
    )

    now_tehran = datetime.now(ZoneInfo("Asia/Tehran"))
    current_day_start = now_tehran.strftime("%Y-%m-%dT%H:%M:%S")
    current_day_end = (now_tehran + timedelta(minutes=30)).strftime("%Y-%m-%dT%H:%M:%S")

    job_id = f"job_live_{uuid.uuid4().hex[:12]}"
    payload = {
        "transport": "mobile",
        "allow_live_submit": True,
        "self_declared_time_of_start_shipment": current_day_start,
        "estimated_time_of_end_shipment": current_day_end,
        "sender": {
            "first_name": "جواد",
            "last_name": "عزتی",
            "phone": "09123150212",
            "national_code": "0084575948",
            "postal_code": "9671111111",
        },
        "receiver": {
            "first_name": "نیما",
            "last_name": "هادی",
            "phone": "09123150212",
            "national_code": "0012345679",
            "postal_code": "9672222222",
        },
        "origin": {
            "province": "خراسان رضوی",
            "city": "کاشمر",
            "address": "کاشمر، خیابان منتظری ۲۵",
            "postal_code": "9671111111",
            "lat": origin_lat,
            "lon": origin_lng,
            "coordinates": {"lat": origin_lat, "lng": origin_lng},
        },
        "destination": {
            "province": "خراسان رضوی",
            "city": "کاشمر",
            "address": "کاشمر، بلوار معلم",
            "postal_code": "9672222222",
            "lat": dest_lat,
            "lon": dest_lng,
            "coordinates": {"lat": dest_lat, "lng": dest_lng},
        },
        "cargo": {
            "type": "مصالح",
            "packaging": "کیسه",
            "weight": 20,
            "items": [
                {
                    "product_id": 10956,
                    "pack_type_id": 18074,
                    "weight": 20,
                    "count": 1,
                    "description": "مصالح ساختمانی",
                }
            ],
            "value": 35000000,
        },
        "vehicle": {
            "driver_national_code": nat_code,
            "driver_phone": "09044049942",
            "plate": plate_number,
            "tag_type": 1,
            "t1": 36,
            "t2": 55,
            "t3": 21,
            "t4": 322,
            "capacity": 20,
            "type": "تریلی کشنده",
            "have_certificate": True,
            "have_3rd_insurance": True,
        },
        "financial": {
            "cost": 4000000,
            "fare": 4000000,
            "bearing_cost": 100000,
            "pre_rent": 1000000,
            "post_rent": 3000000,
        },
        "insurance": {"have_insurance": True, "cover": 35000000},
        "shipping_options": {"send_sms": True, "fuel_type": 1},
        "route_snapshot": route_plan,
    }

    logger.info("Persisting WaybillJob (%s) to PostgreSQL...", job_id)
    async with async_session_factory() as session:
        job = WaybillJob(
            job_id=job_id,
            idempotency_key=f"idem_{uuid.uuid4().hex[:16]}",
            client_id=client_id,
            driver_id=driver.id,
            status=TaskStatus.RUNNING.value,
            payload_json=payload,
            attempt_count=1,
            started_at=_utcnow_naive(),
            created_at=_utcnow_naive(),
            updated_at=_utcnow_naive(),
            mutation_status="intent_persisted",
            mutation_at=_utcnow_naive(),
        )
        session.add(job)
        await session.commit()
        await session.refresh(job)
        db_job_id = job.id
    logger.info("✅ WaybillJob created with DB ID = %d", db_job_id)

    logger.info("Executing WaybillAutomationBot (Mobile Pipeline)...")
    bot = WaybillAutomationBot(page=None, context=None, proxy_url=proxy_url)
    bot_result = await bot.execute_waybill_job(
        username=username,
        password=password,
        payload=payload,
        job_id=job_id,
        client_id=client_id,
        allow_live_submit=True,
        proxy_url=proxy_url,
    )

    logger.info(
        "Bot Execution Completed:\n%s",
        json.dumps(bot_result, ensure_ascii=False, indent=2),
    )

    exec_status = bot_result.get("status")
    doc_id = bot_result.get("document_id")
    tracking_code = bot_result.get("tracking_code")

    if exec_status == TaskStatus.SUCCESS.value and tracking_code:
        logger.info("==================================================================")
        logger.info("  🎉 WAYBILL SUCCESSFULLY ISSUED & CONFIRMED ON UTCMS!            ")
        logger.info("  📄 Document ID:   %s", doc_id)
        logger.info("  🔢 Tracking Code: %s", tracking_code)
        logger.info("  📍 Origin Anchor: (%s, %s)", origin_lat, origin_lng)
        logger.info("  📍 Dest Anchor:   (%s, %s)", dest_lat, dest_lng)
        start_ship_result = bot_result.get("result", {}).get("start_shipping")
        logger.info("  🚚 Start Shipping Result: %s", start_ship_result)
        logger.info("==================================================================")
    else:
        logger.warning(
            "Waybill execution outcome: status=%s, tracking_code=%s, error=%s",
            exec_status,
            tracking_code,
            bot_result.get("error"),
        )


if __name__ == "__main__":
    asyncio.run(main())

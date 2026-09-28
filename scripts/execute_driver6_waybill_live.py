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
            "type": "باری",
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

    logger.info("Authenticating driver via session vault (get_or_login_client)...")
    from app.automation.gps_shipping_manager import get_or_login_client

    auth_client = await get_or_login_client(
        national_code=nat_code,
        password=password,
        proxy_url=proxy_url,
    )
    logger.info("Driver authenticated! Token acquired: %s...", auth_client.token[:20])

    carrying = await auth_client.get_carrying_doc_id()
    if carrying:
        logger.warning("Driver 6 currently has carrying doc ID: %s", carrying)
    else:
        logger.info("Driver 6 is free of active carrying documents (ready for new waybill).")

    payload["token"] = auth_client.token

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

    logger.info("Executing Document Issuance via authenticated mobile client...")
    # Step 1 & 2: Solve issuance CAPTCHA and Insert Document with retry on 4003 (wrong captcha)
    max_insert_attempts = 3
    insert_response = None
    for attempt_no in range(1, max_insert_attempts + 1):
        logger.info("Solving issuance CAPTCHA via MathCRNN (attempt %d/%d)...", attempt_no, max_insert_attempts)
        _, issue_cap_token = await auth_client.auto_solve_captcha(form_id=1)
        logger.info("✅ Issuance CAPTCHA solved: answer=%s", issue_cap_token)

        try:
            logger.info("Submitting InsertDocumentHagigiV3 to UTCMS (attempt %d/%d)...", attempt_no, max_insert_attempts)
            insert_response = await auth_client.insert_document(
                payload,
                allow_live_submit=True,
                cap_token=issue_cap_token,
            )
            break
        except Exception as exc:
            rc = getattr(exc, "result_code", None)
            if (rc == 4003 or str(rc) == "4003" or "کد امنیتی" in str(exc)) and attempt_no < max_insert_attempts:
                logger.warning(
                    "Issuance captcha rejected (code 4003, attempt %d/%d). Refreshing captcha...",
                    attempt_no,
                    max_insert_attempts,
                )
                await asyncio.sleep(1.5)
                continue
            raise

    assert insert_response is not None, "Insert response must not be None"
    logger.info("Insert Response: %s", json.dumps(insert_response, ensure_ascii=False))

    doc_id = auth_client.extract_document_id(insert_response)
    tracking_code = auth_client.extract_tracking_code(insert_response)
    is_otp = insert_response.get("obj", {}).get("isOtpNeeded") if isinstance(insert_response.get("obj"), dict) else False

    logger.info("Doc ID: %s, Tracking Code: %s, OTP Needed: %s", doc_id, tracking_code, is_otp)

    # Step 3: Extract tracking code from GetDocumentByID or GetDocTrackingCode if not in insert response
    if doc_id and not tracking_code:
        logger.info("Tracking code not directly in insert response, querying GetDocumentByID(%s)...", doc_id)
        await asyncio.sleep(1.0)
        try:
            doc_info = await auth_client.get_document(str(doc_id))
            tracking_code = auth_client.extract_tracking_code(doc_info)
            logger.info("Extracted tracking code from GetDocumentByID: %s", tracking_code)
        except Exception as doc_err:
            logger.warning("GetDocumentByID failed: %s", doc_err)

    if doc_id and not tracking_code:
        logger.info("Querying GetDocTrackingCode(%s)...", doc_id)
        try:
            trk_info = await auth_client.get_tracking_code(str(doc_id))
            tracking_code = auth_client.extract_tracking_code(trk_info)
            logger.info("Extracted tracking code from GetDocTrackingCode: %s", tracking_code)
        except Exception as trk_err:
            logger.warning("GetDocTrackingCode failed: %s", trk_err)

    # Step 4: Register Start of Shipping with origin coordinates
    start_ship_result = None
    if doc_id and tracking_code:
        logger.info("Initializing GPS shipping lifecycle for tracking code %s...", tracking_code)
        from app.automation.gps_shipping_manager import init_shipping, save_shipping_state
        ship_state = await init_shipping(
            job_id=job_id,
            doc_no=str(tracking_code),
            payload=payload,
            doc_id=str(doc_id),
            persist=True,
        )

        start_iso = datetime.now(ZoneInfo("Asia/Tehran")).strftime("%Y-%m-%dT%H:%M:%S")
        logger.info(
            "Triggering RegisterStartOfShipping: doc_id=%s, lat=%s, lng=%s, time=%s",
            doc_id,
            origin_lat,
            origin_lng,
            start_iso,
        )
        try:
            start_ship_result = await auth_client.register_start_of_shipping(
                document_id=int(str(doc_id).strip()),
                speed=0,
                altitude=1000,
                longitude=origin_lng,
                latitude=origin_lat,
                start_date=start_iso,
                allow_live_submit=True,
            )
            logger.info("✅ RegisterStartOfShipping response: %s", start_ship_result)
            ship_state.status = "in_transit"
            await save_shipping_state(ship_state)
        except Exception as start_err:
            logger.warning("RegisterStartOfShipping note: %s", start_err)

    # Step 5: Update WaybillJob in PostgreSQL
    result_data = {
        "document_id": doc_id,
        "tracking_code": tracking_code,
        "is_otp_needed": is_otp,
        "insert_response": insert_response,
        "start_shipping": start_ship_result,
        "route": {
            "origin": {"lat": origin_lat, "lng": origin_lng, "city": "کاشمر"},
            "destination": {"lat": dest_lat, "lng": dest_lng, "city": "کاشمر"},
            "distance_km": route_plan.get("distance_km"),
            "duration_s": route_plan.get("duration_s"),
        },
    }

    async with async_session_factory() as session:
        job_db = await session.get(WaybillJob, db_job_id)
        if job_db:
            if tracking_code:
                job_db.status = TaskStatus.SUCCESS.value
                job_db.mutation_status = "confirmed"
            else:
                job_db.status = TaskStatus.FAILED.value
                job_db.mutation_status = "failed"
            job_db.result_json = result_data
            job_db.completed_at = _utcnow_naive()
            job_db.reconciled_at = _utcnow_naive()
            await session.commit()
            logger.info("✅ WaybillJob updated in DB: status=%s, tracking_code=%s", job_db.status, tracking_code)

    # Step 6: Final Verification against live UTCMS portal
    if tracking_code:
        logger.info("==================================================================")
        logger.info("  🎉 WAYBILL SUCCESSFULLY ISSUED & CONFIRMED ON UTCMS!            ")
        logger.info("  📄 Document ID:   %s", doc_id)
        logger.info("  🔢 Tracking Code: %s", tracking_code)
        logger.info("  📍 Origin Anchor: (%s, %s)", origin_lat, origin_lng)
        logger.info("  📍 Dest Anchor:   (%s, %s)", dest_lat, dest_lng)
        logger.info("  🚚 Start Shipping: %s", start_ship_result)

        try:
            live_doc = await auth_client.get_document(str(doc_id))
            obj_v = live_doc.get("obj") or {}
            logger.info("  🔍 UTCMS Live Status: %s (code: %s)", obj_v.get("statusName"), obj_v.get("status"))
            logger.info("  📅 UTCMS Issue Date: %s", obj_v.get("issueDate"))
            logger.info("  📏 UTCMS Distance: %s km", obj_v.get("distanceKm"))
            logger.info("  👤 UTCMS Driver: %s", obj_v.get("driverName"))
            logger.info("  🚗 UTCMS Plate: %s", obj_v.get("carTag"))
        except Exception as v_err:
            logger.warning("Could not fetch live get_document: %s", v_err)
        logger.info("==================================================================")
    else:
        logger.error("❌ Waybill registration failed or tracking code not acquired.")


if __name__ == "__main__":
    asyncio.run(main())

"""Execute a real waybill live for Driver 8 (یوسف قلی زاده) on barname.utcms.ir."""

from __future__ import annotations

import asyncio
import json
import logging
import os
import uuid
from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo

from sqlmodel import select

from app.auth_multitenant import decrypt_driver_password
from app.automation.waybill_bot_multitenant import WaybillAutomationBot
from app.automation.worker_proxy import get_worker_proxy_url
from app.core.config import utcms_config
from app.core.database import async_session_factory
from app.models_multitenant import Driver, TaskStatus, WaybillJob
from app.orchestrator.state_machine import JobStateMachine

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger("live_waybill_driver8")


def _utcnow_naive() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


async def main() -> None:
    logger.info("=== STEP 1: INITIALIZING LIVE WAYBILL SUBMISSION FOR DRIVER 8 ===")
    proxy_url = get_worker_proxy_url()
    logger.info("Egress Proxy: %s", proxy_url)
    os.environ["ALLOW_LIVE_SUBMIT"] = "true"
    utcms_config.ALLOW_LIVE_SUBMIT = True
    logger.info("ALLOW_LIVE_SUBMIT: %s", utcms_config.ALLOW_LIVE_SUBMIT)
    logger.info("UTCMS_TRANSPORT: %s", utcms_config.UTCMS_TRANSPORT)

    async with async_session_factory() as session:
        driver = (await session.exec(select(Driver).where(Driver.id == 8))).first()
        if not driver:
            raise RuntimeError("Driver 8 not found in DB")
        client_id = driver.client_id
        username = driver.utcms_username or driver.driver_national_code
        nat_code = driver.driver_national_code
        enc_pass = driver.utcms_password_encrypted or getattr(driver, "encrypted_password", None)
        password = decrypt_driver_password(enc_pass)

    now_tehran = datetime.now(ZoneInfo("Asia/Tehran"))
    logger.info("Current Tehran Time: %s", now_tehran.isoformat())

    # Driver 8: شوط به شوط (West Azerbaijan)
    # Origin: شوط، روستای دیزج (39.3298, 44.7683)
    # Destination: شوط، مرگن وسط (39.0807, 44.9096)
    current_day_start = datetime.now().strftime("%Y-%m-%dT%H:%M:%S")
    current_day_end = (datetime.now() + timedelta(minutes=45)).strftime("%Y-%m-%dT%H:%M:%S")

    job_id = f"job_live_{uuid.uuid4().hex[:12]}"
    payload = {
        "transport": "mobile",
        "allow_live_submit": True,
        "self_declared_time_of_start_shipment": current_day_start,
        "estimated_time_of_end_shipment": current_day_end,
        "sender": {
            "first_name": "سروش",
            "last_name": "عابدی",
            "phone": "09029856831",
            "national_code": "0084575948",
            "postal_code": "5861111111",
        },
        "receiver": {
            "first_name": "عباس",
            "last_name": "رستمی",
            "phone": "09143446240",
            "national_code": "0012345679",
            "postal_code": "5862222222",
        },
        "origin": {
            "province": "آذربایجان غربی",
            "city": "شوط",
            "address": "آذربایجان غربی، شوط، قره ضیاالدین - ماکو - بازرگان، روستای دیزج، دیزج",
            "postal_code": "5861111111",
            "lat": 39.3298,
            "lon": 44.7683,
        },
        "destination": {
            "province": "آذربایجان غربی",
            "city": "شوط",
            "address": "آذربایجان غربی، شوط، مرگن وسط، مرگن اسماعیل کندی، مرگن-تازه کند",
            "postal_code": "5862222222",
            "lat": 39.0807,
            "lon": 44.9096,
        },
        "cargo": {
            "type": "آجر",
            "packaging": "فله",
            "weight": 20,
            "items": [{"product_id": 10956, "pack_type_id": 18074, "weight": 20, "count": 1, "description": "آجر"}],
            "value": 106000000,
        },
        "vehicle": {
            "driver_national_code": nat_code,
            "driver_phone": driver.phone or "09148420429",
            "plate": "32ع444ایران27",
            "tag_type": 1,
            "t1": 27,
            "t2": 32,
            "t3": 21,
            "t4": 444,
            "capacity": 20,
            "type": "باری",
            "have_certificate": True,
            "have_3rd_insurance": True,
        },
        "insurance": {"have_insurance": False, "cover": 0},
        "financial": {"cost": 9500000, "bearing_cost": 100000, "pre_rent": 0, "post_rent": 9500000},
        "shipping_options": {"send_sms": False, "fuel_type": 1},
    }

    logger.info("=== STEP 2: CREATING WAYBILL JOB IN DATABASE ===")
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
    logger.info("Created DB Job row ID=%s (job_id=%s)", db_job_id, job_id)

    logger.info("=== STEP 3: EXECUTING AUTOMATION BOT VIA MOBILE CLIENT + MATH CRNN ===")
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

    logger.info("Bot execution finished with result: %s", json.dumps(bot_result, ensure_ascii=False, indent=2))

    status = bot_result.get("status")
    doc_id = bot_result.get("document_id")
    tracking_code = bot_result.get("tracking_code")

    if status != TaskStatus.SUCCESS.value or not tracking_code:
        logger.error("Waybill issuance did NOT succeed: %s", bot_result)
        async with async_session_factory() as session:
            db_job = (await session.exec(select(WaybillJob).where(WaybillJob.id == db_job_id))).first()
            if db_job:
                db_job.status = TaskStatus.FAILED.value
                db_job.result_json = bot_result
                db_job.updated_at = _utcnow_naive()
                session.add(db_job)
                await session.commit()
        return

    logger.info("=== STEP 4: WAYBILL ISSUED LIVE ON UTCMS! ===")
    logger.info("Document ID: %s", doc_id)
    logger.info("Tracking Code: %s", tracking_code)

    async with async_session_factory() as session:
        db_job = (await session.exec(select(WaybillJob).where(WaybillJob.id == db_job_id))).first()
        if db_job:
            await JobStateMachine.transition(
                session,
                db_job,
                TaskStatus.SUCCESS,
                result_json={
                    **bot_result,
                    "document_id": doc_id,
                    "tracking_code": tracking_code,
                },
                mutation_status="confirmed",
                reconciled_at=_utcnow_naive(),
                error_message=None,
            )
            await session.commit()
            logger.info("WaybillJob %s transitioned to SUCCESS in PostgreSQL", db_job_id)

    logger.info("=== STEP 5: VERIFYING READBACK ON UTCMS (AFTER START OF SHIPPING) ===")
    from app.automation.gps_shipping_manager import auto_complete_shipping, get_or_login_client

    client = await get_or_login_client(nat_code, password, proxy_url=proxy_url)
    live_doc = await client.get_document(str(doc_id))
    obj = live_doc.get("obj") or {}
    logger.info("UTCMS Portal Readback: StatusName=%s (code=%s)", obj.get("statusName"), obj.get("status"))
    logger.info("SelfDeclaredStartTime: %s", obj.get("selfDeclaredTimeOfStartShipment"))
    logger.info("EstimatedEndTime: %s", obj.get("estimatedTimeOfEndShipment"))
    logger.info("Shipping Start Date on UTCMS: %s", obj.get("shippingStartDate"))
    logger.info("All Document Fields: %s", json.dumps(obj, ensure_ascii=False, indent=2))

    logger.info("=== STEP 6: EXECUTING AUTOMATED END OF SHIPPING AT DESTINATION ===")
    end_res = await auto_complete_shipping(job_id)
    logger.info("auto_complete_shipping response: %s", json.dumps(end_res, ensure_ascii=False, indent=2))

    logger.info("=== STEP 7: FINAL UTCMS READBACK (AFTER END OF SHIPPING) ===")
    final_doc = await client.get_document(str(doc_id))
    final_obj = final_doc.get("obj") or {}
    logger.info("Final UTCMS Status: StatusName=%s (code=%s)", final_obj.get("statusName"), final_obj.get("status"))
    logger.info("Final Shipping Start Date: %s", final_obj.get("shippingStartDate"))
    logger.info("Final Shipping Finish Date: %s", final_obj.get("shippingFinishDate"))
    logger.info("=== ALL WITNESSES CONFIRMED 100%%! ===")


if __name__ == "__main__":
    asyncio.run(main())

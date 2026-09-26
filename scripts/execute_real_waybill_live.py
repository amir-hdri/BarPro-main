"""Execute a real waybill live on barname.utcms.ir using the hardened mobile pipeline."""

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
logger = logging.getLogger("live_waybill_submission")


def _utcnow_naive() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


async def main() -> None:
    logger.info("=== STEP 1: INITIALIZING LIVE WAYBILL SUBMISSION ===")
    proxy_url = get_worker_proxy_url()
    logger.info("Egress Proxy: %s", proxy_url)
    os.environ["ALLOW_LIVE_SUBMIT"] = "true"
    utcms_config.ALLOW_LIVE_SUBMIT = True
    logger.info("ALLOW_LIVE_SUBMIT: %s", utcms_config.ALLOW_LIVE_SUBMIT)
    logger.info("UTCMS_TRANSPORT: %s", utcms_config.UTCMS_TRANSPORT)

    async with async_session_factory() as session:
        driver = (await session.exec(select(Driver).where(Driver.id == 7))).first()
        if not driver:
            raise RuntimeError("Driver 7 not found in DB")
        client_id = driver.client_id
        username = driver.utcms_username
        nat_code = driver.driver_national_code
        enc_pass = driver.utcms_password_encrypted or getattr(driver, "encrypted_password", None)
        password = decrypt_driver_password(enc_pass)

    now_tehran = datetime.now(ZoneInfo("Asia/Tehran"))
    logger.info("Current Tehran Time: %s", now_tehran.isoformat())

    # Origin: Taleqan Mir (36.2611, 50.4423)
    # Destination: Taleqan Keshrud (36.1696, 50.6119)
    current_day_start = datetime.now().strftime("%Y-%m-%dT%H:%M:%S")
    current_day_end = (datetime.now() + timedelta(minutes=50)).strftime("%Y-%m-%dT%H:%M:%S")

    job_id = f"job_live_{uuid.uuid4().hex[:12]}"
    payload = {
        "transport": "mobile",
        "allow_live_submit": True,
        "self_declared_time_of_start_shipment": current_day_start,
        "estimated_time_of_end_shipment": current_day_end,
        "sender": {
            "first_name": "علی",
            "last_name": "موسوی",
            "phone": "09120000000",
            "national_code": "0084575948",
            "postal_code": "3361111111",
        },
        "receiver": {
            "first_name": "حسین",
            "last_name": "احمدی",
            "phone": "09120000000",
            "national_code": "0012345679",
            "postal_code": "3362222222",
        },
        "origin": {
            "province": "البرز",
            "city": "طالقان",
            "address": "طالقان، میر، جاده انجیلاق کلارود اسفاران، پرگه",
            "postal_code": "3361111111",
            "lat": 36.2611,
            "lon": 50.4423,
        },
        "destination": {
            "province": "البرز",
            "city": "طالقان",
            "address": "طالقان، کشرود، مسیر اختصاصی سد، جاده نسا سفلی",
            "postal_code": "3362222222",
            "lat": 36.1696,
            "lon": 50.6119,
        },
        "cargo": {
            "type": "آجر",
            "packaging": "فله",
            "weight": 20,
            "items": [{"product_id": 10956, "pack_type_id": 18074, "weight": 20, "count": 1, "description": "آجر"}],
            "value": 35000000,
        },
        "vehicle": {
            "driver_national_code": nat_code,
            "driver_phone": "09123612956",
            "plate": "23ع965ایران78",
            "tag_type": 1,
            "t1": 78,
            "t2": 23,
            "t3": 21,
            "t4": 965,
            "capacity": 20,
            "type": "باری",
            "have_certificate": True,
            "have_3rd_insurance": True,
        },
        "insurance": {"have_insurance": True, "cover": 35000000},
        "financial": {"cost": 5000000, "bearing_cost": 100000, "pre_rent": 1000000, "post_rent": 4000000},
        "shipping_options": {"send_sms": True, "fuel_type": 1},
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
        logger.error("Waybill execution did not produce confirmed tracking code: status=%s, doc_id=%s", status, doc_id)
        async with async_session_factory() as session:
            job = (await session.exec(select(WaybillJob).where(WaybillJob.id == db_job_id))).first()
            if job:
                JobStateMachine.transition(
                    session,
                    job,
                    TaskStatus.FAILED.value if status == TaskStatus.FAILED.value else TaskStatus.NEEDS_REVIEW.value,
                    last_error=bot_result.get("error") or "No tracking code returned",
                    finished_at=_utcnow_naive(),
                )
                await session.commit()
        raise RuntimeError(f"Waybill submission failed: {bot_result.get('error')}")

    logger.info("=== STEP 4: RECONCILING 3 WITNESSES ===")
    logger.info("Witness 1 (API Response): Document ID = %s", doc_id)
    logger.info("Witness 2 (Tracking Code / DocNo): %s", tracking_code)

    # Witness 3: Verify directly against UTCMS via GetDocumentByID
    from app.automation.gps_shipping_manager import get_or_login_client

    client = await get_or_login_client(nat_code, password, proxy_url=proxy_url)
    utcms_doc = await client.get_document(str(doc_id))
    obj = utcms_doc.get("obj") or {}
    live_status_name = obj.get("statusName")
    live_doc_no = str(obj.get("docNo") or "")

    logger.info("Witness 3 (UTCMS Portal Readback):")
    logger.info("  Status Name: %s (code: %s)", live_status_name, obj.get("status"))
    logger.info("  DocNo: %s", live_doc_no)
    logger.info("  Driver: %s", obj.get("driverMobile"))

    assert live_doc_no == str(tracking_code), f"Mismatch: live_doc_no {live_doc_no} != tracking {tracking_code}"

    # Update Job in PostgreSQL to confirmed success
    async with async_session_factory() as session:
        job = (await session.exec(select(WaybillJob).where(WaybillJob.id == db_job_id))).first()
        if job:
            await JobStateMachine.transition(
                session,
                job,
                TaskStatus.SUCCESS,
                mutation_status="confirmed",
                reconciled_at=_utcnow_naive(),
                finished_at=_utcnow_naive(),
                result_json={
                    "tracking_code": str(tracking_code),
                    "document_id": str(doc_id),
                    "status_name": live_status_name,
                    "transport": "mobile",
                    "solver": "MathCRNN_offline",
                    "reconciled_at": _utcnow_naive().isoformat(),
                },
            )
            await session.commit()

    logger.info("=== STEP 6: EXECUTING AUTOMATED END OF SHIPPING AT DESTINATION ===")
    from app.automation.gps_shipping_manager import auto_complete_shipping

    end_res = await auto_complete_shipping(job_id, force=True)
    logger.info("auto_complete_shipping response: %s", json.dumps(end_res, ensure_ascii=False, indent=2))

    logger.info("=== STEP 7: FINAL UTCMS READBACK (AFTER END OF SHIPPING) ===")
    final_doc = await client.get_document(str(doc_id))
    final_obj = final_doc.get("obj") or {}
    logger.info("Final UTCMS Status: StatusName=%s (code=%s)", final_obj.get("statusName"), final_obj.get("status"))
    logger.info("Final Shipping Start Date: %s", final_obj.get("shippingStartDate"))
    logger.info("Final Shipping Finish Date: %s", final_obj.get("shippingFinishDate"))

    logger.info("=== SUCCESS! WAYBILL OFFICIALLY ISSUED AND FULLY RECONCILED ===")
    print("------------------------------------------------------------")
    print(f"DOCUMENT ID:    {doc_id}")
    print(f"TRACKING CODE:  {tracking_code}")
    print(f"PORTAL STATUS:  {live_status_name}")
    print(f"DB JOB ID:      {db_job_id} ({job_id})")
    print("------------------------------------------------------------")


if __name__ == "__main__":
    asyncio.run(main())

#!/usr/bin/env python3
"""Submit two waybill jobs on the production server (inside barpro-backend).

Mirror of the established remote_submit_waybill.py pattern: upsert driver + plate
under client_id=3 (amir), build a WaybillMapRequest-style payload, create the
WaybillJob, and dispatch it through Celery.

Driver 1: Hussein Ashkhası (national_code 1719262438, UTCMS Bb.1234567890)
Driver 2: Yoosef Jookar   (national_code 2281808351, UTCMS Kk.1234567890)
"""
import asyncio
import json
import uuid
from datetime import UTC, datetime

from sqlmodel import select

from app.auth_multitenant import encrypt_driver_password
from app.core.database import async_session_factory
from app.models_multitenant import (
    Client,
    Driver,
    DriverPlate,
    DriverStatus,
    TaskSource,
    TaskStatus,
    WaybillJob,
)
from app.services.rpa_dispatch_service import rpa_dispatch_service

CLIENT_ID = 3

DRIVERS = [
    {
        "national_code": "1719262438",
        "full_name": "حسین اشخاصی",
        "utcms_username": "Bb.1234567890",
        "utcms_password": "حسین اشخاصی",
        "phone": "09124663360",
        "plate": "52ع57921",
        "vehicle_type": "۱۰تا ۲۰ تن",
        "payload": {
            "sender": {
                "name": "حسین اشخاصی",
                "phone": "09124663360",
                "national_code": "1719262438",
                "address": "البرز طالقان",
            },
            "receiver": {
                "name": "حسین رسوبی",
                "phone": "09192582780",
                "national_code": "1719262438",
                "address": "البرز طالقان میر انجیلاق کلارود",
            },
            "origin": {
                "province": "البرز",
                "city": "کرج",
                "district": "",
                "address": "طالقان",
            },
            "destination": {
                "province": "البرز",
                "city": "طالقان",
                "district": "",
                "address": "میر انجیلاق کلارود",
            },
            "cargo": {
                "type": "مصالح",
                "weight": "19",
                "count": "19",
                "value": "10000000",
                "description": "حمل مصالح ساختمانی",
            },
            "vehicle": {
                "driver_national_code": "1719262438",
                "driver_phone": "09124663360",
                "plate": "۵۲ع۵۷۹ایران ۲۱",
                "type": "۱۰تا ۲۰ تن",
            },
            "financial": {
                "cost": "7600000",
                "payment_method": "نقدی",
            },
            "shipping_options": {
                "two_way": False,
                "time_limit": "30",
                "end_shipping": "",
                "otp": "",
            },
        },
    },
    {
        "national_code": "2281808351",
        "full_name": "یوسف جوکار",
        "utcms_username": "Kk.1234567890",
        "utcms_password": "یوسف جوکار",
        "phone": "09178642772",
        "plate": "72ع72993",
        "vehicle_type": "۱۰ تا ۲۰ تن",
        "payload": {
            "sender": {
                "name": "یوسف جوکار",
                "phone": "09178642772",
                "national_code": "2281808351",
                "address": "فارس شیراز",
            },
            "receiver": {
                "name": "علی حسینی",
                "phone": "09185678093",
                "national_code": "2281808351",
                "address": "فارس شیراز",
            },
            "origin": {
                "province": "فارس",
                "city": "شیراز",
                "district": "",
                "address": "محله دینکان_منصور آباد",
            },
            "destination": {
                "province": "فارس",
                "city": "شیراز",
                "district": "",
                "address": "محله منطقه هوایی شهید دوران",
            },
            "cargo": {
                "type": "مصالح",
                "weight": "19",
                "count": "19",
                "value": "10000000",
                "description": "حمل مصالح ساختمانی",
            },
            "vehicle": {
                "driver_national_code": "2281808351",
                "driver_phone": "09178642772",
                "plate": "۷۲ع۷۲۹ایران ۹۳",
                "type": "۱۰ تا ۲۰ تن",
            },
            "financial": {
                "cost": "7600000",
                "payment_method": "نقدی",
            },
            "shipping_options": {
                "two_way": False,
                "time_limit": "30",
                "end_shipping": "",
                "otp": "",
            },
        },
    },
]


async def upsert_driver_and_plate(session, d):
    encrypted_pass = encrypt_driver_password(d["utcms_password"])
    # Unique constraint is (client_id, driver_national_code) — look up by that.
    drivers = (
        await session.exec(
            select(Driver).where(
                Driver.client_id == CLIENT_ID,
                Driver.driver_national_code == d["national_code"],
            )
        )
    ).all()
    if drivers:
        driver = drivers[0]
        driver.full_name = d["full_name"]
        driver.utcms_password_encrypted = encrypted_pass
        driver.phone = d["phone"]
        driver.driver_national_code = d["national_code"]
        driver.status = DriverStatus.ACTIVE.value
        driver.client_id = CLIENT_ID
        session.add(driver)
        await session.flush()
        driver_id = driver.id
        print(f"✓ Driver '{d['full_name']}' updated (ID {driver_id})")
    else:
        driver = Driver(
            client_id=CLIENT_ID,
            full_name=d["full_name"],
            utcms_username=d["utcms_username"],
            utcms_password_encrypted=encrypted_pass,
            driver_national_code=d["national_code"],
            phone=d["phone"],
            status=DriverStatus.ACTIVE.value,
            runtime_status="idle",
        )
        session.add(driver)
        await session.flush()
        driver_id = driver.id
        print(f"✓ Driver '{d['full_name']}' created (ID {driver_id})")

    plates = (
        await session.exec(
            select(DriverPlate).where(
                DriverPlate.driver_id == driver_id,
                DriverPlate.plate_number == d["plate"],
            )
        )
    ).all()
    if plates:
        plate = plates[0]
        plate.vehicle_type = d["vehicle_type"]
        plate.status = "active"
        plate.client_id = CLIENT_ID
        session.add(plate)
        await session.flush()
    else:
        plate = DriverPlate(
            client_id=CLIENT_ID,
            driver_id=driver_id,
            plate_number=d["plate"],
            vehicle_type=d["vehicle_type"],
            status="active",
        )
        session.add(plate)
        await session.flush()
        print(f"✓ Plate {d['plate']} linked to driver {driver_id}")
    return driver_id


async def submit_one(session, d):
    driver_id = await upsert_driver_and_plate(session, d)
    job_id = f"job_{uuid.uuid4().hex[:16]}"
    idempotency_key = f"key_{uuid.uuid4().hex[:16]}"
    job = WaybillJob(
        job_id=job_id,
        idempotency_key=idempotency_key,
        client_id=CLIENT_ID,
        driver_id=driver_id,
        status=TaskStatus.PENDING.value,
        source=TaskSource.MANUAL.value,
        payload_json=json.dumps(d["payload"], ensure_ascii=False),
        created_at=datetime.now(UTC).replace(tzinfo=None),
        updated_at=datetime.now(UTC).replace(tzinfo=None),
    )
    session.add(job)
    await session.flush()
    print(f"✓ Job {job_id} created in database")
    status = await rpa_dispatch_service.dispatch_waybill_job_now(
        session=session,
        job=job,
        requested_at=datetime.now(UTC).replace(tzinfo=None),
    )
    await session.commit()
    print(f"✓ Job dispatched! Status: {status} | Celery Task ID: {job.celery_task_id}")
    return job_id


async def main():
    print("=== Production Waybill Submission (2 drivers) ===")
    session = async_session_factory()
    try:
        client = await session.get(Client, CLIENT_ID)
        if not client:
            print(f"⚠ Client ID {CLIENT_ID} not found — jobs will still be created but tenant may be missing.")
        results = []
        for d in DRIVERS:
            jid = await submit_one(session, d)
            results.append(jid)
        print("\n=== SUMMARY ===")
        for jid in results:
            print(f"  - {jid}")
    except Exception as e:
        await session.rollback()
        print(f"✗ Submission failed: {e}")
        raise
    finally:
        await session.close()


if __name__ == "__main__":
    asyncio.run(main())

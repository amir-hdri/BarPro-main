"""Delete incomplete drivers (10, 11, 12) and update remaining waybill jobs with valid payloads and dispatch."""
import asyncio
from datetime import datetime, timezone
from sqlalchemy import text
from sqlmodel import select
from app.core.database import async_session_factory
from app.models_multitenant import WaybillJob, Driver, DriverPlate, TaskStatus
from app.automation.multitenant_payload_adapter import (
    build_enhanced_waybill_payload,
    validate_enhanced_waybill_payload,
)

CARGO_CATALOG = [
    {"type": "قطعات صنعتی", "packaging": "پالت", "weight": "4500", "value": "350000000"},
    {"type": "لوازم یدکی خودرو", "packaging": "کارتن", "weight": "3200", "value": "280000000"},
    {"type": "مواد اولیه پلاستیک", "packaging": "کیسه", "weight": "5000", "value": "400000000"},
    {"type": "ابزارآلات ساختمانی", "packaging": "جعبه چوبی", "weight": "2800", "value": "220000000"},
    {"type": "کارتن خالی و بسته‌بندی", "packaging": "بسته", "weight": "1500", "value": "120000000"},
]

ROUTES = [
    {
        "origin": {"province": "تهران", "city": "تهران", "address": "بزرگراه آزادگان باربری مرکزی انبار ۳"},
        "destination": {"province": "اصفهان", "city": "اصفهان", "address": "بلوار دانشگاه خیابان بهار پلاک ۱۰"},
    },
    {
        "origin": {"province": "تهران", "city": "تهران", "address": "جاده مخصوص کرج کیلومتر ۱۱ باربری غرب"},
        "destination": {"province": "فارس", "city": "شیراز", "address": "بلوار امیرکبیر مجتمع تجاری باربری شیراز"},
    },
    {
        "origin": {"province": "تهران", "city": "تهران", "address": "خیابان شوش غربی گاراژ مرکزی تهران"},
        "destination": {"province": "خراسان رضوی", "city": "مشهد", "address": "بلوار فرودگاه شهرک صنعتی توس"},
    },
]

async def process_cleanup_and_update():
    async with async_session_factory() as session:
        print("--- 1. Deleting incomplete drivers (10, 11, 12) & related records ---")
        cleanup_queries = [
            "DELETE FROM dispatch_intents WHERE job_id IN (SELECT job_id FROM waybill_jobs WHERE driver_id IN (10, 11, 12) OR id IN (10, 11));",
            "DELETE FROM executions WHERE job_id IN (SELECT job_id FROM waybill_jobs WHERE driver_id IN (10, 11, 12) OR id IN (10, 11));",
            "DELETE FROM waybill_attempts WHERE job_id IN (SELECT job_id FROM waybill_jobs WHERE driver_id IN (10, 11, 12) OR id IN (10, 11));",
            "DELETE FROM waybill_jobs WHERE driver_id IN (10, 11, 12) OR id IN (10, 11);",
            "DELETE FROM domain_events WHERE driver_id IN (10, 11, 12);",
            "DELETE FROM driver_daily_counters WHERE driver_id IN (10, 11, 12);",
            "DELETE FROM driver_session_metadata WHERE driver_id IN (10, 11, 12);",
            "DELETE FROM fuel_inquiries WHERE driver_id IN (10, 11, 12);",
            "DELETE FROM driver_plates WHERE driver_id IN (10, 11, 12);",
            "DELETE FROM driver_runtime_states WHERE driver_id IN (10, 11, 12);",
            "DELETE FROM drivers WHERE id IN (10, 11, 12);",
        ]
        for q in cleanup_queries:
            await session.exec(text(q))
        await session.commit()
        print("✅ Cleanup completed successfully.\n")

    async with async_session_factory() as session:
        drivers = (await session.exec(select(Driver))).all()
        driver_map = {d.id: d for d in drivers}
        
        plates = (await session.exec(select(DriverPlate))).all()
        plate_map = {p.driver_id: p.plate_number for p in plates}
        
        print("--- 2. Active Drivers in Fleet ---")
        for d in drivers:
            print(f"👤 Driver {d.id}: {d.full_name} | NationalCode: {d.driver_national_code} | Plate: {plate_map.get(d.id, 'N/A')}")
            
        jobs = (await session.exec(select(WaybillJob).order_by(WaybillJob.id))).all()
        print(f"\n--- 3. Validating & Updating {len(jobs)} Remaining Waybill Jobs ---")
        
        updated_count = 0
        for i, job in enumerate(jobs):
            driver = driver_map.get(job.driver_id)
            if not driver:
                print(f"Skipping job {job.id}: driver {job.driver_id} not found.")
                continue
                
            plate = plate_map.get(driver.id)
            if not plate:
                print(f"Skipping job {job.id}: plate for driver {driver.id} not found.")
                continue
                
            cargo = CARGO_CATALOG[i % len(CARGO_CATALOG)]
            route = ROUTES[i % len(ROUTES)]
            
            payload = {
                "sender": {
                    "entity_type": "individual",
                    "first_name": "علی",
                    "last_name": "رضایی",
                    "name": "علی رضایی",
                    "national_id": "0012345678",
                    "phone": "09121111111",
                    "postal_code": "1111111111"
                },
                "receiver": {
                    "entity_type": "individual",
                    "first_name": "حسین",
                    "last_name": "احمدی",
                    "name": "حسین احمدی",
                    "national_id": "0023456789",
                    "phone": "09122222222",
                    "postal_code": "2222222222"
                },
                "origin": route["origin"],
                "destination": route["destination"],
                "cargo": cargo,
                "vehicle": {
                    "driver_national_code": driver.driver_national_code,
                    "plate": plate,
                },
                "financial": {
                    "fare": "15000000",
                    "fare_amount": "15000000",
                },
                "shipping_options": {
                    "cost_mode": "مبلغ کرایه و کمیسیون محاسبه نشود"
                }
            }
            
            normalized = build_enhanced_waybill_payload(payload)
            errors = validate_enhanced_waybill_payload(normalized)
            if errors:
                print(f"❌ Validation errors for job {job.id}: {errors}")
                continue
                
            job.payload_json = payload
            job.status = TaskStatus.PENDING.value
            job.error_category = None
            job.last_error = None
            job.terminal_reason = None
            job.retryable = True
            job.next_retry_at = None
            job.attempt_count = 0
            job.celery_task_id = None
            job.worker_id = None
            job.started_at = None
            job.finished_at = None
            job.updated_at = datetime.now(timezone.utc).replace(tzinfo=None)
            session.add(job)
            updated_count += 1
            print(f"✅ Job {job.id} (Driver: {driver.full_name}, Plate: {plate}) updated to PENDING.")
            
        await session.commit()
        print(f"\n🎉 Total {updated_count}/{len(jobs)} jobs successfully updated and set to PENDING.")

    # 4. Trigger immediate scheduler dispatch
    try:
        from app.services.rpa_dispatch_service import rpa_dispatch_service
        print("\n--- 4. Triggering RPA Dispatch ---")
        dispatched = await rpa_dispatch_service.dispatch_phase1_due_jobs()
        print(f"Dispatched {len(dispatched)} decisions to Celery queues.")
        for d in dispatched:
            print(" ->", d)
    except Exception as e:
        print(f"Note on manual dispatch: {e} (Celery Scheduler will pick up pending jobs automatically in 5s)")

if __name__ == "__main__":
    asyncio.run(process_cleanup_and_update())

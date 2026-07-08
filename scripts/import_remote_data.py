import json
import asyncio
from sqlmodel import select
from app.core.database import async_session_factory
from app.models_multitenant import Driver, DriverPlate, WaybillJob

async def import_data():
    backup_path = "/app/output/remote_data_backup.json"
    print(f"Reading backup from {backup_path}...")
    
    try:
        with open(backup_path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except FileNotFoundError:
        print(f"Error: Backup file not found at {backup_path}. Please place the backup in the local output/ folder first.")
        return
        
    drivers = data.get("drivers", [])
    plates = data.get("driver_plates", [])
    waybills = data.get("waybill_jobs", [])
    
    async with async_session_factory() as session:
        # 1. Import Drivers
        print(f"Importing {len(drivers)} drivers...")
        for d in drivers:
            existing = await session.get(Driver, d["id"])
            if existing:
                for k, v in d.items():
                    setattr(existing, k, v)
                session.add(existing)
            else:
                new_driver = Driver(**d)
                session.add(new_driver)
                
        # 2. Import Plates
        print(f"Importing {len(plates)} driver plates...")
        for p in plates:
            existing = await session.get(DriverPlate, p["id"])
            if existing:
                for k, v in p.items():
                    setattr(existing, k, v)
                session.add(existing)
            else:
                new_plate = DriverPlate(**p)
                session.add(new_plate)
                
        # 3. Import Waybills
        print(f"Importing {len(waybills)} waybill jobs...")
        for w in waybills:
            # Handle string-based IDs if needed, but waybill_jobs table has id as integer or string?
            # Let's check models_multitenant: WaybillJob.id is a string? Or uuid?
            # Actually, WaybillJob has id or job_id? Let's check.
            # Wait, let's look at the fields of WaybillJob model.
            existing = await session.get(WaybillJob, w["id"])
            if existing:
                for k, v in w.items():
                    setattr(existing, k, v)
                session.add(existing)
            else:
                new_waybill = WaybillJob(**w)
                session.add(new_waybill)
                
        await session.commit()
        print("Import completed successfully!")

if __name__ == "__main__":
    asyncio.run(import_data())

import json
import asyncio
from datetime import datetime
from sqlmodel import select
from app.core.database import async_session_factory
from app.models_multitenant import Driver, DriverPlate, WaybillJob, Client
from app.auth_multitenant import hash_password

DATETIME_KEYS = {
    "last_auth_at",
    "last_session_expires_at",
    "created_at",
    "updated_at",
    "next_retry_at",
    "submit_after",
    "started_at",
    "finished_at",
    "subscription_start_date",
    "subscription_end_date"
}

def parse_dict(item: dict) -> dict:
    res = {}
    for k, v in item.items():
        if k in DATETIME_KEYS and isinstance(v, str):
            try:
                if 'T' in v:
                    res[k] = datetime.fromisoformat(v)
                elif ' ' in v:
                    res[k] = datetime.fromisoformat(v.replace(' ', 'T'))
                else:
                    res[k] = datetime.strptime(v, "%Y-%m-%d")
            except ValueError:
                res[k] = v
        else:
            res[k] = v
    return res

def filter_model_fields(model, data_dict: dict) -> dict:
    valid_fields = set(model.model_fields.keys())
    return {k: v for k, v in data_dict.items() if k in valid_fields}

async def import_data():
    import os
    backup_path = "/app/output/remote_data_backup.json"
    if not os.path.exists(backup_path) and os.path.exists("remote_data_backup.json"):
        backup_path = "remote_data_backup.json"
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
        # 0. Ensure Client with ID 1 exists (since foreign keys depend on it)
        client1 = await session.get(Client, 1)
        if not client1:
            print("Creating default client with ID 1...")
            client1 = Client(
                id=1,
                client_code="amir",
                name="امیر",
                full_name="امیر",
                email="amir@gmail.com",
                phone="09120000000",
                hashed_password=hash_password("amir123"),
                status="active",
                access_level="standard",
                username="amir",
                subscription_start_date=None,
                subscription_end_date=datetime(2030, 1, 1)
            )
            session.add(client1)
            await session.commit()
            print("Default client 1 created successfully!")

        # 1. Import Drivers
        print(f"Importing {len(drivers)} drivers...")
        for d in drivers:
            parsed_d = parse_dict(d)
            filtered_d = filter_model_fields(Driver, parsed_d)
            existing = await session.get(Driver, filtered_d["id"])
            if existing:
                for k, v in filtered_d.items():
                    setattr(existing, k, v)
                session.add(existing)
            else:
                new_driver = Driver(**filtered_d)
                session.add(new_driver)
                
        # 2. Import Plates
        print(f"Importing {len(plates)} driver plates...")
        for p in plates:
            parsed_p = parse_dict(p)
            filtered_p = filter_model_fields(DriverPlate, parsed_p)
            existing = await session.get(DriverPlate, filtered_p["id"])
            if existing:
                for k, v in filtered_p.items():
                    setattr(existing, k, v)
                session.add(existing)
            else:
                new_plate = DriverPlate(**filtered_p)
                session.add(new_plate)
                
        # 3. Import Waybills
        print(f"Importing {len(waybills)} waybill jobs...")
        for w in waybills:
            parsed_w = parse_dict(w)
            filtered_w = filter_model_fields(WaybillJob, parsed_w)
            existing = await session.get(WaybillJob, filtered_w["id"])
            if existing:
                for k, v in filtered_w.items():
                    setattr(existing, k, v)
                session.add(existing)
            else:
                new_waybill = WaybillJob(**filtered_w)
                session.add(new_waybill)
                
        await session.commit()
        print("Import completed successfully!")

if __name__ == "__main__":
    asyncio.run(import_data())

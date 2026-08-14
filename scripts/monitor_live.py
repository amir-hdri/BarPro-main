"""Live monitoring script for Waybill jobs, execution status, and worker logs."""
import asyncio
from sqlmodel import select
from app.core.database import async_session_factory
from app.models_multitenant import WaybillJob, Driver, DriverPlate, TaskStatus

async def monitor():
    async with async_session_factory() as session:
        drivers = (await session.exec(select(Driver))).all()
        driver_map = {d.id: d for d in drivers}
        
        plates = (await session.exec(select(DriverPlate))).all()
        plate_map = {p.driver_id: p.plate_number for p in plates}
        
        jobs = (await session.exec(select(WaybillJob).order_by(WaybillJob.id))).all()
        print(f"=== LIVE WAYBILL JOBS MONITOR ({len(jobs)} Total Jobs) ===")
        print(f"{'ID':<4} | {'Driver Name':<20} | {'Plate':<15} | {'Status':<14} | {'Tracking Code':<15} | {'Error Category':<20}")
        print("-" * 100)
        
        status_counts = {}
        for j in jobs:
            driver = driver_map.get(j.driver_id)
            d_name = driver.full_name if driver else "Unknown"
            plate = plate_map.get(j.driver_id, "-")
            status = j.status or "unknown"
            status_counts[status] = status_counts.get(status, 0) + 1
            tc = j.submission_fingerprint or "-"
            err = j.error_category or "-"
            last_err = f" ({j.last_error[:30]}...)" if j.last_error else ""
            print(f"{j.id:<4} | {d_name:<20} | {plate:<15} | {status:<14} | {tc:<15} | {err + last_err:<20}")
            
        print("\nSummary by Status:", status_counts)

if __name__ == "__main__":
    asyncio.run(monitor())

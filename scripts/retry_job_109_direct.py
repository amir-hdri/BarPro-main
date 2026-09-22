import asyncio
from sqlalchemy import text
from sqlmodel import select
from app.core.database import async_session_factory
from app.models_multitenant import WaybillJob, TaskStatus
import logging
from app.services.rpa_submit_service import rpa_submit_service

logging.basicConfig(level=logging.INFO)

async def run_job_109():
    async with async_session_factory() as session:
        job = (await session.exec(select(WaybillJob).where(WaybillJob.id == 109))).first()
        if not job:
            print("Job 109 not found!")
            return
        
        job_id_str = job.job_id
        client_id = job.client_id
        print(f"Executing job {job_id_str} for client {client_id} directly...")

    try:
        await rpa_submit_service._process_job(client_id, job_id_str)
        print("✅ _process_job finished.")
    except Exception as e:
        print(f"Error during _process_job: {e}")

if __name__ == "__main__":
    asyncio.run(run_job_109())

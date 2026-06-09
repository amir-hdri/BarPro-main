#!/usr/bin/env python3
"""
Script to fix stuck jobs in the BarPro system
"""
import asyncio
import sys
from datetime import datetime, UTC
from sqlmodel import select, update, func
from app.core.database import async_session_factory
from app.models_multitenant import WaybillJob, TaskStatus, WaybillTaskLog


async def fix_stuck_job(job_id: str):
    """Fix a job that's stuck in in_progress status."""
    session = async_session_factory()
    try:
        # First, let's query the job to see its current state
        result = await session.exec(select(WaybillJob).where(WaybillJob.job_id == job_id))
        job = result.first()
        
        if not job:
            print(f"Job {job_id} not found in database")
            return False
            
        print(f"Current job status: {job.status}")
        print(f"Created at: {job.created_at}")
        print(f"Updated at: {job.updated_at}")
        print(f"Celery task ID: {job.celery_task_id}")
        print(f"Driver ID: {job.driver_id}")
        print(f"Client ID: {job.client_id}")
        
        # Check if the job is indeed stuck in in_progress status
        if job.status == "in_progress":
            print(f"Job {job_id} is stuck in 'in_progress' status. Attempting to reset...")
            
            # Update the job status to FAILED so it can be retried
            stmt = update(WaybillJob).where(
                WaybillJob.job_id == job_id
            ).values(
                status=TaskStatus.FAILED.value,
                last_error='Job was stuck in in_progress status, manually reset for retry',
                updated_at=datetime.now(UTC).replace(tzinfo=None),
                celery_task_id=None  # Reset the task ID
            )
            
            await session.exec(stmt)
            
            # Add a log entry to document the intervention
            log_entry = WaybillTaskLog(
                job_id=job.job_id,
                client_id=job.client_id,
                step='manual_recovery',
                status='failed',
                message='Job was stuck in in_progress status, manually reset for retry',
            )
            session.add(log_entry)
            
            await session.commit()
            print(f"Successfully updated job {job_id} status from in_progress to failed")
            print("The job should now be available for retry.")
            return True
        else:
            print(f"Job {job_id} is not in in_progress status, current status: {job.status}")
            return False
            
    except Exception as e:
        print(f"Error updating job {job_id}: {e}")
        await session.rollback()
        return False
    finally:
        await session.close()


async def check_job_status(job_id: str):
    """Check the current status of a job."""
    session = async_session_factory()
    try:
        result = await session.exec(select(WaybillJob).where(WaybillJob.job_id == job_id))
        job = result.first()
        
        if job:
            print(f"Job {job_id}:")
            print(f"  Status: {job.status}")
            print(f"  Created: {job.created_at}")
            print(f"  Updated: {job.updated_at}")
            print(f"  Last Error: {job.last_error}")
            print(f"  Celery Task ID: {job.celery_task_id}")
        else:
            print(f"Job {job_id} not found")
    finally:
        await session.close()


if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("Usage: python fix_stuck_job.py <check|fix> <job_id>")
        sys.exit(1)
    
    action = sys.argv[1]
    job_id = sys.argv[2]
    
    if action == "check":
        asyncio.run(check_job_status(job_id))
    elif action == "fix":
        asyncio.run(fix_stuck_job(job_id))
    else:
        print("Invalid action. Use 'check' or 'fix'")
        sys.exit(1)
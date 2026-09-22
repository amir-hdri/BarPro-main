import sys
from app.workers.waybill_worker import process_waybill_job

# Push the job to the celery queue directly
# We use apply_async to specify the queue if needed, or rely on task_routes
print("Enqueuing job_fa257c44d1cf46fa to Celery...")
result = process_waybill_job.apply_async(args=["job_fa257c44d1cf46fa"])
print(f"Task dispatched with ID: {result.id}")

"""Fail-closed legacy Excel upload guard and historical batch reader."""

import json

from fastapi import HTTPException, UploadFile, status
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.models_multitenant import Client, TaskStatus, UploadBatch, WaybillJob
from app.schemas.multitenant import BulkUploadResponse

LEGACY_EXCEL_UPLOAD_DISABLED_DETAIL = {
    "error": "LEGACY_EXCEL_UPLOAD_DISABLED",
    "message": (
        "Legacy Excel job creation is disabled because it does not satisfy the canonical "
        "waybill validation, idempotency, scheduler, and state-machine contract."
    ),
    "canonical_endpoint": "POST /api/v1/waybill-jobs",
}


class ExcelUploadService:
    """Read historical batches while rejecting unsafe legacy creation."""

    @staticmethod
    async def process_upload(
        client: Client,
        file: UploadFile,
        session: AsyncSession,
        max_retries: int = 3,
    ) -> BulkUploadResponse:
        """Reject the unsafe legacy bulk-creation path.

        Rows from this legacy format cannot express the complete live UTCMS
        contract.  In particular, the old implementation inserted
        ``WaybillJob`` rows directly with random idempotency keys, bypassing
        ``WaybillJobCreateRequest``, ``WaybillJobService``, the RPA scheduler,
        and state-machine event creation.  Keep this guard in the service as a
        second line of defence even though the public route is also disabled.
        Existing batch records remain readable through ``get_batch_status``.
        """
        del client, file, session, max_retries
        raise HTTPException(
            status_code=status.HTTP_410_GONE,
            detail=LEGACY_EXCEL_UPLOAD_DISABLED_DETAIL,
        )

    @staticmethod
    async def get_batch_status(
        client: Client,
        batch_id: str,
        session: AsyncSession,
    ) -> dict:
        """Get the status of an upload batch."""
        statement = select(UploadBatch).where((UploadBatch.client_id == client.id) & (UploadBatch.batch_id == batch_id))
        result = await session.exec(statement)
        batch = result.first()

        if not batch:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Batch not found",
            )

        jobs_stmt = select(WaybillJob).where(
            (WaybillJob.client_id == client.id) & (WaybillJob.correlation_id == batch_id)
        )
        jobs_result = await session.exec(jobs_stmt)
        batch_jobs = jobs_result.all()

        jobs_completed = sum(
            1
            for j in batch_jobs
            if j.status in [TaskStatus.SUCCESS.value, TaskStatus.FAILED.value, TaskStatus.DEAD_LETTER.value]
        )

        errors: list[dict] = []
        if batch.errors_json:
            if isinstance(batch.errors_json, list):
                errors = batch.errors_json
            elif isinstance(batch.errors_json, str):
                try:
                    parsed = json.loads(batch.errors_json)
                    if isinstance(parsed, list):
                        errors = parsed
                except json.JSONDecodeError:
                    errors = [{"errors": ["Failed to parse batch errors"]}]

        return {
            "batch_id": batch.batch_id,
            "status": batch.status,
            "total_rows": batch.total_rows,
            "valid_rows": batch.valid_rows,
            "invalid_rows": batch.invalid_rows,
            "jobs_created": len(batch_jobs),
            "jobs_completed": jobs_completed,
            "errors": errors,
            "created_at": batch.created_at,
            "completed_at": batch.completed_at,
        }

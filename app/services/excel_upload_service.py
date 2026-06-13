"""
Excel bulk upload service for waybill jobs.

Handles parsing Excel files, validating rows, and creating waybill jobs in bulk.
"""
import io
import json
import logging
import uuid
from datetime import UTC, datetime
from typing import Any

import openpyxl
from fastapi import HTTPException, UploadFile, status
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.core.config import utcms_config
from app.models_multitenant import (
    Client,
    Driver,
    TaskSource,
    TaskStatus,
    UploadBatch,
    WaybillJob,
)
from app.schemas.multitenant import BulkUploadResponse, WaybillJobResponse, WaybillPayload

logger = logging.getLogger(__name__)


class ExcelUploadService:
    """Service for handling Excel bulk uploads."""

    REQUIRED_COLUMNS = {
        "driver_national_code": ["driver_national_code", "national_code", "کد ملی", "کدملی"],
        "origin": ["origin", "mabda", "مبدأ", "مبدا"],
        "destination": ["destination", "maghsad", "مقصد"],
    }

    OPTIONAL_COLUMNS = {
        "waybill_number": ["waybill_number", "بارنامه", "شماره بارنامه"],
        "cargo_type": ["cargo_type", "نوع بار", "cargo_type"],
        "cargo_weight": ["cargo_weight", "وزن", "weight"],
        "cargo_description": ["cargo_description", "توضیحات بار", "description"],
        "vehicle_type": ["vehicle_type", "نوع خودرو", "vehicle"],
        "plate_number": ["plate_number", "پلاک", "plate"],
        "notes": ["notes", "توضیحات", "یادداشت"],
    }

    @staticmethod
    async def process_upload(
        client: Client,
        file: UploadFile,
        session: AsyncSession,
        max_retries: int = 3,
    ) -> BulkUploadResponse:
        """Process an uploaded Excel file and create waybill jobs."""
        filename = file.filename or "upload.xlsx"
        ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
        if ext not in utcms_config.ALLOWED_UPLOAD_EXTENSIONS:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"File type not allowed. Allowed: {', '.join(utcms_config.ALLOWED_UPLOAD_EXTENSIONS)}",
            )

        content = await file.read()
        if not content:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Empty file",
            )

        try:
            workbook = openpyxl.load_workbook(
                filename=io.BytesIO(content),
                data_only=True,
                read_only=True,
            )
        except Exception as e:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Failed to parse Excel file: {str(e)}",
            ) from e

        try:
            sheet = workbook.active
            if not sheet:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Excel file has no sheets",
                )

            rows = list(sheet.iter_rows(values_only=True))
            if not rows:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Excel file is empty",
                )

            headers = [str(h).strip() if h else "" for h in rows[0]]
            column_mapping = ExcelUploadService._map_columns(headers)
            if not column_mapping:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Missing required columns. Required: {list(ExcelUploadService.REQUIRED_COLUMNS.keys())}",
                )

            data_rows = [
                row
                for row in rows[1:]
                if any(cell is not None and str(cell).strip() != "" for cell in row)
            ]
            total_rows = len(data_rows)

            if total_rows > utcms_config.MAX_UPLOAD_ROWS:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Too many rows. Maximum allowed: {utcms_config.MAX_UPLOAD_ROWS}",
                )

            batch_id = f"batch_{uuid.uuid4().hex[:12]}"
            batch = UploadBatch(
                batch_id=batch_id,
                client_id=client.id,
                original_filename=filename,
                total_rows=total_rows,
                status="processing",
            )
            session.add(batch)
            await session.flush()

            valid_rows: list[tuple[int, dict[str, Any]]] = []
            invalid_rows = 0
            errors: list[dict] = []
            jobs_created: list[WaybillJobResponse] = []

            for row_idx, row in enumerate(data_rows, start=2):
                try:
                    payload = ExcelUploadService._parse_row(row, column_mapping)
                    validation_errors = ExcelUploadService._validate_payload(payload)

                    if validation_errors:
                        invalid_rows += 1
                        errors.append(
                            {
                                "row": row_idx,
                                "errors": validation_errors,
                                "data": {
                                    header: (row[idx] if idx < len(row) else None)
                                    for header, idx in column_mapping.items()
                                },
                            }
                        )
                        continue

                    valid_rows.append((row_idx, payload))

                except Exception as e:
                    invalid_rows += 1
                    errors.append(
                        {
                            "row": row_idx,
                            "errors": [f"Parse error: {str(e)}"],
                            "data": {str(h): str(v) for h, v in zip(headers, row, strict=False) if v is not None},
                        }
                    )

            for row_idx, payload_dict in valid_rows:
                try:
                    job = await ExcelUploadService._create_job_from_row(
                        client=client,
                        payload_dict=payload_dict,
                        session=session,
                        batch_id=batch_id,
                        max_retries=max_retries,
                    )
                    jobs_created.append(job)
                except Exception as e:
                    logger.error("Failed to create job for row %s: %s", row_idx, e)
                    errors.append(
                        {
                            "row": row_idx,
                            "errors": [f"Job creation failed: {str(e)}"],
                        }
                    )

            batch.valid_rows = len(jobs_created)
            batch.invalid_rows = invalid_rows + (len(valid_rows) - len(jobs_created))
            batch.status = "completed"
            batch.errors_json = json.dumps(errors, ensure_ascii=False) if errors else None
            batch.completed_at = datetime.now(UTC).replace(tzinfo=None)

            await session.commit()
            await session.refresh(batch)

            return BulkUploadResponse(
                batch_id=batch.batch_id,
                client_id=batch.client_id,
                original_filename=batch.original_filename,
                total_rows=batch.total_rows,
                valid_rows=batch.valid_rows,
                invalid_rows=batch.invalid_rows,
                status=batch.status,
                jobs_created=jobs_created,
                errors=errors,
            )
        except HTTPException:
            await session.rollback()
            raise
        except Exception:
            await session.rollback()
            raise
        finally:
            workbook.close()

    @staticmethod
    def _map_columns(headers: list[str]) -> dict[str, int] | None:
        """Map Excel headers to expected column names."""
        mapping: dict[str, int] = {}
        headers_lower = [h.lower().strip() for h in headers]

        for expected_col, aliases in ExcelUploadService.REQUIRED_COLUMNS.items():
            index = ExcelUploadService._find_alias_index(headers_lower, aliases)
            if index is None:
                return None
            mapping[expected_col] = index

        for expected_col, aliases in ExcelUploadService.OPTIONAL_COLUMNS.items():
            index = ExcelUploadService._find_alias_index(headers_lower, aliases)
            if index is not None:
                mapping[expected_col] = index

        return mapping

    @staticmethod
    def _find_alias_index(headers_lower: list[str], aliases: list[str]) -> int | None:
        for alias in aliases:
            alias_lower = alias.lower()
            if alias_lower in headers_lower:
                return headers_lower.index(alias_lower)
        return None

    @staticmethod
    def _parse_row(row: tuple[Any, ...], column_mapping: dict[str, int]) -> dict[str, Any]:
        """Parse a row into a payload dictionary."""
        payload: dict[str, Any] = {}
        for field_name, index in column_mapping.items():
            payload[field_name] = row[index] if index < len(row) else None
        return payload

    @staticmethod
    def _validate_payload(payload: dict[str, Any]) -> list[str]:
        """Validate a parsed payload."""
        errors = []

        if not payload.get("driver_national_code"):
            errors.append("driver_national_code is required")
        if not payload.get("origin"):
            errors.append("origin is required")
        if not payload.get("destination"):
            errors.append("destination is required")

        if payload.get("cargo_weight") not in (None, ""):
            try:
                weight = float(payload["cargo_weight"])
                if weight <= 0:
                    errors.append("cargo_weight must be positive")
            except (ValueError, TypeError):
                errors.append("cargo_weight must be a number")

        return errors

    @staticmethod
    async def _create_job_from_row(
        client: Client,
        payload_dict: dict[str, Any],
        session: AsyncSession,
        batch_id: str,
        max_retries: int = 3,
    ) -> WaybillJobResponse:
        """Create a waybill job from a parsed row."""
        driver_national_code = str(payload_dict["driver_national_code"]).strip()
        driver_stmt = select(Driver).where(
            (Driver.client_id == client.id)
            & (Driver.driver_national_code == driver_national_code)
        )
        driver_result = await session.exec(driver_stmt)
        driver = driver_result.first()

        if not driver:
            raise ValueError(f"Driver not found: {driver_national_code}")

        payload = WaybillPayload(
            driver_national_code=driver_national_code,
            origin=str(payload_dict.get("origin", "")).strip(),
            destination=str(payload_dict.get("destination", "")).strip(),
            waybill_number=str(payload_dict.get("waybill_number", "")) if payload_dict.get("waybill_number") else None,
            cargo_type=str(payload_dict.get("cargo_type", "")) if payload_dict.get("cargo_type") else None,
            cargo_weight=float(payload_dict["cargo_weight"]) if payload_dict.get("cargo_weight") else None,
            cargo_description=str(payload_dict.get("cargo_description", "")) if payload_dict.get("cargo_description") else None,
            vehicle_type=str(payload_dict.get("vehicle_type", "")) if payload_dict.get("vehicle_type") else None,
            plate_number=str(payload_dict.get("plate_number", "")) if payload_dict.get("plate_number") else None,
            notes=str(payload_dict.get("notes", "")) if payload_dict.get("notes") else None,
            metadata_json={"batch_id": batch_id},
        )

        job = WaybillJob(
            job_id=f"job_{uuid.uuid4().hex[:12]}",
            idempotency_key=f"idem_{uuid.uuid4().hex[:16]}",
            client_id=client.id,
            driver_id=driver.id,
            status=TaskStatus.PENDING.value,
            source=TaskSource.BULK_UPLOAD.value,
            payload_json=payload.model_dump_json(),
            correlation_id=batch_id,
            max_retries=max_retries,
        )

        session.add(job)
        await session.flush()
        await session.refresh(job)

        return WaybillJobResponse.model_validate(job)

    @staticmethod
    async def get_batch_status(
        client: Client,
        batch_id: str,
        session: AsyncSession,
    ) -> dict:
        """Get the status of an upload batch."""
        statement = select(UploadBatch).where(
            (UploadBatch.client_id == client.id)
            & (UploadBatch.batch_id == batch_id)
        )
        result = await session.exec(statement)
        batch = result.first()

        if not batch:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Batch not found",
            )

        jobs_stmt = select(WaybillJob).where(
            (WaybillJob.client_id == client.id)
            & (WaybillJob.correlation_id == batch_id)
        )
        jobs_result = await session.exec(jobs_stmt)
        batch_jobs = jobs_result.all()

        jobs_completed = sum(
            1 for j in batch_jobs
            if j.status in [TaskStatus.SUCCESS.value, TaskStatus.FAILED.value, TaskStatus.DEAD_LETTER.value]
        )

        errors: list[dict] = []
        if batch.errors_json:
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

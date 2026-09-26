"""Celery worker for auto-completing due in-transit shipping trips."""

from __future__ import annotations

import logging
from typing import Any

from app.automation.gps_shipping_manager import auto_complete_shipping, get_due_in_transit_jobs
from app.core.utils import run_async
from app.workers.celery_app import celery_app

logger = logging.getLogger(__name__)


async def _auto_complete_due_trips() -> dict[str, Any]:
    """Scan due in-transit trips and complete shipping at destination coordinates."""
    due_jobs = await get_due_in_transit_jobs()
    scanned_count = len(due_jobs)
    completed: list[dict[str, Any]] = []
    skipped: list[dict[str, Any]] = []
    failed: list[dict[str, Any]] = []

    logger.info(
        "shipping_due_trips_scan_started",
        extra={"extra_fields": {"due_count": scanned_count}},
    )

    for state in due_jobs:
        job_id = state.job_id
        doc_no = getattr(state, "doc_no", "")
        doc_id = getattr(state, "doc_id", "")
        origin_address = getattr(state, "origin_address", "")
        dest_address = getattr(state, "dest_address", "")
        distance_km = getattr(state, "distance_km", 0.0)
        estimated_end_at = getattr(state, "estimated_end_at", "")

        logger.info(
            "shipping_due_trip_scanned",
            extra={
                "extra_fields": {
                    "job_id": job_id,
                    "doc_no": doc_no,
                    "doc_id": doc_id,
                    "status": getattr(state, "status", None),
                    "origin_address": origin_address,
                    "dest_address": dest_address,
                    "distance_km": distance_km,
                    "estimated_end_at": estimated_end_at,
                }
            },
        )

        try:
            res = await auto_complete_shipping(job_id)
            res_status = res.get("status") if isinstance(res, dict) else str(res)
            if res_status == "delivered":
                completed.append({"job_id": job_id, "doc_no": doc_no, "result": res})
                logger.info(
                    "shipping_due_trip_completed",
                    extra={
                        "extra_fields": {
                            "job_id": job_id,
                            "doc_no": doc_no,
                            "doc_id": doc_id,
                            "result_status": res_status,
                            "result": res,
                        }
                    },
                )
            else:
                skipped.append({"job_id": job_id, "doc_no": doc_no, "status": res_status, "result": res})
                logger.info(
                    "shipping_due_trip_skipped",
                    extra={
                        "extra_fields": {
                            "job_id": job_id,
                            "doc_no": doc_no,
                            "doc_id": doc_id,
                            "result_status": res_status,
                            "result": res,
                        }
                    },
                )
        except Exception as exc:
            failed.append({"job_id": job_id, "doc_no": doc_no, "error": str(exc)})
            logger.error(
                "shipping_due_trip_failed",
                extra={
                    "extra_fields": {
                        "job_id": job_id,
                        "doc_no": doc_no,
                        "doc_id": doc_id,
                        "error": str(exc),
                    }
                },
                exc_info=True,
            )

    summary = {
        "scanned_count": scanned_count,
        "completed_count": len(completed),
        "skipped_count": len(skipped),
        "failed_count": len(failed),
        "completed": completed,
        "skipped": skipped,
        "failed": failed,
    }

    logger.info(
        "shipping_due_trips_scan_completed",
        extra={"extra_fields": summary},
    )
    return summary


def _execute_auto_complete_task(task_instance: Any = None) -> dict[str, Any]:
    try:
        return run_async(_auto_complete_due_trips())
    except Exception as exc:
        logger.error(
            "shipping_auto_complete_due_trips_fatal_error",
            extra={"extra_fields": {"error": str(exc)}},
            exc_info=True,
        )
        if task_instance is not None and hasattr(task_instance, "retry"):
            retries = getattr(getattr(task_instance, "request", None), "retries", 0)
            max_retries = getattr(task_instance, "max_retries", 2)
            if retries < max_retries:
                raise task_instance.retry(exc=exc) from exc
        raise


if celery_app is not None:

    @celery_app.task(
        name="shipping.auto_complete_due_trips",
        bind=True,
        max_retries=2,
        default_retry_delay=30,
    )
    def auto_complete_due_trips(self: Any = None, *args: Any, **kwargs: Any) -> dict[str, Any]:
        """Auto-complete due in-transit shipping trips on schedule."""
        return _execute_auto_complete_task(self)

else:

    def auto_complete_due_trips(self: Any = None, *args: Any, **kwargs: Any) -> dict[str, Any]:
        """Fallback definition when Celery is not initialized."""
        return _execute_auto_complete_task(self)


__all__ = ["auto_complete_due_trips"]

"""
API Routes for Admin Alerts, Manual Reconciliation, and Fencing-Protected Retries.
"""

import logging
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.auth_multitenant import get_current_admin
from app.core.database import get_session
from app.models.admin import AdminAlert
from app.models_multitenant import WaybillJob
from app.models_rpa import Execution
from app.orchestrator.alert_manager import admin_alert_service
from app.orchestrator.reconciliation_service import reconciliation_service
from app.orchestrator.state_machine import JobStateMachine, JobStatus

router = APIRouter(prefix="/api/v1/admin", tags=["admin-alerts"])

logger = logging.getLogger(__name__)


class RetryRequest(BaseModel):
    fencing_token: int | None = None
    reason: str | None = None


@router.get(
    "/alerts",
    summary="دریافت هشدارهای سیستم مدیریت",
    dependencies=[Depends(get_current_admin)],
)
async def list_admin_alerts(
    severity: str | None = Query(None, description="فیلتر بر اساس شدت (info, warning, high, critical)"),
    category: str | None = Query(None, description="فیلتر بر اساس دسته‌بندی"),
    is_acknowledged: bool | None = Query(None, description="فیلتر بر اساس وضعیت تأیید"),
    tenant_id: int | None = Query(None, description="فیلتر بر اساس مشتری"),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    """List admin alerts with optional filters."""
    query = select(AdminAlert)

    if severity:
        query = query.where(AdminAlert.severity == severity.lower())
    if category:
        query = query.where(AdminAlert.category == category)
    if is_acknowledged is not None:
        query = query.where(AdminAlert.is_acknowledged == is_acknowledged)
    if tenant_id:
        query = query.where(AdminAlert.tenant_id == tenant_id)

    # Count query
    count_stmt = select(func.count()).select_from(query.subquery())
    total = (await session.execute(count_stmt)).scalar() or 0

    # Pagination & Ordering
    query = query.order_by(AdminAlert.created_at.desc()).offset(offset).limit(limit)
    alerts = (await session.execute(query)).scalars().all()

    return {
        "total": total,
        "offset": offset,
        "limit": limit,
        "items": [
            {
                "id": a.id,
                "tenant_id": a.tenant_id,
                "severity": a.severity,
                "category": a.category,
                "message": a.message,
                "dedupe_key": a.dedupe_key,
                "details": a.details,
                "is_acknowledged": a.is_acknowledged,
                "acknowledged_at": a.acknowledged_at.isoformat() if a.acknowledged_at else None,
                "acknowledged_by": a.acknowledged_by,
                "created_at": a.created_at.isoformat(),
            }
            for a in alerts
        ],
    }


@router.post(
    "/alerts/{alert_id}/acknowledge",
    summary="تأیید و بستن هشدار توسط ادمین",
)
async def acknowledge_admin_alert(
    alert_id: int,
    admin: Any = Depends(get_current_admin),
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    """Mark alert as acknowledged."""
    admin_id = getattr(admin, "id", None)
    alert = await admin_alert_service.acknowledge_alert(session, alert_id=alert_id, admin_id=admin_id)

    if not alert:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Alert not found")

    return {
        "status": "success",
        "alert_id": alert.id,
        "is_acknowledged": alert.is_acknowledged,
        "acknowledged_at": alert.acknowledged_at.isoformat() if alert.acknowledged_at else None,
    }


@router.post(
    "/reconcile/{job_id}",
    summary="تطبیق دستی وضعیت بارنامه با UTCMS",
    dependencies=[Depends(get_current_admin)],
)
async def reconcile_job_manually(
    job_id: int,
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    """Trigger manual status reconciliation for a specific job."""
    job = await reconciliation_service.reconcile_job(session=session, job_id=job_id)

    if not job:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Job not found")

    return {
        "status": "success",
        "job_id": job.id,
        "current_status": job.status,
        "tracking_code": (job.result_json or {}).get("tracking_code"),
    }


@router.post(
    "/jobs/{job_id}/retry",
    summary="تلاش مجدد دستی با محافظت Fencing Token",
    dependencies=[Depends(get_current_admin)],
)
async def retry_job_manually(
    job_id: int,
    req: RetryRequest | None = None,
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    """
    Manually retry a failed/needs_review job safely using Fencing Token check
    to prevent duplicate submission.
    """
    stmt = select(WaybillJob).where(WaybillJob.id == job_id)
    job = (await session.execute(stmt)).scalar_one_or_none()

    if not job:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Job not found")

    # Reject if currently running or claimed to prevent duplicate execution
    if job.status in (JobStatus.RUNNING, JobStatus.CLAIMED, JobStatus.IN_PROGRESS):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Job #{job_id} is currently in active state '{job.status}'. Manual retry rejected to prevent duplicate submission.",
        )

    # Check active execution or dispatch intent fencing token
    exec_stmt = select(Execution).where(Execution.job_id == str(job_id), Execution.status == "running")
    active_execution = (await session.execute(exec_stmt)).scalar_one_or_none()

    if active_execution:
        provided_token = req.fencing_token if req else None
        if provided_token is not None and provided_token != active_execution.fencing_token:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Fencing token mismatch: active execution token is {active_execution.fencing_token}, provided token is {provided_token}.",
            )
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Job #{job_id} has an active running execution (ID: {active_execution.id}).",
        )

    # Allow retry from FAILED, NEEDS_REVIEW, WAITING_RETRY only.
    # C4 fix: UNKNOWN and CANCELLED are NOT retryable here.
    #  - UNKNOWN means the portal mutation outcome is unproven; the ONLY safe
    #    path is reconciliation (POST /api/v1/admin/alerts/reconcile/{job_id}).
    #    The state machine also forbids unknown → pending, so the old code was a
    #    guaranteed HTTP 500.
    #  - CANCELLED is terminal in the state machine (empty outgoing edges), so
    #    the old code raised StateTransitionError → HTTP 500 as well.
    valid_retry_statuses = {
        JobStatus.FAILED,
        JobStatus.NEEDS_REVIEW,
        JobStatus.WAITING_RETRY,
    }
    if job.status not in valid_retry_statuses:
        guidance = (
            "use POST /api/v1/admin/alerts/reconcile/{job_id} first"
            if job.status == JobStatus.UNKNOWN
            else "cancelled jobs are terminal; create a new job instead"
        )
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                f"Cannot retry job #{job_id} in status '{job.status}'. "
                f"{guidance[0].upper() + guidance[1:]}"
            ),
        )

    # C4 fix: mirror the client endpoint's SUBMISSION_UNCONFIRMED guard. A job
    # whose portal mutation may have landed MUST NOT be reset to PENDING and
    # resubmitted without three-witness confirmation — that is exactly the
    # duplicate-waybill scenario the project red line forbids.
    unretryable_categories = {
        "submission_unconfirmed",
        "ambiguous_mutation",
        "duplicate_submission",
    }
    current_category = (job.error_category or "").strip().lower()
    if current_category in unretryable_categories:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                f"Job #{job_id} has error_category '{current_category}' (unconfirmed portal mutation). "
                f"Direct resubmission risks a DUPLICATE waybill. "
                f"Run reconciliation first via POST /api/v1/admin/alerts/reconcile/{job_id}; "
                f"only after it resolves to failed/needs_review with a safe category can this job be retried."
            ),
        )

    # Transition job back to PENDING (or WAITING_RETRY)
    try:
        # Reset consecutive unknown attempts tracking
        if job.result_json:
            meta = dict(job.result_json)
            meta["consecutive_unknowns"] = 0
            job.result_json = meta

        JobStateMachine.transition(
            session,
            job,
            JobStatus.PENDING,
            expected_from={job.status},
            attempt_count=(job.attempt_count or 0) + 1,
            last_error=None,
            error_category=None,
        )
        await session.commit()
        await session.refresh(job)
    except Exception as exc:
        await session.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to transition job status for retry: {exc}",
        ) from exc

    return {
        "status": "success",
        "job_id": job.id,
        "new_status": job.status,
        "retry_count": job.attempt_count,
    }


@router.post(
    "/alerts/webhook",
    summary="دریافت هشدارهای ارسالی از Alertmanager",
)
async def alertmanager_webhook(
    request: Request,
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    import hashlib
    import hmac
    import time

    from app.core.config import utcms_config
    from app.models.admin import AdminAlert

    # 1. Access control (fail-closed)
    #    - With ALERT_WEBHOOK_SECRET configured: HMAC signature is mandatory.
    #    - Without a secret the endpoint MUST NOT be reachable through the public
    #      edge. Nginx always stamps proxied requests with an X-Request-ID it
    #      generates itself, while Alertmanager calls the backend directly over
    #      the internal Docker network without that header. So a request that
    #      carries X-Request-ID came through nginx → reject with 403.
    secret = utcms_config.ALERT_WEBHOOK_SECRET
    if not secret and request.headers.get("X-Request-ID"):
        logger.warning("alert_webhook_rejected_public_request_without_secret")
        raise HTTPException(
            status_code=403,
            detail="Alert webhook requires ALERT_WEBHOOK_SECRET to accept edge-proxied requests",
        )
    if secret:
        timestamp = request.headers.get("X-Barpro-Timestamp")
        signature = request.headers.get("X-Barpro-Signature")

        if not timestamp or not signature:
            raise HTTPException(status_code=403, detail="Missing signature headers")

        # Check timestamp age (max 5 minutes)
        try:
            ts = float(timestamp)
            if abs(time.time() - ts) > 300:
                raise HTTPException(status_code=403, detail="Signature timestamp expired")
        except ValueError as exc:
            raise HTTPException(status_code=403, detail="Invalid signature timestamp") from exc

        raw_body = await request.body()
        message_to_sign = f"{timestamp}.".encode() + raw_body
        expected_sig = hmac.new(secret.encode("utf-8"), message_to_sign, hashlib.sha256).hexdigest()

        if not hmac.compare_digest(expected_sig, signature):
            raise HTTPException(status_code=403, detail="Invalid signature")

    # 2. Process alerts
    try:
        body = await request.json()
    except Exception as exc:
        raise HTTPException(status_code=400, detail="Invalid JSON payload") from exc

    alerts = body.get("alerts", [])
    processed = 0

    for alert_data in alerts:
        status = alert_data.get("status")  # firing / resolved
        labels = alert_data.get("labels", {})
        annotations = alert_data.get("annotations", {})

        alertname = labels.get("alertname", "UnknownAlert")
        severity = labels.get("severity", "warning")
        worker_id = labels.get("worker_id")

        message = annotations.get("description") or annotations.get("summary") or f"Alert {alertname} ({status})"
        dedupe_key = f"alertmanager_{alertname}_{worker_id or 'global'}"

        if status == "firing":
            await admin_alert_service.create_alert(
                session=session,
                severity=severity,
                category=alertname,
                message=message,
                dedupe_key=dedupe_key,
                details={"labels": labels, "annotations": annotations, "startsAt": alert_data.get("startsAt")},
            )
            processed += 1
        elif status == "resolved":
            # Find and auto-acknowledge resolved alert
            existing_alert_stmt = select(AdminAlert).where(AdminAlert.dedupe_key == dedupe_key)
            existing_alert = (await session.execute(existing_alert_stmt)).scalar_one_or_none()
            if existing_alert and not existing_alert.is_acknowledged:
                await admin_alert_service.acknowledge_alert(
                    session, alert_id=existing_alert.id, admin_id=0
                )  # 0 represents system
                processed += 1

    return {"status": "success", "processed_alerts": processed}

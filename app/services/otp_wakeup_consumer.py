"""Event-driven wake-up consumer and auto-completion for pending waybill jobs on OTP arrival."""

from __future__ import annotations

import asyncio
import json
import logging
import re
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlmodel import col, select

from app.automation.otp_keys import (
    OTP_ACTIVE_PENDING_JOBS_SET,
    consume_scoped_otp,
    normalize_phone_for_otp_key,
    otp_pending_phone_key,
)
from app.core.database import async_session_factory
from app.core.redis_client import redis_manager
from app.models_multitenant import Driver, TaskStatus, WaybillJob

logger = logging.getLogger(__name__)

OTP_STREAM_KEY = "rpa:otp:stream"
OTP_STREAM_GROUP = "barpro_otp_group"


def trigger_job_completion_on_otp_received(phone: str, code: str) -> None:
    """Non-blocking background launcher when an OTP is accepted by the webhook."""
    try:
        loop = asyncio.get_running_loop()
        loop.create_task(resolve_and_complete_pending_job_for_otp(phone=phone, code=code))
    except RuntimeError:
        # No running event loop (e.g. called from synchronous context or during test teardown)
        pass


async def resolve_single_flight_pending_phone() -> str | None:
    """Identify the driver phone when exactly one pending waybill job is awaiting OTP.

    Solves the Iranian SIM card MSISDN limitation where Android forwarders
    cannot detect their own phone number and send only the gateway sender address.
    """
    try:
        redis = await redis_manager.get()
        if redis and hasattr(redis, "smembers"):
            active_jobs = await redis.smembers(OTP_ACTIVE_PENDING_JOBS_SET)
            if active_jobs and len(active_jobs) == 1:
                single_job_id = list(active_jobs)[0]
                if isinstance(single_job_id, bytes):
                    single_job_id = single_job_id.decode()
                cached_raw = await redis.get(f"rpa:job:pending_doc:{single_job_id}")
                if cached_raw:
                    data = json.loads(cached_raw)
                    phone = normalize_phone_for_otp_key(data.get("driver_phone"))
                    if re.fullmatch(r"09[0-9]{9}", phone):
                        logger.info(
                            "single_flight_attribution_resolved_from_redis",
                            extra={"extra_fields": {"job_id": single_job_id, "phone": phone}},
                        )
                        return phone
    except Exception as exc:
        logger.warning("single_flight_redis_check_failed: %s", exc)

    # Fallback to database check
    try:
        async with async_session_factory() as session:
            cutoff = datetime.now(UTC).replace(tzinfo=None) - timedelta(minutes=4)
            statement = select(WaybillJob).where(
                col(WaybillJob.status).in_(
                    [
                        TaskStatus.UNKNOWN.value,
                        TaskStatus.NEEDS_REVIEW.value,
                        TaskStatus.RECONCILING.value,
                        TaskStatus.PENDING.value,
                    ]
                ),
                col(WaybillJob.updated_at) >= cutoff,
            )
            candidates = (await session.exec(statement)).all()
            otp_candidates = []
            for j in candidates:
                res_dict = j.result_json if isinstance(j.result_json, dict) else {}
                has_doc = bool(res_dict.get("document_id") or (j.last_error and "شناسه" in j.last_error))
                if has_doc or j.error_category == "otp_required":
                    otp_candidates.append(j)

            if len(otp_candidates) == 1:
                target = otp_candidates[0]
                payload = target.payload_json if isinstance(target.payload_json, dict) else {}
                driver_mobile = payload.get("vehicle", {}).get("driver_mobile")
                if not driver_mobile and target.driver_id:
                    driver = await session.get(Driver, target.driver_id)
                    if driver:
                        driver_mobile = driver.phone
                clean = normalize_phone_for_otp_key(driver_mobile)
                if re.fullmatch(r"09[0-9]{9}", clean):
                    logger.info(
                        "single_flight_attribution_resolved_from_db",
                        extra={"extra_fields": {"job_id": target.job_id, "phone": clean}},
                    )
                    return clean
    except Exception as exc:
        logger.warning("single_flight_db_check_failed: %s", exc)

    return None


async def resolve_and_complete_pending_job_for_otp(phone: str, code: str) -> dict[str, Any] | None:
    """Find a pending waybill job waiting for this driver's OTP and complete it immediately.

    This resolves the 125-second late SMS condition: even if the Celery worker
    timed out at 120s and left the job in UNKNOWN, the arrival of the OTP at 125s
    will wake up the workflow, issue the document via IssueDocumentByOtp,
    mark the job SUCCESS, and consume the OTP keys.
    """
    clean_phone = normalize_phone_for_otp_key(phone)
    if not clean_phone:
        return None

    redis = await redis_manager.get()
    pending_job_id: str | None = None
    if redis:
        pending_key = otp_pending_phone_key(clean_phone)
        if pending_key:
            raw_id = await redis.get(pending_key)
            if raw_id:
                pending_job_id = raw_id.decode() if isinstance(raw_id, bytes) else str(raw_id)

    async with async_session_factory() as session:
        target_job: WaybillJob | None = None
        if pending_job_id:
            target_job = (await session.exec(select(WaybillJob).where(WaybillJob.job_id == pending_job_id))).first()

        if not target_job:
            # Query recent candidate jobs for this driver
            cutoff = datetime.now(UTC).replace(tzinfo=None) - timedelta(minutes=10)
            statement = (
                select(WaybillJob)
                .where(
                    col(WaybillJob.status).in_(
                        [
                            TaskStatus.UNKNOWN.value,
                            TaskStatus.NEEDS_REVIEW.value,
                            TaskStatus.RECONCILING.value,
                            TaskStatus.PENDING.value,
                        ]
                    ),
                    col(WaybillJob.updated_at) >= cutoff,
                )
                .order_by(col(WaybillJob.updated_at).desc())
            )
            recent_jobs = (await session.exec(statement)).all()
            for job in recent_jobs:
                p = job.payload_json if isinstance(job.payload_json, dict) else {}
                j_phone = normalize_phone_for_otp_key(p.get("vehicle", {}).get("driver_mobile"))
                if j_phone == clean_phone:
                    target_job = job
                    break
                if not j_phone and job.driver_id:
                    d = await session.get(Driver, job.driver_id)
                    if d and normalize_phone_for_otp_key(d.phone) == clean_phone:
                        target_job = job
                        break

        if not target_job:
            logger.debug("no_pending_waybill_found_for_otp_phone", extra={"extra_fields": {"phone": clean_phone}})
            return None

        if target_job.status == TaskStatus.SUCCESS.value:
            # Already completed
            if redis:
                await consume_scoped_otp(redis, job_id=target_job.job_id, driver_phone=clean_phone)
            return {"success": True, "job_id": target_job.job_id, "already_completed": True}

        try:
            from app.services.waybill_job_service import WaybillJobService

            admin_context = {"role": "master_admin"}
            logger.info(
                "attempting_auto_completion_via_otp",
                extra={"extra_fields": {"job_id": target_job.job_id, "phone": clean_phone}},
            )
            response = await WaybillJobService.submit_otp(
                user_context=admin_context,
                job_id=target_job.job_id,
                session=session,
                otp_code=code,
            )
            res_dict = response.result_json if isinstance(response.result_json, dict) else {}
            tracking_code = res_dict.get("tracking_code") or response.document_id

            # Notify any worker that might still be waiting
            if redis:
                completed_payload = json.dumps({"tracking_code": str(tracking_code or "")})
                await redis.set(f"rpa:job:completed_otp:{target_job.job_id}", completed_payload, ex=60)
                await consume_scoped_otp(redis, job_id=target_job.job_id, driver_phone=clean_phone)

            logger.info(
                "otp_auto_completion_succeeded",
                extra={"extra_fields": {"job_id": target_job.job_id, "tracking_code": tracking_code}},
            )
            return {"success": True, "job_id": target_job.job_id, "tracking_code": tracking_code}
        except Exception as exc:
            logger.warning(
                "otp_auto_completion_failed",
                extra={"extra_fields": {"job_id": target_job.job_id, "error": str(exc)}},
            )
            return {"success": False, "job_id": target_job.job_id, "error": str(exc)}


async def process_otp_stream_events(batch_size: int = 10) -> int:
    """Consume durable OTP events from Redis Stream rpa:otp:stream.

    Guarantees event-driven delivery survives worker restarts and reconnections.
    """
    redis = await redis_manager.get()
    if not redis or not hasattr(redis, "xreadgroup"):
        return 0

    try:
        try:
            await redis.xgroup_create(OTP_STREAM_KEY, OTP_STREAM_GROUP, id="$", mkstream=True)
        except Exception:
            # Group already exists
            pass

        messages = await redis.xreadgroup(
            OTP_STREAM_GROUP,
            "consumer_1",
            {OTP_STREAM_KEY: ">"},
            count=batch_size,
            block=1000,
        )
        if not messages:
            return 0

        processed = 0
        for _stream, stream_messages in messages:
            for message_id, data in stream_messages:
                try:
                    payload_raw = data.get(b"payload") or data.get("payload")
                    if payload_raw:
                        payload_str = payload_raw.decode() if isinstance(payload_raw, bytes) else str(payload_raw)
                        entry = json.loads(payload_str)
                        phone = entry.get("phone", "")
                        code = entry.get("code", "")
                        if phone and code:
                            await resolve_and_complete_pending_job_for_otp(phone=phone, code=code)
                    await redis.xack(OTP_STREAM_KEY, OTP_STREAM_GROUP, message_id)
                    processed += 1
                except Exception as msg_err:
                    logger.warning("otp_stream_message_process_error: %s", msg_err)

        return processed
    except Exception as exc:
        logger.warning("process_otp_stream_events_failed: %s", exc)
        return 0

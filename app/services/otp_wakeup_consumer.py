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


def _safe_json_dict(val: Any) -> dict[str, Any]:
    """Safely decode JSON string or return dict; returns empty dict on any failure."""
    if isinstance(val, dict):
        return val
    if isinstance(val, str):
        try:
            parsed = json.loads(val)
            if isinstance(parsed, dict):
                return parsed
        except Exception:
            return {}
    return {}


def trigger_job_completion_on_otp_received(
    phone: str | None = None,
    code: str = "",
    job_id: str | None = None,
) -> None:
    """Non-blocking background launcher when an OTP is accepted by the webhook or manual intake."""
    try:
        loop = asyncio.get_running_loop()
        loop.create_task(resolve_and_complete_pending_job_for_otp(phone=phone, code=code, job_id=job_id))
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
            if active_jobs:
                valid_live_jobs: list[tuple[str, str]] = []
                stale_jobs: list[str] = []
                for j_raw in active_jobs:
                    j_id = j_raw.decode() if isinstance(j_raw, bytes) else str(j_raw)
                    cached_raw = await redis.get(f"rpa:job:pending_doc:{j_id}")
                    if cached_raw:
                        try:
                            data = json.loads(cached_raw)
                            phone = normalize_phone_for_otp_key(data.get("driver_phone"))
                            if re.fullmatch(r"09[0-9]{9}", phone):
                                valid_live_jobs.append((j_id, phone))
                            else:
                                stale_jobs.append(j_id)
                        except Exception:
                            stale_jobs.append(j_id)
                    else:
                        stale_jobs.append(j_id)

                if len(valid_live_jobs) > 1:
                    for sj in stale_jobs:
                        if hasattr(redis, "srem"):
                            await redis.srem(OTP_ACTIVE_PENDING_JOBS_SET, sj)
                    logger.warning(
                        "single_flight_attribution_ambiguous_redis",
                        extra={"extra_fields": {"count": len(valid_live_jobs)}},
                    )
                    return "AMBIGUOUS"

                if len(valid_live_jobs) == 1:
                    for sj in stale_jobs:
                        if hasattr(redis, "srem"):
                            await redis.srem(OTP_ACTIVE_PENDING_JOBS_SET, sj)
                    single_job_id, phone = valid_live_jobs[0]
                    logger.info(
                        "single_flight_attribution_resolved_from_redis",
                        extra={"extra_fields": {"job_id": single_job_id, "phone": phone}},
                    )
                    return phone

                # If no jobs had pending_doc cached (e.g. synthetic unit tests)
                if len(active_jobs) > 1:
                    logger.warning(
                        "single_flight_attribution_ambiguous_redis",
                        extra={"extra_fields": {"count": len(active_jobs)}},
                    )
                    return "AMBIGUOUS"
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
                        TaskStatus.WAITING_RETRY.value,
                        TaskStatus.RETRYING.value,
                    ]
                ),
                col(WaybillJob.updated_at) >= cutoff,
            )
            candidates = (await session.exec(statement)).all()
            otp_candidates = []
            for j in candidates:
                res_dict = _safe_json_dict(j.result_json)
                has_doc = bool(res_dict.get("document_id") or (j.last_error and "شناسه" in j.last_error))
                if has_doc or j.error_category == "otp_required":
                    otp_candidates.append(j)

            if len(otp_candidates) > 1:
                logger.warning(
                    "single_flight_attribution_ambiguous_db",
                    extra={"extra_fields": {"count": len(otp_candidates)}},
                )
                return "AMBIGUOUS"

            if len(otp_candidates) == 1:
                target = otp_candidates[0]
                payload = _safe_json_dict(target.payload_json)
                driver_mobile = (
                    payload.get("vehicle", {}).get("driver_mobile")
                    or payload.get("driver", {}).get("phone")
                    or payload.get("driver", {}).get("mobile")
                    or payload.get("driver_phone")
                    or payload.get("driver_mobile")
                )
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


async def resolve_and_complete_pending_job_for_otp(
    phone: str | None = None,
    code: str = "",
    job_id: str | None = None,
) -> dict[str, Any] | None:
    """Find a pending waybill job waiting for this driver's OTP and complete it immediately.

    This resolves the 125-second late SMS condition: even if the Celery worker
    timed out at 120s and left the job in UNKNOWN, the arrival of the OTP at 125s
    will wake up the workflow, issue the document via IssueDocumentByOtp,
    mark the job SUCCESS, and consume the OTP keys.
    """
    clean_phone = normalize_phone_for_otp_key(phone) if phone else None
    if not clean_phone and not job_id:
        return None

    redis = await redis_manager.get()
    pending_job_id: str | None = job_id
    if not pending_job_id and redis and clean_phone:
        pending_key = otp_pending_phone_key(clean_phone)
        if pending_key:
            raw_id = await redis.get(pending_key)
            if raw_id:
                pending_job_id = raw_id.decode() if isinstance(raw_id, bytes) else str(raw_id)

    async with async_session_factory() as session:
        target_job: WaybillJob | None = None
        if pending_job_id:
            target_job = (await session.exec(select(WaybillJob).where(WaybillJob.job_id == pending_job_id))).first()

        if not target_job and clean_phone:
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
                            TaskStatus.WAITING_RETRY.value,
                            TaskStatus.RETRYING.value,
                        ]
                    ),
                    col(WaybillJob.updated_at) >= cutoff,
                )
                .order_by(col(WaybillJob.updated_at).desc())
            )
            recent_jobs = (await session.exec(statement)).all()
            for job in recent_jobs:
                p = _safe_json_dict(job.payload_json)
                raw_m = (
                    p.get("vehicle", {}).get("driver_mobile")
                    or p.get("driver", {}).get("phone")
                    or p.get("driver", {}).get("mobile")
                    or p.get("driver_phone")
                    or p.get("driver_mobile")
                )
                j_phone = normalize_phone_for_otp_key(raw_m)
                if j_phone == clean_phone:
                    target_job = job
                    break
                if not j_phone and job.driver_id:
                    d = await session.get(Driver, job.driver_id)
                    if d and normalize_phone_for_otp_key(d.phone) == clean_phone:
                        target_job = job
                        break

        if not target_job:
            logger.debug(
                "no_pending_waybill_found_for_otp",
                extra={"extra_fields": {"phone": clean_phone, "job_id": job_id}},
            )
            return None

        # If clean_phone was missing, try to derive it from target_job for cleanup
        if not clean_phone:
            pj = _safe_json_dict(target_job.payload_json)
            m_cand = (
                pj.get("vehicle", {}).get("driver_mobile")
                or pj.get("driver", {}).get("phone")
                or pj.get("driver", {}).get("mobile")
                or pj.get("driver_phone")
                or pj.get("driver_mobile")
            )
            if not m_cand and target_job.driver_id:
                drv = await session.get(Driver, target_job.driver_id)
                if drv:
                    m_cand = drv.phone
            clean_phone = normalize_phone_for_otp_key(m_cand) if m_cand else None

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
            res_dict = _safe_json_dict(response.result_json)
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
                        job_id = entry.get("job_id")
                        if job_id and code:
                            await resolve_and_complete_pending_job_for_otp(phone=phone, code=code, job_id=job_id)
                        elif phone and code:
                            await resolve_and_complete_pending_job_for_otp(phone=phone, code=code)
                    await redis.xack(OTP_STREAM_KEY, OTP_STREAM_GROUP, message_id)
                    processed += 1
                except Exception as msg_err:
                    logger.warning("otp_stream_message_process_error: %s", msg_err)

        return processed
    except Exception as exc:
        logger.warning("process_otp_stream_events_failed: %s", exc)
        return 0

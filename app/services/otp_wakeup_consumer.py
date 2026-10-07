"""Event-driven wake-up consumer and auto-completion for pending waybill jobs on OTP arrival."""

from __future__ import annotations

import asyncio
import json
import logging
import math
import re
import time
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

from fastapi import HTTPException
from redis.exceptions import ResponseError
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
    """Wake the control consumer; intake must already have persisted a stream event."""

    def publish() -> None:
        try:
            from app.core.config import utcms_config
            from app.workers.tasks import sweep_otp_stream

            sweep_otp_stream.apply_async(queue=utcms_config.RPA_SCHEDULER_QUEUE, expires=4, retry=False)
        except Exception:
            logger.warning("otp_stream_wakeup_deferred_to_beat", exc_info=True)

    try:
        asyncio.get_running_loop().run_in_executor(None, publish)
    except RuntimeError:
        logger.info("otp_stream_wakeup_deferred_to_beat_no_event_loop")


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

                for stale_job in stale_jobs:
                    await redis.srem(OTP_ACTIVE_PENDING_JOBS_SET, stale_job)

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


OTP_STREAM_CLAIM_IDLE_MS = 30_000
OTP_COMPLETABLE_STATUSES = {"unknown", "needs_review", "reconciling", "running", "in_progress"}


def otp_worker_index(worker_id: Any) -> int | None:
    """Parse only the explicit worker identity, never the API process's default IP."""
    raw = str(worker_id or "").split("@", 1)[0]
    match = re.fullmatch(r"(?:worker[_-])?(\d{1,3})", raw)
    return int(match.group(1)) if match and int(match.group(1)) > 0 else None


async def job_driver_phone(job: WaybillJob, session: Any) -> str:
    """Resolve cleanup/attribution only from the durable job's own tenant driver."""
    if job.driver_id:
        driver = await session.get(Driver, job.driver_id, populate_existing=True)
        if driver is not None and isinstance(getattr(driver, "phone", None), str):
            if driver.client_id != job.client_id:
                raise HTTPException(409, "Driver tenant does not match the OTP job")
            return normalize_phone_for_otp_key(driver.phone)
    payload = _safe_json_dict(job.payload_json)
    vehicle = _safe_json_dict(payload.get("vehicle"))
    driver_data = _safe_json_dict(payload.get("driver"))
    return normalize_phone_for_otp_key(
        vehicle.get("driver_mobile")
        or vehicle.get("driver_phone")
        or driver_data.get("phone")
        or driver_data.get("mobile")
        or payload.get("driver_phone")
        or payload.get("driver_mobile")
    )


def otp_event_is_current(entry: dict[str, Any]) -> bool:
    try:
        expires = float(entry.get("expires_at", 0))
        received = float(entry.get("received_at", entry.get("ingested_at", 0)))
        return (
            math.isfinite(expires)
            and math.isfinite(received)
            and expires > time.time()
            and 0 < received <= time.time() + 30
        )
    except (ValueError, TypeError):
        return False


async def store_job_otp_event(redis: Any, job: WaybillJob, code: str, phone: str) -> dict[str, Any]:
    """Durable manual intake, scoped to the current document before acknowledgement."""
    result = _safe_json_dict(job.result_json)
    challenge = _safe_json_dict(result.get("_otp_challenge"))
    now = time.time()
    entry = {
        "job_id": job.job_id,
        "document_id": str(result.get("document_id") or job.document_id or ""),
        "phone": phone,
        "code": code,
        "received_at": now,
        "ingested_at": now,
        "expires_at": now + 300,
        "message_id": uuid.uuid4().hex,
        "challenge_created_at": challenge.get("created_at"),
    }
    # One atomic write: no API acknowledgement with only a volatile wake-up.
    try:
        await redis.eval(
            """
local message = redis.call('XADD', KEYS[2], '*', 'payload', ARGV[1])
redis.call('SET', KEYS[1], ARGV[1], 'EX', 300)
return message
""",
            2,
            f"rpa:otp:job:{job.job_id}",
            OTP_STREAM_KEY,
            json.dumps(entry),
        )
    except Exception as exc:
        raise HTTPException(503, "OTP storage unavailable; retry delivery") from exc
    trigger_job_completion_on_otp_received(job_id=job.job_id)
    return entry


async def dispatch_otp_to_worker(redis: Any, job: WaybillJob, entry: dict[str, Any]) -> None:
    from app.workers.tasks import complete_otp_event

    challenge = _safe_json_dict(_safe_json_dict(job.result_json).get("_otp_challenge"))
    index = otp_worker_index(challenge.get("worker_id") or job.worker_id)
    if index is None:
        raise HTTPException(503, "OTP job has no verified owning worker")
    dispatch_key = f"rpa:otp:dispatch:{entry['message_id']}"
    if not await redis.set(dispatch_key, "1", nx=True, ex=30):
        return
    try:
        await asyncio.to_thread(
            complete_otp_event.apply_async,
            kwargs={"entry": entry},
            queue=f"rpa_submit_{index}",
            expires=max(1, int(float(entry["expires_at"]) - time.time())),
        )
    except Exception as exc:
        await redis.delete(dispatch_key)
        raise HTTPException(503, "OTP worker dispatch unavailable") from exc


async def resolve_and_complete_pending_job_for_otp(
    phone: str | None = None,
    code: str = "",
    job_id: str | None = None,
    *,
    entry: dict[str, Any] | None = None,
    execute: bool = False,
) -> dict[str, Any]:
    """Bind an event to one challenge, then route it to its owning worker."""
    event = dict(entry or {})
    if not otp_event_is_current(event):
        return {"success": False, "terminal": True, "error": "OTP event expired or missing original timestamp"}
    if (
        (job_id and event.get("job_id") and job_id != event["job_id"])
        or (
            phone
            and event.get("phone")
            and normalize_phone_for_otp_key(phone) != normalize_phone_for_otp_key(event["phone"])
        )
        or (code and event.get("code") and code != event["code"])
    ):
        return {"success": False, "terminal": True, "error": "OTP event attribution cannot be overridden"}
    clean_phone = normalize_phone_for_otp_key(phone or event.get("phone"))
    code = code or str(event.get("code") or "")
    pending_job_id = job_id or event.get("job_id")
    try:
        redis = await redis_manager.get()
        if redis is None:
            raise HTTPException(503, "OTP store unavailable")
        binding_key = f"rpa:otp:binding:{event.get('message_id', '')}"
        binding_raw = await redis.get(binding_key) if event.get("message_id") else None
        binding = _safe_json_dict(binding_raw.decode() if isinstance(binding_raw, bytes) else binding_raw)
        pending_job_id = binding.get("job_id") or pending_job_id
        if not pending_job_id and clean_phone:
            raw_id = await redis.get(otp_pending_phone_key(clean_phone))
            pending_job_id = raw_id.decode() if isinstance(raw_id, bytes) else raw_id
        if not pending_job_id:
            return {"success": False, "retryable": True, "error": "OTP challenge not yet available"}
        async with async_session_factory() as session:
            job = (await session.exec(select(WaybillJob).where(WaybillJob.job_id == pending_job_id))).first()
            if job is None:
                return {"success": False, "retryable": True, "error": "OTP job not yet available"}
            durable_phone = await job_driver_phone(job, session)
            if not durable_phone or (clean_phone and clean_phone != durable_phone):
                return {"success": False, "terminal": True, "error": "OTP phone does not match job driver"}
            result = _safe_json_dict(job.result_json)
            document_id = str(result.get("document_id") or job.document_id or "")
            if result.get("tracking_code"):
                await consume_scoped_otp(redis, job_id=job.job_id, driver_phone=durable_phone)
                return {"success": True, "terminal": True, "job_id": job.job_id, "already_completed": True}
            if not document_id:
                return {"success": False, "retryable": True, "error": "OTP document not persisted yet"}
            if str(binding.get("document_id") or event.get("document_id") or document_id) != document_id:
                return {"success": False, "terminal": True, "error": "OTP belongs to a different document"}
            challenge = _safe_json_dict(result.get("_otp_challenge"))
            created = float(challenge.get("created_at") or 0)
            if not created:
                return {"success": False, "retryable": True, "error": "OTP challenge not persisted yet"}
            if float(event.get("received_at", 0)) < created:
                return {"success": False, "terminal": True, "error": "OTP predates the pending challenge"}
            event.update(
                job_id=job.job_id,
                document_id=document_id,
                phone=durable_phone,
                message_id=event.get("message_id") or uuid.uuid4().hex,
            )
            binding_key = f"rpa:otp:binding:{event['message_id']}"
            wanted_binding = {"job_id": job.job_id, "document_id": document_id}
            await redis.set(
                binding_key,
                json.dumps(wanted_binding),
                nx=True,
                ex=max(1, int(float(event["expires_at"]) - time.time())),
            )
            actual_raw = await redis.get(binding_key)
            actual = _safe_json_dict(actual_raw.decode() if isinstance(actual_raw, bytes) else actual_raw)
            if actual != wanted_binding:
                return {"success": False, "terminal": True, "error": "OTP challenge binding changed"}
            from app.services.waybill_job_service import WaybillJobService

            response = await WaybillJobService.submit_otp(
                {"role": "master_admin"},
                job.job_id,
                session,
                code,
                _execute=execute,
                otp_event=event,
            )
            response_result = _safe_json_dict(response.result_json)
            tracking = response_result.get("tracking_code")
            if not tracking:
                return {"success": True, "queued": True, "job_id": job.job_id}
            await consume_scoped_otp(redis, job_id=job.job_id, driver_phone=durable_phone)
            return {"success": True, "terminal": True, "job_id": job.job_id, "tracking_code": tracking}
    except HTTPException as exc:
        retryable = exc.status_code in {429, 503}
        return {"success": False, "retryable": retryable, "terminal": not retryable, "error": str(exc.detail)}
    except Exception:
        logger.warning("otp_completion_infrastructure_error", exc_info=True)
        return {"success": False, "retryable": True, "error": "OTP completion infrastructure unavailable"}


async def acknowledge_otp_event(redis: Any, message_id: str) -> None:
    await redis.eval(
        "redis.call('XACK', KEYS[1], ARGV[1], ARGV[2]); return redis.call('XDEL', KEYS[1], ARGV[2])",
        1,
        OTP_STREAM_KEY,
        OTP_STREAM_GROUP,
        message_id,
    )


async def process_otp_stream_events(batch_size: int = 10) -> int:
    """Recover pending deliveries and route new events; workers ACK terminal outcomes."""
    redis = await redis_manager.get()
    if redis is None:
        return 0
    try:
        try:
            await redis.xgroup_create(OTP_STREAM_KEY, OTP_STREAM_GROUP, id="0", mkstream=True)
        except ResponseError as exc:
            if "BUSYGROUP" not in str(exc):
                raise
        cursor = await redis.get("rpa:otp:claim_cursor") or "0-0"
        recovered = await redis.xautoclaim(
            OTP_STREAM_KEY, OTP_STREAM_GROUP, "router", OTP_STREAM_CLAIM_IDLE_MS, start_id=cursor, count=batch_size
        )
        await redis.set("rpa:otp:claim_cursor", recovered[0])
        pending = list(recovered[1])
        if len(pending) < batch_size:
            messages = await redis.xreadgroup(
                OTP_STREAM_GROUP, "router", {OTP_STREAM_KEY: ">"}, count=batch_size - len(pending)
            )
            for _, rows in messages:
                pending.extend(rows)
        processed = 0
        for message_id, data in pending:
            try:
                raw = data.get(b"payload") or data.get("payload")
                entry = _safe_json_dict(raw.decode() if isinstance(raw, bytes) else raw)
                stream_id = message_id.decode() if isinstance(message_id, bytes) else str(message_id)
                entry["stream_id"] = stream_id
                entry.setdefault("message_id", stream_id)
                if not otp_event_is_current(entry):
                    await acknowledge_otp_event(redis, stream_id)
                    processed += 1
                    continue
                result = await resolve_and_complete_pending_job_for_otp(
                    phone=entry.get("phone"),
                    code=str(entry.get("code", "")),
                    job_id=entry.get("job_id"),
                    entry=entry,
                )
                if result and (result.get("terminal") or (result.get("success") and not result.get("queued"))):
                    await acknowledge_otp_event(redis, stream_id)
                processed += 1
            except Exception:
                logger.warning("otp_stream_event_retry_pending", exc_info=True)
        return processed
    except Exception:
        logger.warning("otp_stream_consumer_unavailable", exc_info=True)
        return 0

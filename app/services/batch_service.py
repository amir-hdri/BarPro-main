"""Multi-route batch: expands N route templates into target_count concrete waybill jobs.

The expansion writes a fully-populated ``payload_json`` (sender/receiver/cargo/vehicle
from the batch's base payload, plus origin/destination from each route) and staggers
``submit_after`` by ``interval_minutes``, so the existing scheduler and worker process
them without modification. ``batch_id``/``route_template_id``/``sequence_index``/
``distance_km``/``duration_min`` are kept for tracking/reporting.
"""

from __future__ import annotations

import random
import re
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from fastapi import HTTPException
from sqlalchemy import func
from sqlalchemy.exc import IntegrityError
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.automation.multitenant_payload_adapter import (
    build_enhanced_waybill_payload,
    validate_enhanced_waybill_payload,
)
from app.core.distance import estimate_time
from app.models.waybill_batch import WaybillBatch
from app.models.waybill_route_template import WaybillRouteTemplate
from app.models_multitenant import Driver, DriverPlate, TaskStatus, WaybillJob

REPEAT_MODES = {"round_robin", "random", "sequential"}

_TEHRAN_TZ = ZoneInfo("Asia/Tehran")

_PERSIAN_DIGITS = "۰۱۲۳۴۵۶۷۸۹"
_ARABIC_DIGITS = "٠١٢٣٤٥٦٧٨٩"


def _normalize_national_code(value: Any) -> str:
    """Normalize Persian/Arabic digits and strip non-digits for code comparison."""
    s = str(value or "")
    for i in range(10):
        s = s.replace(_PERSIAN_DIGITS[i], str(i)).replace(_ARABIC_DIGITS[i], str(i))
    return re.sub(r"\D", "", s)


def select_route_index(step: int, num_routes: int, repeat_mode: str) -> int:
    """Pure, deterministic route selection for a given expansion step.

    round_robin → ``step % num_routes``; random → uniform pick;
    sequential → ``min(step, num_routes - 1)`` (advances once per step, then sticks to the last route).
    """
    if num_routes <= 0:
        raise ValueError("num_routes must be >= 1")
    mode = repeat_mode or "round_robin"
    if mode == "random":
        return random.randrange(num_routes)
    if mode == "sequential":
        return min(step, num_routes - 1)
    return step % num_routes


def build_job_payload(route: WaybillRouteTemplate, base_payload: dict[str, Any] | None = None) -> dict[str, Any]:
    """Produce a ``WaybillMapRequest``-compatible payload.

    ``base_payload`` carries the constant waybill parts (sender/receiver/cargo/vehicle/
    financial). The route's origin/destination override those keys. This matches the
    structure consumed by ``build_enhanced_waybill_payload`` in the worker.
    """
    payload: dict[str, Any] = dict(base_payload or {})
    payload.update(
        {
            "route_source": "user_text",
            "location_mode": "user_text",
            "origin": {
                "province": route.origin_province or "",
                "city": route.origin_city or "",
                "address": route.origin_address or "",
                "coordinates": None,
                "location_mode": "user_text",
                "route_source": "user_text",
            },
            "destination": {
                "province": route.dest_province or "",
                "city": route.dest_city or "",
                "address": route.dest_address or "",
                "coordinates": None,
                "location_mode": "user_text",
                "route_source": "user_text",
            },
        }
    )
    return payload


def _validate_route_location(route: WaybillRouteTemplate) -> list[str]:
    """Return the list of missing origin/destination fields for a route."""
    errors: list[str] = []
    for label, province, city, address in (
        ("مبدأ", route.origin_province, route.origin_city, route.origin_address),
        ("مقصد", route.dest_province, route.dest_city, route.dest_address),
    ):
        if not (province or "").strip() or len((province or "").strip()) < 2:
            errors.append(f"استان {label}")
        if not (city or "").strip() or len((city or "").strip()) < 2:
            errors.append(f"شهر {label}")
        if not (address or "").strip() or len((address or "").strip()) < 2:
            errors.append(f"آدرس {label}")
    return errors


def estimate_route_duration_minutes(route: WaybillRouteTemplate) -> float:
    """Return the best available travel-time estimate for one route.

    A persisted UTCMS/Neshan duration is authoritative. When only a measured
    distance exists, use the project's deterministic road estimate. Missing
    distance data is represented as zero: the chain still remains ordered and
    the configured anti-spam interval is preserved, but no address or GPS is
    invented.
    """
    try:
        duration = float(route.duration_min or 0)
    except (TypeError, ValueError):
        duration = 0.0
    if duration > 0:
        return duration

    try:
        distance = float(route.distance_km or 0)
    except (TypeError, ValueError):
        distance = 0.0
    if distance <= 0:
        return 0.0

    is_urban = bool(
        route.origin_city
        and route.dest_city
        and str(route.origin_city).strip() == str(route.dest_city).strip()
    )
    return max(1.0, estimate_time(distance, is_urban=is_urban))


def build_route_chain_schedule(
    routes: list[WaybillRouteTemplate],
    interval_minutes: int,
    start_at: datetime,
) -> list[datetime]:
    """Compute release times for an ordered chain without mutating state.

    The first leg is eligible immediately. Each following leg is released no
    earlier than the previous leg's estimated travel time plus the configured
    spacing. The scheduler also checks the previous job's actual SUCCESS state,
    so a late completion can never cause an early submission.
    """
    spacing = max(0, int(interval_minutes or 0))
    release_times: list[datetime] = []
    cursor = start_at
    for index, _route in enumerate(routes):
        if index:
            cursor += timedelta(minutes=estimate_route_duration_minutes(routes[index - 1]) + spacing)
        release_times.append(cursor)
    return release_times


def _utcnow() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


def _tehran_today_start_utc() -> datetime:
    """Tehran-local midnight expressed as naive UTC (matches ``finished_at`` storage)."""
    tehran_now = _utcnow().replace(tzinfo=UTC).astimezone(_TEHRAN_TZ)
    tehran_midnight = tehran_now.replace(hour=0, minute=0, second=0, microsecond=0)
    return tehran_midnight.astimezone(UTC).replace(tzinfo=None)


class BatchService:
    async def _load_owned_routes(
        self, session: AsyncSession, client_id: int, route_ids: list[int]
    ) -> list[WaybillRouteTemplate]:
        if not route_ids:
            raise HTTPException(status_code=422, detail="حداقل یک مسیر لازم است")
        if len(set(route_ids)) != len(route_ids):
            raise HTTPException(status_code=422, detail="شناسه‌های مسیر تکراری مجاز نیستند")
        statement = select(WaybillRouteTemplate).where(
            WaybillRouteTemplate.id.in_(route_ids),
            WaybillRouteTemplate.client_id == client_id,
        )
        routes = list((await session.exec(statement)).all())
        if len(routes) != len(route_ids):
            raise HTTPException(status_code=404, detail="برخی مسیرها یافت نشدند یا متعلق به شما نیستند")
        order = {route.id: route for route in routes}
        return [order[rid] for rid in route_ids]

    async def create_batch(
        self,
        session: AsyncSession,
        client_id: int,
        payload: Any,
        idempotency_key: str | None = None,
    ) -> WaybillBatch:
        mode = payload.repeat_mode or "round_robin"
        if mode not in REPEAT_MODES:
            raise HTTPException(status_code=422, detail="repeat_mode نامعتبر است")

        # Idempotency: a repeated request with the same key returns the existing batch.
        if idempotency_key:
            existing = (
                await session.exec(
                    select(WaybillBatch).where(
                        WaybillBatch.idempotency_key == idempotency_key,
                        WaybillBatch.client_id == client_id,
                    )
                )
            ).first()
            if existing is not None:
                return existing

        # Tenant isolation: the driver must belong to the requesting client.
        driver = (
            await session.exec(select(Driver).where((Driver.client_id == client_id) & (Driver.id == payload.driver_id)))
        ).first()
        if driver is None:
            raise HTTPException(status_code=404, detail="راننده یافت نشد یا متعلق به شما نیست")

        routes = await self._load_owned_routes(session, client_id, payload.route_template_ids)

        base_payload = dict(getattr(payload, "base_payload_json", None) or {})
        if not base_payload:
            raise HTTPException(status_code=422, detail="base_payload_json الزامی است")

        # Enrich vehicle from the authoritative driver record (100% accuracy):
        # the driver's national code is authoritative; plate/vehicle_type come from
        # the driver's active DriverPlate when the base payload omits them.
        raw_vehicle = base_payload.get("vehicle")
        vehicle = dict(raw_vehicle) if isinstance(raw_vehicle, dict) else {}
        code = _normalize_national_code(vehicle.get("driver_national_code"))
        if code and code != _normalize_national_code(driver.driver_national_code):
            raise HTTPException(status_code=422, detail="کد ملی راننده در payload با رانندهٔ انتخابی مطابقت ندارد")
        vehicle["driver_national_code"] = driver.driver_national_code
        if not str(vehicle.get("plate") or "").strip():
            plate = (
                await session.exec(
                    select(DriverPlate)
                    .where(DriverPlate.driver_id == driver.id, DriverPlate.status == "active")
                    .order_by(DriverPlate.id.desc())
                )
            ).first()
            if plate is not None:
                vehicle["plate"] = plate.plate_number
                if not str(vehicle.get("type") or "").strip():
                    vehicle["type"] = plate.vehicle_type
        base_payload["vehicle"] = vehicle

        # 100%-accuracy gate: reject incomplete routes up front.
        for route in routes:
            route_errors = _validate_route_location(route)
            if route_errors:
                raise HTTPException(status_code=422, detail=f"مسیر «{route.name}» ناقص است: " + "، ".join(route_errors))

        if payload.route_chain and payload.target_count != len(routes):
            raise HTTPException(
                status_code=422,
                detail=(
                    "در حالت زنجیره‌ای، تعداد بارنامه‌ها باید دقیقاً برابر تعداد مسیرهای انتخاب‌شده باشد "
                    f"(مسیرها={len(routes)}، target_count={payload.target_count})"
                ),
            )

        # Validate the merged payload against the live worker contract so every
        # job passes preflight validation (no silent NEEDS_REVIEW at runtime).
        sample_payload = build_job_payload(routes[0], base_payload)
        base_errors = validate_enhanced_waybill_payload(
            build_enhanced_waybill_payload(sample_payload), enforce_live_party_phones=True
        )
        if base_errors:
            raise HTTPException(status_code=422, detail="بارنامه پایه ناقص است: " + "، ".join(base_errors))

        batch = WaybillBatch(
            client_id=client_id,
            idempotency_key=idempotency_key,
            driver_id=payload.driver_id,
            name=getattr(payload, "name", None),
            route_template_ids=[r.id for r in routes],
            base_payload_json=base_payload,
            target_count=payload.target_count,
            repeat_mode=mode,
            route_chain=bool(payload.route_chain),
            interval_minutes=payload.interval_minutes,
            status="active",
            progress={"completed": 0, "failed": 0, "today": 0},
        )
        session.add(batch)
        try:
            await session.flush()  # assign batch.id for FK linkage
        except IntegrityError:
            # A concurrent request with the same (client_id, idempotency_key) won the race.
            await session.rollback()
            if idempotency_key:
                existing = (
                    await session.exec(
                        select(WaybillBatch).where(
                            WaybillBatch.client_id == client_id,
                            WaybillBatch.idempotency_key == idempotency_key,
                        )
                    )
                ).first()
                if existing is not None:
                    return existing
            raise

        now = _utcnow()
        priority = getattr(payload, "priority", 5)
        chain_schedule = (
            build_route_chain_schedule(routes, payload.interval_minutes, now) if payload.route_chain else None
        )
        jobs: list[WaybillJob] = []
        for step in range(payload.target_count):
            route_index = step if payload.route_chain else select_route_index(step, len(routes), mode)
            route = routes[route_index]
            jobs.append(
                WaybillJob(
                    job_id=str(uuid.uuid4()),
                    idempotency_key=str(uuid.uuid4()),
                    client_id=client_id,
                    driver_id=payload.driver_id,
                    status=TaskStatus.PENDING.value,
                    payload_json=build_job_payload(route, base_payload),
                    priority=priority,
                    batch_id=batch.id,
                    route_template_id=route.id,
                    sequence_index=step,
                    distance_km=route.distance_km,
                    duration_min=route.duration_min,
                    # In a route chain, release times are cumulative travel-time
                    # estimates. The scheduler additionally requires the prior
                    # leg to be reconciled SUCCESS before dispatching this job.
                    submit_after=(
                        chain_schedule[step]
                        if chain_schedule is not None
                        else now + timedelta(minutes=step * payload.interval_minutes)
                    ),
                )
            )
        session.add_all(jobs)
        await session.commit()
        await session.refresh(batch)
        return batch

    async def get_progress(self, session: AsyncSession, batch_id: int, client_id: int) -> dict[str, Any]:
        batch = await session.get(WaybillBatch, batch_id)
        if batch is None or batch.client_id != client_id:
            raise HTTPException(status_code=404, detail="batch یافت نشد")

        completed = (
            await session.exec(
                select(func.count(WaybillJob.id)).where(
                    WaybillJob.batch_id == batch_id,
                    WaybillJob.status == TaskStatus.SUCCESS.value,
                )
            )
        ).one()
        failed = (
            await session.exec(
                select(func.count(WaybillJob.id)).where(
                    WaybillJob.batch_id == batch_id,
                    WaybillJob.status.in_(
                        [TaskStatus.FAILED.value, TaskStatus.NEEDS_REVIEW.value, TaskStatus.DEAD_LETTER.value]
                    ),
                )
            )
        ).one()
        today_start = _tehran_today_start_utc()
        today = (
            await session.exec(
                select(func.count(WaybillJob.id)).where(
                    WaybillJob.batch_id == batch_id,
                    WaybillJob.status == TaskStatus.SUCCESS.value,
                    WaybillJob.finished_at >= today_start,
                )
            )
        ).one()

        target = batch.target_count or 0
        route_chain = bool(getattr(batch, "route_chain", False))
        next_sequence: int | None = None
        blocked_by_sequence: int | None = None
        if route_chain:
            chain_jobs = list(
                (
                    await session.exec(
                        select(WaybillJob)
                        .where(WaybillJob.batch_id == batch_id)
                        .order_by(WaybillJob.sequence_index.asc())
                    )
                ).all()
            )
            for chain_job in chain_jobs:
                if chain_job.status == TaskStatus.SUCCESS.value:
                    continue
                next_sequence = chain_job.sequence_index
                if next_sequence and next_sequence > 0:
                    previous = next(
                        (item for item in chain_jobs if item.sequence_index == next_sequence - 1),
                        None,
                    )
                    if previous is not None and previous.status in {
                        TaskStatus.FAILED.value,
                        TaskStatus.NEEDS_REVIEW.value,
                        TaskStatus.DEAD_LETTER.value,
                        TaskStatus.CANCELLED.value,
                    }:
                        blocked_by_sequence = previous.sequence_index
                break
        return {
            "batch_id": batch.id,
            "target": target,
            "completed": completed,
            "failed": failed,
            "today": today,
            "progress_percent": min(int(completed / target * 100), 100) if target else 0,
            "status": batch.status,
            "route_chain": route_chain,
            "next_sequence": next_sequence,
            "blocked_by_sequence": blocked_by_sequence,
        }


batch_service = BatchService()

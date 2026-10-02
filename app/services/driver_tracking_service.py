"""Per-plate driver registration tracking with 15-day Jalali periods.

For every vehicle plate this service reports:
  - ``today_count``   (ثبت امروز): successful registrations created today (Tehran)
  - ``target_count``    (تعداد هدف ثبت): operator-set target per 15-day period
  - ``period_total``    (کل ثبت): successful registrations in the current
    15-day Jalali period. Because totals are computed from the period window,
    the counter returns to zero automatically when a period ends — no
    destructive scheduled reset is needed.

A registration counts as «ثبت» when the waybill reached UTCMS, i.e. the job
status is one of ``success`` / ``issued`` / ``in_transit`` / ``delivered``.
Failed, cancelled or still-running jobs are not counted.
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any

from sqlmodel import col, select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.core.jalali import get_tracking_period, jalali_day_bounds_utc, tehran_today_jalali
from app.models_multitenant import Client, Driver, DriverPlate, WaybillJob
from app.schemas.multitenant import (
    DriverTrackingItem,
    DriverTrackingResponse,
    TrackingPeriodResponse,
)

logger = logging.getLogger(__name__)

# Waybill job statuses that mean "registered on UTCMS" (ثبت شده).
REGISTERED_STATUSES = ("success", "issued", "in_transit", "delivered")

_PERSIAN_DIGITS = "۰۱۲۳۴۵۶۷۸۹"
_ARABIC_DIGITS = "٠١٢٣٤٥٦٧٨٩"


def _to_latin_digits(value: str) -> str:
    out = []
    for ch in value:
        if ch in _PERSIAN_DIGITS:
            out.append(str(_PERSIAN_DIGITS.index(ch)))
        elif ch in _ARABIC_DIGITS:
            out.append(str(_ARABIC_DIGITS.index(ch)))
        else:
            out.append(ch)
    return "".join(out)


def canonicalize_plate_loose(value: Any) -> str | None:
    """Best-effort plate canonicalization that never raises (for matching)."""
    if not isinstance(value, str):
        return None
    compact = "".join(_to_latin_digits(value).split()).replace("-", "")
    return compact or None


def extract_payload_plate(payload: Any) -> str | None:
    """Extract the plate number from a waybill payload (mirrors the frontend parser)."""
    if isinstance(payload, str):
        try:
            import json

            payload = json.loads(payload)
        except Exception:
            return None
    if not isinstance(payload, dict):
        return None

    plate = payload.get("plate_number")
    if isinstance(plate, str) and plate.strip():
        return canonicalize_plate_loose(plate)
    plate = payload.get("vehicle_plate")
    if isinstance(plate, str) and plate.strip():
        return canonicalize_plate_loose(plate)
    vehicle = payload.get("vehicle")
    if isinstance(vehicle, dict):
        plate = vehicle.get("plate_number")
        if isinstance(plate, str) and plate.strip():
            return canonicalize_plate_loose(plate)
        plate = vehicle.get("plate")
        if isinstance(plate, dict):
            parts = [plate.get("two_digits"), plate.get("letter"), plate.get("three_digits"), plate.get("iran_code")]
            if all(isinstance(p, str) and p for p in parts):
                return canonicalize_plate_loose(f"{parts[0]}{parts[1]}{parts[2]}ایران{parts[3]}")
    return None


class DriverTrackingService:
    """Compute per-plate registration stats for the current 15-day period."""

    @staticmethod
    async def get_driver_tracking(
        user_context: dict | Client,
        session: AsyncSession,
        now: datetime | None = None,
    ) -> DriverTrackingResponse:
        period = get_tracking_period(now)
        start_at: datetime = period["start_at"]
        end_at: datetime = period["end_at"]

        if isinstance(user_context, Client):
            user_context = {"role": "client", "user": user_context}
        role = user_context.get("role")
        if role == "master_admin":
            plate_stmt = select(DriverPlate)
            job_stmt = select(WaybillJob)
        else:
            client = user_context["user"]
            assert isinstance(client, Client)
            plate_stmt = select(DriverPlate).where(DriverPlate.client_id == client.id)
            job_stmt = select(WaybillJob).where(WaybillJob.client_id == client.id)

        plates = (await session.exec(plate_stmt.order_by(col(DriverPlate.id).asc()))).all()

        driver_names: dict[int, str] = {}
        if plates:
            driver_ids = {p.driver_id for p in plates}
            drivers = (await session.exec(select(Driver).where(col(Driver.id).in_(driver_ids)))).all()
            driver_names = {d.id: (d.full_name or "") for d in drivers if d.id is not None}

        # One query for the whole scope: successful registrations in the period.
        jobs = (
            await session.exec(
                job_stmt.where(
                    col(WaybillJob.status).in_(REGISTERED_STATUSES),
                    WaybillJob.created_at >= start_at,
                    WaybillJob.created_at < end_at,
                )
            )
        ).all()

        today_j = tehran_today_jalali(now)
        today_start, _ = jalali_day_bounds_utc(*today_j)

        # plate_id -> [period_total, today_count]
        counters: dict[int, list[int]] = {p.id: [0, 0] for p in plates if p.id is not None}
        # driver_id -> list of plate ids (ascending) for fallback attribution
        driver_plates: dict[int, list[int]] = {}
        plate_by_number: dict[int, dict[str, int]] = {}
        for p in plates:
            if p.id is None:
                continue
            driver_plates.setdefault(p.driver_id, []).append(p.id)
            plate_by_number.setdefault(p.driver_id, {})[p.plate_number] = p.id

        for job in jobs:
            driver_id = job.driver_id
            if driver_id is None or driver_id not in driver_plates:
                continue
            target_plate_id: int | None = None
            payload_plate = extract_payload_plate(job.payload_json)
            if payload_plate:
                target_plate_id = plate_by_number[driver_id].get(payload_plate)
                if target_plate_id is None:
                    logger.debug(
                        "tracking_job_plate_unmatched",
                        extra={"extra_fields": {"job_id": job.id, "payload_plate": payload_plate}},
                    )
                    continue
            else:
                # Legacy payload without plate info: attribute to the driver's
                # first (primary) plate.
                target_plate_id = driver_plates[driver_id][0]
            counters[target_plate_id][0] += 1
            if job.created_at is not None and job.created_at >= today_start:
                counters[target_plate_id][1] += 1

        items = [
            DriverTrackingItem(
                plate_id=p.id,
                plate_number=p.plate_number,
                driver_id=p.driver_id,
                driver_name=driver_names.get(p.driver_id, ""),
                vehicle_type=p.vehicle_type,
                status=p.status,
                target_count=p.target_count or 0,
                round_trip=bool(p.round_trip),
                in_transport=bool(p.in_transport),
                today_count=counters[p.id][1],
                period_total=counters[p.id][0],
            )
            for p in plates
            if p.id is not None
        ]

        sy, sm, sd = period["start_jalali"]
        ey, em, ed = period["end_jalali"]
        return DriverTrackingResponse(
            period=TrackingPeriodResponse(
                phase=period["phase"],
                label=period["label"],
                start_jalali=f"{sy:04d}-{sm:02d}-{sd:02d}",
                end_jalali=f"{ey:04d}-{em:02d}-{ed:02d}",
                start_at=start_at,
                end_at=end_at,
            ),
            items=items,
        )

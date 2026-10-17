"""Multi-route batch: expands N route templates into target_count concrete waybill jobs.

The expansion writes a fully-populated ``payload_json`` (sender/receiver/cargo/vehicle
from the batch's base payload, plus origin/destination from each route) and staggers
``submit_after`` by ``interval_minutes``, so the existing scheduler and worker process
them without modification. ``batch_id``/``route_template_id``/``sequence_index``/
``distance_km``/``duration_min`` are kept for tracking/reporting.
"""

from __future__ import annotations

import copy
import random
import re
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any, cast
from zoneinfo import ZoneInfo

from fastapi import HTTPException
from sqlalchemy import func
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import InstrumentedAttribute
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.automation.mobile_payload_adapter import validate_mobile_source_payload
from app.automation.multitenant_payload_adapter import (
    build_enhanced_waybill_payload,
    validate_live_waybill_payload,
)
from app.core.distance import estimate_time
from app.models.waybill_batch import WaybillBatch
from app.models.waybill_route_template import WaybillRouteTemplate
from app.models_multitenant import Driver, DriverPlate, TaskStatus, WaybillJob
from app.schemas.multitenant import _normalize_plate

REPEAT_MODES = {"round_robin", "random", "sequential"}
BATCH_MODES = {"standard", "round_trip_cycling", "one_way_repeated"}

IRAN_ADJACENT_PROVINCES: dict[str, set[str]] = {
    "همدان": {"همدان", "مرکزی", "لرستان", "کرمانشاه", "کردستان", "زنجان", "قزوین"},
    "مرکزی": {"مرکزی", "همدان", "لرستان", "اصفهان", "قم", "تهران", "البرز", "قزوین"},
    "تهران": {"تهران", "البرز", "مازندران", "سمنان", "قم", "مرکزی"},
    "البرز": {"البرز", "تهران", "مازندران", "قزوین", "مرکزی"},
    "اصفهان": {
        "اصفهان",
        "تهران",
        "قم",
        "مرکزی",
        "لرستان",
        "چهارمحال و بختیاری",
        "کهگیلویه و بویراحمد",
        "فارس",
        "یزد",
        "سمنان",
    },
    "فارس": {"فارس", "اصفهان", "یزد", "کرمان", "هرمزگان", "بوشهر", "کهگیلویه و بویراحمد"},
    "خراسان رضوی": {"خراسان رضوی", "خراسان شمالی", "خراسان جنوبی", "سمنان", "گلستان"},
    "خراسان جنوبی": {"خراسان جنوبی", "خراسان رضوی", "یزد", "کرمان", "سیستان و بلوچستان", "سمنان"},
    "خراسان شمالی": {"خراسان شمالی", "خراسان رضوی", "سمنان", "گلستان"},
    "آذربایجان شرقی": {"آذربایجان شرقی", "آذربایجان غربی", "اردبیل", "زنجان"},
    "آذربایجان غربی": {"آذربایجان غربی", "آذربایجان شرقی", "کردستان", "زنجان"},
    "اردبیل": {"اردبیل", "آذربایجان شرقی", "گیلان", "زنجان"},
    "گیلان": {"گیلان", "اردبیل", "زنجان", "قزوین", "مازندران"},
    "مازندران": {"مازندران", "گیلان", "قزوین", "البرز", "تهران", "سمنان", "گلستان"},
    "گلستان": {"گلستان", "مازندران", "سمنان", "خراسان شمالی", "خراسان رضوی"},
    "سمنان": {
        "سمنان",
        "مازندران",
        "گلستان",
        "خراسان شمالی",
        "خراسان رضوی",
        "خراسان جنوبی",
        "یزد",
        "اصفهان",
        "قم",
        "تهران",
    },
    "قم": {"قم", "تهران", "مرکزی", "اصفهان", "سمنان"},
    "قزوین": {"قزوین", "گیلان", "مازندران", "البرز", "مرکزی", "همدان", "زنجان"},
    "زنجان": {"زنجان", "اردبیل", "آذربایجان شرقی", "آذربایجان غربی", "کردستان", "همدان", "قزوین", "گیلان"},
    "کردستان": {"کردستان", "آذربایجان غربی", "زنجان", "همدان", "کرمانشاه"},
    "کرمانشاه": {"کرمانشاه", "کردستان", "همدان", "لرستان", "ایلام"},
    "لرستان": {"لرستان", "همدان", "مرکزی", "اصفهان", "چهارمحال و بختیاری", "خوزستان", "ایلام", "کرمانشاه"},
    "ایلام": {"ایلام", "کرمانشاه", "لرستان", "خوزستان"},
    "خوزستان": {"خوزستان", "ایلام", "لرستان", "چهارمحال و بختیاری", "کهگیلویه و بویراحمد", "بوشهر"},
    "چهارمحال و بختیاری": {"چهارمحال و بختیاری", "اصفهان", "لرستان", "خوزستان", "کهگیلویه و بویراحمد"},
    "کهگیلویه و بویراحمد": {"کهگیلویه و بویراحمد", "اصفهان", "چهارمحال و بختیاری", "خوزستان", "بوشهر", "فارس"},
    "بوشهر": {"بوشهر", "خوزستان", "کهگیلویه و بویراحمد", "فارس", "هرمزگان"},
    "هرمزگان": {"هرمزگان", "بوشهر", "فارس", "کرمان", "سیستان و بلوچستان"},
    "کرمان": {"کرمان", "یزد", "فارس", "هرمزگان", "سیستان و بلوچستان", "خراسان جنوبی"},
    "یزد": {"یزد", "اصفهان", "فارس", "کرمان", "خراسان جنوبی", "سمنان"},
    "سیستان و بلوچستان": {"سیستان و بلوچستان", "خراسان جنوبی", "کرمان", "هرمزگان"},
}


_TEHRAN_TZ = ZoneInfo("Asia/Tehran")

_PERSIAN_DIGITS = "۰۱۲۳۴۵۶۷۸۹"
_ARABIC_DIGITS = "٠١٢٣٤٥٦٧٨٩"

# SQLModel declares table columns as their plain Python types on the class, so
# class-level attribute access (e.g. WaybillJob.id) types as int | None while the
# runtime value is a SQLAlchemy InstrumentedAttribute. These aliases cast to the
# real runtime type for query-builder usage; cast() is a runtime no-op.
_route_template_id_col = cast(InstrumentedAttribute[int | None], WaybillRouteTemplate.id)
_plate_id_col = cast(InstrumentedAttribute[int | None], DriverPlate.id)
_job_id_col = cast(InstrumentedAttribute[int | None], WaybillJob.id)
_job_status_col = cast(InstrumentedAttribute[str], WaybillJob.status)
_job_finished_at_col = cast(InstrumentedAttribute[datetime | None], WaybillJob.finished_at)
_job_sequence_index_col = cast(InstrumentedAttribute[int | None], WaybillJob.sequence_index)


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


def _route_coordinates(lat: Any, lng: Any) -> dict[str, float] | None:
    """Return a ``{"lat": …, "lng": …}`` mapping when the route carries usable GPS.

    Returns ``None`` for missing, non-numeric, out-of-range, or (0, 0) values so
    callers never invent a location the route template does not actually have.
    """
    try:
        lat_f = float(lat) if lat is not None else None
        lng_f = float(lng) if lng is not None else None
    except (TypeError, ValueError):
        return None
    if lat_f is None or lng_f is None:
        return None
    if not (-90.0 <= lat_f <= 90.0 and -180.0 <= lng_f <= 180.0):
        return None
    if lat_f == 0.0 and lng_f == 0.0:
        return None
    return {"lat": lat_f, "lng": lng_f}


def _merge_route_location(
    base_location: Any,
    *,
    province: str | None,
    city: str | None,
    address: str | None,
    lat: Any,
    lng: Any,
) -> dict[str, Any]:
    """Merge a route endpoint over the base location without dropping base keys.

    Postal codes live only in the base payload (route templates carry no postal
    columns), so a blind overwrite would silently discard them and doom the job
    on the live mobile transport. Route GPS wins when present; otherwise any
    base coordinates are preserved.
    """
    merged: dict[str, Any] = dict(base_location) if isinstance(base_location, dict) else {}
    coords = _route_coordinates(lat, lng)
    if coords is None:
        raw_coords = merged.get("coordinates")
        coords = dict(raw_coords) if isinstance(raw_coords, dict) else None
        if coords is None:
            base_lat = merged.get("lat", merged.get("latitude"))
            base_lng = merged.get("lng", merged.get("lon", merged.get("longitude")))
            coords = _route_coordinates(base_lat, base_lng)
    merged.update(
        {
            "province": province or "",
            "city": city or "",
            "address": address or "",
            "location_mode": "user_text",
            "route_source": "user_text",
        }
    )
    if coords is not None:
        merged["lat"] = coords["lat"]
        merged["lng"] = coords["lng"]
        merged["coordinates"] = coords
    else:
        merged["coordinates"] = None
    return merged


def build_job_payload(route: WaybillRouteTemplate, base_payload: dict[str, Any] | None = None) -> dict[str, Any]:
    """Produce a ``WaybillMapRequest``-compatible payload.

    ``base_payload`` carries the constant waybill parts (sender/receiver/cargo/vehicle/
    financial). The route's origin/destination override the location keys while
    preserving base-only keys (postal codes, coordinate fallback). This matches the
    structure consumed by ``build_enhanced_waybill_payload`` in the worker.
    """
    base: dict[str, Any] = dict(base_payload or {})
    payload: dict[str, Any] = dict(base)
    payload.update(
        {
            "route_source": "user_text",
            "location_mode": "user_text",
            "origin": _merge_route_location(
                base.get("origin"),
                province=route.origin_province,
                city=route.origin_city,
                address=route.origin_address,
                lat=route.origin_lat,
                lng=route.origin_lng,
            ),
            "destination": _merge_route_location(
                base.get("destination"),
                province=route.dest_province,
                city=route.dest_city,
                address=route.dest_address,
                lat=route.dest_lat,
                lng=route.dest_lng,
            ),
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
        if not (address or "").strip() or len((address or "").strip()) < 5:
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
        route.origin_city and route.dest_city and str(route.origin_city).strip() == str(route.dest_city).strip()
    )
    return max(1.0, estimate_time(distance, is_urban=is_urban))


def route_schedule_metric_error(route: WaybillRouteTemplate) -> str | None:
    """Explain why a route cannot drive distance-based chain scheduling."""
    if estimate_route_duration_minutes(route) > 0:
        return None
    return f"مسیر «{route.name}» فاصله یا زمان تخمینی معتبر ندارد"


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


def invert_waybill_payload(forward_payload: dict[str, Any]) -> dict[str, Any]:
    """Invert a waybill payload for return leg (B -> A) with Smart Inversion.

    Swaps origin <-> destination locations and sender <-> receiver parties, ensuring
    party postal codes remain aligned with their respective cities.
    """
    inverted = copy.deepcopy(forward_payload)

    # 1. Invert structured locations
    orig = dict(inverted.get("origin") or {})
    dest = dict(inverted.get("destination") or {})
    inverted["origin"] = dest
    inverted["destination"] = orig

    # 2. Invert parties (Smart Role Swap)
    sender = dict(inverted.get("sender") or {})
    receiver = dict(inverted.get("receiver") or {})
    inverted["sender"] = receiver
    inverted["receiver"] = sender

    # Synchronize party postal codes to origin/dest postal codes if present
    if dest.get("postal_code") and not inverted["sender"].get("postal_code"):
        inverted["sender"]["postal_code"] = dest["postal_code"]
    if orig.get("postal_code") and not inverted["receiver"].get("postal_code"):
        inverted["receiver"]["postal_code"] = orig["postal_code"]

    # Invert flat location keys if present
    for k_orig, k_dest in (
        ("origin_province", "dest_province"),
        ("origin_city", "dest_city"),
        ("origin_address", "dest_address"),
        ("origin_postal_code", "dest_postal_code"),
        ("origin_lat", "dest_lat"),
        ("origin_lng", "dest_lng"),
    ):
        if k_orig in inverted or k_dest in inverted:
            v_orig = inverted.get(k_orig)
            v_dest = inverted.get(k_dest)
            inverted[k_orig] = v_dest
            inverted[k_dest] = v_orig

    # Invert flat party keys if present
    for k_s, k_r in (
        ("sender_national_code", "receiver_national_code"),
        ("sender_name", "receiver_name"),
        ("sender_phone", "receiver_phone"),
        ("sender_postal_code", "receiver_postal_code"),
    ):
        if k_s in inverted or k_r in inverted:
            v_s = inverted.get(k_s)
            v_r = inverted.get(k_r)
            inverted[k_s] = v_r
            inverted[k_r] = v_s

    inverted["is_return_trip"] = True
    return inverted


def get_driver_fleet_scope(driver: Driver) -> tuple[str | None, str | None]:
    """Extract driver's licensed activity city and province from metadata or defaults."""
    meta = driver.metadata_json or {}
    defaults = driver.default_payload_json or {}

    city = meta.get("activity_city") or meta.get("fleet_city") or meta.get("city")
    if not city:
        city = (defaults.get("origin") or {}).get("city") or defaults.get("origin_city")

    province = meta.get("activity_province") or meta.get("fleet_province") or meta.get("province")
    if not province:
        province = (defaults.get("origin") or {}).get("province") or defaults.get("origin_province")

    return (str(city).strip() if city else None, str(province).strip() if province else None)


def validate_driver_fleet_scope(
    driver: Driver,
    origin_city: str | None,
    dest_province: str | None,
) -> None:
    """Pre-dispatch gate to prevent UTCMS 4028 (city scope) and 4045 (province scope) rejections."""
    licensed_city, licensed_province = get_driver_fleet_scope(driver)

    # 1. Code 4028 gate: origin city must match driver's activity city if specified
    if licensed_city and origin_city:
        clean_orig = str(origin_city).strip()
        clean_lic = str(licensed_city).strip()
        if clean_orig != clean_lic and clean_orig not in clean_lic and clean_lic not in clean_orig:
            raise HTTPException(
                status_code=422,
                detail=(
                    f"مبدأ بارنامه («{clean_orig}») با شهر پروانه فعالیت راننده («{clean_lic}») "
                    "همخوانی ندارد. صدور سند حمل صرفاً در محدوده شهر/شهرستان پروانه امکان‌پذیر است (پیشگیری از خطای ۴۰۲۸ کشوری)."
                ),
            )

    # 2. Code 4045 gate: destination province must be licensed province or adjacent
    if licensed_province and dest_province:
        clean_dest = str(dest_province).strip()
        clean_prov = str(licensed_province).strip()
        adjacents = IRAN_ADJACENT_PROVINCES.get(clean_prov, {clean_prov})
        if clean_dest not in adjacents:
            raise HTTPException(
                status_code=422,
                detail=(
                    f"مقصد انتخابی («{clean_dest}») در استان پروانه ناوگان («{clean_prov}») یا استان‌های همجوار آن نیست "
                    "(پیشگیری از خطای ۴۰۴۵ کشوری)."
                ),
            )


def build_cycling_schedule(
    routes: list[WaybillRouteTemplate],
    batch_mode: str,
    cycles_count: int | None,
    repeat_count: int | None,
    buffer_minutes: int,
    start_at: datetime,
) -> tuple[int, list[datetime], list[bool]]:
    """Compute total count, release times, and is_return flags for cycling schedules."""
    buffer = max(10, int(buffer_minutes or 45))
    release_times: list[datetime] = []
    is_return_flags: list[bool] = []
    cursor = start_at
    route = routes[0]
    duration = max(1.0, estimate_route_duration_minutes(route))

    if batch_mode == "round_trip_cycling":
        cycles = max(1, int(cycles_count or 1))
        total_count = cycles * 2
        step_delta = timedelta(minutes=duration + buffer)
        for step in range(total_count):
            release_times.append(cursor)
            is_return = step % 2 == 1
            is_return_flags.append(is_return)
            cursor += step_delta

    elif batch_mode == "one_way_repeated":
        reps = max(1, int(repeat_count or 1))
        total_count = reps
        # Outbound trip + rest/unloading buffer + empty return trip + reload buffer
        step_delta = timedelta(minutes=(duration * 2) + (buffer * 2))
        for _ in range(total_count):
            release_times.append(cursor)
            is_return_flags.append(False)
            cursor += step_delta

    else:
        total_count = len(routes)
        return total_count, [start_at] * total_count, [False] * total_count

    return total_count, release_times, is_return_flags


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
            _route_template_id_col.in_(route_ids),
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

        batch_mode = getattr(payload, "batch_mode", "standard") or "standard"
        if batch_mode not in BATCH_MODES:
            raise HTTPException(status_code=422, detail="batch_mode نامعتبر است")

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
        driver_status = getattr(driver.status, "value", driver.status)
        if str(driver_status).lower() != "active":
            raise HTTPException(status_code=409, detail="رانندهٔ انتخاب‌شده فعال نیست و امکان ایجاد دسته ندارد")

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
        provided_plate = str(vehicle.get("plate") or "").strip()
        normalized_provided_plate: str | None = None
        if provided_plate:
            try:
                normalized_provided_plate = _normalize_plate(provided_plate)
            except ValueError as exc:
                raise HTTPException(status_code=422, detail=str(exc)) from exc

        plate_query = select(DriverPlate).where(
            DriverPlate.driver_id == driver.id,
            DriverPlate.status == "active",
        )
        if normalized_provided_plate:
            plate_query = plate_query.where(DriverPlate.plate_number == normalized_provided_plate)
        plate = (await session.exec(plate_query.order_by(_plate_id_col.desc()))).first()
        if plate is None:
            raise HTTPException(
                status_code=422,
                detail=(
                    "پلاک ارسالی فعال نیست یا به این راننده تعلق ندارد"
                    if normalized_provided_plate
                    else "برای رانندهٔ انتخاب‌شده پلاک فعال ثبت نشده است"
                ),
            )
        vehicle["plate"] = plate.plate_number
        if not str(vehicle.get("type") or "").strip() and plate.vehicle_type:
            vehicle["type"] = plate.vehicle_type
        base_payload["vehicle"] = vehicle

        # 100%-accuracy gate: reject incomplete routes up front.
        for route in routes:
            route_errors = _validate_route_location(route)
            if route_errors:
                raise HTTPException(status_code=422, detail=f"مسیر «{route.name}» ناقص است: " + "، ".join(route_errors))
            # Validate fleet license scope against driver's registered activity scope
            validate_driver_fleet_scope(driver, route.origin_city, route.dest_province)

        is_route_chain = bool(payload.route_chain) or (batch_mode in {"round_trip_cycling", "one_way_repeated"})

        if batch_mode in {"round_trip_cycling", "one_way_repeated"}:
            metric_errors = [error for route in routes if (error := route_schedule_metric_error(route))]
            if metric_errors:
                raise HTTPException(
                    status_code=422,
                    detail=(
                        "برای زمان‌بندی چرخه، فاصله یا زمان تخمینی مثبت برای مسیرها الزامی است: "
                        + "، ".join(metric_errors)
                    ),
                )
        elif is_route_chain and payload.target_count != len(routes):
            raise HTTPException(
                status_code=422,
                detail=(
                    "در حالت زنجیره‌ای، تعداد بارنامه‌ها باید دقیقاً برابر تعداد مسیرهای انتخاب‌شده باشد "
                    f"(مسیرها={len(routes)}، target_count={payload.target_count})"
                ),
            )
        elif is_route_chain:
            metric_errors = [error for route in routes if (error := route_schedule_metric_error(route))]
            if metric_errors:
                raise HTTPException(
                    status_code=422,
                    detail=(
                        "برای زمان‌بندی زنجیره‌ای، فاصله یا زمان تخمینی مثبت برای همه مسیرها لازم است: "
                        + "، ".join(metric_errors)
                    ),
                )

        # Validate the merged payload against the live worker contract so every
        # job passes preflight validation (no silent NEEDS_REVIEW at runtime).
        # The mobile transport is the only live issuance path, so its stricter
        # gate (party national/postal codes, location postal codes + GPS,
        # explicit fare) runs here too — mirroring single-job creation.
        for route in routes:
            route_payload = build_job_payload(route, base_payload)
            enhanced_payload = build_enhanced_waybill_payload(route_payload)
            base_errors = validate_live_waybill_payload(
                enhanced_payload,
                expected_driver_national_code=driver.driver_national_code,
                expected_plate=plate.plate_number,
                expected_driver_mobile=driver.phone,
            )
            payload_errors = list(base_errors)
            for mobile_error in validate_mobile_source_payload(enhanced_payload):
                if mobile_error not in payload_errors:
                    payload_errors.append(mobile_error)
            if payload_errors:
                raise HTTPException(
                    status_code=422,
                    detail=f"بارنامهٔ مسیر «{route.name}» ناقص است: " + "، ".join(payload_errors),
                )

            if batch_mode == "round_trip_cycling":
                inverted_payload = invert_waybill_payload(route_payload)
                enhanced_inverted = build_enhanced_waybill_payload(inverted_payload)
                inv_base_errors = validate_live_waybill_payload(
                    enhanced_inverted,
                    expected_driver_national_code=driver.driver_national_code,
                    expected_plate=plate.plate_number,
                    expected_driver_mobile=driver.phone,
                )
                inv_errors = list(inv_base_errors)
                for mobile_error in validate_mobile_source_payload(enhanced_inverted):
                    if mobile_error not in inv_errors:
                        inv_errors.append(mobile_error)
                if inv_errors:
                    raise HTTPException(
                        status_code=422,
                        detail=f"بارنامهٔ برگشت مسیر «{route.name}» ناقص است: " + "، ".join(inv_errors),
                    )

        now = _utcnow()
        if batch_mode in {"round_trip_cycling", "one_way_repeated"}:
            total_target_count, release_times, is_return_flags = build_cycling_schedule(
                routes,
                batch_mode,
                getattr(payload, "cycles_count", None),
                getattr(payload, "repeat_count", None),
                getattr(payload, "buffer_minutes", 45),
                now,
            )
        else:
            total_target_count = payload.target_count
            release_times = (
                build_route_chain_schedule(routes, payload.interval_minutes, now)
                if is_route_chain
                else [now + timedelta(minutes=step * payload.interval_minutes) for step in range(total_target_count)]
            )
            is_return_flags = [False] * total_target_count

        batch = WaybillBatch(
            client_id=client_id,
            idempotency_key=idempotency_key,
            driver_id=payload.driver_id,
            name=getattr(payload, "name", None),
            route_template_ids=[r.id for r in routes],
            base_payload_json=base_payload,
            target_count=total_target_count,
            repeat_mode=mode,
            route_chain=is_route_chain,
            interval_minutes=payload.interval_minutes,
            status="active",
            progress={
                "completed": 0,
                "failed": 0,
                "today": 0,
                "batch_mode": batch_mode,
                "cycles_count": getattr(payload, "cycles_count", None),
                "repeat_count": getattr(payload, "repeat_count", None),
                "buffer_minutes": getattr(payload, "buffer_minutes", 45),
                "smart_inversion": getattr(payload, "smart_inversion", True),
            },
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

        priority = getattr(payload, "priority", 5)
        jobs: list[WaybillJob] = []
        for step in range(total_target_count):
            route_index = (
                0
                if batch_mode in {"round_trip_cycling", "one_way_repeated"}
                else (step if is_route_chain else select_route_index(step, len(routes), mode))
            )
            route = routes[route_index]
            is_return = is_return_flags[step] if step < len(is_return_flags) else False

            forward_job_payload = build_job_payload(route, base_payload)
            job_payload = (
                invert_waybill_payload(forward_job_payload)
                if (is_return and getattr(payload, "smart_inversion", True))
                else forward_job_payload
            )

            jobs.append(
                WaybillJob(
                    job_id=str(uuid.uuid4()),
                    idempotency_key=str(uuid.uuid4()),
                    client_id=client_id,
                    driver_id=payload.driver_id,
                    status=TaskStatus.PENDING.value,
                    payload_json=job_payload,
                    priority=priority,
                    batch_id=batch.id,
                    route_template_id=route.id,
                    sequence_index=step,
                    distance_km=route.distance_km,
                    duration_min=route.duration_min,
                    submit_after=release_times[step] if step < len(release_times) else now,
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
                select(func.count(_job_id_col)).where(
                    WaybillJob.batch_id == batch_id,
                    WaybillJob.status == TaskStatus.SUCCESS.value,
                )
            )
        ).one()
        failed = (
            await session.exec(
                select(func.count(_job_id_col)).where(
                    WaybillJob.batch_id == batch_id,
                    _job_status_col.in_(
                        [TaskStatus.FAILED.value, TaskStatus.NEEDS_REVIEW.value, TaskStatus.DEAD_LETTER.value]
                    ),
                )
            )
        ).one()
        today_start = _tehran_today_start_utc()
        today = (
            await session.exec(
                select(func.count(_job_id_col)).where(
                    WaybillJob.batch_id == batch_id,
                    WaybillJob.status == TaskStatus.SUCCESS.value,
                    _job_finished_at_col >= today_start,
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
                        .order_by(_job_sequence_index_col.asc())
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

        progress_data = batch.progress if isinstance(batch.progress, dict) else {}
        return {
            "batch_id": batch.id,
            "target": target,
            "completed": completed,
            "failed": failed,
            "today": today,
            "progress_percent": min(int(completed / target * 100), 100) if target else 0,
            "status": batch.status,
            "route_chain": route_chain,
            "batch_mode": progress_data.get("batch_mode", "standard"),
            "cycles_count": progress_data.get("cycles_count"),
            "repeat_count": progress_data.get("repeat_count"),
            "buffer_minutes": progress_data.get("buffer_minutes", 45),
            "next_sequence": next_sequence,
            "blocked_by_sequence": blocked_by_sequence,
        }


batch_service = BatchService()

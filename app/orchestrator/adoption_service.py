"""External Waybill Adoption Service.

Periodically queries driver accounts on UTCMS for waybills issued externally/manually,
creates tracked WaybillJob records with status='success', initializes their ShippingState,
and triggers the automated shipping lifecycle (RegisterStartOfShipping and RegisterEndOfShipping).
"""

from __future__ import annotations

import logging
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import cast, or_
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import col, select

from app.auth_multitenant import decrypt_driver_password
from app.automation.gps_shipping_manager import (
    ShippingState,
    auto_start_shipping,
    find_city_coordinates,
    get_or_login_client,
    init_shipping,
    save_shipping_state,
)
from app.automation.worker_proxy import get_worker_proxy_url
from app.core.database import async_session_factory
from app.models.waybill_route_template import WaybillRouteTemplate
from app.models_multitenant import Driver, WaybillJob

logger = logging.getLogger(__name__)


class ExternalWaybillAdoptionService:
    """Discovers externally issued UTCMS waybills and integrates them into the BarPro shipping lifecycle."""

    async def adopt_for_driver(self, session: AsyncSession, driver: Driver) -> list[WaybillJob]:
        """Query issued waybills for one driver and adopt any not currently tracked."""
        if not driver.utcms_password_encrypted or not driver.client_id:
            logger.info("adoption_skip_driver_no_credentials driver_id=%s", driver.id)
            return []

        proxy_url = get_worker_proxy_url()
        try:
            client = await get_or_login_client(
                national_code=driver.driver_national_code,
                password=decrypt_driver_password(driver.utcms_password_encrypted),
                proxy_url=proxy_url,
                client_id=driver.client_id,
            )
        except Exception as client_err:
            logger.warning(
                "adoption_login_client_failed driver_id=%s nat=%s err=%s",
                driver.id,
                driver.driver_national_code,
                client_err,
            )
            return []

        items: list[tuple[dict[str, Any], bool]] = []
        try:
            shipping_resp = await client.get_shipping_documents(
                page_number=1,
                page_size=20,
                driver_national_code=driver.driver_national_code,
            )
            raw_ship = shipping_resp.get("obj")
            ship_items = (
                raw_ship
                if isinstance(raw_ship, list)
                else (raw_ship.get("items") or raw_ship.get("list") or [raw_ship]) if isinstance(raw_ship, dict) else []
            )
            for s in ship_items:
                if isinstance(s, dict):
                    items.append((s, True))
        except Exception as ship_err:
            logger.warning("adoption_get_shipping_documents_non_fatal: %s", ship_err)

        try:
            docs_resp = await client.get_issued_documents(
                page_number=1,
                page_size=20,
                driver_national_code=driver.driver_national_code,
            )
            raw_docs = docs_resp.get("obj")
            doc_items = (
                raw_docs
                if isinstance(raw_docs, list)
                else (raw_docs.get("items") or raw_docs.get("list") or [raw_docs]) if isinstance(raw_docs, dict) else []
            )
            for d in doc_items:
                if isinstance(d, dict):
                    items.append((d, False))
        except Exception as docs_err:
            logger.warning("adoption_get_issued_documents_non_fatal: %s", docs_err)

        adopted_jobs: list[WaybillJob] = []

        for item, is_already_shipping in items:
            if not isinstance(item, dict):
                continue
            doc_id = str(item.get("id") or "").strip()
            doc_no = str(item.get("docNo") or "").strip()
            if not doc_id and not doc_no:
                continue

            # Check if this waybill is already tracked in WaybillJob
            query = select(WaybillJob).where(
                or_(
                    WaybillJob.document_id == doc_id,
                    cast(WaybillJob.result_json, JSONB)["tracking_code"].astext == doc_no,
                )
            )
            existing = (await session.exec(query)).first()
            if existing is not None:
                continue

            # Waybill not found in BarPro: adopt it!
            logger.info(
                "adopting_external_waybill driver_id=%s doc_id=%s doc_no=%s",
                driver.id,
                doc_id,
                doc_no,
            )

            source_city = str(item.get("sourceCityTitle") or "ملایر").strip()
            source_prov = str(item.get("sourceStateTitle") or "همدان").strip()
            dest_city = str(item.get("destCityTitle") or source_city).strip()
            dest_prov = str(item.get("destStateTitle") or source_prov).strip()

            # Attempt route template matching for this client
            template_query = (
                select(WaybillRouteTemplate)
                .where(
                    WaybillRouteTemplate.client_id == driver.client_id,
                    WaybillRouteTemplate.origin_city == source_city,
                    WaybillRouteTemplate.dest_city == dest_city,
                )
                .order_by(col(WaybillRouteTemplate.id).desc())
            )
            template = (await session.exec(template_query)).first()
            if template is None:
                fallback_template_query = (
                    select(WaybillRouteTemplate)
                    .where(WaybillRouteTemplate.client_id == driver.client_id)
                    .order_by(col(WaybillRouteTemplate.id).desc())
                )
                template = (await session.exec(fallback_template_query)).first()

            doc_coords_found = False
            if doc_id and str(doc_id).strip().isdigit():
                try:
                    doc_detail = await client._post("/Document/GetDocumentByID", {"id": int(str(doc_id).strip())})
                    doc_obj = doc_detail.get("obj") if isinstance(doc_detail, dict) else {}
                    if isinstance(doc_obj, dict) and doc_obj.get("sourceLat") and doc_obj.get("sourceLon"):
                        olat = float(doc_obj["sourceLat"])
                        olng = float(doc_obj["sourceLon"])
                        dlat = float(doc_obj.get("destLat") or (olat + 0.0018))
                        dlng = float(doc_obj.get("destLon") or (olng + 0.0018))
                        dist_km = 30.0 if abs(olat - dlat) > 0.05 or abs(olng - dlng) > 0.05 else 10.0
                        dur_min = 30.0
                        route_id = None
                        doc_coords_found = True
                except Exception:
                    pass

            if not doc_coords_found:
                if template and template.origin_lat and template.origin_lng:
                    olat = float(template.origin_lat)
                    olng = float(template.origin_lng)
                    dlat = float(template.dest_lat or template.origin_lat)
                    dlng = float(template.dest_lng or template.origin_lng)
                    dist_km = float(template.distance_km or 10.0)
                    dur_min = float(template.duration_min or 30.0)
                    route_id = template.id
                else:
                    city_coords = find_city_coordinates(source_city)
                    olat = city_coords[0] if city_coords else 34.2981
                    olng = city_coords[1] if city_coords else 48.8242
                    dlat = olat + 0.0018
                    dlng = olng + 0.0018
                    dist_km = 10.0
                    dur_min = 30.0
                    route_id = None

            now_utc = datetime.now(UTC)
            new_job_id = f"ext-{uuid.uuid4().hex[:12]}"
            idempotency_key = f"adopt-{doc_id or doc_no}"

            payload_json = {
                "transport": "mobile",
                "driver_national_code": driver.driver_national_code,
                "driver_id": driver.id,
                "origin_province": source_prov,
                "origin_city": source_city,
                "dest_province": dest_prov,
                "dest_city": dest_city,
                "origin_lat": olat,
                "origin_lng": olng,
                "dest_lat": dlat,
                "dest_lng": dlng,
                "distance_km": dist_km,
                "adopted_from_utcms": True,
                "external_doc_id": doc_id,
                "external_doc_no": doc_no,
            }

            result_json = {
                "status": "success",
                "tracking_code": doc_no,
                "document_id": doc_id,
                "adopted_external": True,
                "details": item,
            }

            job = WaybillJob(
                job_id=new_job_id,
                idempotency_key=idempotency_key,
                client_id=driver.client_id,
                driver_id=driver.id,
                status="success",
                source="adopted_external",
                scheduled_by="adoption_worker",
                payload_json=payload_json,
                result_json=result_json,
                document_id=doc_id,
                mutation_status="confirmed",
                reconciled_at=now_utc.replace(tzinfo=None),
                route_template_id=route_id,
                distance_km=dist_km,
                duration_min=dur_min,
                created_at=now_utc.replace(tzinfo=None),
                updated_at=now_utc.replace(tzinfo=None),
            )
            session.add(job)
            await session.commit()
            await session.refresh(job)

            if is_already_shipping:
                timer_str = str(item.get("dateTimeForTimer") or "").strip()
                estimated_end_str = ""
                if timer_str:
                    try:
                        dt_timer = datetime.fromisoformat(timer_str.replace(" ", "T"))
                        estimated_end_str = dt_timer.replace(tzinfo=UTC).isoformat()
                    except Exception:
                        pass
                if not estimated_end_str:
                    mins = int(item.get("minuteForShipping") or dur_min)
                    estimated_end_str = (now_utc + timedelta(minutes=mins)).isoformat()

                raw_start = item.get("shippingDateLatin")
                if raw_start:
                    try:
                        from zoneinfo import ZoneInfo

                        dt_local = datetime.fromisoformat(str(raw_start).replace(" ", "T"))
                        if dt_local.tzinfo is None:
                            dt_local = dt_local.replace(tzinfo=ZoneInfo("Asia/Tehran"))
                        start_time_str = dt_local.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%S.000Z")
                    except Exception:
                        start_time_str = now_utc.strftime("%Y-%m-%dT%H:%M:%S.000Z")
                else:
                    start_time_str = now_utc.strftime("%Y-%m-%dT%H:%M:%S.000Z")

                ship_state = ShippingState(
                    job_id=job.job_id,
                    doc_no=doc_no,
                    doc_id=doc_id,
                    status="in_transit",
                    origin_lat=olat,
                    origin_lng=olng,
                    dest_lat=dlat,
                    dest_lng=dlng,
                    distance_km=dist_km,
                    estimated_end_at=estimated_end_str,
                    created_at=start_time_str,
                    gps_list=[
                        {
                            "Latitude": olat,
                            "Longitude": olng,
                            "Type": 2,
                            "Date": start_time_str,
                            "Speed": 0,
                            "Altitude": 1000,
                            "Provider": "operator_anchor",
                            "Provenance": "registered_start_of_shipping",
                        }
                    ],
                )
                await save_shipping_state(ship_state)
                logger.info(
                    "adopted_already_shipping_waybill job=%s doc_id=%s estimated_end_at=%s",
                    job.job_id,
                    doc_id,
                    estimated_end_str,
                )
            else:
                # Initialize shipping state so shipping lifecycle executes
                try:
                    await init_shipping(
                        job_id=job.job_id,
                        doc_no=doc_no,
                        payload=payload_json,
                        doc_id=doc_id,
                        persist=True,
                    )
                except Exception as init_err:
                    logger.warning("adoption_init_shipping_fallback job=%s err=%s", job.job_id, init_err)
                    ship_state = ShippingState(
                        job_id=job.job_id,
                        doc_no=doc_no,
                        doc_id=doc_id,
                        status="ready",
                        origin_lat=olat,
                        origin_lng=olng,
                        dest_lat=dlat,
                        dest_lng=dlng,
                        distance_km=dist_km,
                        estimated_end_at=(now_utc + timedelta(minutes=dur_min)).isoformat(),
                        created_at=now_utc.isoformat(),
                    )
                    await save_shipping_state(ship_state)

                # Trigger automated start of shipping
                try:
                    start_res = await auto_start_shipping(job.job_id)
                    logger.info("adopted_waybill_start_shipping job=%s result=%s", job.job_id, start_res)
                except Exception as start_err:
                    logger.warning("adopted_waybill_start_shipping_failed job=%s err=%s", job.job_id, start_err)

            adopted_jobs.append(job)

        return adopted_jobs

    async def adopt_all_external_waybills(self) -> dict[str, Any]:
        """Iterate over all active drivers with encrypted credentials and adopt untracked waybills."""
        adopted: list[dict[str, Any]] = []
        errors: list[dict[str, Any]] = []
        scanned_drivers = 0

        async with async_session_factory() as session:
            query = select(Driver).where(
                Driver.status == "active",
                col(Driver.utcms_password_encrypted).isnot(None),
                col(Driver.client_id).isnot(None),
            )
            drivers = (await session.exec(query)).all()
            scanned_drivers = len(drivers)

            for driver in drivers:
                try:
                    jobs = await self.adopt_for_driver(session, driver)
                    for j in jobs:
                        adopted.append(
                            {
                                "job_id": j.job_id,
                                "driver_id": driver.id,
                                "document_id": j.document_id,
                                "tracking_code": (j.result_json or {}).get("tracking_code"),
                            }
                        )
                except Exception as exc:
                    logger.error("adoption_for_driver_failed driver_id=%s", driver.id, exc_info=True)
                    errors.append({"driver_id": driver.id, "error": str(exc)})

        summary = {
            "scanned_drivers": scanned_drivers,
            "adopted_count": len(adopted),
            "error_count": len(errors),
            "adopted": adopted,
            "errors": errors,
        }
        logger.info("external_waybill_adoption_run_completed", extra={"extra_fields": summary})
        return summary


adoption_service = ExternalWaybillAdoptionService()

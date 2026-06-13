import hashlib
import json
import math
import os
import tempfile
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from app.automation.auth import UTCMSAuthenticator
from app.automation.browser import browser_manager
from app.automation.proxy_rotator import get_proxy_rotator
from app.core.config import utcms_config
from app.core.database import engine
from app.core.worker_heartbeat import worker_heartbeat_registry
from app.models_management import (
    ManagedAccount,
    ManagedCustomer,
    ManagedQueueItem,
    ManagedRoute,
    ManagedSyncLog,
)
from app.queue.queue_manager import queue_manager
from app.realtime.events import event_hub
from app.schemas.management import (
    ManagedAccountUpsertRequest,
    ManagedCustomerUpsertRequest,
    ManagedQueueCreateRequest,
    ManagedQueueDispatchRequest,
    ManagedRouteUpsertRequest,
    ManagementBootstrapRequest,
    ManagementExcelImportOptions,
)
from app.services.session_vault import session_vault
from app.services.task_service import task_service
from scripts.register_waybills_from_excel import read_xlsx, to_header_map
from scripts.register_waybills_web_from_excel import ReverseGeoResolver, _build_request


def _safe_json_dump(value: Any) -> str:
    return json.dumps(value if value is not None else {}, ensure_ascii=False)


def _safe_json_load(raw: str | None) -> Any:
    if not raw:
        return None
    try:
        return json.loads(raw)
    except Exception:
        return None


def _to_bool(value: Any) -> bool | None:
    if value is None:
        return None
    if isinstance(value, bool):
        return value
    if isinstance(value, int | float):
        return bool(value)
    text = str(value).strip().lower()
    if text in {"1", "true", "yes", "on"}:
        return True
    if text in {"0", "false", "no", "off"}:
        return False
    return None


def _parse_location_details(raw_value: Any) -> dict[str, Any]:
    if raw_value is None:
        return {}
    if isinstance(raw_value, dict):
        return raw_value
    if not isinstance(raw_value, str):
        return {}
    text = raw_value.strip()
    if not text:
        return {}
    try:
        parsed = json.loads(text)
        return parsed if isinstance(parsed, dict) else {}
    except Exception:
        return {}


def _extract_coordinates(details: dict[str, Any]) -> tuple[float | None, float | None]:
    geom = details.get("geom") or {}
    coords = geom.get("coordinates") if isinstance(geom, dict) else None
    if isinstance(coords, list) and len(coords) >= 2:
        try:
            return float(coords[1]), float(coords[0])
        except Exception:
            return None, None
    return None, None


def _build_route_key(source: dict[str, Any], destination: dict[str, Any], fallback_name: str | None = None) -> str:
    seed = {
        "fallback_name": fallback_name or "",
        "source": {
            "province": source.get("province"),
            "city": source.get("city"),
            "address": source.get("address_compact") or source.get("postal_address") or source.get("address"),
            "coordinates": (source.get("geom") or {}).get("coordinates"),
        },
        "destination": {
            "province": destination.get("province"),
            "city": destination.get("city"),
            "address": destination.get("address_compact") or destination.get("postal_address") or destination.get("address"),
            "coordinates": (destination.get("geom") or {}).get("coordinates"),
        },
    }
    digest = hashlib.sha256(_safe_json_dump(seed).encode("utf-8")).hexdigest()[:20]
    return f"route-{digest}"


def _slug_text(value: str | None, fallback: str) -> str:
    text = (value or "").strip()
    if not text:
        return fallback
    return text.replace(" ", "-")


def _location_to_management_details(location: Any) -> dict[str, Any]:
    coordinates = getattr(location, "coordinates", None)
    lng = getattr(coordinates, "lng", None) if coordinates else None
    lat = getattr(coordinates, "lat", None) if coordinates else None
    return {
        "province": getattr(location, "province", None),
        "city": getattr(location, "city", None),
        "district": getattr(location, "district", None),
        "address": getattr(location, "address", None),
        "address_compact": getattr(location, "address", None),
        "postal_address": getattr(location, "address", None),
        "geom": {
            "type": "Point",
            "coordinates": [lng, lat],
        } if lng is not None and lat is not None else {},
    }


def _normalize_operation_mode(value: Any) -> str:
    if value is None:
        return "safe"
    enum_value = getattr(value, "value", None)
    if isinstance(enum_value, str) and enum_value:
        return enum_value
    text = str(value).strip()
    if text.startswith("OperationMode."):
        return text.split(".", 1)[1].lower()
    return text.lower() if text else "safe"


def _estimate_route_metrics(
    origin_lat: float | None,
    origin_lng: float | None,
    destination_lat: float | None,
    destination_lng: float | None,
) -> tuple[float | None, float | None]:
    if None in {origin_lat, origin_lng, destination_lat, destination_lng}:
        return None, None
    lat1 = math.radians(float(origin_lat))
    lat2 = math.radians(float(destination_lat))
    d_lat = math.radians(float(destination_lat) - float(origin_lat))
    d_lng = math.radians(float(destination_lng) - float(origin_lng))
    hav = (
        math.sin(d_lat / 2) ** 2
        + math.cos(lat1) * math.cos(lat2) * math.sin(d_lng / 2) ** 2
    )
    distance_km = 6371 * 2 * math.atan2(math.sqrt(hav), math.sqrt(1 - hav))
    duration_minutes = max(1.0, distance_km)
    return round(distance_km, 2), round(duration_minutes, 0)


class ManagementService:
    @staticmethod
    def _extract_account_auth_details(raw_payload: Any) -> dict[str, str | None]:
        payload = raw_payload
        if isinstance(raw_payload, str):
            payload = _safe_json_load(raw_payload) or {}
        if not isinstance(payload, dict):
            payload = {}

        utcms_auth = payload.get("utcms_auth") or {}
        if not isinstance(utcms_auth, dict):
            utcms_auth = {}

        username = str(utcms_auth.get("username") or "").strip() or None
        password = str(utcms_auth.get("password") or "").strip() or None
        login_url = str(utcms_auth.get("login_url") or "").strip() or None
        return {
            "username": username,
            "password": password,
            "login_url": login_url,
        }

    @classmethod
    def _account_auth_state_path(
        cls,
        *,
        external_name: str | None = None,
        national_code: str | None = None,
        phone_number: str | None = None,
        raw_payload: Any = None,
    ) -> str:
        auth_details = cls._extract_account_auth_details(raw_payload)
        return session_vault.auth_state_path_for_account(
            username=auth_details.get("username") or external_name,
            national_code=national_code,
            fallback=phone_number,
        )

    @staticmethod
    def _account_has_session_state(account: dict[str, Any]) -> bool:
        path = ManagementService._account_auth_state_path(
            external_name=account.get("external_name"),
            national_code=account.get("national_code"),
            phone_number=account.get("phone_number"),
            raw_payload=account.get("raw"),
        )
        return session_vault.auth_state_exists(path)

    async def upsert_customer(self, request: ManagedCustomerUpsertRequest) -> dict[str, Any]:
        async with AsyncSession(engine) as session:
            statement = select(ManagedCustomer).where(
                ManagedCustomer.source_system == request.source_system,
                ManagedCustomer.external_key == request.external_key,
            )
            record = (await session.execute(statement)).scalars().first()
            if record is None:
                record = ManagedCustomer(
                    source_system=request.source_system,
                    external_key=request.external_key,
                    full_name=request.full_name,
                )
            record.full_name = request.full_name
            record.wallet = request.wallet
            record.driver_limit = request.driver_limit
            record.bot_running = request.bot_running
            record.bot_running_barname = request.bot_running_barname
            record.auto_stop = request.auto_stop
            record.two_way = request.two_way
            record.remaining_duration = request.remaining_duration
            record.raw_json = _safe_json_dump(request.raw)
            record.synced_at = datetime.now(UTC).replace(tzinfo=None)
            session.add(record)
            await session.commit()
            await session.refresh(record)
            return self._customer_to_dict(record)

    async def upsert_route(self, request: ManagedRouteUpsertRequest) -> dict[str, Any]:
        async with AsyncSession(engine) as session:
            statement = select(ManagedRoute).where(
                ManagedRoute.source_system == request.source_system,
                ManagedRoute.route_key == request.route_key,
            )
            record = (await session.execute(statement)).scalars().first()
            if record is None:
                record = ManagedRoute(
                    source_system=request.source_system,
                    route_key=request.route_key,
                )
            for field in request.model_dump().keys():
                if field == "raw":
                    continue
                setattr(record, field, getattr(request, field))
            record.raw_json = _safe_json_dump(request.raw)
            record.synced_at = datetime.now(UTC).replace(tzinfo=None)
            session.add(record)
            await session.commit()
            await session.refresh(record)
            return self._route_to_dict(record)

    async def upsert_account(self, request: ManagedAccountUpsertRequest) -> dict[str, Any]:
        async with AsyncSession(engine) as session:
            statement = select(ManagedAccount).where(
                ManagedAccount.source_system == request.source_system,
                ManagedAccount.external_name == request.external_name,
            )
            record = (await session.execute(statement)).scalars().first()
            if record is None:
                record = ManagedAccount(
                    source_system=request.source_system,
                    external_name=request.external_name,
                )
            data = request.model_dump()
            record.bot_owner = data["bot_owner"]
            record.title = data["title"]
            record.phone_number = data["phone_number"]
            record.national_code = data["national_code"]
            record.platform = data["platform"]
            record.status = data["status"]
            record.route_key = data["route_key"]
            record.otp_needed = data["otp_needed"]
            record.has_account_is_enabled = data["has_account_is_enabled"]
            record.has_driver_data = data["has_driver_data"]
            record.has_truck_data = data["has_truck_data"]
            record.has_valid_location = data["has_valid_location"]
            record.start_shipping = data["start_shipping"]
            record.two_way = data["two_way"]
            record.custom_current_submit = data["custom_current_submit"]
            record.custom_target_submit = data["custom_target_submit"]
            record.time_interval = data["time_interval"]
            record.last_success = data["last_success"]
            record.source_details_json = data["source_details_json"]
            record.destination_detail_json = data["destination_detail_json"]
            record.mobile_info_json = data["mobile_info_json"]
            record.payment_details_json = data["payment_details_json"]
            record.flags_json = _safe_json_dump(data["flags"])
            record.raw_json = _safe_json_dump(data["raw"])
            record.synced_at = datetime.now(UTC).replace(tzinfo=None)
            session.add(record)
            await session.commit()
            await session.refresh(record)
            return self._account_to_dict(record)

    async def list_customers(self) -> list[dict[str, Any]]:
        async with AsyncSession(engine) as session:
            rows = (await session.execute(select(ManagedCustomer).order_by(ManagedCustomer.synced_at.desc()))).scalars().all()
            return [self._customer_to_dict(row) for row in rows]

    async def list_routes(self) -> list[dict[str, Any]]:
        async with AsyncSession(engine) as session:
            rows = (await session.execute(select(ManagedRoute).order_by(ManagedRoute.synced_at.desc()))).scalars().all()
            return [self._route_to_dict(row) for row in rows]

    async def list_accounts(self) -> list[dict[str, Any]]:
        async with AsyncSession(engine) as session:
            rows = (await session.execute(select(ManagedAccount).order_by(ManagedAccount.synced_at.desc()))).scalars().all()
            return [self._account_to_dict(row) for row in rows]

    async def warm_account_session(self, account_external_name: str) -> dict[str, Any]:
        async with AsyncSession(engine) as session:
            statement = select(ManagedAccount).where(ManagedAccount.external_name == account_external_name)
            record = (await session.execute(statement)).scalars().first()
            if record is None:
                raise HTTPException(status_code=404, detail="اکانت مدیریتی یافت نشد")

        raw_payload = _safe_json_load(record.raw_json) or {}
        auth_details = self._extract_account_auth_details(raw_payload)
        username = str(auth_details.get("username") or record.external_name or "").strip()
        password = str(auth_details.get("password") or "").strip()
        login_url = auth_details.get("login_url")
        if not username or not password:
            raise HTTPException(status_code=400, detail="برای این اکانت، اطلاعات ورود UTCMS ذخیره نشده است")

        auth_state_path = self._account_auth_state_path(
            external_name=record.external_name,
            national_code=record.national_code,
            phone_number=record.phone_number,
            raw_payload=raw_payload,
        )

        internal_session_id: str | None = None
        try:
            await browser_manager.initialize()
            proxy_info = await get_proxy_rotator().get_next()
            proxy_dict = proxy_info.to_playwright_proxy() if proxy_info else None
            internal_session_id, context = await browser_manager.create_context(auth_state_path=auth_state_path, proxy_dict=proxy_dict)
            page = await browser_manager.new_page(context)
            auth = UTCMSAuthenticator(page, context)

            session_reused = await auth._is_logged_in()
            if not session_reused:
                login_success = await auth.login(username, password, login_url=login_url)
                if not login_success:
                    detail = "ساخت session برای اکانت ناموفق بود"
                    if auth.last_error:
                        detail = f"{detail}: {auth.last_error}"
                    raise HTTPException(status_code=401, detail=detail)

            await browser_manager.save_auth_state(context, auth_state_path=auth_state_path)

            return {
                "account_external_name": record.external_name,
                "auth_username": auth_details.get("username") or record.external_name,
                "session_ready": True,
                "session_reused": session_reused,
                "auth_state_path": auth_state_path,
                "login_url": login_url,
            }
        finally:
            if internal_session_id:
                await browser_manager.close_context(internal_session_id)

    async def list_queue(self) -> list[dict[str, Any]]:
        async with AsyncSession(engine) as session:
            rows = (await session.execute(select(ManagedQueueItem).order_by(ManagedQueueItem.updated_at.desc()))).scalars().all()
            return [self._queue_to_dict(row) for row in rows]

    async def summary(self) -> dict[str, Any]:
        customers = await self.list_customers()
        routes = await self.list_routes()
        accounts = await self.list_accounts()
        queue = await self.list_queue()
        local_queue_count = len([item for item in queue if item.get("source_system") == "local"])
        imported_queue_count = len([item for item in queue if item.get("source_system") != "local"])
        session_ready_accounts_count = len([item for item in accounts if self._account_has_session_state(item)])
        return {
            "customers_count": len(customers),
            "routes_count": len(routes),
            "accounts_count": len(accounts),
            "queue_count": len(queue),
            "active_accounts_count": len([item for item in accounts if item.get("start_shipping") is True]),
            "otp_accounts_count": len([item for item in accounts if item.get("otp_needed") is True]),
            "session_ready_accounts_count": session_ready_accounts_count,
            "queued_local_items_count": local_queue_count,
            "imported_queue_items_count": imported_queue_count,
            "external_synced_items_count": imported_queue_count,
        }

    async def diagnostics(self) -> dict[str, Any]:
        customers = await self.list_customers()
        routes = await self.list_routes()
        accounts = await self.list_accounts()
        queue = await self.list_queue()

        issues = {
            "accounts_missing_route": [item["external_name"] for item in accounts if not item.get("route_key")],
            "accounts_missing_phone": [item["external_name"] for item in accounts if not item.get("phone_number")],
            "accounts_missing_national_code": [item["external_name"] for item in accounts if not item.get("national_code")],
            "accounts_missing_location": [
                item["external_name"]
                for item in accounts
                if item.get("has_valid_location") is False or (
                    not item.get("source_details") and not item.get("destination_detail")
                )
            ],
            "accounts_inactive": [item["external_name"] for item in accounts if item.get("start_shipping") is False],
            "accounts_waiting_otp": [item["external_name"] for item in accounts if item.get("otp_needed") is True],
            "accounts_missing_session_state": [
                item["external_name"] for item in accounts if not self._account_has_session_state(item)
            ],
            "routes_missing_coordinates": [
                item["route_key"]
                for item in routes
                if item.get("origin_lat") is None
                or item.get("origin_lng") is None
                or item.get("destination_lat") is None
                or item.get("destination_lng") is None
            ],
            "routes_disabled": [item["route_key"] for item in routes if item.get("enabled") is False],
            "queue_missing_payload": [item["queue_item_id"] for item in queue if not item.get("payload")],
            "queue_failed_or_blocked": [
                item["queue_item_id"]
                for item in queue
                if item.get("status") in {"failed", "blocked", "error"}
            ],
            "customers_without_wallet": [item["external_key"] for item in customers if not item.get("wallet")],
        }

        return {
            "summary": await self.summary(),
            "readiness": {
                "accounts_ready_for_dispatch": len([
                    item for item in accounts
                    if item.get("start_shipping") is True
                    and item.get("otp_needed") is not True
                    and item.get("has_driver_data") is not False
                    and item.get("has_truck_data") is not False
                    and item.get("has_valid_location") is not False
                    and item.get("route_key")
                    and self._account_has_session_state(item)
                ]),
                "routes_ready": len([
                    item for item in routes
                    if item.get("enabled") is True
                    and item.get("origin_lat") is not None
                    and item.get("origin_lng") is not None
                    and item.get("destination_lat") is not None
                    and item.get("destination_lng") is not None
                ]),
                "queued_with_payload": len([item for item in queue if item.get("payload")]),
            },
            "issues": {
                key: {
                    "count": len(values),
                    "samples": values[:10],
                }
                for key, values in issues.items()
            },
        }

    @staticmethod
    def _artifact_root() -> Path:
        return Path(utcms_config.FAILURE_ARTIFACTS_DIR)

    @classmethod
    def _safe_artifact_path(cls, relative_path: str) -> Path:
        root = cls._artifact_root().resolve()
        candidate = (root / relative_path).resolve()
        if root not in candidate.parents and candidate != root:
            raise HTTPException(status_code=400, detail="artifact path invalid")
        return candidate

    @classmethod
    def _list_artifacts_for_task(cls, task_id: str) -> list[dict[str, Any]]:
        root = cls._artifact_root()
        if not root.exists():
            return []
        files: list[dict[str, Any]] = []
        for path in sorted(root.glob(f"**/{task_id}/**/*")):
            if not path.is_file():
                continue
            relative = path.relative_to(root).as_posix()
            files.append(
                {
                    "name": path.name,
                    "relative_path": relative,
                    "size_bytes": path.stat().st_size,
                    "modified_at": datetime.utcfromtimestamp(path.stat().st_mtime).isoformat(),
                    "content_type": "json" if path.suffix == ".json" else ("html" if path.suffix == ".html" else path.suffix.lstrip(".")),
                }
            )
        files.sort(key=lambda item: item["modified_at"], reverse=True)
        return files

    async def operator_dashboard(self) -> dict[str, Any]:
        summary = await self.summary()
        queue_snapshot = await task_service.queue_snapshot()
        recent_tasks = await task_service.list_tasks(limit=12)
        active_heartbeats = worker_heartbeat_registry.snapshot()
        stalled = worker_heartbeat_registry.detect_stalled(utcms_config.WORKER_STALL_TIMEOUT_SECONDS)
        return {
            "summary": summary,
            "queue": queue_snapshot,
            "recent_tasks": recent_tasks,
            "heartbeats": {
                "active_count": len(active_heartbeats),
                "stalled_count": len(stalled),
                "active": active_heartbeats,
                "stalled": stalled,
            },
            "recent_events": event_hub.history()[-20:],
        }

    async def operator_tasks(self, limit: int = 50) -> dict[str, Any]:
        tasks = await task_service.list_tasks(limit=limit)
        enriched = []
        for task in tasks:
            row = dict(task)
            row["artifact_count"] = len(self._list_artifacts_for_task(task["task_id"]))
            enriched.append(row)
        return {"tasks": enriched, "count": len(enriched)}

    async def operator_artifacts(self, task_id: str) -> dict[str, Any]:
        task = await task_service.get_task_status(task_id)
        return {
            "task": task,
            "artifacts": self._list_artifacts_for_task(task_id),
            "event_history": event_hub.history(task_id=task_id),
        }

    async def read_artifact_content(self, relative_path: str) -> dict[str, Any]:
        target = self._safe_artifact_path(relative_path)
        if not target.exists() or not target.is_file():
            raise HTTPException(status_code=404, detail="artifact not found")
        suffix = target.suffix.lower()
        if suffix in {".json", ".html", ".txt", ".log"}:
            return {
                "name": target.name,
                "relative_path": relative_path,
                "content": target.read_text(encoding="utf-8", errors="replace"),
                "content_type": suffix.lstrip("."),
            }
        raise HTTPException(status_code=400, detail="artifact preview is only available for text-based files")

    async def create_queue_item(self, request: ManagedQueueCreateRequest) -> dict[str, Any]:
        queue_item_id = str(uuid.uuid4())
        payload_json = request.waybill_payload.model_dump_json() if request.waybill_payload else None
        operation_mode = _normalize_operation_mode(request.operation_mode)
        async with AsyncSession(engine) as session:
            record = ManagedQueueItem(
                queue_item_id=queue_item_id,
                source_system=request.source_system,
                external_key=queue_item_id,
                account_external_name=request.account_external_name,
                route_key=request.route_key,
                bot_owner=request.bot_owner,
                status="queued",
                operation_mode=operation_mode,
                priority=request.priority,
                origin="local",
                payload_json=payload_json,
                metadata_json=_safe_json_dump(request.metadata),
            )
            session.add(record)
            await session.commit()
            await session.refresh(record)
            return self._queue_to_dict(record)

    async def bootstrap_local_scenario(self, request: ManagementBootstrapRequest) -> dict[str, Any]:
        payload = request.waybill_payload
        customer_external_key = request.customer_external_key or request.bot_owner or "local-operations"
        customer_name = request.customer_name or request.bot_owner or "Local Operations"
        bot_owner = request.bot_owner or customer_external_key
        source_details = _location_to_management_details(payload.origin)
        destination_details = _location_to_management_details(payload.destination)
        route_name = f"{payload.origin.city} ← {payload.destination.city}"
        route_key = _build_route_key(
            source_details,
            destination_details,
            fallback_name=route_name,
        )
        account_external_name = (
            request.account_external_name
            or getattr(payload.utcms_auth, "username", None)
            or getattr(payload.vehicle, "driver_national_code", None)
            or _slug_text(getattr(payload.vehicle, "plate", None), "managed-account")
        )
        account_phone_number = request.account_phone_number or getattr(payload.vehicle, "driver_phone", None) or getattr(payload.sender, "phone", None)
        account_national_code = request.account_national_code or getattr(payload.vehicle, "driver_national_code", None)
        shipping_options = getattr(payload, "shipping_options", None)
        two_way = request.two_way if request.two_way is not None else getattr(shipping_options, "two_way", False)
        time_interval = request.time_interval if request.time_interval is not None else getattr(shipping_options, "time_limit", None)
        otp_needed = request.otp_needed if request.otp_needed is not None else bool(getattr(shipping_options, "otp", None))
        origin_lat = getattr(payload.origin.coordinates, "lat", None) if payload.origin.coordinates else None
        origin_lng = getattr(payload.origin.coordinates, "lng", None) if payload.origin.coordinates else None
        destination_lat = getattr(payload.destination.coordinates, "lat", None) if payload.destination.coordinates else None
        destination_lng = getattr(payload.destination.coordinates, "lng", None) if payload.destination.coordinates else None
        distance_km, duration_minutes = _estimate_route_metrics(
            origin_lat,
            origin_lng,
            destination_lat,
            destination_lng,
        )

        customer = await self.upsert_customer(
            ManagedCustomerUpsertRequest(
                source_system=request.source_system,
                external_key=customer_external_key,
                full_name=customer_name,
                wallet=request.wallet,
                driver_limit=request.driver_limit,
                bot_running=True,
                bot_running_barname=True,
                auto_stop=False,
                two_way=two_way,
                raw={
                    "source": "bootstrap_local_scenario",
                    "bot_owner": bot_owner,
                },
            )
        )

        route = await self.upsert_route(
            ManagedRouteUpsertRequest(
                source_system=request.source_system,
                route_key=route_key,
                name=route_name,
                origin_label=payload.origin.city,
                origin_province=payload.origin.province,
                origin_city=payload.origin.city,
                origin_address=payload.origin.address,
                origin_lat=origin_lat,
                origin_lng=origin_lng,
                destination_label=payload.destination.city,
                destination_province=payload.destination.province,
                destination_city=payload.destination.city,
                destination_address=payload.destination.address,
                destination_lat=destination_lat,
                destination_lng=destination_lng,
                distance_km=distance_km,
                duration_minutes=duration_minutes,
                same_province=payload.origin.province == payload.destination.province,
                recommended=True,
                enabled=True,
                raw={
                    "source": "bootstrap_local_scenario",
                    "waybill_payload": payload.model_dump(mode="json"),
                },
            )
        )

        account = await self.upsert_account(
            ManagedAccountUpsertRequest(
                source_system=request.source_system,
                external_name=account_external_name,
                bot_owner=bot_owner,
                title=request.account_title or payload.sender.name,
                phone_number=account_phone_number,
                national_code=account_national_code,
                platform=request.platform,
                status=request.status or "Ready",
                route_key=route_key,
                otp_needed=otp_needed,
                has_account_is_enabled=True,
                has_driver_data=bool(account_national_code),
                has_truck_data=bool(getattr(payload.vehicle, "plate", None)),
                has_valid_location=bool(payload.origin.coordinates and payload.destination.coordinates),
                start_shipping=request.start_shipping,
                two_way=two_way,
                custom_current_submit=request.custom_current_submit,
                custom_target_submit=request.custom_target_submit,
                time_interval=time_interval,
                last_success=None,
                source_details_json=_safe_json_dump(source_details),
                destination_detail_json=_safe_json_dump(destination_details),
                mobile_info_json=_safe_json_dump({
                    "sender_phone": getattr(payload.sender, "phone", None),
                    "receiver_phone": getattr(payload.receiver, "phone", None),
                    "driver_phone": getattr(payload.vehicle, "driver_phone", None),
                }),
                payment_details_json=_safe_json_dump(payload.financial.model_dump(mode="json")),
                flags={
                    "source": "bootstrap_local_scenario",
                    "has_utcms_auth": bool(payload.utcms_auth),
                },
                raw=payload.model_dump(mode="json"),
            )
        )

        queue_item = None
        if request.create_queue:
            queue_item = await self.create_queue_item(
                ManagedQueueCreateRequest(
                    source_system=request.source_system,
                    account_external_name=account_external_name,
                    route_key=route_key,
                    bot_owner=bot_owner,
                    operation_mode=_normalize_operation_mode(payload.operation_mode),
                    priority=request.priority,
                    metadata={
                        "source": "bootstrap_local_scenario",
                        "customer_external_key": customer_external_key,
                    },
                    waybill_payload=payload,
                )
            )

        summary = {
            "customer_external_key": customer_external_key,
            "route_key": route_key,
            "account_external_name": account_external_name,
            "queue_created": bool(queue_item),
        }
        await self._write_log(
            source_system=request.source_system,
            sync_type="bootstrap",
            status="completed",
            summary=summary,
        )
        return {
            "summary": summary,
            "customer": customer,
            "route": route,
            "account": account,
            "queue_item": queue_item,
        }

    async def import_excel_workbook(self, content: bytes, filename: str, options: ManagementExcelImportOptions) -> dict[str, Any]:
        suffix = os.path.splitext(filename or "")[1] or ".xlsx"
        temp_path = None
        geo_resolver = ReverseGeoResolver(enabled=options.reverse_geo_enabled)
        imported_items = []
        errors = []

        try:
            with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as handle:
                handle.write(content)
                temp_path = handle.name

            rows = read_xlsx(temp_path)
            if not rows:
                raise HTTPException(status_code=400, detail="فایل اکسل خالی است یا خوانده نشد")

            header_map = to_header_map(rows[0])
            for row_index, row in enumerate(rows[1:], start=2):
                if not any(str(cell).strip() for cell in row):
                    continue
                try:
                    waybill_payload, excerpt, _ = await _build_request(
                        row=row,
                        header_map=header_map,
                        operation_mode=options.operation_mode,
                        login_url=options.login_url,
                        include_auth=options.include_auth,
                        geo_resolver=geo_resolver,
                        default_province=options.default_province,
                        default_city=options.default_city,
                    )
                    bootstrap = await self.bootstrap_local_scenario(
                        ManagementBootstrapRequest(
                            source_system=options.source_system,
                            customer_external_key=options.customer_external_key,
                            customer_name=options.customer_name,
                            bot_owner=options.bot_owner,
                            wallet=options.wallet,
                            driver_limit=options.driver_limit,
                            account_external_name=excerpt.get("username") or excerpt.get("driver_national_code") or f"excel-row-{row_index}",
                            account_title=excerpt.get("sender"),
                            account_phone_number=getattr(waybill_payload.vehicle, "driver_phone", None),
                            account_national_code=excerpt.get("driver_national_code"),
                            platform=options.platform,
                            status="Excel Imported",
                            start_shipping=True,
                            time_interval=options.time_interval,
                            priority=options.priority,
                            create_queue=options.create_queue,
                            waybill_payload=waybill_payload,
                        )
                    )
                    imported_items.append(
                        {
                            "row_index": row_index,
                            "account_external_name": bootstrap["summary"]["account_external_name"],
                            "route_key": bootstrap["summary"]["route_key"],
                            "queue_created": bootstrap["summary"]["queue_created"],
                            "excerpt": excerpt,
                        }
                    )
                except Exception as exc:
                    errors.append(
                        {
                            "row_index": row_index,
                            "detail": str(exc),
                        }
                    )

            summary = {
                "filename": filename,
                "rows_total": max(len(rows) - 1, 0),
                "rows_imported": len(imported_items),
                "rows_failed": len(errors),
                "queue_created": len([item for item in imported_items if item.get("queue_created")]),
            }
            await self._write_log(
                source_system=options.source_system,
                sync_type="excel_import",
                status="completed" if not errors else "partial",
                summary=summary,
                error_text=_safe_json_dump(errors[:20]) if errors else None,
            )
            return {
                "summary": summary,
                "imported": imported_items,
                "errors": errors,
                "header_map": header_map,
            }
        finally:
            await geo_resolver.close()
            if temp_path and os.path.exists(temp_path):
                os.unlink(temp_path)

    async def dispatch_queue_item(self, queue_item_id: str, request: ManagedQueueDispatchRequest) -> dict[str, Any]:
        async with AsyncSession(engine) as session:
            statement = select(ManagedQueueItem).where(ManagedQueueItem.queue_item_id == queue_item_id)
            record = (await session.execute(statement)).scalars().first()
            if record is None:
                raise HTTPException(status_code=404, detail="queue item یافت نشد")
            if not record.payload_json:
                raise HTTPException(status_code=400, detail="برای این queue item، payload بارنامه ذخیره نشده است")
            try:
                payload = json.loads(record.payload_json)
            except Exception:
                raise HTTPException(status_code=400, detail="payload queue item نامعتبر است") from None

            account_record = None
            if record.account_external_name:
                account_statement = select(ManagedAccount).where(
                    ManagedAccount.external_name == record.account_external_name
                )
                account_record = (await session.execute(account_statement)).scalars().first()

            if account_record and account_record.otp_needed is True and not request.allow_otp_pending:
                record.status = "blocked"
                record.last_error = "otp_required"
                record.result_json = _safe_json_dump(
                    {
                        "dispatch_blocked": True,
                        "reason": "otp_required",
                        "account_external_name": account_record.external_name,
                    }
                )
                record.updated_at = datetime.now(UTC).replace(tzinfo=None)
                session.add(record)
                await session.commit()
                await session.refresh(record)
                return self._queue_to_dict(record)

            from app.schemas.waybill import WaybillMapRequest

            waybill_request = WaybillMapRequest.model_validate(payload)
            warm_session_result = None
            try:
                if request.warm_session_first and account_record and account_record.external_name:
                    warm_session_result = await self.warm_account_session(account_record.external_name)

                enqueue_result = await queue_manager.enqueue_waybill(
                    request=waybill_request,
                    idempotency_key=request.idempotency_key,
                )
            except Exception as exc:
                record.status = "error"
                record.last_error = str(exc)
                record.result_json = _safe_json_dump(
                    {
                        "dispatch_error": str(exc),
                        "warm_session": warm_session_result,
                    }
                )
                record.updated_at = datetime.now(UTC).replace(tzinfo=None)
                session.add(record)
                await session.commit()
                raise

            record.status = "dispatched" if getattr(enqueue_result, "queued", True) else "submitted"
            record.last_error = None
            record.result_json = _safe_json_dump(
                {
                    "enqueue": enqueue_result.model_dump(),
                    "warm_session": warm_session_result,
                    "auth_strategy": "session-first" if request.warm_session_first else "direct-enqueue",
                }
            )
            record.dispatched_at = datetime.now(UTC).replace(tzinfo=None)
            record.updated_at = datetime.now(UTC).replace(tzinfo=None)
            session.add(record)
            await session.commit()
            await session.refresh(record)
            return self._queue_to_dict(record)


    async def get_sync_logs(self) -> list[dict[str, Any]]:
        async with AsyncSession(engine) as session:
            rows = (await session.execute(select(ManagedSyncLog).order_by(ManagedSyncLog.created_at.desc()))).scalars().all()
            return [
                {
                    "id": row.id,
                    "source_system": row.source_system,
                    "sync_type": row.sync_type,
                    "status": row.status,
                    "summary": _safe_json_load(row.summary_json),
                    "error_text": row.error_text,
                    "created_at": row.created_at,
                }
                for row in rows
            ]

    async def _write_log(
        self,
        source_system: str,
        sync_type: str,
        status: str,
        summary: dict[str, Any],
        error_text: str | None = None,
    ) -> None:
        async with AsyncSession(engine) as session:
            log_record = ManagedSyncLog(
                source_system=source_system,
                sync_type=sync_type,
                status=status,
                summary_json=_safe_json_dump(summary),
                error_text=error_text,
            )
            session.add(log_record)
            await session.commit()

    @staticmethod
    def _customer_to_dict(record: ManagedCustomer) -> dict[str, Any]:
        return {
            "id": record.id,
            "source_system": record.source_system,
            "external_key": record.external_key,
            "full_name": record.full_name,
            "wallet": record.wallet,
            "driver_limit": record.driver_limit,
            "bot_running": record.bot_running,
            "bot_running_barname": record.bot_running_barname,
            "auto_stop": record.auto_stop,
            "two_way": record.two_way,
            "remaining_duration": record.remaining_duration,
            "raw": _safe_json_load(record.raw_json),
            "synced_at": record.synced_at,
        }

    @staticmethod
    def _route_to_dict(record: ManagedRoute) -> dict[str, Any]:
        return {
            "id": record.id,
            "source_system": record.source_system,
            "route_key": record.route_key,
            "name": record.name,
            "origin_label": record.origin_label,
            "origin_province": record.origin_province,
            "origin_city": record.origin_city,
            "origin_address": record.origin_address,
            "origin_lat": record.origin_lat,
            "origin_lng": record.origin_lng,
            "destination_label": record.destination_label,
            "destination_province": record.destination_province,
            "destination_city": record.destination_city,
            "destination_address": record.destination_address,
            "destination_lat": record.destination_lat,
            "destination_lng": record.destination_lng,
            "distance_km": record.distance_km,
            "duration_minutes": record.duration_minutes,
            "same_province": record.same_province,
            "recommended": record.recommended,
            "enabled": record.enabled,
            "raw": _safe_json_load(record.raw_json),
            "synced_at": record.synced_at,
        }

    @staticmethod
    def _account_to_dict(record: ManagedAccount) -> dict[str, Any]:
        raw = _safe_json_load(record.raw_json)
        auth_details = ManagementService._extract_account_auth_details(raw)
        session_state_path = ManagementService._account_auth_state_path(
            external_name=record.external_name,
            national_code=record.national_code,
            phone_number=record.phone_number,
            raw_payload=raw,
        )
        return {
            "id": record.id,
            "source_system": record.source_system,
            "external_name": record.external_name,
            "bot_owner": record.bot_owner,
            "title": record.title,
            "phone_number": record.phone_number,
            "national_code": record.national_code,
            "platform": record.platform,
            "status": record.status,
            "route_key": record.route_key,
            "otp_needed": record.otp_needed,
            "has_account_is_enabled": record.has_account_is_enabled,
            "has_driver_data": record.has_driver_data,
            "has_truck_data": record.has_truck_data,
            "has_valid_location": record.has_valid_location,
            "start_shipping": record.start_shipping,
            "two_way": record.two_way,
            "custom_current_submit": record.custom_current_submit,
            "custom_target_submit": record.custom_target_submit,
            "time_interval": record.time_interval,
            "last_success": record.last_success,
            "source_details": _safe_json_load(record.source_details_json),
            "destination_detail": _safe_json_load(record.destination_detail_json),
            "mobile_info": _safe_json_load(record.mobile_info_json),
            "payment_details": _safe_json_load(record.payment_details_json),
            "flags": _safe_json_load(record.flags_json),
            "raw": raw,
            "auth_username": auth_details.get("username"),
            "auth_login_url": auth_details.get("login_url"),
            "session_state_path": session_state_path,
            "session_ready": session_vault.auth_state_exists(session_state_path),
            "synced_at": record.synced_at,
        }

    @staticmethod
    def _queue_to_dict(record: ManagedQueueItem) -> dict[str, Any]:
        return {
            "id": record.id,
            "queue_item_id": record.queue_item_id,
            "source_system": record.source_system,
            "external_key": record.external_key,
            "account_external_name": record.account_external_name,
            "route_key": record.route_key,
            "bot_owner": record.bot_owner,
            "status": record.status,
            "operation_mode": record.operation_mode,
            "priority": record.priority,
            "origin": record.origin,
            "payload": _safe_json_load(record.payload_json),
            "result": _safe_json_load(record.result_json),
            "metadata": _safe_json_load(record.metadata_json),
            "last_error": record.last_error,
            "created_at": record.created_at,
            "updated_at": record.updated_at,
            "dispatched_at": record.dispatched_at,
            "finished_at": record.finished_at,
        }


management_service = ManagementService()

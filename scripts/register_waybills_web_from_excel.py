#!/usr/bin/env python3
import argparse
import asyncio
import json
import shutil
import sys
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import aiohttp
from fastapi import HTTPException

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.automation.browser import browser_manager
from app.automation.reporting import report_service
from app.core.config import utcms_config
from app.core.database import init_db
from app.schemas.waybill import WaybillMapRequest
from app.services.waybill_service import waybill_service
from scripts.register_waybills_from_excel import (
    get_cell,
    normalize_digits,
    normalize_float,
    normalize_int,
    read_xlsx,
    to_header_map,
)


@dataclass
class RunItem:
    row_index: int
    status: str
    message: str
    mode: str
    attempt_count: int
    request_id: Optional[str] = None
    tracking_code: Optional[str] = None
    duration_seconds: Optional[float] = None
    detail: Optional[Any] = None
    artifacts: Optional[List[str]] = None
    payload_excerpt: Optional[Dict[str, Any]] = None


def _clean_text(value: Any) -> str:
    return str(value or "").strip()


def _normalize_phone(value: Any) -> str:
    return normalize_digits(value)


def _choose_phone(primary: str, secondary: str) -> str:
    return primary or secondary


def _plate_string(
    plate_first_two: Any,
    plate_letter: Any,
    plate_three: Any,
    plate_last_two: Any,
) -> str:
    first_two = normalize_int(plate_first_two, default=0)
    three = normalize_int(plate_three, default=0)
    last_two = normalize_int(plate_last_two, default=0)
    letter = _clean_text(plate_letter) or "ع"
    return f"{first_two:02d}{letter}{three:03d}{last_two:02d}"


def _safe_float(value: Any, default: float) -> float:
    parsed = normalize_float(value, default=default)
    if parsed == 0 and default != 0:
        return default
    return parsed


class ReverseGeoResolver:
    def __init__(self, enabled: bool = True, timeout_seconds: float = 8.0, min_interval_seconds: float = 1.0):
        self.enabled = enabled
        self.timeout_seconds = max(2.0, timeout_seconds)
        self.min_interval_seconds = max(0.0, min_interval_seconds)
        self._session: Optional[aiohttp.ClientSession] = None
        self._cache: Dict[Tuple[float, float], Dict[str, str]] = {}
        self._last_call_at = 0.0

    async def _get_session(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            timeout = aiohttp.ClientTimeout(total=self.timeout_seconds)
            self._session = aiohttp.ClientSession(timeout=timeout)
        return self._session

    async def close(self) -> None:
        if self._session and not self._session.closed:
            await self._session.close()

    async def resolve(self, lat: float, lng: float) -> Optional[Dict[str, str]]:
        if not self.enabled:
            return None

        key = (round(lat, 6), round(lng, 6))
        if key in self._cache:
            return self._cache[key]

        sleep_for = self.min_interval_seconds - (time.monotonic() - self._last_call_at)
        if sleep_for > 0:
            await asyncio.sleep(sleep_for)

        url = "https://nominatim.openstreetmap.org/reverse"
        params = {
            "format": "jsonv2",
            "lat": f"{lat:.6f}",
            "lon": f"{lng:.6f}",
            "accept-language": "fa",
            "zoom": 10,
        }
        headers = {
            "User-Agent": "UTCMS-Automation/2.0 (Excel Web Runner)",
        }

        try:
            session = await self._get_session()
            async with session.get(url, params=params, headers=headers) as response:
                self._last_call_at = time.monotonic()
                if response.status != 200:
                    return None
                payload = await response.json()
        except Exception:
            return None

        address = payload.get("address") if isinstance(payload, dict) else None
        if not isinstance(address, dict):
            return None

        province = (
            _clean_text(address.get("state"))
            or _clean_text(address.get("province"))
            or _clean_text(address.get("region"))
        )
        city = (
            _clean_text(address.get("city"))
            or _clean_text(address.get("town"))
            or _clean_text(address.get("county"))
            or _clean_text(address.get("village"))
        )
        district = (
            _clean_text(address.get("suburb"))
            or _clean_text(address.get("neighbourhood"))
            or _clean_text(address.get("quarter"))
        )
        if not province and not city:
            return None

        result = {
            "province": province,
            "city": city,
            "district": district,
        }
        self._cache[key] = result
        return result


def _build_credentials(row: List[str], header_map: Dict[str, int]) -> Tuple[str, str]:
    username = normalize_digits(get_cell(row, header_map["account_username"]))
    password = _clean_text(get_cell(row, header_map["account_password"]))
    return username, password


async def _build_request(
    row: List[str],
    header_map: Dict[str, int],
    operation_mode: str,
    login_url: str,
    include_auth: bool,
    geo_resolver: ReverseGeoResolver,
    default_province: str,
    default_city: str,
) -> Tuple[WaybillMapRequest, Dict[str, Any], Tuple[str, str]]:
    username, password = _build_credentials(row, header_map)

    sender_name = _clean_text(get_cell(row, header_map["sender_name"])) or "فرستنده"
    sender_national_code = normalize_digits(get_cell(row, header_map["sender_national_code"]))[:10].zfill(10)
    sender_mobile = _normalize_phone(get_cell(row, header_map["sender_mobile"]))
    sender_phone = _normalize_phone(get_cell(row, header_map["sender_phone"]))
    sender_address_col = _clean_text(get_cell(row, header_map.get("sender_address", -1)))

    receiver_name = _clean_text(get_cell(row, header_map["receiver_name"])) or "گیرنده"
    receiver_national_code = normalize_digits(get_cell(row, header_map.get("receiver_national_code", -1)))
    receiver_mobile = _normalize_phone(get_cell(row, header_map["receiver_mobile"]))
    receiver_phone = _normalize_phone(get_cell(row, header_map["receiver_phone"]))
    receiver_address_col = _clean_text(get_cell(row, header_map.get("receiver_address", -1)))

    driver_national_code = normalize_digits(get_cell(row, header_map["driver_national_code"]))[:10].zfill(10)

    plate = _plate_string(
        get_cell(row, header_map["plate_first_two"]),
        get_cell(row, header_map["plate_letter"]),
        get_cell(row, header_map["plate_three"]),
        get_cell(row, header_map["plate_last_two"]),
    )

    weight_ton = _safe_float(get_cell(row, header_map["weight_ton"]), default=1.0)
    cargo_count = max(1, normalize_int(get_cell(row, header_map["cargo_count"]), default=1))
    cargo_value = max(1, normalize_int(get_cell(row, header_map["cargo_value"]), default=1))
    good_type_id = max(1, normalize_int(get_cell(row, header_map["good_type_id"]), default=1))
    good_type_name = _clean_text(get_cell(row, header_map.get("good_type_name", -1)))
    vehicle_type_col = _clean_text(get_cell(row, header_map.get("vehicle_type", -1))) or "کامیون"
    trip_minutes = normalize_int(get_cell(row, header_map.get("trip_minutes", -1)), default=0)
    end_shipping_date = _clean_text(get_cell(row, header_map.get("end_shipping_date", -1)))

    origin_lat = _safe_float(get_cell(row, header_map["sender_lat"]), default=35.6997)
    origin_lng = _safe_float(get_cell(row, header_map["sender_lng"]), default=51.3380)
    destination_lat = _safe_float(get_cell(row, header_map["receiver_lat"]), default=36.2972)
    destination_lng = _safe_float(get_cell(row, header_map["receiver_lng"]), default=59.6067)

    origin_geo = await geo_resolver.resolve(origin_lat, origin_lng)
    destination_geo = await geo_resolver.resolve(destination_lat, destination_lng)

    origin_province = (origin_geo or {}).get("province") or default_province
    origin_city = (origin_geo or {}).get("city") or default_city
    origin_district = (origin_geo or {}).get("district") or None

    destination_province = (destination_geo or {}).get("province") or default_province
    destination_city = (destination_geo or {}).get("city") or default_city
    destination_district = (destination_geo or {}).get("district") or None

    origin_address = (
        sender_address_col
        or f"{origin_city} - مختصات: {origin_lat:.6f}, {origin_lng:.6f}"
    )
    destination_address = (
        receiver_address_col
        or f"{destination_city} - مختصات: {destination_lat:.6f}, {destination_lng:.6f}"
    )

    # cargo type: prefer human-readable name for web form dropdown; fall back to GOOD-<id>
    cargo_type_label = good_type_name or f"GOOD-{good_type_id}"

    payload: Dict[str, Any] = {
        "operation_mode": operation_mode,
        "sender": {
            "name": sender_name,
            "phone": _choose_phone(sender_mobile, sender_phone),
            "address": origin_address,
            "national_code": sender_national_code,
        },
        "receiver": {
            "name": receiver_name,
            "phone": _choose_phone(receiver_mobile, receiver_phone),
            "address": destination_address,
        },
        "origin": {
            "province": origin_province,
            "city": origin_city,
            "district": origin_district,
            "address": origin_address,
            "coordinates": {"lat": origin_lat, "lng": origin_lng},
        },
        "destination": {
            "province": destination_province,
            "city": destination_city,
            "district": destination_district,
            "address": destination_address,
            "coordinates": {"lat": destination_lat, "lng": destination_lng},
        },
        "cargo": {
            "type": cargo_type_label,
            "weight": str(weight_ton),
            "count": str(cargo_count),
            "description": f"excel-import good_type={good_type_id} value={cargo_value}",
        },
        "vehicle": {
            "driver_national_code": driver_national_code,
            "driver_phone": _choose_phone(sender_mobile, receiver_mobile),
            "plate": plate,
            "type": vehicle_type_col,
        },
        "financial": {
            "cost": cargo_value,
            "payment_method": "cash",
        },
    }

    # receiver national_code (optional)
    if receiver_national_code:
        payload["receiver"]["national_code"] = receiver_national_code[:10].zfill(10)

    # shipping_options from excel columns
    shipping_opts: Dict[str, Any] = {}
    if trip_minutes and trip_minutes > 0:
        shipping_opts["time_limit"] = trip_minutes
    if end_shipping_date:
        shipping_opts["end_shipping"] = end_shipping_date
    if shipping_opts:
        payload["shipping_options"] = shipping_opts

    if include_auth:
        payload["utcms_auth"] = {
            "username": username,
            "password": password,
            "login_url": login_url,
        }

    model = WaybillMapRequest.model_validate(payload)
    excerpt = {
        "username": username,
        "plate": plate,
        "driver_national_code": driver_national_code,
        "sender": sender_name,
        "receiver": receiver_name,
        "origin": {"province": origin_province, "city": origin_city},
        "destination": {"province": destination_province, "city": destination_city},
    }
    return model, excerpt, (username, password)


def _is_retryable_http(exc: HTTPException) -> bool:
    return exc.status_code in (429, 500, 502, 503, 504)


def _detail_text(detail: Any) -> str:
    if isinstance(detail, dict):
        for key in ("detail", "message", "err_desc", "error", "reason"):
            value = detail.get(key)
            if value:
                return str(value)
    return str(detail)


def _collect_failure_artifacts(row_index: int, artifacts_dir: Path) -> List[str]:
    files_to_capture = [
        Path("waybill_map_error.png"),
        Path("waybill_notfound_snapshot.html"),
    ]
    copied: List[str] = []

    timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    artifacts_dir.mkdir(parents=True, exist_ok=True)

    for source_path in files_to_capture:
        if not source_path.exists():
            continue
        target = artifacts_dir / f"row_{row_index}_{timestamp}_{source_path.name}"
        try:
            shutil.copy2(source_path, target)
            copied.append(str(target))
        except Exception:
            continue

    return copied


async def _submit_with_retries(
    request_model: WaybillMapRequest,
    retries: int,
) -> Dict[str, Any]:
    attempts = max(1, retries)
    last_error: Optional[Exception] = None

    for attempt in range(1, attempts + 1):
        try:
            return await waybill_service.create_waybill_with_map(request_model)
        except HTTPException as exc:
            last_error = exc
            if _is_retryable_http(exc) and attempt < attempts:
                await asyncio.sleep(1.2 * attempt)
                continue
            raise
        except Exception as exc:
            last_error = exc
            if attempt < attempts:
                await asyncio.sleep(1.2 * attempt)
                continue
            raise

    if last_error:
        raise last_error
    raise RuntimeError("unknown_submit_error")


async def run(
    excel_path: Path,
    output_json: Path,
    artifacts_dir: Path,
    max_rows: int,
    retries: int,
    live_submit: bool,
    reauth_each_row: bool,
    reverse_geocode: bool,
    login_url: str,
    default_province: str,
    default_city: str,
    captcha_auto_only: bool,
    captcha_auto_attempts: int,
) -> Dict[str, Any]:
    await init_db()
    utcms_config.ALLOW_LIVE_SUBMIT = bool(live_submit)
    utcms_config.CAPTCHA_AUTO_ONLY = bool(captcha_auto_only)
    utcms_config.UTCMS_ENABLE_MANUAL_CAPTCHA = not bool(captcha_auto_only)
    utcms_config.CAPTCHA_AUTO_MAX_ATTEMPTS = max(1, int(captcha_auto_attempts))

    rows = read_xlsx(excel_path)
    if len(rows) < 2:
        raise RuntimeError("Excel does not contain data rows")

    header_map = to_header_map(rows[0])
    data_rows = rows[1:]
    if max_rows > 0:
        data_rows = data_rows[:max_rows]

    geo_resolver = ReverseGeoResolver(enabled=reverse_geocode)
    run_items: List[RunItem] = []
    mode = "full" if live_submit else "safe"

    last_success_credential: Optional[Tuple[str, str]] = None
    started_at = datetime.utcnow().isoformat() + "Z"

    try:
        for offset, row in enumerate(data_rows, start=2):
            for stale_file in ("waybill_map_error.png", "waybill_notfound_snapshot.html"):
                try:
                    Path(stale_file).unlink(missing_ok=True)
                except Exception:
                    pass

            row_started = time.perf_counter()
            username, password = _build_credentials(row, header_map)
            if not username or not password:
                message = "نام کاربری/رمز عبور اکانت ثبت در اکسل خالی است"
                run_items.append(
                    RunItem(
                        row_index=offset,
                        status="failed",
                        message=message,
                        mode=mode,
                        attempt_count=0,
                    )
                )
                print(f"[FAILED] row={offset} {message}")
                continue

            include_auth = reauth_each_row or (last_success_credential != (username, password))

            try:
                request_model, excerpt, credential_key = await _build_request(
                    row=row,
                    header_map=header_map,
                    operation_mode=mode,
                    login_url=login_url,
                    include_auth=include_auth,
                    geo_resolver=geo_resolver,
                    default_province=default_province,
                    default_city=default_city,
                )
            except Exception as exc:
                run_items.append(
                    RunItem(
                        row_index=offset,
                        status="failed",
                        message=f"payload_build_failed: {exc}",
                        mode=mode,
                        attempt_count=0,
                    )
                )
                print(f"[FAILED] row={offset} payload_build_failed={exc}")
                continue

            submit_attempt = 0
            result_payload: Optional[Dict[str, Any]] = None
            failure_message: Optional[str] = None
            failure_detail: Any = None

            while submit_attempt < max(1, retries):
                submit_attempt += 1
                try:
                    result_payload = await _submit_with_retries(request_model, retries=1)
                    break
                except HTTPException as exc:
                    failure_message = _detail_text(exc.detail)
                    failure_detail = {
                        "status_code": exc.status_code,
                        "detail": exc.detail,
                    }

                    should_retry_with_auth = (
                        exc.status_code == 401
                        and not include_auth
                        and bool(username and password)
                    )
                    if should_retry_with_auth:
                        include_auth = True
                        request_model, excerpt, credential_key = await _build_request(
                            row=row,
                            header_map=header_map,
                            operation_mode=mode,
                            login_url=login_url,
                            include_auth=True,
                            geo_resolver=geo_resolver,
                            default_province=default_province,
                            default_city=default_city,
                        )
                        await asyncio.sleep(0.8)
                        continue

                    if _is_retryable_http(exc) and submit_attempt < max(1, retries):
                        await asyncio.sleep(1.2 * submit_attempt)
                        continue
                    break
                except Exception as exc:
                    failure_message = str(exc)
                    failure_detail = {"exception_type": exc.__class__.__name__}
                    if submit_attempt < max(1, retries):
                        await asyncio.sleep(1.2 * submit_attempt)
                        continue
                    break

            duration_seconds = round(time.perf_counter() - row_started, 2)
            if result_payload is not None:
                last_success_credential = credential_key
                run_items.append(
                    RunItem(
                        row_index=offset,
                        status="success",
                        message=str(result_payload.get("status", "submitted")),
                        mode=mode,
                        attempt_count=submit_attempt,
                        request_id=result_payload.get("request_id"),
                        tracking_code=result_payload.get("tracking_code"),
                        duration_seconds=duration_seconds,
                        payload_excerpt=excerpt,
                    )
                )
                print(
                    f"[SUCCESS] row={offset} tracking={result_payload.get('tracking_code')} "
                    f"attempts={submit_attempt} duration={duration_seconds}s"
                )
                continue

            artifacts = _collect_failure_artifacts(offset, artifacts_dir)
            run_items.append(
                RunItem(
                    row_index=offset,
                    status="failed",
                    message=failure_message or "submit_failed",
                    mode=mode,
                    attempt_count=submit_attempt,
                    duration_seconds=duration_seconds,
                    detail=failure_detail,
                    artifacts=artifacts,
                    payload_excerpt=excerpt,
                )
            )
            print(
                f"[FAILED] row={offset} attempts={submit_attempt} "
                f"duration={duration_seconds}s err={failure_message}"
            )
    finally:
        await geo_resolver.close()
        await browser_manager.close()

    total = len(run_items)
    succeeded = sum(1 for item in run_items if item.status == "success")
    failed = sum(1 for item in run_items if item.status == "failed")
    success_rate = round((succeeded / total) * 100, 2) if total else 0.0
    operational_report = await report_service.get_operational_report()

    result = {
        "excel_path": str(excel_path),
        "timestamp": datetime.utcnow().isoformat() + "Z",
        "started_at": started_at,
        "mode": mode,
        "settings": {
            "live_submit": bool(live_submit),
            "retries": max(1, retries),
            "reauth_each_row": bool(reauth_each_row),
            "reverse_geocode": bool(reverse_geocode),
            "captcha_auto_only": bool(captcha_auto_only),
            "captcha_auto_attempts": max(1, int(captcha_auto_attempts)),
            "login_url": login_url,
            "default_province": default_province,
            "default_city": default_city,
        },
        "summary": {
            "total": total,
            "succeeded": succeeded,
            "failed": failed,
            "success_rate": success_rate,
        },
        "items": [
            {
                "row_index": item.row_index,
                "status": item.status,
                "message": item.message,
                "mode": item.mode,
                "attempt_count": item.attempt_count,
                "request_id": item.request_id,
                "tracking_code": item.tracking_code,
                "duration_seconds": item.duration_seconds,
                "detail": item.detail,
                "artifacts": item.artifacts,
                "payload_excerpt": item.payload_excerpt,
            }
            for item in run_items
        ],
        "operational_report": operational_report,
    }

    output_json.parent.mkdir(parents=True, exist_ok=True)
    output_json.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    return result


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Register UTCMS waybills from Excel through web automation (no official API)."
    )
    parser.add_argument(
        "--excel-path",
        default="data/test_waybills.xlsx",
        help="Path to xlsx file.",
    )
    parser.add_argument("--max-rows", type=int, default=0, help="Limit rows. 0 means all data rows.")
    parser.add_argument("--retries", type=int, default=2, help="Retries per row.")
    parser.add_argument(
        "--output-json",
        default="docs/real_web_run_report.json",
        help="Detailed report path.",
    )
    parser.add_argument(
        "--artifacts-dir",
        default="docs/run_artifacts",
        help="Failure artifacts directory.",
    )
    parser.add_argument("--live-submit", action="store_true", help="Submit real waybills (operation_mode=full).")
    parser.add_argument(
        "--reauth-each-row",
        action="store_true",
        help="Force re-login using row credentials for each row.",
    )
    parser.add_argument(
        "--reverse-geocode",
        action="store_true",
        help="Resolve province/city using reverse geocoding (Nominatim).",
    )
    parser.add_argument(
        "--login-url",
        default="https://barname.utcms.ir/Barname/Account/Login",
        help="UTCMS login URL.",
    )
    parser.add_argument(
        "--captcha-auto-only",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Enable fully automatic captcha mode (manual fallback disabled).",
    )
    parser.add_argument(
        "--captcha-auto-attempts",
        type=int,
        default=5,
        help="Max auto attempts for captcha solving.",
    )
    parser.add_argument("--default-province", default="اصفهان", help="Fallback province when geocode is unavailable.")
    parser.add_argument("--default-city", default="اصفهان", help="Fallback city when geocode is unavailable.")
    args = parser.parse_args()

    excel_path = Path(args.excel_path).expanduser()
    output_json = Path(args.output_json)
    artifacts_dir = Path(args.artifacts_dir)

    if not excel_path.exists():
        print(f"excel_not_found: {excel_path}")
        return 1

    result = asyncio.run(
        run(
            excel_path=excel_path,
            output_json=output_json,
            artifacts_dir=artifacts_dir,
            max_rows=max(0, int(args.max_rows)),
            retries=max(1, int(args.retries)),
            live_submit=bool(args.live_submit),
            reauth_each_row=bool(args.reauth_each_row),
            reverse_geocode=bool(args.reverse_geocode),
            login_url=args.login_url.strip(),
            default_province=args.default_province.strip() or "اصفهان",
            default_city=args.default_city.strip() or "اصفهان",
            captcha_auto_only=bool(args.captcha_auto_only),
            captcha_auto_attempts=max(1, int(args.captcha_auto_attempts)),
        )
    )
    print(json.dumps(result["summary"], ensure_ascii=False))
    print(f"report_saved={output_json}")
    return 0 if result["summary"]["failed"] == 0 else 2


if __name__ == "__main__":
    raise SystemExit(main())

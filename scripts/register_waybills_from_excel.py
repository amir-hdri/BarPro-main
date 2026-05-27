#!/usr/bin/env python3
import argparse
import asyncio
import json
import re
import sys
import time
import xml.etree.ElementTree as ET
import zipfile
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from fastapi import HTTPException

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.core.config import utcms_config
from app.schemas.itmb_ws import WS01InsertBOLRequest
from app.services.itmb_ws_service import itmb_ws_service

XML_NS = {
    "a": "http://schemas.openxmlformats.org/spreadsheetml/2006/main",
    "r": "http://schemas.openxmlformats.org/officeDocument/2006/relationships",
}


@dataclass
class RunItem:
    row_index: int
    status: str
    message: str
    trace_code: str | None = None
    err_code: Any | None = None
    detail: Any | None = None
    payload_excerpt: dict[str, Any] | None = None


HEADER_ALIASES = {
    "plate_last_two": ("پلاک ملی: دو رقم آخر پلاک",),
    "plate_three": ("پلاک ملی: سه رقم پلاک",),
    "plate_letter": ("پلاک ملی: حرف پلاک",),
    "plate_first_two": ("پلاک ملی: دو رقم اول پلاک",),
    "driver_national_code": ("کد ملی راننده",),
    "weight_ton": ("وزن بار (تن)",),
    "cargo_count": ("تعداد بار",),
    "cargo_value": ("ارزش بار (ریال)",),
    "sender_name": ("نام فرستنده",),
    "sender_national_code": ("کد ملی فرستنده",),
    "sender_mobile": ("موبایل فرستنده",),
    "sender_phone": ("تلفن ثابت فرستنده",),
    "sender_postal_code": ("کد پستی فرستنده",),
    "sender_lat": ("lat فرستنده",),
    "sender_lng": ("long فرستنده",),
    "sender_address": ("آدرس فرستنده",),
    "receiver_name": ("نام گیرنده",),
    "receiver_national_code": ("کد ملی گیرنده",),
    "receiver_mobile": ("موبایل گیرنده",),
    "receiver_phone": ("تلفن گیرنده",),
    "receiver_postal_code": ("کد پستی گیرنده",),
    "receiver_lat": ("lat گیرنده",),
    "receiver_lng": ("long گیرنده",),
    "receiver_address": ("آدرس گیرنده",),
    "good_type_id": ("کد نوع بار",),
    "good_type_name": ("نام نوع بار",),
    "packing_type_list": ("کد نوع بسته بندی (لیست)",),
    "vehicle_type": ("نوع ناوگان",),
    "driver_password": ("رمز عبور راننده (فقط برای حمل)",),
    "account_username": ("نام کاربری اکانت ثبت",),
    "account_password": ("رمز عبور اکانت ثبت",),
    "trip_minutes": ("فاصله بین شروع و پایان حمل (دقیقه)",),
    "end_shipping_date": ("تاریخ پایان حمل",),
    "driver_username": ("نام کاربری راننده (فقط برای حمل)",),
    "sms_sender": ("ارسال پیامک به فرستنده (لیست)",),
    "insurance_flag": ("بیمه اختیاری بار (لیست)",),
    "company_code": ("شناسه باربری",),
}


def normalize_header_text(value: Any) -> str:
    text = str(value or "").replace("\u200c", " ").replace("\ufeff", " ")
    text = " ".join(text.replace("\r", "\n").split())
    return text.strip()


def _header_matches(actual_header: str, expected_headers: tuple[str, ...]) -> bool:
    normalized_actual = normalize_header_text(actual_header)
    if not normalized_actual:
        return False

    for candidate in expected_headers:
        normalized_candidate = normalize_header_text(candidate)
        if not normalized_candidate:
            continue
        if normalized_actual == normalized_candidate:
            return True
        if normalized_actual.startswith(f"{normalized_candidate} "):
            return True
    return False


def _cell_to_col_index(cell_ref: str) -> int:
    match = re.match(r"([A-Z]+)", cell_ref)
    if not match:
        return 0
    letters = match.group(1)
    index = 0
    for char in letters:
        index = index * 26 + (ord(char) - 64)
    return index - 1


def read_xlsx(path: Path, sheet_name: str | None = None) -> list[list[str]]:
    with zipfile.ZipFile(path) as archive:
        workbook = ET.fromstring(archive.read("xl/workbook.xml"))
        sheets = workbook.find("a:sheets", XML_NS)
        if sheets is None or len(sheets) == 0:
            return []

        rels_root = ET.fromstring(archive.read("xl/_rels/workbook.xml.rels"))
        rel_map = {item.attrib["Id"]: item.attrib["Target"] for item in rels_root}

        selected_sheet = None
        if sheet_name:
            for sheet in sheets:
                if sheet.attrib.get("name") == sheet_name:
                    selected_sheet = sheet
                    break
        if selected_sheet is None:
            selected_sheet = sheets[0]

        rel_id = selected_sheet.attrib.get("{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id")
        target = rel_map.get(rel_id, "")
        if not target:
            return []
        if not target.startswith("xl/"):
            target = f"xl/{target}"

        shared_strings: list[str] = []
        if "xl/sharedStrings.xml" in archive.namelist():
            shared_root = ET.fromstring(archive.read("xl/sharedStrings.xml"))
            for item in shared_root.findall("a:si", XML_NS):
                text = "".join((node.text or "") for node in item.findall(".//a:t", XML_NS))
                shared_strings.append(text)

        sheet_root = ET.fromstring(archive.read(target))
        row_nodes = sheet_root.findall(".//a:sheetData/a:row", XML_NS)

        rows: list[list[str]] = []
        for row_node in row_nodes:
            values_by_index: dict[int, str] = {}
            for cell in row_node.findall("a:c", XML_NS):
                ref = cell.attrib.get("r", "")
                index = _cell_to_col_index(ref)
                cell_type = cell.attrib.get("t")
                value_node = cell.find("a:v", XML_NS)
                raw_value = "" if value_node is None or value_node.text is None else value_node.text

                if cell_type == "s" and raw_value.isdigit():
                    raw_index = int(raw_value)
                    if 0 <= raw_index < len(shared_strings):
                        raw_value = shared_strings[raw_index]
                values_by_index[index] = str(raw_value).strip()

            if not values_by_index:
                continue
            max_index = max(values_by_index.keys())
            row_values = [values_by_index.get(i, "") for i in range(max_index + 1)]
            rows.append(row_values)
        return rows


def normalize_digits(value: Any) -> str:
    text = str(value or "").strip()
    return text.translate(str.maketrans("۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩", "01234567890123456789"))


def normalize_int(value: Any, default: int = 0) -> int:
    text = normalize_digits(value)
    if text == "":
        return default
    try:
        return int(float(text))
    except Exception:
        return default


def normalize_float(value: Any, default: float = 0.0) -> float:
    text = normalize_digits(value).replace(",", "")
    if text == "":
        return default
    try:
        return float(text)
    except Exception:
        return default


def split_name(name: str) -> tuple[str, str | None, int]:
    parts = [part for part in str(name or "").strip().split() if part]
    if not parts:
        return "Unknown", None, 2
    if "شرکت" in parts[0] or "شرکت" in "".join(parts):
        return " ".join(parts), None, 2
    if len(parts) == 1:
        return parts[0], "نامشخص", 1
    return parts[0], " ".join(parts[1:]), 1


def parse_packing_code(value: str) -> int:
    text = normalize_digits(value)
    numbers = re.findall(r"\d+", text)
    if numbers:
        return max(1, int(numbers[0]))
    return 1


def to_header_map(header_row: list[str]) -> dict[str, int]:
    result: dict[str, int] = {}
    for key, expected_headers in HEADER_ALIASES.items():
        result[key] = -1
        for index, actual_header in enumerate(header_row):
            if _header_matches(actual_header, expected_headers):
                result[key] = index
                break
    return result


def get_cell(row: list[str], index: int) -> str:
    if index < 0 or index >= len(row):
        return ""
    return str(row[index]).strip()


def build_ws_payload(
    row: list[str],
    header_map: dict[str, int],
    serial_seed: int,
) -> dict[str, Any]:
    plate_last_two = normalize_int(get_cell(row, header_map["plate_last_two"]), default=10)
    plate_three = normalize_int(get_cell(row, header_map["plate_three"]), default=100)
    plate_first_two = normalize_int(get_cell(row, header_map["plate_first_two"]), default=10)
    plaque_id = f"{plate_first_two:02d}{plate_three:03d}{plate_last_two:02d}"
    plaque_type = get_cell(row, header_map["plate_letter"]) or "ع"

    driver_national_code = normalize_digits(get_cell(row, header_map["driver_national_code"]))[:10].zfill(10)
    sender_name_raw = get_cell(row, header_map["sender_name"]) or "Sender"
    receiver_name_raw = get_cell(row, header_map["receiver_name"]) or "Receiver"
    sender_first_name, sender_last_name, sender_type = split_name(sender_name_raw)
    receiver_first_name, receiver_last_name, receiver_type = split_name(receiver_name_raw)

    sender_national = normalize_digits(get_cell(row, header_map["sender_national_code"]))[:10].zfill(10)
    receiver_national = normalize_digits(get_cell(row, header_map["receiver_national_code"]))[:10].zfill(10)
    issuer_na_code = driver_national_code
    owner_national_id = sender_national

    weight_ton = normalize_float(get_cell(row, header_map["weight_ton"]), default=1.0)
    weight_kg = max(1.0, round(weight_ton * 1000, 2))
    cargo_count = max(1, normalize_int(get_cell(row, header_map["cargo_count"]), default=1))
    cargo_value = max(1, normalize_int(get_cell(row, header_map["cargo_value"]), default=1))
    good_type_id = max(1, normalize_int(get_cell(row, header_map["good_type_id"]), default=1))
    packing_type_id = parse_packing_code(get_cell(row, header_map["packing_type_list"]))

    origin_lat = normalize_float(get_cell(row, header_map["sender_lat"]), default=35.7)
    origin_lng = normalize_float(get_cell(row, header_map["sender_lng"]), default=51.4)
    dest_lat = normalize_float(get_cell(row, header_map["receiver_lat"]), default=36.3)
    dest_lng = normalize_float(get_cell(row, header_map["receiver_lng"]), default=59.6)

    sender_mobile = normalize_digits(get_cell(row, header_map["sender_mobile"]))
    sender_phone = normalize_digits(get_cell(row, header_map["sender_phone"]))
    receiver_mobile = normalize_digits(get_cell(row, header_map["receiver_mobile"]))
    receiver_phone = normalize_digits(get_cell(row, header_map["receiver_phone"]))

    sender_postal = normalize_digits(get_cell(row, header_map["sender_postal_code"]))
    receiver_postal = normalize_digits(get_cell(row, header_map["receiver_postal_code"]))

    company_code = normalize_digits(get_cell(row, header_map["company_code"])) or utcms_config.ITMBOL_COMPANY_CODE
    service_password = (
        get_cell(row, header_map["account_password"])
        or get_cell(row, header_map["driver_password"])
        or utcms_config.ITMBOL_SERVICE_PASSWORD
    )

    issue_time = int(time.time())
    freightage = cargo_value
    total_amount = freightage

    return {
        "CompanyCode": company_code,
        "ServicePassword": service_password,
        "bol": {
            "PlaqueID": plaque_id,
            "PlaqueSN": plate_last_two,
            "PlaqueType": plaque_type,
            "DriverNationalCode": driver_national_code,
            "OWNERNATIONALID": owner_national_id,
            "SenderType": sender_type,
            "SenderName": sender_first_name,
            "SenderLastName": sender_last_name,
            "SenderNationalID": sender_national if sender_type == 1 else None,
            "SenderMobile": sender_mobile or None,
            "SenderPhoneNo": sender_phone or None,
            "SenderPostalCode": sender_postal or None,
            "SenderAddress": f"origin@{origin_lat},{origin_lng}",
            "RecieverType": receiver_type,
            "RecieverName": receiver_first_name,
            "RecieverLastName": receiver_last_name,
            "RecieverNationalID": receiver_national if receiver_type == 1 else None,
            "RecieverMobile": receiver_mobile or None,
            "RecieverPhoneNo": receiver_phone or None,
            "RecieverPostalCode": receiver_postal or None,
            "RecieverAddress": f"destination@{dest_lat},{dest_lng}",
            "Freightage": freightage,
            "PreFreightage": 0,
            "FreightageTax": 0,
            "CompanyCommission": 0,
            "ITServiceCost": 0,
            "InfoServiceCost": 0,
            "InsuranceCosts": 0,
            "TotalAmountPayment": total_amount,
            "Description": f"auto-import row {serial_seed}",
            "SerialNo": serial_seed,
            "IssuerNaCode": issuer_na_code,
            "IssuerMobile": sender_mobile or None,
            "IssueDate": issue_time,
            "LoadingPlacePostalCode": sender_postal or None,
            "LoadingPlaceAddress": f"origin@{origin_lat},{origin_lng}",
            "OffLoadingPlacePostalCode": receiver_postal or None,
            "OffLoadingPlaceAddress": f"destination@{dest_lat},{dest_lng}",
            "OriginLattitude": origin_lat,
            "OriginLongitude": origin_lng,
            "DestinationLattitude": dest_lat,
            "DestinationLongitude": dest_lng,
            "Goods": [
                {
                    "GoodID": good_type_id,
                    "WeightKg": max(1.0, weight_kg),
                    "Value": max(1, cargo_value),
                    "PackingTypeID": max(1, packing_type_id),
                    "GoodtypeID": max(1, good_type_id),
                    "Description": f"count={cargo_count}",
                }
            ],
        },
        "InsertTime": issue_time,
        "InsertPosition": {
            "Latitude": origin_lat,
            "Longitude": origin_lng,
            "Altitude": 0,
            "Bearing": 0,
            "NumberOfSatellite": 0,
            "PDOP": 0,
            "GPSSpeed": 0,
            "GPSMaxSpeed": 0,
            "GPSTotalTraveledDistance": 0,
        },
    }


async def submit_payload(payload: dict[str, Any], retries: int) -> dict[str, Any]:
    last_exc: Exception | None = None
    for attempt in range(1, max(1, retries) + 1):
        try:
            req = WS01InsertBOLRequest.model_validate(payload)
            return await itmb_ws_service.insert_bol(req)
        except HTTPException as exc:
            last_exc = exc
            if exc.status_code in (502, 503) and attempt < retries:
                await asyncio.sleep(1.0 * attempt)
                continue
            raise
        except Exception as exc:
            last_exc = exc
            if attempt < retries:
                await asyncio.sleep(1.0 * attempt)
                continue
            raise
    if last_exc:
        raise last_exc
    raise RuntimeError("submit_failed_unknown")


def ensure_ready_for_live() -> None:
    if not utcms_config.ITMBOL_SERVICE_URL.strip():
        raise RuntimeError("ITMBOL_SERVICE_URL is empty")


async def run(
    excel_path: Path,
    max_rows: int,
    retries: int,
    output_json: Path,
    dry_run: bool,
) -> dict[str, Any]:
    ensure_ready_for_live()
    rows = read_xlsx(excel_path)
    if len(rows) < 2:
        raise RuntimeError("Excel does not contain data rows")

    header_map = to_header_map(rows[0])
    data_rows = rows[1:]
    if max_rows > 0:
        data_rows = data_rows[:max_rows]

    run_items: list[RunItem] = []
    serial_seed = int(datetime.utcnow().timestamp())

    for offset, row in enumerate(data_rows, start=2):
        serial_seed += 1
        payload = build_ws_payload(row=row, header_map=header_map, serial_seed=serial_seed)

        if not payload.get("CompanyCode"):
            run_items.append(
                RunItem(
                    row_index=offset,
                    status="failed",
                    message="CompanyCode is missing",
                    payload_excerpt={"PlaqueID": payload["bol"]["PlaqueID"]},
                )
            )
            print(f"[FAILED] row={offset} CompanyCode is missing")
            continue

        if not payload.get("ServicePassword"):
            run_items.append(
                RunItem(
                    row_index=offset,
                    status="failed",
                    message="ServicePassword is missing",
                    payload_excerpt={"PlaqueID": payload["bol"]["PlaqueID"]},
                )
            )
            print(f"[FAILED] row={offset} ServicePassword is missing")
            continue

        if dry_run:
            try:
                WS01InsertBOLRequest.model_validate(payload)
                run_items.append(
                    RunItem(
                        row_index=offset,
                        status="validated",
                        message="payload_valid",
                        payload_excerpt={
                            "CompanyCode": payload.get("CompanyCode"),
                            "PlaqueID": payload["bol"]["PlaqueID"],
                            "DriverNationalCode": payload["bol"]["DriverNationalCode"],
                        },
                    )
                )
                print(f"[VALID] row={offset} payload validated")
            except Exception as exc:
                run_items.append(
                    RunItem(
                        row_index=offset,
                        status="failed",
                        message=f"validation_error: {exc}",
                        payload_excerpt={
                            "CompanyCode": payload.get("CompanyCode"),
                            "PlaqueID": payload["bol"]["PlaqueID"],
                        },
                    )
                )
                print(f"[FAILED] row={offset} validation_error={exc}")
            continue

        try:
            result = await submit_payload(payload, retries=retries)
            run_items.append(
                RunItem(
                    row_index=offset,
                    status="success",
                    message="ok",
                    trace_code=result.get("bol_trace_code"),
                    payload_excerpt={
                        "CompanyCode": payload.get("CompanyCode"),
                        "PlaqueID": payload["bol"]["PlaqueID"],
                        "DriverNationalCode": payload["bol"]["DriverNationalCode"],
                    },
                )
            )
            print(f"[SUCCESS] row={offset} trace={result.get('bol_trace_code')}")
        except HTTPException as exc:
            detail = exc.detail
            err_code = None
            message = str(detail)
            if isinstance(detail, dict):
                err_code = detail.get("err_code") or detail.get("upstream_status")
                message = detail.get("err_desc") or detail.get("message") or str(detail)
            run_items.append(
                RunItem(
                    row_index=offset,
                    status="failed",
                    message=message,
                    err_code=err_code,
                    detail=detail,
                    payload_excerpt={
                        "CompanyCode": payload.get("CompanyCode"),
                        "PlaqueID": payload["bol"]["PlaqueID"],
                        "DriverNationalCode": payload["bol"]["DriverNationalCode"],
                    },
                )
            )
            print(f"[FAILED] row={offset} status={exc.status_code} err={message}")
        except Exception as exc:
            run_items.append(
                RunItem(
                    row_index=offset,
                    status="failed",
                    message=str(exc),
                    detail={"exception_type": exc.__class__.__name__},
                    payload_excerpt={
                        "CompanyCode": payload.get("CompanyCode"),
                        "PlaqueID": payload["bol"]["PlaqueID"],
                        "DriverNationalCode": payload["bol"]["DriverNationalCode"],
                    },
                )
            )
            print(f"[FAILED] row={offset} exc={exc}")

    total = len(run_items)
    succeeded = sum(1 for item in run_items if item.status == "success")
    validated = sum(1 for item in run_items if item.status == "validated")
    failed = sum(1 for item in run_items if item.status == "failed")

    result_payload = {
        "excel_path": str(excel_path),
        "timestamp": datetime.utcnow().isoformat() + "Z",
        "summary": {
            "total": total,
            "succeeded": succeeded,
            "failed": failed,
            "validated": validated,
            "success_rate": round((succeeded / total) * 100, 2) if total else 0.0,
        },
        "items": [
            {
                "row_index": item.row_index,
                "status": item.status,
                "message": item.message,
                "err_code": item.err_code,
                "detail": item.detail,
                "trace_code": item.trace_code,
                "payload_excerpt": item.payload_excerpt,
            }
            for item in run_items
        ],
    }

    output_json.parent.mkdir(parents=True, exist_ok=True)
    output_json.write_text(json.dumps(result_payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return result_payload


def main() -> int:
    parser = argparse.ArgumentParser(description="Register waybills from Excel in real ITMB service.")
    parser.add_argument(
        "--excel-path",
        default="data/test_waybills.xlsx",
        help="Path to xlsx file",
    )
    parser.add_argument("--max-rows", type=int, default=0, help="Limit rows. 0 means all rows.")
    parser.add_argument("--retries", type=int, default=2, help="Retry count for transient failures.")
    parser.add_argument(
        "--output-json",
        default="docs/real_run_report.json",
        help="Path for detailed run report json",
    )
    parser.add_argument("--dry-run", action="store_true", help="Validate payloads without sending to ITMB")
    args = parser.parse_args()

    excel_path = Path(args.excel_path).expanduser()
    output_json = Path(args.output_json)

    if not excel_path.exists():
        print(f"excel_not_found: {excel_path}")
        return 1

    result = asyncio.run(
        run(
            excel_path=excel_path,
            max_rows=max(0, int(args.max_rows)),
            retries=max(1, int(args.retries)),
            output_json=output_json,
            dry_run=args.dry_run,
        )
    )
    print(json.dumps(result["summary"], ensure_ascii=False))
    print(f"report_saved={output_json}")
    return 0 if result["summary"]["failed"] == 0 else 2


if __name__ == "__main__":
    raise SystemExit(main())

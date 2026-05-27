"""Service for handling manual waybill entry and Excel file uploads."""

import logging
import uuid
from pathlib import Path
from typing import Any

from fastapi import UploadFile

from app.core.config import utcms_config
from app.schemas.waybill import (
    CargoModel,
    FinancialModel,
    GeoCoordinateModel,
    LocationModel,
    OperationMode,
    ReceiverModel,
    SenderModel,
    UTCMSLoginModel,
    VehicleModel,
    WaybillMapRequest,
)

logger = logging.getLogger(__name__)


def normalize_digits(text: str) -> str:
    """Normalize Persian/Arabic digits to English."""
    if not text:
        return ""
    persian_digits = "۰۱۲۳۴۵۶۷۸۹"
    arabic_digits = "٠١٢٣٤٥٦٧٨٩"
    result = text
    for i, digit in enumerate(persian_digits):
        result = result.replace(digit, str(i))
    for i, digit in enumerate(arabic_digits):
        result = result.replace(digit, str(i))
    return result


def normalize_float(value: Any, default: float = 0.0) -> float:
    """Normalize value to float."""
    if value is None:
        return default
    try:
        return float(str(value).strip().replace(",", ""))
    except (ValueError, TypeError):
        return default


def normalize_int(value: Any, default: int = 0) -> int:
    """Normalize value to integer."""
    if value is None:
        return default
    try:
        return int(float(str(value).strip().replace(",", "")))
    except (ValueError, TypeError):
        return default


def clean_text(value: Any) -> str:
    """Clean and normalize text value."""
    return str(value or "").strip()


def normalize_phone(value: Any) -> str:
    """Normalize phone number."""
    phone = normalize_digits(str(value or "").strip())
    # Remove spaces and dashes
    phone = phone.replace(" ", "").replace("-", "")
    # Add country code if needed
    if phone.startswith("0"):
        phone = "+98" + phone[1:]
    return phone


def format_plate(
    plate_first_two: Any,
    plate_letter: Any,
    plate_three: Any,
    plate_last_two: Any,
) -> str:
    """Format vehicle plate number."""
    first_two = normalize_int(plate_first_two, default=0)
    three = normalize_int(plate_three, default=0)
    last_two = normalize_int(plate_last_two, default=0)
    letter = clean_text(plate_letter) or "ع"
    return f"{first_two:02d}{letter}{three:03d}{last_two:02d}"


class ExcelWaybillParser:
    """Parse Excel files for waybill data."""

    # Header mapping: expected field -> possible column names
    HEADER_MAPPING = {
        "sender_name": ["نام فرستنده", "فرستنده", "sender_name"],
        "sender_national_code": ["کد ملی فرستنده", "کد ملی", "sender_national_code"],
        "sender_phone": ["موبایل فرستنده", "تلفن فرستنده", "sender_phone", "sender_mobile"],
        "sender_address": ["آدرس فرستنده", "sender_address"],
        "sender_lat": ["lat فرستنده", "عرض جغرافیایی فرستنده", "sender_lat"],
        "sender_lng": ["long فرستنده", "طول جغرافیایی فرستنده", "sender_lng"],

        "receiver_name": ["نام گیرنده", "گیرنده", "receiver_name"],
        "receiver_national_code": ["کد ملی گیرنده", "receiver_national_code"],
        "receiver_phone": ["موبایل گیرنده", "تلفن گیرنده", "receiver_phone", "receiver_mobile"],
        "receiver_address": ["آدرس گیرنده", "receiver_address"],
        "receiver_lat": ["lat گیرنده", "عرض جغرافیایی گیرنده", "receiver_lat"],
        "receiver_lng": ["long گیرنده", "طول جغرافیایی گیرنده", "receiver_lng"],

        "origin_province": ["استان مبدأ", "استان مبدا", "origin_province"],
        "origin_city": ["شهر مبدأ", "شهر مبدا", "origin_city"],
        "origin_district": ["منطقه مبدأ", "منطقه مبدا", "origin_district"],
        "origin_address": ["آدرس مبدأ", "origin_address"],
        "origin_lat": ["lat مبدأ", "lat مبدا", "origin_lat"],
        "origin_lng": ["long مبدأ", "long مبدا", "origin_lng"],

        "destination_province": ["استان مقصد", "destination_province"],
        "destination_city": ["شهر مقصد", "destination_city"],
        "destination_district": ["منطقه مقصد", "destination_district"],
        "destination_address": ["آدرس مقصد", "destination_address"],
        "destination_lat": ["lat مقصد", "destination_lat"],
        "destination_lng": ["long مقصد", "destination_lng"],

        "cargo_type": ["نوع کالا", "cargo_type"],
        "cargo_weight": ["وزن بار (تن)", "وزن کالا", "cargo_weight", "weight_ton"],
        "cargo_count": ["تعداد بار", "تعداد کالا", "cargo_count"],
        "cargo_description": ["توضیحات کالا", "cargo_description"],

        "driver_national_code": ["کد ملی راننده", "driver_national_code"],
        "driver_phone": ["تلفن راننده", "driver_phone"],
        "plate_first_two": ["پلاک ملی: دو رقم اول پلاک", "plate_first_two"],
        "plate_letter": ["پلاک ملی: حرف پلاک", "plate_letter"],
        "plate_three": ["پلاک ملی: سه رقم پلاک", "plate_three"],
        "plate_last_two": ["پلاک ملی: دو رقم آخر پلاک", "plate_last_two"],

        "cost": ["هزینه حمل", "cost", "freight_cost"],
        "payment_method": ["روش پرداخت", "payment_method"],

        "account_username": ["نام کاربری اکانت ثبت", "account_username", "username"],
        "account_password": ["رمز عبور اکانت ثبت", "account_password", "password"],
    }

    @classmethod
    def parse_header_row(cls, headers: list[str]) -> dict[str, int]:
        """Parse header row and map columns to fields."""
        column_map = {}
        for col_idx, header in enumerate(headers):
            header_normalized = clean_text(header).replace("\u200c", " ")

            for field, possible_names in cls.HEADER_MAPPING.items():
                for name in possible_names:
                    if header_normalized == name or header_normalized.lower() == name.lower():
                        column_map[field] = col_idx
                        break

        return column_map

    @classmethod
    def get_cell(cls, row: list[str], column_map: dict[str, int], field: str, default: str = "") -> str:
        """Get cell value from row using column map."""
        col_idx = column_map.get(field)
        if col_idx is None or col_idx >= len(row):
            return default
        return clean_text(row[col_idx])

    @classmethod
    def row_to_waybill_request(
        cls,
        row: list[str],
        column_map: dict[str, int],
        operation_mode: OperationMode = OperationMode.SAFE,
    ) -> WaybillMapRequest | None:
        """Convert Excel row to WaybillMapRequest."""
        try:
            # Extract sender info
            sender_name = cls.get_cell(row, column_map, "sender_name")
            sender_national_code = cls.get_cell(row, column_map, "sender_national_code")
            sender_phone = cls.get_cell(row, column_map, "sender_phone")
            sender_address = cls.get_cell(row, column_map, "sender_address")

            if not sender_name or not sender_national_code:
                return None

            sender = SenderModel(
                name=sender_name,
                phone=normalize_phone(sender_phone),
                address=sender_address,
                national_code=normalize_digits(sender_national_code),
            )

            # Extract receiver info
            receiver_name = cls.get_cell(row, column_map, "receiver_name")
            receiver_national_code = cls.get_cell(row, column_map, "receiver_national_code")
            receiver_phone = cls.get_cell(row, column_map, "receiver_phone")
            receiver_address = cls.get_cell(row, column_map, "receiver_address")

            receiver = ReceiverModel(
                name=receiver_name,
                phone=normalize_phone(receiver_phone),
                address=receiver_address,
                national_code=normalize_digits(receiver_national_code) if receiver_national_code else None,
            )

            # Extract origin
            origin_province = cls.get_cell(row, column_map, "origin_province")
            origin_city = cls.get_cell(row, column_map, "origin_city")
            origin_district = cls.get_cell(row, column_map, "origin_district")
            origin_address = cls.get_cell(row, column_map, "origin_address")
            origin_lat = normalize_float(cls.get_cell(row, column_map, "origin_lat"))
            origin_lng = normalize_float(cls.get_cell(row, column_map, "origin_lng"))

            origin_coords = None
            if origin_lat and origin_lng:
                origin_coords = GeoCoordinateModel(lat=origin_lat, lng=origin_lng)

            origin = LocationModel(
                province=origin_province,
                city=origin_city,
                district=origin_district if origin_district else None,
                address=origin_address,
                coordinates=origin_coords,
            )

            # Extract destination
            destination_province = cls.get_cell(row, column_map, "destination_province")
            destination_city = cls.get_cell(row, column_map, "destination_city")
            destination_district = cls.get_cell(row, column_map, "destination_district")
            destination_address = cls.get_cell(row, column_map, "destination_address")
            dest_lat = normalize_float(cls.get_cell(row, column_map, "destination_lat"))
            dest_lng = normalize_float(cls.get_cell(row, column_map, "destination_lng"))

            dest_coords = None
            if dest_lat and dest_lng:
                dest_coords = GeoCoordinateModel(lat=dest_lat, lng=dest_lng)

            destination = LocationModel(
                province=destination_province,
                city=destination_city,
                district=destination_district if destination_district else None,
                address=destination_address,
                coordinates=dest_coords,
            )

            # Extract cargo
            cargo_type = cls.get_cell(row, column_map, "cargo_type")
            cargo_weight = normalize_float(cls.get_cell(row, column_map, "cargo_weight"), default=1.0)
            cargo_count = normalize_int(cls.get_cell(row, column_map, "cargo_count"), default=1)
            cargo_description = cls.get_cell(row, column_map, "cargo_description")

            cargo = CargoModel(
                type=cargo_type if cargo_type else None,
                weight=cargo_weight,
                count=str(cargo_count),
                description=cargo_description if cargo_description else None,
            )

            # Extract vehicle
            driver_national_code = cls.get_cell(row, column_map, "driver_national_code")
            driver_phone = cls.get_cell(row, column_map, "driver_phone")
            plate_first_two = cls.get_cell(row, column_map, "plate_first_two")
            plate_letter = cls.get_cell(row, column_map, "plate_letter")
            plate_three = cls.get_cell(row, column_map, "plate_three")
            plate_last_two = cls.get_cell(row, column_map, "plate_last_two")

            plate = None
            if plate_first_two or plate_letter or plate_three or plate_last_two:
                plate = format_plate(plate_first_two, plate_letter, plate_three, plate_last_two)

            vehicle = VehicleModel(
                driver_national_code=normalize_digits(driver_national_code) if driver_national_code else None,
                driver_phone=normalize_phone(driver_phone) if driver_phone else None,
                plate=plate,
                type=None,
            )

            # Extract financial
            cost = cls.get_cell(row, column_map, "cost")
            payment_method = cls.get_cell(row, column_map, "payment_method")

            financial = FinancialModel(
                cost=normalize_float(cost) if cost else None,
                payment_method=payment_method if payment_method else None,
            )

            # Extract auth credentials
            account_username = cls.get_cell(row, column_map, "account_username")
            account_password = cls.get_cell(row, column_map, "account_password")

            utcms_auth = None
            if account_username and account_password:
                utcms_auth = UTCMSLoginModel(
                    username=account_username,
                    password=account_password,
                )

            return WaybillMapRequest(
                operation_mode=operation_mode,
                utcms_auth=utcms_auth,
                sender=sender,
                receiver=receiver,
                origin=origin,
                destination=destination,
                cargo=cargo,
                vehicle=vehicle,
                financial=financial,
                shipping_options=None,
            )

        except Exception as exc:
            logger.warning(
                "excel_row_parse_failed",
                extra={"extra_fields": {"error": str(exc), "row_data": row[:5]}},
            )
            return None


class ManualWaybillService:
    """Service for manual waybill entry validation and processing."""

    @staticmethod
    def validate_manual_entry(request: WaybillMapRequest) -> dict[str, Any]:
        """Validate manual entry and return validation summary."""
        errors = []
        warnings = []

        # Validate sender
        if not request.sender.name.strip():
            errors.append("نام فرستنده الزامی است")
        if not request.sender.phone.strip():
            errors.append("تلفن فرستنده الزامی است")
        if not request.sender.national_code.strip():
            errors.append("کد ملی فرستنده الزامی است")
        elif len(normalize_digits(request.sender.national_code)) != 10:
            warnings.append("کد ملی فرستنده ممکن است نامعتبر باشد")

        # Validate receiver
        if not request.receiver.name.strip():
            errors.append("نام گیرنده الزامی است")
        if not request.receiver.phone.strip():
            errors.append("تلفن گیرنده الزامی است")

        # Validate origin
        if not request.origin.province.strip():
            errors.append("استان مبدأ الزامی است")
        if not request.origin.city.strip():
            errors.append("شهر مبدأ الزامی است")

        # Validate destination
        if not request.destination.province.strip():
            errors.append("استان مقصد الزامی است")
        if not request.destination.city.strip():
            errors.append("شهر مقصد الزامی است")

        # Validate cargo
        if not request.cargo.weight or request.cargo.weight <= 0:
            errors.append("وزن کالا باید مثبت باشد")

        # Validate auth
        has_request_auth = (
            request.utcms_auth
            and request.utcms_auth.username.strip()
            and request.utcms_auth.password.strip()
        )
        if not has_request_auth:
            errors.append("اطلاعات ورود UTCMS باید برای هر راننده یا هر درخواست به صورت صریح ارسال شود")

        return {
            "valid": len(errors) == 0,
            "errors": errors,
            "warnings": warnings,
            "field_count": 15,
            "completed_fields": ManualWaybillService._count_completed_fields(request),
        }

    @staticmethod
    def _count_completed_fields(request: WaybillMapRequest) -> int:
        """Count number of completed fields."""
        count = 0
        total = 20

        if request.sender.name: count += 1
        if request.sender.phone: count += 1
        if request.sender.national_code: count += 1
        if request.sender.address: count += 1

        if request.receiver.name: count += 1
        if request.receiver.phone: count += 1
        if request.receiver.address: count += 1

        if request.origin.province: count += 1
        if request.origin.city: count += 1
        if request.origin.address: count += 1

        if request.destination.province: count += 1
        if request.destination.city: count += 1
        if request.destination.address: count += 1

        if request.cargo.weight: count += 1
        if request.vehicle.driver_national_code: count += 1
        if request.vehicle.plate: count += 1
        if request.financial.cost: count += 1
        if request.utcms_auth and request.utcms_auth.username: count += 1
        if request.utcms_auth and request.utcms_auth.password: count += 1

        return count


class ExcelWaybillService:
    """Service for Excel file upload and batch processing."""

    def __init__(self):
        self.parser = ExcelWaybillParser()
        self.manual_service = ManualWaybillService()

    async def parse_excel_file(
        self,
        file: UploadFile,
        operation_mode: OperationMode = OperationMode.SAFE,
    ) -> dict[str, Any]:
        """Parse uploaded Excel file and return waybill requests."""
        try:
            # Read file content
            content = await file.read()

            # Save to temp file for parsing
            temp_dir = Path("tmp")
            temp_dir.mkdir(exist_ok=True)
            temp_file = temp_dir / f"upload_{uuid.uuid4().hex[:8]}_{file.filename}"
            temp_file.write_bytes(content)

            # Parse using existing Excel reader
            from scripts.register_waybills_from_excel import read_xlsx

            rows = read_xlsx(temp_file)
            if not rows or len(rows) < 2:
                return {
                    "success": False,
                    "error": "فایل اکسل باید شامل هدر و حداقل یک ردیف داده باشد",
                    "row_count": 0,
                }

            # Parse headers
            headers = rows[0]
            column_map = self.parser.parse_header_row(headers)

            # Parse data rows
            waybills = []
            errors = []
            for idx, row in enumerate(rows[1:], start=2):
                try:
                    waybill = self.parser.row_to_waybill_request(
                        row, column_map, operation_mode
                    )
                    if waybill:
                        # Validate
                        validation = self.manual_service.validate_manual_entry(waybill)
                        waybills.append({
                            "row": idx,
                            "waybill": waybill,
                            "validation": validation,
                        })
                    else:
                        errors.append({
                            "row": idx,
                            "error": "داده‌های ناکافی برای ایجاد بارنامه",
                        })
                except Exception as exc:
                    errors.append({
                        "row": idx,
                        "error": str(exc),
                    })

            # Cleanup temp file
            temp_file.unlink(missing_ok=True)

            return {
                "success": True,
                "file_name": file.filename,
                "total_rows": len(rows) - 1,
                "valid_waybills": len(waybills),
                "errors": len(errors),
                "waybills": waybills,
                "error_details": errors,
                "column_map": column_map,
            }

        except Exception as exc:
            logger.exception(
                "excel_parse_failed",
                extra={"extra_fields": {"filename": file.filename, "error": str(exc)}},
            )
            return {
                "success": False,
                "error": f"خطا در پردازش فایل اکسل: {str(exc)}",
                "row_count": 0,
            }

    async def process_excel_waybills(
        self,
        file: UploadFile,
        operation_mode: OperationMode = OperationMode.SAFE,
        skip_invalid: bool = True,
    ) -> dict[str, Any]:
        """Parse and process all waybills from Excel file."""
        # First parse the file
        parse_result = await self.parse_excel_file(file, operation_mode)

        if not parse_result["success"]:
            return parse_result

        # Process each waybill
        results = []
        success_count = 0
        error_count = 0

        for item in parse_result["waybills"]:
            try:
                waybill: WaybillMapRequest = item["waybill"]

                # Check if live submit is allowed
                if operation_mode == OperationMode.FULL and not utcms_config.ALLOW_LIVE_SUBMIT:
                    if skip_invalid:
                        error_count += 1
                        results.append({
                            "row": item["row"],
                            "status": "skipped",
                            "error": "ارسال واقعی غیرفعال است",
                        })
                        continue

                # Here you would call the waybill service to actually process
                # For now, just mark as queued
                results.append({
                    "row": item["row"],
                    "status": "queued",
                    "validation": item["validation"],
                })
                success_count += 1

            except Exception as exc:
                error_count += 1
                results.append({
                    "row": item["row"],
                    "status": "failed",
                    "error": str(exc),
                })

        return {
            "success": True,
            "file_name": parse_result["file_name"],
            "total_processed": len(results),
            "success_count": success_count,
            "error_count": error_count,
            "results": results,
        }


# Singleton instance
excel_waybill_service = ExcelWaybillService()
manual_waybill_service = ManualWaybillService()

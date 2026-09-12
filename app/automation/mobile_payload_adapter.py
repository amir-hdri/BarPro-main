"""Translate BarPro's normalized waybill payload to the UTCMS mobile DTO.

The mobile application is used as a contract reference only. This module
keeps the mapping explicit and refuses to invent values for required fields.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from typing import Any


def _mapping(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, Mapping) else {}


def _required(mapping: Mapping[str, Any], key: str, label: str) -> Any:
    value = mapping.get(key)
    if value is None or (isinstance(value, str) and not value.strip()):
        raise ValueError(f"{label} برای transport موبایل الزامی است")
    return value


def _value(mapping: Mapping[str, Any], *keys: str) -> Any:
    for key in keys:
        value = mapping.get(key)
        if value is not None and not (isinstance(value, str) and not value.strip()):
            return value
    return None


def _required_alias(mapping: Mapping[str, Any], keys: tuple[str, ...], label: str) -> Any:
    value = _value(mapping, *keys)
    if value is None:
        raise ValueError(f"{label} برای transport موبایل الزامی است")
    return value


def _party_payload(party: Mapping[str, Any], label: str) -> dict[str, Any]:
    is_company = bool(_value(party, "is_company", "isCompany")) or str(
        _value(party, "entity_type", "type") or ""
    ).lower() in {"company", "legal", "حقوقی", "2"}
    first_name = _value(party, "first_name", "firstName")
    last_name = _value(party, "last_name", "lastName")
    full_name = str(_value(party, "name", "full_name", "fullName") or "").strip()
    if not first_name and not last_name and full_name and not is_company:
        parts = full_name.split()
        if len(parts) >= 2:
            first_name, last_name = parts[0], " ".join(parts[1:])
    if is_company and not first_name:
        first_name = _value(party, "company_name", "office_name", "name")
    return {
        "isCompany": is_company,
        "firstName": _required_alias({"value": first_name}, ("value",), f"نام {label}"),
        "lastName": str(last_name or "").strip(),
        "nationalCode": _required_alias(party, ("national_code", "nationalCode"), f"کد ملی {label}"),
        "mobile": _required_alias(party, ("phone", "mobile", "mobile_no"), f"موبایل {label}"),
        "postalCode": _required_alias(party, ("postal_code", "postalCode"), f"کدپستی {label}"),
        "telNumber": str(_value(party, "landline", "tel_number", "telNumber", "phone_number") or "").strip(),
    }


def _location_payload(location: Mapping[str, Any], label: str) -> dict[str, Any]:
    coordinates = _mapping(_value(location, "coordinates"))
    lat = _value(location, "lat", "latitude")
    lon = _value(location, "lon", "lng", "longitude")
    if lat is None:
        lat = _value(coordinates, "lat", "latitude")
    if lon is None:
        lon = _value(coordinates, "lon", "lng", "longitude")
    province = _required_alias(location, ("province", "state_name", "stateName"), f"استان {label}")
    city = _required_alias(location, ("city", "city_name", "cityName"), f"شهر {label}")
    payload: dict[str, Any] = {
        "province": province,
        "city": city,
        "stateName": province,
        "cityName": city,
        "address": _required_alias(location, ("address",), f"آدرس {label}"),
        "postalCode": _required_alias(location, ("postal_code", "postalCode"), f"کدپستی {label}"),
        "lat": _required_alias({"value": lat}, ("value",), f"عرض جغرافیایی {label}"),
        "lon": _required_alias({"value": lon}, ("value",), f"طول جغرافیایی {label}"),
    }
    for opt_key in ("primary", "county", "district", "neighbourhood", "plaque"):
        val = _value(location, opt_key)
        if val is not None:
            payload[opt_key] = val
    return payload


def _load_items(cargo: Mapping[str, Any]) -> list[dict[str, Any]]:
    raw_items = _value(cargo, "items", "load_list", "loadList")
    items = raw_items if isinstance(raw_items, list) else [cargo]
    if not items:
        raise ValueError("حداقل یک محموله برای transport موبایل الزامی است")
    result: list[dict[str, Any]] = []
    for index, raw_item in enumerate(items, start=1):
        item = _mapping(raw_item)
        result.append(
            {
                "productId": _required_alias(
                    item, ("product_id", "productId"), f"شناسه کالا در محموله {index}"
                ),
                # ``wheight`` is the misspelled key used by the APK DTO.
                "wheight": _required_alias(item, ("weight", "wheight"), f"وزن محموله {index}"),
                "packTypeId": _required_alias(
                    item, ("pack_type_id", "packTypeId"), f"شناسه بسته‌بندی محموله {index}"
                ),
                "description": str(_value(item, "description") or "").strip(),
                "boxNum": _required_alias(item, ("count", "box_num", "boxNum"), f"تعداد بسته در محموله {index}"),
            }
        )
    return result


def validate_mobile_source_payload(payload: Mapping[str, Any]) -> list[str]:
    """Reject values that the web normalizer or APK would silently backfill."""
    errors: list[str] = []
    financial = _mapping(payload.get("financial"))
    explicit_cost = (
        financial.get("cost")
        or financial.get("fare")
        or financial.get("rent")
        or payload.get("cost")
        or payload.get("fare")
        or payload.get("rent")
    )
    if explicit_cost in (None, ""):
        errors.append("کرایه باید صریحاً در payload موبایل وارد شود")
    cargo = _mapping(payload.get("cargo"))
    raw_items = _value(cargo, "items", "load_list", "loadList")
    items = raw_items if isinstance(raw_items, list) else [cargo]
    for index, raw_item in enumerate(items, start=1):
        item = _mapping(raw_item)
        if _value(item, "count", "box_num", "boxNum") in (None, ""):
            errors.append(f"تعداد بسته در محموله {index}")
        if _value(item, "product_id", "productId") in (None, ""):
            errors.append(f"شناسه کالا در محموله {index}")
        if _value(item, "pack_type_id", "packTypeId") in (None, ""):
            errors.append(f"شناسه بسته‌بندی محموله {index}")
    for key, label in (("origin", "مبدا"), ("destination", "مقصد")):
        location = _mapping(payload.get(key))
        if _value(location, "postal_code", "postalCode") in (None, ""):
            errors.append(f"کدپستی {label}")
        if _value(location, "lat", "latitude") is None and not _mapping(_value(location, "coordinates")):
            errors.append(f"عرض جغرافیایی {label}")
        if _value(location, "lon", "lng", "longitude") is None and not _mapping(_value(location, "coordinates")):
            errors.append(f"طول جغرافیایی {label}")
    return errors


def build_mobile_document_payload(
    payload: Mapping[str, Any], *, token: str, cap_token: str | None = None
) -> dict[str, Any]:
    """Build InsertDocumentHagigiV3 body from a normalized BarPro payload."""

    if not token or not token.strip():
        raise ValueError("token احراز هویت موبایل خالی است")

    sender = _mapping(payload.get("sender"))
    receiver = _mapping(payload.get("receiver"))
    origin = _mapping(payload.get("origin"))
    destination = _mapping(payload.get("destination"))
    cargo = _mapping(payload.get("cargo"))
    vehicle = _mapping(payload.get("vehicle"))
    financial = _mapping(payload.get("financial"))
    shipping = _mapping(payload.get("shipping_options"))

    errors = validate_mobile_source_payload(payload)
    if errors:
        raise ValueError("، ".join(errors))
    is_draft = bool(payload.get("is_draft", False))
    if not is_draft and not str(cap_token or "").strip():
        raise ValueError("CAPTCHA صدور برای سند نهایی transport موبایل الزامی است")

    rent = _required_alias(financial, ("cost", "fare", "rent"), "کرایه")
    insurance = _mapping(payload.get("insurance"))
    if not insurance:
        raise ValueError("اطلاعات بیمه برای transport موبایل الزامی است")

    t1 = _value(vehicle, "t1")
    t2 = _value(vehicle, "t2")
    t3 = _value(vehicle, "t3")
    t4 = _value(vehicle, "t4")
    if (t1 is None or t2 is None or t3 is None or t4 is None) and _value(vehicle, "plate"):
        plate_str = str(_value(vehicle, "plate") or "")
        norm = plate_str.strip().replace(" ", "").replace("‌", "").replace("ایران", "")
        for idx, digit in enumerate("۰۱۲۳۴۵۶۷۸۹"):
            norm = norm.replace(digit, str(idx))
        for idx, digit in enumerate("٠١٢٣٤٥٦٧٨٩"):
            norm = norm.replace(digit, str(idx))
        match = re.fullmatch(r"(\d{2})([^\d]+)(\d{3})(\d{2})", norm)
        if match:
            # APK field order follows the natural Iranian plate layout:
            # two digits, letter, three digits, Iran/serial digits.
            t1 = t1 or match.group(1)
            t2 = t2 or match.group(2)
            t3 = t3 or match.group(3)
            t4 = t4 or match.group(4)
            supplied = (t1, t2, t3, t4)
            natural = match.groups()
            if all(value is not None for value in supplied) and tuple(str(value) for value in supplied) != natural:
                raise ValueError("اجزای پلاک با قالب واقعی پلاک ایران مطابقت ندارد")

    bearing_cost = _value(financial, "bearing_cost", "bearingCost")
    pre_rent = _value(financial, "pre_rent", "preRent")
    post_rent = _value(financial, "post_rent", "postRent")
    fuel_type = _value(shipping, "fuel_type") or _value(payload, "fuel_type") or 1
    send_sms = bool(_value(shipping, "send_sms", "sendSMS") or _value(payload, "send_sms", "sendSMS") or False)
    doc_id = _value(payload, "doc_id", "docID") or 0
    insurance_cover = _value(insurance, "cover", "insurance_cover", "insuranceCover")

    body: dict[str, Any] = {
        "token": token,
        "load": _load_items(cargo),
        "source": _location_payload(origin, "مبدا"),
        "destination": _location_payload(destination, "مقصد"),
        "sender": _party_payload(sender, "فرستنده"),
        "receiver": _party_payload(receiver, "گیرنده"),
        "driverNationalCode": _required_alias(
            vehicle, ("driver_national_code", "driverNationalCode"), "کد ملی راننده"
        ),
        "truck": {
            "tagType": _required_alias(vehicle, ("tag_type", "tagType"), "نوع پلاک"),
            "t1": _required_alias({"value": t1}, ("value",), "بخش اول پلاک"),
            "t2": _required_alias({"value": t2}, ("value",), "بخش دوم پلاک"),
            "t3": _required_alias({"value": t3}, ("value",), "حرف پلاک"),
            "t4": _required_alias({"value": t4}, ("value",), "بخش چهارم پلاک"),
            "capacity": _required_alias(vehicle, ("capacity",), "ظرفیت خودرو"),
            "haveCertificate": bool(_value(vehicle, "have_certificate", "haveCertificate")),
            "have3rdInsurance": bool(_value(vehicle, "have_3rd_insurance", "have3rdInsurance")),
            "type": _required_alias(vehicle, ("type", "vehicle_type"), "نوع خودرو"),
        },
        "insurance": {
            "haveInsurance": bool(_value(insurance, "have_insurance", "haveInsurance")),
            "insuranceCover": insurance_cover if insurance_cover is not None else 0,
        },
        "value": _required_alias(cargo, ("value", "approximate_value", "approximateValueOfLoad"), "ارزش کالا"),
        "bearingCost": bearing_cost if bearing_cost is not None else 0,
        "rent": rent,
        "preRent": pre_rent if pre_rent is not None else 0,
        "postRent": post_rent if post_rent is not None else rent,
        "fuelType": fuel_type,
        "sendSMS": send_sms,
        "docID": doc_id,
        "isDraft": is_draft,
        "selfDeclaredTimeOfStartShipment": _value(payload, "self_declared_time_of_start_shipment", "selfDeclaredTimeOfStartShipment"),
    }
    if cap_token and cap_token.strip():
        body["capToken"] = cap_token.strip()
    return body


__all__ = ["build_mobile_document_payload", "validate_mobile_source_payload"]

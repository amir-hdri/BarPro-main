import base64
import json
import time
from collections.abc import Iterable
from dataclasses import dataclass
from typing import Any

import httpx
from fastapi import HTTPException

from app.core.config import utcms_config
from app.schemas.itmb_ws import BOLCnt
from app.services.itmb_common import resolve_itmb_auth


@dataclass
class BaseInfoCacheEntry:
    data: Any
    fetched_at: int


class ITMBBaseInfoService:
    REFERENCE_METHODS = {
        "plate_types": "GetBaseInfoPlateType_46WS",
        "province_cities": "GetBaseInfoProvinceCity_43WS",
        "goods": "GetBaseInfoGood_34WS",
        "packing_types": "GetBaseInfoPackingType_33WS",
        "good_types": "GetBaseInfoGoodType_31WS",
    }

    def __init__(self) -> None:
        self._cache: dict[str, BaseInfoCacheEntry] = {}

    @staticmethod
    def _now() -> int:
        return int(time.time())

    def _is_stale(self, entry: BaseInfoCacheEntry | None) -> bool:
        if entry is None:
            return True
        ttl = max(60, utcms_config.ITMBOL_BASEINFO_CACHE_TTL_SECONDS)
        return (self._now() - entry.fetched_at) >= ttl

    @staticmethod
    def _extract_result_text(response_text: str) -> str:
        text = response_text.strip()
        if not text:
            raise HTTPException(status_code=502, detail="پاسخ خالی از وب‌سرویس دریافت شد")

        try:
            parsed = json.loads(text)
        except json.JSONDecodeError:
            return text

        if isinstance(parsed, dict) and "d" in parsed:
            return str(parsed["d"]).strip()
        if isinstance(parsed, str):
            return parsed.strip()
        return text

    @staticmethod
    def _decode_base64_json(encoded_text: str) -> Any:
        try:
            decoded = base64.b64decode(encoded_text).decode("utf-8")
            return json.loads(decoded)
        except Exception as exc:
            raise HTTPException(status_code=502, detail=f"فرمت BaseInfo نامعتبر است: {str(exc)}") from exc

    async def _fetch_method(
        self,
        method_name: str,
        company_code: str | None = None,
        service_password: str | None = None,
    ) -> Any:
        resolved_company_code, salt, hashed_value = resolve_itmb_auth(
            company_code=company_code,
            service_password=service_password,
        )
        payload = {
            "CompanyCode": resolved_company_code,
            "Salt": salt,
            "HashedValue": hashed_value,
        }
        endpoint = f"{utcms_config.ITMBOL_SERVICE_URL.rstrip('/')}/{method_name}"
        async with httpx.AsyncClient(timeout=utcms_config.ITMBOL_TIMEOUT_SECONDS) as client:
            response = await client.post(endpoint, json=payload)
            response.raise_for_status()
        encoded_payload = self._extract_result_text(response.text)
        return self._decode_base64_json(encoded_payload)

    async def refresh_all(
        self,
        company_code: str | None = None,
        service_password: str | None = None,
    ) -> dict[str, Any]:
        refreshed: dict[str, Any] = {}
        fetched_at = self._now()
        for cache_key, method_name in self.REFERENCE_METHODS.items():
            data = await self._fetch_method(
                method_name=method_name,
                company_code=company_code,
                service_password=service_password,
            )
            self._cache[cache_key] = BaseInfoCacheEntry(data=data, fetched_at=fetched_at)
            refreshed[cache_key] = self._summarize_data(data)
        return {
            "updated": True,
            "fetched_at": fetched_at,
            "summary": refreshed,
        }

    def status(self) -> dict[str, Any]:
        now = self._now()
        status_map: dict[str, Any] = {}
        for key in self.REFERENCE_METHODS:
            entry = self._cache.get(key)
            if not entry:
                status_map[key] = {"cached": False}
                continue
            status_map[key] = {
                "cached": True,
                "fetched_at": entry.fetched_at,
                "age_seconds": now - entry.fetched_at,
                "is_stale": self._is_stale(entry),
                "summary": self._summarize_data(entry.data),
            }
        return status_map

    @staticmethod
    def _summarize_data(value: Any) -> dict[str, Any]:
        if isinstance(value, list):
            return {"type": "list", "count": len(value)}
        if isinstance(value, dict):
            return {"type": "dict", "count": len(value)}
        return {"type": type(value).__name__}

    async def ensure_fresh(
        self,
        company_code: str | None = None,
        service_password: str | None = None,
    ) -> None:
        need_refresh = any(self._is_stale(self._cache.get(key)) for key in self.REFERENCE_METHODS)
        if need_refresh:
            await self.refresh_all(
                company_code=company_code,
                service_password=service_password,
            )

    async def probe_connection(
        self,
        company_code: str | None = None,
        service_password: str | None = None,
    ) -> dict[str, Any]:
        plate_types = await self._fetch_method(
            method_name=self.REFERENCE_METHODS["plate_types"],
            company_code=company_code,
            service_password=service_password,
        )
        return {
            "ok": True,
            "summary": self._summarize_data(plate_types),
        }

    @staticmethod
    def _collect_codes(records: Any, keys: Iterable[str]) -> set[str]:
        if not isinstance(records, list):
            return set()
        result: set[str] = set()
        for record in records:
            if not isinstance(record, dict):
                continue
            for key in keys:
                value = record.get(key)
                if value is None or value == "":
                    continue
                result.add(str(value).strip())
        return result

    async def validate_bol_references(
        self,
        bol: BOLCnt,
        company_code: str | None = None,
        service_password: str | None = None,
    ) -> dict[str, Any]:
        if not utcms_config.ITMBOL_VALIDATE_BASEINFO:
            return {"validated": False, "reason": "baseinfo_validation_disabled"}

        await self.ensure_fresh(company_code=company_code, service_password=service_password)

        cache_goods = self._cache.get("goods")
        cache_packing_types = self._cache.get("packing_types")
        cache_good_types = self._cache.get("good_types")
        cache_plate_types = self._cache.get("plate_types")
        cache_city_data = self._cache.get("province_cities")

        if (
            cache_goods is None
            or cache_packing_types is None
            or cache_good_types is None
            or cache_plate_types is None
            or cache_city_data is None
        ):
            raise HTTPException(status_code=503, detail="داده‌های BaseInfo کامل نیست")

        goods_ids = self._collect_codes(cache_goods.data, ("GoodID", "ID", "Code"))
        packing_ids = self._collect_codes(cache_packing_types.data, ("PackingTypeID", "ID", "Code"))
        good_type_ids = self._collect_codes(cache_good_types.data, ("GoodtypeID", "ID", "Code"))
        plate_types = self._collect_codes(cache_plate_types.data, ("PlateType", "Code", "PlaqueType"))
        city_codes = self._collect_codes(cache_city_data.data, ("CityCode", "Code"))
        county_codes = self._collect_codes(cache_city_data.data, ("CountieCode", "CountyCode"))

        errors: list[str] = []

        if plate_types and bol.PlaqueType not in plate_types:
            errors.append("PlaqueType در BaseInfo معتبر نیست")

        for index, good in enumerate(bol.Goods, start=1):
            if goods_ids and str(good.GoodID) not in goods_ids:
                errors.append(f"GoodID آیتم {index} معتبر نیست")
            if packing_ids and str(good.PackingTypeID) not in packing_ids:
                errors.append(f"PackingTypeID آیتم {index} معتبر نیست")
            if good_type_ids and str(good.GoodtypeID) not in good_type_ids:
                errors.append(f"GoodtypeID آیتم {index} معتبر نیست")

        city_code_fields = [
            ("SenderCityCode", bol.SenderCityCode),
            ("RecieverCityCode", bol.RecieverCityCode),
            ("LoadingPlaceCityCode", bol.LoadingPlaceCityCode),
            ("OffLoadingPlaceCityCode", bol.OffLoadingPlaceCityCode),
        ]
        for field_name, field_value in city_code_fields:
            if field_value and city_codes and field_value not in city_codes:
                errors.append(f"{field_name} معتبر نیست")

        county_code_fields = [
            ("LoadingPlaceCountieCode", bol.LoadingPlaceCountieCode),
            ("OffLoadingPlaceCountieCode", bol.OffLoadingPlaceCountieCode),
        ]
        for field_name, field_value in county_code_fields:
            if field_value and county_codes and field_value not in county_codes:
                errors.append(f"{field_name} معتبر نیست")

        if errors:
            raise HTTPException(status_code=400, detail={"message": "اعتبارسنجی BaseInfo شکست خورد", "errors": errors})

        return {"validated": True, "errors": []}


itmb_baseinfo_service = ITMBBaseInfoService()

"""Contract-first client for the UTCMS mobile API used by the official APK."""

from __future__ import annotations

import hashlib
import json
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any
from urllib.parse import quote
from zoneinfo import ZoneInfo

import httpx

from app.automation.mobile_payload_adapter import build_mobile_document_payload
from app.core.config import utcms_config


class UtcmsMobileApiError(RuntimeError):
    """A sanitized mobile API failure; response bodies are never logged."""

    def __init__(self, message: str, *, status_code: int | None = None, result_code: Any = None) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.result_code = result_code


@dataclass(slots=True)
class MobileAuthResult:
    token: str
    refresh_token: str | None
    expires_at: str | None
    raw: dict[str, Any] = field(default_factory=dict)


def _as_dict(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, dict) else {}


def _sanitize(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            key: "[REDACTED]"
            if str(key).lower()
            in {
                "password",
                "token",
                "refreshtoken",
                "accesstoken",
                "bearertoken",
                "captoken",
                "captcha",
                "otp",
                "otpcode",
                "cookie",
            }
            else _sanitize(item)
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [_sanitize(item) for item in value]
    return value


def _unwrap_obj(response: dict[str, Any]) -> dict[str, Any]:
    for key in ("obj", "data", "result"):
        value = response.get(key)
        if isinstance(value, dict):
            nested = value.get("obj")
            return _as_dict(nested) if isinstance(nested, dict) else value
    return response


def _iter_dicts(value: Any):
    if isinstance(value, dict):
        yield value
        for nested in value.values():
            yield from _iter_dicts(nested)
    elif isinstance(value, list):
        for nested in value:
            yield from _iter_dicts(nested)


class UtcmsMobileClient:
    """Small, non-retrying API client."""

    def __init__(
        self,
        *,
        base_url: str | None = None,
        token: str | None = None,
        timeout: float | None = None,
        proxy_url: str | None = None,
        http_client: Any | None = None,
        now: Callable[[], datetime] | None = None,
    ) -> None:
        self.base_url = (base_url or utcms_config.UTCMS_MOBILE_API_BASE_URL).rstrip("/")
        self.token = token
        self.timeout = timeout or utcms_config.UTCMS_MOBILE_API_TIMEOUT_SECONDS
        self.proxy_url = proxy_url
        self._http_client = http_client
        self._now = now or (lambda: datetime.now(ZoneInfo("Asia/Tehran")))

    def _headers(self, body: dict[str, Any]) -> dict[str, str]:
        serialized = json.dumps(body, ensure_ascii=False, separators=(",", ":"))
        current = self._now()
        if current.tzinfo is None:
            current = current.replace(tzinfo=ZoneInfo("Asia/Tehran"))
        date = current.astimezone(ZoneInfo("Asia/Tehran")).strftime("%Y%m%d")
        headers = {
            "Content-Type": "application/json",
            "ServicePassword": f"9#$K<31l0?+;{date}0KxsoSx)IFI&",
            "SecurityKey": hashlib.md5(serialized.encode("utf-8")).hexdigest(),
        }
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        return headers

    async def _get(self, path: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        url = f"{self.base_url}/{path.lstrip('/')}"
        client = self._http_client
        owns_client = client is None
        if owns_client:
            client = httpx.AsyncClient(proxy=self.proxy_url, timeout=self.timeout, follow_redirects=False)
        try:
            # For GET requests, SecurityKey is MD5 of empty JSON or params
            serialized = json.dumps(params or {}, ensure_ascii=False, separators=(",", ":"))
            current = self._now()
            if current.tzinfo is None:
                current = current.replace(tzinfo=ZoneInfo("Asia/Tehran"))
            date = current.astimezone(ZoneInfo("Asia/Tehran")).strftime("%Y%m%d")
            headers = {
                "ServicePassword": f"9#$K<31l0?+;{date}0KxsoSx)IFI&",
                "SecurityKey": hashlib.md5(serialized.encode("utf-8")).hexdigest(),
            }
            if self.token:
                headers["Authorization"] = f"Bearer {self.token}"
            try:
                response = await client.get(url, params=params, headers=headers)
            except httpx.HTTPError as exc:
                raise UtcmsMobileApiError("UTCMS mobile API transport failed") from exc
            try:
                decoded = response.json()
            except (TypeError, ValueError) as exc:
                raise UtcmsMobileApiError(
                    "UTCMS mobile API returned non-JSON response",
                    status_code=getattr(response, "status_code", None),
                ) from exc
            if not isinstance(decoded, dict):
                raise UtcmsMobileApiError(
                    "UTCMS mobile API returned an invalid response envelope",
                    status_code=getattr(response, "status_code", None),
                )
            result_code = decoded.get("resultCode")
            status_code = int(getattr(response, "status_code", 0) or 0)
            if status_code < 200 or status_code >= 300 or result_code in {3000, 3001}:
                raise UtcmsMobileApiError(
                    "UTCMS mobile API rejected the request",
                    status_code=status_code,
                    result_code=result_code,
                )
            return decoded
        finally:
            if owns_client:
                await client.aclose()

    async def _post(self, path: str, body: dict[str, Any]) -> dict[str, Any]:
        url = f"{self.base_url}/{path.lstrip('/')}"
        client = self._http_client
        owns_client = client is None
        if owns_client:
            client = httpx.AsyncClient(proxy=self.proxy_url, timeout=self.timeout, follow_redirects=False)
        try:
            # Sign exactly the UTF-8 bytes sent to UTCMS.  Contract-test fakes
            # may only accept ``json=``; real httpx clients use the signed bytes.
            serialized = json.dumps(body, ensure_ascii=False, separators=(",", ":"), allow_nan=False)
            request_kwargs: dict[str, Any] = {"headers": self._headers(body)}
            if owns_client:
                request_kwargs["content"] = serialized.encode("utf-8")
            else:
                request_kwargs["json"] = body
            try:
                response = await client.post(url, **request_kwargs)
            except httpx.HTTPError as exc:
                raise UtcmsMobileApiError("UTCMS mobile API transport failed") from exc
            try:
                decoded = response.json()
            except (TypeError, ValueError) as exc:
                raise UtcmsMobileApiError(
                    "UTCMS mobile API returned non-JSON response",
                    status_code=getattr(response, "status_code", None),
                ) from exc
            if not isinstance(decoded, dict):
                raise UtcmsMobileApiError(
                    "UTCMS mobile API returned an invalid response envelope",
                    status_code=getattr(response, "status_code", None),
                )
            result_code = decoded.get("resultCode")
            status_code = int(getattr(response, "status_code", 0) or 0)
            if status_code < 200 or status_code >= 300 or result_code in {3000, 3001}:
                raise UtcmsMobileApiError(
                    "UTCMS mobile API rejected the request",
                    status_code=status_code,
                    result_code=result_code,
                )
            return decoded
        finally:
            if owns_client:
                await client.aclose()

    async def get_captcha(self, *, form_id: int = 1) -> dict[str, Any]:
        numeric_form_id = 1 if str(form_id).lower() == "login" else int(form_id)
        return await self._post("/Utils/GetCaptcha", {"token": self.token or "", "formId": numeric_form_id})

    @staticmethod
    def _cap_seed(value: str, length: int) -> str:
        """Match the small FNV/xorshift PRNG embedded in the APK widget."""
        state = 2166136261
        mask = 0xFFFFFFFF
        for char in value:
            state ^= ord(char)
            state = (state + (state << 1) + (state << 4) + (state << 7) + (state << 8) + (state << 24)) & mask
        output = ""
        while len(output) < length:
            state ^= (state << 13) & mask
            state ^= state >> 17
            state ^= (state << 5) & mask
            state &= mask
            output += f"{state:08x}"
        return output[:length]

    @classmethod
    def _cap_challenges(cls, challenge: Any, token: str) -> list[tuple[str, str]]:
        if isinstance(challenge, list):
            pairs: list[tuple[str, str]] = []
            for item in challenge:
                if not isinstance(item, (list, tuple)) or len(item) != 2:
                    raise UtcmsMobileApiError("UTCMS CAPTCHA challenge envelope is invalid")
                pairs.append((str(item[0]), str(item[1])))
            return pairs
        if not isinstance(challenge, dict):
            raise UtcmsMobileApiError("UTCMS CAPTCHA challenge envelope is invalid")
        try:
            count = int(challenge["c"])
            salt_length = int(challenge["s"])
            target_length = int(challenge["d"])
        except (KeyError, TypeError, ValueError) as exc:
            raise UtcmsMobileApiError("UTCMS CAPTCHA challenge parameters are invalid") from exc
        if count <= 0 or count > 64 or salt_length <= 0 or target_length <= 0 or target_length % 2:
            raise UtcmsMobileApiError("UTCMS CAPTCHA challenge parameters are invalid")
        return [
            (
                cls._cap_seed(f"{token}{index}", salt_length),
                cls._cap_seed(f"{token}{index}d", target_length),
            )
            for index in range(1, count + 1)
        ]

    @classmethod
    def _solve_cap_pair(cls, salt: str, target: str, *, deadline: float) -> int:
        try:
            target_bytes = bytes.fromhex(target)
        except ValueError as exc:
            raise UtcmsMobileApiError("UTCMS CAPTCHA target is invalid") from exc
        if not target_bytes:
            raise UtcmsMobileApiError("UTCMS CAPTCHA target is empty")
        for nonce in range(utcms_config.UTCMS_CAPTCHA_POW_MAX_NONCE):
            if time.monotonic() > deadline:
                raise UtcmsMobileApiError("UTCMS CAPTCHA proof-of-work timed out")
            digest = hashlib.sha256(f"{salt}{nonce}".encode()).digest()
            if digest[: len(target_bytes)] == target_bytes:
                return nonce
        raise UtcmsMobileApiError("UTCMS CAPTCHA proof-of-work has no solution in configured range")

    async def solve_cap_pow(self) -> str:
        """Solve the CapJS challenge/redeem flow used by the Android APK."""
        endpoint = utcms_config.UTCMS_CAPTCHA_POW_API_ENDPOINT.rstrip("/") + "/"
        client = self._http_client
        owns_client = client is None
        if owns_client:
            client = httpx.AsyncClient(proxy=self.proxy_url, timeout=utcms_config.UTCMS_CAPTCHA_POW_TIMEOUT_SECONDS)
        try:
            try:
                challenge_response = await client.post(f"{endpoint}challenge", headers={"Accept": "application/json"})
                challenge_body = challenge_response.json()
            except (httpx.HTTPError, TypeError, ValueError) as exc:
                raise UtcmsMobileApiError("UTCMS CAPTCHA challenge request failed") from exc
            if not isinstance(challenge_body, dict) or not challenge_body.get("token"):
                raise UtcmsMobileApiError("UTCMS CAPTCHA challenge response is invalid")
            token = str(challenge_body["token"]).strip()
            pairs = self._cap_challenges(challenge_body.get("challenge"), token)
            deadline = time.monotonic() + utcms_config.UTCMS_CAPTCHA_POW_TIMEOUT_SECONDS
            solutions = [self._solve_cap_pair(salt, target, deadline=deadline) for salt, target in pairs]
            redeem_response = await client.post(
                f"{endpoint}redeem",
                json={"token": token, "solutions": solutions},
                headers={"Content-Type": "application/json", "Accept": "application/json"},
            )
            redeem_body = redeem_response.json()
            if not isinstance(redeem_body, dict) or not redeem_body.get("success"):
                raise UtcmsMobileApiError("UTCMS CAPTCHA proof-of-work was rejected")
            solved_token = str(redeem_body.get("token") or "").strip()
            if not solved_token:
                raise UtcmsMobileApiError("UTCMS CAPTCHA redeem returned no token")
            return solved_token
        finally:
            if owns_client:
                await client.aclose()

    async def auto_solve_captcha(self, form_id: int = 1) -> tuple[str, str]:
        """Fetch, decode and solve CAPTCHA via configured provider. Returns (solution_text, cap_token)."""
        if str(form_id).lower() == "login":
            try:
                return "", await self.solve_cap_pow()
            except UtcmsMobileApiError:
                # Older UTCMS tenants may still expose the image contract;
                # retain the existing provider path as an explicit fallback.
                pass
        from app.automation.captcha import get_captcha_provider

        response = await self.get_captcha(form_id=form_id)
        image_base64 = self.extract_captcha_image(response)
        cap_token = self.extract_cap_token(response)

        if not image_base64:
            raise UtcmsMobileApiError("UTCMS mobile get_captcha returned no image data")
        if not cap_token:
            raise UtcmsMobileApiError("UTCMS mobile get_captcha returned no capToken")

        provider = get_captcha_provider()
        if provider is None:
            raise UtcmsMobileApiError("CAPTCHA provider is not configured or disabled")

        result = await provider.solve_text_captcha(image_base64)
        if not result.solved or not result.value:
            raise UtcmsMobileApiError(f"Failed to solve mobile CAPTCHA: {result.error or 'unsolved'}")

        return result.value.strip(), cap_token

    @staticmethod
    def cap_token_from_solution(value: Any) -> str:
        """Return the server proof token from ``auto_solve_captcha`` output."""
        if isinstance(value, (tuple, list)):
            if len(value) > 1 and value[1]:
                return str(value[1]).strip()
            return str(value[0] if value else "").strip()
        return str(value or "").strip()

    async def login(self, national_code: str, password: str, cap_token: str) -> MobileAuthResult:
        body = {"nationalCode": national_code, "password": password, "capToken": cap_token}
        response = await self._post("/Account/UserLoginV2", body)
        res_code = response.get("resultCode")
        res_msg = response.get("resultMessage") or "خطای نامشخص"
        if res_code != 200:
            raise UtcmsMobileApiError(f"UTCMS mobile login failed: {res_msg} (code: {res_code})", result_code=res_code)
        obj = _unwrap_obj(response)
        token = str(obj.get("token") or obj.get("bearerToken") or response.get("token") or "").strip()
        if not token:
            raise UtcmsMobileApiError(f"UTCMS mobile login returned no token: {res_msg}", result_code=res_code)
        self.token = token
        return MobileAuthResult(
            token=token,
            refresh_token=str(obj.get("refreshToken") or "").strip() or None,
            expires_at=str(obj.get("tokenExpireDate") or "").strip() or None,
            raw=_sanitize(response),
        )

    async def refresh(self, refresh_token: str) -> MobileAuthResult:
        encoded = quote(refresh_token, safe="")
        response = await self._post("/Account/GetTokenByRefreshToken", {"refreshToken": encoded})
        obj = _unwrap_obj(response)
        token = str(obj.get("token") or obj.get("bearerToken") or "").strip()
        if not token:
            raise UtcmsMobileApiError("UTCMS mobile refresh returned no token", result_code=response.get("resultCode"))
        self.token = token
        return MobileAuthResult(
            token=token,
            refresh_token=str(obj.get("refreshToken") or "").strip() or refresh_token,
            expires_at=str(obj.get("tokenExpireDate") or "").strip() or None,
            raw=_sanitize(response),
        )

    async def get_document(self, document_id: str) -> dict[str, Any]:
        return await self._post("/Document/GetDocumentByID", {"id": document_id})

    async def get_tracking_code(self, document_id: str) -> dict[str, Any]:
        return await self._post("/Document/GetDocTrackingCode", {"id": document_id})

    async def get_issued_documents(
        self, *, page_number: int = 1, page_size: int = 20, **filters: Any
    ) -> dict[str, Any]:
        body = {
            "nCarTag": filters.get("n_car_tag"),
            "driverNationalCode": filters.get("driver_national_code"),
            "docNo": filters.get("doc_no"),
            "pageNumber": page_number,
            "pageSize": page_size,
        }
        return await self._post("/Document/GetIssuedDocuments", body)

    async def get_shipping_documents(
        self, *, page_number: int = 1, page_size: int = 20, **filters: Any
    ) -> dict[str, Any]:
        body = {
            "nCarTag": filters.get("n_car_tag"),
            "driverNationalCode": filters.get("driver_national_code"),
            "docNo": filters.get("doc_no"),
            "pageNumber": page_number,
            "pageSize": page_size,
        }
        return await self._post("/Document/GetShippingDocuments", body)

    async def insert_document(
        self,
        payload: dict[str, Any],
        *,
        allow_live_submit: bool,
        cap_token: str | None = None,
    ) -> dict[str, Any]:
        if not allow_live_submit:
            raise PermissionError("ALLOW_LIVE_SUBMIT must be explicitly enabled for mobile mutation")
        body = build_mobile_document_payload(payload, token=self.token or "", cap_token=cap_token)
        return await self._post("/Document/InsertDocumentHagigiV3", body)

    async def issue_document_by_otp(self, document_id: str, code: str, *, allow_live_submit: bool) -> dict[str, Any]:
        if not allow_live_submit:
            raise PermissionError("ALLOW_LIVE_SUBMIT must be explicitly enabled for mobile OTP mutation")
        if not code or not code.isdigit() or len(code) not in {5, 6}:
            raise ValueError("کد OTP باید ۵ یا ۶ رقم باشد")
        return await self._post("/Document/IssueDocumentByOtp", {"docId": document_id, "code": code})

    async def resend_otp(self, document_id: str, *, allow_live_submit: bool) -> dict[str, Any]:
        if not allow_live_submit:
            raise PermissionError("ALLOW_LIVE_SUBMIT must be explicitly enabled for mobile OTP mutation")
        return await self._post("/Document/ResendOtpForIssueDocument", {"documentId": document_id})

    async def register_start_of_shipping(
        self,
        document_id: str,
        *,
        speed: Any,
        altitude: Any,
        longitude: Any,
        latitude: Any,
        start_date: str,
        allow_live_submit: bool,
    ) -> dict[str, Any]:
        if not allow_live_submit:
            raise PermissionError("ALLOW_LIVE_SUBMIT must be explicitly enabled for mobile shipping mutation")
        return await self._post(
            "/Document/RegisterStartOfShipping",
            {
                "DocId": document_id,
                "Speed": speed,
                "Altitude": altitude,
                "Longitude": longitude,
                "Latitude": latitude,
                "StartDate": start_date,
                "havePermission": True,
            },
        )

    async def register_end_of_shipping(
        self, document_id: str, gps_list: Any, *, allow_live_submit: bool
    ) -> dict[str, Any]:
        if not allow_live_submit:
            raise PermissionError("ALLOW_LIVE_SUBMIT must be explicitly enabled for mobile shipping mutation")
        return await self._post(
            "/Document/RegisterEndOfShipping",
            {"docId": document_id, "gpsList": gps_list},
        )

    async def start_shipping_with_gps(
        self,
        doc_no: str,
        lat: float,
        lon: float,
        alt: float = 0,
        speed: float = 0,
        allow_live_submit: bool = False,
    ) -> dict[str, Any]:
        """Start shipping with initial GPS point (/Document/StartShippingWithGps)."""
        if not allow_live_submit:
            raise PermissionError("ALLOW_LIVE_SUBMIT must be explicitly enabled for mobile shipping mutation")
        body = {
            "gps": {
                "gPSSpeedField": speed,
                "gPSMaxSpeedField": "0",
                "gPSTotalTraveledDistanceField": "0",
                "latitudeField": lat,
                "longitudeField": lon,
                "altitudeField": alt,
                "bearingField": "0",
                "numberOfSatelliteField": "0",
                "pDOPField": "0",
            },
            "docNo": str(doc_no),
        }
        return await self._post("/Document/StartShippingWithGps", body)

    async def finish_shipping_with_gps(
        self,
        doc_no: str,
        lat: float,
        lon: float,
        alt: float = 0,
        total_distance_km: float = 0,
        speed: float = 0,
        allow_live_submit: bool = False,
    ) -> dict[str, Any]:
        """Finish shipping with terminal GPS point and traveled distance (/Document/FinishShippingWithGps)."""
        if not allow_live_submit:
            raise PermissionError("ALLOW_LIVE_SUBMIT must be explicitly enabled for mobile shipping mutation")
        body = {
            "gps": {
                "gPSSpeedField": speed,
                "gPSMaxSpeedField": "0",
                "gPSTotalTraveledDistanceField": str(total_distance_km),
                "latitudeField": lat,
                "longitudeField": lon,
                "altitudeField": alt,
                "bearingField": "0",
                "numberOfSatelliteField": "0",
                "pDOPField": "0",
            },
            "docNo": str(doc_no),
        }
        return await self._post("/Document/FinishShippingWithGps", body)

    async def get_carrying_doc_id(self) -> dict[str, Any]:
        """Inquire current active carrying document ID (APK wrapper uses GET)."""
        return await self._get("/Document/GetCarryingDocId")

    async def get_carried_document_path(self, document_id: str) -> dict[str, Any]:
        """Fetch historical route path for carried document (APK wrapper uses GET)."""
        return await self._get("/Document/GetCarriedDocumnetPath", {"documentId": str(document_id)})

    async def get_user_fleet_list(self, **kwargs: Any) -> dict[str, Any]:
        """Fetch registered vehicles for user (/Truck/GetUserFleetList)."""
        body: dict[str, Any] = {"token": self.token or ""}
        body.update(kwargs)
        return await self._post("/Truck/GetUserFleetList", body)

    async def get_user_fleet_list_full(self, **kwargs: Any) -> dict[str, Any]:
        """Fetch complete technical details for user fleet (/Truck/GetUserFleetListFull)."""
        body: dict[str, Any] = {"token": self.token or ""}
        body.update(kwargs)
        return await self._post("/Truck/GetUserFleetListFull", body)

    async def get_diesel_quota(
        self,
        year: int | str,
        month: int | str,
        quota_type_id: int | str,
        ir_tag_part1: str,
        ir_tag_part2: str,
        ir_tag_part3: str,
        ir_tag_part4: str,
        cap_token: str | None = None,
        *,
        has_free_zone: bool = False,
        free_zone_code: str | None = None,
        free_zone_no: str | None = None,
        free_zone_digit: str | None = None,
        **extra: Any,
    ) -> dict[str, Any]:
        """Direct diesel quota inquiry via /Utils/GetDieselQuotaV3."""
        body: dict[str, Any] = {
            "year": int(year) if str(year).isdigit() else year,
            "month": int(month) if str(month).isdigit() else month,
            "quotaTypeId": int(quota_type_id) if str(quota_type_id).isdigit() else quota_type_id,
            "hasFreeZone": has_free_zone,
            "irTagPart1": str(ir_tag_part1),
            "irTagPart2": str(ir_tag_part2),
            "irTagPart3": str(ir_tag_part3),
            "irTagPart4": str(ir_tag_part4),
            "freeZoneCode": free_zone_code or "",
            "freeZoneNo": free_zone_no or "",
            "freeZoneDigit": free_zone_digit or "",
        }
        if self.token:
            body["token"] = self.token
        if cap_token:
            body["capToken"] = cap_token
        body.update(extra)
        return await self._post("/Utils/GetDieselQuotaV3", body)

    async def get_gasoline_quota(
        self,
        year: int | str,
        month: int | str,
        national_code: str,
        cap_token: str | None = None,
        **extra: Any,
    ) -> dict[str, Any]:
        """Direct gasoline quota inquiry via /Utils/GetGasolineQuotaV3."""
        body: dict[str, Any] = {
            "year": int(year) if str(year).isdigit() else year,
            "month": int(month) if str(month).isdigit() else month,
            "nationalCode": str(national_code),
        }
        if self.token:
            body["token"] = self.token
        if cap_token:
            body["capToken"] = cap_token
        body.update(extra)
        return await self._post("/Utils/GetGasolineQuotaV3", body)

    @staticmethod
    def extract_captcha_image(response: dict[str, Any]) -> str | None:
        """Extract captcha image base64 string from response envelope."""
        for item in _iter_dicts(response):
            for key in (
                "dntCaptchaImgUrl",
                "captchaImage",
                "imageBase64",
                "image",
                "img",
                "captchaImg",
                "fileContent",
                "captcha",
                "base64",
            ):
                val = item.get(key)
                if isinstance(val, str) and val.strip():
                    raw = val.strip()
                    if "," in raw and ("data:image" in raw or "base64" in raw):
                        return raw.split(",", 1)[-1].strip()
                    return raw
        return None

    @staticmethod
    def extract_cap_token(response: dict[str, Any]) -> str | None:
        """Extract captcha token string from response envelope."""
        for item in _iter_dicts(response):
            for key in ("capToken", "cap_token", "dntCaptchaToken"):
                val = item.get(key)
                if isinstance(val, str) and val.strip():
                    return val.strip()
        for item in _iter_dicts(response):
            for key in ("token", "tokenKey"):
                val = item.get(key)
                if isinstance(val, str) and val.strip():
                    return val.strip()
        return None

    @staticmethod
    def extract_document_id(response: dict[str, Any]) -> str | None:
        obj = _unwrap_obj(response)
        for key in ("docId", "documentId", "id", "DocID"):
            value = obj.get(key)
            if value is not None and str(value).strip():
                return str(value).strip()
        return None

    @staticmethod
    def extract_tracking_code(response: dict[str, Any]) -> str | None:
        obj = _unwrap_obj(response)
        for key in ("trackingCode", "tracking_code", "docTrackingCode", "transportDocTrackingCode"):
            value = obj.get(key)
            if value is not None and str(value).strip():
                return str(value).strip()
        return None

    @staticmethod
    def extract_captcha_type(response: dict[str, Any]) -> Any:
        """Return the server-selected CAPTCHA kind without applying a time heuristic."""
        for item in _iter_dicts(response):
            for key in ("capType", "captchaType", "captcha_type", "UserCaptchaType"):
                if key in item and item[key] not in (None, ""):
                    return item[key]
        return None

    @staticmethod
    def extract_otp_required(response: dict[str, Any]) -> bool | None:
        """Read UTCMS' OTP decision; local clock windows are only predictions."""
        for item in _iter_dicts(response):
            if "isOtpNeeded" in item:
                value = item["isOtpNeeded"]
                if isinstance(value, str):
                    return value.strip().lower() in {"1", "true", "yes"}
                return bool(value)
        return None


__all__ = ["MobileAuthResult", "UtcmsMobileClient", "UtcmsMobileApiError"]

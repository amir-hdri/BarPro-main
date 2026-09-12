import hashlib
import json
from datetime import datetime
from unittest.mock import AsyncMock, patch

import pytest

from app.automation.captcha.base import CaptchaProvider, CaptchaResult
from app.automation.mobile_payload_adapter import build_mobile_document_payload, validate_mobile_source_payload
from app.automation.utcms_mobile_client import UtcmsMobileApiError, UtcmsMobileClient
from app.core.config import utcms_config

TEST_PASSWORD = "TEST_INPUT"


def _payload() -> dict:
    return {
        "sender": {
            "is_company": False,
            "first_name": "علی",
            "last_name": "رضایی",
            "phone": "09121234567",
            "national_code": "0084575948",
            "postal_code": "1111111111",
            "landline": "02112345678",
        },
        "receiver": {
            "is_company": False,
            "first_name": "حسن",
            "last_name": "محمدی",
            "phone": "09129876543",
            "national_code": "0012345679",
            "postal_code": "2222222222",
            "landline": "02612345678",
        },
        "origin": {
            "province": "تهران",
            "city": "تهران",
            "address": "خیابان آزادی",
            "postal_code": "1111111111",
            "lat": 35.7,
            "lon": 51.4,
        },
        "destination": {
            "province": "البرز",
            "city": "کرج",
            "address": "بلوار جمهوری",
            "postal_code": "2222222222",
            "lat": 35.84,
            "lon": 50.94,
        },
        "cargo": {
            "type": "آهن",
            "packaging": "فله",
            "product_id": 17,
            "pack_type_id": 3,
            "weight": 1000,
            "count": 12,
            "description": "شاخه آهن",
            "value": 1000000,
        },
        "vehicle": {
            "driver_national_code": "0084575948",
            "plate": "12ب345ایران11",
            "tag_type": 1,
            "t1": "11",
            "t2": "345",
            "t3": "ب",
            "t4": "12",
            "capacity": 10,
            "type": "کامیون",
        },
        "insurance": {"have_insurance": True, "cover": 1000000},
        "financial": {"cost": 5000000, "bearing_cost": 100000, "pre_rent": 1000000, "post_rent": 4000000},
        "shipping_options": {"send_sms": True, "fuel_type": 1},
    }


def test_mobile_payload_maps_explicit_fields_without_silent_defaults():
    body = build_mobile_document_payload(_payload(), token="token-1", cap_token="issue-cap")

    assert body["token"] == "token-1"
    assert body["load"][0]["productId"] == 17
    assert body["load"][0]["packTypeId"] == 3
    assert body["load"][0]["wheight"] == 1000
    assert body["load"][0]["boxNum"] == 12
    assert body["source"]["cityName"] == "تهران"
    assert body["destination"]["cityName"] == "کرج"
    assert body["source"]["postalCode"] == "1111111111"
    assert body["sender"]["firstName"] == "علی"
    assert body["sender"]["telNumber"] == "02112345678"
    assert body["driverNationalCode"] == "0084575948"
    assert body["rent"] == 5000000
    assert body["sendSMS"] is True
    assert body["insurance"] == {"haveInsurance": True, "insuranceCover": 1000000}

    missing_cost = _payload()
    missing_cost["financial"] = {}
    assert validate_mobile_source_payload(missing_cost)
    with pytest.raises(ValueError, match="کرایه"):
        build_mobile_document_payload(missing_cost, token="token-1")


def test_mobile_payload_rejects_missing_package_count_and_location_postal_code():
    missing_required = _payload()
    missing_required["cargo"] = {"type": "آهن", "packaging": "فله", "product_id": 17, "pack_type_id": 3, "weight": 1000}
    missing_required["origin"].pop("postal_code")

    errors = validate_mobile_source_payload(missing_required)

    assert any("تعداد بسته" in error for error in errors)
    assert any("کدپستی مبدا" in error for error in errors)
    with pytest.raises(ValueError, match="تعداد بسته"):
        build_mobile_document_payload(missing_required, token="token-1")


def test_mobile_payload_maps_multiple_loads_to_apk_field_names():
    payload = _payload()
    payload["cargo"] = {
        "value": 2500000,
        "items": [
            {"product_id": 17, "pack_type_id": 3, "weight": 100, "count": 2, "description": "آهن"},
            {"product_id": 18, "pack_type_id": 4, "weight": 50, "count": 1, "description": "میلگرد"},
        ],
    }

    body = build_mobile_document_payload(payload, token="token-1", cap_token="issue-cap")

    assert body["load"] == [
        {"productId": 17, "wheight": 100, "packTypeId": 3, "description": "آهن", "boxNum": 2},
        {"productId": 18, "wheight": 50, "packTypeId": 4, "description": "میلگرد", "boxNum": 1},
    ]
    assert body["capToken"] == "issue-cap"


def test_non_draft_mobile_insert_requires_second_issue_captcha():
    payload = _payload()

    with pytest.raises(ValueError, match="CAPTCHA صدور"):
        build_mobile_document_payload(payload, token="token-1")

    draft = dict(payload)
    draft["is_draft"] = True
    body = build_mobile_document_payload(draft, token="token-1")
    assert "capToken" not in body


def test_mobile_security_headers_match_json_stringify_digest():
    client = UtcmsMobileClient(base_url="https://example.invalid/API", now=lambda: datetime(2026, 9, 10))
    body = {"nationalCode": "0084575948", "password": TEST_PASSWORD, "capToken": "cap"}

    headers = client._headers(body)
    serialized = json.dumps(body, ensure_ascii=False, separators=(",", ":"))

    assert headers["Content-Type"] == "application/json"
    assert headers["ServicePassword"] == "9#$K<31l0?+;20260910" + "0KxsoSx)IFI&"
    assert headers["SecurityKey"] == hashlib.md5(serialized.encode("utf-8")).hexdigest()


def test_captcha_kind_is_read_from_server_response_without_guessing_time_window():
    response = {"resultCode": 200, "obj": {"capType": 2, "isOtpNeeded": True}}

    assert UtcmsMobileClient.extract_captcha_type(response) == 2
    assert UtcmsMobileClient.extract_otp_required(response) is True


def test_otp_requirement_is_detected_from_nested_result_envelope():
    response = {"result": {"data": {"isOtpNeeded": False}}}

    assert UtcmsMobileClient.extract_otp_required(response) is False


@pytest.mark.asyncio
async def test_insert_is_blocked_without_explicit_live_gate():
    client = UtcmsMobileClient(base_url="https://example.invalid/API")

    with pytest.raises(PermissionError, match="ALLOW_LIVE_SUBMIT"):
        await client.insert_document(_payload(), allow_live_submit=False)


@pytest.mark.asyncio
async def test_insert_passes_second_captcha_only_for_final_document():
    class FakeResponse:
        status_code = 200

        def json(self):
            return {"resultCode": 200, "obj": {"id": "doc-1"}}

    class FakeClient:
        async def post(self, url, **kwargs):
            assert url.endswith("/Document/InsertDocumentHagigiV3")
            assert kwargs["json"]["capToken"] == "issue-cap"
            return FakeResponse()

    client = UtcmsMobileClient(base_url="https://example.invalid/API", token="token-1", http_client=FakeClient())
    await client.insert_document(_payload(), allow_live_submit=True, cap_token="issue-cap")


@pytest.mark.asyncio
async def test_login_and_tracking_use_sanitized_response_shape():
    class FakeResponse:
        status_code = 200
        text = "{}"

        def json(self):
            return {
                "resultCode": 200,
                "obj": {
                "token": "token-1",
                "refreshToken": "refresh-1",
                "tokenExpireDate": "2026-09-10T12:00:00",
                "capToken": "secret-cap",
                },
            }

    class FakeClient:
        async def post(self, url, **kwargs):
            assert url.endswith("/Account/UserLoginV2")
            assert kwargs["json"] == {
                "nationalCode": "0084575948",
                "password": "secret",
                "capToken": "cap",
            }
            return FakeResponse()

    client = UtcmsMobileClient(base_url="https://example.invalid/API", http_client=FakeClient())
    auth = await client.login("0084575948", "secret", "cap")

    assert auth.token == "token-1"
    assert auth.refresh_token == "refresh-1"
    assert auth.raw["resultCode"] == 200
    assert "password" not in json.dumps(auth.raw)
    assert "secret-cap" not in json.dumps(auth.raw)


def test_client_initialization_with_proxy():
    client = UtcmsMobileClient(
        base_url="https://example.invalid/API",
        proxy_url="http://127.0.0.1:3128",
    )
    assert client.proxy_url == "http://127.0.0.1:3128"


@pytest.mark.asyncio
async def test_post_uses_proxy_when_creating_client():
    with patch("httpx.AsyncClient") as mock_client_cls:
        class _ProxyFakeResponse:
            status_code = 200

            def json(self):
                return {"resultCode": 200, "obj": {"success": True}}

        mock_instance = AsyncMock()
        mock_instance.post.return_value = _ProxyFakeResponse()
        mock_client_cls.return_value = mock_instance

        client = UtcmsMobileClient(
            base_url="https://example.invalid/API",
            proxy_url="http://127.0.0.1:3128",
        )
        await client.get_captcha()

        mock_client_cls.assert_called_once_with(
            proxy="http://127.0.0.1:3128",
            timeout=client.timeout,
            follow_redirects=False,
        )


@pytest.mark.asyncio
async def test_auto_solve_captcha_success():
    class FakeCaptchaProvider(CaptchaProvider):
        async def solve_text_captcha(self, image_base64: str) -> CaptchaResult:
            assert image_base64 == "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg=="
            return CaptchaResult(solved=True, value="42", provider="mock")

    class FakeResponseObj:
        status_code = 200

        def json(self):
            return {
                "resultCode": 200,
                "obj": {
                    "capToken": "token-test-123",
                    "imageBase64": "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg==",
                },
            }

    class FakeClient:
        async def post(self, url, **kwargs):
            assert url.endswith("/Utils/GetCaptcha")
            return FakeResponseObj()

    client = UtcmsMobileClient(base_url="https://example.invalid/API", http_client=FakeClient())
    with patch("app.automation.captcha.get_captcha_provider", return_value=FakeCaptchaProvider()):
        solution, token = await client.auto_solve_captcha()
        assert solution == "42"
        assert token == "token-test-123"


@pytest.mark.asyncio
async def test_auto_solve_captcha_error_handling():
    class FakeResp:
        def __init__(self, data):
            self._data = data
            self.status_code = 200

        def json(self):
            return self._data

    class FakeClientEmptyImg:
        async def post(self, url, **kwargs):
            return FakeResp({"resultCode": 200, "obj": {"capToken": "token-123"}})

    client = UtcmsMobileClient(base_url="https://example.invalid/API", http_client=FakeClientEmptyImg())
    with pytest.raises(UtcmsMobileApiError, match="returned no image data"):
        await client.auto_solve_captcha()

    class FakeClientEmptyToken:
        async def post(self, url, **kwargs):
            return FakeResp({"resultCode": 200, "obj": {"imageBase64": "abc"}})

    client2 = UtcmsMobileClient(base_url="https://example.invalid/API", http_client=FakeClientEmptyToken())
    with pytest.raises(UtcmsMobileApiError, match="returned no capToken"):
        await client2.auto_solve_captcha()

    class FakeClientValid:
        async def post(self, url, **kwargs):
            return FakeResp({"resultCode": 200, "obj": {"imageBase64": "abc", "capToken": "tok"}})

    client3 = UtcmsMobileClient(base_url="https://example.invalid/API", http_client=FakeClientValid())
    with patch("app.automation.captcha.get_captcha_provider", return_value=None):
        with pytest.raises(UtcmsMobileApiError, match="provider is not configured"):
            await client3.auto_solve_captcha()


@pytest.mark.asyncio
async def test_cap_pow_matches_apk_challenge_and_redeem_contract():
    token = "challenge-token"
    salt = UtcmsMobileClient._cap_seed(f"{token}1", 8)
    target = hashlib.sha256(f"{salt}0".encode()).hexdigest()[:4]
    calls = []

    class FakeResponse:
        status_code = 200

        def __init__(self, data):
            self.data = data

        def json(self):
            return self.data

    class FakeClient:
        async def post(self, url, **kwargs):
            calls.append((url, kwargs))
            if url.endswith("/challenge"):
                return FakeResponse({"challenge": [[salt, target]], "token": token})
            return FakeResponse({"success": True, "token": "redeemed-token", "expires": "2099-01-01T00:00:00Z"})

    with patch.object(utcms_config, "UTCMS_CAPTCHA_POW_API_ENDPOINT", "https://captcha.example/"), patch.object(
        utcms_config, "UTCMS_CAPTCHA_POW_MAX_NONCE", 10
    ):
        client = UtcmsMobileClient(base_url="https://example.invalid/API", http_client=FakeClient())
        result = await client.solve_cap_pow()

    assert result == "redeemed-token"
    assert calls[0][0] == "https://captcha.example/challenge"
    assert calls[1][0] == "https://captcha.example/redeem"
    assert calls[1][1]["json"] == {"token": token, "solutions": [0]}


@pytest.mark.asyncio
async def test_get_user_fleet_list_and_full():
    calls = []

    class FakeResp:
        status_code = 200

        def json(self):
            return {"resultCode": 200, "obj": [{"plate": "12ب345-11"}]}

    class FakeClient:
        async def post(self, url, **kwargs):
            calls.append((url, kwargs.get("json", {})))
            return FakeResp()

    client = UtcmsMobileClient(base_url="https://example.invalid/API", token="my-token", http_client=FakeClient())
    res1 = await client.get_user_fleet_list(page=1)
    res2 = await client.get_user_fleet_list_full()

    assert res1["resultCode"] == 200
    assert calls[0][0].endswith("/Truck/GetUserFleetList")
    assert calls[0][1] == {"token": "my-token", "page": 1}

    assert res2["resultCode"] == 200
    assert calls[1][0].endswith("/Truck/GetUserFleetListFull")
    assert calls[1][1] == {"token": "my-token"}


@pytest.mark.asyncio
async def test_get_diesel_quota():
    sent_payload = {}

    class FakeResp:
        status_code = 200

        def json(self):
            return {"resultCode": 200, "obj": {"quota": 500}}

    class FakeClient:
        async def post(self, url, **kwargs):
            assert url.endswith("/Utils/GetDieselQuotaV3")
            nonlocal sent_payload
            sent_payload = kwargs.get("json", {})
            return FakeResp()

    client = UtcmsMobileClient(base_url="https://example.invalid/API", token="auth-tok", http_client=FakeClient())
    res = await client.get_diesel_quota(
        year=1403,
        month=6,
        quota_type_id=1,
        ir_tag_part1="12",
        ir_tag_part2="ع",
        ir_tag_part3="345",
        ir_tag_part4="67",
        cap_token="cap-123",
    )

    assert res["resultCode"] == 200
    assert sent_payload["year"] == 1403
    assert sent_payload["month"] == 6
    assert sent_payload["quotaTypeId"] == 1
    assert sent_payload["irTagPart1"] == "12"
    assert sent_payload["irTagPart2"] == "ع"
    assert sent_payload["irTagPart3"] == "345"
    assert sent_payload["irTagPart4"] == "67"
    assert sent_payload["capToken"] == "cap-123"
    assert sent_payload["token"] == "auth-tok"
    assert sent_payload["hasFreeZone"] is False


@pytest.mark.asyncio
async def test_get_gasoline_quota():
    sent_payload = {}

    class FakeResp:
        status_code = 200

        def json(self):
            return {"resultCode": 200, "obj": {"quota": 60}}

    class FakeClient:
        async def post(self, url, **kwargs):
            assert url.endswith("/Utils/GetGasolineQuotaV3")
            nonlocal sent_payload
            sent_payload = kwargs.get("json", {})
            return FakeResp()

    client = UtcmsMobileClient(base_url="https://example.invalid/API", token="auth-tok", http_client=FakeClient())
    res = await client.get_gasoline_quota(
        year=1403,
        month=6,
        national_code="0012345678",
        cap_token="cap-456",
    )

    assert res["resultCode"] == 200
    assert sent_payload["year"] == 1403
    assert sent_payload["month"] == 6
    assert sent_payload["nationalCode"] == "0012345678"
    assert sent_payload["capToken"] == "cap-456"
    assert sent_payload["token"] == "auth-tok"


def test_mobile_payload_matches_deep_analysis_schema_complete():
    payload = _payload()
    body = build_mobile_document_payload(payload, token="tok-1", cap_token="cap-2")

    # Verify root fields
    assert body["token"] == "tok-1"
    assert body["driverNationalCode"] == "0084575948"
    assert body["isDraft"] is False
    assert body["docID"] == 0
    assert body["bearingCost"] == 100000
    assert body["rent"] == 5000000
    assert body["preRent"] == 1000000
    assert body["postRent"] == 4000000
    assert body["fuelType"] == 1
    assert body["sendSMS"] is True
    assert body["value"] == 1000000
    assert body["capToken"] == "cap-2"

    # Verify insurance
    assert body["insurance"]["haveInsurance"] is True
    assert body["insurance"]["insuranceCover"] == 1000000

    # Verify truck
    assert body["truck"]["tagType"] == 1
    assert body["truck"]["t1"] == "11"
    assert body["truck"]["t2"] == "345"
    assert body["truck"]["t3"] == "ب"
    assert body["truck"]["t4"] == "12"
    assert body["truck"]["capacity"] == 10
    assert body["truck"]["type"] == "کامیون"

    # Verify load
    assert len(body["load"]) == 1
    assert body["load"][0]["productId"] == 17
    assert body["load"][0]["wheight"] == 1000
    assert body["load"][0]["packTypeId"] == 3
    assert body["load"][0]["boxNum"] == 12

    # Verify source & destination
    assert body["source"]["province"] == "تهران"
    assert body["source"]["city"] == "تهران"
    assert body["source"]["stateName"] == "تهران"
    assert body["source"]["cityName"] == "تهران"
    assert body["source"]["lat"] == 35.7
    assert body["source"]["lon"] == 51.4
    assert body["source"]["postalCode"] == "1111111111"

    assert body["destination"]["province"] == "البرز"
    assert body["destination"]["city"] == "کرج"
    assert body["destination"]["stateName"] == "البرز"
    assert body["destination"]["cityName"] == "کرج"
    assert body["destination"]["lat"] == 35.84
    assert body["destination"]["lon"] == 50.94
    assert body["destination"]["postalCode"] == "2222222222"

    # Verify sender & receiver
    assert body["sender"]["isCompany"] is False
    assert body["sender"]["firstName"] == "علی"
    assert body["sender"]["lastName"] == "رضایی"
    assert body["sender"]["nationalCode"] == "0084575948"
    assert body["sender"]["mobile"] == "09121234567"
    assert body["sender"]["postalCode"] == "1111111111"
    assert body["sender"]["telNumber"] == "02112345678"

    assert body["receiver"]["isCompany"] is False
    assert body["receiver"]["firstName"] == "حسن"
    assert body["receiver"]["lastName"] == "محمدی"
    assert body["receiver"]["nationalCode"] == "0012345679"
    assert body["receiver"]["mobile"] == "09129876543"
    assert body["receiver"]["postalCode"] == "2222222222"
    assert body["receiver"]["telNumber"] == "02612345678"


def test_plate_parsing_fallback_in_truck():
    payload = _payload()
    payload["vehicle"] = {
        "driver_national_code": "0084575948",
        "plate": "12ع345ایران67",
        "tag_type": 1,
        "capacity": 15,
        "type": "کامیون تک",
        "have_certificate": True,
        "have_3rd_insurance": True,
    }
    body = build_mobile_document_payload(payload, token="tok-1", cap_token="cap-1")
    assert body["truck"]["t1"] == "12"
    assert body["truck"]["t2"] == "ع"
    assert body["truck"]["t3"] == "345"
    assert body["truck"]["t4"] == "67"

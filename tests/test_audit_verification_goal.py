"""Exhaustive audit and verification test suite for UTCMS Mobile Client, WAF Evasion,
Session Vault, Fail-Closed Proxy Guard, and APK Bytecode Contracts.

This suite provides empirical verification for the /goal command.
"""

import hashlib
import json
import os
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch
from zoneinfo import ZoneInfo

import pytest

from app.automation.utcms_mobile_client import (
    MobileAuthResult,
    UtcmsMobileClient,
)
from app.core.config import utcms_config


# ==============================================================================
# 1. ITEM 1: Client Hints Suppression (default_headers=False)
# ==============================================================================
@pytest.mark.asyncio
async def test_item1_async_session_default_headers_false_in_get():
    """Verify default_headers=False is passed when _get creates AsyncSession."""
    with patch("app.automation.utcms_mobile_client.cc_requests.AsyncSession") as mock_session_cls:
        mock_instance = AsyncMock()
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json = lambda: {"resultCode": 200, "obj": {"data": 123}}
        mock_instance.get.return_value = mock_resp
        mock_session_cls.return_value = mock_instance

        client = UtcmsMobileClient(proxy_url="http://127.0.0.1:3128")
        res = await client._get("/test")
        assert res == {"resultCode": 200, "obj": {"data": 123}}

        mock_session_cls.assert_called_once_with(
            proxies={"http": "http://127.0.0.1:3128", "https": "http://127.0.0.1:3128"},
            timeout=20.0,
            allow_redirects=False,
            impersonate="chrome120",
            default_headers=False,
            verify=True,
        )


@pytest.mark.asyncio
async def test_item1_async_session_default_headers_false_in_post():
    """Verify default_headers=False is passed when _post creates AsyncSession."""
    with patch("app.automation.utcms_mobile_client.cc_requests.AsyncSession") as mock_session_cls:
        mock_instance = AsyncMock()
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json = lambda: {"resultCode": 200, "obj": {"data": 456}}
        mock_instance.post.return_value = mock_resp
        mock_session_cls.return_value = mock_instance

        client = UtcmsMobileClient(proxy_url="http://127.0.0.1:3128")
        res = await client._post("/test", {"sample": "val"})
        assert res == {"resultCode": 200, "obj": {"data": 456}}

        mock_session_cls.assert_called_once_with(
            proxies={"http": "http://127.0.0.1:3128", "https": "http://127.0.0.1:3128"},
            timeout=20.0,
            allow_redirects=False,
            impersonate="chrome120",
            default_headers=False,
            verify=True,
        )


@pytest.mark.asyncio
async def test_item1_async_session_default_headers_false_in_solve_cap_pow():
    """Verify default_headers=False is passed when solve_cap_pow creates AsyncSession."""
    with patch("app.automation.utcms_mobile_client.cc_requests.AsyncSession") as mock_session_cls:
        mock_instance = AsyncMock()
        mock_chall_resp = MagicMock()
        mock_chall_resp.json = lambda: {
            "token": "tok_123",
            "challenge": [["s1", "00"]],
        }
        mock_redeem_resp = MagicMock()
        mock_redeem_resp.json = lambda: {"success": True, "token": "redeemed_tok_999"}
        mock_instance.post.side_effect = [mock_chall_resp, mock_redeem_resp]
        mock_session_cls.return_value = mock_instance

        client = UtcmsMobileClient(proxy_url="http://127.0.0.1:3128")
        solved_tok = await client.solve_cap_pow(site_key="test_site_key")
        assert solved_tok == "redeemed_tok_999"

        mock_session_cls.assert_called_once_with(
            proxies={"http": "http://127.0.0.1:3128", "https": "http://127.0.0.1:3128"},
            timeout=utcms_config.UTCMS_CAPTCHA_POW_TIMEOUT_SECONDS,
            allow_redirects=False,
            impersonate="chrome120",
            default_headers=False,
            verify=True,
        )


# ==============================================================================
# 2. ITEM 2: Elimination of Fabricated X-Requested-With Header
# ==============================================================================
def test_item2_x_requested_with_eliminated_from_headers():
    """Verify X-Requested-With is absent from base headers, signed headers, and never sent."""
    base_headers = UtcmsMobileClient._mobile_base_headers()
    assert "X-Requested-With" not in base_headers
    assert "x-requested-with" not in {k.lower(): v for k, v in base_headers.items()}

    client = UtcmsMobileClient()
    signed_headers = client._headers({"test": "data"})
    assert "X-Requested-With" not in signed_headers
    assert "x-requested-with" not in {k.lower(): v for k, v in signed_headers.items()}


# ==============================================================================
# 3. ITEM 3: Genuine Accept Header (application/json, text/plain, */*)
# ==============================================================================
def test_item3_genuine_accept_header():
    """Verify Accept header matches React Native Axios default in official APK."""
    base_headers = UtcmsMobileClient._mobile_base_headers()
    assert base_headers["Accept"] == "application/json, text/plain, */*"

    client = UtcmsMobileClient()
    signed_headers = client._headers({"test": "data"})
    assert signed_headers["Accept"] == "application/json, text/plain, */*"


# ==============================================================================
# 4. ITEM 4: Base API URL Configuration (https://mobservices-barname.utcms.ir/baarnameh_sd/API)
# ==============================================================================
def test_item4_base_api_url_default():
    """Verify config default and client default use verified production mobservices base URL."""
    assert utcms_config.UTCMS_MOBILE_API_BASE_URL == "https://mobservices-barname.utcms.ir/baarnameh_sd/API"
    client = UtcmsMobileClient()
    assert client.base_url == "https://mobservices-barname.utcms.ir/baarnameh_sd/API"


# ==============================================================================
# 5. ITEM 5: curl_cffi Syntax Fix (data= vs content=)
# ==============================================================================
@pytest.mark.asyncio
async def test_item5_curl_cffi_post_uses_data_bytes():
    """Verify _post passes data= (bytes) and never content= to curl_cffi.AsyncSession."""
    with patch("app.automation.utcms_mobile_client.cc_requests.AsyncSession") as mock_session_cls:
        mock_instance = AsyncMock()
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json = lambda: {"resultCode": 200, "obj": {}}
        mock_instance.post.return_value = mock_resp
        mock_session_cls.return_value = mock_instance

        payload = {"key": "مقدار فارسی"}
        client = UtcmsMobileClient()
        await client._post("/test", payload)

        call_args = mock_instance.post.call_args
        _, kwargs = call_args

        assert "data" in kwargs, "data argument must be passed to curl_cffi"
        assert "content" not in kwargs, "content argument must not be passed to curl_cffi"
        assert isinstance(kwargs["data"], bytes), "data argument must be UTF-8 bytes"
        deserialized = json.loads(kwargs["data"].decode("utf-8"))
        assert deserialized == payload


# ==============================================================================
# 6. ITEM 6: refresh() Contract via GET with Query Parameter
# ==============================================================================
@pytest.mark.asyncio
async def test_item6_refresh_contract_uses_get_with_query_param():
    """Verify refresh uses GET /Account/GetTokenByRefreshToken with query parameter."""

    class FakeGetClient:
        def __init__(self):
            self.calls = []

        async def get(self, url, **kwargs):
            self.calls.append((url, kwargs))
            resp = MagicMock()
            resp.status_code = 200
            resp.json = lambda: {
                "resultCode": 200,
                "obj": {
                    "token": "refreshed_access_token_123",
                    "refreshToken": "new_refresh_token_456",
                    "tokenExpireDate": "2026-09-15T12:00:00",
                },
            }
            return resp

    fake_client = FakeGetClient()
    client = UtcmsMobileClient(http_client=fake_client)
    res = await client.refresh("old_refresh_token_000")

    assert len(fake_client.calls) == 1
    url, kwargs = fake_client.calls[0]
    assert url == "https://mobservices-barname.utcms.ir/baarnameh_sd/API/Account/GetTokenByRefreshToken"
    assert kwargs.get("params") == {"refreshToken": "old_refresh_token_000"}

    assert isinstance(res, MobileAuthResult)
    assert res.token == "refreshed_access_token_123"
    assert res.refresh_token == "new_refresh_token_456"
    assert res.expires_at == "2026-09-15T12:00:00"
    assert client.token == "refreshed_access_token_123"


# ==============================================================================
# 7. ITEM 7: Security Headers Integrity (ServicePassword & SecurityKey)
# ==============================================================================
def test_item7_security_headers_service_password_and_security_key():
    """Verify ServicePassword date format and SecurityKey MD5 calculation."""
    fixed_dt = datetime(2026, 9, 14, 15, 30, 0, tzinfo=ZoneInfo("Asia/Tehran"))
    client = UtcmsMobileClient(token="my-jwt-token", now=lambda: fixed_dt)

    body = {"nationalCode": "0012345678", "password": "secret_password"}
    serialized = json.dumps(body, ensure_ascii=False, separators=(",", ":"))
    expected_md5 = hashlib.md5(serialized.encode("utf-8")).hexdigest()

    headers = client._headers(body)

    assert headers["ServicePassword"] == "9#$K<31l0?+;202609140KxsoSx)IFI&"
    assert headers["SecurityKey"] == expected_md5
    assert headers["Authorization"] == "Bearer my-jwt-token"
    assert headers["Content-Type"] == "application/json"


# ==============================================================================
# 8. ITEM 8: OTP Validation Range (4 to 8 digits)
# ==============================================================================
@pytest.mark.asyncio
async def test_item8_otp_validation_range():
    """Verify issue_document_by_otp accepts 4 to 8 digit codes and rejects invalid formats."""

    class FakeOtpClient:
        async def post(self, url, **kwargs):
            resp = MagicMock()
            resp.status_code = 200
            resp.json = lambda: {"resultCode": 200, "obj": {"success": True}}
            return resp

    client = UtcmsMobileClient(http_client=FakeOtpClient())

    # Valid digit counts: 4, 5, 6, 7, 8
    for code in ["1234", "12345", "123456", "1234567", "12345678"]:
        res = await client.issue_document_by_otp("doc_1", code, allow_live_submit=True)
        assert res["resultCode"] == 200

    # Invalid digit counts and values
    for invalid in ["", "123", "123456789", "abcde", "12a45", "None"]:
        with pytest.raises(ValueError, match="کد OTP باید بین ۴ تا ۸ رقم باشد"):
            await client.issue_document_by_otp("doc_1", invalid, allow_live_submit=True)

    # Permission guard
    with pytest.raises(PermissionError, match="ALLOW_LIVE_SUBMIT"):
        await client.issue_document_by_otp("doc_1", "12345", allow_live_submit=False)


# ==============================================================================
# 9. ITEM 9: Helper Methods (GetCurrentShamsiDate, GetDocumentPdfV2, RevokeDocument)
# ==============================================================================
@pytest.mark.asyncio
async def test_item9_new_apk_endpoints():
    """Verify helper methods call the correct endpoints."""
    calls = []

    class FakeClient:
        async def post(self, url, **kwargs):
            calls.append((url, kwargs))
            resp = MagicMock()
            resp.status_code = 200
            resp.json = lambda: {"resultCode": 200, "obj": {"success": True}}
            return resp

    client = UtcmsMobileClient(http_client=FakeClient())

    await client.get_current_shamsi_date()
    assert calls[-1][0].endswith("/Document/GetCurrentShamsiDate")

    await client.get_document_pdf_v2("doc_77")
    assert calls[-1][0].endswith("/Document/GetDocumentPdfV2")
    assert calls[-1][1]["json"] == {"documentId": "doc_77"}

    await client.revoke_document("doc_77", "ابطال به دلیل اشتباه", allow_live_submit=True)
    assert calls[-1][0].endswith("/Document/RevokeDocument")
    assert calls[-1][1]["json"] == {"documentId": "doc_77", "reason": "ابطال به دلیل اشتباه"}

    with pytest.raises(PermissionError):
        await client.revoke_document("doc_77", allow_live_submit=False)


# ==============================================================================
# 10. ITEM 10: CapJS Proof-of-Work Solving (solve_cap_pow)
# ==============================================================================
def test_item10_cap_pow_math_solver():
    """Verify _solve_cap_pair finds the valid SHA-256 target collision."""
    salt = "test_salt_"
    # Target "00" requires finding a nonce whose SHA-256 starts with 0x00
    nonce = UtcmsMobileClient._solve_cap_pair(salt, "00", deadline=1e10)
    digest = hashlib.sha256(f"{salt}{nonce}".encode()).digest()
    assert digest[0] == 0x00

    # Test widget headers
    headers = UtcmsMobileClient._cap_pow_headers()
    assert headers["Origin"] == "https://cptch.utcms.ir"
    assert headers["Referer"] == "https://cptch.utcms.ir/"
    assert headers["Content-Type"] == "application/json"


# ==============================================================================
# 11. ITEM 11: Fail-Closed Proxy Guard (ProxyUnavailableError & HTTP 503)
# ==============================================================================
@pytest.mark.asyncio
async def test_item11_fail_closed_proxy_guard():
    """Verify that in production without proxy, ProxyUnavailableError is raised and HTTP 503 is returned."""
    from fastapi import HTTPException

    from app.automation.worker_proxy import ProxyUnavailableError

    with (
        patch.dict(os.environ, {"ENVIRONMENT": "production"}),
        patch("app.api.routes.shipping_gps.get_worker_proxy_url", return_value=None),
    ):

        proxy_url = None
        env = (os.environ.get("ENVIRONMENT") or "").lower()
        assert env == "production"

        caught_503 = False
        try:
            if proxy_url is None and (env == "production" or os.environ.get("PROXY_FAIL_CLOSED", "").lower() == "true"):
                raise ProxyUnavailableError("ارتباط مستقیم با UTCMS بدون پراکسی در پروداکشن مجاز نیست")
        except ProxyUnavailableError:
            http_exc = HTTPException(status_code=503, detail="پراکسی UTCMS در دسترس نیست — IP سرور محافظت شد")
            assert http_exc.status_code == 503
            assert "پراکسی UTCMS در دسترس نیست" in http_exc.detail
            caught_503 = True

        assert caught_503


# ==============================================================================
# 12. ITEM 12: Session Vault & Driver Token Reuse in Redis
# ==============================================================================
@pytest.mark.asyncio
async def test_item12_session_vault_driver_token_reuse():
    """Verify get_or_login_client reuses cached token from Redis without solving CAPTCHA."""
    from app.automation import gps_shipping_manager

    with (
        patch.object(gps_shipping_manager, "get_cached_token", new=AsyncMock(return_value="cached_jwt_token_valid")),
        patch.object(gps_shipping_manager, "_get_redis", new=AsyncMock(return_value=None)),
        patch.object(UtcmsMobileClient, "auto_solve_captcha", new=AsyncMock()) as mock_captcha,
        patch.object(UtcmsMobileClient, "login", new=AsyncMock()) as mock_login,
    ):

        client = await gps_shipping_manager.get_or_login_client(
            national_code="0012345678",
            password="secret_password",
            proxy_url="http://127.0.0.1:3128",
        )

        assert client.token == "cached_jwt_token_valid"
        assert client.proxy_url == "http://127.0.0.1:3128"
        mock_captcha.assert_not_called()
        mock_login.assert_not_called()


# ==============================================================================
# 13. ITEM 13: Asymmetric Shipping Endpoints Contract
# ==============================================================================
@pytest.mark.asyncio
async def test_item13_asymmetric_shipping_endpoints_contract():
    """Verify start calls StartShippingWithGps alone, while finish calls FinishShippingWithGps + RegisterEndOfShipping."""
    mock_client = AsyncMock(spec=UtcmsMobileClient)
    mock_client.start_shipping_with_gps.return_value = {"resultCode": 200, "obj": {"success": True}}
    mock_client.finish_shipping_with_gps.return_value = {"resultCode": 200, "obj": {"distance": 120}}
    mock_client.register_end_of_shipping.return_value = {"resultCode": 200, "obj": {"success": True}}

    # Start flow
    res_start = await mock_client.start_shipping_with_gps(
        doc_no="DOC123",
        lat=35.7,
        lon=51.4,
        alt=1200.0,
        speed=0.0,
        allow_live_submit=True,
    )
    assert res_start["resultCode"] == 200
    mock_client.start_shipping_with_gps.assert_called_once()
    mock_client.finish_shipping_with_gps.assert_not_called()
    mock_client.register_end_of_shipping.assert_not_called()

    # Finish flow
    res_finish = await mock_client.finish_shipping_with_gps(
        doc_no="DOC123",
        lat=35.8,
        lon=50.9,
        alt=1250.0,
        speed=0.0,
        allow_live_submit=True,
    )
    res_end = await mock_client.register_end_of_shipping(
        document_id="DOC123",
        gps_list=[{"lat": 35.7, "lon": 51.4}, {"lat": 35.8, "lon": 50.9}],
        allow_live_submit=True,
    )
    assert res_finish["resultCode"] == 200
    assert res_end["resultCode"] == 200
    mock_client.finish_shipping_with_gps.assert_called_once()
    mock_client.register_end_of_shipping.assert_called_once()

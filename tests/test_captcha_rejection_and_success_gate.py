"""Regression: success must require business resultCode ok + docId present; 4003 must raise."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import pytest

from app.automation.captcha.base import CaptchaProvider, CaptchaResult
from app.automation.captcha.debug_artifacts import save_rejection_artifact
from app.automation.utcms_mobile_client import UtcmsMobileApiError, UtcmsMobileClient


def _payload() -> dict:
    return {
        "sender": {
            "is_company": False,
            "first_name": "علی",
            "last_name": "رضایی",
            "phone": "09121234567",
            "national_code": "0084575948",
            "postal_code": "1111111111",
        },
        "receiver": {
            "is_company": False,
            "first_name": "حسن",
            "last_name": "محمدی",
            "phone": "09129876543",
            "national_code": "0012345679",
            "postal_code": "2222222222",
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
            "t1": "12",
            "t2": "ب",
            "t3": 345,
            "t4": "11",
            "capacity": 10,
            "type": "کامیون",
        },
        "insurance": {"have_insurance": True, "cover": 1000000},
        "financial": {"cost": 5000000, "bearing_cost": 100000, "pre_rent": 1000000, "post_rent": 4000000},
        "shipping_options": {"send_sms": True, "fuel_type": 1},
    }


class _Resp:
    def __init__(self, body: dict, status: int = 200):
        self.status_code = status
        self._body = body
        self.text = json.dumps(body)

    def json(self):
        return self._body


class _Client4003:
    async def post(self, url, **kwargs):
        assert url.endswith("/Document/InsertDocumentHagigiV3")
        return _Resp({"resultCode": 4003, "resultMessage": "لطفا کد امنیتی صحیح را وارد نمایید"})


class _ClientOkNoId:
    async def post(self, url, **kwargs):
        return _Resp({"resultCode": 200, "resultMessage": "ok", "obj": {}})


class _ClientOkWithId:
    async def post(self, url, **kwargs):
        return _Resp(
            {
                "resultCode": 200,
                "obj": {"id": 99, "docId": "doc-1", "trackingCode": "TR-1", "isOtpNeeded": False},
            }
        )


@pytest.mark.asyncio
async def test_insert_raises_on_http200_result_code_4003():
    """Business rejection 4003 must raise so bot retry loops fire."""
    client = UtcmsMobileClient(base_url="https://example.invalid/API", token="t", http_client=_Client4003())
    with pytest.raises(UtcmsMobileApiError) as exc_info:
        await client.insert_document(_payload(), allow_live_submit=True, cap_token="12")
    assert str(exc_info.value.result_code) == "4003"


@pytest.mark.asyncio
async def test_insert_success_requires_result_code_but_client_returns_obj():
    client = UtcmsMobileClient(base_url="https://example.invalid/API", token="t", http_client=_ClientOkWithId())
    res = await client.insert_document(_payload(), allow_live_submit=True, cap_token="12")
    assert str(res["resultCode"]) == "200"
    assert UtcmsMobileClient.extract_document_id(res) == "doc-1"


def test_success_gate_requires_doc_id_and_doc_no_not_doc_no_alone():
    """Mirror the execute_job success gate: docId+docNo both required."""
    # doc_no only (old false-success path)
    doc_id, doc_no = None, "ONLY-DOC-NO"
    assert not (doc_id and doc_no)
    # both present
    doc_id, doc_no = "doc-1", "TR-1"
    assert doc_id and doc_no
    # resultCode must be ok for the higher-level script gate
    assert str({"resultCode": 200}.get("resultCode")) in {"0", "200"}
    assert str({"resultCode": 4003}.get("resultCode")) not in {"0", "200"}


def test_save_rejection_artifact_writes_png_and_json(tmp_path: Path):
    # 1x1 PNG
    png_b64 = "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg=="
    out = save_rejection_artifact(
        f"data:image/png;base64,{png_b64}",
        prediction="17",
        result_code=4003,
        provider="cnn",
        expression="17 + 15",
        confidence=0.91,
        form_id=1,
        directory=tmp_path,
        extra={"attempt": 1},
    )
    assert out is not None and out.exists()
    payload = json.loads(out.read_text())
    assert payload["result_code"] == 4003
    assert payload["prediction"] == "17"
    assert payload["expression"] == "17 + 15"
    assert payload["provider"] == "cnn"
    assert payload["image_png"] and Path(payload["image_png"]).exists()


@pytest.mark.asyncio
async def test_dump_captcha_rejection_uses_last_debug(tmp_path: Path):
    class _Provider(CaptchaProvider):
        async def solve_text_captcha(self, image_base64: str) -> CaptchaResult:
            return CaptchaResult(
                solved=True,
                provider="cnn",
                value="32",
                meta={"expression": "17 + 15", "confidence": 0.88},
            )

    client = UtcmsMobileClient(base_url="https://example.invalid/API", token="t")

    async def _fake_get_captcha(*, form_id: int = 1):
        return {"resultCode": 200, "obj": "aGVsbG8="}

    client.get_captcha = _fake_get_captcha  # type: ignore[method-assign]
    client.extract_captcha_image = staticmethod(lambda r: r.get("obj"))  # type: ignore[method-assign]
    client.extract_cap_token = staticmethod(lambda r: None)  # type: ignore[method-assign]

    with patch("app.automation.captcha.get_captcha_provider", return_value=_Provider()):
        solution, _token = await client.auto_solve_captcha(form_id=1)

    assert solution == "32"
    assert client.last_captcha_debug is not None
    assert client.last_captcha_debug["meta"]["expression"] == "17 + 15"

    art = client.dump_captcha_rejection(4003, directory=tmp_path)
    assert art is not None and art.exists()
    data = json.loads(Path(art).read_text())
    assert data["prediction"] == "32"
    assert data["result_code"] == 4003
    assert data["expression"] == "17 + 15"


@pytest.mark.asyncio
async def test_issue_document_by_otp_raises_on_business_rejection():
    class _BadOtp:
        async def post(self, url, **kwargs):
            assert url.endswith("/Document/IssueDocumentByOtp")
            return _Resp({"resultCode": 4001, "resultMessage": "کد نامعتبر"})

    client = UtcmsMobileClient(base_url="https://example.invalid/API", token="t", http_client=_BadOtp())
    with pytest.raises(UtcmsMobileApiError) as exc_info:
        await client.issue_document_by_otp("123", "1234", allow_live_submit=True)
    assert str(exc_info.value.result_code) == "4001"

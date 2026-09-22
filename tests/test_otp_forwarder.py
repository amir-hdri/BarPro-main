import pytest

from app.api.routes.otp_forwarder import clean_phone_number, extract_otp_code, normalize_to_english_digits


def test_normalize_digits():
    assert normalize_to_english_digits("۱۲۳۴۵۶۷۸۹۰") == "1234567890"
    assert normalize_to_english_digits("١٢٣٤٥٦٧٨٩٠") == "1234567890"
    assert normalize_to_english_digits("123abc456") == "123abc456"


def test_extract_otp_code_persian_messages():
    # Real UTCMS / Iranian gateway SMS messages
    msg1 = "کد تایید صدور بارنامه شما: ۵۴۳۲۱"
    assert extract_otp_code(msg1) == "54321"

    msg2 = "سامانه بارنامه شهرداری\nکد تایید: 123456\nانقضا: ۲ دقیقه"
    assert extract_otp_code(msg2) == "123456"

    msg3 = "کد ورود شما: 98765"
    assert extract_otp_code(msg3) == "98765"

    msg4 = "رمز یکبار مصرف: ۴۳۲۱۵"
    assert extract_otp_code(msg4) == "43215"

    msg5 = "کد فعالسازی 876543 برای بارنامه شهرداری"
    assert extract_otp_code(msg5) == "876543"

    msg6 = "کد: 65432"
    assert extract_otp_code(msg6) == "65432"

    # Message with year and date
    msg7 = "در تاریخ 1404/06/30 کد تایید شما 33221 می باشد"
    assert extract_otp_code(msg7) == "33221"


def test_clean_phone_number():
    assert clean_phone_number("09123612956") == "09123612956"
    assert clean_phone_number("+989123612956") == "09123612956"
    assert clean_phone_number("۹۸۹۱۲۳۶۱۲۹۵۶") == "09123612956"
    assert clean_phone_number("20007777") == "20007777"


@pytest.mark.asyncio
async def test_submit_manual_otp_stores_redis():
    from unittest.mock import AsyncMock, patch

    from app.api.routes.otp_forwarder import ManualOtpRequest, submit_manual_otp

    mock_redis = AsyncMock()
    with patch("app.core.redis_client.redis_manager.get", new_callable=AsyncMock, return_value=mock_redis):
        req = ManualOtpRequest(code="۵۴۳۲۱", phone="09121234567", job_id="job-test-123")
        res = await submit_manual_otp(req)

    assert res["status"] == "success"
    assert res["code"] == "54321"
    assert res["job_id"] == "job-test-123"
    # Verify set called for rpa:otp:latest and rpa:otp:job:job-test-123
    assert mock_redis.set.await_count >= 2


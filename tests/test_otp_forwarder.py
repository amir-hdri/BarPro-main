import pytest
from app.api.routes.otp_forwarder import extract_otp_code, normalize_to_english_digits, clean_phone_number


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

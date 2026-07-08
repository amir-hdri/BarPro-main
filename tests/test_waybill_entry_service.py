from app.services.waybill_entry_service import (
    clean_text,
    format_plate,
    normalize_digits,
    normalize_float,
    normalize_int,
    normalize_phone,
)


def test_normalize_digits():
    assert normalize_digits("123") == "123"
    assert normalize_digits("۱۲۳") == "123"
    assert normalize_digits("١٢٣") == "123"
    assert normalize_digits("1۲٣") == "123"
    assert normalize_digits("") == ""
    assert normalize_digits(None) == ""
    # Mixed strings
    assert normalize_digits("شماره: ۱۲۳") == "شماره: 123"
    assert normalize_digits("Code ٤٥٦") == "Code 456"
    assert normalize_digits("تست ۱۲۳ test ٤٥٦") == "تست 123 test 456"

    # Pure strings without digits
    assert normalize_digits("abc") == "abc"
    assert normalize_digits("سلام") == "سلام"

    # Special characters and spaces
    assert normalize_digits(" ۱۲۳ - ٤٥٦ ") == " 123 - 456 "

    assert normalize_digits(str(123)) == "123"


def test_normalize_float():
    assert normalize_float("123.45") == 123.45
    assert normalize_float("123,456.78") == 123456.78
    assert normalize_float(123.45) == 123.45
    assert normalize_float(None) == 0.0
    assert normalize_float("abc", default=1.0) == 1.0
    assert normalize_float("") == 0.0


def test_normalize_int():
    assert normalize_int("123") == 123
    assert normalize_int("123,456") == 123456
    assert normalize_int(123) == 123
    assert normalize_int(123.9) == 123
    assert normalize_int(None) == 0
    assert normalize_int("abc", default=5) == 5
    assert normalize_int("") == 0


def test_clean_text():
    assert clean_text("  hello  ") == "hello"
    assert clean_text(None) == ""
    assert clean_text(123) == "123"
    assert clean_text("") == ""


def test_normalize_phone():
    # Standard Iranian mobile
    assert normalize_phone("09123456789") == "+989123456789"
    # With spaces and dashes
    assert normalize_phone("0912-345 6789") == "+989123456789"
    # Persian digits
    assert normalize_phone("۰۹۱۲۳۴۵۶۷۸۹") == "+989123456789"
    # Arabic digits
    assert normalize_phone("٠٩١٢٣٤٥٦٧٨٩") == "+989123456789"
    # Already normalized
    assert normalize_phone("+989123456789") == "+989123456789"
    # No leading zero
    assert normalize_phone("9123456789") == "9123456789"
    # Empty and None
    assert normalize_phone("") == ""
    assert normalize_phone(None) == ""
    # Integer input
    assert normalize_phone(9123456789) == "9123456789"
    # Mixed formatting
    assert normalize_phone(" ۰۹۱۲-۳۴۵ ۶۷۸۹ ") == "+989123456789"


def test_format_plate():
    assert format_plate("12", "A", "345", "67") == "12A34567"
    assert format_plate(12, "ب", 345, 67) == "12ب34567"
    # Padding
    assert format_plate("1", "ج", "2", "3") == "01ج00203"
    # Defaults
    assert format_plate(None, None, None, None) == "00ع00000"
    # Mixed types
    assert format_plate("12", None, 345, "67") == "12ع34567"

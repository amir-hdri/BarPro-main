"""Unit tests for Iranian phone number normalization, operator catalog, and carrier routing."""

from app.core.phone_utils import (
    detect_operator,
    is_known_operator_prefix,
    is_valid_iranian_mobile,
    normalize_iranian_phone,
    resolve_carrier_route,
    resolve_hub_target_carrier,
)


def test_normalize_standard_11_digit():
    assert normalize_iranian_phone("09303653432") == "09303653432"
    assert is_valid_iranian_mobile("09303653432") is True


def test_normalize_international_plus_98():
    assert normalize_iranian_phone("+98 930 365 3432") == "09303653432"
    assert normalize_iranian_phone("+989303653432") == "09303653432"
    # Edge case: +98 with leading 0 (common user input "+98 0930 365 3432")
    assert normalize_iranian_phone("+98 0930 365 3432") == "09303653432"
    assert normalize_iranian_phone("+9809303653432") == "09303653432"
    assert is_valid_iranian_mobile("+98 930 365 3432") is True
    assert is_valid_iranian_mobile("+98 0930 365 3432") is True


def test_normalize_double_zero_98():
    assert normalize_iranian_phone("00989303653432") == "09303653432"
    assert normalize_iranian_phone("0098 930 365 3432") == "09303653432"
    # Edge case: 0098 with leading 0 (e.g. 009809303653432)
    assert normalize_iranian_phone("009809303653432") == "09303653432"
    assert normalize_iranian_phone("0098 0930 365 3432") == "09303653432"


def test_normalize_formatted_spaces_and_hyphens():
    assert normalize_iranian_phone("0930 365 3432") == "09303653432"
    assert normalize_iranian_phone("0930-365-3432") == "09303653432"
    assert normalize_iranian_phone(" 0930-365 3432 ") == "09303653432"


def test_normalize_persian_and_arabic_numerals():
    assert normalize_iranian_phone("۰۹۳۰۳۶۵۳۴۳۲") == "09303653432"
    assert normalize_iranian_phone(" ۰۹۳۰ ۳۶۵ ۳۴۳۲ ") == "09303653432"
    assert normalize_iranian_phone("٠٩٣٠٣٦٥٣٤٣٢") == "09303653432"


def test_normalize_10_digit_without_leading_zero():
    assert normalize_iranian_phone("9303653432") == "09303653432"


def test_invalid_and_empty_phones():
    assert normalize_iranian_phone("") == ""
    assert normalize_iranian_phone(None) == ""
    assert is_valid_iranian_mobile("") is False
    assert is_valid_iranian_mobile(None) is False
    assert is_valid_iranian_mobile("12345") is False
    assert is_valid_iranian_mobile("02188888888") is False  # Landline is not 09


def test_detect_mci_and_hub_routing():
    # Primary MCI prefixes (0910-0919, 0990-0994, 0996, 0997)
    for prefix in [f"091{i}" for i in range(10)] + ["0990", "0991", "0992", "0993", "0994", "0996", "0997"]:
        phone = f"{prefix}1234567"
        op, hub = resolve_carrier_route(phone)
        assert op == "MCI", f"Failed for {phone}"
        assert hub == "MCI", f"Failed hub for {phone}"
        assert detect_operator(phone) == "MCI"
        assert resolve_hub_target_carrier(phone) == "MCI"


def test_detect_irancell_and_hub_routing():
    # Irancell prefixes
    irancell_prefixes = ["0930", "0933", "0935", "0936", "0937", "0938", "0939"] + [
        "0900",
        "0901",
        "0902",
        "0903",
        "0904",
        "0905",
        "0941",
    ]
    for prefix in irancell_prefixes:
        phone = f"{prefix}1234567"
        op, hub = resolve_carrier_route(phone)
        assert op == "IRANCELL", f"Failed for {phone}"
        assert hub == "IRANCELL", f"Failed hub for {phone}"
        assert detect_operator(phone) == "IRANCELL"
        assert resolve_hub_target_carrier(phone) == "IRANCELL"


def test_detect_rightel_routes_to_irancell_hub():
    # RighTel 0920-0923 routes to Hub Irancell SIM per rule
    for prefix in ["0920", "0921", "0922", "0923"]:
        phone = f"{prefix}1234567"
        op, hub = resolve_carrier_route(phone)
        assert op == "RIGHTEL", f"Failed for {phone}"
        assert hub == "IRANCELL", f"Failed hub for {phone}"
        assert detect_operator(phone) == "RIGHTEL"
        assert resolve_hub_target_carrier(phone) == "IRANCELL"


def test_detect_taliya_and_tkc_route_to_mci_hub():
    # Talia 0932 operates on MCI
    assert detect_operator("09321234567") == "TALIYA"
    assert resolve_hub_target_carrier("09321234567") == "MCI"

    # TKC 0934 / 093476 operates on MCI
    assert detect_operator("09341234567") == "TKC"
    assert resolve_hub_target_carrier("09341234567") == "MCI"
    assert detect_operator("09347612345") == "TKC"
    assert resolve_hub_target_carrier("09347612345") == "MCI"


def test_detect_mvnos_and_longest_prefix_match():
    # Shatel Mobile (0998, 09981, 09982) -> IRANCELL hub
    assert detect_operator("09981234567") == "SHATEL"
    assert resolve_hub_target_carrier("09981234567") == "IRANCELL"
    assert detect_operator("09982234567") == "SHATEL"
    assert detect_operator("09980123456") == "SHATEL"

    # LotusTel 09990 (5-digit) vs SamanTel 0999 (4-digit)
    # Longest prefix match must pick LotusTel (length 5) and route to MCI!
    assert detect_operator("09990123456") == "LOTUSTEL"
    assert resolve_hub_target_carrier("09990123456") == "MCI"

    # Aptel 09991 & 09993 (5-digit) vs SamanTel 0999 (4-digit)
    # Longest prefix match must pick Aptel (length 5) and route to MCI!
    assert detect_operator("09991123456") == "APTEL"
    assert resolve_hub_target_carrier("09991123456") == "MCI"
    assert detect_operator("09993123456") == "APTEL"
    assert resolve_hub_target_carrier("09993123456") == "MCI"

    # SamanTel 09999 & 09995 & 0999 -> IRANCELL hub
    assert detect_operator("09999123456") == "SAMANTEL"
    assert resolve_hub_target_carrier("09999123456") == "IRANCELL"
    assert detect_operator("09995123456") == "SAMANTEL"
    assert resolve_hub_target_carrier("09995123456") == "IRANCELL"
    assert detect_operator("09994123456") == "SAMANTEL"
    assert resolve_hub_target_carrier("09994123456") == "IRANCELL"

    # Other MVNOs on Irancell
    assert detect_operator("09992123456") == "FANAP"
    assert resolve_hub_target_carrier("09992123456") == "IRANCELL"

    assert detect_operator("09998123456") == "ARIANTEL"
    assert resolve_hub_target_carrier("09998123456") == "IRANCELL"

    assert detect_operator("09988123456") == "SMARTCOMM"
    assert resolve_hub_target_carrier("09988123456") == "IRANCELL"

    assert detect_operator("09989123456") == "TOSAN"
    assert resolve_hub_target_carrier("09989123456") == "IRANCELL"


def test_unknown_prefix_fallback():
    # Unknown prefix falls back to UNKNOWN and Hub MCI (default road coverage)
    op, hub = resolve_carrier_route("09501234567")
    assert op == "UNKNOWN"
    assert hub == "MCI"
    assert detect_operator("09501234567") == "UNKNOWN"
    assert resolve_hub_target_carrier("09501234567") == "MCI"

    assert detect_operator("12345") == "UNKNOWN"
    assert resolve_hub_target_carrier("12345") == "MCI"


def test_is_known_operator_prefix():
    assert is_known_operator_prefix("09121234567") is True
    assert is_known_operator_prefix("09351234567") is True
    assert is_known_operator_prefix("09211234567") is True
    assert is_known_operator_prefix("09971234567") is True
    assert is_known_operator_prefix("09989123456") is True
    assert is_known_operator_prefix("09501234567") is False
    assert is_known_operator_prefix("12345") is False
    assert is_known_operator_prefix(None) is False

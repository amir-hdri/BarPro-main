"""Iranian mobile phone normalization and carrier detection utilities.

Provides consistent normalization across Arabic/Persian digits, international
prefixes (+98 / 0098), whitespace, hyphens, and standardizes to 09XXXXXXXXX.
Implements complete Iranian operator and MVNO prefix catalog with Longest-Prefix Match (LPM).
"""

from __future__ import annotations

import re
from typing import Final

_PERSIAN_ARABIC_DIGIT_MAP: Final[dict[int, int]] = str.maketrans("۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩", "01234567890123456789")

# Canonical Iranian Operator and MVNO Prefix ranges
# Hamrah-e Aval (MCI) - 17 prefixes per persian-tools + 0997
MCI_PREFIXES: Final[frozenset[str]] = frozenset(
    [f"091{i}" for i in range(10)]  # 0910-0919
    + ["0990", "0991", "0992", "0993", "0994", "0995", "0996", "0997"]  # 0990-0997
)

# MTN Irancell - 14 prefixes per persian-tools
IRANCELL_PREFIXES: Final[frozenset[str]] = frozenset(
    ["0930", "0933", "0935", "0936", "0937", "0938", "0939"]
    + ["0900", "0901", "0902", "0903", "0904", "0905"]
    + ["0941"]
)

# RighTel - 4 prefixes per persian-tools
RIGHTEL_PREFIXES: Final[frozenset[str]] = frozenset(["0920", "0921", "0922", "0923"])

# Talia
TALIYA_PREFIXES: Final[frozenset[str]] = frozenset(["0932"])

# Kish Telecommunication (TKC)
TKC_PREFIXES: Final[frozenset[str]] = frozenset(["0934", "093476"])

# Spadan (MTCE)
SPADAN_PREFIXES: Final[frozenset[str]] = frozenset(["0931"])

# MVNOs
SHATEL_PREFIXES: Final[frozenset[str]] = frozenset(["0998", "09981", "09982"])
SAMANTEL_PREFIXES: Final[frozenset[str]] = frozenset(["0999", "09999", "09995"])
LOTUSTEL_PREFIXES: Final[frozenset[str]] = frozenset(["09990"])
APTEL_PREFIXES: Final[frozenset[str]] = frozenset(["09991", "09993"])
FANAP_PREFIXES: Final[frozenset[str]] = frozenset(["09992"])
ARIANTEL_PREFIXES: Final[frozenset[str]] = frozenset(["09998"])
SMARTCOMM_PREFIXES: Final[frozenset[str]] = frozenset(["09988"])
TOSAN_PREFIXES: Final[frozenset[str]] = frozenset(["09989"])

# Catalog of prefix rules ordered for Longest-Prefix Match (LPM)
# Structure: (operator_code, target_hub_carrier, set_of_prefixes)
OPERATOR_RULES: Final[list[tuple[str, str, frozenset[str]]]] = [
    # 5-digit / specific MVNO prefixes first for longest match priority
    ("LOTUSTEL", "MCI", LOTUSTEL_PREFIXES),
    ("APTEL", "MCI", APTEL_PREFIXES),
    ("SHATEL", "IRANCELL", SHATEL_PREFIXES),
    ("SAMANTEL", "IRANCELL", SAMANTEL_PREFIXES),
    ("FANAP", "IRANCELL", FANAP_PREFIXES),
    ("ARIANTEL", "IRANCELL", ARIANTEL_PREFIXES),
    ("SMARTCOMM", "IRANCELL", SMARTCOMM_PREFIXES),
    ("TOSAN", "IRANCELL", TOSAN_PREFIXES),
    ("TKC", "MCI", TKC_PREFIXES),
    ("TALIYA", "MCI", TALIYA_PREFIXES),
    ("SPADAN", "MCI", SPADAN_PREFIXES),
    # 4-digit primary operators
    ("MCI", "MCI", MCI_PREFIXES),
    ("IRANCELL", "IRANCELL", IRANCELL_PREFIXES),
    ("RIGHTEL", "IRANCELL", RIGHTEL_PREFIXES),
]


def normalize_iranian_phone(raw_phone: str | None) -> str:
    """Normalize raw phone number to canonical 11-digit Iranian mobile format (09XXXXXXXXX).

    Handles:
    - Persian digits: '۰۹۳۰۳۶۵۳۴۳۲' -> '09303653432'
    - Arabic digits: '٠٩٣٠٣٦٥٣٤٣٢' -> '09303653432'
    - International +98: '+98 930 365 3432' -> '09303653432'
    - International 0098: '00989303653432' -> '09303653432'
    - Country code 98: '989303653432' -> '09303653432'
    - 10-digit without leading zero: '9303653432' -> '09303653432'
    - Spaces, hyphens, parentheses, and non-digit separators.
    """
    if not raw_phone:
        return ""

    # Convert Persian/Arabic digits to ASCII
    text = str(raw_phone).translate(_PERSIAN_ARABIC_DIGIT_MAP)

    # Remove all non-digit characters
    digits = re.sub(r"\D", "", text)
    if not digits:
        return ""

    if digits.startswith("0098") and len(digits) >= 14:
        remainder = digits[4:]
        digits = remainder if remainder.startswith("0") else "0" + remainder
    elif digits.startswith("98") and len(digits) >= 12:
        remainder = digits[2:]
        digits = remainder if remainder.startswith("0") else "0" + remainder
    elif not digits.startswith("0") and len(digits) == 10 and digits.startswith("9"):
        digits = "0" + digits

    return digits


def is_valid_iranian_mobile(raw_phone: str | None) -> bool:
    """Check if the normalized number is a valid 11-digit Iranian mobile number."""
    normalized = normalize_iranian_phone(raw_phone)
    return bool(re.fullmatch(r"09\d{9}", normalized))


def is_known_operator_prefix(raw_phone: str | None) -> bool:
    """Check if phone number starts with a recognized Iranian mobile network operator or MVNO prefix."""
    return resolve_carrier_route(raw_phone)[0] != "UNKNOWN"


def resolve_carrier_route(raw_phone: str | None) -> tuple[str, str]:
    """Resolve operator and target Hub SIM carrier ('MCI' or 'IRANCELL') using Longest-Prefix Match (LPM).

    Returns:
        tuple[str, str]: (detected_operator, target_hub_carrier)
        e.g., ("LOTUSTEL", "MCI"), ("SHATEL", "IRANCELL"), ("RIGHTEL", "IRANCELL"), ("UNKNOWN", "MCI")
    """
    normalized = normalize_iranian_phone(raw_phone)
    if len(normalized) < 4:
        return "UNKNOWN", "MCI"

    best_operator = "UNKNOWN"
    best_target_hub = "MCI"  # Default fallback to MCI (Hamrah-e Aval intercity coverage)
    best_length = 0

    for operator, target_hub, prefixes in OPERATOR_RULES:
        for prefix in prefixes:
            if normalized.startswith(prefix) and len(prefix) > best_length:
                best_operator = operator
                best_target_hub = target_hub
                best_length = len(prefix)

    return best_operator, best_target_hub


def detect_operator(raw_phone: str | None) -> str:
    """Detect Iranian mobile network operator name or 'UNKNOWN'."""
    return resolve_carrier_route(raw_phone)[0]


def resolve_hub_target_carrier(raw_phone: str | None) -> str:
    """Determine which Hub SIM ('MCI' or 'IRANCELL') should be targeted for this driver's phone."""
    return resolve_carrier_route(raw_phone)[1]

"""Shared utility functions and constants for UTCMS authentication.

This module provides standalone helper functions used by the authentication
subsystem: URL detection, captcha normalization, error classification,
navigation error formatting, and debug artifact persistence.
"""

import base64
import binascii
import json
import logging
import re
from datetime import UTC, datetime
from pathlib import Path

from app.automation.captcha import captcha_engine
from app.core.config import utcms_config

logger = logging.getLogger(__name__)

CAPTCHA_DIGIT_MAP = str.maketrans("۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩", "01234567890123456789")
CAPTCHA_VALUE_PATTERN = re.compile(r"^-?\d+$")
CAPTCHA_HINT_MARKERS = (
    "captcha",
    "کپچا",
    "کد امنیتی",
    "عبارت امنیتی",
    "حاصل",
    "جمع",
    "منهای",
    "تفریق",
    "ضرب",
    "تقسیم",
    "+",
    "-",
    "*",
    "/",
    "×",
    "÷",
)


def is_login_url(url: str) -> bool:
    lowered = (url or "").lower()
    return any(fragment in lowered for fragment in ("/login", "/account/login", "/signin", "/sign-in"))


def is_authenticated_url(url: str) -> bool:
    lowered = (url or "").lower()
    return any(
        fragment in lowered
        for fragment in ("/notification/notification", "/barname/notification", "/dashboard", "/home/index")
    )


def is_ajax_login_response_url(url: str) -> bool:
    lowered = (url or "").lower()
    return any(
        fragment in lowered
        for fragment in (
            "/account/oldlogin",
            "/barname/account/oldlogin",
            "/account/login",
            "/barname/account/login",
            "/api/account/login",
            "/api/login",
        )
    )


def is_captcha_related_error(text: str | None) -> bool:
    value = (text or "").lower()
    return any(
        marker in value
        for marker in (
            "captcha",
            "کپچا",
            "cap token",
            "verification code",
            "verify code",
            "security code",
            "عبارت امنیتی",
        )
    )


def is_credential_related_error(text: str | None) -> bool:
    value = (text or "").lower()
    return any(
        marker in value
        for marker in (
            "password",
            "username",
            "نام کاربری",
            "رمز عبور",
            "invalid credential",
            "کد ملی",
            "کاربری با این مشخصات",
            "یافت نشد",
        )
    )


def is_plausible_captcha_image(box: dict) -> bool:
    width = float(box.get("width") or 0)
    height = float(box.get("height") or 0)
    if width < 35 or height < 18:
        return False
    if width > 220 or height > 120:
        return False
    aspect_ratio = width / max(height, 1.0)
    return 1.0 <= aspect_ratio <= 5.5


def captcha_image_score(box: dict, input_box: dict | None, selector: str) -> float:
    width = float(box.get("width") or 0)
    height = float(box.get("height") or 0)
    score = 200.0 - abs(width - 110.0) - abs(height - 40.0)
    lowered = selector.lower()
    if "dnt" in lowered:
        score += 20
    if "captcha" in lowered:
        score += 10
    if input_box:
        image_center_x = float(box.get("x") or 0) + (width / 2.0)
        image_center_y = float(box.get("y") or 0) + (height / 2.0)
        input_center_x = float(input_box.get("x") or 0) + (float(input_box.get("width") or 0) / 2.0)
        input_center_y = float(input_box.get("y") or 0) + (float(input_box.get("height") or 0) / 2.0)
        score -= abs(image_center_x - input_center_x) * 0.35
        score -= abs(image_center_y - input_center_y) * 0.6
    return score


def normalize_captcha_solution(value: str | None) -> str | None:
    if value is None:
        return None
    normalized = str(value).strip().translate(CAPTCHA_DIGIT_MAP)
    if not normalized:
        return None
    normalized = normalized.replace(" ", "").replace("=", "").replace("؟", "").replace("?", "")
    if any(
        token in normalized for token in ("+", "-", "*", "/", "x", "X", "×", "÷")
    ) and not CAPTCHA_VALUE_PATTERN.match(normalized):
        decision = captcha_engine.solve_text_with_confidence(normalized)
        min_confidence = get_captcha_math_min_confidence()
        if decision.value and decision.confidence >= min_confidence:
            normalized = str(decision.value).translate(CAPTCHA_DIGIT_MAP).strip()
        else:
            return None
    if not CAPTCHA_VALUE_PATTERN.match(normalized):
        return None
    min_len = max(1, utcms_config.CAPTCHA_VALUE_MIN_LENGTH)
    max_len = max(min_len, utcms_config.CAPTCHA_VALUE_MAX_LENGTH)
    if not (min_len <= len(normalized) <= max_len):
        return None
    return normalized


def get_captcha_math_min_confidence() -> float:
    return max(0.0, min(1.0, min(float(utcms_config.CAPTCHA_MATH_MIN_CONFIDENCE), 0.55)))


def get_captcha_mode() -> str:
    mode = (utcms_config.CAPTCHA_MODE or "").strip().lower()
    if mode in ("provider_first", "manual_only", "provider_only", "local_only"):
        return mode
    return "local_only"


def get_captcha_strategy_order(mode: str, local_fallback_enabled: bool = True) -> tuple[str, ...]:
    """Return the canonical automatic solver order for every supported mode."""
    normalized = (mode or "").strip().lower()
    if normalized == "provider_only":
        return ("provider",)
    if normalized == "provider_first":
        return ("provider", "math") if local_fallback_enabled else ("provider",)
    if normalized == "manual_only":
        return ()
    return ("math", "provider")


def navigation_error_message(url: str, error: Exception) -> str:
    raw = str(error or "").strip()
    lowered = raw.lower()
    host_hint = url.strip() or "UTCMS"
    if any(
        marker in lowered
        for marker in (
            "err_name_not_resolved",
            "name_not_resolved",
            "dns",
            "could not resolve host",
            "nodename nor servname provided",
        )
    ):
        return (
            f"دسترسی به صفحه ورود UTCMS ممکن نشد؛ دامنه/شبکه برای {host_hint} resolve نشد " "(ERR_NAME_NOT_RESOLVED)."
        )
    if "timeout" in lowered or "timed out" in lowered:
        return f"دسترسی به صفحه ورود UTCMS ممکن نشد؛ پاسخ از {host_hint} در زمان مجاز دریافت نشد."
    if raw:
        return f"دسترسی به صفحه ورود UTCMS ممکن نشد ({host_hint}): {raw}"
    return f"دسترسی به صفحه ورود UTCMS ممکن نشد ({host_hint})."


def navigation_failures_message(failures: list[tuple[str, Exception]]) -> str:
    if not failures:
        return "دسترسی به صفحه ورود UTCMS ممکن نشد."
    first_url, _ = failures[0]
    last_url, last_error = failures[-1]
    message = navigation_error_message(last_url, last_error)
    if first_url and first_url != last_url:
        message = f"{message} تلاش روی URL اصلی نیز ناموفق بود: {first_url}"
    return message


def hint_candidates_from_text(raw_text: str | None) -> list[str]:
    text = (raw_text or "").strip()
    if not text:
        return []
    candidates: list[str] = []
    full_text = " ".join(text.split())
    if full_text:
        candidates.append(full_text)
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    for line in lines:
        lower_line = line.lower()
        if any(marker in lower_line for marker in CAPTCHA_HINT_MARKERS):
            candidates.append(line)
    for fragment in re.findall(r"[^\n]{0,40}[+\-*/×÷][^\n]{0,40}", text):
        cleaned = " ".join(fragment.split())
        if cleaned:
            candidates.append(cleaned)
    unique: list[str] = []
    seen = set()
    for item in candidates:
        normalized = item.lower()
        if normalized in seen:
            continue
        seen.add(normalized)
        unique.append(item)
    return unique


def save_captcha_debug_artifact(
    page_url: str,
    image_base64: str,
    phase: str,
    attempt: int | None,
    stage: str,
    provider: str | None = None,
    solution: str | None = None,
    error: str | None = None,
) -> None:
    if not utcms_config.CAPTCHA_DEBUG_SAVE_IMAGES or not image_base64:
        return
    try:
        image_bytes = base64.b64decode(image_base64, validate=True)
    except (ValueError, binascii.Error):
        return
    timestamp = datetime.now(UTC).replace(tzinfo=None).strftime("%Y%m%d-%H%M%S-%f")
    safe_phase = re.sub(r"[^a-zA-Z0-9_-]+", "_", phase or "login")
    safe_stage = re.sub(r"[^a-zA-Z0-9_-]+", "_", stage or "capture")
    debug_dir = Path(utcms_config.CAPTCHA_DEBUG_DIR)
    debug_dir.mkdir(parents=True, exist_ok=True)
    base_name = f"{timestamp}-{safe_phase}-a{attempt or 0}-{safe_stage}"
    image_path = debug_dir / f"{base_name}.png"
    meta_path = debug_dir / f"{base_name}.json"
    image_path.write_bytes(image_bytes)
    meta_path.write_text(
        json.dumps(
            {
                "saved_at": datetime.now(UTC).replace(tzinfo=None).isoformat() + "Z",
                "phase": phase,
                "attempt": attempt,
                "stage": stage,
                "provider": provider,
                "solution_recorded": bool(solution),
                "error": error,
                "url": page_url,
                "image_path": str(image_path),
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    logger.info(
        "captcha_debug_saved",
        extra={
            "extra_fields": {
                "image_path": str(image_path),
                "meta_path": str(meta_path),
                "phase": phase,
                "attempt": attempt,
                "stage": stage,
            }
        },
    )

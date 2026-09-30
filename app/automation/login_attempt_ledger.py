"""Per-account UTCMS login attempt ledger + cooldown.

Live incident (2026-09-30): repeated *failed* logins against one driver
account (ad-hoc checks with misread CAPTCHAs, job retries, keepalive
re-auth) pushed the account into a UTCMS-side lockout
(``resultCode=1 خطا در سامانه``) while a sibling account on the same egress
still returned ``resultCode=200``. Nothing capped per-account attempts.

Rules:
- Only authoritative portal verdicts (a rejected login POST) burn an
  attempt. Transport/infra blips belong to the egress layer (see
  ``worker_proxy`` / P0-2) and never touch the ledger.
- At ``LOGIN_FAILURE_THRESHOLD`` burned attempts inside
  ``LOGIN_FAILURE_WINDOW_SECONDS``, further logins are refused *locally*
  (zero UTCMS traffic) until ``LOGIN_COOLDOWN_SECONDS`` expires.
- A successful login clears the ledger; a Redis outage fails open so a
  cache problem can never lock every account.
"""

from __future__ import annotations

import logging
from typing import Any

from app.core.config import utcms_config
from app.core.exceptions import UTCMSException

logger = logging.getLogger(__name__)

FAILURES_KEY = "utcms:login:failures:{identity}"
COOLDOWN_KEY = "utcms:login:cooldown:{identity}"

_DIGIT_MAP = str.maketrans("۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩", "01234567890123456789")


class AccountCooldownError(UTCMSException):
    """A login was refused locally because the account is cooling down.

    Worded for the text-based taxonomy: contains ``login`` (→ AUTH_FAILURE)
    and ``cooldown`` (operator-visible reason); avoids ``captcha``,
    ``timeout``, ``proxy`` and other routing keywords. Retryable so the
    worker backs off with delay instead of burning UTCMS attempts.
    """

    def __init__(self, identity: str, reason: str):
        super().__init__(
            f"UTCMS login cooldown active for account {identity}: {reason}. "
            "Skipping the login attempt to avoid an account lockout.",
            retryable=True,
        )
        self.identity = identity


def normalize_identity(identity: Any) -> str:
    """Normalize an account identifier (national code / username)."""
    return str(identity or "").translate(_DIGIT_MAP).strip()


async def _get_redis():
    """Best-effort Redis accessor; None when Redis is unavailable."""
    try:
        from app.core.redis import redis_manager

        return await redis_manager.get()
    except Exception:
        return None


def _thresholds() -> tuple[int, int, int]:
    """Return (window_seconds, threshold, cooldown_seconds) from config."""
    window = int(getattr(utcms_config, "LOGIN_FAILURE_WINDOW_SECONDS", 3600))
    threshold = int(getattr(utcms_config, "LOGIN_FAILURE_THRESHOLD", 5))
    cooldown = int(getattr(utcms_config, "LOGIN_COOLDOWN_SECONDS", 7200))
    return window, threshold, cooldown


async def check_login_allowed(identity: Any) -> tuple[bool, str | None]:
    """Return (allowed, reason). Refused only while a cooldown key exists."""
    ident = normalize_identity(identity)
    if not ident:
        return False, "empty account identity"
    try:
        redis = await _get_redis()
        if redis is None:
            return True, None
        if await redis.get(COOLDOWN_KEY.format(identity=ident)):
            return False, "login cooldown active (account protected after repeated failures)"
    except Exception as exc:
        logger.debug("login_ledger_check_unavailable; allowing: %s", exc)
        return True, None
    return True, None


async def record_login_failure(identity: Any, kind: str = "auth") -> None:
    """Record one burned login attempt; arm the cooldown at threshold."""
    ident = normalize_identity(identity)
    if not ident:
        return
    window, threshold, cooldown = _thresholds()
    try:
        redis = await _get_redis()
        if redis is None:
            return
        key = FAILURES_KEY.format(identity=ident)
        count = await redis.incr(key)
        await redis.expire(key, window)
        if count >= threshold:
            await redis.set(COOLDOWN_KEY.format(identity=ident), "1", ex=cooldown, nx=True)
            logger.warning(
                "login_account_cooldown_activated",
                extra={"extra_fields": {"identity": ident, "kind": kind, "failures": count, "cooldown": cooldown}},
            )
    except Exception as exc:
        logger.debug("login_ledger_record_unavailable: %s", exc)


async def record_login_success(identity: Any) -> None:
    """Clear the ledger: a success proves the account is healthy."""
    ident = normalize_identity(identity)
    if not ident:
        return
    try:
        redis = await _get_redis()
        if redis is None:
            return
        await redis.delete(FAILURES_KEY.format(identity=ident), COOLDOWN_KEY.format(identity=ident))
    except Exception as exc:
        logger.debug("login_ledger_clear_unavailable: %s", exc)

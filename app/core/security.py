import hmac
from typing import Any

import jwt
from fastapi import HTTPException, Request
from jwt.exceptions import PyJWTError as JWTError

from app.core.config import utcms_config


def _extract_bearer_token(authorization: str | None) -> str | None:
    if not authorization:
        return None
    parts = authorization.strip().split(" ", 1)
    if len(parts) != 2:
        return None
    scheme, token = parts
    if scheme.lower() != "bearer":
        return None
    token = token.strip()
    return token or None


def _is_api_key_valid(api_key: str | None) -> bool:
    configured = utcms_config.API_KEY.strip()
    if not configured:
        return False
    if not api_key:
        return False
    return hmac.compare_digest(api_key.strip(), configured)


def _is_jwt_valid(token: str | None) -> dict[str, Any] | None:
    """Validate JWT token and return decoded payload if valid, otherwise None."""
    if not token:
        return None
    secret = utcms_config.JWT_SECRET.strip()
    if not secret:
        return None

    kwargs = {
        "algorithms": [utcms_config.JWT_ALGORITHM],
        "leeway": utcms_config.JWT_LEEWAY_SECONDS,
    }
    if utcms_config.JWT_AUDIENCE:
        kwargs["audience"] = utcms_config.JWT_AUDIENCE
    if utcms_config.JWT_ISSUER:
        kwargs["issuer"] = utcms_config.JWT_ISSUER

    try:
        decoded: dict[str, Any] = jwt.decode(token, secret, **kwargs)
        return decoded
    except JWTError:
        return None


def _has_admin_role(decoded: dict[str, Any] | None) -> bool:
    """Check if decoded JWT contains master_admin role."""
    if not decoded:
        return False
    role = decoded.get("role") or decoded.get("type")
    return role == "master_admin"


def _ensure_auth_config(mode: str) -> None:
    if mode == "api_key" and not utcms_config.API_KEY.strip():
        raise HTTPException(
            status_code=503,
            detail="پیکربندی امنیتی ناقص است: API_KEY تنظیم نشده است",
        )
    if mode == "jwt" and not utcms_config.JWT_SECRET.strip():
        raise HTTPException(
            status_code=503,
            detail="پیکربندی امنیتی ناقص است: JWT_SECRET تنظیم نشده است",
        )
    if mode == "api_key_and_jwt":
        if not utcms_config.API_KEY.strip():
            raise HTTPException(
                status_code=503,
                detail="پیکربندی امنیتی ناقص است: API_KEY تنظیم نشده است",
            )
        if not utcms_config.JWT_SECRET.strip():
            raise HTTPException(
                status_code=503,
                detail="پیکربندی امنیتی ناقص است: JWT_SECRET تنظیم نشده است",
            )
    if mode == "api_key_or_jwt":
        if not utcms_config.API_KEY.strip() and not utcms_config.JWT_SECRET.strip():
            raise HTTPException(
                status_code=503,
                detail="پیکربندی امنیتی ناقص است: حداقل یکی از API_KEY یا JWT_SECRET باید تنظیم شده باشد",
            )


async def _reject_revoked_jwt(decoded: dict[str, Any] | None) -> None:
    """Raise 401 when the JWT has been revoked via the logout blacklist (H5 fix).

    Without this check, a token blacklisted at logout remained fully valid on
    every sensitive endpoint until its natural expiry — while the client-facing
    dependencies (auth_multitenant) DID enforce the blacklist, so revocation was
    only half-enforced. Tokens without a ``jti`` (issued before the feature)
    are skipped and expire naturally within their short window, mirroring
    ``auth_multitenant._check_token_blacklist``.
    """
    if not decoded:
        return
    jti = decoded.get("jti")
    if not jti:
        return
    from app.core.token_blacklist import is_blacklisted

    if await is_blacklisted(jti):
        raise HTTPException(
            status_code=401,
            detail="Token has been revoked",
            headers={"WWW-Authenticate": "Bearer"},
        )


async def require_sensitive_auth(request: Request) -> None:
    """Protect sensitive endpoints with API Key / JWT.

    Validates that JWT has a valid role (client or master_admin) when JWT is used.
    """
    mode = utcms_config.API_AUTH_MODE.strip().lower()

    if mode in ("off", "none", "disabled"):
        return

    if mode not in ("api_key", "jwt", "api_key_or_jwt", "api_key_and_jwt"):
        raise HTTPException(status_code=500, detail="مقدار API_AUTH_MODE نامعتبر است")

    _ensure_auth_config(mode)

    api_key = request.headers.get(utcms_config.API_KEY_HEADER)
    token = _extract_bearer_token(request.headers.get("Authorization")) or request.cookies.get(
        utcms_config.AUTH_COOKIE_NAME
    )

    has_api_key = _is_api_key_valid(api_key)
    decoded_jwt = _is_jwt_valid(token)

    authorized = False
    if mode == "api_key":
        authorized = has_api_key
    elif mode == "jwt":
        authorized = decoded_jwt is not None
    elif mode == "api_key_or_jwt":
        authorized = has_api_key or decoded_jwt is not None
    elif mode == "api_key_and_jwt":
        authorized = has_api_key and decoded_jwt is not None

    if not authorized:
        raise HTTPException(
            status_code=401,
            detail="دسترسی به endpoint حساس مجاز نیست (API Key/JWT نامتبر یا غایب)",
        )

    # H5: reject blacklisted (logged-out) JWTs before role validation
    await _reject_revoked_jwt(decoded_jwt)

    # If JWT is used, validate it has a valid role
    if decoded_jwt:
        role = decoded_jwt.get("role") or decoded_jwt.get("type")
        if role not in ("client", "master_admin"):
            raise HTTPException(
                status_code=403,
                detail="دسترسی مجاز نیست: نقش کاربر معتبر نیست",
            )


async def require_sensitive_admin(request: Request) -> None:
    """Protect admin-only sensitive endpoints with API Key / admin-role JWT."""
    mode = utcms_config.API_AUTH_MODE.strip().lower()

    if mode in ("off", "none", "disabled"):
        return

    if mode not in ("api_key", "jwt", "api_key_or_jwt", "api_key_and_jwt"):
        raise HTTPException(status_code=500, detail="مقدار API_AUTH_MODE نامعتبر است")

    _ensure_auth_config(mode)

    api_key = request.headers.get(utcms_config.API_KEY_HEADER)
    token = _extract_bearer_token(request.headers.get("Authorization"))
    if not token:
        token = request.cookies.get(utcms_config.AUTH_COOKIE_NAME)

    has_api_key = _is_api_key_valid(api_key)
    decoded = _is_jwt_valid(token)
    has_admin_jwt = _has_admin_role(decoded)

    authorized = False
    if mode == "api_key":
        authorized = has_api_key
    elif mode == "jwt":
        authorized = has_admin_jwt
    elif mode == "api_key_or_jwt":
        authorized = has_api_key or has_admin_jwt
    elif mode == "api_key_and_jwt":
        authorized = has_api_key and has_admin_jwt

    if not authorized:
        raise HTTPException(
            status_code=401,
            detail="دسترسی به endpoint مدیریتی حساس مجاز نیست (نقش administator یا API Key معتبر لازم است)",
        )

    # H5: reject blacklisted (logged-out) JWTs
    await _reject_revoked_jwt(decoded)

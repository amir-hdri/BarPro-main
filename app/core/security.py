import hmac

from fastapi import HTTPException, Request
from jose import JWTError, jwt

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


def _is_jwt_valid(token: str | None) -> bool:
    if not token:
        return False
    secret = utcms_config.JWT_SECRET.strip()
    if not secret:
        return False

    kwargs = {
        "algorithms": ["HS256"],
        "leeway": utcms_config.JWT_LEEWAY_SECONDS,
    }
    if utcms_config.JWT_AUDIENCE:
        kwargs["audience"] = utcms_config.JWT_AUDIENCE
    if utcms_config.JWT_ISSUER:
        kwargs["issuer"] = utcms_config.JWT_ISSUER

    try:
        jwt.decode(token, secret, **kwargs)
        return True
    except JWTError:
        return False


def _ensure_auth_config(mode: str) -> None:
    requires_api_key = mode in ("api_key", "api_key_or_jwt", "api_key_and_jwt")
    requires_jwt = mode in ("jwt", "api_key_or_jwt", "api_key_and_jwt")

    if requires_api_key and not utcms_config.API_KEY.strip():
        raise HTTPException(
            status_code=503,
            detail="پیکربندی امنیتی ناقص است: API_KEY تنظیم نشده است",
        )
    if requires_jwt and not utcms_config.JWT_SECRET.strip() and mode in ("jwt", "api_key_and_jwt"):
        raise HTTPException(
            status_code=503,
            detail="پیکربندی امنیتی ناقص است: JWT_SECRET تنظیم نشده است",
        )


async def require_sensitive_auth(request: Request) -> None:
    """Protect sensitive endpoints with API Key / JWT."""
    mode = utcms_config.API_AUTH_MODE.strip().lower()

    if mode in ("off", "none", "disabled"):
        return

    if mode not in ("api_key", "jwt", "api_key_or_jwt", "api_key_and_jwt"):
        raise HTTPException(status_code=500, detail="مقدار API_AUTH_MODE نامعتبر است")

    _ensure_auth_config(mode)

    api_key = request.headers.get(utcms_config.API_KEY_HEADER)
    token = _extract_bearer_token(request.headers.get("Authorization"))
    if not token:
        token = request.cookies.get("utcms_auth_token")

    has_api_key = _is_api_key_valid(api_key)
    has_jwt = _is_jwt_valid(token)

    authorized = False
    if mode == "api_key":
        authorized = has_api_key
    elif mode == "jwt":
        authorized = has_jwt
    elif mode == "api_key_or_jwt":
        authorized = has_api_key or has_jwt
    elif mode == "api_key_and_jwt":
        authorized = has_api_key and has_jwt

    if not authorized:
        raise HTTPException(
            status_code=401,
            detail="دسترسی به endpoint حساس مجاز نیست (API Key/JWT نامعتبر یا غایب)",
        )

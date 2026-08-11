"""
Multi-tenant authentication and authorization system.

Provides JWT-based authentication for clients with tenant isolation enforcement.
Each client can only access their own drivers and waybill tasks.
"""

import asyncio
import logging
import secrets
import uuid
from datetime import UTC, datetime, timedelta

import bcrypt
import jwt
from cryptography.fernet import Fernet
from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jwt.exceptions import PyJWTError as JWTError
from pydantic import BaseModel
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.core.config import utcms_config
from app.core.database import get_session
from app.core.token_blacklist import is_blacklisted
from app.models_multitenant import Client, ClientStatus

logger = logging.getLogger(__name__)


class DriverPasswordDecryptError(Exception):
    """Raised when a driver's encrypted UTCMS password cannot be decrypted.

    The most common cause is a DRIVER_ENCRYPTION_KEY mismatch: the password was
    encrypted with a different key than the one currently configured. The
    original plaintext is unrecoverable, so the driver's password must be
    re-saved (via the UI/API) or re-encrypted with the original key.
    """


# Security scheme
security = HTTPBearer(auto_error=False)


class TokenPayload(BaseModel):
    """JWT token payload structure."""

    sub: int  # client_id
    client_code: str
    email: str
    role: str = "client"
    exp: datetime
    iat: datetime


class TokenResponse(BaseModel):
    """Token response model."""

    access_token: str
    token_type: str = "bearer"
    expires_in: int
    client_id: int
    client_code: str
    client_name: str


async def hash_password(password: str) -> str:
    """Hash a password using bcrypt (off the event loop)."""
    salt = bcrypt.gensalt()
    hashed = await asyncio.to_thread(bcrypt.hashpw, password.encode("utf-8"), salt)
    return hashed.decode("utf-8")


async def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verify a password against its hash (off the event loop)."""
    try:
        return await asyncio.to_thread(
            bcrypt.checkpw,
            plain_password.encode("utf-8"),
            hashed_password.encode("utf-8"),
        )
    except Exception as e:
        logger.error("password_verification_error", extra={"extra_fields": {"error_type": type(e).__name__}})
        return False


def _build_fernet() -> "Fernet":
    from base64 import urlsafe_b64decode, urlsafe_b64encode

    from cryptography.fernet import Fernet
    from cryptography.hazmat.primitives import hashes
    from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC

    raw_key = utcms_config.DRIVER_ENCRYPTION_KEY.encode("utf-8")
    try:
        decoded = urlsafe_b64decode(raw_key)
        if len(decoded) == 32:
            return Fernet(raw_key.decode())
    except Exception:
        logger.warning("fernet_decode_failed_using_pbkdf2", exc_info=True)
    kdf = PBKDF2HMAC(algorithm=hashes.SHA256(), length=32, salt=b"barpro-fernet-kdf", iterations=600000)
    derived = urlsafe_b64encode(kdf.derive(raw_key))
    return Fernet(derived.decode())


_fernet_instance: "Fernet | None" = None


def _get_fernet() -> "Fernet":
    global _fernet_instance
    if _fernet_instance is None:
        _fernet_instance = _build_fernet()
    return _fernet_instance


def encrypt_driver_password(plain_password: str) -> str:
    """Encrypt driver's UTCMS password for storage using Fernet."""
    return _get_fernet().encrypt(plain_password.encode("utf-8")).decode("utf-8")


def decrypt_driver_password(encrypted_password: str) -> str:
    """Decrypt driver's UTCMS password.

    Raises DriverPasswordDecryptError (with an actionable message) when the
    ciphertext cannot be decrypted — typically because DRIVER_ENCRYPTION_KEY
    does not match the key used to encrypt this driver's password.
    """
    try:
        return _get_fernet().decrypt(encrypted_password.encode("utf-8")).decode("utf-8")
    except Exception as exc:
        logger.error(
            "driver_password_decrypt_failed",
            extra={
                "extra_fields": {
                    "error": type(exc).__name__,
                    "hint": "DRIVER_ENCRYPTION_KEY mismatch — re-save the driver's password or "
                    "re-encrypt with the original key",
                }
            },
        )
        raise DriverPasswordDecryptError(
            "Driver password could not be decrypted. The DRIVER_ENCRYPTION_KEY in the "
            "environment does not match the key used to encrypt this driver's password. "
            "Re-save the driver's UTCMS password via the UI/API, or re-encrypt the existing "
            "values using the original key (see scripts/reencrypt_drivers.py)."
        ) from exc


def _decode_jwt(token: str) -> dict:
    """Centralized JWT decode with consistent audience/issuer verification.

    All decode paths in this module must use this helper to ensure audience and
    issuer claims are verified when configured, matching the behaviour of
    ``security._is_jwt_valid()``.
    """
    kwargs: dict = {
        "algorithms": [utcms_config.JWT_ALGORITHM],
    }
    if utcms_config.JWT_AUDIENCE:
        kwargs["audience"] = utcms_config.JWT_AUDIENCE
    if utcms_config.JWT_ISSUER:
        kwargs["issuer"] = utcms_config.JWT_ISSUER
    return jwt.decode(token, utcms_config.JWT_SECRET, **kwargs)


async def _check_token_blacklist(payload: dict) -> None:
    """Raise 401 if the decoded token's JTI has been blacklisted (logout).

    Tokens without a ``jti`` claim (issued before the blacklist feature was
    added) are not checked — they will expire naturally within the reduced
    4-hour window.
    """
    jti = payload.get("jti")
    if not jti:
        return
    if await is_blacklisted(jti):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token has been revoked",
            headers={"WWW-Authenticate": "Bearer"},
        )


def create_access_token(
    client_id: int,
    client_code: str,
    email: str,
    role: str = "client",
    expires_delta: timedelta | None = None,
) -> str:
    """Create a JWT access token."""
    if expires_delta:
        expire = datetime.now(UTC).replace(tzinfo=None) + expires_delta
    else:
        expire = datetime.now(UTC).replace(tzinfo=None) + timedelta(
            minutes=utcms_config.JWT_ACCESS_TOKEN_EXPIRE_MINUTES
        )

    to_encode = {
        "sub": str(client_id),  # JWT sub must be string
        "client_code": client_code,
        "email": email,
        "role": role,
        "iat": datetime.now(UTC).replace(tzinfo=None),
        "exp": expire,
        "jti": uuid.uuid4().hex,
    }

    # Include audience and issuer claims when configured, so that
    # ``_decode_jwt`` can verify them on every decode path.
    if utcms_config.JWT_AUDIENCE:
        to_encode["aud"] = utcms_config.JWT_AUDIENCE
    if utcms_config.JWT_ISSUER:
        to_encode["iss"] = utcms_config.JWT_ISSUER

    encoded_jwt = jwt.encode(
        to_encode,
        utcms_config.JWT_SECRET,
        algorithm=utcms_config.JWT_ALGORITHM,
    )
    return encoded_jwt


def decode_access_token(token: str) -> dict:
    """Decode and validate a JWT access token."""
    try:
        payload = _decode_jwt(token)
        # Convert sub to int if it's a string
        if isinstance(payload.get("sub"), str) and payload["sub"].isdigit():
            payload["sub"] = int(payload["sub"])
        return payload
    except JWTError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
            headers={"WWW-Authenticate": "Bearer"},
        ) from None


async def get_current_client(
    request: Request = None,
    credentials: HTTPAuthorizationCredentials | None = Depends(security),
    session: AsyncSession = Depends(get_session),
) -> Client:
    """
    Get the current authenticated client from JWT token (header or cookie).
    Enforces tenant isolation by validating the token and returning the client.
    """
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )

    token = None
    if credentials:
        token = credentials.credentials
    elif request is not None:
        token = request.cookies.get("utcms_auth_token")

    if not token:
        raise credentials_exception

    try:
        payload = _decode_jwt(token)
        await _check_token_blacklist(payload)
        if payload.get("role") != "client":
            raise credentials_exception
        raw_client_id = payload.get("sub")
        if raw_client_id is None:
            raise credentials_exception

        # Safely convert sub claim to int, rejecting any non-integer values
        try:
            client_id = int(str(raw_client_id))
        except (TypeError, ValueError):
            raise credentials_exception from None

        raw_client_code = payload.get("client_code")
        if raw_client_code is None:
            raise credentials_exception

        client_code: str = str(raw_client_code)

        if not client_id:
            raise credentials_exception
    except JWTError:
        raise credentials_exception from None

    # Fetch client from database
    statement = select(Client).where(Client.id == client_id)
    result = await session.exec(statement)
    client = result.first()

    if client is None:
        raise credentials_exception
    if client.client_code != client_code:
        raise credentials_exception

    # Check if client is active
    if client.status != ClientStatus.ACTIVE.value:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Client account is not active",
        )

    # Check subscription dates
    now = datetime.now(UTC).replace(tzinfo=None)
    if client.subscription_start_date and client.subscription_start_date > now:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="اشتراک شما هنوز شروع نشده است.",
        )
    if client.subscription_end_date and client.subscription_end_date < now:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="اشتراک شما به پایان رسیده است.",
        )

    return client


async def is_master_admin(username: str, password: str) -> bool:
    """Validate the singleton master admin account configured for the system.

    Uses bcrypt for secure password comparison. Master admin password must be bcrypt-hashed.
    """
    if not secrets.compare_digest(username, utcms_config.MASTER_ADMIN_USERNAME):
        return False

    stored = utcms_config.MASTER_ADMIN_PASSWORD
    # Master admin password must be bcrypt-hashed (security requirement)
    if not stored.startswith(("$2a$", "$2b$", "$2y$")):
        raise ValueError(
            "MASTER_ADMIN_PASSWORD must be bcrypt-hashed. " "Plain-text passwords are not allowed for security reasons."
        )
    try:
        return await asyncio.to_thread(bcrypt.checkpw, password.encode("utf-8"), stored.encode("utf-8"))
    except Exception:
        return False


async def get_current_admin(
    request: Request = None,
    credentials: HTTPAuthorizationCredentials | None = Depends(security),
):
    """Validate and return the current master admin identity from JWT token (header or cookie)."""
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate admin credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )

    token = None
    if credentials:
        token = credentials.credentials
    elif request is not None:
        token = request.cookies.get("utcms_auth_token")

    if not token:
        raise credentials_exception

    try:
        payload = _decode_jwt(token)
        await _check_token_blacklist(payload)
        if payload.get("role") != "master_admin":
            raise credentials_exception
        if payload.get("client_code") != utcms_config.MASTER_ADMIN_USERNAME:
            raise credentials_exception
    except JWTError:
        raise credentials_exception from None

    return {
        "username": utcms_config.MASTER_ADMIN_USERNAME,
        "role": "master_admin",
    }


def enforce_tenant_filter(client: Client, query, model_class):
    """
    Enforce tenant isolation by adding client_id filter to queries.
    This ensures clients can only access their own data.
    """
    if hasattr(model_class, "client_id"):
        return query.where(model_class.client_id == client.id)
    return query


class TenantIsolationError(Exception):
    """Raised when tenant isolation is violated."""


def verify_tenant_ownership(
    client: Client,
    resource,
    resource_model,
) -> bool:
    """
    Verify that a resource belongs to the given client.
    Raises TenantIsolationError if the resource belongs to another tenant.
    """
    if not hasattr(resource_model, "client_id"):
        raise TenantIsolationError(f"Model {resource_model.__name__} does not support tenant isolation")

    if resource.client_id != client.id:
        raise TenantIsolationError(
            f"Client {client.id} attempted to access resource belonging to client {resource.client_id}"
        )
    return True


async def get_current_user_or_admin(
    request: Request = None,
    credentials: HTTPAuthorizationCredentials | None = Depends(security),
    session: AsyncSession = Depends(get_session),
) -> dict:
    """
    Dependency that accepts either client or master_admin and returns a context dict:
    {"role": "client", "user": ClientInstance} or {"role": "master_admin", "user": {"username": "admin"}}
    """
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )

    token = None
    if credentials:
        token = credentials.credentials
    elif request is not None:
        token = request.cookies.get("utcms_auth_token")

    if not token:
        raise credentials_exception

    try:
        payload = _decode_jwt(token)
        await _check_token_blacklist(payload)
        role = payload.get("role")
        if role == "master_admin":
            if payload.get("client_code") != utcms_config.MASTER_ADMIN_USERNAME:
                raise credentials_exception
            return {
                "role": "master_admin",
                "user": {
                    "username": utcms_config.MASTER_ADMIN_USERNAME,
                    "role": "master_admin",
                },
            }
        elif role == "client":
            raw_client_id = payload.get("sub")
            if raw_client_id is None:
                raise credentials_exception
            client_id = int(str(raw_client_id))

            raw_client_code = payload.get("client_code")
            if raw_client_code is None:
                raise credentials_exception
            client_code = str(raw_client_code)

            statement = select(Client).where(Client.id == client_id)
            result = await session.exec(statement)
            client = result.first()

            if client is None or client.client_code != client_code:
                raise credentials_exception

            if client.status != ClientStatus.ACTIVE.value:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Client account is not active",
                )

            # Check subscription dates
            now = datetime.now(UTC).replace(tzinfo=None)
            if client.subscription_start_date and client.subscription_start_date > now:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="اشتراک شما هنوز شروع نشده است.",
                )
            if client.subscription_end_date and client.subscription_end_date < now:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="اشتراک شما به پایان رسیده است.",
                )

            return {"role": "client", "user": client}
        else:
            raise credentials_exception
    except JWTError:
        raise credentials_exception from None

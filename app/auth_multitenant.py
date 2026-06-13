"""
Multi-tenant authentication and authorization system.

Provides JWT-based authentication for clients with tenant isolation enforcement.
Each client can only access their own drivers and waybill tasks.
"""
import hashlib
import logging
import secrets
from datetime import UTC, datetime, timedelta

import bcrypt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError, jwt
from pydantic import BaseModel
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.core.config import utcms_config
from app.core.database import get_session
from app.models_multitenant import Client, ClientStatus

logger = logging.getLogger(__name__)

# Security scheme
security = HTTPBearer()


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


def hash_password(password: str) -> str:
    """Hash a password using bcrypt."""
    salt = bcrypt.gensalt()
    hashed = bcrypt.hashpw(password.encode("utf-8"), salt)
    return hashed.decode("utf-8")


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verify a password against its hash."""
    try:
        return bcrypt.checkpw(
            plain_password.encode("utf-8"),
            hashed_password.encode("utf-8"),
        )
    except Exception as e:
        logger.error("password_verification_error", extra={"extra_fields": {"error_type": type(e).__name__}})
        return False


def encrypt_driver_password(plain_password: str) -> str:
    """
    Encrypt driver's UTCMS password for storage.
    Uses a simple hash-based approach suitable for automation injection.
    """
    # For automation purposes, we store a reversible encryption
    # In production, use proper encryption like Fernet
    from cryptography.fernet import Fernet

    # Derive a key from a master encryption key
    master_key = utcms_config.DRIVER_ENCRYPTION_KEY.encode("utf-8")
    key = hashlib.sha256(master_key).digest()
    from base64 import urlsafe_b64encode
    fernet = Fernet(urlsafe_b64encode(key[:32]))

    return fernet.encrypt(plain_password.encode("utf-8")).decode("utf-8")


def decrypt_driver_password(encrypted_password: str) -> str:
    """Decrypt driver's UTCMS password."""
    from base64 import urlsafe_b64encode

    from cryptography.fernet import Fernet

    master_key = utcms_config.DRIVER_ENCRYPTION_KEY.encode("utf-8")
    key = hashlib.sha256(master_key).digest()
    fernet = Fernet(urlsafe_b64encode(key[:32]))

    return fernet.decrypt(encrypted_password.encode("utf-8")).decode("utf-8")


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
        expire = datetime.now(UTC).replace(tzinfo=None) + timedelta(minutes=utcms_config.JWT_ACCESS_TOKEN_EXPIRE_MINUTES)

    to_encode = {
        "sub": str(client_id),  # JWT sub must be string
        "client_code": client_code,
        "email": email,
        "role": role,
        "iat": datetime.now(UTC).replace(tzinfo=None),
        "exp": expire,
    }

    encoded_jwt = jwt.encode(
        to_encode,
        utcms_config.JWT_SECRET,
        algorithm=utcms_config.JWT_ALGORITHM,
    )
    return encoded_jwt


def decode_access_token(token: str) -> dict:
    """Decode and validate a JWT access token."""
    try:
        payload = jwt.decode(
            token,
            utcms_config.JWT_SECRET,
            algorithms=[utcms_config.JWT_ALGORITHM],
            options={"verify_aud": False},
        )
        # Convert sub to int if it's a string
        if isinstance(payload.get('sub'), str) and payload['sub'].isdigit():
            payload['sub'] = int(payload['sub'])
        return payload
    except JWTError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
            headers={"WWW-Authenticate": "Bearer"},
        ) from None


async def get_current_client(
    credentials: HTTPAuthorizationCredentials = Depends(security),
    session: AsyncSession = Depends(get_session),
) -> Client:
    """
    Get the current authenticated client from JWT token.
    Enforces tenant isolation by validating the token and returning the client.
    """
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )

    try:
        payload = jwt.decode(
            credentials.credentials,
            utcms_config.JWT_SECRET,
            algorithms=[utcms_config.JWT_ALGORITHM],
        )
        if payload.get("role", "client") != "client":
            raise credentials_exception
        raw_client_id = payload.get("sub")
        # Safely convert sub claim to int, rejecting any non-integer values
        try:
            client_id = int(raw_client_id)
        except (TypeError, ValueError):
            raise credentials_exception from None
        client_code: str = payload.get("client_code")
        if not client_id or client_code is None:
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

    return client


def is_master_admin(username: str, password: str) -> bool:
    """Validate the singleton master admin account configured for the system.

    Uses bcrypt for secure password comparison when the stored password is bcrypt-hashed.
    Falls back to direct comparison for plain-text configured passwords.
    """
    if not secrets.compare_digest(username, utcms_config.MASTER_ADMIN_USERNAME):
        return False

    stored = utcms_config.MASTER_ADMIN_PASSWORD
    # If stored password looks like a bcrypt hash, use bcrypt comparison
    if stored.startswith(("$2a$", "$2b$", "$2y$")):
        try:
            return bcrypt.checkpw(password.encode("utf-8"), stored.encode("utf-8"))
        except Exception:
            return False
    # Direct constant-time comparison for plain-text configured passwords
    return secrets.compare_digest(password, stored)


async def get_current_admin(
    credentials: HTTPAuthorizationCredentials = Depends(security),
):
    """Validate and return the current master admin identity from JWT token."""
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate admin credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )

    try:
        payload = jwt.decode(
            credentials.credentials,
            utcms_config.JWT_SECRET,
            algorithms=[utcms_config.JWT_ALGORITHM],
        )
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
    pass


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

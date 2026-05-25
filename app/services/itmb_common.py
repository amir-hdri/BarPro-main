import hashlib
import random
from typing import Optional, Tuple

from fastapi import HTTPException

from app.core.config import utcms_config


def build_hashed_value(company_code: str, salt: int, service_password: str) -> str:
    raw_value = f"{company_code}{salt}{service_password}"
    return hashlib.sha512(raw_value.encode("utf-8")).hexdigest().upper()


def resolve_itmb_auth(
    company_code: Optional[str],
    service_password: Optional[str],
    salt: Optional[int] = None,
    hashed_value: Optional[str] = None,
) -> Tuple[str, int, str]:
    resolved_company_code = (company_code or utcms_config.ITMBOL_COMPANY_CODE).strip()
    if not resolved_company_code:
        raise HTTPException(status_code=400, detail="CompanyCode تنظیم نشده است")

    resolved_salt = salt if salt is not None else random.randint(100000, 999999999)

    if hashed_value:
        return resolved_company_code, resolved_salt, hashed_value.strip().upper()

    resolved_password = (service_password or utcms_config.ITMBOL_SERVICE_PASSWORD).strip()
    if not resolved_password:
        raise HTTPException(status_code=400, detail="ServicePassword برای محاسبه HashedValue تنظیم نشده است")

    generated_hash = build_hashed_value(
        company_code=resolved_company_code,
        salt=resolved_salt,
        service_password=resolved_password,
    )
    return resolved_company_code, resolved_salt, generated_hash


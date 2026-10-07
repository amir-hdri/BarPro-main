"""Prevent a new driver submission while a persisted OTP document is unresolved."""

from __future__ import annotations

import json
from typing import Any

from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.models_multitenant import WaybillJob


def unresolved_otp_document(job: WaybillJob) -> bool:
    raw: Any = job.result_json
    if isinstance(raw, str):
        try:
            raw = json.loads(raw)
        except (TypeError, ValueError):
            return False
    result = raw if isinstance(raw, dict) else {}
    if result.get("tracking_code"):
        return False
    document = str(result.get("document_id") or job.document_id or "").strip()
    challenge = result.get("_otp_challenge")
    return bool(document) and (
        result.get("otp_required") is True
        or job.error_category in {"otp_required", "otp_rejected"}
        or (isinstance(challenge, dict) and str(challenge.get("document_id")) == document)
    )


async def find_unresolved_driver_otp_job(
    session: AsyncSession,
    *,
    client_id: int,
    driver_id: int | None,
) -> WaybillJob | None:
    """Tracking or removal of the challenge resolves the block; age alone never does.

    Historical error states without a real document/challenge do not block a driver.
    Workers must call this while holding the existing per-driver submission lock.
    """
    if driver_id is None:
        return None
    rows = (
        await session.exec(
            select(WaybillJob)
            .where(
                WaybillJob.client_id == client_id,
                WaybillJob.driver_id == driver_id,
            )
            .execution_options(populate_existing=True)
        )
    ).all()
    return next((job for job in rows if unresolved_otp_document(job)), None)

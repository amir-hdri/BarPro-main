"""
Schemas for Client Panel API
"""

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, field_validator


class WaybillResponse(BaseModel):
    """Waybill response"""

    id: int
    job_id: str
    client_id: int
    driver_id: int
    status: str
    scheduled_by: str

    # Result
    waybill_number: str | None = None
    payload_json: dict | list | str | Any | None = None
    result_json: dict | list | str | Any | None = None

    # Error info
    terminal_reason: str | None = None
    last_error: str | None = None

    # Timing
    created_at: datetime
    started_at: datetime | None = None
    finished_at: datetime | None = None
    duration_seconds: float | None = None

    @field_validator("payload_json", "result_json", mode="before")
    @classmethod
    def coerce_json_fields(cls, v: Any) -> Any:
        if v is None:
            return v
        if isinstance(v, (dict, list)):
            return v
        if isinstance(v, str):
            import json

            try:
                return json.loads(v)
            except (ValueError, TypeError):
                return v
        return v

    model_config = ConfigDict(from_attributes=True)

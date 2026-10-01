"""
Schemas for Super Admin API
"""

from pydantic import BaseModel, Field


class DriverReportFilter(BaseModel):
    """Filter parameters for driver reports"""

    client_id: int | None = Field(default=None, description="Filter by client")
    driver_id: int | None = Field(default=None, description="Filter by driver")
    driver_national_code: str | None = Field(default=None, description="Filter by driver national code")
    driver_name: str | None = Field(default=None, description="Filter by driver name")
    plate_id: int | None = Field(default=None, description="Filter by plate ID")
    plate_number: str | None = Field(default=None, description="Filter by plate number")
    status: str | None = Field(default=None, description="Filter by job status")
    date_from: str | None = Field(default=None, description="Start date (YYYY-MM-DD)")
    date_to: str | None = Field(default=None, description="End date (YYYY-MM-DD)")
    operation_type: str | None = Field(default=None, description="Filter by source (manual, api, bulk_upload)")
    page: int = Field(default=1, ge=1)
    page_size: int = Field(default=50, ge=1, le=200)

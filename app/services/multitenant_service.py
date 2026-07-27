"""
Backward-compatibility shim.

All service classes have been decomposed into per-domain modules:
    - app.services.client_service      → ClientService
    - app.services.driver_service      → DriverService
    - app.services.plate_service       → PlateService
    - app.services.driver_schedule_service → DriverScheduleService
    - app.services.waybill_job_service → WaybillJobService
    - app.services._helpers            → shared utility functions

This module re-exports everything so that existing imports of the form
    from app.services.multitenant_service import ClientService
continue to work without changes.
"""

from app.services.client_service import ClientService
from app.services.driver_schedule_service import DriverScheduleService
from app.services.driver_service import DriverService
from app.services.plate_service import PlateService
from app.services.waybill_job_service import WaybillJobService

__all__ = [
    "ClientService",
    "DriverScheduleService",
    "DriverService",
    "PlateService",
    "WaybillJobService",
]

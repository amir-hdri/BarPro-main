"""Contract tests for the /new wizard submit payload (frontend ↔ backend).

Regression context (user screenshots, Oct 2026): the wizard POSTed a nested-only
payload — ``origin``/``destination`` as OBJECTS, no top-level strings, no
``financial`` key — and the backend union ``WaybillPayload | WaybillNestedPayload``
rejected it with HTTP 422::

    payload.WaybillPayload.origin: Input should be a valid string,
    payload.WaybillPayload.destination: Input should be a valid string,
    payload.WaybillNestedPayload.financial: Field required

The fix is frontend-side (send top-level ``origin``/``destination`` strings so the
flat contract validates). These tests pin both sides of that contract, plus the
run-due guard for schedules whose stored template cannot materialize a job
(empty template → skip, never an unhandled 500).
"""

import pytest
from pydantic import ValidationError
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.orm import sessionmaker
from sqlmodel import SQLModel
from sqlmodel.ext.asyncio.session import AsyncSession

from app.models_multitenant import Client, Driver
from app.schemas.multitenant import WaybillJobCreateRequest
from app.services.driver_schedule_service import DriverScheduleService


def _wizard_payload_nested_only() -> dict:
    """Exact shape the /new wizard sent before the fix (no flat strings, no financial)."""
    return {
        "driver_national_code": "0084575948",
        "origin_city": "همدان",
        "destination_city": "همدان",
        "origin_postal_code": "6511111111",
        "destination_postal_code": "6511222222",
        "origin_lat": 34.8,
        "origin_lng": 48.5,
        "dest_lat": 34.8,
        "dest_lng": 48.5,
        "cargo_type": "آجر",
        "cargo_packaging": "فله",
        "cargo_weight": 8000.0,
        "cargo_value": "20000000",
        "vehicle_type": "کامیون",
        "plate_number": "28ع856ایران28",
        "driver_phone": "09123456789",
        "sender_name": "الف",
        "sender_phone": "09121111111",
        "sender_national_code": "4929889601",
        "sender_postal_code": "6511111111",
        "receiver_name": "ب",
        "receiver_phone": "09122222222",
        "receiver_national_code": "0321410408",
        "receiver_postal_code": "6511222222",
        "sender": {"name": "الف", "phone": "09121111111", "national_code": "4929889601", "postal_code": "6511111111"},
        "receiver": {"name": "ب", "phone": "09122222222", "national_code": "0321410408", "postal_code": "6511222222"},
        "origin": {"province": "همدان", "city": "همدان", "address": "خ", "postal_code": "6511111111"},
        "destination": {"province": "همدان", "city": "همدان", "address": "خ", "postal_code": "6511222222"},
        "cargo": {"type": "آجر", "packaging": "فله", "weight": 8000.0, "value": "20000000"},
        "vehicle": {"driver_national_code": "0084575948", "plate": "28ع856ایران28", "type": "کامیون"},
    }


def test_nested_only_wizard_payload_rejected_with_screenshot_errors():
    """Pin the diagnosis: nested-only payload fails BOTH union members (HTTP 422)."""
    with pytest.raises(ValidationError) as exc_info:
        WaybillJobCreateRequest(driver_national_code="0084575948", payload=_wizard_payload_nested_only())
    errors = exc_info.value.errors()
    flat_origin = [e for e in errors if list(e["loc"][-2:]) == ["WaybillPayload", "origin"]]
    flat_destination = [e for e in errors if list(e["loc"][-2:]) == ["WaybillPayload", "destination"]]
    nested_financial = [e for e in errors if list(e["loc"][-2:]) == ["WaybillNestedPayload", "financial"]]
    assert flat_origin and "valid string" in str(flat_origin[0]["msg"])
    assert flat_destination and "valid string" in str(flat_destination[0]["msg"])
    assert nested_financial and nested_financial[0]["type"] == "missing"
    # No more, no less: the union must fail on exactly these three top-level locs.
    top_level_locs = {(e["loc"][-2], e["loc"][-1]) for e in errors}
    assert top_level_locs == {
        ("WaybillPayload", "origin"),
        ("WaybillPayload", "destination"),
        ("WaybillNestedPayload", "financial"),
    }


def test_wizard_payload_with_flat_strings_validates():
    """The frontend fix (top-level origin/destination strings; the redundant nested
    origin/destination objects removed, rich data kept in metadata_json) validates
    as the flat WaybillPayload contract."""
    from app.schemas.multitenant import WaybillPayload

    payload = _wizard_payload_nested_only()
    del payload["origin"]
    del payload["destination"]
    payload["origin"] = "همدان"
    payload["destination"] = "همدان"
    payload["metadata_json"] = {"wizard": "new", "route": {"origin_city": "همدان", "destination_city": "همدان"}}
    req = WaybillJobCreateRequest(driver_national_code="0084575948", payload=payload)
    assert isinstance(req.payload, WaybillPayload)
    assert req.payload.origin == "همدان"
    assert req.payload.destination == "همدان"
    assert req.payload.metadata_json == {
        "wizard": "new",
        "route": {"origin_city": "همدان", "destination_city": "همدان"},
    }


@pytest.mark.asyncio
async def test_run_due_with_empty_template_skips_without_raising():
    """A schedule with an empty payload template must be skipped, never 500."""
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    mk = sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    async with engine.begin() as conn:
        await conn.run_sync(SQLModel.metadata.create_all)
    async with mk() as session:
        client = Client(
            client_code="t-sched-500",
            name="T",
            email="t@t.com",
            hashed_password="h",
            username="u500",
            full_name="U",
        )
        session.add(client)
        await session.commit()
        await session.refresh(client)
        driver = Driver(
            client_id=client.id,
            driver_national_code="0084575948",
            full_name="D",
            utcms_username="u",
            utcms_password_encrypted="p",
        )
        session.add(driver)
        await session.commit()
        await session.refresh(driver)
        from app.models_multitenant import DriverSchedule

        session.add(
            DriverSchedule(
                client_id=client.id,
                driver_id=driver.id,
                title="empty template",
                frequency="daily",
                run_time="00:00",
                run_times_csv="00:00",
                payload_template_json={},
                is_active=True,
            )
        )
        await session.commit()
        # Must not raise (previously: pydantic ValidationError → HTTP 500).
        result = await DriverScheduleService.run_due_schedules(client, session)
        assert result["created_count"] == 0
        assert result["skipped"] >= 1
        # Invalid-template skip consumes the slot but leaves the row in place
        # and creates no job.
        from sqlmodel import select

        from app.models_multitenant import DriverSchedule, WaybillJob

        remaining_schedules = (await session.exec(select(DriverSchedule))).all()
        assert len(remaining_schedules) == 1
        created_jobs = (await session.exec(select(WaybillJob))).all()
        assert created_jobs == []
    await engine.dispose()

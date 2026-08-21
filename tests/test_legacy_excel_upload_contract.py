"""Fail-closed contract tests for the deprecated multi-tenant Excel upload."""

import io
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException, UploadFile, status

from app.api.routes.multitenant import router, upload_excel_file
from app.services.excel_upload_service import (
    LEGACY_EXCEL_UPLOAD_DISABLED_DETAIL,
    ExcelUploadService,
)


def _upload_file() -> UploadFile:
    return UploadFile(filename="legacy.xlsx", file=io.BytesIO(b"not-read"))


def _assert_gone(exc: HTTPException) -> None:
    assert exc.status_code == status.HTTP_410_GONE
    assert exc.detail == LEGACY_EXCEL_UPLOAD_DISABLED_DETAIL
    assert exc.detail["canonical_endpoint"] == "POST /api/v1/waybill-jobs"


@pytest.mark.asyncio
async def test_legacy_excel_route_fails_closed_without_calling_creation_service() -> None:
    with patch.object(ExcelUploadService, "process_upload", new_callable=AsyncMock) as process_upload:
        with pytest.raises(HTTPException) as exc_info:
            await upload_excel_file(
                file=_upload_file(),
                max_retries=3,
                client=MagicMock(),
                session=AsyncMock(),
            )

    _assert_gone(exc_info.value)
    process_upload.assert_not_awaited()


@pytest.mark.asyncio
async def test_legacy_excel_service_rejects_before_reading_file_or_mutating_session() -> None:
    file = AsyncMock()
    session = AsyncMock()

    with pytest.raises(HTTPException) as exc_info:
        await ExcelUploadService.process_upload(
            client=MagicMock(),
            file=file,
            session=session,
            max_retries=3,
        )

    _assert_gone(exc_info.value)
    file.read.assert_not_awaited()
    session.add.assert_not_called()
    session.commit.assert_not_awaited()


def test_legacy_excel_route_is_marked_deprecated_in_openapi_metadata() -> None:
    route = next(
        route
        for route in router.routes
        if getattr(route, "path", None) == "/api/v1/upload/excel" and "POST" in getattr(route, "methods", set())
    )

    assert route.deprecated is True
    assert route.status_code == status.HTTP_410_GONE

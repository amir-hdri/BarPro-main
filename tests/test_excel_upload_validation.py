"""Excel upload validation tests for ManagementService.import_excel_workbook.

Uploads must fail with controlled 4xx errors — never bypass validation and
never 500:
- empty / shorter-than-4-bytes input must not slip past the magic-byte check
- legacy OLE .xls must be rejected (read_xlsx only parses ZIP-based .xlsx)
- corrupt ZIP bodies and malformed XML inside must be 400, not 500
"""

import io
import zipfile

import pytest
from fastapi import HTTPException

from app.schemas.management import ManagementExcelImportOptions
from app.services.management_service import ManagementService


def _options() -> ManagementExcelImportOptions:
    return ManagementExcelImportOptions()


async def _import(content: bytes, filename: str = "test.xlsx") -> dict:
    # Validation failures happen before any DB/browser/self usage, so the
    # service instance itself is never touched on these paths.
    return await ManagementService.import_excel_workbook(
        object(), content, filename, _options()  # type: ignore[arg-type]
    )


@pytest.mark.asyncio
async def test_empty_file_rejected():
    with pytest.raises(HTTPException) as exc_info:
        await _import(b"", "empty.xlsx")
    assert exc_info.value.status_code == 400


@pytest.mark.asyncio
async def test_short_file_rejected():
    # Fewer than 4 bytes previously bypassed the magic-byte comparison.
    with pytest.raises(HTTPException) as exc_info:
        await _import(b"\x50\x4b", "short.xlsx")
    assert exc_info.value.status_code == 400


@pytest.mark.asyncio
async def test_wrong_magic_rejected():
    with pytest.raises(HTTPException) as exc_info:
        await _import(b"%PDF-1.4 fake pdf content", "fake.xlsx")
    assert exc_info.value.status_code == 400


@pytest.mark.asyncio
async def test_ole_xls_rejected_not_500():
    # Legacy .xls OLE container: accepted by the old magic set but unparseable
    # by zipfile-based read_xlsx (was a 500 via BadZipFile).
    ole = b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1" + b"\x00" * 64
    with pytest.raises(HTTPException) as exc_info:
        await _import(ole, "legacy.xls")
    assert exc_info.value.status_code == 400
    assert "xls" in exc_info.value.detail.lower()


@pytest.mark.asyncio
async def test_truncated_zip_rejected_not_500():
    # Valid ZIP magic but corrupt body.
    with pytest.raises(HTTPException) as exc_info:
        await _import(b"\x50\x4b\x03\x04" + b"\xff" * 100, "corrupt.xlsx")
    assert exc_info.value.status_code == 400


@pytest.mark.asyncio
async def test_zip_without_workbook_rejected_not_500():
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("random.txt", "not an excel file")
    with pytest.raises(HTTPException) as exc_info:
        await _import(buf.getvalue(), "not-excel.xlsx")
    assert exc_info.value.status_code == 400


@pytest.mark.asyncio
async def test_malformed_workbook_xml_rejected_not_500():
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("xl/workbook.xml", "<broken><xml")
        zf.writestr("xl/_rels/workbook.xml.rels", "<broken><xml")
    with pytest.raises(HTTPException) as exc_info:
        await _import(buf.getvalue(), "bad-xml.xlsx")
    assert exc_info.value.status_code == 400

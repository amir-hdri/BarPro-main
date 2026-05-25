from pathlib import Path

from fastapi import APIRouter
from fastapi.responses import FileResponse

router = APIRouter(tags=["ui"])

_PROJECT_ROOT = Path(__file__).resolve().parents[3]
_UI_INDEX = _PROJECT_ROOT / "app" / "ui" / "index.html"


@router.get("/ui", include_in_schema=False)
async def ui_home() -> FileResponse:
    return FileResponse(_UI_INDEX)


@router.head("/ui", include_in_schema=False)
async def ui_home_head() -> FileResponse:
    return FileResponse(_UI_INDEX)

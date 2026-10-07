"""Persist private CAPTCHA images and non-sensitive diagnostics after rejection."""

from __future__ import annotations

import base64
import hashlib
import json
import logging
import secrets
import tempfile
import time
from pathlib import Path
from typing import Any

from app.core.private_storage import private_directory, write_private_file

logger = logging.getLogger(__name__)

# Same discoverable basename on Linux; private_directory verifies ownership,
# refuses directory symlinks and pins all file writes to a private directory.
DEFAULT_ARTIFACT_DIR = Path(tempfile.gettempdir()) / "captcha_rejections"


def _strip_data_uri(image_base64: str) -> bytes:
    cleaned = str(image_base64 or "").strip()
    if "," in cleaned:
        cleaned = cleaned.split(",", 1)[1]
    pad = len(cleaned) % 4
    if pad:
        cleaned += "=" * (4 - pad)
    return base64.b64decode(cleaned)


def save_rejection_artifact(
    image_base64: str,
    *,
    prediction: str | None = None,
    result_code: Any,
    provider: str | None = None,
    expression: str | None = None,
    confidence: float | None = None,
    form_id: Any = 1,
    directory: Path | None = None,
    extra: dict[str, Any] | None = None,
) -> Path | None:
    """Write a private image and metadata without solved answers or expressions.

    The prediction/expression arguments remain accepted for legacy callers but
    are deliberately excluded from logs and artifacts. Extra context is limited
    to known operational fields so solver metadata cannot reintroduce answers.
    Returns the JSON path, or None on any failure (never raises).
    """
    try:
        out_dir = directory or DEFAULT_ARTIFACT_DIR
        stamp = f"{time.strftime('%Y%m%dT%H%M%S')}-{secrets.token_hex(12)}"
        png_path = out_dir / f"{stamp}.png"
        json_path = out_dir / f"{stamp}.json"

        with private_directory(out_dir) as directory_fd:
            image_data = None
            try:
                image_data = _strip_data_uri(image_base64)
                write_private_file(directory_fd, png_path.name, image_data)
                image_saved = True
            except Exception as img_exc:
                logger.warning("captcha_artifact_image_write_failed: %s", img_exc)
                image_saved = False

            payload = {
                "saved_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                "result_code": result_code,
                "provider": provider,
                "confidence": confidence,
                "form_id": form_id,
                "image_png": str(png_path) if image_saved else None,
                "image_b64_len": len(image_base64 or ""),
                "image_sha256": hashlib.sha256(image_data).hexdigest() if image_data is not None else None,
                "image_bytes": len(image_data) if image_data is not None else None,
            }
            if extra:
                safe_extra = {
                    key: value
                    for key, value in extra.items()
                    if key in {"attempt", "form_id", "script"} and isinstance(value, (int, str))
                }
                if safe_extra:
                    payload["extra"] = safe_extra
            write_private_file(
                directory_fd, json_path.name, json.dumps(payload, ensure_ascii=False, indent=2).encode("utf-8")
            )
        logger.warning(
            "captcha_rejection_artifact result_code=%s conf=%s json=%s",
            result_code,
            confidence,
            json_path,
        )
        return json_path
    except Exception as exc:
        logger.warning("captcha_artifact_save_failed: %s", exc)
        return None

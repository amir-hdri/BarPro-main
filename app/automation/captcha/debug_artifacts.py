"""Persist CAPTCHA image + model prediction side-by-side when UTCMS rejects a solve (4003)."""

from __future__ import annotations

import base64
import json
import logging
import time
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

DEFAULT_ARTIFACT_DIR = Path("/tmp/captcha_rejections")


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
    prediction: str | None,
    result_code: Any,
    provider: str | None = None,
    expression: str | None = None,
    confidence: float | None = None,
    form_id: Any = 1,
    directory: Path | None = None,
    extra: dict[str, Any] | None = None,
) -> Path | None:
    """Write `<ts>.png` + `<ts>.json` with image and prediction side-by-side metadata.

    Returns the JSON path, or None on any failure (never raises).
    """
    try:
        out_dir = directory or DEFAULT_ARTIFACT_DIR
        out_dir.mkdir(parents=True, exist_ok=True)
        stamp = time.strftime("%Y%m%dT%H%M%S")
        png_path = out_dir / f"{stamp}.png"
        json_path = out_dir / f"{stamp}.json"

        try:
            png_path.write_bytes(_strip_data_uri(image_base64))
            image_saved = True
        except Exception as img_exc:
            logger.warning("captcha_artifact_image_write_failed: %s", img_exc)
            image_saved = False

        payload = {
            "saved_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "result_code": result_code,
            "provider": provider,
            "prediction": prediction,
            "expression": expression,
            "confidence": confidence,
            "form_id": form_id,
            "image_png": str(png_path) if image_saved else None,
            "image_b64_len": len(image_base64 or ""),
        }
        if extra:
            payload["extra"] = extra
        json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        logger.warning(
            "captcha_rejection_artifact result_code=%s prediction=%r expression=%r conf=%s json=%s",
            result_code,
            prediction,
            expression,
            confidence,
            json_path,
        )
        return json_path
    except Exception as exc:
        logger.warning("captcha_artifact_save_failed: %s", exc)
        return None

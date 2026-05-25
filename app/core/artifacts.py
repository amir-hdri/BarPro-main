import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional

from app.core.config import utcms_config
from app.core.execution_context import get_execution_context

logger = logging.getLogger(__name__)

_MAX_CAPTURED_HTML_CHARS = 50000
_MAX_CAPTURED_TELEMETRY_EVENTS = 80


class FailureArtifactService:
    def __init__(self, base_dir: str):
        self.base_dir = Path(base_dir)

    async def capture_failure_bundle(
        self,
        page: Any = None,
        *,
        error: Optional[Exception] = None,
        stage: str,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Optional[str]]:
        context = get_execution_context()
        timestamp = datetime.now(timezone.utc).replace(tzinfo=None).strftime("%Y%m%dT%H%M%S%fZ")
        bundle_dir = (
            self.base_dir
            / context.tenant_id
            / context.batch_id
            / context.task_id
            / timestamp
        )
        bundle_dir.mkdir(parents=True, exist_ok=True)

        paths = {
            "bundle_dir": str(bundle_dir),
            "screenshot_path": None,
            "dom_snapshot_path": None,
            "metadata_path": None,
            "console_log_path": None,
            "network_log_path": None,
        }

        payload = {
            "captured_at": datetime.now(timezone.utc).replace(tzinfo=None).isoformat(),
            "stage": stage,
            "error": str(error) if error else None,
            "context": context.__dict__,
            "metadata": metadata or {},
        }

        metadata_path = bundle_dir / "failure_bundle.json"
        metadata_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        paths["metadata_path"] = str(metadata_path)

        if page is not None:
            screenshot_path = bundle_dir / "failure.png"
            try:
                await page.screenshot(
                    path=str(screenshot_path),
                    full_page=False,
                    timeout=2500,
                    animations="disabled",
                )
                paths["screenshot_path"] = str(screenshot_path)
            except Exception as exc:
                logger.warning(
                    "failure_bundle_screenshot_failed",
                    extra={"extra_fields": {"error": str(exc), "stage": stage}},
                )

            dom_path = bundle_dir / "dom_snapshot.html"
            try:
                html = await page.content()
                dom_path.write_text(html[:_MAX_CAPTURED_HTML_CHARS], encoding="utf-8")
                paths["dom_snapshot_path"] = str(dom_path)
            except Exception as exc:
                logger.warning(
                    "failure_bundle_dom_failed",
                    extra={"extra_fields": {"error": str(exc), "stage": stage}},
                )

            console_path = bundle_dir / "console.json"
            try:
                console_events = list(getattr(page, "_telemetry_console_messages", []))[-_MAX_CAPTURED_TELEMETRY_EVENTS:]
                console_path.write_text(json.dumps(console_events, ensure_ascii=False, indent=2), encoding="utf-8")
                paths["console_log_path"] = str(console_path)
            except Exception as exc:
                logger.warning(
                    "failure_bundle_console_failed",
                    extra={"extra_fields": {"error": str(exc), "stage": stage}},
                )

            network_path = bundle_dir / "network.json"
            try:
                network_events = list(getattr(page, "_telemetry_network_events", []))[-_MAX_CAPTURED_TELEMETRY_EVENTS:]
                network_path.write_text(json.dumps(network_events, ensure_ascii=False, indent=2), encoding="utf-8")
                paths["network_log_path"] = str(network_path)
            except Exception as exc:
                logger.warning(
                    "failure_bundle_network_failed",
                    extra={"extra_fields": {"error": str(exc), "stage": stage}},
                )

        return paths


failure_artifact_service = FailureArtifactService(utcms_config.FAILURE_ARTIFACTS_DIR)

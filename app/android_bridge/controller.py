"""Android Shipping Controller for virtual Android / FakeTraveler integration.

Orchestrates location mocking with FakeTraveler and shipping lifecycle in
the official UTCMS transport application (com.baarnameshahri).
"""

from __future__ import annotations

import asyncio
import logging
import math
from datetime import datetime

try:
    from datetime import UTC
except ImportError:
    from datetime import timezone

    UTC = timezone.utc  # noqa: UP017
from typing import Any

from app.android_bridge.client import (
    LOCATION_PACKAGE,
    TARGET_PACKAGE,
    AndroidBridge,
    BridgeConfig,
    BridgeError,
    CommandRunner,
    _run_command,
)

logger = logging.getLogger(__name__)

__all__ = ["AndroidShippingController"]


class AndroidShippingController:
    """Controller orchestrating FakeTraveler and official transport app over ADB."""

    def __init__(
        self,
        config: BridgeConfig | None = None,
        *,
        bridge: AndroidBridge | None = None,
        runner: CommandRunner = _run_command,
        apply_button_coords: tuple[int, int] = (487, 189),
        use_layout: bool = False,
    ) -> None:
        if bridge is not None:
            self.bridge = bridge
            self.config = bridge.config
            self._runner = bridge._runner
        elif config is not None:
            self.config = config
            self._runner = runner
            self.bridge = AndroidBridge(config, runner=runner)
        else:
            self.config = BridgeConfig.from_env()
            self._runner = runner
            self.bridge = AndroidBridge(self.config, runner=runner)

        self.apply_button_coords = apply_button_coords
        self._use_layout = use_layout

    def _require_enabled(self) -> None:
        if not self.config.enabled:
            raise BridgeError("bridge_disabled")

    async def _adb(self, *args: str) -> str:
        self._require_enabled()
        argv = (self.config.adb_binary, "-s", self.config.serial, *args)
        return (await self._runner(argv, timeout=self.config.command_timeout)).strip()

    async def verify_device_ready(self) -> None:
        """Safety fence: fail-closed if bridge disabled, device not booted, or proxy mismatch."""
        self._require_enabled()
        state = await self._adb("get-state")
        if state != "device":
            raise BridgeError("device_not_ready")
        booted = await self._adb("shell", "getprop", "sys.boot_completed")
        if booted != "1":
            raise BridgeError("android_not_booted")
        proxy = await self._adb("shell", "settings", "get", "global", "http_proxy")
        if proxy != self.config.expected_proxy:
            raise BridgeError("proxy_setting_mismatch")

    @staticmethod
    def _validate_coordinates(lat: float, lon: float, altitude: float = 0.0) -> None:
        """Validate latitude and longitude bounds."""
        if not isinstance(lat, (int, float)) or not math.isfinite(lat) or not -90.0 <= float(lat) <= 90.0:
            raise ValueError(f"Latitude must be a finite number between -90 and 90, got: {lat}")
        if not isinstance(lon, (int, float)) or not math.isfinite(lon) or not -180.0 <= float(lon) <= 180.0:
            raise ValueError(f"Longitude must be a finite number between -180 and 180, got: {lon}")
        if not isinstance(altitude, (int, float)) or not math.isfinite(altitude):
            raise ValueError(f"Altitude must be a finite number, got: {altitude}")

    async def _trigger_apply_action(self) -> None:
        """Trigger location update/apply button in FakeTraveler."""
        if self._use_layout:
            try:
                obs = await self.bridge.layout()
                node = obs.require_unique(resource_id=f"{LOCATION_PACKAGE}:id/button_applyStop")
                if node.bounds:
                    left, top, right, bottom = node.bounds
                    x, y = (left + right) // 2, (top + bottom) // 2
                    await self._adb("shell", "input", "tap", str(x), str(y))
                    return
            except Exception as exc:
                logger.debug("layout_apply_fallback: %s", exc)
        await self._adb("shell", "input", "tap", str(self.apply_button_coords[0]), str(self.apply_button_coords[1]))

    async def _verify_mock_location_registered(self) -> None:
        """Verify FakeTraveler MockedLocationService or mock provider is active."""
        if self._use_layout:
            try:
                obs = await self.bridge.layout()
                node = obs.require_unique(resource_id=f"{LOCATION_PACKAGE}:id/button_applyStop")
                if node.text == "Stop":
                    return
            except Exception:
                pass
        services_out = await self._adb("shell", "dumpsys", "activity", "services", LOCATION_PACKAGE)
        if "MockedLocationService" in services_out:
            return
        loc_out = await self._adb("shell", "dumpsys", "location")
        if "mock" in loc_out.lower() or LOCATION_PACKAGE in loc_out:
            return
        raise BridgeError("mock_location_not_registered")

    async def apply_location(self, lat: float, lon: float, altitude: float = 1200.0) -> None:
        """Send geo intent to FakeTraveler, trigger Apply, and verify mock location is registered."""
        self._validate_coordinates(lat, lon, altitude)
        await self.verify_device_ready()
        logger.info("applying_location lat=%.6f lon=%.6f altitude=%.1f", lat, lon, altitude)
        # 1. Send geo:{lat},{lon} intent
        await self._adb(
            "shell",
            "am",
            "start",
            "-a",
            "android.intent.action.VIEW",
            "-d",
            f"geo:{lat},{lon}",
            f"{LOCATION_PACKAGE}/.MainActivity",
        )
        await asyncio.sleep(0.5)
        # 2. Trigger apply button
        await self._trigger_apply_action()
        await asyncio.sleep(0.5)
        # 3. Verify mock location registration
        await self._verify_mock_location_registered()

    async def stop_location_mock(self) -> None:
        """Stop mock location provider in FakeTraveler."""
        self._require_enabled()
        logger.info("stopping_location_mock")
        await self._adb("shell", "am", "force-stop", LOCATION_PACKAGE)

    async def launch_transport_app(self) -> None:
        """Launch the official UTCMS transport application (com.baarnameshahri)."""
        await self.verify_device_ready()
        logger.info("launching_transport_app package=%s", TARGET_PACKAGE)
        await self._adb("shell", "am", "start", "-n", f"{TARGET_PACKAGE}/.MainActivity")

    async def _perform_transport_action(self, action: str, doc_no: str) -> dict[str, Any]:
        """Send action intent to the transport app and check response."""
        output = await self._adb(
            "shell",
            "am",
            "start",
            "-n",
            f"{TARGET_PACKAGE}/.MainActivity",
            "--es",
            "action",
            f"{action}_shipping",
            "--es",
            "doc_no",
            doc_no,
        )
        if "error" in output.lower():
            raise BridgeError("transport_action_failed")
        return {"action": action, "doc_no": doc_no, "result": "ok"}

    async def start_shipping(
        self,
        doc_no: str,
        origin_lat: float,
        origin_lon: float,
        *,
        altitude: float = 1200.0,
        raise_on_error: bool = False,
    ) -> dict[str, Any]:
        """Start shipping flow: validate coordinates, apply mock origin location, and launch app."""
        if not doc_no or not isinstance(doc_no, str) or not doc_no.strip():
            raise ValueError("doc_no must be a non-empty string")
        self._validate_coordinates(origin_lat, origin_lon, altitude)
        await self.verify_device_ready()

        sanitized_doc = str(doc_no).strip()
        logger.info("start_shipping doc_no=%s", sanitized_doc)
        try:
            await self.apply_location(origin_lat, origin_lon, altitude=altitude)
            await self.launch_transport_app()
            action_res = await self._perform_transport_action("start", sanitized_doc)
            return {
                "status": "started",
                "doc_no": sanitized_doc,
                "origin_lat": origin_lat,
                "origin_lon": origin_lon,
                "altitude": altitude,
                "action_result": action_res,
                "timestamp": datetime.now(UTC).isoformat(),
            }
        except BridgeError as exc:
            if raise_on_error:
                raise
            logger.warning("start_shipping_failed doc_no=%s reason=%s", sanitized_doc, exc)
            return {
                "status": "error",
                "reason": str(exc),
                "doc_no": sanitized_doc,
            }

    async def finish_shipping(
        self,
        doc_no: str,
        dest_lat: float,
        dest_lon: float,
        *,
        altitude: float = 1200.0,
        raise_on_error: bool = False,
    ) -> dict[str, Any]:
        """Finish shipping flow: validate coordinates, apply mock dest location, complete app action, and stop mock."""
        if not doc_no or not isinstance(doc_no, str) or not doc_no.strip():
            raise ValueError("doc_no must be a non-empty string")
        self._validate_coordinates(dest_lat, dest_lon, altitude)
        await self.verify_device_ready()

        sanitized_doc = str(doc_no).strip()
        logger.info("finish_shipping doc_no=%s", sanitized_doc)
        try:
            await self.apply_location(dest_lat, dest_lon, altitude=altitude)
            await self.launch_transport_app()
            action_res = await self._perform_transport_action("finish", sanitized_doc)
            await self.stop_location_mock()
            return {
                "status": "delivered",
                "finished": True,
                "doc_no": sanitized_doc,
                "dest_lat": dest_lat,
                "dest_lon": dest_lon,
                "altitude": altitude,
                "mock_stopped": True,
                "action_result": action_res,
                "timestamp": datetime.now(UTC).isoformat(),
            }
        except BridgeError as exc:
            if raise_on_error:
                raise
            logger.warning("finish_shipping_failed doc_no=%s reason=%s", sanitized_doc, exc)
            return {
                "status": "error",
                "reason": str(exc),
                "doc_no": sanitized_doc,
            }

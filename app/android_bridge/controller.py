"""Android Shipping Controller for virtual Android / FakeTraveler integration.

Orchestrates location mocking with FakeTraveler and shipping lifecycle in
the official UTCMS transport application (com.baarnameshahri).
"""

from __future__ import annotations

import asyncio
import logging
import math
import time
from datetime import datetime, timedelta

try:
    from datetime import UTC
except ImportError:
    from datetime import timezone

    UTC = timezone.utc  # noqa: UP017
from typing import Any

from app.android_bridge.client import (
    ANDROID_DEVICE_MUTATION_LOCK_KEY,
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
        apply_attempts: int = 3,
        apply_retry_delay: float = 1.0,
        apply_verify_timeout: float = 5.0,
        apply_poll_interval: float = 0.5,
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

        if not isinstance(apply_attempts, int) or isinstance(apply_attempts, bool) or apply_attempts < 1:
            raise ValueError("apply_attempts must be an integer >= 1")
        for name, value in (
            ("apply_retry_delay", apply_retry_delay),
            ("apply_verify_timeout", apply_verify_timeout),
            ("apply_poll_interval", apply_poll_interval),
        ):
            if not isinstance(value, (int, float)) or not math.isfinite(value) or not 0 < float(value) <= 300:
                raise ValueError(f"{name} must be a finite number in (0, 300] seconds")
        self.apply_attempts = apply_attempts
        self.apply_retry_delay = float(apply_retry_delay)
        self.apply_verify_timeout = float(apply_verify_timeout)
        self.apply_poll_interval = float(apply_poll_interval)

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
        if (
            isinstance(lat, bool)
            or not isinstance(lat, (int, float))
            or not math.isfinite(lat)
            or not -90.0 <= float(lat) <= 90.0
        ):
            raise ValueError(f"Latitude must be a finite number between -90 and 90, got: {lat}")
        if (
            isinstance(lon, bool)
            or not isinstance(lon, (int, float))
            or not math.isfinite(lon)
            or not -180.0 <= float(lon) <= 180.0
        ):
            raise ValueError(f"Longitude must be a finite number between -180 and 180, got: {lon}")
        if isinstance(altitude, bool) or not isinstance(altitude, (int, float)) or not math.isfinite(altitude):
            raise ValueError(f"Altitude must be a finite number, got: {altitude}")

    async def _read_apply_button_state(self) -> str | None:
        """Read the FakeTraveler Apply/Stop toggle state from the layout dump.

        Returns ``"apply"`` when the button shows Apply (a tap is needed),
        ``"stop"`` when it shows Stop (the provider is already active), or
        ``None`` when the state cannot be determined — the caller must then
        fail closed instead of tapping blindly.
        """
        try:
            obs = await self.bridge.layout()
            node = obs.require_unique(resource_id=f"{LOCATION_PACKAGE}:id/button_applyStop")
        except Exception as exc:
            logger.debug("apply_button_state_unreadable: %s", exc)
            return None
        text = (node.text or "").strip().lower()
        if text == "stop":
            return "stop"
        if text == "apply":
            return "apply"
        logger.warning("apply_button_unexpected_text text=%r", node.text)
        return None

    async def _trigger_apply_action(self) -> None:
        """Tap the Apply button at its layout-reported center.

        Must only be called after :meth:`_read_apply_button_state` returned
        ``"apply"``. There is deliberately no coordinate fallback: tapping
        hard-coded coordinates on a toggle button is a blind click that can
        turn the provider off instead of on.

        The layout is re-read immediately before the tap and the button text
        is re-validated: if the toggle flipped to Stop between the state read
        and the tap, the tap is aborted instead of disabling the provider.
        """
        try:
            obs = await self.bridge.layout()
            node = obs.require_unique(resource_id=f"{LOCATION_PACKAGE}:id/button_applyStop")
        except Exception as exc:
            raise BridgeError("apply_button_lost") from exc
        if node.bounds is None:
            raise BridgeError("apply_button_unusable")
        if (node.text or "").strip().lower() != "apply":
            raise BridgeError("apply_button_state_changed")
        left, top, right, bottom = node.bounds
        x, y = (left + right) // 2, (top + bottom) // 2
        await self._adb("shell", "input", "tap", str(x), str(y))

    async def _verify_mock_location_registered(self) -> None:
        """Verify FakeTraveler MockedLocationService or mock provider is active."""
        try:
            obs = await self.bridge.layout()
            node = obs.require_unique(resource_id=f"{LOCATION_PACKAGE}:id/button_applyStop")
            if node.text == "Stop":
                return
        except Exception as exc:
            logger.debug("mock_location_fast_path_check_failed: %s", exc)
        services_out = await self._adb("shell", "dumpsys", "activity", "services", LOCATION_PACKAGE)
        if "MockedLocationService" in services_out:
            return
        loc_out = await self._adb("shell", "dumpsys", "location")
        if "mock" in loc_out.lower() or LOCATION_PACKAGE in loc_out:
            return
        raise BridgeError("mock_location_not_registered")

    async def _wait_until_mock_registered(self) -> None:
        """Poll mock-registration verification until it succeeds or the timeout expires.

        Replaces fixed sleeps with bounded polling: FakeTraveler's
        MockedLocationService may take a moment to appear after the Apply tap,
        and a single immediate check would report a false negative under load.
        """
        deadline = time.monotonic() + self.apply_verify_timeout
        while True:
            try:
                await self._verify_mock_location_registered()
                return
            except BridgeError:
                if time.monotonic() >= deadline:
                    raise
                await asyncio.sleep(self.apply_poll_interval)

    async def apply_location(self, lat: float, lon: float, altitude: float = 1200.0) -> None:
        """Send geo intent to FakeTraveler, trigger Apply, and verify mock location is registered.

        The Apply button is an Apply/Stop *toggle*: its state is read before
        every tap, so a retry never taps a button that already shows Stop
        (which would disable the provider). Taps happen only when the state
        is definitively "apply"; an unreadable or unexpected state fails
        closed without any tap. The final attempt's error propagates
        unchanged.

        Device serialization (batch-B fix B3): the single Redroid/FakeTraveler
        device is shared across jobs, so every apply is additionally
        serialized through the device-wide Redis lock
        (``ANDROID_DEVICE_MUTATION_LOCK_KEY``) on top of the per-job lock in
        shipping_gps.py. Fail-closed: an unavailable or busy lock raises
        BridgeError — the device is never mutated without the lock held.
        """
        self._validate_coordinates(lat, lon, altitude)
        self._require_enabled()
        # Lazy imports: rpa_runtime_service must never be imported at module
        # load (it pulls config/redis/contracts); the enabled check above keeps
        # a disabled bridge failing with bridge_disabled, not a lock error.
        from app.core.config import utcms_config
        from app.services.rpa_runtime_service import rpa_runtime

        try:
            acquired = await rpa_runtime.acquire_lock(
                ANDROID_DEVICE_MUTATION_LOCK_KEY, max(int(utcms_config.RPA_LOCK_TTL_SECONDS), 120)
            )
        except Exception as exc:
            logger.error("android_device_lock_unavailable", exc_info=True)
            raise BridgeError("android_device_lock_unavailable") from exc
        if not acquired:
            raise BridgeError("android_device_lock_busy")
        try:
            await self._apply_location_locked(lat, lon, altitude)
        finally:
            await rpa_runtime.release_lock(ANDROID_DEVICE_MUTATION_LOCK_KEY)

    async def _apply_location_locked(self, lat: float, lon: float, altitude: float = 1200.0) -> None:
        """Apply once, then prove a fresh matching mock fix while holding the device lease."""
        from app.travel.android_observer import AdbLocationObserver
        from app.travel.geometry import haversine_km

        await self.verify_device_ready()
        for package in (LOCATION_PACKAGE, TARGET_PACKAGE):
            if not (await self._adb("shell", "pm", "path", package)).startswith("package:"):
                raise BridgeError("required_android_package_missing")
        # Foreground FakeTraveler first so the toggle can be read before filling.
        await self._adb("shell", "am", "start", "-n", f"{LOCATION_PACKAGE}/.MainActivity")
        state = await self._read_apply_button_state()
        if state == "stop":
            observation = await self.bridge.layout()
            node = observation.require_unique(resource_id=f"{LOCATION_PACKAGE}:id/button_applyStop")
            if (node.text or "").lower() != "stop" or node.bounds is None:
                raise BridgeError("apply_button_state_changed")
            left, top, right, bottom = node.bounds
            await self._adb("shell", "input", "tap", str((left + right) // 2), str((top + bottom) // 2))
            if await self._read_apply_button_state() != "apply":
                raise BridgeError("stop_button_postcondition_failed")
        elif state != "apply":
            raise BridgeError("apply_button_state_unknown")
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
        applied_at = datetime.now(UTC)
        await self._trigger_apply_action()
        observer = AdbLocationObserver(self.config, bridge=self.bridge, runner=self._runner)
        deadline = time.monotonic() + self.apply_verify_timeout
        while True:
            try:
                fix = await observer.observe()
                if not fix.is_mock or fix.serial != self.config.serial:
                    raise BridgeError("location_readback_invalid")
                if fix.sampled_at < applied_at - timedelta(seconds=1.5):
                    raise BridgeError("location_readback_stale")
                if haversine_km(fix.latitude, fix.longitude, lat, lon) > 0.005:
                    raise BridgeError("location_readback_mismatch")
                return
            except BridgeError:
                if time.monotonic() >= deadline:
                    raise
                await asyncio.sleep(min(self.apply_poll_interval, max(0.0, deadline - time.monotonic())))

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
        """The APK has no verified shipping intent contract or result read-back."""
        raise BridgeError("android_shipping_action_contract_unverified")

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
            action_res = await self._perform_transport_action("finish", sanitized_doc)
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

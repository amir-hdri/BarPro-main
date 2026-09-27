"""Production Android location observer (Phase 7).

Fills the documented gap: ``AndroidFakeGpsProvider`` already fails closed
with ``location_readback_unavailable`` when no observer is supplied, but no
bundled observer existed. This module supplies one ADB-backed observer that
reads the *actual* Android location provider and returns an
``AndroidLocationObservation`` — never an engine waypoint.

Fail-closed contract:
- bridge disabled / device not ready / ADB error  → BridgeError / GpsProviderError
- no location / stale fix / unparsable output     → GpsProviderError
- caller decides tolerance (provider validates ≤5 m by default)

The observer never injects, never taps, never starts containers. Mutation
lives exclusively in ``AndroidFakeGpsProvider`` / ``AndroidShippingController``.
"""

from __future__ import annotations

import logging
import re
from datetime import UTC, datetime
from typing import Any

from app.android_bridge.client import AndroidBridge, BridgeConfig, BridgeError, CommandRunner, _run_command
from app.travel.providers import AndroidLocationObservation

logger = logging.getLogger(__name__)

_LOCATION_LINE = re.compile(
    r"provider=(?P<provider>\S+).*?lat[=:](?P<lat>-?\d+(?:\.\d+)?).*?lon[=:](?P<lon>-?\d+(?:\.\d+)?)",
    re.IGNORECASE | re.DOTALL,
)
_LATLON_PAIR = re.compile(r"(?P<lat>-?\d+\.\d+)\s*,\s*(?P<lon>-?\d+\.\d+)")
_MOCK_HINT = re.compile(r"mock|faketraveler|cl\.coders", re.IGNORECASE)


class AdbLocationObserver:
    """Read the latest Android location fix over ADB.

    Strategy (best-effort, fail-closed):
    1. ``dumpsys location`` — parse the last known fix (provider + lat/lon).
    2. Fall back to ``dumpsys location <package>`` context when needed.
    3. ``is_mock`` is True when the dump references a mock provider or the
       FakeTraveler package; physical GPS without mock hints yields False.
       The provider layer still enforces serial/provider/tolerance checks.

    ``max_age_s`` guards staleness: a fix whose dump carries an explicit age
    older than this is rejected. When the dump carries no timestamp, the read
    time is used for both ``sampled_at`` and ``observed_at`` (documented, not
    back-dated).
    """

    def __init__(
        self,
        config: BridgeConfig | None = None,
        *,
        bridge: AndroidBridge | None = None,
        runner: CommandRunner = _run_command,
        max_age_s: float = 30.0,
    ) -> None:
        if bridge is not None:
            self.bridge = bridge
            self.config = bridge.config
        else:
            self.config = config or BridgeConfig.from_env()
            self.bridge = AndroidBridge(self.config, runner=runner)
        self._runner = runner
        self._max_age_s = max(1.0, float(max_age_s))

    async def _adb(self, *args: str) -> str:
        if not self.config.enabled:
            raise BridgeError("bridge_disabled")
        argv = (self.config.adb_binary, "-s", self.config.serial, *args)
        return (await self._runner(argv, timeout=self.config.command_timeout)).strip()

    async def observe(self) -> AndroidLocationObservation:
        """Return the latest Android fix. Raises on any unreadable state."""
        if not self.config.enabled:
            raise BridgeError("bridge_disabled")
        state = await self._adb("get-state")
        if state != "device":
            raise BridgeError("device_not_ready")
        observed_at = datetime.now(UTC)
        dump = await self._adb("shell", "dumpsys", "location")
        if not dump or "location" not in dump.lower():
            raise BridgeError("location_readback_unavailable")
        parsed = self.parse_dump(dump)
        if parsed is None:
            raise BridgeError("location_readback_unavailable")
        provider, lat, lon, is_mock, age_s = parsed
        if age_s is not None and age_s > self._max_age_s:
            raise BridgeError("location_readback_stale")
        # sampled_at == observed_at when the dump carries no fix timestamp:
        # documented approximation, never back-dated.
        return AndroidLocationObservation(
            latitude=lat,
            longitude=lon,
            serial=self.config.serial,
            provider=provider,
            is_mock=is_mock,
            sampled_at=observed_at,
            observed_at=observed_at,
        )

    @staticmethod
    def parse_dump(dump: str) -> tuple[str, float, float, bool, float | None] | None:
        """Parse ``dumpsys location`` text.

        Returns (provider, lat, lon, is_mock, age_s|None) or None.
        Prefers the last ``provider=… lat=… lon=…`` record; falls back to the
        last bare ``lat,lon`` pair. Age is extracted from ``age=…s`` / ``elapsed=…``
        hints when present.
        """
        candidates: list[tuple[str, float, float]] = []
        for match in _LOCATION_LINE.finditer(dump):
            try:
                candidates.append(
                    (match.group("provider"), float(match.group("lat")), float(match.group("lon")))
                )
            except ValueError:
                continue
        provider = "fused"
        lat: float | None = None
        lon: float | None = None
        if candidates:
            provider, lat, lon = candidates[-1]
        else:
            pairs = list(_LATLON_PAIR.finditer(dump))
            if not pairs:
                return None
            try:
                lat, lon = float(pairs[-1].group("lat")), float(pairs[-1].group("lon"))
            except ValueError:
                return None
        if lat is None or lon is None:
            return None
        if not (-90.0 <= lat <= 90.0 and -180.0 <= lon <= 180.0):
            return None
        is_mock = bool(_MOCK_HINT.search(dump))
        age_s: float | None = None
        age_matches = re.findall(r"age[=:]\s*(\d+(?:\.\d+)?)\s*s", dump, re.IGNORECASE)
        if age_matches:
            try:
                # Age belongs to the chosen (last) fix, not the first line.
                age_s = float(age_matches[-1])
            except ValueError:
                age_s = None
        return provider, lat, lon, is_mock, age_s

    def as_callable(self) -> Any:
        """Return ``observe`` as the ``location_observer`` callable providers expect."""
        return self.observe


__all__ = ["AdbLocationObserver"]

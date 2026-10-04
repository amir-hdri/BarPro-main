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
from datetime import UTC, datetime, timedelta
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
# A stock ``dumpsys location`` ALWAYS prints a "Mock Providers:" section header,
# even when nothing is mocked, so the bare word "mock" must never count as a
# dump-level signal (it would mark every physical fix as mocked and silently
# disable the fail-closed anchor gates). Only an explicitly *active* marker --
# AOSP's "Mocked by <pkg>" line or the FakeTraveler package itself -- qualifies.
_MOCK_ACTIVE_HINT = re.compile(r"mocked\s*by|faketraveler|cl\.coders", re.IGNORECASE)
_AGE_TOKEN = re.compile(r"age[=:]\s*(?P<age>\d+(?:\.\d+)?)\s*s", re.IGNORECASE)
# ``Location.toString()`` on API 29+ prints the fix's elapsed-realtime stamp as
# an Android ``TimeUtils.formatDuration`` value, e.g. "et=+1s045ms", "et=+12m3s".
# It is a time-since-boot, NOT an age: the age is (device uptime - et).
_ET_TOKEN = re.compile(r"\bet=(?P<sign>[+-]?)(?P<body>[0-9][0-9dhmsu.]*)", re.IGNORECASE)
_DURATION_PART = re.compile(r"(?P<value>\d+(?:\.\d+)?)(?P<unit>ms|s|m|h|d)", re.IGNORECASE)


def _parse_android_duration(body: str) -> float | None:
    """Parse an Android ``TimeUtils.formatDuration`` body into seconds.

    Accepts the concatenated-component form ("1h2m3s045ms"). Returns ``None``
    when nothing parses, so callers can fail closed rather than assume zero.
    """
    scale = {"ms": 0.001, "s": 1.0, "m": 60.0, "h": 3600.0, "d": 86400.0}
    total = 0.0
    matched = False
    for part in _DURATION_PART.finditer(body):
        total += float(part.group("value")) * scale[part.group("unit").lower()]
        matched = True
    return total if matched else None


def _parse_uptime_seconds(raw: str) -> float | None:
    """Parse ``/proc/uptime`` ("<uptime> <idle>") into seconds since boot."""
    for token in (raw or "").split():
        try:
            return float(token)
        except ValueError:
            continue
    return None


class AdbLocationObserver:
    """Read the latest Android location fix over ADB.

    Strategy (best-effort, fail-closed):
    1. ``dumpsys location`` — parse the last known fix (provider + lat/lon).
    2. Fall back to ``dumpsys location <package>`` context when needed.
    3. ``is_mock`` is True when the fix line itself carries a mock marker, or
       the dump carries an *active* mock marker ("Mocked by <pkg>" / the
       FakeTraveler package). The stock "Mock Providers:" section header does
       NOT count — it is present even when nothing is mocked. The provider
       layer still enforces serial/provider/tolerance checks.

    ``max_age_s`` guards staleness. The fix age comes from an explicit
    ``age=…s`` token, or from the ``et=`` elapsed-realtime stamp that
    ``Location.toString()`` prints on API 29+ resolved against the device's
    ``/proc/uptime``. ``sampled_at`` is back-dated by that age. A fix whose age
    cannot be established at all is **rejected** rather than assumed fresh, so
    a stale read can never be mistaken for proof that a mutation landed.
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
        read_started_at = datetime.now(UTC)
        dump = await self._adb("shell", "dumpsys", "location")
        if not dump or "location" not in dump.lower():
            raise BridgeError("location_readback_unavailable")
        parsed = self.parse_dump(dump)
        if parsed is None:
            raise BridgeError("location_readback_unavailable")
        if parsed[4] is None and _ET_TOKEN.search(dump):
            # Real AOSP/redroid dumps stamp the fix with an elapsed-realtime
            # ``et=`` value instead of an ``age=`` token. Resolve it against the
            # device's seconds-since-boot so the staleness gate below still has
            # a real age to check (one extra ADB read, only on this path).
            uptime_s = _parse_uptime_seconds(await self._adb("shell", "cat", "/proc/uptime"))
            if uptime_s is not None:
                parsed = self.parse_dump(dump, uptime_s=uptime_s) or parsed
        provider, lat, lon, is_mock, age_s = parsed
        if age_s is None:
            # Fail closed: without a provable fix timestamp we cannot claim the
            # read-back is fresh, and a stale fix would be accepted as proof.
            raise BridgeError("location_fix_timestamp_missing")
        if age_s > self._max_age_s:
            raise BridgeError("location_readback_stale")
        return AndroidLocationObservation(
            latitude=lat,
            longitude=lon,
            serial=self.config.serial,
            provider=provider,
            is_mock=is_mock,
            sampled_at=read_started_at - timedelta(seconds=age_s),
            observed_at=datetime.now(UTC),
        )

    @staticmethod
    def parse_dump(dump: str, *, uptime_s: float | None = None) -> tuple[str, float, float, bool, float | None] | None:
        """Parse ``dumpsys location`` text.

        Returns (provider, lat, lon, is_mock, age_s|None) or None.
        Prefers the last ``provider=… lat=… lon=…`` record; falls back to the
        last bare ``lat,lon`` pair.

        Age resolution, in order:
        1. An explicit ``age=…s`` token on the fix line.
        2. The ``et=`` elapsed-realtime stamp that ``Location.toString()``
           prints on API 29+ (e.g. ``et=+1s045ms``), converted to an age with
           ``uptime_s`` (seconds since boot, from ``/proc/uptime``). Without
           ``uptime_s`` an ``et=`` stamp cannot yield an age and ``None`` is
           returned, so the caller fails closed rather than assuming freshness.
        """
        candidates: list[tuple[str, float, float, bool, float | None]] = []
        # A genuine mock marker may appear on its OWN line (AOSP prints
        # "Mocked by <pkg>" outside the fix line), so a dump-level hint must
        # also count. It must NOT match the bare word "mock", because a stock
        # dump always contains a "Mock Providers:" section header even when
        # nothing is mocked — that would mark every physical fix as mocked and
        # silently disable the fail-closed anchor read-back gates.
        dump_mock = bool(_MOCK_ACTIVE_HINT.search(dump))
        for line in dump.splitlines():
            # Coordinates, mock marker and age must come from the same fix.
            match = _LOCATION_LINE.search(line)
            if match:
                provider = match.group("provider")
                lat, lon = float(match.group("lat")), float(match.group("lon"))
            else:
                pair = _LATLON_PAIR.search(line)
                if pair is None or "Location[" not in line:
                    continue
                provider_match = re.search(r"Location\[(\w+)", line)
                provider = provider_match.group(1) if provider_match else "unknown"
                lat, lon = float(pair.group("lat")), float(pair.group("lon"))
            if not (-90 <= lat <= 90 and -180 <= lon <= 180):
                continue
            age_match = _AGE_TOKEN.search(line)
            age_s = float(age_match.group("age")) if age_match else None
            if age_s is None and uptime_s is not None:
                et_match = _ET_TOKEN.search(line)
                if et_match and et_match.group("sign") != "-":
                    et_s = _parse_android_duration(et_match.group("body"))
                    if et_s is not None:
                        # Clamp: a fix stamped slightly ahead of our uptime read
                        # (clock granularity) is fresh, not negatively aged.
                        age_s = max(0.0, uptime_s - et_s)
            candidates.append((provider, lat, lon, bool(_MOCK_HINT.search(line)) or dump_mock, age_s))
        return candidates[-1] if candidates else None

    def as_callable(self) -> Any:
        """Return ``observe`` as the ``location_observer`` callable providers expect."""
        return self.observe


__all__ = ["AdbLocationObserver"]

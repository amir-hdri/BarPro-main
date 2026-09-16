"""Fake-GPS providers: the only layer allowed to touch a device (PHASE 22-23).

A provider receives a coordinate the engine already computed and transports it
somewhere. It never computes route state, never decides where the vehicle
should be next, and never feeds anything back into the engine. The dependency
arrow is one-way::

    TravelEngine -> FakeGpsProvider -> Android / Redroid / (test sink)

Three implementations ship here:

``RecordingGpsProvider``
    In-memory sink. Lets the whole travel pipeline run in tests and in the
    headless engine verification without a device.

``AndroidFakeGpsProvider``
    Drives ``cl.coders.faketraveler`` over ADB on a physical or emulated
    device, following the applyIntentOrDefault/Apply-button protocol documented
    in ``docs/ANDROID_CLIENT_IMPLEMENTATION_PLAN.md``.

``RedroidFakeGpsProvider``
    The same ADB protocol against a Redroid container.

Provenance is carried explicitly on every dispatch. CRITICAL_RULES requires
that a planned point, an Android-observed sample and a physically measured GPS
fix are never reported as one another, so a dispatch says which it is, and a
recorded point never claims to be a device observation.

Mutation lives here rather than in :class:`app.android_bridge.client.AndroidBridge`
on purpose: the bridge is documented as observation-only, and confining taps to
an explicitly-enabled provider keeps that guarantee intact.
"""

from __future__ import annotations

import asyncio
import logging
import re
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from app.android_bridge.client import (
    LOCATION_PACKAGE,
    AndroidBridge,
    BridgeConfig,
    BridgeError,
    CommandRunner,
    _run_command,
)
from app.travel.engine import TravelSample

__all__ = [
    "AndroidFakeGpsProvider",
    "FakeGpsProvider",
    "GpsDispatch",
    "GpsProviderError",
    "PROVENANCE_ANDROID_APPLIED",
    "PROVENANCE_SIMULATED",
    "RecordingGpsProvider",
    "RedroidFakeGpsProvider",
    "build_gps_provider",
]

logger = logging.getLogger(__name__)

#: The engine's planned point. Not a measurement, not a device observation.
PROVENANCE_SIMULATED = "simulated_planned"
#: FakeTraveler acknowledged applying the point. Still not a physical fix.
PROVENANCE_ANDROID_APPLIED = "android_faketraveler_applied"

_FAKETRAVELER_ACTIVITY = f"{LOCATION_PACKAGE}/.MainActivity"
_APPLY_STOP_BUTTON = f"{LOCATION_PACKAGE}:id/button_applyStop"
#: Button labels FakeTraveler toggles between. Matched exactly, never guessed.
_APPLY_LABELS = frozenset({"Apply"})
_STOP_LABELS = frozenset({"Stop"})


class GpsProviderError(RuntimeError):
    """A provider could not deliver a coordinate. Reason strings stay sanitized."""


@dataclass(frozen=True, slots=True)
class GpsDispatch:
    """Outcome of handing one coordinate to a provider."""

    accepted: bool
    provider: str
    provenance: str
    latitude: float
    longitude: float
    dispatched_at: datetime
    latency_ms: float
    reason: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "accepted": self.accepted,
            "provider": self.provider,
            "provenance": self.provenance,
            "lat": round(self.latitude, 7),
            "lon": round(self.longitude, 7),
            "dispatched_at": self.dispatched_at.isoformat(),
            "latency_ms": round(self.latency_ms, 3),
            "reason": self.reason,
        }


class FakeGpsProvider(ABC):
    """Transport a coordinate to a location sink. Computes nothing."""

    #: Stable identifier used in events, logs and the provider factory.
    name: str = "abstract"
    #: What a successful dispatch through this provider actually proves.
    provenance: str = PROVENANCE_SIMULATED

    @abstractmethod
    async def start(self) -> None:
        """Prepare the sink. Must fail closed if it cannot be used."""

    @abstractmethod
    async def publish(self, sample: TravelSample) -> GpsDispatch:
        """Deliver one coordinate. Never raises for an expected failure."""

    @abstractmethod
    async def stop(self) -> None:
        """Release the sink. Safe to call when start() failed or never ran."""

    async def __aenter__(self) -> FakeGpsProvider:
        await self.start()
        return self

    async def __aexit__(self, *_exc: object) -> None:
        await self.stop()


class RecordingGpsProvider(FakeGpsProvider):
    """In-memory sink for tests and headless verification (PHASE 22).

    Records exactly what the engine produced, labelled ``simulated_planned``.
    A run against this provider proves the engine is correct; it proves nothing
    whatsoever about Android or UTCMS, and it must never be reported as if it
    did.
    """

    name = "recording"
    provenance = PROVENANCE_SIMULATED

    def __init__(self, *, fail_after: int | None = None, capacity: int = 200_000) -> None:
        self._dispatches: list[GpsDispatch] = []
        self._samples: list[TravelSample] = []
        self._fail_after = fail_after
        self._capacity = capacity
        self._started = False

    async def start(self) -> None:
        self._started = True

    async def publish(self, sample: TravelSample) -> GpsDispatch:
        if not self._started:
            raise GpsProviderError("provider_not_started")
        began = time.perf_counter()
        # `fail_after` exists for the PHASE 36 injection tests: it simulates a
        # sink that dies partway through a travel.
        failed = self._fail_after is not None and len(self._dispatches) >= self._fail_after
        dispatch = GpsDispatch(
            accepted=not failed,
            provider=self.name,
            provenance=self.provenance,
            latitude=sample.latitude,
            longitude=sample.longitude,
            dispatched_at=sample.timestamp,
            latency_ms=(time.perf_counter() - began) * 1000.0,
            reason="" if not failed else "injected_failure",
        )
        if len(self._dispatches) < self._capacity:
            self._dispatches.append(dispatch)
            self._samples.append(sample)
        return dispatch

    async def stop(self) -> None:
        self._started = False

    @property
    def dispatches(self) -> list[GpsDispatch]:
        return list(self._dispatches)

    @property
    def samples(self) -> list[TravelSample]:
        """Samples as emitted, for the PHASE 33/34 verification tables."""
        return list(self._samples)


@dataclass(frozen=True)
class AndroidGpsConfig:
    """Injection settings, separate from the observation-only bridge config."""

    enabled: bool = False
    serial: str = ""
    adb_binary: str = "adb"
    command_timeout: float = 10.0
    #: Verify the Apply/Stop button state before every click. Blind re-clicks
    #: toggle the button and would silently kill the mock provider.
    verify_button_state: bool = True

    def __post_init__(self) -> None:
        if self.enabled and not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.:\-\[\]]{0,254}", self.serial):
            raise ValueError("An explicit device serial is required to inject GPS")
        if not 0 < self.command_timeout <= 300:
            raise ValueError("command_timeout must be in (0, 300] seconds")


class AndroidFakeGpsProvider(FakeGpsProvider):
    """Drive FakeTraveler over ADB.

    FakeTraveler's intent handler only *fills the form*; the mock provider
    starts when the Apply button is pressed, and the same button becomes Stop
    while it runs. Moving the vehicle therefore takes Stop -> intent -> Apply
    per update, and each click is preceded by a layout read so a toggle can
    never be applied to the wrong state.

    Disabled by default and fails closed: if the device, the package or the
    button is not where it should be, the dispatch is rejected. It never falls
    back to a recording sink, because a silent downgrade would make a travel
    look injected when nothing reached the device.
    """

    name = "android"
    provenance = PROVENANCE_ANDROID_APPLIED

    def __init__(
        self,
        config: AndroidGpsConfig,
        *,
        bridge: AndroidBridge | None = None,
        runner: CommandRunner = _run_command,
        min_interval_s: float = 1.0,
    ) -> None:
        self._config = config
        self._runner = runner
        self._min_interval_s = max(0.0, min_interval_s)
        self._bridge = bridge or AndroidBridge(
            BridgeConfig(
                enabled=config.enabled,
                serial=config.serial,
                # Injection does not assert anything about egress; the proxy
                # check belongs to the observation bridge, not here.
                expected_proxy="127.0.0.1:1",
                adb_binary=config.adb_binary,
                command_timeout=config.command_timeout,
            )
        )
        self._started = False
        self._applied = False
        self._last_publish = 0.0
        self._lock = asyncio.Lock()

    async def _adb(self, *args: str) -> str:
        argv = (self._config.adb_binary, "-s", self._config.serial, *args)
        return (await self._runner(argv, timeout=self._config.command_timeout)).strip()

    async def start(self) -> None:
        if not self._config.enabled:
            raise GpsProviderError("gps_injection_disabled")
        if await self._adb("get-state") != "device":
            raise GpsProviderError("device_not_ready")
        package = await self._adb("shell", "pm", "path", LOCATION_PACKAGE)
        if not package.startswith("package:"):
            raise GpsProviderError("faketraveler_missing")
        self._started = True
        self._applied = False

    async def publish(self, sample: TravelSample) -> GpsDispatch:
        began = time.perf_counter()
        if not self._started:
            return self._reject(sample, began, "provider_not_started")

        # Serialise: two overlapping Stop/Apply sequences would desynchronise
        # the toggle and leave the mock provider off.
        async with self._lock:
            now = time.monotonic()
            if self._min_interval_s and now - self._last_publish < self._min_interval_s:
                return self._reject(sample, began, "rate_limited")
            try:
                await self._apply_coordinate(sample.latitude, sample.longitude)
            except (BridgeError, GpsProviderError) as exc:
                return self._reject(sample, began, str(exc) or "injection_failed")
            self._last_publish = time.monotonic()

        return GpsDispatch(
            accepted=True,
            provider=self.name,
            provenance=self.provenance,
            latitude=sample.latitude,
            longitude=sample.longitude,
            dispatched_at=sample.timestamp,
            latency_ms=(time.perf_counter() - began) * 1000.0,
        )

    async def _apply_coordinate(self, lat: float, lon: float) -> None:
        # 1. If the mock is running, stop it — the form is ignored while active.
        if self._applied:
            await self._click_apply_stop(expect=_STOP_LABELS)
            self._applied = False
        # 2. Fill the form via the documented VIEW/geo: intent.
        await self._adb(
            "shell",
            "am",
            "start",
            "-a",
            "android.intent.action.VIEW",
            "-d",
            f"geo:{lat:.7f},{lon:.7f}",
            _FAKETRAVELER_ACTIVITY,
        )
        # 3. Press Apply to start the mock provider at the new point.
        await self._click_apply_stop(expect=_APPLY_LABELS)
        self._applied = True

    async def _click_apply_stop(self, *, expect: frozenset[str]) -> None:
        """Tap the Apply/Stop button, refusing to click the wrong state."""
        node = None
        if self._config.verify_button_state:
            observation = await self._bridge.layout()
            node = observation.require_unique(resource_id=_APPLY_STOP_BUTTON)
            if node.text not in expect:
                raise GpsProviderError("apply_button_unexpected_state")
        if node is None or node.bounds is None:
            raise GpsProviderError("apply_button_not_locatable")
        left, top, right, bottom = node.bounds
        await self._adb("shell", "input", "tap", str((left + right) // 2), str((top + bottom) // 2))

    def _reject(self, sample: TravelSample, began: float, reason: str) -> GpsDispatch:
        logger.warning("gps_dispatch_rejected provider=%s reason=%s", self.name, reason)
        return GpsDispatch(
            accepted=False,
            provider=self.name,
            provenance=self.provenance,
            latitude=sample.latitude,
            longitude=sample.longitude,
            dispatched_at=sample.timestamp,
            latency_ms=(time.perf_counter() - began) * 1000.0,
            reason=reason,
        )

    async def stop(self) -> None:
        if self._started and self._applied:
            try:
                await self._click_apply_stop(expect=_STOP_LABELS)
            except (BridgeError, GpsProviderError):
                logger.warning("gps_provider_stop_failed provider=%s", self.name)
        self._started = False
        self._applied = False


class RedroidFakeGpsProvider(AndroidFakeGpsProvider):
    """FakeTraveler inside a Redroid container.

    The ADB protocol is identical; what differs is the container lifecycle and
    the serial (``host:port`` rather than a USB serial). Container startup is
    explicitly *not* this class's job — it connects to a serial that is already
    up, so nothing here can start a privileged container, which CRITICAL_RULES
    forbids.
    """

    name = "redroid"


def build_gps_provider(kind: str, **kwargs: Any) -> FakeGpsProvider:
    """Factory used by the worker so no call site hard-codes a provider."""
    normalised = (kind or "").strip().lower()
    if normalised in ("recording", "test", "memory"):
        return RecordingGpsProvider(**kwargs)
    if normalised == "android":
        return AndroidFakeGpsProvider(AndroidGpsConfig(**kwargs))
    if normalised == "redroid":
        return RedroidFakeGpsProvider(AndroidGpsConfig(**kwargs))
    raise ValueError(f"unknown gps provider: {kind!r}; known: recording, android, redroid")


@dataclass(slots=True)
class DispatchStats:
    """Aggregate view of a provider's dispatches, for the run report."""

    total: int = 0
    accepted: int = 0
    rejected: int = 0
    reasons: dict[str, int] = field(default_factory=dict)

    def record(self, dispatch: GpsDispatch) -> None:
        self.total += 1
        if dispatch.accepted:
            self.accepted += 1
        else:
            self.rejected += 1
            self.reasons[dispatch.reason] = self.reasons.get(dispatch.reason, 0) + 1

    def to_dict(self) -> dict[str, Any]:
        return {
            "total": self.total,
            "accepted": self.accepted,
            "rejected": self.rejected,
            "reasons": dict(self.reasons),
            "generated_at": datetime.now(UTC).isoformat(),
        }

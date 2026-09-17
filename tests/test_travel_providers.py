"""Exercise provider decisions with only the external Android I/O replaced."""

from dataclasses import replace
from datetime import UTC, datetime, timedelta

import pytest

from app.android_bridge.client import AndroidBridge, BridgeConfig
from app.travel import RouteGeometry, TravelEngine
from app.travel.providers import AndroidFakeGpsProvider, AndroidGpsConfig, AndroidLocationObservation


class AndroidIo:
    def __init__(self, *, changes_button: bool = True) -> None:
        self.label = "Apply"
        self.changes_button = changes_button
        self.taps = 0
        self.intent_at = datetime.now(UTC)

    async def __call__(self, argv: tuple[str, ...], *, timeout: float) -> str:
        if argv[0] == "android":
            return (
                '[{"resourceId":"cl.coders.faketraveler:id/button_applyStop",'
                f'"text":"{self.label}","bounds":"[0,0][100,100]","enabled":true}}]'
            )
        args = argv[3:]
        if args == ("get-state",):
            return "device"
        if args == ("shell", "pm", "path", "cl.coders.faketraveler"):
            return "package:/data/app/faketraveler/base.apk"
        if args[:3] == ("shell", "input", "tap"):
            self.taps += 1
            if self.changes_button:
                self.label = "Stop" if self.label == "Apply" else "Apply"
            return ""
        if args[:3] == ("shell", "am", "start"):
            self.intent_at = datetime.now(UTC)
            return "Starting: Intent { act=android.intent.action.VIEW dat=geo:35,51 }"
        raise AssertionError(f"Unexpected Android command: {argv}")


def provider_with_io(io: AndroidIo, **kwargs) -> AndroidFakeGpsProvider:
    bridge = AndroidBridge(BridgeConfig(enabled=True, serial="test-device", expected_proxy="127.0.0.1:3128"), runner=io)
    return AndroidFakeGpsProvider(
        AndroidGpsConfig(enabled=True, serial="test-device"), bridge=bridge, runner=io, min_interval_s=0, **kwargs
    )


def origin_sample():
    now = datetime.now(UTC)
    return TravelEngine.build(RouteGeometry.from_points([(35, 51), (35.01, 51)])).start(now=now)


@pytest.mark.asyncio
async def test_provider_without_location_observer_rejects_before_mutation() -> None:
    io = AndroidIo()
    provider = provider_with_io(io)
    await provider.start()
    dispatch = await provider.publish(origin_sample())
    assert not dispatch.accepted
    assert dispatch.provenance == "simulated_planned"
    assert dispatch.reason == "location_readback_unavailable"
    assert io.taps == 0


def observed_fix(**changes) -> AndroidLocationObservation:
    now = datetime.now(UTC)
    observation = AndroidLocationObservation(
        latitude=35, longitude=51, serial="test-device", provider="gps", is_mock=True, sampled_at=now, observed_at=now
    )
    return replace(observation, **changes)


@pytest.mark.asyncio
async def test_success_requires_and_preserves_observed_virtual_fix() -> None:
    async def observe():
        return observed_fix()

    provider = provider_with_io(AndroidIo(), location_observer=observe)
    await provider.start()
    dispatch = await provider.publish(origin_sample())
    assert dispatch.accepted
    assert dispatch.provenance == "android_faketraveler_applied"
    wire = dispatch.to_dict()
    assert wire.get("device_serial") == "test-device"
    assert wire.get("location_provider") == "gps"
    assert wire.get("observed_at") is not None
    assert wire.get("sampled_at") is not None


@pytest.mark.asyncio
async def test_noop_apply_tap_is_rejected_even_if_readback_matches() -> None:
    async def observe():
        return observed_fix()

    provider = provider_with_io(AndroidIo(changes_button=False), location_observer=observe)
    await provider.start()
    dispatch = await provider.publish(origin_sample())
    assert not dispatch.accepted
    assert dispatch.reason == "apply_button_postcondition_failed"


@pytest.mark.asyncio
async def test_fix_from_before_apply_is_not_new_location_evidence() -> None:
    io = AndroidIo()

    async def observe():
        return observed_fix(sampled_at=io.intent_at)

    provider = provider_with_io(io, location_observer=observe)
    await provider.start()
    dispatch = await provider.publish(origin_sample())
    assert not dispatch.accepted
    assert dispatch.reason == "location_readback_stale"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "changes",
    [
        {"latitude": 36},
        {"serial": "other-device"},
        {"is_mock": False},
        {"provider": ""},
        {"latitude": float("nan")},
        {"sampled_at": datetime(2020, 1, 1, tzinfo=UTC)},
        {"observed_at": datetime(2020, 1, 1, tzinfo=UTC)},
        {"sampled_at": datetime.now(UTC) + timedelta(days=1)},
    ],
)
async def test_unverified_location_is_rejected_and_never_retried_blindly(changes) -> None:
    async def observe():
        return observed_fix(**changes)

    io = AndroidIo()
    provider = provider_with_io(io, location_observer=observe)
    await provider.start()
    dispatch = await provider.publish(origin_sample())
    assert not dispatch.accepted
    assert dispatch.provenance == "simulated_planned"
    taps_before_retry = io.taps
    second = await provider.publish(origin_sample())
    assert not second.accepted
    assert second.reason == "injection_outcome_unknown"
    assert io.taps == taps_before_retry

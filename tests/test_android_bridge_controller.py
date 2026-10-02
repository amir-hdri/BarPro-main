"""Unit tests for AndroidShippingController in app/android_bridge/controller.py."""

import asyncio
import re
from dataclasses import replace
from unittest.mock import AsyncMock

import pytest

from app.android_bridge.client import (
    ANDROID_DEVICE_MUTATION_LOCK_KEY,
    LOCATION_PACKAGE,
    TARGET_PACKAGE,
    AndroidBridge,
    BridgeConfig,
    BridgeError,
    parse_layout,
)
from app.android_bridge.controller import AndroidShippingController


def config(**changes) -> BridgeConfig:
    return replace(
        BridgeConfig(
            enabled=True,
            serial="127.0.0.1:5555",
            expected_proxy="squid:3128",
        ),
        **changes,
    )


def make_mock_runner(overrides: dict[tuple[str, ...], str] | None = None) -> AsyncMock:
    """Create a stateful mock ADB runner for the controller's apply/observe flow.

    It satisfies the exact device calls the authoritative controller + observer
    make:

    * ``verify_device_ready`` → get-state / boot / proxy,
    * the fail-closed package gate → ``pm path`` for BOTH packages returns a
      ``package:`` line (missing this is why the old runner tripped
      ``required_android_package_missing`` before any button logic ran),
    * the geo VIEW intent → the applied ``geo:lat,lon`` coordinates are
      captured, and
    * ``dumpsys location`` → echoes those exact coordinates back as a fresh mock
      fix (``age=0.0s``) so ``AdbLocationObserver`` reads them back and the apply
      verification succeeds (haversine 0 ≤ 5 m, is_mock=True, fresh).

    ``overrides`` (checked first, exact prefix match) let an individual test
    force a specific response — e.g. an unreadable ``dumpsys location``.
    """
    default_handlers = {
        ("get-state",): "device\n",
        ("shell", "getprop", "sys.boot_completed"): "1\n",
        ("shell", "settings", "get", "global", "http_proxy"): "squid:3128\n",
        ("shell", "pm", "path", LOCATION_PACKAGE): f"package:/data/app/{LOCATION_PACKAGE}-1/base.apk\n",
        ("shell", "pm", "path", TARGET_PACKAGE): f"package:/data/app/{TARGET_PACKAGE}-1/base.apk\n",
        ("shell", "am", "force-stop", LOCATION_PACKAGE): "\n",
    }
    custom = overrides or {}
    applied: dict[str, str] = {}

    async def runner_impl(argv: tuple[str, ...], *, timeout: float) -> str:
        # argv begins with (adb_binary, "-s", serial, ...)
        sub_args = argv[3:]
        for pattern, response in custom.items():  # explicit overrides win first
            if sub_args[: len(pattern)] == pattern:
                return response
        # Capture the applied coordinates from the geo VIEW intent so the dumpsys
        # readback can echo back exactly what was "set" on the device.
        if sub_args[:3] == ("shell", "am", "start") and "-d" in sub_args:
            target = sub_args[sub_args.index("-d") + 1]
            geo = re.match(r"geo:(-?\d+(?:\.\d+)?),(-?\d+(?:\.\d+)?)", target)
            if geo:
                applied["lat"], applied["lon"] = geo.group(1), geo.group(2)
        if sub_args[:3] == ("shell", "dumpsys", "location"):
            if applied:
                return (
                    "Last Known Locations:\n"
                    f"  Location[fused {applied['lat']},{applied['lon']} mock age=0.0s]\n"
                )
            return "Last Known Locations: provider=fused\n"
        for pattern, response in default_handlers.items():
            if sub_args[: len(pattern)] == pattern:
                return response
        if len(sub_args) >= 2 and sub_args[0] == "shell" and sub_args[1] == "am":
            return "Starting: Intent { ... }\n"
        if len(sub_args) >= 3 and sub_args[0] == "shell" and sub_args[1] == "input":
            return "\n"
        return "ok\n"

    return AsyncMock(side_effect=runner_impl)


APPLY_BUTTON_LAYOUT = (
    '[{"resourceId": "cl.coders.faketraveler:id/button_applyStop", '
    '"text": "%s", "bounds": "[100,200][300,400]", '
    '"interactions": ["clickable"], "state": [], "off-screen": false, "enabled": true}]'
)


def mock_apply_button(controller: AndroidShippingController, text: str = "Apply") -> AndroidShippingController:
    """Point the controller's bridge layout dump at a FakeTraveler Apply/Stop button."""
    controller.bridge.layout = AsyncMock(return_value=parse_layout(APPLY_BUTTON_LAYOUT % text))
    return controller


@pytest.fixture(autouse=True)
def _stub_device_mutation_lock(monkeypatch: pytest.MonkeyPatch) -> None:
    """Keep controller unit tests hermetic.

    apply_location now takes the device-wide Redis lock (batch-B fix B3).
    Stub it as acquired here so the ADB-flow tests exercise the device logic
    without a Redis server; the lock itself is covered by the dedicated B3
    tests at the end of this file, which install their own fakes from the
    test body (after this fixture runs).
    """
    from app.services import rpa_runtime_service

    monkeypatch.setattr(rpa_runtime_service.rpa_runtime, "acquire_lock", AsyncMock(return_value=True))
    monkeypatch.setattr(rpa_runtime_service.rpa_runtime, "release_lock", AsyncMock())


# ─────────────────────────────────────────────────────────────────────────────
# 1. Coordinate Validation Tests
# ─────────────────────────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    ("lat", "lon"),
    [
        (90.1, 51.0),
        (-90.1, 51.0),
        (35.0, 180.1),
        (35.0, -180.1),
        (float("nan"), 51.0),
        (35.0, float("nan")),
        (float("inf"), 51.0),
        (35.0, float("-inf")),
        ("35.0", 51.0),
        (35.0, None),
    ],
)
def test_coordinate_validation_rejects_out_of_bounds(lat, lon):
    controller = AndroidShippingController(config(), runner=make_mock_runner())
    with pytest.raises(ValueError):
        controller._validate_coordinates(lat, lon)


@pytest.mark.parametrize(
    ("lat", "lon"),
    [
        (90.0, 180.0),
        (-90.0, -180.0),
        (0.0, 0.0),
        (35.6892, 51.3890),
        (-33.8688, 151.2093),
    ],
)
def test_coordinate_validation_accepts_valid_bounds(lat, lon):
    controller = AndroidShippingController(config(), runner=make_mock_runner())
    controller._validate_coordinates(lat, lon)


@pytest.mark.parametrize("altitude", [float("nan"), float("inf"), float("-inf"), "high"])
def test_coordinate_validation_rejects_invalid_altitude(altitude):
    controller = AndroidShippingController(config(), runner=make_mock_runner())
    with pytest.raises(ValueError):
        controller._validate_coordinates(35.0, 51.0, altitude)


# ─────────────────────────────────────────────────────────────────────────────
# 2. Safety Fences & Preflight Verification Tests
# ─────────────────────────────────────────────────────────────────────────────


async def test_disabled_bridge_fails_closed():
    controller = AndroidShippingController(BridgeConfig(enabled=False), runner=AsyncMock())
    with pytest.raises(BridgeError, match="bridge_disabled"):
        await controller.verify_device_ready()
    with pytest.raises(BridgeError, match="bridge_disabled"):
        await controller.apply_location(35.0, 51.0)
    with pytest.raises(BridgeError, match="bridge_disabled"):
        await controller.launch_transport_app()
    with pytest.raises(BridgeError, match="bridge_disabled"):
        await controller.stop_location_mock()
    with pytest.raises(BridgeError, match="bridge_disabled"):
        await controller.start_shipping("DOC1", 35.0, 51.0)
    with pytest.raises(BridgeError, match="bridge_disabled"):
        await controller.finish_shipping("DOC1", 35.0, 51.0)


async def test_device_not_ready_fails_closed():
    runner = make_mock_runner({("get-state",): "offline\n"})
    controller = AndroidShippingController(config(), runner=runner)
    with pytest.raises(BridgeError, match="device_not_ready"):
        await controller.verify_device_ready()


async def test_android_not_booted_fails_closed():
    runner = make_mock_runner({("shell", "getprop", "sys.boot_completed"): "0\n"})
    controller = AndroidShippingController(config(), runner=runner)
    with pytest.raises(BridgeError, match="android_not_booted"):
        await controller.verify_device_ready()
    with pytest.raises(BridgeError, match="android_not_booted"):
        await controller.start_shipping("DOC1", 35.0, 51.0)


async def test_proxy_setting_mismatch_fails_closed():
    runner = make_mock_runner({("shell", "settings", "get", "global", "http_proxy"): "wrong_proxy:8080\n"})
    controller = AndroidShippingController(config(), runner=runner)
    with pytest.raises(BridgeError, match="proxy_setting_mismatch"):
        await controller.verify_device_ready()
    with pytest.raises(BridgeError, match="proxy_setting_mismatch"):
        await controller.finish_shipping("DOC1", 35.0, 51.0)


# ─────────────────────────────────────────────────────────────────────────────
# 3. Location Injection Intent Formatting & Apply Tests
# ─────────────────────────────────────────────────────────────────────────────


async def test_apply_location_intent_command_formatting():
    runner = make_mock_runner()
    controller = mock_apply_button(AndroidShippingController(config(), runner=runner))

    await controller.apply_location(35.6892, 51.3890, altitude=1200.0)

    # Check intent command sent to FakeTraveler
    expected_intent_call = (
        "adb",
        "-s",
        "127.0.0.1:5555",
        "shell",
        "am",
        "start",
        "-a",
        "android.intent.action.VIEW",
        "-d",
        "geo:35.6892,51.389",
        f"{LOCATION_PACKAGE}/.MainActivity",
    )
    calls = [call.args[0] for call in runner.await_args_list]
    assert expected_intent_call in calls

    # The tap must land on the layout-reported button center (200, 300) —
    # never on blind hard-coded coordinates.
    expected_tap_call = (
        "adb",
        "-s",
        "127.0.0.1:5555",
        "shell",
        "input",
        "tap",
        "200",
        "300",
    )
    assert expected_tap_call in calls
    taps = [c for c in calls if len(c) > 5 and c[5] == "tap"]
    assert len(taps) == 1

    # The observer reads the applied fix back via `dumpsys location` (no
    # longer the old `dumpsys activity services` service-record probe).
    expected_verify_call = (
        "adb",
        "-s",
        "127.0.0.1:5555",
        "shell",
        "dumpsys",
        "location",
    )
    assert expected_verify_call in calls


async def test_apply_location_fails_if_mock_not_registered():
    """If the device never reports a parseable mock fix, apply fails closed.

    The controller taps Apply exactly once, then POLLS `dumpsys location` via
    AdbLocationObserver. An unparseable readback (no Location[...] line) means
    the mock was never confirmed, so apply_location raises after the verify
    window — without ever re-tapping the Apply/Stop toggle.
    """
    runner = make_mock_runner(
        {
            ("shell", "dumpsys", "location"): "Last Known Locations: provider=network\n",
        }
    )
    # Tight verify window: the point is the readback-exhaustion behavior, not timing.
    controller = mock_apply_button(
        AndroidShippingController(
            config(),
            runner=runner,
            apply_verify_timeout=0.05,
            apply_poll_interval=0.01,
        )
    )
    with pytest.raises(BridgeError, match="location_readback_unavailable"):
        await controller.apply_location(35.7, 51.4)

    # Exactly one Apply tap — the poll-based verify must never blind-retap.
    taps = [call.args[0] for call in runner.await_args_list if len(call.args[0]) > 5 and call.args[0][5] == "tap"]
    assert len(taps) == 1


async def test_apply_location_with_layout_finds_and_taps_button():
    runner = make_mock_runner()
    bridge = AndroidBridge(config(), runner=runner)
    layout_json = (
        '[{"resourceId": "cl.coders.faketraveler:id/button_applyStop", '
        '"text": "Apply", "bounds": "[100,200][300,400]", '
        '"interactions": ["clickable"], "state": [], "off-screen": false, "enabled": true}]'
    )
    bridge.layout = AsyncMock(return_value=parse_layout(layout_json))

    controller = AndroidShippingController(bridge=bridge)
    await controller.apply_location(35.7, 51.4)

    # Button center: x=(100+300)//2=200, y=(200+400)//2=300
    expected_tap = ("adb", "-s", "127.0.0.1:5555", "shell", "input", "tap", "200", "300")
    calls = [call.args[0] for call in runner.await_args_list]
    assert expected_tap in calls


async def test_unreadable_layout_fails_closed_without_any_tap():
    """No layout dump means no blind tap: fail closed, zero taps.

    The default mock runner answers the layout command with garbage, so the
    button state is unreadable and apply_location must raise without ever
    issuing an 'input tap'.
    """
    runner = make_mock_runner()
    controller = AndroidShippingController(
        config(),
        runner=runner,
        apply_attempts=2,
        apply_retry_delay=0.01,
    )
    with pytest.raises(BridgeError, match="apply_button_state_unknown"):
        await controller.apply_location(35.7, 51.4)

    taps = [call.args[0] for call in runner.await_args_list if len(call.args[0]) > 5 and call.args[0][5] == "tap"]
    assert taps == []


async def test_apply_button_flipped_to_stop_between_state_read_and_tap():
    """If the toggle flips to Stop between the state read and the tap, the tap
    must be aborted: tapping Stop would disable the provider."""
    runner = make_mock_runner()
    bridge = AndroidBridge(config(), runner=runner)
    bridge.layout = AsyncMock(
        side_effect=[
            parse_layout(APPLY_BUTTON_LAYOUT % "Apply"),
            parse_layout(APPLY_BUTTON_LAYOUT % "Stop"),
        ]
    )
    controller = AndroidShippingController(bridge=bridge, apply_attempts=1)

    with pytest.raises(BridgeError, match="apply_button_state_changed"):
        await controller.apply_location(35.7, 51.4)

    taps = [call.args[0] for call in runner.await_args_list if len(call.args[0]) > 5 and call.args[0][5] == "tap"]
    assert taps == []


async def test_unexpected_button_text_fails_closed_without_any_tap():
    """A button with unknown text must not be tapped: fail closed, zero taps."""
    runner = make_mock_runner()
    controller = mock_apply_button(
        AndroidShippingController(config(), runner=runner, apply_attempts=1),
        text="???",
    )
    with pytest.raises(BridgeError, match="apply_button_state_unknown"):
        await controller.apply_location(35.7, 51.4)

    taps = [call.args[0] for call in runner.await_args_list if len(call.args[0]) > 5 and call.args[0][5] == "tap"]
    assert taps == []


async def test_stop_state_resets_toggle_then_applies():
    """When the button already shows Stop, the controller must RESET the toggle.

    A live Stop means a stale provider is active, so the controller taps once to
    flip Stop→Apply, re-reads to confirm the reset, then performs the normal
    apply tap. Net: exactly two taps, and the postcondition read must see Apply.
    Layout reads, in order: state-read (Stop) → reset re-read (Stop) →
    postcondition (Apply) → apply-action re-read (Apply).
    """
    runner = make_mock_runner()
    bridge = AndroidBridge(config(), runner=runner)
    bridge.layout = AsyncMock(
        side_effect=[
            parse_layout(APPLY_BUTTON_LAYOUT % "Stop"),
            parse_layout(APPLY_BUTTON_LAYOUT % "Stop"),
            parse_layout(APPLY_BUTTON_LAYOUT % "Apply"),
            parse_layout(APPLY_BUTTON_LAYOUT % "Apply"),
        ]
    )
    controller = AndroidShippingController(bridge=bridge)

    await controller.apply_location(35.7, 51.4)  # must not raise

    taps = [call.args[0] for call in runner.await_args_list if len(call.args[0]) > 5 and call.args[0][5] == "tap"]
    assert len(taps) == 2  # one reset tap (Stop→Apply) + one apply tap


async def test_no_blind_retap_when_layout_unreadable():
    """Regression for the Apply/Stop toggle hazard: with an unreadable layout
    dump, retries must not tap blind coordinates on the toggle button.

    The pre-fix code fell back to hard-coded coordinates on every attempt, so
    a second tap could switch an already-active provider OFF. Now the state
    gate fails closed with zero taps.
    """
    state = {"taps": 0}
    base = make_mock_runner()

    async def runner_impl(argv: tuple[str, ...], *, timeout: float) -> str:
        sub_args = argv[3:]
        if sub_args[:2] == ("shell", "input"):
            state["taps"] += 1
        return await base.side_effect(argv, timeout=timeout)

    runner = AsyncMock(side_effect=runner_impl)
    bridge = AndroidBridge(config(), runner=runner)
    bridge.layout = AsyncMock(side_effect=BridgeError("uiautomator_broken"))
    controller = AndroidShippingController(
        bridge=bridge,
        apply_attempts=2,
        apply_retry_delay=0.01,
    )

    with pytest.raises(BridgeError, match="apply_button_state_unknown"):
        await controller.apply_location(35.7, 51.4)

    assert state["taps"] == 0  # pre-fix code tapped blind coordinates here
    # without ever confirming the button state (and reported success).


async def test_apply_button_lost_between_state_read_and_tap():
    """If the button vanishes between the state read and the tap, fail closed."""
    runner = make_mock_runner()
    bridge = AndroidBridge(config(), runner=runner)
    bridge.layout = AsyncMock(
        side_effect=[
            parse_layout(APPLY_BUTTON_LAYOUT % "Apply"),
            BridgeError("selector_missing"),
        ]
    )
    controller = AndroidShippingController(bridge=bridge, apply_attempts=1)

    with pytest.raises(BridgeError, match="apply_button_lost"):
        await controller.apply_location(35.7, 51.4)

    taps = [call.args[0] for call in runner.await_args_list if len(call.args[0]) > 5 and call.args[0][5] == "tap"]
    assert taps == []


async def test_apply_location_polls_readback_until_fix_appears():
    """A readback fix that arrives slightly late must not fail the apply.

    The authoritative flow taps Apply exactly ONCE, then POLLS `dumpsys
    location` via AdbLocationObserver until a fresh matching mock fix appears
    or the verify window expires. A device that reports no parseable fix on the
    first read but the correct fix on a later read must still succeed — and the
    single apply tap must never be repeated (re-tapping an Apply/Stop toggle
    could switch the provider off).
    """
    state = {"taps": 0, "loc_reads": 0}
    base = make_mock_runner()

    async def flaky_runner(argv: tuple[str, ...], *, timeout: float) -> str:
        sub_args = argv[3:]
        if sub_args[:2] == ("shell", "input"):
            state["taps"] += 1
        if sub_args[:3] == ("shell", "dumpsys", "location"):
            state["loc_reads"] += 1
            if state["loc_reads"] == 1:
                # Provider not registered yet: no parseable Location[...] line,
                # so the observer raises location_readback_unavailable and the
                # poll loop retries the READBACK (never the tap).
                return "Last Known Locations: (acquiring fix)\n"
            # Later reads delegate to the base runner, which echoes the exact
            # applied coordinates back as a fresh mock fix.
        return await base.side_effect(argv, timeout=timeout)

    runner = AsyncMock(side_effect=flaky_runner)
    bridge = AndroidBridge(config(), runner=runner)
    bridge.layout = AsyncMock(return_value=parse_layout(APPLY_BUTTON_LAYOUT % "Apply"))
    controller = AndroidShippingController(
        bridge=bridge,
        apply_verify_timeout=0.3,
        apply_poll_interval=0.01,
    )

    await controller.apply_location(35.7, 51.4)  # must not raise

    assert state["taps"] == 1, "the single apply tap must never be repeated"
    assert state["loc_reads"] >= 2, "readback must have polled past the first empty read"


@pytest.mark.parametrize("kwargs", [{"apply_attempts": 0}, {"apply_attempts": -2}])
def test_invalid_apply_attempts_rejected(kwargs):
    with pytest.raises(ValueError, match="apply_attempts"):
        AndroidShippingController(config(), runner=make_mock_runner(), **kwargs)


@pytest.mark.parametrize(
    "kwargs",
    [
        {"apply_retry_delay": 0},
        {"apply_retry_delay": -1.0},
        {"apply_verify_timeout": float("inf")},
        {"apply_poll_interval": float("nan")},
    ],
)
def test_invalid_apply_timing_rejected(kwargs):
    with pytest.raises(ValueError, match="apply_"):
        AndroidShippingController(config(), runner=make_mock_runner(), **kwargs)


# ─────────────────────────────────────────────────────────────────────────────
# 4. Stop Location Mock & Launch Transport App Tests
# ─────────────────────────────────────────────────────────────────────────────


async def test_stop_location_mock():
    runner = make_mock_runner()
    controller = AndroidShippingController(config(), runner=runner)

    await controller.stop_location_mock()

    expected_call = ("adb", "-s", "127.0.0.1:5555", "shell", "am", "force-stop", LOCATION_PACKAGE)
    calls = [call.args[0] for call in runner.await_args_list]
    assert expected_call in calls


async def test_launch_transport_app():
    runner = make_mock_runner()
    controller = AndroidShippingController(config(), runner=runner)

    await controller.launch_transport_app()

    expected_call = ("adb", "-s", "127.0.0.1:5555", "shell", "am", "start", "-n", f"{TARGET_PACKAGE}/.MainActivity")
    calls = [call.args[0] for call in runner.await_args_list]
    assert expected_call in calls


# ─────────────────────────────────────────────────────────────────────────────
# 5. Shipping Flow Tests (start_shipping & finish_shipping)
# ─────────────────────────────────────────────────────────────────────────────


async def test_start_shipping_returns_contract_unverified_error():
    """The official APK has no verified shipping-intent contract, so the
    transport action is a hard fail-closed stub. The default
    (raise_on_error=False) path must surface a sanitized error dict — never a
    fabricated 'started' result that would misreport an unproven mutation."""
    runner = make_mock_runner()
    controller = AndroidShippingController(config(), runner=runner)

    result = await controller.start_shipping("DOC-12345", 35.6892, 51.3890)

    assert result["status"] == "error"
    assert result["reason"] == "android_shipping_action_contract_unverified"
    assert result["doc_no"] == "DOC-12345"


async def test_start_shipping_error_sanitizes_doc_no():
    """The fail-closed error dict must still normalize its inputs: a doc_no with
    surrounding whitespace is echoed back stripped."""
    runner = make_mock_runner()
    controller = AndroidShippingController(config(), runner=runner)

    result = await controller.start_shipping("  DOC-12345  ", 35.6892, 51.3890)

    assert result["status"] == "error"
    assert result["reason"] == "android_shipping_action_contract_unverified"
    assert result["doc_no"] == "DOC-12345"


async def test_start_shipping_raises_when_raise_on_error_requested():
    """With raise_on_error=True the fail-closed stub propagates the BridgeError
    instead of swallowing it into the error dict."""
    runner = make_mock_runner()
    controller = AndroidShippingController(config(), runner=runner)
    with pytest.raises(BridgeError, match="android_shipping_action_contract_unverified"):
        await controller.start_shipping("DOC-12345", 35.6892, 51.3890, raise_on_error=True)


@pytest.mark.parametrize("doc_no", ["", "   ", None])
async def test_start_shipping_rejects_invalid_doc_no(doc_no):
    controller = AndroidShippingController(config(), runner=make_mock_runner())
    with pytest.raises(ValueError):
        await controller.start_shipping(doc_no, 35.7, 51.4)


async def test_finish_shipping_returns_contract_unverified_error():
    """finish_shipping shares the fail-closed transport stub: by default it
    returns the sanitized error dict, never a delivered/finished success."""
    runner = make_mock_runner()
    controller = AndroidShippingController(config(), runner=runner)

    result = await controller.finish_shipping("DOC-12345", 35.7500, 51.4500)

    assert result["status"] == "error"
    assert result["reason"] == "android_shipping_action_contract_unverified"
    assert result["doc_no"] == "DOC-12345"


async def test_finish_shipping_raises_when_raise_on_error_requested():
    """With raise_on_error=True finish propagates the BridgeError like start."""
    runner = make_mock_runner()
    controller = AndroidShippingController(config(), runner=runner)
    with pytest.raises(BridgeError, match="android_shipping_action_contract_unverified"):
        await controller.finish_shipping("DOC-12345", 35.7500, 51.4500, raise_on_error=True)


@pytest.mark.parametrize("doc_no", ["", "   ", None])
async def test_finish_shipping_rejects_invalid_doc_no(doc_no):
    controller = AndroidShippingController(config(), runner=make_mock_runner())
    with pytest.raises(ValueError):
        await controller.finish_shipping(doc_no, 35.7, 51.4)


# ─────────────────────────────────────────────────────────────────────────────
# 6. Controller Initialization & Bridge Config Tests
# ─────────────────────────────────────────────────────────────────────────────


def test_controller_initialization_from_env(monkeypatch):
    monkeypatch.setenv("ANDROID_BRIDGE_ENABLED", "true")
    monkeypatch.setenv("ANDROID_BRIDGE_SERIAL", "emulator-5554")
    monkeypatch.setenv("ANDROID_BRIDGE_EXPECTED_PROXY", "squid:3128")

    controller = AndroidShippingController()
    assert controller.config.enabled is True
    assert controller.config.serial == "emulator-5554"
    assert controller.config.expected_proxy == "squid:3128"


def test_controller_initialization_with_custom_bridge():
    bridge = AndroidBridge(config(serial="192.168.1.100:5555"))
    controller = AndroidShippingController(bridge=bridge)
    assert controller.bridge is bridge
    assert controller.config.serial == "192.168.1.100:5555"


# ─────────────────────────────────────────────────────────────────────────────
# B3. Device-level (cross-job) mutation lock — batch-B regression tests
# ─────────────────────────────────────────────────────────────────────────────


def _install_fake_device_lock(monkeypatch: pytest.MonkeyPatch, state: dict) -> None:
    """Install an atomic in-test stand-in for the Redis device lock.

    Called from the test body, so it overrides the autouse stub above.
    """
    from app.services import rpa_runtime_service

    async def fake_acquire(key: str, ttl_seconds: int) -> bool:
        assert key == ANDROID_DEVICE_MUTATION_LOCK_KEY
        if state["held"]:
            return False
        state["held"] = True
        return True

    async def fake_release(key: str, token: str | None = None) -> None:
        state["held"] = False

    monkeypatch.setattr(rpa_runtime_service.rpa_runtime, "acquire_lock", fake_acquire)
    monkeypatch.setattr(rpa_runtime_service.rpa_runtime, "release_lock", fake_release)


def _recording_controller(tag: str, calls: list, state: dict | None = None) -> AndroidShippingController:
    """Controller whose ADB runner records every device command under `tag`."""
    inner = make_mock_runner()

    async def recording_runner(argv: tuple, *, timeout: float) -> str:
        calls.append((tag, argv[3:]))
        await asyncio.sleep(0.02)  # widen the race window
        return await inner(argv, timeout=timeout)

    controller = AndroidShippingController(config(), runner=recording_runner)
    return mock_apply_button(controller, "Apply")


async def test_concurrent_apply_location_serializes_on_shared_device(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """B3: concurrent apply_location calls (job A /start vs job B /finish)
    must serialize on the single shared device: exactly one wins, and the
    loser fails closed BEFORE touching the device — never proceeds unlocked."""
    state = {"held": False}
    _install_fake_device_lock(monkeypatch, state)
    calls: list = []

    controller_a = _recording_controller("job-a", calls)
    controller_b = _recording_controller("job-b", calls)

    results = await asyncio.gather(
        controller_a.apply_location(35.7, 51.4),
        controller_b.apply_location(35.8, 51.5),
        return_exceptions=True,
    )

    successes = [r for r in results if r is None]
    busy_failures = [r for r in results if isinstance(r, BridgeError) and "android_device_lock_busy" in str(r)]
    assert len(successes) == 1, f"exactly one apply must win the device lock, got {results!r}"
    assert len(busy_failures) == 1, f"the loser must fail closed on the busy lock, got {results!r}"

    winner = "job-a" if results[0] is None else "job-b"
    loser = "job-b" if winner == "job-a" else "job-a"
    assert calls, "the winner must have issued device commands"
    assert all(tag == winner for tag, _ in calls), "device commands interleaved across jobs"
    assert not any(tag == loser for tag, _ in calls), "the loser touched the device without the lock"
    assert state["held"] is False, "device lock was not released"


async def test_apply_location_fails_closed_when_device_lock_unavailable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """B3: if the device lock cannot be acquired at all (Redis down), apply
    must fail closed without touching the device — never proceed unlocked."""
    from app.services import rpa_runtime_service

    async def failing_acquire(key: str, ttl_seconds: int) -> bool:
        raise RuntimeError("redis down")

    release = AsyncMock()
    monkeypatch.setattr(rpa_runtime_service.rpa_runtime, "acquire_lock", failing_acquire)
    monkeypatch.setattr(rpa_runtime_service.rpa_runtime, "release_lock", release)

    runner = make_mock_runner()
    controller = AndroidShippingController(config(), runner=runner)
    mock_apply_button(controller, "Apply")

    with pytest.raises(BridgeError, match="android_device_lock_unavailable"):
        await controller.apply_location(35.7, 51.4)

    runner.assert_not_awaited()
    release.assert_not_awaited()

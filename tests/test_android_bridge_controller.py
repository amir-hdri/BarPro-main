"""Unit tests for AndroidShippingController in app/android_bridge/controller.py."""

from dataclasses import replace
from unittest.mock import AsyncMock

import pytest

from app.android_bridge.client import (
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
    """Create a mock runner that returns standard successful ADB outputs unless overridden."""
    default_handlers = {
        ("get-state",): "device\n",
        ("shell", "getprop", "sys.boot_completed"): "1\n",
        ("shell", "settings", "get", "global", "http_proxy"): "squid:3128\n",
        ("shell", "dumpsys", "activity", "services", LOCATION_PACKAGE): (
            "ServiceRecord{421abc0 u0 cl.coders.faketraveler/.MockedLocationService}\n"
        ),
        ("shell", "dumpsys", "location"): "Last Known Locations: provider=fused, mock=true\n",
        ("shell", "am", "force-stop", LOCATION_PACKAGE): "\n",
    }
    custom = overrides or {}

    async def runner_impl(argv: tuple[str, ...], *, timeout: float) -> str:
        # argv begins with (adb_binary, "-s", serial, ...)
        sub_args = argv[3:]
        for pattern, response in custom.items():
            if sub_args[: len(pattern)] == pattern:
                return response
        for pattern, response in default_handlers.items():
            if sub_args[: len(pattern)] == pattern:
                return response
        if len(sub_args) >= 2 and sub_args[0] == "shell" and sub_args[1] == "am":
            return "Starting: Intent { ... }\n"
        if len(sub_args) >= 3 and sub_args[0] == "shell" and sub_args[1] == "input":
            return "\n"
        return "ok\n"

    return AsyncMock(side_effect=runner_impl)


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
    controller = AndroidShippingController(config(), runner=runner)

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

    # Check input tap sent for apply button
    expected_tap_call = (
        "adb",
        "-s",
        "127.0.0.1:5555",
        "shell",
        "input",
        "tap",
        "540",
        "1100",
    )
    assert expected_tap_call in calls

    # Check mock location verification query
    expected_verify_call = (
        "adb",
        "-s",
        "127.0.0.1:5555",
        "shell",
        "dumpsys",
        "activity",
        "services",
        LOCATION_PACKAGE,
    )
    assert expected_verify_call in calls


async def test_apply_location_fails_if_mock_not_registered():
    runner = make_mock_runner(
        {
            ("shell", "dumpsys", "activity", "services", LOCATION_PACKAGE): "No services\n",
            ("shell", "dumpsys", "location"): "Last Known Locations: provider=network\n",
        }
    )
    controller = AndroidShippingController(config(), runner=runner)
    with pytest.raises(BridgeError, match="mock_location_not_registered"):
        await controller.apply_location(35.7, 51.4)


async def test_apply_location_with_layout_finds_and_taps_button():
    runner = make_mock_runner()
    bridge = AndroidBridge(config(), runner=runner)
    layout_json = (
        '[{"resourceId": "cl.coders.faketraveler:id/button_applyStop", '
        '"text": "Apply", "bounds": "[100,200][300,400]", '
        '"interactions": ["clickable"], "state": [], "off-screen": false, "enabled": true}]'
    )
    bridge.layout = AsyncMock(return_value=parse_layout(layout_json))

    controller = AndroidShippingController(bridge=bridge, use_layout=True)
    await controller.apply_location(35.7, 51.4)

    # Button center: x=(100+300)//2=200, y=(200+400)//2=300
    expected_tap = ("adb", "-s", "127.0.0.1:5555", "shell", "input", "tap", "200", "300")
    calls = [call.args[0] for call in runner.await_args_list]
    assert expected_tap in calls


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


async def test_start_shipping_success_response():
    runner = make_mock_runner()
    controller = AndroidShippingController(config(), runner=runner)

    result = await controller.start_shipping("DOC-12345", 35.6892, 51.3890)

    assert result["status"] == "started"
    assert result["doc_no"] == "DOC-12345"
    assert result["origin_lat"] == 35.6892
    assert result["origin_lon"] == 51.3890
    assert "timestamp" in result
    assert result["action_result"]["result"] == "ok"


async def test_start_shipping_error_response_when_transport_action_fails():
    runner = make_mock_runner(
        {
            ("shell", "am", "start", "-n", f"{TARGET_PACKAGE}/.MainActivity", "--es", "action", "start_shipping"): (
                "Error: Activity class does not exist\n"
            )
        }
    )
    controller = AndroidShippingController(config(), runner=runner)

    # By default, error during execution returns sanitized error response dict
    result = await controller.start_shipping("DOC-12345", 35.6892, 51.3890)

    assert result["status"] == "error"
    assert result["reason"] == "transport_action_failed"
    assert result["doc_no"] == "DOC-12345"


async def test_start_shipping_raises_when_raise_on_error_requested():
    runner = make_mock_runner(
        {
            ("shell", "am", "start", "-n", f"{TARGET_PACKAGE}/.MainActivity", "--es", "action", "start_shipping"): (
                "Error: crash\n"
            )
        }
    )
    controller = AndroidShippingController(config(), runner=runner)
    with pytest.raises(BridgeError, match="transport_action_failed"):
        await controller.start_shipping("DOC-12345", 35.6892, 51.3890, raise_on_error=True)


@pytest.mark.parametrize("doc_no", ["", "   ", None])
async def test_start_shipping_rejects_invalid_doc_no(doc_no):
    controller = AndroidShippingController(config(), runner=make_mock_runner())
    with pytest.raises(ValueError):
        await controller.start_shipping(doc_no, 35.7, 51.4)


async def test_finish_shipping_success_response():
    runner = make_mock_runner()
    controller = AndroidShippingController(config(), runner=runner)

    result = await controller.finish_shipping("DOC-12345", 35.7500, 51.4500)

    assert result["status"] == "delivered"
    assert result["finished"] is True
    assert result["doc_no"] == "DOC-12345"
    assert result["dest_lat"] == 35.7500
    assert result["dest_lon"] == 51.4500
    assert result["mock_stopped"] is True
    assert "timestamp" in result

    # Verify force-stop was called to stop mock location after delivery
    expected_stop = ("adb", "-s", "127.0.0.1:5555", "shell", "am", "force-stop", LOCATION_PACKAGE)
    calls = [call.args[0] for call in runner.await_args_list]
    assert expected_stop in calls


async def test_finish_shipping_error_response():
    runner = make_mock_runner(
        {
            ("shell", "am", "start", "-n", f"{TARGET_PACKAGE}/.MainActivity", "--es", "action", "finish_shipping"): (
                "Error: document not in transit\n"
            )
        }
    )
    controller = AndroidShippingController(config(), runner=runner)

    result = await controller.finish_shipping("DOC-12345", 35.7500, 51.4500)

    assert result["status"] == "error"
    assert result["reason"] == "transport_action_failed"
    assert result["doc_no"] == "DOC-12345"


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

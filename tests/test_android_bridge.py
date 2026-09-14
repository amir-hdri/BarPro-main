"""Behavior tests using synthetic Android CLI output, never a live UTCMS device."""

import asyncio
import json
import os
import sys
from dataclasses import replace
from unittest.mock import AsyncMock

import pytest

from app.android_bridge.client import (
    AndroidBridge,
    BridgeConfig,
    BridgeError,
    _run_command,
    parse_layout,
)


def config(**changes):
    return replace(BridgeConfig(enabled=True, serial="127.0.0.1:5555", expected_proxy="squid:3128"), **changes)


def ready_runner():
    return AsyncMock(
        side_effect=[
            "device\n",
            "1\n",
            "package:/data/app/example/base.apk\n",
            "package:/data/app/faketraveler/base.apk\n",
            "34\n",
            "x86_64,x86\n",
            "Physical size: 1080x1920\nOverride size: 720x1280\n",
            "Physical density: 480\nOverride density: 320\n",
            "squid:3128\n",
        ]
    )


def node(**changes):
    return {
        "resourceId": "com.baarnameshahri:id/test_only_control",
        "text": "synthetic label",
        "contentDesc": "synthetic description",
        "bounds": "[10,20][110,80]",
        "interactions": ["clickable"],
        "state": [],
        **changes,
    }


async def test_disabled_bridge_never_starts_a_process():
    runner = AsyncMock()
    bridge = AndroidBridge(BridgeConfig(), runner=runner)
    with pytest.raises(BridgeError, match="bridge_disabled"):
        await bridge.probe()
    with pytest.raises(BridgeError, match="bridge_disabled"):
        await bridge.layout()
    runner.assert_not_awaited()


@pytest.mark.parametrize("serial", ["", "-d", "device;reboot", "a b", "a\n", "$(id)"])
def test_invalid_serial_is_rejected(serial):
    with pytest.raises(ValueError):
        config(serial=serial)


@pytest.mark.parametrize("proxy", ["", ":3128", "http://squid:3128", "user:pass@squid:3128", "squid:0", "squid:65536"])
def test_proxy_requires_an_explicit_host_and_port(proxy):
    with pytest.raises(ValueError):
        config(expected_proxy=proxy)


@pytest.mark.parametrize("timeout", [0, -1, float("nan"), float("inf")])
def test_invalid_timeouts_are_rejected(timeout):
    with pytest.raises(ValueError):
        config(command_timeout=timeout)


def test_environment_is_opt_in_and_does_not_accept_typo_as_enabled():
    assert BridgeConfig.from_env({}).enabled is False
    with pytest.raises(ValueError):
        BridgeConfig.from_env({"ANDROID_BRIDGE_ENABLED": "yes"})
    loaded = BridgeConfig.from_env(
        {
            "ANDROID_BRIDGE_ENABLED": "true",
            "ANDROID_BRIDGE_SERIAL": "emulator-5554",
            "ANDROID_BRIDGE_EXPECTED_PROXY": "squid:3128",
            "ANDROID_BRIDGE_ADB_BINARY": "/opt/android/adb",
        }
    )
    assert loaded.serial == "emulator-5554"
    assert loaded.adb_binary == "/opt/android/adb"


async def test_probe_binds_every_command_to_device_and_preserves_evidence_limits():
    runner = ready_runner()
    snapshot = await AndroidBridge(config(), runner=runner).probe()
    assert snapshot.sdk == 34
    assert snapshot.abis == ("x86_64", "x86")
    assert (snapshot.width, snapshot.height, snapshot.density) == (720, 1280, 320)
    assert snapshot.observed_at.tzinfo is not None
    assert snapshot.proxy_setting_matches is True
    assert snapshot.egress_verified is False
    assert snapshot.submission_ready is False
    expected_queries = [
        ("get-state",),
        ("shell", "getprop", "sys.boot_completed"),
        ("shell", "pm", "path", "com.baarnameshahri"),
        ("shell", "pm", "path", "cl.coders.faketraveler"),
        ("shell", "getprop", "ro.build.version.sdk"),
        ("shell", "getprop", "ro.product.cpu.abilist"),
        ("shell", "wm", "size"),
        ("shell", "wm", "density"),
        ("shell", "settings", "get", "global", "http_proxy"),
    ]
    assert [call.args[0] for call in runner.await_args_list] == [
        ("adb", "-s", "127.0.0.1:5555", *query) for query in expected_queries
    ]


@pytest.mark.parametrize(
    ("index", "value", "reason"),
    [
        (0, "offline", "device_not_ready"),
        (0, "unauthorized", "device_not_ready"),
        (1, "0", "android_not_booted"),
        (2, "", "package_missing"),
        (3, "", "faketraveler_missing"),
        (4, "not-a-version", "invalid_device_output"),
        (5, "", "invalid_device_output"),
        (6, "Physical size: 0x1920", "invalid_display"),
        (6, "Physical size: 1080x1920\nOverride size: broken", "invalid_display"),
        (7, "Physical density: 0", "invalid_display"),
        (8, "null", "proxy_setting_mismatch"),
        (8, ":0", "proxy_setting_mismatch"),
        (8, "another:3128", "proxy_setting_mismatch"),
    ],
)
async def test_probe_stops_on_missing_or_conflicting_evidence(index, value, reason):
    runner = ready_runner()
    responses = list(runner.side_effect)
    responses[index] = value
    runner.side_effect = responses
    with pytest.raises(BridgeError, match=reason):
        await AndroidBridge(config(), runner=runner).probe()
    assert runner.await_count == index + 1


async def test_probe_has_an_overall_deadline():
    async def stalled(*args, **kwargs):
        await asyncio.Event().wait()

    with pytest.raises(BridgeError, match="observation_timeout"):
        await AndroidBridge(config(observation_timeout=0.01), runner=stalled).probe()


async def test_layout_uses_flat_json_and_explicit_device_without_clicking():
    runner = AsyncMock(return_value=json.dumps([node()]))
    snapshot = await AndroidBridge(config(), runner=runner).layout()
    runner.assert_awaited_once_with(("android", "layout", "--device", "127.0.0.1:5555", "--flat"), timeout=10.0)
    assert snapshot.require_unique(resource_id=node()["resourceId"]).bounds == (10, 20, 110, 80)
    assert "synthetic label" not in repr(snapshot)


@pytest.mark.parametrize("raw", ["not JSON", "{}", "[null]", '[{"bounds": "bad"}]', '[{"state": "focused"}]'])
def test_layout_rejects_unknown_or_malformed_format(raw):
    with pytest.raises(BridgeError, match="invalid_layout"):
        parse_layout(raw)


def test_selector_fails_for_absence_and_ambiguity():
    snapshot = parse_layout(json.dumps([node(), node()]))
    with pytest.raises(BridgeError, match="selector_ambiguous"):
        snapshot.require_unique(resource_id=node()["resourceId"])
    with pytest.raises(BridgeError, match="selector_missing"):
        snapshot.require_unique(resource_id="com.baarnameshahri:id/absent")
    with pytest.raises(ValueError):
        snapshot.require_unique()
    with pytest.raises(ValueError):
        snapshot.require_unique(text="")


def test_selector_matches_all_explicit_predicates_without_fuzzy_fallback():
    snapshot = parse_layout(json.dumps([node(text="wrong"), node()]))
    selected = snapshot.require_unique(resource_id=node()["resourceId"], text="synthetic label")
    assert selected.text == "synthetic label"
    with pytest.raises(BridgeError, match="selector_missing"):
        snapshot.require_unique(text="synthetic")


@pytest.mark.parametrize(
    "changes",
    [
        {"off-screen": True},
        {"enabled": False},
        {"bounds": "[0,0][0,0]"},
        {"bounds": "[-10,0][20,20]"},
    ],
)
def test_selector_rejects_unusable_node(changes):
    snapshot = parse_layout(json.dumps([node(**changes)]))
    with pytest.raises(BridgeError, match="selector_unusable"):
        snapshot.require_unique(resource_id=node()["resourceId"])


async def test_real_runner_returns_stdout_without_using_shell():
    output = await _run_command((sys.executable, "-c", "print('synthetic output')"), timeout=2)
    assert output.strip() == "synthetic output"


async def test_real_runner_sanitizes_error_output():
    with pytest.raises(BridgeError, match="command_failed") as error:
        await _run_command(
            (
                sys.executable,
                "-c",
                "import sys; print('sensitive stdout'); sys.stderr.write('sensitive stderr'); sys.exit(3)",
            ),
            timeout=2,
        )
    assert "sensitive" not in str(error.value)


async def test_real_runner_reaps_child_on_timeout(tmp_path):
    pid_file = tmp_path / "child.pid"
    with pytest.raises(BridgeError, match="command_timeout"):
        await _run_command(
            (
                sys.executable,
                "-c",
                "import os, pathlib, sys, time; pathlib.Path(sys.argv[1]).write_text(str(os.getpid())); time.sleep(60)",
                str(pid_file),
            ),
            timeout=0.5,
        )
    import os

    with pytest.raises(ProcessLookupError):
        os.kill(int(pid_file.read_text()), 0)


async def test_real_runner_bounds_output():
    with pytest.raises(BridgeError, match="command_output_limit"):
        await _run_command((sys.executable, "-c", "print('x' * 2000000)"), timeout=2)


async def test_real_runner_reports_missing_binary():
    with pytest.raises(BridgeError, match="tool_unavailable"):
        await _run_command(("/nonexistent/barpro-test-adb",), timeout=1)


async def test_real_runner_reaps_child_on_cancellation(tmp_path):
    pid_file = tmp_path / "cancel.pid"
    task = asyncio.create_task(
        _run_command(
            (
                sys.executable,
                "-c",
                "import os, pathlib, sys, time; pathlib.Path(sys.argv[1]).write_text(str(os.getpid())); time.sleep(60)",
                str(pid_file),
            ),
            timeout=10,
        )
    )
    try:
        async with asyncio.timeout(2):
            while not pid_file.exists():
                await asyncio.sleep(0.01)
    finally:
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
    with pytest.raises(ProcessLookupError):
        os.kill(int(pid_file.read_text()), 0)


async def test_cli_reports_summary_without_raw_layout(monkeypatch):
    from app.android_bridge import __main__ as cli

    bridge = AndroidBridge(config(), runner=ready_runner())
    bridge.layout = AsyncMock(return_value=parse_layout(json.dumps([node(text="private driver data")])))
    monkeypatch.setattr(cli, "AndroidBridge", lambda _: bridge)
    result = await cli.observe(True)
    assert result["layout_node_count"] == 1
    assert result["execution_authorized"] is False
    assert result["submission_ready"] is False
    assert "private driver data" not in json.dumps(result)


def test_cli_defaults_to_disabled_in_a_clean_environment():
    import subprocess

    env = {key: value for key, value in os.environ.items() if not key.startswith("ANDROID_BRIDGE_")}
    result = subprocess.run(
        [sys.executable, "-m", "app.android_bridge"], capture_output=True, text=True, env=env, timeout=5
    )
    assert result.returncode == 2
    assert json.loads(result.stdout) == {
        "status": "unavailable",
        "reason": "bridge_disabled",
        "execution_authorized": False,
    }
    assert result.stderr == ""

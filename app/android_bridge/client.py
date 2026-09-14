"""Bounded, device-specific Android observation without a mutation API.

Proxy settings and accessible UI are observations, not proof of Iranian egress,
account ownership, network health, or permission to submit a shipment.
"""

from __future__ import annotations

import asyncio
import json
import logging
import math
import os
import re
import signal
from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Protocol

TARGET_PACKAGE = "com.baarnameshahri"
LOCATION_PACKAGE = "cl.coders.faketraveler"
_OUTPUT_LIMIT = 1024 * 1024
logger = logging.getLogger(__name__)


class BridgeError(RuntimeError):
    """Sanitized reason; never include device stdout, SMS, tokens or UI text."""


class CommandRunner(Protocol):
    async def __call__(self, argv: tuple[str, ...], *, timeout: float) -> str: ...


@dataclass(frozen=True)
class BridgeConfig:
    enabled: bool = False
    serial: str = ""
    expected_proxy: str = ""
    adb_binary: str = "adb"
    android_binary: str = "android"
    command_timeout: float = 10.0
    observation_timeout: float = 60.0

    def __post_init__(self) -> None:
        for value in (self.command_timeout, self.observation_timeout):
            if not math.isfinite(value) or not 0 < value <= 300:
                raise ValueError("Android timeouts must be finite, positive and at most 300 seconds")
        for executable in (self.adb_binary, self.android_binary):
            if not executable or executable.startswith("-") or any(char in executable for char in "\x00\r\n"):
                raise ValueError("Invalid Android executable path")
        if self.enabled:
            if re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.:\-\[\]]{0,254}", self.serial) is None:
                raise ValueError("An explicit Android device serial is required")
            proxy = re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9.\-]*:([0-9]{1,5})", self.expected_proxy)
            if proxy is None or not 1 <= int(proxy[1]) <= 65535:
                raise ValueError("Expected Android HTTP proxy must be a credential-free host:port")

    @classmethod
    def from_env(cls, environ: Mapping[str, str] | None = None) -> BridgeConfig:
        """Read explicit process env only; do not initialize BarPro secrets/DB."""
        env = os.environ if environ is None else environ
        enabled = env.get("ANDROID_BRIDGE_ENABLED", "false").lower()
        if enabled not in {"true", "false"}:
            raise ValueError("ANDROID_BRIDGE_ENABLED must be true or false")
        return cls(
            enabled=enabled == "true",
            serial=env.get("ANDROID_BRIDGE_SERIAL", ""),
            expected_proxy=env.get("ANDROID_BRIDGE_EXPECTED_PROXY", ""),
            adb_binary=env.get("ANDROID_BRIDGE_ADB_BINARY", "adb"),
            android_binary=env.get("ANDROID_BRIDGE_ANDROID_BINARY", "android"),
            command_timeout=float(env.get("ANDROID_BRIDGE_COMMAND_TIMEOUT_SECONDS", "10")),
            observation_timeout=float(env.get("ANDROID_BRIDGE_OBSERVATION_TIMEOUT_SECONDS", "60")),
        )


async def _stop_process(process: asyncio.subprocess.Process) -> None:
    try:
        if os.name == "posix":
            # CLI launchers may spawn Java: clean up the whole local process group.
            os.killpg(process.pid, signal.SIGKILL)
        elif process.returncode is None:
            process.kill()
    except ProcessLookupError:
        # The command may have exited between timeout detection and cleanup.
        logger.debug("android_command_already_exited")
    try:
        await asyncio.wait_for(process.wait(), timeout=2.0)
    except TimeoutError:
        raise BridgeError("command_cleanup_timeout") from None


async def _run_command(argv: tuple[str, ...], *, timeout: float) -> str:
    """No shell; bounded stdout, discarded stderr, timeout/cancellation cleanup."""
    try:
        process = await asyncio.create_subprocess_exec(
            *argv,
            stdin=asyncio.subprocess.DEVNULL,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.DEVNULL,
            start_new_session=os.name == "posix",
        )
    except OSError:
        raise BridgeError("tool_unavailable") from None

    async def collect() -> str:
        assert process.stdout is not None
        chunks: list[bytes] = []
        size = 0
        while chunk := await process.stdout.read(65536):
            size += len(chunk)
            if size > _OUTPUT_LIMIT:
                raise BridgeError("command_output_limit")
            chunks.append(chunk)
        if await process.wait() != 0:
            raise BridgeError("command_failed")
        try:
            return b"".join(chunks).decode("utf-8")
        except UnicodeDecodeError:
            raise BridgeError("invalid_command_encoding") from None

    try:
        return await asyncio.wait_for(collect(), timeout=timeout)
    except TimeoutError:
        await _stop_process(process)
        raise BridgeError("command_timeout") from None
    except (asyncio.CancelledError, BridgeError):
        await _stop_process(process)
        raise


@dataclass(frozen=True)
class DeviceObservation:
    observed_at: datetime
    sdk: int
    abis: tuple[str, ...]
    width: int
    height: int
    density: int
    proxy_setting_matches: bool = True
    egress_verified: bool = False
    submission_ready: bool = False


@dataclass(frozen=True)
class UiNode:
    resource_id: str = ""
    text: str = field(default="", repr=False)
    content_description: str = field(default="", repr=False)
    bounds: tuple[int, int, int, int] | None = None
    interactions: tuple[str, ...] = ()
    state: tuple[str, ...] = ()
    off_screen: bool = False
    enabled: bool = True


@dataclass(frozen=True)
class UiObservation:
    observed_at: datetime
    nodes: tuple[UiNode, ...] = field(repr=False)

    def require_unique(
        self,
        *,
        resource_id: str | None = None,
        text: str | None = None,
        content_description: str | None = None,
    ) -> UiNode:
        """Exact conjunction only. A result is observational, never a click plan."""
        predicates = {
            key: value
            for key, value in (
                ("resource_id", resource_id),
                ("text", text),
                ("content_description", content_description),
            )
            if value is not None
        }
        if not predicates or any(not value for value in predicates.values()):
            raise ValueError("At least one nonempty exact selector is required")
        matches = [node for node in self.nodes if all(getattr(node, key) == value for key, value in predicates.items())]
        if not matches:
            raise BridgeError("selector_missing")
        if len(matches) != 1:
            raise BridgeError("selector_ambiguous")
        node = matches[0]
        if node.off_screen or not node.enabled or node.bounds is None:
            raise BridgeError("selector_unusable")
        left, top, right, bottom = node.bounds
        if min(left, top) < 0 or right <= left or bottom <= top:
            raise BridgeError("selector_unusable")
        return node


def parse_layout(raw: str) -> UiObservation:
    """Parse the documented `android layout --flat` format; reject schema drift.

    Keep text only in memory. This parser does not prove foreground package,
    absence of overlays, viewport inclusion, clickability, or app readiness.
    """
    if len(raw) > _OUTPUT_LIMIT:
        raise BridgeError("invalid_layout")
    try:
        values = json.loads(raw)
    except (ValueError, RecursionError):
        raise BridgeError("invalid_layout") from None
    if not isinstance(values, list) or len(values) > 5000:
        raise BridgeError("invalid_layout")
    nodes = []
    for value in values:
        if not isinstance(value, dict):
            raise BridgeError("invalid_layout")
        for key in ("resourceId", "text", "contentDesc"):
            if key in value and not isinstance(value[key], str):
                raise BridgeError("invalid_layout")
        for key in ("interactions", "state"):
            if key in value and (
                not isinstance(value[key], list) or not all(isinstance(item, str) for item in value[key])
            ):
                raise BridgeError("invalid_layout")
        for key in ("off-screen", "enabled"):
            if key in value and not isinstance(value[key], bool):
                raise BridgeError("invalid_layout")
        bounds = None
        if "bounds" in value:
            if not isinstance(value["bounds"], str):
                raise BridgeError("invalid_layout")
            match = re.fullmatch(r"\[(-?\d+),(-?\d+)\]\[(-?\d+),(-?\d+)\]", value["bounds"])
            if match is None:
                raise BridgeError("invalid_layout")
            try:
                bounds = (int(match[1]), int(match[2]), int(match[3]), int(match[4]))
            except ValueError:
                raise BridgeError("invalid_layout") from None
        nodes.append(
            UiNode(
                resource_id=value.get("resourceId", ""),
                text=value.get("text", ""),
                content_description=value.get("contentDesc", ""),
                bounds=bounds,
                interactions=tuple(value.get("interactions", [])),
                state=tuple(value.get("state", [])),
                off_screen=value.get("off-screen", False),
                enabled=value.get("enabled", True),
            )
        )
    return UiObservation(observed_at=datetime.now(UTC), nodes=tuple(nodes))


def _display_value(raw: str, kind: str) -> tuple[int, ...]:
    # An invalid override must not silently fall back to physical dimensions.
    lines = [line.strip() for line in raw.splitlines() if line.strip()]
    label = "Override" if any(line.startswith("Override") for line in lines) else "Physical"
    matches = [line for line in lines if line.startswith(f"{label} {kind}:")]
    pattern = r"([0-9]+)x([0-9]+)" if kind == "size" else r"([0-9]+)"
    match = re.fullmatch(rf"{label} {kind}: {pattern}", matches[0]) if len(matches) == 1 else None
    if match is None:
        raise BridgeError("invalid_display")
    try:
        values = tuple(int(item) for item in match.groups())
    except ValueError:
        raise BridgeError("invalid_display") from None
    if any(not 0 < value <= 10000 for value in values):
        raise BridgeError("invalid_display")
    return values


class AndroidBridge:
    def __init__(self, config: BridgeConfig, *, runner: CommandRunner = _run_command) -> None:
        self.config = config
        self._runner = runner

    def _require_enabled(self) -> None:
        if not self.config.enabled:
            raise BridgeError("bridge_disabled")

    async def _adb(self, *args: str) -> str:
        self._require_enabled()
        return (
            await self._runner(
                (self.config.adb_binary, "-s", self.config.serial, *args), timeout=self.config.command_timeout
            )
        ).strip()

    async def probe(self) -> DeviceObservation:
        self._require_enabled()
        try:
            async with asyncio.timeout(self.config.observation_timeout):
                return await self._probe()
        except TimeoutError:
            raise BridgeError("observation_timeout") from None

    async def _probe(self) -> DeviceObservation:
        if await self._adb("get-state") != "device":
            raise BridgeError("device_not_ready")
        if await self._adb("shell", "getprop", "sys.boot_completed") != "1":
            raise BridgeError("android_not_booted")
        for package_name in (TARGET_PACKAGE, LOCATION_PACKAGE):
            package = await self._adb("shell", "pm", "path", package_name)
            if not package or not all(re.fullmatch(r"package:/[^\r\n]+\.apk", line) for line in package.splitlines()):
                reason = "package_missing" if package_name == TARGET_PACKAGE else "faketraveler_missing"
                raise BridgeError(reason)
        sdk_raw = await self._adb("shell", "getprop", "ro.build.version.sdk")
        if not re.fullmatch(r"[0-9]{1,3}", sdk_raw) or int(sdk_raw) < 1:
            raise BridgeError("invalid_device_output")
        abis_raw = await self._adb("shell", "getprop", "ro.product.cpu.abilist")
        if not re.fullmatch(r"[a-zA-Z0-9_-]+(?:,[a-zA-Z0-9_-]+)*", abis_raw):
            raise BridgeError("invalid_device_output")
        width, height = _display_value(await self._adb("shell", "wm", "size"), "size")
        (density,) = _display_value(await self._adb("shell", "wm", "density"), "density")
        proxy = await self._adb("shell", "settings", "get", "global", "http_proxy")
        if proxy != self.config.expected_proxy:
            raise BridgeError("proxy_setting_mismatch")
        return DeviceObservation(
            observed_at=datetime.now(UTC),
            sdk=int(sdk_raw),
            abis=tuple(abis_raw.split(",")),
            width=width,
            height=height,
            density=density,
        )

    async def layout(self) -> UiObservation:
        self._require_enabled()
        raw = await self._runner(
            (self.config.android_binary, "layout", "--device", self.config.serial, "--flat"),
            timeout=self.config.command_timeout,
        )
        return parse_layout(raw)

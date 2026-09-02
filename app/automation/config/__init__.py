"""
Configuration profiles for Anti-Detection system
================================================
This module contains configuration profiles for browser automation,
including user agents, fingerprints, proxy settings, and behavior patterns.
"""

import json
import os
from dataclasses import asdict, dataclass, field
from datetime import datetime
from typing import Any, Optional


@dataclass
class ScreenFingerprint:
    """Screen configuration for realistic browser fingerprint"""

    width: int = 1920
    height: int = 1080
    color_depth: int = 24
    pixel_ratio: float = 1.0
    avail_width: int = 1920
    avail_height: int = 1040
    available_color_depth: int = 24

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class WebGLFingerprint:
    """WebGL/GPU fingerprint configuration"""

    vendor: str = ""
    renderer: str = ""
    version: str = "WebGL 1.0"
    unmasked_vendor: str = ""
    unmasked_renderer: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class BrowserProfile:
    """Complete browser fingerprint profile"""

    name: str = "default"
    user_agent: str = ""
    platform: str = ""
    platform_version: str = ""
    language: str = "en-US"
    languages: list[str] = field(default_factory=lambda: ["en-US", "en"])
    timezone: str = "America/New_York"
    screen: ScreenFingerprint = field(default_factory=ScreenFingerprint)
    webgl: WebGLFingerprint = field(default_factory=WebGLFingerprint)
    hardware_concurrency: int = 8
    device_memory: int = 8
    max_touch_points: int = 0
    do_not_track: str | None = None
    device_pixel_ratio: float = 1.0
    cookie_enabled: bool = True
    local_storage_enabled: bool = True
    session_storage_enabled: bool = True

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        # Convert nested dataclasses to dicts
        if hasattr(self.screen, "to_dict"):
            data["screen"] = self.screen.to_dict()
        if hasattr(self.webgl, "to_dict"):
            data["webgl"] = self.webgl.to_dict()
        return data

    def fingerprint_hash(self) -> str:
        """Generate unique hash for fingerprint identification"""
        import hashlib
        import json

        raw = json.dumps(self.to_dict(), sort_keys=True)
        return hashlib.sha256(raw.encode()).hexdigest()[:16]


# ============================================================================
# REALISTIC USER AGENT POOLS
# ============================================================================

USER_AGENT_PROFILES = [
    {
        "name": "chrome_windows_124",
        "user_agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
        "platform": "Win32",
        "platform_version": "10.0",
        "language": "en-US",
        "languages": ["en-US", "en"],
        "timezone": "America/New_York",
        "screen": {"width": 1920, "height": 1080, "pixel_ratio": 1.0},
        "hardware_concurrency": 8,
        "device_memory": 8,
    },
    {
        "name": "chrome_windows_124_en_uk",
        "user_agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
        "platform": "Win32",
        "platform_version": "10.0",
        "language": "en-GB",
        "languages": ["en-GB", "en-US", "en"],
        "timezone": "Europe/London",
        "screen": {"width": 1366, "height": 768, "pixel_ratio": 1.0},
        "hardware_concurrency": 4,
        "device_memory": 4,
    },
    {
        "name": "chrome_mac_m1",
        "user_agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
        "platform": "MacIntel",
        "platform_version": "10.15.7",
        "language": "en-US",
        "languages": ["en-US", "en"],
        "timezone": "America/Los_Angeles",
        "screen": {"width": 2560, "height": 1440, "pixel_ratio": 2.0},
        "hardware_concurrency": 8,
        "device_memory": 16,
    },
    {
        "name": "chrome_mac_apple_silicon",
        "user_agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36",
        "platform": "MacIntel",
        "platform_version": "14.0",
        "language": "fa-IR",
        "languages": ["fa-IR", "fa", "en-US", "en"],
        "timezone": "Asia/Tehran",
        "screen": {"width": 1920, "height": 1080, "pixel_ratio": 2.0},
        "hardware_concurrency": 8,
        "device_memory": 16,
    },
    {
        "name": "firefox_windows_125",
        "user_agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:125.0) Gecko/20100101 Firefox/125.0",
        "platform": "Win32",
        "platform_version": "10.0",
        "language": "en-US",
        "languages": ["en-US", "en"],
        "timezone": "America/Chicago",
        "screen": {"width": 1920, "height": 1080, "pixel_ratio": 1.5},
        "hardware_concurrency": 12,
        "device_memory": 8,
    },
    {
        "name": "edge_chromium_windows",
        "user_agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36 Edg/124.0.0.0",
        "platform": "Win32",
        "platform_version": "10.0",
        "language": "en-US",
        "languages": ["en-US"],
        "timezone": "America/New_York",
        "screen": {"width": 1440, "height": 900, "pixel_ratio": 1.5},
        "hardware_concurrency": 8,
        "device_memory": 16,
    },
    {
        "name": "chrome_linux",
        "user_agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
        "platform": "Linux x86_64",
        "platform_version": "",
        "language": "en-US",
        "languages": ["en-US", "en"],
        "timezone": "Europe/Berlin",
        "screen": {"width": 1920, "height": 1080, "pixel_ratio": 1.0},
        "hardware_concurrency": 8,
        "device_memory": 8,
    },
    {
        "name": "chrome_tablet",
        "user_agent": "Mozilla/5.0 (iPad; CPU OS 17_0 like Mac OS X) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
        "platform": "iPad",
        "platform_version": "17.0",
        "language": "en-US",
        "languages": ["en-US", "en"],
        "timezone": "America/Los_Angeles",
        "screen": {"width": 1024, "height": 768, "pixel_ratio": 2.0},
        "hardware_concurrency": 4,
        "device_memory": 4,
        "max_touch_points": 5,
    },
]

# ============================================================================
# REALISTIC GPU/WEBGL FINGERPRINTS
# ============================================================================

GPU_PROFILES = [
    {
        "vendor": "Google Inc. (AMD)",
        "renderer": "ANGLE (AMD, AMD Radeon RX 6700 XT Direct3D11 vs_5_0 ps_5_0)",
        "unmasked_vendor": "Advanced Micro Devices, Inc.",
        "unmasked_renderer": "AMD Radeon RX 6700 XT",
    },
    {
        "vendor": "Google Inc. (Intel)",
        "renderer": "ANGLE (Intel, Intel(R) UHD Graphics 770 Direct3D11 vs_5_0 ps_5_0)",
        "unmasked_vendor": "Intel Corporation",
        "unmasked_renderer": "Intel(R) UHD Graphics 770",
    },
    {
        "vendor": "Google Inc. (Intel)",
        "renderer": "ANGLE (Intel, Intel(R) Iris(R) Xe Graphics Direct3D11 vs_5_0 ps_5_0)",
        "unmasked_vendor": "Intel Corporation",
        "unmasked_renderer": "Intel(R) Iris(R) Xe Graphics",
    },
    {
        "vendor": "Google Inc. (Apple)",
        "renderer": "Apple M2 Pro, Metal",
        "unmasked_vendor": "Apple Inc.",
        "unmasked_renderer": "Apple M2 Pro",
    },
    {
        "vendor": "Google Inc. (Apple)",
        "renderer": "Apple M1, Metal",
        "unmasked_vendor": "Apple Inc.",
        "unmasked_renderer": "Apple M1",
    },
    {
        "vendor": "Google Inc. (Intel)",
        "renderer": "ANGLE (Intel, Intel(R) HD Graphics 620 Direct3D11 vs_5_0 ps_5_0)",
        "unmasked_vendor": "Intel Corporation",
        "unmasked_renderer": "Intel(R) HD Graphics 620",
    },
]

# ============================================================================
# SCREEN PRESETS
# ============================================================================

SCREEN_PRESETS = [
    # Popular laptop resolutions
    {"width": 1366, "height": 768, "avail_width": 1366, "avail_height": 728, "color_depth": 24, "pixel_ratio": 1.0},
    {"width": 1440, "height": 900, "avail_width": 1440, "avail_height": 860, "color_depth": 24, "pixel_ratio": 1.0},
    {"width": 1536, "height": 864, "avail_width": 1536, "avail_height": 824, "color_depth": 24, "pixel_ratio": 1.25},
    {"width": 1680, "height": 1050, "avail_width": 1680, "avail_height": 1010, "color_depth": 24, "pixel_ratio": 1.0},
    # Desktop resolutions
    {"width": 1920, "height": 1080, "avail_width": 1920, "avail_height": 1040, "color_depth": 24, "pixel_ratio": 1.0},
    {"width": 1920, "height": 1200, "avail_width": 1920, "avail_height": 1160, "color_depth": 24, "pixel_ratio": 1.0},
    {"width": 2560, "height": 1440, "avail_width": 2560, "avail_height": 1400, "color_depth": 24, "pixel_ratio": 1.0},
    {"width": 3440, "height": 1440, "avail_width": 3440, "avail_height": 1400, "color_depth": 24, "pixel_ratio": 1.0},
    # 4K and high DPI
    {"width": 3840, "height": 2160, "avail_width": 3840, "avail_height": 2100, "color_depth": 24, "pixel_ratio": 1.5},
    {"width": 2880, "height": 1800, "avail_width": 2880, "avail_height": 1760, "color_depth": 24, "pixel_ratio": 2.0},
    # Common tablet resolutions
    {"width": 1024, "height": 768, "avail_width": 1024, "avail_height": 728, "color_depth": 24, "pixel_ratio": 2.0},
    {"width": 1080, "height": 1920, "avail_width": 1080, "avail_height": 1880, "color_depth": 24, "pixel_ratio": 2.0},
]

# ============================================================================
# TIMEZONE & LOCALE PROFILES
# ============================================================================

TIMEZONE_PROFILES = [
    "America/New_York",
    "America/Chicago",
    "America/Denver",
    "America/Los_Angeles",
    "America/Phoenix",
    "America/Toronto",
    "America/Vancouver",
    "America/Mexico_City",
    "Europe/London",
    "Europe/Paris",
    "Europe/Berlin",
    "Europe/Madrid",
    "Europe/Rome",
    "Europe/Amsterdam",
    "Europe/Stockholm",
    "Europe/Warsaw",
    "Europe/Moscow",
    "Asia/Tehran",
    "Asia/Dubai",
    "Asia/Karachi",
    "Asia/Kolkata",
    "Asia/Dhaka",
    "Asia/Bangkok",
    "Asia/Jakarta",
    "Asia/Manila",
    "Asia/Singapore",
    "Asia/Hong_Kong",
    "Asia/Shanghai",
    "Asia/Tokyo",
    "Asia/Seoul",
    "Asia/Taipei",
    "Australia/Sydney",
    "Australia/Melbourne",
    "Australia/Perth",
    "Pacific/Auckland",
    "Africa/Cairo",
    "Africa/Johannesburg",
]

LOCALE_PROFILES = [
    {"locale": "en-US", "timezone": "America/New_York", "languages": ["en-US", "en"]},
    {"locale": "en-GB", "timezone": "Europe/London", "languages": ["en-GB", "en"]},
    {"locale": "en-CA", "timezone": "America/Toronto", "languages": ["en-CA", "en"]},
    {"locale": "en-AU", "timezone": "Australia/Sydney", "languages": ["en-AU", "en"]},
    {"locale": "de-DE", "timezone": "Europe/Berlin", "languages": ["de-DE", "de"]},
    {"locale": "fr-FR", "timezone": "Europe/Paris", "languages": ["fr-FR", "fr"]},
    {"locale": "es-ES", "timezone": "Europe/Madrid", "languages": ["es-ES", "es"]},
    {"locale": "it-IT", "timezone": "Europe/Rome", "languages": ["it-IT", "it"]},
    {"locale": "ja-JP", "timezone": "Asia/Tokyo", "languages": ["ja-JP", "ja"]},
    {"locale": "ko-KR", "timezone": "Asia/Seoul", "languages": ["ko-KR", "ko"]},
    {"locale": "zh-CN", "timezone": "Asia/Shanghai", "languages": ["zh-CN", "zh"]},
    {"locale": "zh-TW", "timezone": "Asia/Taipei", "languages": ["zh-TW", "zh"]},
    {"locale": "fa-IR", "timezone": "Asia/Tehran", "languages": ["fa-IR", "fa", "en-US"]},
    {"locale": "ar-SA", "timezone": "Asia/Riyadh", "languages": ["ar-SA", "ar"]},
    {"locale": "ru-RU", "timezone": "Europe/Moscow", "languages": ["ru-RU", "ru"]},
    {"locale": "pt-BR", "timezone": "America/Sao_Paulo", "languages": ["pt-BR", "pt"]},
]

# ============================================================================
# ACCEPT HEADERS
# ============================================================================

ACCEPT_VARIANTS = [
    "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7",
    "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7",
    "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
    "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "text/html,application/xhtml+xml;q=0.9,image/webp,image/apng,*/*;q=0.8",
]

SEC_CH_UA_VARIANTS = [
    '"Chromium";v="124", "Google Chrome";v="124", "Not.A/Brand";v="99"',
    '"Chromium";v="123", "Google Chrome";v="123", "Not.A/Brand";v="99"',
    '"Not_A Brand";v="8", "Chromium";v="120", "Google Chrome";v="120"',
]

# ============================================================================
# FILE I/O
# ============================================================================

CONFIG_DIR = os.path.join(os.path.dirname(__file__), "..", "..", "config")


def ensure_config_dir():
    """Ensure config directory exists"""
    os.makedirs(CONFIG_DIR, exist_ok=True)


def save_profiles(profiles: list[dict], filename: str = "profiles.json"):
    """Save browser profiles to JSON file"""
    ensure_config_dir()
    filepath = os.path.join(CONFIG_DIR, filename)
    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(
            {"version": "1.0", "created_at": datetime.now().isoformat(), "profiles": profiles},
            f,
            indent=2,
            ensure_ascii=False,
        )
    return filepath


def load_profiles(filename: str = "profiles.json") -> dict:
    """Load browser profiles from JSON file"""
    filepath = os.path.join(CONFIG_DIR, filename)
    if not os.path.exists(filepath):
        # Return default profiles if file doesn't exist
        return {"profiles": USER_AGENT_PROFILES}

    with open(filepath, encoding="utf-8") as f:
        return json.load(f)


def save_gpus(gpu_profiles: list[dict], filename: str = "gpus.json"):
    """Save GPU profiles to JSON file"""
    ensure_config_dir()
    filepath = os.path.join(CONFIG_DIR, filename)
    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(
            {"version": "1.0", "created_at": datetime.now().isoformat(), "gpus": gpu_profiles},
            f,
            indent=2,
            ensure_ascii=False,
        )
    return filepath


def load_gpus(filename: str = "gpus.json") -> dict:
    """Load GPU profiles from JSON file"""
    filepath = os.path.join(CONFIG_DIR, filename)
    if not os.path.exists(filepath):
        return {"gpus": GPU_PROFILES}

    with open(filepath, encoding="utf-8") as f:
        return json.load(f)


# ============================================================================
# INITIALIZATION
# ============================================================================


def init_config_files():
    """Initialize config files with default profiles"""
    ensure_config_dir()

    # Save profiles
    save_profiles(USER_AGENT_PROFILES)

    # Save GPUs
    save_gpus(GPU_PROFILES)

    return True


if __name__ == "__main__":
    # Generate default config files
    init_config_files()
    print("✅ Config files initialized successfully!")
    print(f"   Profiles: {CONFIG_DIR}/profiles.json")
    print(f"   GPUs: {CONFIG_DIR}/gpus.json")

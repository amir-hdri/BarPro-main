"""
Anti-Detection Automation Package
==================================
Complete anti-detection browser automation system with:
- Fingerprint management
- Proxy rotation with health checks
- HTTP header building
- Human-like behavior simulation
- Stealth browser management
"""

from .browser import (
    BrowserManager,
    PageInteractor,
    browser_manager,
    managed_browser_session,
    managed_page,
)
from .browser_pool import (
    BrowserPool,
)
from .config import (
    ACCEPT_VARIANTS,
    LOCALE_PROFILES,
    SCREEN_PRESETS,
    SEC_CH_UA_VARIANTS,
    TIMEZONE_PROFILES,
    USER_AGENT_PROFILES,
    BrowserProfile,
    ScreenFingerprint,
    WebGLFingerprint,
    load_gpus,
    load_profiles,
)
from .header_builder import (
    BrowserHeaderBuilder,
    HeaderBuilder,
    HeaderContext,
    get_header_builder,
    set_header_builder,
)
from .human_interaction import (
    HumanBehaviorSimulator,
    HumanTiming,
    MouseMovementEngine,
    TypingProfile,
    click_with_human_movement,
    human_type,
    type_with_human_delays,
    wait_like_human,
)
from .proxy_rotator import (
    ProxyInfo,
    ProxyRotator,
    get_proxy_rotator,
    set_proxy_rotator,
    _test_proxy as test_proxy,
)
test_proxy.__test__ = False
from .stealth import (
    apply_stealth_mode,
    get_random_user_agent,
    get_random_viewport,
    human_like_mouse_movement,
    human_like_typing,
    random_scroll,
    simulate_human_behavior,
)
from .stealth_advanced import (
    LOCALE_PRESETS,
    USER_AGENT_POOL,
    WEBGL_FINGERPRINTS,
    apply_enterprise_stealth,
    detect_waf,
    get_random_locale_preset,
    get_random_screen_preset,
    get_random_webgl_fingerprint,
    handle_cloudflare_challenge,
)
from .stealth_advanced import (
    SCREEN_PRESETS as ADVANCED_SCREEN_PRESETS,
)
from .stealth_advanced import (
    get_random_user_agent as get_advanced_ua,
)

# Export all main classes for easy import
__all__ = [
    # Config
    "USER_AGENT_PROFILES",
    "SCREEN_PRESETS",
    "TIMEZONE_PROFILES",
    "LOCALE_PROFILES",
    "ACCEPT_VARIANTS",
    "SEC_CH_UA_VARIANTS",
    "BrowserProfile",
    "ScreenFingerprint",
    "WebGLFingerprint",
    "load_profiles",
    "load_gpus",
    # Proxy
    "ProxyInfo",
    "ProxyRotator",
    "get_proxy_rotator",
    "set_proxy_rotator",
    "test_proxy",
    # Headers
    "HeaderBuilder",
    "BrowserHeaderBuilder",
    "HeaderContext",
    "get_header_builder",
    "set_header_builder",
    # Stealth
    "apply_stealth_mode",
    "get_random_user_agent",
    "get_random_viewport",
    "human_like_typing",
    "human_like_mouse_movement",
    "random_scroll",
    "simulate_human_behavior",
    # Stealth Advanced
    "USER_AGENT_POOL",
    "WEBGL_FINGERPRINTS",
    "ADVANCED_SCREEN_PRESETS",
    "LOCALE_PRESETS",
    "apply_enterprise_stealth",
    "detect_waf",
    "handle_cloudflare_challenge",
    "get_advanced_ua",
    "get_random_screen_preset",
    "get_random_locale_preset",
    "get_random_webgl_fingerprint",
    # Human Interaction
    "human_type",
    "click_with_human_movement",
    "wait_like_human",
    "type_with_human_delays",
    "MouseMovementEngine",
    "TypingProfile",
    "HumanBehaviorSimulator",
    "HumanTiming",
    # Browser Management
    "BrowserManager",
    "PageInteractor",
    "managed_browser_session",
    "managed_page",
    "browser_manager",
    # Browser Pool
    "BrowserPool",
]

# Version
__version__ = "1.0.0"
__author__ = "Automation Team"

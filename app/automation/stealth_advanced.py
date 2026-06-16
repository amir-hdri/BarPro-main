"""
Enterprise-Grade Anti-Bot Evasion & Stealth System
===================================================
Advanced techniques to mask automation indicators and bypass WAF detection.
Implements multi-layered stealth for Cloudflare, Imperva, and custom WAFs.
"""

import asyncio
import random
import time
from typing import Any

from playwright.async_api import Page

# ============================================================================
# ENHANCED USER AGENT & FINGERPRINT POOLS
# ============================================================================

# Realistic user agents with version-specific fingerprints
USER_AGENT_POOL = {
    "chrome_windows": [
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36",
    ],
    "chrome_mac": [
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    ],
    "firefox_windows": [
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:122.0) Gecko/20100101 Firefox/122.0",
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:121.0) Gecko/20100101 Firefox/121.0",
    ],
    "edge_windows": [
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36 Edg/121.0.0.0",
    ],
}

# WebGL fingerprint database - realistic GPU signatures
WEBGL_FINGERPRINTS = [
    {
        "vendor": "Intel Inc.",
        "renderer": "Intel Iris OpenGL Engine",
        "unmasked_vendor": "Intel Inc.",
        "unmasked_renderer": "Intel Iris Pro 6200",
    },
    {
        "vendor": "Google Inc. (Intel)",
        "renderer": "ANGLE (Intel, Intel(R) HD Graphics 620 Direct3D11 vs_5_0 ps_5_0)",
        "unmasked_vendor": "Intel",
        "unmasked_renderer": "Intel(R) HD Graphics 620",
    },
    {
        "vendor": "Google Inc. (NVIDIA)",
        "renderer": "ANGLE (NVIDIA, NVIDIA GeForce GTX 1050 Direct3D11 vs_5_0 ps_5_0)",
        "unmasked_vendor": "NVIDIA Corporation",
        "unmasked_renderer": "NVIDIA GeForce GTX 1050",
    },
    {
        "vendor": "Google Inc. (AMD)",
        "renderer": "ANGLE (AMD, AMD Radeon RX 580 Direct3D11 vs_5_0 ps_5_0)",
        "unmasked_vendor": "ATI Technologies Inc.",
        "unmasked_renderer": "AMD Radeon RX 580",
    },
]

# Screen resolution presets (realistic combinations)
SCREEN_PRESETS = [
    {"width": 1366, "height": 768, "avail_width": 1366, "avail_height": 728, "color_depth": 24, "pixel_depth": 24},
    {"width": 1440, "height": 900, "avail_width": 1440, "avail_height": 860, "color_depth": 24, "pixel_depth": 24},
    {"width": 1536, "height": 864, "avail_width": 1536, "avail_height": 824, "color_depth": 24, "pixel_depth": 24},
    {"width": 1920, "height": 1080, "avail_width": 1920, "avail_height": 1040, "color_depth": 24, "pixel_depth": 24},
    {"width": 2560, "height": 1440, "avail_width": 2560, "avail_height": 1400, "color_depth": 24, "pixel_depth": 24},
]

# Timezone & locale presets
LOCALE_PRESETS = [
    {"locale": "fa-IR", "timezone": "Asia/Tehran", "languages": ["fa-IR", "fa", "en-US", "en"]},
    {"locale": "en-US", "timezone": "America/New_York", "languages": ["en-US", "en"]},
    {"locale": "en-GB", "timezone": "Europe/London", "languages": ["en-GB", "en"]},
]


# ============================================================================
# ADVANCED STEALTH SCRIPTS
# ============================================================================

# Core stealth script - removes all automation indicators
STEALTH_CORE_SCRIPT = """
() => {
    // 1. Remove webdriver flag
    Object.defineProperty(navigator, 'webdriver', {
        get: () => undefined,
        configurable: true
    });

    // 2. Spoof Chrome runtime
    if (!window.chrome) {
        window.chrome = {};
    }

    window.chrome.runtime = {
        ...window.chrome.runtime,
        OnInstalledReason: {
            INSTALL: 'install',
            UPDATE: 'update',
            CHROME_UPDATE: 'chrome_update',
            SHARED_MODULE_UPDATE: 'shared_module_update'
        },
        OnRestartRequiredReason: {
            APP_UPDATE: 'app_update',
            OS_UPDATE: 'os_update',
            PERIODIC: 'periodic'
        },
        PlatformArch: {
            ARM: 'arm',
            X86_32: 'x86-32',
            X86_64: 'x86-64'
        },
        PlatformNaclArch: {
            ARM: 'arm',
            X86_32: 'x86-32',
            X86_64: 'x86-64'
        },
        PlatformOs: {
            ANDROID: 'android',
            CROS: 'cros',
            LINUX: 'linux',
            MAC: 'mac',
            OPENBSD: 'openbsd',
            WIN: 'win'
        },
        RequestUpdateCheckStatus: {
            NO_UPDATE: 'no_update',
            THROTTLED: 'throttled',
            UPDATE_AVAILABLE: 'update_available'
        }
    };

    // 3. Mock chrome.csi and chrome.loadTimes
    if (!window.chrome.csi) {
        window.chrome.csi = () => ({
            startE: Date.now(),
            onloadT: Date.now(),
            pageT: Math.random() * 1000,
            tran: 15
        });
    }

    if (!window.chrome.loadTimes) {
        window.chrome.loadTimes = () => ({
            connectionInfo: 'h2',
            npnNegotiatedProtocol: 'h2',
            navigationType: 'Other',
            wasAlternateProtocolAvailable: false,
            wasFetchedViaSpdy: true,
            wasNpnNegotiated: true,
            firstPaintAfterLoadTime: 0,
            firstPaintTime: (Date.now() - performance.timing.navigationStart) / 1000,
            requestTime: performance.timing.navigationStart / 1000,
            startLoadTime: performance.timing.navigationStart / 1000,
            commitLoadTime: performance.timing.responseStart / 1000,
            finishDocumentLoadTime: performance.timing.domContentLoadedEventEnd / 1000,
            finishLoadTime: performance.timing.loadEventEnd / 1000,
            redirectCount: performance.navigation.redirectCount
        });
    }

    // 4. Remove Playwright-specific properties
    const propsToDelete = [
        '__playwright__', '__pw_manual__', '__PW_inspect__',
        '__webdriver_evaluate', '__selenium_evaluate', '__webdriver_script_function',
        '__webdriver_script_func', '__webdriver_script_fn', '__fxdriver_evaluate',
        '__driver_evaluate', '__webdriver_attr', '__webdriver_script_attr'
    ];

    for (const prop of propsToDelete) {
        if (window[prop] !== undefined) {
            delete window[prop];
        }
        if (window.document && window.document[prop] !== undefined) {
            delete window.document[prop];
        }
        if (navigator[prop] !== undefined) {
            delete navigator[prop];
        }
    }

    // 5. Remove Selenium indicators
    const seleniumProps = [
        'webdriver', '__driver_evaluate', '__webdriver_attr',
        '__fxdriver_evaluate', '__webdriver_script_function'
    ];

    seleniumProps.forEach(prop => {
        try {
            Object.defineProperty(navigator, prop, {
                get: () => undefined,
                configurable: true
            });
        } catch (e) {}
    });

    // 6. Spoof permissions API
    const originalQuery = window.navigator.permissions.query;
    window.navigator.permissions.query = (parameters) => {
        if (parameters.name === 'notifications') {
            return Promise.resolve({ state: Notification.permission });
        }
        return originalQuery(parameters);
    };

    // 7. Remove headless indicators
    Object.defineProperty(navigator, 'plugins', {
        get: () => [
            { name: 'Chrome PDF Plugin', filename: 'internal-pdf-viewer', description: 'Portable Document Format' },
            { name: 'Chrome PDF Viewer', filename: 'mhjfbmdgcfjbbpaeojofohoefgiehjai', description: 'Portable Document Format' },
            { name: 'Native Client', filename: 'internal-nacl-plugin', description: '' }
        ],
        configurable: true
    });

    // 8. Mock connection information
    Object.defineProperty(navigator, 'connection', {
        get: () => ({
            downlink: 10 + Math.random() * 5,
            effectiveType: '4g',
            rtt: 50 + Math.random() * 30,
            saveData: false
        }),
        configurable: true
    });

    // 9. Remove iframe contentWindow anomalies
    const iframeContentWindow = Object.getOwnPropertyDescriptor(HTMLIFrameElement.prototype, 'contentWindow');
    if (iframeContentWindow) {
        const origValue = iframeContentWindow.get;
        Object.defineProperty(HTMLIFrameElement.prototype, 'contentWindow', {
            get: function() {
                const win = origValue.call(this);
                if (win && win.navigator.webdriver) {
                    Object.defineProperty(win.navigator, 'webdriver', {
                        get: () => undefined
                    });
                }
                return win;
            }
        });
    }
}
"""

# WebGL & Canvas fingerprint spoofing
WEBGL_SPOOF_SCRIPT = """
(vendor, renderer, unmaskedVendor, unmaskedRenderer) => {
    const getParameter = WebGLRenderingContext.prototype.getParameter;
    const getExtension = WebGLRenderingContext.prototype.getExtension;

    WebGLRenderingContext.prototype.getParameter = function(parameter) {
        // UNMASKED_VENDOR_WEBGL
        if (parameter === 37445) {
            return unmaskedVendor || 'Intel Inc.';
        }
        // UNMASKED_RENDERER_WEBGL
        if (parameter === 37446) {
            return unmaskedRenderer || 'Intel Iris OpenGL Engine';
        }
        // VENDOR
        if (parameter === 7936) {
            return vendor || 'Intel Inc.';
        }
        // RENDERER
        if (parameter === 7937) {
            return renderer || 'Intel Iris OpenGL Engine';
        }
        return getParameter.call(this, parameter);
    };

    // WebGL2 support
    if (typeof WebGL2RenderingContext !== 'undefined') {
        const getParameter2 = WebGL2RenderingContext.prototype.getParameter;
        WebGL2RenderingContext.prototype.getParameter = function(parameter) {
            if (parameter === 37445) {
                return unmaskedVendor || 'Intel Inc.';
            }
            if (parameter === 37446) {
                return unmaskedRenderer || 'Intel Iris OpenGL Engine';
            }
            return getParameter2.call(this, parameter);
        };
    }
}
"""

# Canvas fingerprint noise injection (subtle, won't break functionality)
CANVAS_NOISE_SCRIPT = """
() => {
    const originalToDataURL = HTMLCanvasElement.prototype.toDataURL;
    const originalToBlob = HTMLCanvasElement.prototype.toBlob;

    HTMLCanvasElement.prototype.toDataURL = function(...args) {
        const ctx = this.getContext('2d');
        if (ctx) {
            // Add subtle noise to canvas fingerprint
            const imageData = ctx.getImageData(0, 0, this.width, this.height);
            for (let i = 0; i < imageData.data.length; i += 4) {
                imageData.data[i] += Math.floor(Math.random() * 3) - 1;
                imageData.data[i + 1] += Math.floor(Math.random() * 3) - 1;
                imageData.data[i + 2] += Math.floor(Math.random() * 3) - 1;
            }
            ctx.putImageData(imageData, 0, 0);
        }
        return originalToDataURL.apply(this, args);
    };

    HTMLCanvasElement.prototype.toBlob = function(callback, ...args) {
        const ctx = this.getContext('2d');
        if (ctx) {
            const imageData = ctx.getImageData(0, 0, this.width, this.height);
            for (let i = 0; i < imageData.data.length; i += 4) {
                imageData.data[i] += Math.floor(Math.random() * 3) - 1;
                imageData.data[i + 1] += Math.floor(Math.random() * 3) - 1;
                imageData.data[i + 2] += Math.floor(Math.random() * 3) - 1;
            }
            ctx.putImageData(imageData, 0, 0);
        }
        return originalToBlob.apply(this, [callback, ...args]);
    };
}
"""

# Audio context fingerprint spoofing
AUDIO_SPOOF_SCRIPT = """
() => {
    if (typeof AudioContext === 'undefined' && typeof webkitAudioContext === 'undefined') {
        return;
    }

    const AudioContextClass = window.AudioContext || window.webkitAudioContext;

    window.AudioContext = class extends AudioContextClass {
        constructor(...args) {
            super(...args);
            const originalCreateAnalyser = this.createAnalyser.bind(this);

            this.createAnalyser = () => {
                const analyser = originalCreateAnalyser();
                const originalGetFloatFrequencyData = analyser.getFloatFrequencyData;
                const originalGetByteFrequencyData = analyser.getByteFrequencyData;

                analyser.getFloatFrequencyData = function(array) {
                    originalGetFloatFrequencyData.call(this, array);
                    for (let i = 0; i < array.length; i++) {
                        array[i] += (Math.random() - 0.5) * 0.1;
                    }
                };

                analyser.getByteFrequencyData = function(array) {
                    originalGetByteFrequencyData.call(this, array);
                    for (let i = 0; i < array.length; i++) {
                        array[i] += Math.floor(Math.random() * 3) - 1;
                    }
                };

                return analyser;
            };
        }
    };
}
"""

# WAF bypass scripts for Cloudflare/Imperva
WAF_BYPASS_SCRIPT = """
() => {
    // 1. Spoof client hints (Chrome-specific)
    if (navigator.userAgentData) {
        const originalGetHighEntropyValues = navigator.userAgentData.getHighEntropyValues;
        navigator.userAgentData.getHighEntropyValues = async function(hints) {
            const result = await originalGetHighEntropyValues.call(this, hints);
            return {
                ...result,
                platform: 'Windows',
                platformVersion: '10.0.0',
                architecture: 'x86',
                model: '',
                uaFullVersion: '121.0.0.0',
                fullVersionList: [
                    { brand: 'Not_A Brand', version: '8.0.0.0' },
                    { brand: 'Chromium', version: '121.0.0.0' },
                    { brand: 'Google Chrome', version: '121.0.0.0' }
                ]
            };
        };
    }

    // 2. Mock Intl API for timezone consistency
    const originalDateTimeFormat = Intl.DateTimeFormat;
    Intl.DateTimeFormat = function(...args) {
        const dtf = new originalDateTimeFormat(...args);
        const originalResolvedOptions = dtf.resolvedOptions;
        dtf.resolvedOptions = function() {
            const options = originalResolvedOptions.call(this);
            return {
                ...options,
                timeZone: Intl.DateTimeFormat().resolvedOptions().timeZone
            };
        };
        return dtf;
    };
    Intl.DateTimeFormat.prototype = originalDateTimeFormat.prototype;

    // 3. Ensure consistent Date.toString output
    const originalDateToString = Date.prototype.toString;
    Date.prototype.toString = function() {
        const str = originalDateToString.call(this);
        // Remove any automation-related anomalies
        return str.replace(/Automation/g, '').replace(/Headless/g, '');
    };

    // 4. Mock battery API (remove if present)
    if (navigator.getBattery) {
        const originalGetBattery = navigator.getBattery;
        navigator.getBattery = async function() {
            return {
                charging: true,
                chargingTime: 0,
                dischargingTime: Infinity,
                level: 1.0
            };
        };
    }

    // 5. Ensure consistent screen properties
    Object.defineProperty(screen, 'orientation', {
        get: () => ({
            type: 'landscape-primary',
            angle: 0,
            onchange: null,
            addEventListener: () => {},
            removeEventListener: () => {}
        })
    });

    // 6. Mock media devices enumeration
    if (navigator.mediaDevices && navigator.mediaDevices.enumerateDevices) {
        const originalEnumerateDevices = navigator.mediaDevices.enumerateDevices;
        navigator.mediaDevices.enumerateDevices = async function() {
            const devices = await originalEnumerateDevices.call(this);
            // Return realistic device list
            return [
                { deviceId: '', kind: 'audioinput', label: '', groupId: 'audio-input-group' },
                { deviceId: '', kind: 'audiooutput', label: '', groupId: 'audio-output-group' },
                { deviceId: '', kind: 'videoinput', label: '', groupId: 'video-input-group' }
            ];
        };
    }
}
"""


# ============================================================================
# STEALTH INITIALIZATION & MANAGEMENT
# ============================================================================


class StealthConfig:
    """Configuration for stealth behavior."""

    def __init__(
        self,
        enable_core_stealth: bool = True,
        enable_webgl_spoof: bool = True,
        enable_canvas_noise: bool = True,
        enable_audio_spoof: bool = True,
        enable_waf_bypass: bool = True,
        randomize_fingerprints: bool = True,
        enable_behavior_simulation: bool = True,
    ):
        self.enable_core_stealth = enable_core_stealth
        self.enable_webgl_spoof = enable_webgl_spoof
        self.enable_canvas_noise = enable_canvas_noise
        self.enable_audio_spoof = enable_audio_spoof
        self.enable_waf_bypass = enable_waf_bypass
        self.randomize_fingerprints = randomize_fingerprints
        self.enable_behavior_simulation = enable_behavior_simulation


async def apply_enterprise_stealth(page: Page, config: StealthConfig | None = None) -> dict[str, bool]:
    """
    Apply comprehensive stealth modifications to hide all automation indicators.
    This is the enterprise-grade replacement for the basic apply_stealth_mode.

    Args:
        page: Playwright page instance
        config: Optional stealth configuration

    Returns:
        Dictionary of applied stealth modules and their success status
    """
    if config is None:
        config = StealthConfig()

    applied = {}

    try:
        # 1. Core stealth (always first)
        if config.enable_core_stealth:
            try:
                await page.add_init_script(STEALTH_CORE_SCRIPT)
                applied["core_stealth"] = True
            except Exception:
                applied["core_stealth"] = False

        # 2. WebGL spoof
        if config.enable_webgl_spoof:
            try:
                fingerprint = random.choice(WEBGL_FINGERPRINTS)
                await page.add_init_script(
                    WEBGL_SPOOF_SCRIPT,
                    fingerprint["vendor"],
                    fingerprint["renderer"],
                    fingerprint["unmasked_vendor"],
                    fingerprint["unmasked_renderer"],
                )
                applied["webgl_spoof"] = True
            except Exception:
                applied["webgl_spoof"] = False

        # 3. Canvas noise
        if config.enable_canvas_noise:
            try:
                await page.add_init_script(CANVAS_NOISE_SCRIPT)
                applied["canvas_noise"] = True
            except Exception:
                applied["canvas_noise"] = False

        # 4. Audio spoof
        if config.enable_audio_spoof:
            try:
                await page.add_init_script(AUDIO_SPOOF_SCRIPT)
                applied["audio_spoof"] = True
            except Exception:
                applied["audio_spoof"] = False

        # 5. WAF bypass
        if config.enable_waf_bypass:
            try:
                await page.add_init_script(WAF_BYPASS_SCRIPT)
                applied["waf_bypass"] = True
            except Exception:
                applied["waf_bypass"] = False

        # 6. CDP leak patches (critical — must run after all other scripts)
        try:
            from app.automation.stealth_cdp_patches import (
                ADVANCED_TIMING_PATCH,
                CDP_LEAK_PATCH_SCRIPT,
                TLS_FINGERPRINT_PATCH,
            )

            await page.add_init_script(CDP_LEAK_PATCH_SCRIPT)
            await page.add_init_script(TLS_FINGERPRINT_PATCH)
            await page.add_init_script(ADVANCED_TIMING_PATCH)
            applied["cdp_patches"] = True
        except Exception:
            applied["cdp_patches"] = False

        # 7. Set realistic viewport and user agent
        if config.randomize_fingerprints:
            try:
                screen_preset = random.choice(SCREEN_PRESETS)
                random.choice(LOCALE_PRESETS)

                # These are set at context creation time, but we can override some via JS
                await page.add_init_script(f"""
                    Object.defineProperty(screen, 'width', {{ get: () => {screen_preset['width']} }});
                    Object.defineProperty(screen, 'height', {{ get: () => {screen_preset['height']} }});
                    Object.defineProperty(screen, 'availWidth', {{ get: () => {screen_preset['avail_width']} }});
                    Object.defineProperty(screen, 'availHeight', {{ get: () => {screen_preset['avail_height']} }});
                    Object.defineProperty(screen, 'colorDepth', {{ get: () => {screen_preset['color_depth']} }});
                    Object.defineProperty(screen, 'pixelDepth', {{ get: () => {screen_preset['pixel_depth']} }});
                """)
                applied["screen_spoof"] = True
            except Exception:
                applied["screen_spoof"] = False

    except Exception:
        # Log error but don't fail the entire operation
        pass

    return applied


# ============================================================================
# WAF DETECTION & BYPASS STRATEGIES
# ============================================================================


class WAFType:
    """WAF detection identifiers."""

    CLOUDFLARE = "cloudflare"
    IMPERVA = "imperva"
    AKAMAI = "akamai"
    CUSTOM = "custom"
    NONE = "none"


async def detect_waf(page: Page) -> str:
    try:
        cookies = await page.context.cookies()
        cookie_names = [c["name"] for c in cookies]
        cookie_str = " ".join(cookie_names)

        # Cookie-based detection
        cf_cookie_markers = ["cf-browser", "cf-ray", "__cfduid", "cf_chl_opt", "cf_captcha", "cf_clearance", "__cf_bm"]
        imperva_cookie_markers = ["incap_ses_", "visid_incap_", "nlbi_"]
        akamai_cookie_markers = ["ak_bmsc", "bm_sz", "_abck"]

        for m in cf_cookie_markers:
            if m in cookie_str:
                return WAFType.CLOUDFLARE
        for m in imperva_cookie_markers:
            if m in cookie_str:
                return WAFType.IMPERVA
        for m in akamai_cookie_markers:
            if m in cookie_str:
                return WAFType.AKAMAI

        # Content-based detection
        content = await page.content()
        content_lower = content.lower()
        if any(
            m in content_lower
            for m in [
                "cf-browser-verification",
                "checking your browser",
                "just a moment",
                "enable javascript and cookies",
                "cf_chl_opt",
                "cloudflare",
            ]
        ):
            return WAFType.CLOUDFLARE
        if any(m in content_lower for m in ["incapsula", "imperva", "visid_incap"]):
            return WAFType.IMPERVA
        if any(m in content_lower for m in ["akamai", "ak_bmsc", "_abck"]):
            return WAFType.AKAMAI

        # URL-based detection
        url = page.url
        if "cdn-cgi" in url or "challenge" in url:
            return WAFType.CLOUDFLARE

        return WAFType.NONE
    except Exception:
        return WAFType.NONE


async def handle_cloudflare_challenge(page: Page, timeout_seconds: float = 30.0) -> bool:
    try:
        start_time = time.time()
        from app.automation.stealth import simulate_human_behavior

        while time.time() - start_time < timeout_seconds:
            current_url = page.url
            content = await page.content()
            content_lower = content.lower()

            is_challenge = (
                "cdn-cgi" in current_url
                or "challenge" in current_url
                or "just a moment" in content_lower
                or "checking your browser" in content_lower
                or "cf-browser-verification" in content_lower
            )

            if not is_challenge:
                return True

            # Simulate human presence while waiting
            try:
                await simulate_human_behavior(page, duration=0.5)
            except Exception:
                pass

            # Try clicking the Turnstile checkbox if present
            try:
                turnstile = await page.query_selector('iframe[src*="challenges.cloudflare.com"]')
                if turnstile:
                    box = await turnstile.bounding_box()
                    if box:
                        click_x = box["x"] + 30 + random.uniform(-3, 3)
                        click_y = box["y"] + box["height"] / 2 + random.uniform(-3, 3)
                        await page.mouse.click(click_x, click_y)
                        await asyncio.sleep(random.uniform(2.0, 4.0))
                        continue
            except Exception:
                pass

            await asyncio.sleep(random.uniform(1.5, 3.0))

        return False
    except Exception:
        return False


# ============================================================================
# UTILITY FUNCTIONS
# ============================================================================


def get_random_user_agent(browser_type: str = "chrome_windows") -> str:
    """Get a random user agent from the specified pool."""
    pool = USER_AGENT_POOL.get(browser_type, USER_AGENT_POOL["chrome_windows"])
    return random.choice(pool)


def get_random_screen_preset() -> dict[str, int]:
    """Get a random screen configuration."""
    return random.choice(SCREEN_PRESETS)


def get_random_locale_preset() -> dict[str, Any]:
    """Get a random locale and timezone configuration."""
    return random.choice(LOCALE_PRESETS)


def get_random_webgl_fingerprint() -> dict[str, str]:
    """Get a random WebGL fingerprint configuration."""
    return random.choice(WEBGL_FINGERPRINTS)

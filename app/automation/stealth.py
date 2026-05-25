# -*- coding: utf-8 -*-
"""
Stealth utilities — masks all Playwright/automation indicators.
Drop-in replacement; all original public names preserved.
Uses common stealth scripts to avoid duplication.
"""

import asyncio
import random
from typing import Dict
from playwright.async_api import Page

from app.automation.stealth_common import (
    build_core_stealth_script,
)


# ---------------------------------------------------------------------------
# Fingerprint pools (kept for backward compatibility)
# ---------------------------------------------------------------------------

_UA_POOL = [
    ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36", "win", "124"),
    ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36", "mac", "123"),
    ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36", "win", "122"),
    ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36 Edg/124.0.0.0", "win", "124"),
]

_VIEWPORTS = [
    {"width": 1366, "height": 768},
    {"width": 1440, "height": 900},
    {"width": 1536, "height": 864},
    {"width": 1920, "height": 1080},
    {"width": 1280, "height": 800},
]

_WEBGL = [
    {"vendor": "Google Inc. (Intel)", "renderer": "ANGLE (Intel, Intel(R) UHD Graphics 620 Direct3D11 vs_5_0 ps_5_0, D3D11)"},
    {"vendor": "Google Inc. (NVIDIA)", "renderer": "ANGLE (NVIDIA, NVIDIA GeForce GTX 1650 Direct3D11 vs_5_0 ps_5_0, D3D11)"},
    {"vendor": "Google Inc. (AMD)", "renderer": "ANGLE (AMD, AMD Radeon RX 580 Direct3D11 vs_5_0 ps_5_0, D3D11)"},
    {"vendor": "Apple", "renderer": "Apple M1"},
]


def _pick_fingerprint() -> Dict:
    """Pick a random fingerprint configuration."""
    ua = random.choice(_UA_POOL)
    return {
        "ua": ua[0],
        "viewport": random.choice(_VIEWPORTS),
        "webgl": random.choice(_WEBGL),
        "hw_concurrency": random.choice([4, 8, 12, 16]),
        "device_memory": random.choice([4, 8, 16]),
    }


def _build_init_script(fp: Dict) -> str:
    """
    Build stealth initialization script.
    Uses common script from stealth_common module.
    
    Args:
        fp: Fingerprint dictionary
        
    Returns:
        JavaScript stealth script
    """
    return build_core_stealth_script(
        webgl_vendor=fp["webgl"]["vendor"],
        webgl_renderer=fp["webgl"]["renderer"],
        hw_concurrency=fp["hw_concurrency"],
        device_memory=fp["device_memory"],
    )


# ---------------------------------------------------------------------------
# Public API — same names as original, no import changes needed elsewhere
# ---------------------------------------------------------------------------

async def apply_stealth_mode(page: Page) -> None:
    """
    Apply full stealth fingerprint to a page. Must be called before navigation.
    
    Args:
        page: Playwright page instance
    """
    fp = _pick_fingerprint()
    await page.add_init_script(_build_init_script(fp))


def get_random_user_agent() -> str:
    """Get a random user agent from the pool."""
    return random.choice(_UA_POOL)[0]


def get_random_viewport() -> dict:
    """Get a random viewport configuration."""
    return random.choice(_VIEWPORTS)


async def add_random_delay(_page: Page, min_seconds: float = 0.5, max_seconds: float = 2.0) -> None:
    """Add random delay for human-like behavior."""
    await asyncio.sleep(random.uniform(min_seconds, max_seconds))


async def human_like_typing(
    page: Page, selector: str, text: str,
    min_delay: float = 0.04, max_delay: float = 0.13
) -> None:
    """
    Type text with human-like delays.
    
    Args:
        page: Playwright page
        selector: Element selector
        text: Text to type
        min_delay: Minimum delay between characters
        max_delay: Maximum delay between characters
    """
    element = await page.wait_for_selector(selector, state="visible", timeout=10000)
    await element.click()
    await asyncio.sleep(random.uniform(0.15, 0.4))
    for char in text:
        await element.press(char)
        delay = random.uniform(min_delay, max_delay)
        if char in ".,!? ":
            delay += random.uniform(0.05, 0.15)
        await asyncio.sleep(delay)


async def human_like_mouse_movement(page: Page, target_selector: str) -> None:
    """
    Move mouse to target using cubic bezier curve.
    
    Args:
        page: Playwright page
        target_selector: Element selector to move to
    """
    try:
        element = await page.wait_for_selector(target_selector, state="visible", timeout=5000)
        box = await element.bounding_box()
        if not box:
            return
        sx, sy = random.randint(80, 400), random.randint(80, 400)
        ex = box["x"] + box["width"] / 2 + random.uniform(-4, 4)
        ey = box["y"] + box["height"] / 2 + random.uniform(-4, 4)
        cp1x = sx + (ex - sx) * 0.3 + random.uniform(-40, 40)
        cp1y = sy + (ey - sy) * 0.1 + random.uniform(-40, 40)
        cp2x = sx + (ex - sx) * 0.7 + random.uniform(-40, 40)
        cp2y = sy + (ey - sy) * 0.9 + random.uniform(-40, 40)
        steps = random.randint(18, 30)
        for i in range(1, steps + 1):
            t = i / steps
            u = 1 - t
            x = u**3*sx + 3*u**2*t*cp1x + 3*u*t**2*cp2x + t**3*ex
            y = u**3*sy + 3*u**2*t*cp1y + 3*u*t**2*cp2y + t**3*ey
            await page.mouse.move(x, y)
            await asyncio.sleep(random.uniform(0.008, 0.022))
        await page.mouse.move(ex, ey)
    except Exception:
        pass


async def random_scroll(page: Page) -> None:
    """Random scroll for human-like behavior."""
    try:
        amount = random.randint(60, 220)
        await page.mouse.wheel(0, amount)
        await asyncio.sleep(random.uniform(0.12, 0.35))
        await page.mouse.wheel(0, -(amount // 2))
    except Exception:
        pass


async def simulate_human_behavior(page: Page, duration: float = 1.0) -> None:
    """
    Simulate human browsing behavior.
    
    Args:
        page: Playwright page
        duration: Duration in seconds
    """
    for _ in range(random.randint(2, 4)):
        await page.mouse.move(random.randint(100, 900), random.randint(100, 700))
        await asyncio.sleep(random.uniform(0.08, 0.3))
    for _ in range(random.randint(1, 2)):
        await random_scroll(page)
        await asyncio.sleep(random.uniform(0.15, 0.5))

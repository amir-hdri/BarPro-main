"""
Enterprise-Grade Human-Like Interaction System
================================================
Simulates realistic human behavior to avoid bot detection.
Includes advanced typing, mouse movement, timing, and behavioral patterns.
"""

import asyncio
import random
import time

from playwright.async_api import Page

# ============================================================================
# HUMAN-LIKE TYPING ENGINE
# ============================================================================


class TypingProfile:
    """Simulates different human typing profiles."""

    # Typing speeds (characters per minute) - OPTIMIZED FOR SPEED
    SLOW = {"min_delay": 0.02, "max_delay": 0.06, "name": "slow"}
    AVERAGE = {"min_delay": 0.01, "max_delay": 0.04, "name": "average"}
    FAST = {"min_delay": 0.005, "max_delay": 0.02, "name": "fast"}

    # Special patterns
    HUNT_AND_PECK = {"min_delay": 0.03, "max_delay": 0.08, "name": "hunt_and_peck"}
    PROFESSIONAL = {"min_delay": 0.002, "max_delay": 0.01, "name": "professional"}


async def human_type(
    page: Page,
    selector: str,
    text: str,
    profile: dict[str, float] = TypingProfile.AVERAGE,
    add_typos: bool = False,
    typo_chance: float = 0.02,
    pause_on_punctuation: bool = True,
    pause_on_capitals: bool = True,
    random_hesitation: bool = True,
) -> None:
    """
    Type text with realistic human-like delays and patterns.

    Args:
        page: Playwright page instance
        selector: Target element selector
        text: Text to type
        profile: Typing speed profile
        add_typos: Simulate occasional typos and corrections
        typo_chance: Probability of making a typo (0-1)
        pause_on_punctuation: Add longer delays for punctuation
        pause_on_capitals: Add delays for shift+capital letters
        random_hesitation: Add random hesitation pauses
    """
    element = await page.wait_for_selector(selector, state="visible", timeout=10000)
    await element.click()

    # Initial pause before typing (human thinks before typing)
    await asyncio.sleep(random.uniform(0.05, 0.15))

    min_delay = profile["min_delay"]
    max_delay = profile["max_delay"]

    i = 0
    while i < len(text):
        char = text[i]

        # Check for typo simulation
        if add_typos and random.random() < typo_chance and char.isalpha():
            # Type wrong character, then backspace and correct
            wrong_char = _generate_wrong_char(char)
            await element.press(wrong_char)
            await asyncio.sleep(random.uniform(0.15, 0.35))  # Realize mistake

            # Backspace
            await element.press("Backspace")
            await asyncio.sleep(random.uniform(0.10, 0.25))  # Think

            # Type correct character
            await element.press(char)
            i += 1
        else:
            # Normal typing with variable delays
            delay = _calculate_typing_delay(
                char, min_delay, max_delay, pause_on_punctuation, pause_on_capitals, random_hesitation
            )
            await element.press(char)
            await asyncio.sleep(delay)
            i += 1

    # Final pause after typing (human reviews what they typed)
    await asyncio.sleep(random.uniform(0.05, 0.1))


def _calculate_typing_delay(
    char: str,
    min_delay: float,
    max_delay: float,
    pause_on_punctuation: bool,
    pause_on_capitals: bool,
    random_hesitation: bool,
) -> float:
    """Calculate realistic delay for typing a character."""
    base_delay = random.uniform(min_delay, max_delay)

    # Punctuation causes longer delays (thinking about sentence structure)
    if pause_on_punctuation and char in ".,;:!?\"'()[]{}":
        base_delay *= random.uniform(1.5, 3.0)

    # Capital letters cause slight delays (shift key)
    if pause_on_capitals and char.isupper():
        base_delay *= random.uniform(1.2, 1.8)

    # Space bar is usually faster
    if char == " ":
        base_delay *= random.uniform(0.5, 0.9)

    # Random hesitation (human-like pauses)
    if random_hesitation and random.random() < 0.05:  # 5% chance
        base_delay += random.uniform(0.3, 1.2)  # Longer hesitation

    # Word boundary pauses (after spaces)
    if char == " ":
        base_delay += random.uniform(0.05, 0.15)

    return max(0.01, base_delay)


def _generate_wrong_char(correct_char: str) -> str:
    """Generate a wrong character close to the correct one (keyboard proximity)."""
    keyboard_layout = {
        "q": "qwertasdfgzxcvb",
        "w": "qwertasdfgsdxcv",
        "e": "wertdfsrfcvbg",
        "r": "ertydfgvcbh",
        "t": "tyrtfgvhn",
        "y": "yutghbnjm",
        "u": "uiyhjnmk",
        "i": "iojnmk,l",
        "o": "opkml,.",
        "p": "pol;./",
        "a": "aqwsxzdecfrv",
        "s": "swaqxdecfrvgt",
        "d": "desrfcvgt",
        "f": "fdertgbvhn",
        "g": "gftybhnjm",
        "h": "hgyujnmk",
        "j": "jhuikm,l",
        "k": "kjio l,./",
        "l": "lkop;./",
        "z": "zaxscdefvb",
        "x": "xzsd cvfgb",
        "c": "cxdfvbg",
        "v": "vcfgbhn",
        "b": "bvgtnh",
        "n": "nbhjm",
        "m": "mnjk,",
    }

    lower_char = correct_char.lower()
    if lower_char in keyboard_layout:
        neighbors = keyboard_layout[lower_char]
        wrong = random.choice(neighbors)
        return wrong.upper() if correct_char.isupper() else wrong

    return correct_char


# ============================================================================
# ADVANCED MOUSE MOVEMENT ENGINE
# ============================================================================


class MouseMovementEngine:
    """Generates human-like mouse movement patterns."""

    @staticmethod
    async def move_to_element(
        page: Page,
        selector: str,
        steps: int = 15,
        use_bezier: bool = True,
        add_wobble: bool = True,
        hover_before_click: bool = True,
    ) -> tuple[float, float] | None:
        """
        Move mouse to element with realistic human movement.

        Args:
            page: Playwright page instance
            selector: Target element selector
            steps: Number of intermediate movement points
            use_bezier: Use bezier curve for natural movement
            add_wobble: Add slight wobble (hand tremor simulation)
            hover_before_click: Pause briefly before clicking

        Returns:
            Target coordinates or None if failed
        """
        try:
            element = await page.wait_for_selector(selector, state="visible", timeout=5000)
            box = await element.bounding_box()

            if not box:
                return None

            # Calculate target position (center of element with slight random offset)
            target_x = box["x"] + box["width"] / 2 + random.uniform(-3, 3)
            target_y = box["y"] + box["height"] / 2 + random.uniform(-3, 3)

            # Get current mouse position (or use random starting point)
            start_x = random.randint(100, 400)
            start_y = random.randint(100, 400)

            # Generate movement path
            if use_bezier:
                path = _generate_bezier_path(start_x, start_y, target_x, target_y, steps)
            else:
                path = _generate_linear_path(start_x, start_y, target_x, target_y, steps)

            # Execute movement with variable speed
            for i, (x, y) in enumerate(path):
                # Add wobble for realism
                if add_wobble:
                    wobble_x = random.uniform(-2, 2)
                    wobble_y = random.uniform(-2, 2)
                    x += wobble_x
                    y += wobble_y

                await page.mouse.move(x, y)

                # Variable speed: faster in middle, slower at start/end
                t = i / max(1, len(path) - 1)
                delay = _calculate_mouse_delay(t)
                await asyncio.sleep(delay)

            # Hover pause before click (human behavior)
            if hover_before_click:
                await asyncio.sleep(random.uniform(0.05, 0.1))

            return (target_x, target_y)

        except Exception:
            return None

    @staticmethod
    async def click_element(
        page: Page,
        selector: str,
        use_human_movement: bool = True,
        wait_for_navigation: bool = False,
    ) -> bool:
        """
        Click element with human-like mouse behavior.

        Args:
            page: Playwright page instance
            selector: Target element selector
            use_human_movement: Use realistic mouse movement
            wait_for_navigation: Wait for page navigation after click

        Returns:
            True if click was successful
        """
        try:
            element = await page.wait_for_selector(selector, state="visible", timeout=5000)

            if use_human_movement:
                # Move mouse to element
                target = await MouseMovementEngine.move_to_element(page, selector, hover_before_click=True)

                if target:
                    # Perform click
                    if wait_for_navigation:
                        async with page.expect_navigation(timeout=15000):
                            await page.mouse.click(target[0], target[1])
                    else:
                        await page.mouse.click(target[0], target[1])

                    # Post-click pause
                    await asyncio.sleep(random.uniform(0.05, 0.15))
                    return True
            else:
                # Direct click with small random offset
                box = await element.bounding_box()
                if box:
                    x = box["x"] + box["width"] / 2 + random.uniform(-2, 2)
                    y = box["y"] + box["height"] / 2 + random.uniform(-2, 2)

                    if wait_for_navigation:
                        async with page.expect_navigation(timeout=15000):
                            await page.mouse.click(x, y)
                    else:
                        await page.mouse.click(x, y)

                    await asyncio.sleep(random.uniform(0.05, 0.15))
                    return True

            return False

        except Exception:
            return False


def _generate_bezier_path(
    start_x: float, start_y: float, end_x: float, end_y: float, steps: int
) -> list[tuple[float, float]]:
    """Generate cubic bezier curve path for mouse movement."""
    # Control points for natural curve
    dx = end_x - start_x
    dy = end_y - start_y

    # Random control point offset for curve variation
    offset_x = random.uniform(-100, 100)
    offset_y = random.uniform(-100, 100)

    cp1_x = start_x + dx * 0.3 + offset_x
    cp1_y = start_y + dy * 0.3 + offset_y
    cp2_x = start_x + dx * 0.7 + offset_x
    cp2_y = start_y + dy * 0.7 + offset_y

    path = []
    for i in range(steps + 1):
        t = i / steps

        # Cubic bezier formula
        x = (1 - t) ** 3 * start_x + 3 * (1 - t) ** 2 * t * cp1_x + 3 * (1 - t) * t**2 * cp2_x + t**3 * end_x
        y = (1 - t) ** 3 * start_y + 3 * (1 - t) ** 2 * t * cp1_y + 3 * (1 - t) * t**2 * cp2_y + t**3 * end_y

        path.append((x, y))

    return path


def _generate_linear_path(
    start_x: float, start_y: float, end_x: float, end_y: float, steps: int
) -> list[tuple[float, float]]:
    """Generate linear path with slight wobble."""
    path = []
    for i in range(steps + 1):
        t = i / steps
        x = start_x + (end_x - start_x) * t + random.uniform(-5, 5)
        y = start_y + (end_y - start_y) * t + random.uniform(-5, 5)
        path.append((x, y))
    return path


def _calculate_mouse_delay(t: float) -> float:
    """
    Calculate mouse movement delay based on position in path.
    Humans move faster in the middle and slower at start/end.
    """
    # Parabolic speed curve: slower at edges, faster in middle
    speed_factor = 1.0 - 0.6 * (1 - 4 * (t - 0.5) ** 2)
    base_delay = random.uniform(0.001, 0.005)
    return base_delay / max(0.3, speed_factor)


# ============================================================================
# HUMAN BEHAVIOR SIMULATION
# ============================================================================


class HumanBehaviorSimulator:
    """Simulates comprehensive human browsing behavior."""

    def __init__(self, page: Page):
        self.page = page

    async def simulate_reading(self, duration_seconds: float = 2.0) -> None:
        """Simulate reading page content with eye movement patterns."""
        start_time = time.time()

        while time.time() - start_time < duration_seconds:
            # Random small mouse movements (eye tracking simulation)
            x = random.randint(100, 800)
            y = random.randint(100, 600)
            await self.page.mouse.move(x, y)
            await asyncio.sleep(random.uniform(0.3, 1.2))

            # Occasional scroll
            if random.random() < 0.3:
                scroll_amount = random.randint(20, 100)
                await self.page.mouse.wheel(0, scroll_amount)
                await asyncio.sleep(random.uniform(0.2, 0.5))

    async def simulate_thinking(self, min_seconds: float = 1.0, max_seconds: float = 3.0) -> None:
        """Simulate thinking pause with minimal mouse movement."""
        duration = random.uniform(min_seconds, max_seconds)
        start_time = time.time()

        while time.time() - start_time < duration:
            # Very small, slow movements
            if random.random() < 0.2:
                x = random.randint(300, 500)
                y = random.randint(200, 400)
                await self.page.mouse.move(x, y)

            await asyncio.sleep(random.uniform(0.5, 1.5))

    async def simulate_form_filling_behavior(self) -> None:
        """Simulate natural form interaction patterns."""
        # Look at form fields
        await self.simulate_reading(duration_seconds=random.uniform(0.5, 1.5))

        # Small scroll to see more of form
        await self.page.mouse.wheel(0, random.randint(30, 80))
        await asyncio.sleep(random.uniform(0.2, 0.5))

        # Move mouse toward form area
        target_x = random.randint(200, 600)
        target_y = random.randint(150, 400)
        await self.page.mouse.move(target_x, target_y)
        await asyncio.sleep(random.uniform(0.3, 0.8))


# ============================================================================
# TIMING & DELAY UTILITIES
# ============================================================================


class HumanTiming:
    """Manages realistic timing between actions."""

    @staticmethod
    async def random_delay(min_seconds: float = 0.5, max_seconds: float = 2.0, distribution: str = "uniform") -> None:
        """
        Add random delay with different distribution options.

        Args:
            min_seconds: Minimum delay
            max_seconds: Maximum delay
            distribution: 'uniform', 'exponential', or 'normal'
        """
        if distribution == "uniform":
            delay = random.uniform(min_seconds, max_seconds)
        elif distribution == "exponential":
            # Exponential distribution (more short delays, some long ones)
            lambda_param = 1.0 / ((max_seconds - min_seconds) / 2)
            delay = min_seconds + random.expovariate(lambda_param)
            delay = min(delay, max_seconds)
        elif distribution == "normal":
            # Normal distribution around midpoint
            midpoint = (min_seconds + max_seconds) / 2
            std_dev = (max_seconds - min_seconds) / 6
            delay = random.gauss(midpoint, std_dev)
            delay = max(min_seconds, min(max_seconds, delay))
        else:
            delay = random.uniform(min_seconds, max_seconds)

        await asyncio.sleep(delay)

    @staticmethod
    async def action_delay(action_type: str = "default") -> None:
        """
        Pre-configured delays for different action types.

        Args:
            action_type: Type of action ('page_load', 'click', 'form_fill', 'submit', 'default')
        """
        delays = {
            "page_load": (0.2, 0.5),
            "click": (0.1, 0.3),
            "form_fill": (0.1, 0.4),
            "submit": (0.2, 0.6),
            "default": (0.1, 0.4),
            "captcha_solve": (0.5, 1.5),
            "navigation": (0.3, 0.8),
        }

        min_delay, max_delay = delays.get(action_type, delays["default"])
        await HumanTiming.random_delay(min_delay, max_delay)


# ============================================================================
# CONVENIENCE WRAPPERS
# ============================================================================


async def type_with_human_delays(page: Page, selector: str, text: str, speed: str = "average") -> None:
    """Convenience wrapper for human-like typing."""
    profiles = {
        "slow": TypingProfile.SLOW,
        "average": TypingProfile.AVERAGE,
        "fast": TypingProfile.FAST,
        "hunt_and_peck": TypingProfile.HUNT_AND_PECK,
        "professional": TypingProfile.PROFESSIONAL,
    }

    profile = profiles.get(speed, TypingProfile.AVERAGE)
    await human_type(page, selector, text, profile=profile)


async def click_with_human_movement(page: Page, selector: str, wait_for_navigation: bool = False) -> bool:
    """Convenience wrapper for human-like clicking."""
    return await MouseMovementEngine.click_element(page, selector, wait_for_navigation=wait_for_navigation)


async def wait_like_human(min_seconds: float = 1.0, max_seconds: float = 3.0) -> None:
    """Convenience wrapper for human-like waiting."""
    await HumanTiming.random_delay(min_seconds, max_seconds)

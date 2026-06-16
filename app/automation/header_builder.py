"""
Enterprise-Grade Header Builder
=================================
Builds realistic HTTP headers based on browser fingerprint and context.
Ensures header consistency and prevents fingerprinting through headers.
"""

import logging
import random
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass
class HeaderContext:
    """Context for header building"""

    url: str = ""
    referer: str = ""
    is_navigation: bool = True
    is_ajax: bool = False
    accept_language: str | None = None
    locale: str | None = None


class HeaderBuilder:
    """
    Advanced HTTP header builder that creates realistic, consistent headers.

    Features:
    - Fingerprint-consistent headers
    - Realistic Accept headers
    - Proper Sec-* headers for modern browsers
    - Referer chain support
    - Cookie handling
    - Connection optimization headers
    """

    # Accept header variants (real browsers)
    ACCEPT_VARIANTS = [
        # Chrome 124+
        "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7",
        # Chrome 123
        "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/png,image/svg+xml,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7",
        # Chrome with less image support
        "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
        # Edge
        "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7",
        # Firefox style
        "text/html,application/xhtml+xml;q=0.9,image/webp,*/*;q=0.8",
    ]

    # Accept-Encoding variants
    ACCEPT_ENCODING_VARIANTS = [
        "gzip, deflate, br",
        "gzip, deflate, lzma, sdch, br",
        "gzip, deflate",
        "br",
    ]

    # Sec-CH-UA variants (Chrome 120+)
    SEC_CH_UA_VARIANTS = [
        '"Chromium";v="124", "Google Chrome";v="124", "Not.A/Brand";v="99"',
        '"Chromium";v="123", "Google Chrome";v="123", "Not.A/Brand";v="99"',
        '"Not_A Brand";v="8", "Chromium";v="120", "Google Chrome";v="120"',
        '"Google Chrome";v="121", "Chromium";v="121", "Not_A-Brand";v="24"',
    ]

    # Sec-CH-UA-Platform variants
    SEC_CH_UA_PLATFORM_VARIANTS = {
        "Windows": '"Windows"',
        "macOS": '"macOS"',
        "Macintosh": '"Macintosh"',
        "Linux": '"Linux"',
        "Android": '"Android"',
        "iPad": '"iPad"',
        "iPhone": '"iPhone"',
    }

    # Sec-Fetch-* headers based on context
    SEC_FETCH_HEADERS = {
        "navigation": {
            "Sec-Fetch-Dest": "document",
            "Sec-Fetch-Mode": "navigate",
            "Sec-Fetch-Site": "none",
            "Sec-Fetch-User": "?1",
        },
        "same-origin": {
            "Sec-Fetch-Dest": "empty",
            "Sec-Fetch-Mode": "cors",
            "Sec-Fetch-Site": "same-origin",
        },
        "cross-site": {
            "Sec-Fetch-Dest": "empty",
            "Sec-Fetch-Mode": "cors",
            "Sec-Fetch-Site": "cross-site",
        },
        "nested-navigation": {
            "Sec-Fetch-Dest": "document",
            "Sec-Fetch-Mode": "navigate",
            "Sec-Fetch-Site": "same-origin",
            "Sec-Fetch-User": "?1",
        },
    }

    # Connection headers
    CONNECTION_HEADERS = [
        "keep-alive",
    ]

    # Upgrade-Insecure-Requests (always 1 for navigation)
    UPGRADE_INSECURE_REQUESTS = "1"

    # Cache-Control variants
    CACHE_CONTROL_VARIANTS = [
        "max-age=0",
        "no-cache",
        "no-cache, no-store, must-revalidate",
    ]

    # Pragma variants
    PRAGMA_VARIANTS = [
        "no-cache",
        "",
    ]

    def __init__(self):
        """Initialize header builder"""
        self._request_count = 0

    def build(
        self,
        user_agent: str,
        platform: str = "Win32",
        language: str = "en-US",
        timezone: str = "America/New_York",
        accept_language: str | None = None,
        referer: str = "",
        is_navigation: bool = True,
        is_ajax: bool = False,
        include_sec_headers: bool = True,
        include_cache_headers: bool = True,
    ) -> dict[str, str]:
        """
        Build complete HTTP headers based on fingerprint.

        Args:
            user_agent: Browser user agent string
            platform: Platform identifier (Win32, MacIntel, etc.)
            language: Primary language code (en-US, fa-IR, etc.)
            timezone: Timezone identifier
            accept_language: Override for Accept-Language header
            referer: Referrer URL
            is_navigation: Whether this is a page navigation
            is_ajax: Whether this is an AJAX request
            include_sec_headers: Include Sec-* headers
            include_cache_headers: Include cache control headers

        Returns:
            Dictionary of HTTP headers
        """
        self._request_count += 1

        # Detect browser type
        is_firefox = "Firefox" in user_agent
        is_edge = "Edg/" in user_agent
        is_chrome = "Chrome/" in user_agent and "Edg/" not in user_agent

        # Build base headers
        headers = {
            "User-Agent": user_agent,
            "Accept": random.choice(self.ACCEPT_VARIANTS),
            "Accept-Language": accept_language or self._build_accept_language(language),
            "Accept-Encoding": random.choice(self.ACCEPT_ENCODING_VARIANTS),
            "Connection": random.choice(self.CONNECTION_HEADERS),
        }

        # Add navigation-specific headers
        if is_navigation:
            headers["Upgrade-Insecure-Requests"] = self.UPGRADE_INSECURE_REQUESTS

            # Sec-Fetch-* headers
            if referer:
                fetch_headers = self.SEC_FETCH_HEADERS.get("same-origin", {})
                if "cross-site" in referer:
                    fetch_headers = self.SEC_FETCH_HEADERS.get("cross-site", {})
            else:
                fetch_headers = self.SEC_FETCH_HEADERS.get("navigation", {})

            headers.update(fetch_headers)

        # Add cache headers (only for navigation)
        if include_cache_headers and is_navigation:
            headers["Cache-Control"] = random.choice(self.CACHE_CONTROL_VARIANTS)
            headers["Pragma"] = random.choice(self.PRAGMA_VARIANTS)

        # Add referer
        if referer:
            headers["Referer"] = referer

        # Add Sec-* headers for Chrome/Edge
        if include_sec_headers and (is_chrome or is_edge):
            headers.update(
                self._build_sec_headers(
                    platform=platform,
                    is_firefox=is_firefox,
                )
            )

        # Add DNT if timezone suggests privacy-conscious user
        if random.random() < 0.15:  # 15% of requests
            headers["DNT"] = "1"

        # Additional headers for realism
        headers.update(
            self._build_additional_headers(
                user_agent=user_agent,
                platform=platform,
            )
        )

        return headers

    def _build_accept_language(self, language: str) -> str:
        """Build Accept-Language header with language variants"""
        # Parse language code
        primary = language.split("-")[0].lower()

        # Generate language list based on primary language
        if primary == "en":
            variants = ["en-US", "en-GB", "en"]
        elif primary == "fa":
            variants = ["fa-IR", "fa", "en-US", "en"]
        elif primary == "de":
            variants = ["de-DE", "de", "en-US", "en"]
        elif primary == "fr":
            variants = ["fr-FR", "fr", "en-US", "en"]
        elif primary == "es":
            variants = ["es-ES", "es", "en-US", "en"]
        elif primary == "ja":
            variants = ["ja-JP", "ja", "en-US", "en"]
        elif primary == "ko":
            variants = ["ko-KR", "ko", "en-US", "en"]
        elif primary == "zh":
            variants = ["zh-CN", "zh-TW", "zh", "en-US", "en"]
        elif primary == "ru":
            variants = ["ru-RU", "ru", "en-US", "en"]
        elif primary == "ar":
            variants = ["ar-SA", "ar", "en-US", "en"]
        else:
            variants = [language, "en-US", "en"]

        # Format with quality values
        quality_values = [1.0, 0.9, 0.8, 0.7]
        formatted = []

        for i, lang in enumerate(variants[:4]):
            q = quality_values[i] if i < len(quality_values) else 0.5
            formatted.append(f"{lang};q={q}")

        return ",".join(formatted)

    def _build_sec_headers(
        self,
        platform: str,
        is_firefox: bool,
    ) -> dict[str, str]:
        """Build Sec-* headers for modern browsers"""
        headers = {}

        if is_firefox:
            # Firefox doesn't use Sec-CH-UA headers
            headers.update(
                {
                    "Sec-Fetch-Dest": "document",
                    "Sec-Fetch-Mode": "navigate",
                    "Sec-Fetch-Site": "none",
                    "Sec-Fetch-User": "?1",
                }
            )
            return headers

        # Chrome/Edge Sec-CH-UA headers
        headers["Sec-CH-UA"] = random.choice(self.SEC_CH_UA_VARIANTS)
        headers["Sec-CH-UA-Mobile"] = "?0"  # Desktop
        headers["Sec-CH-UA-Platform"] = self.SEC_CH_UA_PLATFORM_VARIANTS.get(
            platform.split()[0] if platform else "Windows", '"Windows"'
        )

        # Additional Sec-* headers
        headers["Sec-Fetch-Dest"] = "document"
        headers["Sec-Fetch-Mode"] = "navigate"
        headers["Sec-Fetch-Site"] = "none"
        headers["Sec-Fetch-User"] = "?1"

        return headers

    def _build_additional_headers(
        self,
        user_agent: str,
        platform: str,
    ) -> dict[str, str]:
        """Build additional headers for realism"""
        headers = {}

        # Host header (would be set by request, but good to have in context)
        # This is informational only

        # X-Forwarded-For (simulated - in reality this is set by proxy/load balancer)
        if random.random() < 0.05:  # 5% chance
            headers["X-Forwarded-For"] = self._generate_ip()

        # X-Client-IP
        if random.random() < 0.03:
            headers["X-Client-IP"] = self._generate_ip()

        # CF-Connecting-IP (Cloudflare)
        if random.random() < 0.02:
            headers["CF-Connecting-IP"] = self._generate_ip()

        # True-Client-IP (Akamai)
        if random.random() < 0.01:
            headers["True-Client-IP"] = self._generate_ip()

        # Additional Chrome-specific headers
        if "Chrome/" in user_agent:
            if random.random() < 0.1:
                headers["Sec-Ch-Ua-Bitness"] = '"64"'
            if random.random() < 0.1:
                headers["Sec-Ch-Ua-Platform-Version"] = '"10.0"'

        # Strict-Transport-Security (if HTTPS)
        if random.random() < 0.05:
            headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"

        return headers

    def _generate_ip(self) -> str:
        """Generate a realistic public IP address"""
        # Common ISP ranges
        prefixes = [
            "72.",
            "98.",
            "67.",
            "73.",
            "71.",
            "99.",  # Comcast
            "184.",
            "162.",
            "173.",  # Time Warner
            "104.",
            "172.",  # Cloudflare, AWS
            "208.",
            "65.",  # Various ISPs
            "192.",
            "198.",
            "174.",
        ]

        prefix = random.choice(prefixes)
        return f"{prefix}{random.randint(1, 254)}.{random.randint(0, 255)}.{random.randint(1, 254)}"

    def build_for_request(
        self,
        user_agent: str,
        url: str,
        method: str = "GET",
        existing_headers: dict[str, str] | None = None,
    ) -> dict[str, str]:
        """
        Build headers optimized for a specific request.

        Args:
            user_agent: Browser user agent
            url: Request URL
            method: HTTP method
            existing_headers: Existing headers to merge with

        Returns:
            Complete headers dictionary
        """
        headers = self.build(user_agent=user_agent)

        # Parse URL for context
        parsed_url = self._parse_url(url)

        # Add host header
        headers["Host"] = parsed_url.get("host", "")

        # Add Origin header
        if parsed_url.get("scheme"):
            origin = f"{parsed_url['scheme']}://{parsed_url['host']}"
            headers["Origin"] = origin

            # Add same-origin headers if same domain
            if existing_headers:
                existing_origin = existing_headers.get("Origin")
                if existing_origin == origin:
                    headers["Sec-Fetch-Site"] = "same-origin"
                    headers["Sec-Fetch-Dest"] = "empty"
                    headers["Sec-Fetch-Mode"] = "cors"

        # Merge with existing headers
        if existing_headers:
            headers.update(existing_headers)

        return headers

    def _parse_url(self, url: str) -> dict[str, str]:
        """Parse URL into components"""
        import re

        result = {
            "scheme": "https",  # Default
            "host": "",
            "path": "/",
        }

        # Simple URL parsing
        match = re.match(r"^(https?)://([^:/]+)(?::\d+)?(.*?)(?:\?.*)?$", url)
        if match:
            result["scheme"] = match.group(1)
            result["host"] = match.group(2)
            result["path"] = match.group(3) or "/"

        return result

    def build_api_headers(
        self,
        user_agent: str,
        content_type: str = "application/json",
        referer: str = "",
    ) -> dict[str, str]:
        """
        Build headers optimized for API requests.

        Args:
            user_agent: Browser user agent
            content_type: Content-Type of request
            referer: Referrer URL

        Returns:
            API-optimized headers
        """
        headers = self.build(
            user_agent=user_agent,
            is_navigation=False,
            is_ajax=True,
            referer=referer,
        )

        # API-specific headers
        headers["Content-Type"] = content_type
        headers["Accept"] = "application/json, text/javascript, */*; q=0.01"
        headers["Sec-Fetch-Dest"] = "empty"
        headers["Sec-Fetch-Mode"] = "cors"
        headers["Sec-Fetch-Site"] = "same-origin" if referer else "cross-site"

        # X-Requested-With for AJAX
        headers["X-Requested-With"] = "XMLHttpRequest"

        return headers

    def build_cookie_headers(self, cookies: dict[str, str]) -> dict[str, str]:
        """
        Build Cookie header from cookie dictionary.

        Args:
            cookies: Dictionary of cookie name -> value

        Returns:
            Cookie header dictionary
        """
        if not cookies:
            return {}

        cookie_string = "; ".join(f"{k}={v}" for k, v in cookies.items())
        return {"Cookie": cookie_string}

    def merge_headers(self, *header_dicts: dict[str, str]) -> dict[str, str]:
        """
        Merge multiple header dictionaries.

        Args:
            *header_dicts: Header dictionaries to merge

        Returns:
            Merged headers (later dicts override earlier ones)
        """
        merged = {}
        for headers in header_dicts:
            if headers:
                merged.update(headers)
        return merged

    def validate_consistency(self, headers: dict[str, str]) -> list[str]:
        """
        Validate header consistency.

        Args:
            headers: Headers to validate

        Returns:
            List of warnings for inconsistent headers
        """
        warnings = []

        user_agent = headers.get("User-Agent", "")

        # Check Sec-CH-UA consistency
        if "Sec-CH-UA" in headers:
            if "Chrome" not in user_agent and "Edg/" not in user_agent:
                warnings.append("Sec-CH-UA header present but user agent is not Chrome/Edge")

        if "Sec-CH-UA-Platform" in headers:
            platform = headers["Sec-CH-UA-Platform"].strip('"')
            if "Windows" in platform and "Windows" not in user_agent:
                warnings.append("Platform header (Windows) doesn't match user agent")
            elif "macOS" in platform and "Mac" not in user_agent:
                warnings.append("Platform header (macOS) doesn't match user agent")

        # Check Accept-Language consistency
        accept_lang = headers.get("Accept-Language", "")
        if "en-US" in accept_lang and "en" not in user_agent.lower():
            # This might be ok, just log it
            pass

        return warnings

    def get_request_count(self) -> int:
        """Get total number of headers built"""
        return self._request_count


# ============================================================================
# HEADER BUILDER FOR SPECIFIC BROWSER TYPES
# ============================================================================


class BrowserHeaderBuilder:
    """Specialized header builders for different browsers"""

    def __init__(self):
        self._builder = HeaderBuilder()

    def chrome(
        self,
        user_agent: str,
        **kwargs,
    ) -> dict[str, str]:
        """Build headers for Chrome browser"""
        return self._builder.build(
            user_agent=user_agent,
            platform=kwargs.get("platform", "Win32"),
            **kwargs,
        )

    def firefox(
        self,
        user_agent: str,
        **kwargs,
    ) -> dict[str, str]:
        """Build headers for Firefox browser"""
        return self._builder.build(
            user_agent=user_agent,
            platform=kwargs.get("platform", "Win32"),
            include_sec_headers=False,  # Firefox doesn't use Sec-CH-UA
            **kwargs,
        )

    def edge(
        self,
        user_agent: str,
        **kwargs,
    ) -> dict[str, str]:
        """Build headers for Edge browser"""
        return self._builder.build(
            user_agent=user_agent,
            platform=kwargs.get("platform", "Win32"),
            **kwargs,
        )

    def safari(
        self,
        user_agent: str,
        **kwargs,
    ) -> dict[str, str]:
        """Build headers for Safari browser"""
        # Safari has different header requirements
        headers = self._builder.build(
            user_agent=user_agent,
            platform=kwargs.get("platform", "MacIntel"),
            include_sec_headers=False,  # Safari doesn't use Sec-CH-UA
            **kwargs,
        )

        # Safari-specific headers
        headers["Sec-Fetch-Dest"] = "document"
        headers["Sec-Fetch-Mode"] = "navigate"
        headers["Sec-Fetch-Site"] = "none"
        headers["Sec-Fetch-User"] = "?1"
        headers["Upgrade-Insecure-Requests"] = "1"

        return headers


# ============================================================================
# GLOBAL INSTANCE
# ============================================================================

_global_builder: HeaderBuilder | None = None


def get_header_builder() -> HeaderBuilder:
    """Get or create global header builder instance"""
    global _global_builder
    if _global_builder is None:
        _global_builder = HeaderBuilder()
    return _global_builder


def set_header_builder(builder: HeaderBuilder):
    """Set global header builder instance"""
    global _global_builder
    _global_builder = builder

"""
Comprehensive Anti-Detection Integration Tests
================================================
Tests for complete anti-detection system including:
- Config profiles
- Proxy rotator
- Header builder
- Stealth scripts
- Human behavior
"""

import os
import sys

import pytest

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


class TestConfigProfiles:
    """Test configuration profiles"""

    def test_user_agent_profiles_exist(self):
        """Test that user agent profiles are loaded"""
        from app.automation.config import USER_AGENT_PROFILES

        assert len(USER_AGENT_PROFILES) > 0, "User agent profiles should exist"

        # Verify structure
        for profile in USER_AGENT_PROFILES:
            assert "user_agent" in profile
            assert "platform" in profile
            assert "language" in profile

    def test_gpu_profiles_exist(self):
        """Test that GPU profiles are loaded"""
        from app.automation.config import GPU_PROFILES

        assert len(GPU_PROFILES) > 0, "GPU profiles should exist"

        for gpu in GPU_PROFILES:
            assert "vendor" in gpu
            assert "renderer" in gpu

    def test_screen_presets_exist(self):
        """Test that screen presets are loaded"""
        from app.automation.config import SCREEN_PRESETS

        assert len(SCREEN_PRESETS) > 0, "Screen presets should exist"

        for preset in SCREEN_PRESETS:
            assert "width" in preset
            assert "height" in preset

    def test_timezone_profiles_exist(self):
        """Test that timezone profiles are loaded"""
        from app.automation.config import TIMEZONE_PROFILES

        assert len(TIMEZONE_PROFILES) > 0, "Timezone profiles should exist"

        # Verify they are valid timezone names
        valid_prefixes = ["America/", "Europe/", "Asia/", "Australia/", "Africa/", "Pacific/"]
        for tz in TIMEZONE_PROFILES:
            assert any(tz.startswith(prefix) for prefix in valid_prefixes), f"Invalid timezone: {tz}"

    def test_browser_profile_dataclass(self):
        """Test BrowserProfile dataclass"""
        from app.automation.config import BrowserProfile, ScreenFingerprint, WebGLFingerprint

        screen = ScreenFingerprint(width=1920, height=1080)
        webgl = WebGLFingerprint(vendor="Test", renderer="Test")

        profile = BrowserProfile(
            name="test",
            user_agent="Test UA",
            platform="Win32",
            screen=screen,
            webgl=webgl,
        )

        # Test to_dict
        data = profile.to_dict()
        assert data["name"] == "test"
        assert data["screen"]["width"] == 1920

        # Test fingerprint_hash
        hash_value = profile.fingerprint_hash()
        assert len(hash_value) == 16
        assert isinstance(hash_value, str)


class TestProxyRotator:
    """Test proxy rotator functionality"""

    def test_proxy_info_creation(self):
        """Test ProxyInfo creation"""
        from app.automation.proxy_rotator import ProxyInfo

        proxy = ProxyInfo(
            url="http://example.com:8080",
            protocol="http",
            username="user",
            password="pass",
        )

        assert proxy.full_url == "http://user:pass@example.com:8080"
        assert proxy.is_healthy is True
        assert proxy.fail_count == 0

    def test_proxy_info_failure(self):
        """Test ProxyInfo failure tracking"""
        from app.automation.proxy_rotator import ProxyInfo

        proxy = ProxyInfo(url="http://example.com:8080")

        # Simulate failures
        for _ in range(3):
            proxy.record_failure("test error")

        assert proxy.fail_count == 3
        assert proxy.is_healthy is False

    def test_proxy_rotator_creation(self):
        """Test ProxyRotator initialization"""
        from app.automation.proxy_rotator import ProxyConfig, ProxyRotator

        rotator = ProxyRotator(
            cooldown=5.0,
            timeout=10.0,
        )

        assert len(rotator.proxies) == 0
        assert rotator.cooldown == 5.0

    def test_proxy_rotator_load_from_list(self):
        """Test loading proxies from list"""
        from app.automation.proxy_rotator import ProxyConfig, ProxyRotator

        rotator = ProxyRotator()
        urls = [
            "http://proxy1.com:8080",
            "socks5://proxy2.com:1080",
            "http://user:pass@proxy3.com:3128",
        ]

        loaded = rotator.load_from_list(urls)
        assert loaded == 3
        assert len(rotator.proxies) == 3
        assert rotator.proxies[0].protocol == "http"
        assert rotator.proxies[1].protocol == "socks5"

    def test_proxy_rotator_load_from_file(self, tmp_path):
        """Test loading proxies from file"""
        from app.automation.proxy_rotator import ProxyConfig, ProxyRotator

        # Create test file
        proxy_file = tmp_path / "proxies.txt"
        proxy_file.write_text("# Comment line\n" "http://proxy1.com:8080\n" "\n" "http://proxy2.com:3128\n")

        rotator = ProxyRotator()
        loaded = rotator.load_from_file(str(proxy_file))

        assert loaded == 2
        assert rotator.proxies[0].url == "http://proxy1.com:8080"

    @pytest.mark.asyncio
    async def test_proxy_rotator_get_next(self):
        """Test getting next proxy"""
        from app.automation.proxy_rotator import ProxyConfig, ProxyRotator

        rotator = ProxyRotator(cooldown=0)  # No cooldown for testing

        rotator.add_proxy(ProxyConfig(url="http://proxy1.com:8080"))
        rotator.add_proxy(ProxyConfig(url="http://proxy2.com:3128"))

        proxy = await rotator.get_next()
        assert proxy is not None
        assert proxy.url in ["http://proxy1.com:8080", "http://proxy2.com:3128"]

    def test_proxy_rotator_stats(self):
        """Test proxy statistics"""
        from app.automation.proxy_rotator import ProxyConfig, ProxyRotator

        rotator = ProxyRotator()
        rotator.add_proxy(ProxyConfig(url="http://proxy1.com:8080"))

        proxy = rotator.proxies[0]
        proxy.record_success(1.5, 1024)
        proxy.record_success(2.0, 2048)

        stats = rotator.get_stats()

        assert stats["total_proxies"] == 1
        assert stats["healthy_proxies"] == 1
        assert stats["total_requests"] == 2
        assert stats["successful_requests"] == 2

    @pytest.mark.asyncio
    async def test_proxy_rotator_waybill_scoring_and_geoip(self):
        """Test proxy rotator waybill scoring and Geo-IP filtering"""
        from app.automation.proxy_rotator import ProxyConfig, ProxyRotator
        from unittest.mock import AsyncMock

        # Initialize with require_iran_ip=True explicitly for testing
        rotator = ProxyRotator(cooldown=0, require_iran_ip=True)
        
        # Mock verify_country
        async def mock_verify(proxy):
            if "iran" in proxy.url:
                proxy.country = "IR"
            else:
                proxy.country = "US"
            return True
        
        rotator.verify_country = mock_verify

        rotator.add_proxy(ProxyConfig(url="http://iran-proxy.com:8080")) # country None at start
        rotator.add_proxy(ProxyConfig(url="http://us-proxy.com:8080")) # country None at start

        # Test on-the-fly Geo-IP checking
        # Only the iran-proxy should be selected because it gets verified as "IR"
        chosen = await rotator.get_next()
        assert chosen is not None
        assert "iran-proxy.com" in chosen.url
        assert chosen.country == "IR"

        # Check scoring with waybill results
        p = rotator.proxies[0]
        p.record_waybill_result(success=True, latency=1.2)
        assert p.waybill_attempts == 1
        assert p.waybill_successes == 1
        assert p.waybill_success_rate == 100.0
        
        # Test low success rate is unhealthy
        p.record_waybill_result(success=False, latency=1.0)
        p.record_waybill_result(success=False, latency=1.0)
        # 1 success out of 3 attempts = 33.3% success rate
        assert p.waybill_success_rate < 50.0
        assert p.is_healthy is False


class TestHeaderBuilder:
    """Test header builder functionality"""

    def test_header_builder_creation(self):
        """Test HeaderBuilder initialization"""
        from app.automation.header_builder import HeaderBuilder

        builder = HeaderBuilder()
        assert builder is not None

    def test_basic_header_building(self):
        """Test basic header building"""
        from app.automation.header_builder import HeaderBuilder

        builder = HeaderBuilder()

        headers = builder.build(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/124.0",
            platform="Win32",
            language="en-US",
        )

        assert "User-Agent" in headers
        assert "Accept" in headers
        assert "Accept-Language" in headers
        assert "Connection" in headers

    def test_chrome_headers(self):
        """Test Chrome-specific headers"""
        from app.automation.header_builder import HeaderBuilder

        builder = HeaderBuilder()

        headers = builder.build(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/124.0",
            platform="Win32",
            include_sec_headers=True,
        )

        # Chrome should have Sec-CH-UA headers
        assert "Sec-CH-UA" in headers
        assert "Sec-CH-UA-Platform" in headers

    def test_firefox_headers(self):
        """Test Firefox-specific headers"""
        from app.automation.header_builder import HeaderBuilder

        builder = HeaderBuilder()

        headers = builder.build(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:125.0) Firefox/125.0",
            platform="Win32",
            include_sec_headers=True,
        )

        # Firefox should NOT have Sec-CH-UA headers
        assert "Sec-CH-UA" not in headers

    def test_accept_language(self):
        """Test Accept-Language header building"""
        from app.automation.header_builder import HeaderBuilder

        builder = HeaderBuilder()

        # Persian language
        headers = builder.build(
            user_agent="Chrome/124.0",
            language="fa-IR",
        )

        accept_lang = headers["Accept-Language"]
        assert "fa-IR" in accept_lang
        assert "en" in accept_lang

    def test_api_headers(self):
        """Test API-specific headers"""
        from app.automation.header_builder import HeaderBuilder

        builder = HeaderBuilder()

        headers = builder.build_api_headers(
            user_agent="Chrome/124.0",
            content_type="application/json",
        )

        assert headers["Content-Type"] == "application/json"
        assert headers["X-Requested-With"] == "XMLHttpRequest"
        assert headers["Sec-Fetch-Dest"] == "empty"

    def test_cookie_headers(self):
        """Test cookie header building"""
        from app.automation.header_builder import HeaderBuilder

        builder = HeaderBuilder()

        cookies = {"session": "abc123", "user": "test"}
        cookie_headers = builder.build_cookie_headers(cookies)

        assert "Cookie" in cookie_headers
        assert "session=abc123" in cookie_headers["Cookie"]
        assert "user=test" in cookie_headers["Cookie"]

    def test_header_consistency_validation(self):
        """Test header consistency validation"""
        from app.automation.header_builder import HeaderBuilder

        builder = HeaderBuilder()

        # Inconsistent headers (Chrome with wrong platform)
        headers = {
            "User-Agent": "Firefox/125.0",
            "Sec-CH-UA-Platform": '"Windows"',
        }

        warnings = builder.validate_consistency(headers)

        # Should warn about inconsistency
        assert len(warnings) > 0


class TestHumanInteraction:
    """Test human-like interaction functions"""

    @pytest.mark.asyncio
    async def test_typing_delay_calculation(self):
        """Test typing delay calculation"""
        from app.automation.human_interaction import _calculate_typing_delay

        # Test base delay
        delay = _calculate_typing_delay(
            char="a",
            min_delay=0.05,
            max_delay=0.15,
            pause_on_punctuation=False,
            pause_on_capitals=False,
            random_hesitation=False,
        )

        assert 0.05 <= delay <= 0.15

    @pytest.mark.asyncio
    async def test_punctuation_delay(self):
        """Test punctuation causes longer delays"""
        from app.automation.human_interaction import _calculate_typing_delay
        import random
        from unittest.mock import patch

        def mock_uniform(a, b):
            return (a + b) / 2

        with patch("random.uniform", side_effect=mock_uniform):
            base_delay = _calculate_typing_delay(
                char="a",
                min_delay=0.05,
                max_delay=0.15,
                pause_on_punctuation=False,
                pause_on_capitals=False,
                random_hesitation=False,
            )

            punct_delay = _calculate_typing_delay(
                char=".",
                min_delay=0.05,
                max_delay=0.15,
                pause_on_punctuation=True,
                pause_on_capitals=False,
                random_hesitation=False,
            )

        # Punctuation should be slower
        assert punct_delay > base_delay


class TestStealthScripts:
    """Test stealth script generation"""

    def test_stealth_script_structure(self):
        """Test that stealth script is properly structured"""
        from app.automation.stealth import _build_init_script

        test_fp = {
            "ua": "Test UA",
            "viewport": {"width": 1920, "height": 1080},
            "webgl": {
                "vendor": "Test Vendor",
                "renderer": "Test Renderer",
            },
            "hw_concurrency": 8,
            "device_memory": 8,
        }

        script = _build_init_script(test_fp)

        # Should contain key stealth elements
        assert "webdriver" in script
        assert "cdc_adoQpoasnfa76pfcZLmcfl" in script
        assert "chrome" in script
        assert "WebGLRenderingContext" in script
        assert "toDataURL" in script

    def test_get_random_viewport(self):
        """Test get_random_viewport returns a valid dictionary"""
        from app.automation.stealth import get_random_viewport

        viewport = get_random_viewport()

        assert isinstance(viewport, dict)
        assert "width" in viewport
        assert "height" in viewport
        assert isinstance(viewport["width"], int)
        assert isinstance(viewport["height"], int)
        assert viewport["width"] > 0
        assert viewport["height"] > 0

    def test_stealth_script_executable(self):
        """Test that stealth script is valid JavaScript"""
        from app.automation.stealth import _build_init_script

        test_fp = {
            "ua": "Test UA",
            "viewport": {"width": 1920, "height": 1080},
            "webgl": {
                "vendor": "Test Vendor",
                "renderer": "Test Renderer",
            },
            "hw_concurrency": 8,
            "device_memory": 8,
        }

        script = _build_init_script(test_fp)

        # Should be wrapped in IIFE
        assert script.strip().startswith("(() => {")
        assert script.strip().endswith("})();")


class TestIntegration:
    """Integration tests for complete workflow"""

    @pytest.mark.asyncio
    async def test_complete_request_workflow(self):
        """Test complete request workflow: config -> proxy -> headers"""
        from app.automation.config import SCREEN_PRESETS, USER_AGENT_PROFILES
        from app.automation.header_builder import HeaderBuilder
        from app.automation.proxy_rotator import ProxyConfig, ProxyRotator

        # 1. Select random profile
        profile = USER_AGENT_PROFILES[0]
        screen = SCREEN_PRESETS[0]

        # 2. Create proxy
        rotator = ProxyRotator(cooldown=0)
        rotator.add_proxy(ProxyConfig(url="http://test-proxy.com:8080"))

        # 3. Build headers
        builder = HeaderBuilder()
        headers = builder.build(
            user_agent=profile["user_agent"],
            platform=profile["platform"],
            language=profile["language"],
            referer="",
        )

        # Verify integration
        assert headers["User-Agent"] == profile["user_agent"]
        assert "Accept" in headers
        assert "Accept-Language" in headers

        # Check proxy is available
        proxy = await rotator.get_next()
        assert proxy is not None
        assert proxy.url == "http://test-proxy.com:8080"

    def test_config_file_persistence(self, tmp_path):
        """Test that config can be saved and loaded"""
        from app.automation.config import load_profiles, save_profiles

        tmp_path / "config"

        # Save profiles
        filepath = save_profiles([{"name": "test", "user_agent": "Test"}], filename="test_profiles.json")

        # Verify file exists
        assert os.path.exists(filepath)

        # Load profiles
        data = load_profiles("test_profiles.json")
        assert "profiles" in data
        assert len(data["profiles"]) > 0


class TestEdgeCases:
    """Test edge cases and error handling"""

    def test_empty_proxy_list(self):
        """Test handling empty proxy list"""
        from app.automation.proxy_rotator import ProxyConfig, ProxyRotator

        rotator = ProxyRotator()
        # No proxies added

        import asyncio

        proxy = asyncio.run(rotator.get_next())
        assert proxy is None

    def test_all_proxies_failed(self):
        """Test when all proxies have failed"""
        from app.automation.proxy_rotator import ProxyConfig, ProxyInfo, ProxyRotator

        rotator = ProxyRotator(cooldown=0, max_fail_count=1)

        # Add proxy and fail it
        proxy = ProxyInfo(url="http://fail.com:8080")
        proxy.record_failure("error1")
        proxy.record_failure("error2")
        rotator.proxies.append(proxy)

        import asyncio

        result = asyncio.run(rotator.get_next())
        assert result is None  # Should be unhealthy

    def test_invalid_user_agent(self):
        """Test handling unusual user agents"""
        from app.automation.header_builder import HeaderBuilder

        builder = HeaderBuilder()

        # Very unusual UA
        headers = builder.build(
            user_agent="CustomBrowser/1.0 (VeryCustom OS)",
            platform="CustomOS",
        )

        # Should still build headers
        assert "User-Agent" in headers
        assert headers["User-Agent"] == "CustomBrowser/1.0 (VeryCustom OS)"

    def test_special_characters_in_headers(self):
        """Test handling special characters"""
        from app.automation.header_builder import HeaderBuilder

        builder = HeaderBuilder()

        headers = builder.build(
            user_agent="Test/1.0",
            language="zh-CN",
        )

        # Should handle unicode correctly
        accept_lang = headers["Accept-Language"]
        assert len(accept_lang) > 0


# Run tests with pytest
if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
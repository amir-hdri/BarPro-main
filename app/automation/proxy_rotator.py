"""
Enterprise-Grade Proxy Rotator with Health Check
==================================================
Advanced proxy management with automatic health monitoring, latency tracking,
and intelligent rotation for maximum anonymity and reliability.
"""

import asyncio
import contextlib
import ipaddress
import json
import logging
import random
import threading
import time
from collections.abc import AsyncIterator, Awaitable, Callable
from dataclasses import asdict, dataclass, field
from datetime import datetime
from typing import Any
from urllib.parse import urlparse

from aiohttp import ClientError, ClientSession, ClientTimeout

logger = logging.getLogger(__name__)


@dataclass
class ProxyConfig:
    """Configuration for adding a new proxy."""

    url: str
    protocol: str = "http"
    country: str | None = None
    city: str | None = None
    tags: list[str] = field(default_factory=list)


@dataclass
class ProxyInfo:
    """
    Comprehensive proxy information with health tracking.
    """

    url: str
    protocol: str = "http"
    username: str | None = None
    password: str | None = None
    country: str | None = None
    city: str | None = None
    isp: str | None = None
    fail_count: int = 0
    last_used: float = 0.0
    last_health_check: float = 0.0
    avg_latency: float = 0.0
    total_requests: int = 0
    successful_requests: int = 0
    failed_requests: int = 0
    success_rate: float = 100.0
    bandwidth_used: int = 0  # in bytes
    session_duration: float = 0.0
    last_error: str | None = None
    tags: list[str] = field(default_factory=list)

    # Waybill submission tracking (for UTCMS target site)
    waybill_attempts: int = 0
    waybill_successes: int = 0
    waybill_failures: int = 0
    waybill_success_rate: float = 100.0

    @property
    def full_url(self) -> str:
        """Get proxy URL with credentials if available"""
        if self.username and self.password:
            proto, rest = self.url.split("://", 1)
            return f"{proto}://{self.username}:{self.password}@{rest}"
        return self.url

    @property
    def is_healthy(self) -> bool:
        """Check if proxy is considered healthy"""
        if self.fail_count >= 3:
            return False
        if self.success_rate < 70.0:
            return False
        # If latency is too high (e.g. > 7.0 seconds), consider unhealthy
        if self.avg_latency > 7.0:
            return False
        # Blocked / flagged proxy detection (high waybill failure rate)
        if self.waybill_attempts > 0 and self.waybill_success_rate < 50.0:
            return False
        return True

    @property
    def is_active(self) -> bool:
        """Check if proxy is currently active and usable"""
        if not self.is_healthy:
            return False
        # Consider cooldown period after last use
        cooldown_period = 5.0  # seconds
        return (time.time() - self.last_used) >= cooldown_period

    @property
    def health_score(self) -> float:
        """
        Calculate health score (0-100) based on multiple factors.
        Higher is better.
        """
        # Base score from success rate
        score = self.success_rate * 0.4

        # Add weight from waybill success rate if waybills attempted
        if self.waybill_attempts > 0:
            score += self.waybill_success_rate * 0.2
        else:
            score += 20.0  # Neutral base points for untested waybill capability

        # Latency penalty/bonus (lower is better, over 5s is penalized)
        if self.avg_latency > 0:
            if self.avg_latency > 5.0:
                score -= (self.avg_latency - 5.0) * 8.0  # Heavy penalty for slowness
            elif self.avg_latency < 1.0:
                score += 15.0
            elif self.avg_latency < 2.0:
                score += 10.0
            elif self.avg_latency < 3.0:
                score += 5.0

        # Total requests bonus (more experience is better)
        if self.total_requests >= 100:
            score += 10.0
        elif self.total_requests >= 50:
            score += 7.0
        elif self.total_requests >= 10:
            score += 3.0

        # Fail count penalty
        score -= self.fail_count * 5

        return max(0.0, min(100.0, score))

    def record_success(self, latency: float, bandwidth: int = 0):
        """Record successful request"""
        self.fail_count = 0
        self.total_requests += 1
        self.successful_requests += 1
        self.last_used = time.time()
        self.bandwidth_used += bandwidth

        # Exponential moving average for latency
        alpha = 0.2
        if self.avg_latency == 0:
            self.avg_latency = latency
        else:
            self.avg_latency = alpha * latency + (1 - alpha) * self.avg_latency

        # Update success rate
        self.success_rate = (self.successful_requests / self.total_requests) * 100.0

    def record_failure(self, error: str = ""):
        """Record failed request"""
        self.fail_count += 1
        self.total_requests += 1
        self.failed_requests += 1
        self.last_used = time.time()
        self.last_health_check = time.time()
        self.last_error = error

        # Update success rate
        if self.total_requests > 0:
            self.success_rate = (self.successful_requests / self.total_requests) * 100.0

    def record_waybill_result(self, success: bool, latency: float, error: str | None = None):
        """Record outcome of a waybill registration attempt (success/failure/latency)."""
        self.waybill_attempts += 1
        self.total_requests += 1
        self.last_used = time.time()

        if success:
            self.fail_count = 0
            self.waybill_successes += 1
            self.successful_requests += 1
            # Exponential moving average for latency
            alpha = 0.2
            if self.avg_latency == 0:
                self.avg_latency = latency
            else:
                self.avg_latency = alpha * latency + (1 - alpha) * self.avg_latency
        else:
            self.fail_count += 1
            self.waybill_failures += 1
            self.failed_requests += 1
            self.last_error = error or "Waybill registration failed"

        # Recalculate success rates
        if self.total_requests > 0:
            self.success_rate = (self.successful_requests / self.total_requests) * 100.0
        if self.waybill_attempts > 0:
            self.waybill_success_rate = (self.waybill_successes / self.waybill_attempts) * 100.0

    def to_playwright_proxy(self) -> dict[str, Any]:
        """Get proxy dictionary format for Playwright"""
        proxy_dict = {"server": f"{self.protocol}://{self.url.split('://')[-1]}"}
        if self.username and self.password:
            proxy_dict["username"] = self.username
            proxy_dict["password"] = self.password
        return proxy_dict

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary"""
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ProxyInfo":
        """Create from dictionary"""
        return cls(**data)


class ProxyRotator:
    """
    Advanced proxy rotator with health monitoring and intelligent selection.
    """

    def __init__(
        self,
        cooldown: float = 5.0,
        health_check_interval: float = 300.0,  # 5 minutes
        max_health_check_attempts: int = 3,
        test_url: str = "https://barname.utcms.ir",
        timeout: float = 10.0,
        min_success_rate: float = 70.0,
        max_fail_count: int = 3,
        require_iran_ip: bool | None = None,
    ):

        if require_iran_ip is None:
            require_iran_ip = False

        self.proxies: list[ProxyInfo] = []
        self.cooldown = cooldown
        self.health_check_interval = health_check_interval
        self.max_health_check_attempts = max_health_check_attempts
        self.test_url = test_url
        self.timeout = timeout
        self.min_success_rate = min_success_rate
        self.max_fail_count = max_fail_count
        self.require_iran_ip = require_iran_ip

        self._lock = threading.Lock()
        self._health_check_task: asyncio.Task | None = None
        self._running = False
        self._on_proxy_used: Callable[[ProxyInfo], Awaitable[None]] | None = None
        self._on_proxy_failed: Callable[[ProxyInfo, str], Awaitable[None]] | None = None

        logger.info(
            f"ProxyRotator initialized with {len(self.proxies)} proxies (require_iran_ip={self.require_iran_ip})"
        )

    @contextlib.asynccontextmanager
    async def lock(self) -> AsyncIterator[None]:
        with self._lock:
            yield

    def load_from_list(self, proxy_urls: list[str]) -> int:
        """Load proxies from URL list."""
        loaded = 0
        for url in proxy_urls:
            url = url.strip()
            if not url or url.startswith("#"):
                continue

            if "socks5://" in url:
                protocol = "socks5"
            elif "socks4://" in url:
                protocol = "socks4"
            else:
                protocol = "http"

            username = None
            password = None
            clean_url = url

            if "@" in url:
                parts = url.split("@")
                clean_url = f"{protocol}://{parts[1]}" if "://" in url else parts[1]

                auth_part = parts[0].split("://")[-1]
                if ":" in auth_part:
                    username, password = auth_part.split(":", 1)

            proxy = ProxyInfo(
                url=clean_url,
                protocol=protocol,
                username=username,
                password=password,
            )
            self.proxies.append(proxy)
            loaded += 1

        logger.info(f"Loaded {loaded} proxies from list")
        return loaded

    def load_from_file(self, filepath: str, encoding: str = "utf-8") -> int:
        """Load proxies from file (one per line)."""
        try:
            with open(filepath, encoding=encoding) as f:
                lines = f.readlines()
            return self.load_from_list(lines)
        except Exception as e:
            logger.error(f"Failed to load proxies from {filepath}: {e}")
            return 0

    def load_from_json(self, data: dict[str, Any]) -> int:
        """Load proxies from JSON data."""
        loaded = 0

        if "proxies" in data:
            for proxy_data in data["proxies"]:
                if isinstance(proxy_data, str):
                    self.load_from_list([proxy_data])
                elif isinstance(proxy_data, dict):
                    proxy = ProxyInfo.from_dict(proxy_data)
                    self.proxies.append(proxy)
                    loaded += 1
        elif "proxy_list" in data:
            for proxy_data in data["proxy_list"]:
                if isinstance(proxy_data, str):
                    self.load_from_list([proxy_data])
                elif isinstance(proxy_data, dict):
                    proxy = ProxyInfo.from_dict(proxy_data)
                    self.proxies.append(proxy)
                    loaded += 1
        else:
            for item in data:
                if isinstance(item, str):
                    self.load_from_list([item])
                elif isinstance(item, dict):
                    proxy = ProxyInfo.from_dict(item)
                    self.proxies.append(proxy)
                    loaded += 1

        logger.info(f"Loaded {loaded} proxies from JSON")
        return loaded

    @staticmethod
    def _is_safe_proxy_url(url: str) -> bool:
        parsed = urlparse(url)
        host = parsed.hostname or ""
        try:
            ip = ipaddress.ip_address(host)
            if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_multicast:
                return False
        except ValueError:
            logger.debug("proxy_host_not_an_ip_treating_as_safe", extra={"extra_fields": {"host": host}})
        return True

    def add_proxy(self, config: ProxyConfig) -> ProxyInfo:
        """Add a single proxy using ProxyConfig."""
        if not self._is_safe_proxy_url(config.url):
            logger.warning("blocked_private_proxy_url", extra={"extra_fields": {"url": config.url[:60]}})
            raise ValueError(f"Proxy URL points to a private/reserved IP range: {config.url[:60]}")

        proxy = ProxyInfo(
            url=config.url,
            protocol=config.protocol,
            country=config.country,
            city=config.city,
            tags=config.tags or [],
        )
        self.proxies.append(proxy)
        parsed = urlparse(config.url)
        safe_url = parsed._replace(netloc=f"{parsed.hostname}:{parsed.port}") if parsed.password else config.url
        logger.debug(f"Added proxy: {safe_url}")
        return proxy

    async def verify_country(self, proxy: ProxyInfo) -> bool:
        """Fetch geo-information to detect proxy country."""
        geo_apis = [
            "https://freeipapi.com/api/json/",
            "http://ip-api.com/json/",
            "https://ipapi.co/json/",
        ]
        for geo_url in geo_apis:
            try:
                async with ClientSession(timeout=ClientTimeout(total=self.timeout)) as session:
                    async with session.get(geo_url, proxy=proxy.full_url) as resp:
                        if resp.status == 200:
                            data = await resp.json()
                            country_code = data.get("countryCode") or data.get("country") or data.get("country_code")
                            if country_code:
                                proxy.country = str(country_code).strip().upper()
                                proxy.city = data.get("cityName") or data.get("city")
                                proxy.isp = data.get("isp") or data.get("org")
                                return True
            except Exception:
                continue
        return False

    async def get_next(
        self,
        country: str | None = None,
        tags: list[str] | None = None,
        exclude_failed: bool = True,
        prefer_low_latency: bool = True,
        require_iran_ip: bool | None = None,
    ) -> ProxyInfo | None:
        """Get next available proxy based on health score with Geo-IP check option."""
        if require_iran_ip is None:
            require_iran_ip = self.require_iran_ip

        max_verification_attempts = 3
        for _attempt in range(max_verification_attempts):
            chosen = None
            async with self.lock():
                now = time.time()

                available = []
                for proxy in self.proxies:
                    if exclude_failed and not proxy.is_healthy:
                        continue

                    if (now - proxy.last_used) < self.cooldown:
                        continue

                    if country and proxy.country != country:
                        continue

                    if tags and not all(tag in proxy.tags for tag in tags):
                        continue

                    available.append(proxy)

                if not available:
                    logger.debug("No available proxies")
                    return None

                # Prioritize/strictly enforce IR proxies for Iranian site operations
                if require_iran_ip:
                    # Allow country == "IR" or None (so we can check/verify it on-the-fly)
                    ir_candidates = [p for p in available if p.country == "IR" or p.country is None]
                    if not ir_candidates:
                        logger.warning("No Iranian or unverified proxies available in pool")
                        return None
                    available = ir_candidates

                def sort_key(p):
                    score = p.health_score
                    if prefer_low_latency:
                        score -= p.avg_latency * 2
                    if p.country == "IR":
                        score += 500.0  # Massive score boost for Iranian proxies
                    return score

                available.sort(key=sort_key, reverse=True)

                if len(available) >= 3:
                    top_proxies = available[:3]
                    chosen = random.choice(top_proxies)
                else:
                    chosen = available[0]

                # Reserve proxy cooldown immediately to prevent double selection in concurrent calls
                chosen.last_used = now

            # If require_iran_ip is true and proxy's country is not verified, check on-the-fly
            if require_iran_ip and chosen.country is None:
                logger.info(f"Checking Geo-IP on-the-fly for proxy {chosen.url[:40]}...")
                # Fetch country info outside of the lock to prevent blocking get_next for other tasks
                success = await self.verify_country(chosen)
                if not success or chosen.country != "IR":
                    logger.warning(
                        f"On-the-fly Geo-IP check failed or proxy {chosen.url[:40]} is not in Iran. Detected: {chosen.country}. Skipping."
                    )
                    # Mark as non-IR and record failure
                    chosen.record_failure("Not an Iran IP")
                    # Enforce cooldown on this proxy
                    chosen.last_used = time.time()
                    continue

            # Return if verification succeeded or was not required/already IR
            if self._on_proxy_used:
                try:
                    await self._on_proxy_used(chosen)
                except Exception as e:
                    logger.warning(f"Proxy used callback failed: {e}")

            logger.debug(
                f"Selected proxy: {chosen.url[:50]}... (health: {chosen.health_score:.1f}, country: {chosen.country})"
            )
            return chosen

        return None

    async def health_check(self, proxy: ProxyInfo) -> bool:
        """Perform health check on a single proxy and auto-detect country."""
        start_time = time.time()

        try:
            # 1. Attempt to fetch geo-information to detect country
            await self.verify_country(proxy)

            # 2. Test target URL connectivity
            test_urls = [
                self.test_url,
                "https://api.ipify.org?format=json",
                "https://ident.me",
            ]

            for test_url in test_urls:
                try:
                    async with ClientSession(timeout=ClientTimeout(total=self.timeout)) as session:
                        async with session.get(
                            test_url,
                            proxy=proxy.full_url,
                        ) as response:
                            if response.status in (200, 301, 302):
                                latency = time.time() - start_time
                                proxy.record_success(latency)
                                proxy.last_health_check = time.time()

                                try:
                                    data = await response.json()
                                    if isinstance(data, dict) and "ip" in data:
                                        logger.debug(
                                            f"Proxy OK: {proxy.url[:40]}... IP: {data['ip']} Country: {proxy.country} ({latency:.2f}s)"
                                        )
                                except Exception:
                                    logger.debug(
                                        f"Proxy OK: {proxy.url[:40]}... Country: {proxy.country} ({latency:.2f}s)"
                                    )

                                return True
                except ClientError:
                    continue
                except Exception:
                    continue

            proxy.record_failure("All test URLs failed")
            return False

        except TimeoutError:
            proxy.record_failure("Timeout")
            return False
        except Exception as e:
            proxy.record_failure(str(e))
            return False

    async def check_all(self) -> dict[str, int]:
        """Run health check on all proxies."""
        logger.info(f"Running health check on {len(self.proxies)} proxies...")

        start_time = time.time()
        results = {
            "healthy": 0,
            "unhealthy": 0,
            "total": len(self.proxies),
            "checked": 0,
        }

        semaphore = asyncio.Semaphore(10)

        async def check_with_semaphore(proxy):
            async with semaphore:
                try:
                    healthy = await self.health_check(proxy)
                    if healthy:
                        results["healthy"] += 1
                    else:
                        results["unhealthy"] += 1
                except Exception as e:
                    results["unhealthy"] += 1
                    logger.error(f"Health check error: {e}")
                finally:
                    results["checked"] += 1

        tasks = [check_with_semaphore(p) for p in self.proxies]
        await asyncio.gather(*tasks, return_exceptions=True)

        elapsed = time.time() - start_time
        logger.info(f"Health check complete: {results['healthy']}/{results['total']} healthy ({elapsed:.1f}s)")

        return results

    async def start_auto_health_check(self, interval: float = None):
        """Start automatic background health checking."""
        if self._running:
            logger.warning("Health check already running")
            return

        interval = interval or self.health_check_interval
        self._running = True

        logger.info(f"Starting automatic health check (interval: {interval}s)")

        async def health_check_loop():
            while self._running:
                try:
                    await self.check_all()
                except Exception as e:
                    logger.error(f"Health check loop error: {e}")

                await asyncio.sleep(interval)

        self._health_check_task = asyncio.create_task(health_check_loop())

    def stop_auto_health_check(self):
        """Stop automatic health checking"""
        self._running = False
        if self._health_check_task:
            self._health_check_task.cancel()
            self._health_check_task = None
        logger.info("Stopped automatic health checking")

    def get_stats(self) -> dict[str, Any]:
        """Get comprehensive proxy statistics."""
        total = len(self.proxies)
        healthy = sum(1 for p in self.proxies if p.is_healthy)
        failed = sum(1 for p in self.proxies if p.fail_count >= self.max_fail_count)

        avg_latency = sum(p.avg_latency for p in self.proxies if p.avg_latency > 0) / max(
            1, sum(1 for p in self.proxies if p.avg_latency > 0)
        )

        total_requests = sum(p.total_requests for p in self.proxies)
        total_success = sum(p.successful_requests for p in self.proxies)
        overall_success_rate = (total_success / total_requests * 100.0) if total_requests > 0 else 0.0

        return {
            "total_proxies": total,
            "healthy_proxies": healthy,
            "failed_proxies": failed,
            "average_latency": round(avg_latency, 3),
            "total_requests": total_requests,
            "successful_requests": total_success,
            "overall_success_rate": round(overall_success_rate, 2),
            "proxies": [
                {
                    "url": p.url[:50] + "..." if len(p.url) > 50 else p.url,
                    "health_score": round(p.health_score, 2),
                    "success_rate": round(p.success_rate, 2),
                    "avg_latency": round(p.avg_latency, 3),
                    "fail_count": p.fail_count,
                    "total_requests": p.total_requests,
                }
                for p in self.proxies
            ],
        }

    def save_to_file(self, filepath: str, encoding: str = "utf-8"):
        """Save proxy state to JSON file."""
        data = {
            "version": "1.0",
            "updated_at": datetime.now().isoformat(),
            "proxies": [p.to_dict() for p in self.proxies],
        }

        with open(filepath, "w", encoding=encoding) as f:
            json.dump(data, f, indent=2, ensure_ascii=False)

        logger.info(f"Saved {len(self.proxies)} proxies to {filepath}")

    def load_from_file_state(self, filepath: str, encoding: str = "utf-8") -> int:
        """Load proxy state from JSON file."""
        try:
            with open(filepath, encoding=encoding) as f:
                data = json.load(f)

            if "proxies" in data:
                loaded = 0
                for proxy_data in data["proxies"]:
                    proxy = ProxyInfo.from_dict(proxy_data)
                    self.proxies.append(proxy)
                    loaded += 1
                logger.info(f"Loaded {loaded} proxies from {filepath}")
                return loaded
            return 0
        except Exception as e:
            logger.error(f"Failed to load proxy state from {filepath}: {e}")
            return 0

    def clear_failed(self):
        """Remove proxies that have exceeded max fail count"""
        initial_count = len(self.proxies)
        self.proxies = [p for p in self.proxies if p.fail_count < self.max_fail_count]
        removed = initial_count - len(self.proxies)

        if removed > 0:
            logger.info(f"Removed {removed} failed proxies")

    def on_proxy_used(self, callback: Callable[[ProxyInfo], Awaitable[None]]):
        """Register callback for when a proxy is used"""
        self._on_proxy_used = callback

    def on_proxy_failed(self, callback: Callable[[ProxyInfo, str], Awaitable[None]]):
        """Register callback for when a proxy fails"""
        self._on_proxy_failed = callback


# ============================================================================
# CONVENIENCE FUNCTIONS
# ============================================================================


async def test_proxy(proxy_url: str, timeout: float = 10.0) -> bool:
    """Quick proxy test."""
    try:
        async with ClientSession(timeout=ClientTimeout(total=timeout)) as session:
            protocol = "socks5" if "socks5://" in proxy_url else "http"
            proxy_str = proxy_url

            if not proxy_str.startswith(("http://", "https://", "socks4://", "socks5://")):
                proxy_str = f"http://{proxy_str}"

            # Try UTCMS first, then fallback
            for target_url in ("https://barname.utcms.ir", "https://httpbin.org/ip"):
                try:
                    async with session.get(
                        target_url,
                        proxy=f"{protocol}://{proxy_str.split('://')[1]}",
                    ) as response:
                        if response.status in (200, 301, 302):
                            return True
                except Exception:
                    continue
            return False
    except Exception:
        return False


# ============================================================================
# GLOBAL INSTANCE
# ============================================================================

_global_rotator: ProxyRotator | None = None


def get_proxy_rotator() -> ProxyRotator:
    """Get or create global proxy rotator instance"""
    global _global_rotator
    if _global_rotator is None:
        _global_rotator = ProxyRotator()
    return _global_rotator


def set_proxy_rotator(rotator: ProxyRotator):
    """Set global proxy rotator instance"""
    global _global_rotator
    _global_rotator = rotator

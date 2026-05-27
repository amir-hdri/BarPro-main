# -*- coding: utf-8 -*-
"""
Enterprise-Grade Proxy Rotator with Health Check
==================================================
Advanced proxy management with automatic health monitoring, latency tracking,
and intelligent rotation for maximum anonymity and reliability.
"""

import asyncio
import time
import random
import json
from dataclasses import dataclass, asdict, field
from typing import Optional, List, Dict, Any, Callable, Awaitable
from datetime import datetime
from aiohttp import ClientSession, ClientTimeout, ClientError
import logging

logger = logging.getLogger(__name__)


@dataclass
class ProxyConfig:
    """Configuration for adding a new proxy."""

    url: str
    protocol: str = "http"
    country: Optional[str] = None
    city: Optional[str] = None
    tags: List[str] = field(default_factory=list)


@dataclass
class ProxyInfo:
    """
    Comprehensive proxy information with health tracking.
    """

    url: str
    protocol: str = "http"
    username: Optional[str] = None
    password: Optional[str] = None
    country: Optional[str] = None
    city: Optional[str] = None
    isp: Optional[str] = None
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
    last_error: Optional[str] = None
    tags: List[str] = field(default_factory=list)

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
        return self.fail_count < 3 and self.success_rate >= 70.0

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
        score = self.success_rate * 0.5

        # Latency bonus (lower is better)
        if self.avg_latency < 1.0:
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

    def to_playwright_proxy(self) -> Dict[str, Any]:
        """Get proxy dictionary format for Playwright"""
        proxy_dict = {"server": f"{self.protocol}://{self.url.split('://')[-1]}"}
        if self.username and self.password:
            proxy_dict["username"] = self.username
            proxy_dict["password"] = self.password
        return proxy_dict

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary"""
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ProxyInfo":
        """Create from dictionary"""
        return cls(**data)


class ProxyRotator:
    """
    Advanced proxy rotator with health monitoring and intelligent selection.

    Features:
    - Automatic health checking
    - Latency tracking
    - Success rate monitoring
    - Country/region filtering
    - Intelligent rotation based on health score
    - Cooldown management
    - Persistent state (optional)
    """

    def __init__(
        self,
        cooldown: float = 5.0,
        health_check_interval: float = 300.0,  # 5 minutes
        max_health_check_attempts: int = 3,
        test_url: str = "https://httpbin.org/ip",
        timeout: float = 10.0,
        min_success_rate: float = 70.0,
        max_fail_count: int = 3,
    ):
        """
        Initialize proxy rotator.

        Args:
            cooldown: Minimum seconds between uses of same proxy
            health_check_interval: Seconds between automatic health checks
            max_health_check_attempts: Number of attempts for health check
            test_url: URL to test proxy connectivity
            timeout: Timeout for health check in seconds
            min_success_rate: Minimum success rate to consider proxy healthy
            max_fail_count: Maximum consecutive failures before marking unhealthy
        """
        self.proxies: List[ProxyInfo] = []
        self.cooldown = cooldown
        self.health_check_interval = health_check_interval
        self.max_health_check_attempts = max_health_check_attempts
        self.test_url = test_url
        self.timeout = timeout
        self.min_success_rate = min_success_rate
        self.max_fail_count = max_fail_count

        self._lock = asyncio.Lock()
        self._health_check_task: Optional[asyncio.Task] = None
        self._running = False
        self._on_proxy_used: Optional[Callable[[ProxyInfo], Awaitable[None]]] = None
        self._on_proxy_failed: Optional[Callable[[ProxyInfo, str], Awaitable[None]]] = None

        logger.info(f"ProxyRotator initialized with {len(self.proxies)} proxies")

    def load_from_list(self, proxy_urls: List[str]) -> int:
        """
        Load proxies from URL list.

        Args:
            proxy_urls: List of proxy URLs (with or without credentials)

        Returns:
            Number of proxies loaded
        """
        loaded = 0
        for url in proxy_urls:
            url = url.strip()
            if not url or url.startswith("#"):
                continue

            # Detect protocol
            if "socks5://" in url:
                protocol = "socks5"
            elif "socks4://" in url:
                protocol = "socks4"
            else:
                protocol = "http"

            # Attempt to extract auth
            username = None
            password = None
            clean_url = url

            # e.g., http://user:pass@1.2.3.4:8080
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
        """
        Load proxies from file (one per line).

        Args:
            filepath: Path to proxy list file
            encoding: File encoding

        Returns:
            Number of proxies loaded
        """
        try:
            with open(filepath, "r", encoding=encoding) as f:
                lines = f.readlines()
            return self.load_from_list(lines)
        except Exception as e:
            logger.error(f"Failed to load proxies from {filepath}: {e}")
            return 0

    def load_from_json(self, data: Dict[str, Any]) -> int:
        """
        Load proxies from JSON data.

        Args:
            data: JSON data with proxy information

        Returns:
            Number of proxies loaded
        """
        loaded = 0

        # Handle different JSON formats
        if "proxies" in data:
            # Format: {"proxies": [...]}
            for proxy_data in data["proxies"]:
                if isinstance(proxy_data, str):
                    self.load_from_list([proxy_data])
                elif isinstance(proxy_data, dict):
                    proxy = ProxyInfo.from_dict(proxy_data)
                    self.proxies.append(proxy)
                    loaded += 1
        elif "proxy_list" in data:
            # Format: {"proxy_list": [...]}
            for proxy_data in data["proxy_list"]:
                if isinstance(proxy_data, str):
                    self.load_from_list([proxy_data])
                elif isinstance(proxy_data, dict):
                    proxy = ProxyInfo.from_dict(proxy_data)
                    self.proxies.append(proxy)
                    loaded += 1
        else:
            # Assume it's a list
            for item in data:
                if isinstance(item, str):
                    self.load_from_list([item])
                elif isinstance(item, dict):
                    proxy = ProxyInfo.from_dict(item)
                    self.proxies.append(proxy)
                    loaded += 1

        logger.info(f"Loaded {loaded} proxies from JSON")
        return loaded

    def add_proxy(self, config: ProxyConfig) -> ProxyInfo:
        """
        Add a single proxy.

        Args:
            config: Configuration for the new proxy

        Returns:
            Created ProxyInfo object
        """
        proxy = ProxyInfo(
            url=config.url,
            protocol=config.protocol,
            country=config.country,
            city=config.city,
            tags=config.tags or [],
        )
        self.proxies.append(proxy)
        logger.debug(f"Added proxy: {config.url[:50]}...")
        return proxy

    async def get_next(
        self,
        country: str = None,
        tags: List[str] = None,
        exclude_failed: bool = True,
        prefer_low_latency: bool = True,
    ) -> Optional[ProxyInfo]:
        """
        Get next available proxy based on health score.

        Args:
            country: Filter by country code
            tags: Required tags (all must be present)
            exclude_failed: Exclude proxies with high fail count
            prefer_low_latency: Prefer proxies with lower latency

        Returns:
            ProxyInfo object or None if no proxy available
        """
        async with self._lock:
            now = time.time()

            # Filter proxies
            available = []
            for proxy in self.proxies:
                # Skip if not healthy
                if not proxy.is_healthy:
                    continue

                # Skip if in cooldown
                if (now - proxy.last_used) < self.cooldown:
                    continue

                # Filter by country
                if country and proxy.country != country:
                    continue

                # Filter by tags
                if tags and not all(tag in proxy.tags for tag in tags):
                    continue

                available.append(proxy)

            if not available:
                logger.debug("No available proxies")
                return None

            # Sort by health score (and optionally by latency)
            def sort_key(proxy):
                score = proxy.health_score
                if prefer_low_latency:
                    score -= proxy.avg_latency * 2  # Lower latency = higher score
                return score

            available.sort(key=sort_key, reverse=True)

            # Select best proxy (weighted random for variety)
            # Top 3 proxies have higher chance of being selected
            if len(available) >= 3:
                top_proxies = available[:3]
                chosen = random.choice(top_proxies)
            else:
                chosen = available[0]

            # Update last used time
            chosen.last_used = now

            # Callback for proxy usage
            if self._on_proxy_used:
                try:
                    await self._on_proxy_used(chosen)
                except Exception as e:
                    logger.warning(f"Proxy used callback failed: {e}")

            logger.debug(f"Selected proxy: {chosen.url[:50]}... (health: {chosen.health_score:.1f})")
            return chosen

    async def health_check(self, proxy: ProxyInfo) -> bool:
        """
        Perform health check on a single proxy.

        Args:
            proxy: Proxy to check

        Returns:
            True if proxy is healthy, False otherwise
        """
        start_time = time.time()

        try:
            # Try multiple test URLs
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
                            if response.status == 200:
                                latency = time.time() - start_time
                                proxy.record_success(latency)
                                proxy.last_health_check = time.time()

                                # Extract IP info
                                try:
                                    data = await response.json()
                                    if "ip" in data:
                                        logger.debug(
                                            f"Proxy OK: {proxy.url[:40]}... " f"IP: {data['ip']} ({latency:.2f}s)"
                                        )
                                except Exception:
                                    logger.debug(f"Proxy OK: {proxy.url[:40]}... " f"({latency:.2f}s)")

                                return True
                except ClientError:
                    continue
                except Exception as e:
                    continue

            # All URLs failed
            proxy.record_failure("All test URLs failed")
            return False

        except asyncio.TimeoutError:
            proxy.record_failure("Timeout")
            return False

        except Exception as e:
            proxy.record_failure(str(e))
            return False

    async def check_all(self) -> Dict[str, int]:
        """
        Run health check on all proxies.

        Returns:
            Dictionary with health statistics
        """
        logger.info(f"Running health check on {len(self.proxies)} proxies...")

        start_time = time.time()
        results = {
            "healthy": 0,
            "unhealthy": 0,
            "total": len(self.proxies),
            "checked": 0,
        }

        # Run health checks in parallel (limited concurrency)
        semaphore = asyncio.Semaphore(10)  # Max 10 concurrent checks

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
        logger.info(f"Health check complete: " f"{results['healthy']}/{results['total']} healthy " f"({elapsed:.1f}s)")

        return results

    async def start_auto_health_check(self, interval: float = None):
        """
        Start automatic background health checking.

        Args:
            interval: Seconds between health checks (uses default if None)
        """
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

    def get_stats(self) -> Dict[str, Any]:
        """
        Get comprehensive proxy statistics.

        Returns:
            Dictionary with proxy pool statistics
        """
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
        """
        Save proxy state to JSON file.

        Args:
            filepath: Output file path
            encoding: File encoding
        """
        data = {
            "version": "1.0",
            "updated_at": datetime.now().isoformat(),
            "proxies": [p.to_dict() for p in self.proxies],
        }

        with open(filepath, "w", encoding=encoding) as f:
            json.dump(data, f, indent=2, ensure_ascii=False)

        logger.info(f"Saved {len(self.proxies)} proxies to {filepath}")

    def load_from_file_state(self, filepath: str, encoding: str = "utf-8"):
        """
        Load proxy state from JSON file.

        Args:
            filepath: Input file path
            encoding: File encoding

        Returns:
            Number of proxies loaded
        """
        try:
            with open(filepath, "r", encoding=encoding) as f:
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
    """
    Quick proxy test.

    Args:
        proxy_url: Proxy URL to test
        timeout: Timeout in seconds

    Returns:
        True if proxy is working
    """
    try:
        async with ClientSession(timeout=ClientTimeout(total=timeout)) as session:
            # Auto-detect protocol
            protocol = "socks5" if "socks5://" in proxy_url else "http"
            proxy_str = proxy_url

            # Add protocol if missing
            if not proxy_str.startswith(("http://", "https://", "socks4://", "socks5://")):
                proxy_str = f"http://{proxy_str}"

            async with session.get(
                "https://httpbin.org/ip",
                proxy=f"{protocol}://{proxy_str.split('://')[1]}",
            ) as response:
                return response.status == 200
    except Exception:
        return False


# ============================================================================
# GLOBAL INSTANCE
# ============================================================================

_global_rotator: Optional[ProxyRotator] = None


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

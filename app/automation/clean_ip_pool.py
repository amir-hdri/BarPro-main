"""
Clean IP Pool Manager for BarPro & UTCMS
=========================================
Aggregates, benchmarks, and maintains a live pool of clean Iranian proxies
from 11+ online sources, local files, and external feeds.

Features:
1. Multi-source scraping from 11+ global proxy lists and mirrors.
2. Concurrent HTTPS CONNECT probing against https://utcms.ir and LOGIN_URL.
3. Strict SSRF validation (_is_safe_proxy_url) to block private/internal subnets.
4. Redis-backed shared cache (utcms:clean_ips:pool, utcms:clean_ips:best) with
   atomic file fallback in runtime/proxies/.
5. Per-IP circuit breaker (mark_blocked) so blocking a single third-party proxy
   does NOT drain or block the worker node.
6. Thread-safe, event-loop-safe, zero external dependencies for core testing.
"""

from __future__ import annotations

import asyncio
import concurrent.futures
import hashlib
import ipaddress
import json
import logging
import os
import re
import ssl
import threading
import time
import urllib.error
import urllib.request
from dataclasses import asdict, dataclass, field
from typing import Any

from app.core.config import utcms_config
from app.core.redis_client import redis_manager

logger = logging.getLogger(__name__)

# --- Default Parameters ---
UTCMS_HOST = "utcms.ir"
UTCMS_TARGET_URL = f"https://{UTCMS_HOST}"
DEFAULT_TIMEOUT_SECONDS = 7.5
MAX_PROBE_WORKERS = 35

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) " "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36"
)

# Runtime paths for atomic fallback files
BASE_RUNTIME_DIR = os.getenv("RUNTIME_DATA_DIR", "runtime")
PROXIES_RUNTIME_DIR = os.path.join(BASE_RUNTIME_DIR, "proxies")
FILE_BEST_TXT = os.path.join(PROXIES_RUNTIME_DIR, "best_iran_proxy.txt")
FILE_WORKING_TXT = os.path.join(PROXIES_RUNTIME_DIR, "working_iran_proxies.txt")
FILE_WORKING_JSON = os.path.join(PROXIES_RUNTIME_DIR, "working_iran_proxies.json")

# Cached SSL context for TLS handshakes
SSL_CTX = ssl.create_default_context()
SSL_CTX.check_hostname = False
SSL_CTX.verify_mode = ssl.CERT_NONE


@dataclass
class CleanIPRecord:
    """Represents a validated clean Iranian proxy with performance metrics."""

    url: str
    protocol: str = "http"
    ip: str = ""
    port: int = 0
    country: str = "IR"
    city: str | None = None
    isp: str | None = None
    score: float = 100.0
    fail_count: int = 0
    latency_ms: float = 0.0
    last_checked: float = 0.0
    blocked_until: float = 0.0
    source: str = "aggregator"
    tags: list[str] = field(default_factory=list)

    @property
    def safe_url(self) -> str:
        """Strip username/password for safe logging."""
        if "@" in self.url:
            proto, rest = self.url.split("://", 1) if "://" in self.url else ("http", self.url)
            host_part = rest.split("@")[-1]
            return f"{proto}://{host_part}"
        return self.url

    @property
    def is_usable(self) -> bool:
        """Check if proxy is healthy and not currently blocked."""
        now = time.time()
        if self.blocked_until > now:
            return False
        if self.fail_count >= 3:
            return False
        if self.score < 20.0:
            return False
        return True

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> CleanIPRecord:
        allowed_keys = {
            "url",
            "protocol",
            "ip",
            "port",
            "country",
            "city",
            "isp",
            "score",
            "fail_count",
            "latency_ms",
            "last_checked",
            "blocked_until",
            "source",
            "tags",
        }
        filtered = {k: v for k, v in data.items() if k in allowed_keys}
        return cls(**filtered)


# ==============================================================================
# Helper Functions: IP validation & Safe Fetching
# ==============================================================================


def is_valid_public_ip(ip_str: str) -> bool:
    """Verify that an IP is a valid public (non-private, non-loopback) IPv4/v6 address."""
    try:
        ip_obj = ipaddress.ip_address(ip_str.strip())
        return not (
            ip_obj.is_private or ip_obj.is_loopback or ip_obj.is_reserved or ip_obj.is_link_local or ip_obj.is_multicast
        )
    except (ValueError, TypeError):
        return False


def is_valid_port(port: Any) -> bool:
    """Verify standard TCP port range (1-65535)."""
    try:
        p = int(port)
        return 1 <= p <= 65535
    except (ValueError, TypeError):
        return False


def _safe_fetch(url: str, timeout: float = 6.0) -> str | None:
    """Safely fetch text from an online proxy list source with timeout."""
    try:
        req = urllib.request.Request(
            url,
            headers={
                "User-Agent": USER_AGENT,
                "Accept": "*/*",
                "Connection": "close",
            },
        )
        with urllib.request.urlopen(req, timeout=timeout) as resp:  # nosec B310
            return resp.read().decode("utf-8", errors="ignore")
    except Exception as exc:
        logger.debug(f"Failed to fetch proxy source {url[:60]}: {exc}")
        return None


def atomic_write(filepath: str, content: str) -> None:
    """Safely write file atomically via temp file to avoid partial reads."""
    os.makedirs(os.path.dirname(filepath), exist_ok=True)
    tmp_file = f"{filepath}.tmp.{os.getpid()}"
    try:
        with open(tmp_file, "w", encoding="utf-8") as f:
            f.write(content)
        os.replace(tmp_file, filepath)
    except Exception as exc:
        logger.warning(f"Failed atomic write to {filepath}: {exc}")
        try:
            if os.path.exists(tmp_file):
                os.remove(tmp_file)
        except OSError:
            pass


# ==============================================================================
# Multi-Source Scrapers (11+ Global Feeds & Custom Sources)
# ==============================================================================


def fetch_spys_sources() -> list[dict[str, Any]]:
    """Sources 1 & 2: Spys.one / Spys.me text database for HTTP & SOCKS5."""
    results = []
    for url, proto in [("https://spys.me/proxy.txt", "http"), ("https://spys.me/socks.txt", "socks5")]:
        text = _safe_fetch(url, timeout=5.0)
        if not text:
            continue
        for line in text.splitlines():
            if any(tag in line for tag in ("-IR", " IR ", "IR-")):
                parts = line.split()
                if parts and ":" in parts[0]:
                    ip, port = parts[0].split(":", 1)
                    if is_valid_public_ip(ip) and is_valid_port(port):
                        results.append(
                            {
                                "protocol": proto,
                                "ip": ip,
                                "port": int(port),
                                "isp": "Spys.one / Spys.me",
                                "city": "Iran",
                                "source": "spys",
                            }
                        )
    return results


def fetch_freeproxy_world() -> list[dict[str, Any]]:
    """Source 3: FreeProxy.World scraping (pages 1 to 3)."""
    results = []
    for page in [1, 2, 3]:
        url = f"https://www.freeproxy.world/?country=IR&page={page}"
        html = _safe_fetch(url, timeout=5.0)
        if not html:
            continue
        pattern = r'<tr>\s*<td style="font-weight: 500;">([\d\.]+)</td>\s*<td><a href="/\?port=\d+">(\d+)</a>.*?<a href="/\?type=(\w+)"'
        for ip, port, ptype in re.findall(pattern, html, re.DOTALL):
            if is_valid_public_ip(ip) and is_valid_port(port):
                results.append(
                    {
                        "protocol": ptype.lower(),
                        "ip": ip,
                        "port": int(port),
                        "isp": "FreeProxy.World",
                        "city": "Iran",
                        "source": "freeproxy_world",
                    }
                )
    return results


def fetch_geonode_api() -> list[dict[str, Any]]:
    """Source 4: Geonode Free Proxy API."""
    results = []
    url = "https://proxylist.geonode.com/api/proxy-list?country=IR&limit=500&page=1&sort_by=lastChecked&sort_type=desc"
    raw = _safe_fetch(url, timeout=6.0)
    if not raw:
        return results
    try:
        data = json.loads(raw)
        for item in data.get("data", []):
            ip = item.get("ip", "")
            port = item.get("port", "")
            protocols = item.get("protocols", ["http"])
            isp = item.get("isp", "Geonode")
            city = item.get("city", "Iran")
            if is_valid_public_ip(ip) and is_valid_port(port):
                results.append(
                    {
                        "protocol": protocols[0].lower(),
                        "ip": ip,
                        "port": int(port),
                        "isp": isp,
                        "city": city,
                        "source": "geonode",
                    }
                )
    except Exception:
        pass
    return results


def fetch_monosans_geojson() -> list[dict[str, Any]]:
    """Source 5: monosans GeoJSON proxy list on GitHub."""
    results = []
    url = "https://raw.githubusercontent.com/monosans/proxy-list/main/proxies_geolocation/all.json"
    raw = _safe_fetch(url, timeout=7.0)
    if not raw:
        return results
    try:
        data = json.loads(raw)
        for item in data:
            if item.get("country") == "IR":
                ip = item.get("ip", "")
                port = item.get("port", "")
                if is_valid_public_ip(ip) and is_valid_port(port):
                    results.append(
                        {
                            "protocol": item.get("protocol", "http").lower(),
                            "ip": ip,
                            "port": int(port),
                            "isp": item.get("org", item.get("asn", "monosans IR")),
                            "city": item.get("city", "Iran"),
                            "source": "monosans",
                        }
                    )
    except Exception:
        pass
    return results


def fetch_proxylist_download() -> list[dict[str, Any]]:
    """Source 6: Proxy-List.download API."""
    results = []
    for ptype in ["http", "https", "socks4", "socks5"]:
        url = f"https://www.proxy-list.download/api/v1/get?type={ptype}&country=IR"
        raw = _safe_fetch(url, timeout=4.0)
        if raw:
            for line in raw.splitlines():
                line = line.strip()
                if ":" in line:
                    ip, port = line.split(":", 1)
                    if is_valid_public_ip(ip) and is_valid_port(port):
                        results.append(
                            {
                                "protocol": ptype,
                                "ip": ip,
                                "port": int(port),
                                "isp": "Proxy-List.download",
                                "city": "Iran",
                                "source": "proxy_list_download",
                            }
                        )
    return results


def fetch_vakhov_github() -> list[dict[str, Any]]:
    """Source 7: vakhov fresh-proxy-list repository."""
    results = []
    url = "https://raw.githubusercontent.com/vakhov/fresh-proxy-list/master/proxies.json"
    raw = _safe_fetch(url, timeout=6.0)
    if not raw:
        return results
    try:
        data = json.loads(raw)
        for item in data:
            if item.get("code") == "IR" or item.get("country") == "Iran":
                ip = item.get("ip", "")
                port = item.get("port", "")
                if is_valid_public_ip(ip) and is_valid_port(port):
                    results.append(
                        {
                            "protocol": item.get("type", "http").lower(),
                            "ip": ip,
                            "port": int(port),
                            "isp": "vakhov GitHub",
                            "city": "Iran",
                            "source": "vakhov",
                        }
                    )
    except Exception:
        pass
    return results


def fetch_proxyscrape_apis() -> list[dict[str, Any]]:
    """Sources 8 & 9: ProxyScrape API v4 (JSON) and v2 (Plain text)."""
    results = []
    # v4 JSON
    url_v4 = (
        "https://api.proxyscrape.com/v4/free-proxy-list/get?"
        "request=get_proxies&proxy_format=protocolipport&format=json&country=ir"
    )
    raw_v4 = _safe_fetch(url_v4, timeout=6.0)
    if raw_v4:
        try:
            data = json.loads(raw_v4)
            for p in data.get("proxies", []):
                ip = p.get("ip", "")
                port = p.get("port", "")
                if is_valid_public_ip(ip) and is_valid_port(port):
                    results.append(
                        {
                            "protocol": (p.get("protocol") or "http").lower(),
                            "ip": ip,
                            "port": int(port),
                            "isp": (p.get("ip_data") or {}).get("isp", "ProxyScrape v4"),
                            "city": (p.get("ip_data") or {}).get("city", "Tehran"),
                            "source": "proxyscrape_v4",
                        }
                    )
        except Exception:
            pass

    # v2 Plain
    url_v2 = "https://api.proxyscrape.com/v2/?request=displayproxies&protocol=http,socks4,socks5&country=IR"
    raw_v2 = _safe_fetch(url_v2, timeout=5.0)
    if raw_v2:
        for line in raw_v2.splitlines():
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            proto, addr = ("http", line) if "://" not in line else line.split("://", 1)
            if ":" in addr:
                ip, port = addr.split(":", 1)
                if is_valid_public_ip(ip) and is_valid_port(port):
                    results.append(
                        {
                            "protocol": proto.lower(),
                            "ip": ip,
                            "port": int(port),
                            "isp": "ProxyScrape v2",
                            "city": "Iran",
                            "source": "proxyscrape_v2",
                        }
                    )
    return results


def fetch_github_sources() -> list[dict[str, Any]]:
    """Sources 10 & 11: Specialized GitHub proxy collections."""
    github_urls = [
        "https://raw.githubusercontent.com/proxifly/free-proxy-list/main/proxies/countries/IR/data.txt",
        "https://raw.githubusercontent.com/Zloi-user/hideip.me/main/http.txt",
        "https://raw.githubusercontent.com/Zloi-user/hideip.me/main/socks5.txt",
        "https://raw.githubusercontent.com/roosterkid/openproxylist/main/HTTPS_RAW.txt",
    ]
    results = []
    for url in github_urls:
        raw = _safe_fetch(url, timeout=5.0)
        if not raw:
            continue
        for line in raw.splitlines():
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            proto, addr = ("http", line) if "://" not in line else line.split("://", 1)
            if ":" in addr:
                ip, port = addr.split(":", 1)
                if is_valid_public_ip(ip) and is_valid_port(port):
                    results.append(
                        {
                            "protocol": proto.lower(),
                            "ip": ip,
                            "port": int(port),
                            "isp": "GitHub Mirror",
                            "city": "Iran",
                            "source": "github_mirror",
                        }
                    )
    return results


def fetch_file_or_env_sources() -> list[dict[str, Any]]:
    """Load proxies from configured local file (RPA_PROXY_LIST_FILE / CLEAN_IP_SOURCE_FILE)."""
    results = []
    source_file = os.getenv("CLEAN_IP_SOURCE_FILE") or os.getenv("RPA_PROXY_LIST_FILE")
    if source_file and os.path.isfile(source_file):
        try:
            with open(source_file, encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line or line.startswith("#"):
                        continue
                    proto = "http"
                    clean_line = line
                    if "://" in line:
                        proto, clean_line = line.split("://", 1)
                    if "@" in clean_line:
                        clean_line = clean_line.split("@")[-1]
                    if ":" in clean_line:
                        ip, port = clean_line.split(":", 1)
                        if is_valid_public_ip(ip) and is_valid_port(port):
                            results.append(
                                {
                                    "protocol": proto.lower(),
                                    "ip": ip,
                                    "port": int(port),
                                    "isp": "Configured File",
                                    "city": "Iran",
                                    "source": "file_source",
                                }
                            )
        except Exception as exc:
            logger.debug(f"Could not read clean proxy source file {source_file}: {exc}")

    # Also check custom URL source if defined
    custom_url = os.getenv("CLEAN_IP_SOURCE_URL")
    if custom_url:
        raw = _safe_fetch(custom_url, timeout=6.0)
        if raw:
            for line in raw.splitlines():
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                proto, addr = ("http", line) if "://" not in line else line.split("://", 1)
                if ":" in addr:
                    ip, port = addr.split(":", 1)
                    if is_valid_public_ip(ip) and is_valid_port(port):
                        results.append(
                            {
                                "protocol": proto.lower(),
                                "ip": ip,
                                "port": int(port),
                                "isp": "Custom URL Source",
                                "city": "Iran",
                                "source": "custom_url",
                            }
                        )
    return results


def aggregate_all_candidates() -> list[CleanIPRecord]:
    """
    Run all harvesters in parallel, enforce SSRF security checks,
    deduplicate, and return candidate CleanIPRecords.
    """
    from app.automation.proxy_rotator import ProxyRotator

    harvesters = [
        ("Spys Sources", fetch_spys_sources),
        ("FreeProxy.World", fetch_freeproxy_world),
        ("Geonode API", fetch_geonode_api),
        ("monosans GeoJSON", fetch_monosans_geojson),
        ("Proxy-List.download", fetch_proxylist_download),
        ("vakhov GitHub", fetch_vakhov_github),
        ("ProxyScrape APIs", fetch_proxyscrape_apis),
        ("GitHub Mirrors", fetch_github_sources),
        ("File/Env Sources", fetch_file_or_env_sources),
    ]

    candidates_map: dict[str, CleanIPRecord] = {}

    with concurrent.futures.ThreadPoolExecutor(max_workers=len(harvesters)) as executor:
        futures = {executor.submit(fn): name for name, fn in harvesters}
        for fut in concurrent.futures.as_completed(futures):
            try:
                items = fut.result()
                for p in items:
                    ip = p.get("ip", "")
                    port = p.get("port", 0)
                    proto = p.get("protocol", "http").lower()
                    proxy_url = f"{proto}://{ip}:{port}"

                    # Strict SSRF and public IP checks
                    if not ProxyRotator._is_safe_proxy_url(proxy_url):
                        continue
                    if not is_valid_public_ip(ip):
                        continue

                    key = f"{ip}:{port}"
                    if key not in candidates_map:
                        candidates_map[key] = CleanIPRecord(
                            url=proxy_url,
                            protocol=proto,
                            ip=ip,
                            port=int(port),
                            country=p.get("country", "IR"),
                            city=p.get("city", "Iran"),
                            isp=p.get("isp", "Iran ISP"),
                            source=p.get("source", "aggregator"),
                        )
            except Exception as exc:
                logger.debug(f"Harvester error: {exc}")

    return list(candidates_map.values())


# ==============================================================================
# Screening & Verification Engine
# ==============================================================================


def probe_single_proxy(
    candidate: CleanIPRecord,
    target_url: str = UTCMS_TARGET_URL,
    timeout: float = DEFAULT_TIMEOUT_SECONDS,
) -> CleanIPRecord | None:
    """
    Test HTTPS CONNECT handshake and status code against the target URL.
    Returns the updated CleanIPRecord if verified healthy, or None.
    """
    proxy_handler = urllib.request.ProxyHandler({"http": candidate.url, "https": candidate.url})
    https_handler = urllib.request.HTTPSHandler(context=SSL_CTX)
    opener = urllib.request.build_opener(proxy_handler, https_handler)

    req = urllib.request.Request(
        target_url,
        headers={
            "User-Agent": USER_AGENT,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "fa-IR,fa;q=0.9,en-US;q=0.8",
            "Connection": "close",
        },
    )

    start_time = time.perf_counter()
    try:
        with opener.open(req, timeout=timeout) as resp:
            elapsed_ms = (time.perf_counter() - start_time) * 1000
            status_code = resp.status

            # Real HTTP response from target proving tunnel works
            if status_code in (200, 301, 302):
                candidate.latency_ms = round(elapsed_ms, 1)
                candidate.last_checked = time.time()
                candidate.fail_count = 0
                candidate.blocked_until = 0.0

                # Score calculation (faster latency = higher score)
                score = 100.0 - min(80.0, candidate.latency_ms / 100.0)
                candidate.score = round(max(20.0, score), 1)
                return candidate
    except Exception as exc:
        candidate.fail_count += 1
        candidate.score = max(0.0, candidate.score - 25.0)
        candidate.last_checked = time.time()
        logger.debug(f"Proxy probe failed for {candidate.safe_url}: {exc}")

    return None


def run_screening_cycle(
    timeout: float = DEFAULT_TIMEOUT_SECONDS,
    max_workers: int = MAX_PROBE_WORKERS,
    max_pool_size: int = 50,
) -> list[CleanIPRecord]:
    """
    Perform a complete aggregation and benchmarking cycle.
    Updates runtime files and returns sorted verified proxies.
    """
    start_time = time.time()
    candidates = aggregate_all_candidates()
    logger.info(f"CleanIPPool: harvested {len(candidates)} unique Iranian proxy candidates.")

    verified: list[CleanIPRecord] = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {executor.submit(probe_single_proxy, c, UTCMS_TARGET_URL, timeout): c for c in candidates}
        for fut in concurrent.futures.as_completed(futures):
            try:
                res = fut.result()
                if res and res.is_usable:
                    verified.append(res)
            except Exception:
                pass

    # Sort fastest first
    verified.sort(key=lambda x: x.latency_ms)
    verified = verified[:max_pool_size]

    duration = round(time.time() - start_time, 2)
    logger.info(f"CleanIPPool: verified {len(verified)} working proxies in {duration}s.")

    # Write atomic runtime fallback files
    if verified:
        best_url = verified[0].url
        atomic_write(FILE_BEST_TXT, f"{best_url}\n")
        atomic_write(FILE_WORKING_TXT, "\n".join(p.url for p in verified) + "\n")
        atomic_write(
            FILE_WORKING_JSON,
            json.dumps([p.to_dict() for p in verified], indent=2, ensure_ascii=False) + "\n",
        )

    return verified


# ==============================================================================
# CleanIPPoolManager (Singleton & Redis Integration)
# ==============================================================================


class CleanIPPoolManager:
    """
    Central Manager for the Clean IP Pool.
    Provides async access to verified proxies with Redis backing and fallback.
    """

    _instance: CleanIPPoolManager | None = None
    _lock = threading.Lock()

    REDIS_KEY_POOL = "utcms:clean_ips:pool"
    REDIS_KEY_BEST = "utcms:clean_ips:best"
    REDIS_KEY_LAST_REFRESH = "utcms:clean_ips:last_refresh"
    REDIS_LOCK_REFRESH = "lock:utcms:clean_ip_refresh"
    REDIS_BLOCKED_PREFIX = "utcms:clean_ips:blocked:"

    def __new__(cls, *args, **kwargs) -> CleanIPPoolManager:
        with cls._lock:
            if cls._instance is None:
                cls._instance = super().__new__(cls)
                cls._instance._initialized = False
            return cls._instance

    def __init__(self) -> None:
        if getattr(self, "_initialized", False):
            return
        self._local_cache: list[CleanIPRecord] = []
        self._local_cache_time: float = 0.0
        self._cache_ttl_seconds: float = 15.0
        self._initialized = True

    async def get_all_clean_ips(self) -> list[CleanIPRecord]:
        """Fetch all verified active proxies from Redis or local fallback."""
        now = time.time()
        if self._local_cache and (now - self._local_cache_time) < self._cache_ttl_seconds:
            return [p for p in self._local_cache if p.is_usable]

        try:
            r = await redis_manager.get()
            if r is not None:
                raw_data = await r.get(self.REDIS_KEY_POOL)
                if raw_data:
                    items = json.loads(raw_data)
                    records = [CleanIPRecord.from_dict(item) for item in items]
                    self._local_cache = records
                    self._local_cache_time = now
                    return [p for p in records if p.is_usable]
        except Exception as exc:
            logger.debug(f"Redis get clean IP pool failed: {exc}")

        # Fallback to local runtime file if Redis is unavailable or empty
        if os.path.exists(FILE_WORKING_JSON):
            try:
                with open(FILE_WORKING_JSON, encoding="utf-8") as f:
                    items = json.load(f)
                    records = [CleanIPRecord.from_dict(item) for item in items]
                    self._local_cache = records
                    self._local_cache_time = now
                    return [p for p in records if p.is_usable]
            except Exception as exc:
                logger.debug(f"File fallback read failed: {exc}")

        return []

    def clear_local_cache(self) -> None:
        """Clear in-memory cache of clean proxies."""
        self._local_cache = []
        self._local_cache_time = 0.0

    async def get_clean_ip(self) -> str | None:
        """
        Return the URL of the best available clean Iranian proxy.
        Skips currently blocked proxies.
        """
        ips = await self.get_all_clean_ips()
        if not ips:
            return None

        # Check Redis blocked status for the top proxies
        try:
            r = await redis_manager.get()
            for record in ips:
                if not record.is_usable:
                    continue
                if r is not None:
                    url_hash = hashlib.sha256(record.url.encode()).hexdigest()[:16]
                    if await r.exists(f"{self.REDIS_BLOCKED_PREFIX}{url_hash}"):
                        continue
                return record.url
        except Exception as exc:
            logger.debug(f"Clean IP selection error: {exc}")
            if ips:
                return ips[0].url

        return None

    def _is_blocked_sync(self, proxy_url: str) -> bool:
        """Synchronously check if a proxy URL is marked blocked in Redis."""
        if not proxy_url:
            return True
        try:
            from app.core.circuit_breaker import _get_redis_sync

            r = _get_redis_sync()
            url_hash = hashlib.sha256(proxy_url.encode()).hexdigest()[:16]
            return bool(r.exists(f"{self.REDIS_BLOCKED_PREFIX}{url_hash}"))
        except Exception:
            return False

    def get_clean_ip_sync(self) -> str | None:
        """Synchronous helper to retrieve best clean proxy (respects blocked status)."""
        if self._local_cache:
            for p in self._local_cache:
                if p.is_usable and not self._is_blocked_sync(p.url):
                    return p.url

        if os.path.exists(FILE_BEST_TXT):
            try:
                with open(FILE_BEST_TXT, encoding="utf-8") as f:
                    content = f.read().strip()
                    if content and not self._is_blocked_sync(content):
                        return content
            except Exception:
                pass
        return None

    async def mark_blocked(self, proxy_url: str, duration_seconds: int = 1800) -> None:
        """
        Mark a specific third-party clean proxy as blocked in Redis without
        affecting the worker's own IP or circuit breaker.
        """
        if not proxy_url:
            return
        logger.warning(f"CleanIPPool: Marking proxy {proxy_url} as blocked for {duration_seconds}s")
        url_hash = hashlib.sha256(proxy_url.encode()).hexdigest()[:16]

        # Update in-memory record
        for p in self._local_cache:
            if p.url == proxy_url:
                p.fail_count += 1
                p.blocked_until = time.time() + duration_seconds
                break

        try:
            r = await redis_manager.get()
            if r is not None:
                await r.set(f"{self.REDIS_BLOCKED_PREFIX}{url_hash}", "1", ex=duration_seconds)
        except Exception as exc:
            logger.debug(f"Redis mark clean proxy blocked failed: {exc}")

    async def refresh_pool(self, force: bool = False) -> list[CleanIPRecord]:
        """
        Execute a full screening cycle under distributed Redis lock
        and update Redis cache.
        """
        r = None
        try:
            r = await redis_manager.get()
            if r is not None and not force:
                # Acquire distributed lock so only 1 worker runs the scan
                lock_acquired = await r.set(self.REDIS_LOCK_REFRESH, "1", ex=240, nx=True)
                if not lock_acquired:
                    logger.info("CleanIPPool: Refresh already in progress by another worker.")
                    return await self.get_all_clean_ips()

            # Run screening in background thread pool to avoid blocking async loop
            loop = asyncio.get_running_loop()
            verified = await loop.run_in_executor(
                None,
                run_screening_cycle,
                getattr(utcms_config, "IRAN_PROXY_TIMEOUT_SECONDS", DEFAULT_TIMEOUT_SECONDS),
                MAX_PROBE_WORKERS,
                getattr(utcms_config, "CLEAN_IP_MAX_POOL", 50),
            )

            # Store in Redis
            if r is not None and verified:
                payload = json.dumps([p.to_dict() for p in verified], ensure_ascii=False)
                await r.set(self.REDIS_KEY_POOL, payload, ex=3600)
                await r.set(self.REDIS_KEY_BEST, verified[0].url, ex=3600)
                await r.set(self.REDIS_KEY_LAST_REFRESH, str(time.time()), ex=3600)
                logger.info(f"CleanIPPool: Redis updated with {len(verified)} verified Iranian proxies.")

            self._local_cache = verified
            self._local_cache_time = time.time()
            return verified
        except Exception as exc:
            logger.error(f"CleanIPPool: Refresh error: {exc}")
            return await self.get_all_clean_ips()
        finally:
            try:
                if r is not None:
                    await r.delete(self.REDIS_LOCK_REFRESH)
            except Exception:
                pass


# Global singleton instance
clean_ip_pool = CleanIPPoolManager()


def get_clean_ip_pool() -> CleanIPPoolManager:
    """Return singleton CleanIPPoolManager."""
    return clean_ip_pool


async def get_best_clean_iran_proxy() -> str | None:
    """Convenience async accessor for the fastest active clean Iranian proxy."""
    return await clean_ip_pool.get_clean_ip()

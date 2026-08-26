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
import socket
import ssl
import threading
import time
import urllib.error
import urllib.request
import uuid
from dataclasses import asdict, dataclass, field
from typing import Any
from urllib.parse import urljoin, urlparse

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

# curl_cffi is the SAME transport used by the RPA login path
# (utcms_http_login) and the Squid health check (worker_proxy), both with
# ``impersonate="chrome120"``. Screening must present the identical TLS
# fingerprint, otherwise a proxy that passes a Python-urllib probe can still be
# WAF-blocked for real Chrome-fingerprint traffic (and vice versa).
try:
    import curl_cffi  # noqa: F401

    _CURL_CFFI_IMPORT_ERROR: str | None = None
except Exception as _exc:  # pragma: no cover - depends on environment
    _CURL_CFFI_IMPORT_ERROR = str(_exc)

# Headers mirror utcms_http_login.UtcmsHttpLoginClient so WAF sees one
# consistent (TLS + header + UA) identity end-to-end.
PROBE_HEADERS = {
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9,fa;q=0.8",
    "Accept-Encoding": "gzip, deflate, br",
    "Cache-Control": "no-cache",
    "Pragma": "no-cache",
    "Sec-Fetch-Dest": "document",
    "Sec-Fetch-Mode": "navigate",
    "Sec-Fetch-Site": "same-origin",
    "Sec-Fetch-User": "?1",
    "Upgrade-Insecure-Requests": "1",
}


@dataclass
class CleanIPRecord:
    """Represents a validated clean proxy with performance metrics.

    ``country`` is what the SOURCE DECLARED (may be empty for global mirrors).
    ``observed_country`` is what a GeoIP endpoint saw when queried THROUGH the
    proxy (ground truth). Only records with ``egress_verified=True`` and an
    Iranian observed egress belong in the production pool.
    """

    VALID_PROTOCOLS = ("http", "https", "socks4", "socks5")

    url: str
    protocol: str = "http"
    ip: str = ""
    port: int = 0
    country: str = ""
    city: str | None = None
    isp: str | None = None
    score: float = 100.0
    fail_count: int = 0
    latency_ms: float = 0.0
    last_checked: float = 0.0
    blocked_until: float = 0.0
    source: str = "aggregator"
    tags: list[str] = field(default_factory=list)
    observed_country: str | None = None
    egress_verified: bool = False

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
    def from_dict(cls, data: dict[str, Any]) -> CleanIPRecord | None:
        """Deserialize with validation — malformed/stale Redis or file state
        must never re-enter the runtime pool (validate → normalize → accept)."""
        if not isinstance(data, dict):
            return None
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
            "observed_country",
            "egress_verified",
        }
        filtered = {k: v for k, v in data.items() if k in allowed_keys}
        url = str(filtered.get("url") or "").strip()
        protocol = str(filtered.get("protocol") or "http").lower().strip()
        ip = str(filtered.get("ip") or "").strip()
        try:
            port = int(filtered.get("port") or 0)
        except (TypeError, ValueError):
            return None
        if not url or protocol not in cls.VALID_PROTOCOLS:
            return None
        if not is_valid_public_ip(ip) or not is_valid_port(port):
            return None
        filtered["url"] = url
        filtered["protocol"] = protocol
        filtered["ip"] = ip
        filtered["port"] = port
        try:
            return cls(**filtered)
        except TypeError:
            return None


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


def _is_safe_source_url(url: str) -> bool:
    """Allow source feeds only over HTTP(S) to publicly routable hosts."""
    try:
        parsed = urlparse(url)
        if parsed.scheme not in {"http", "https"} or not parsed.hostname:
            return False
        if parsed.username or parsed.password:
            return False
        addresses = {
            item[4][0]
            for item in socket.getaddrinfo(parsed.hostname, parsed.port or (443 if parsed.scheme == "https" else 80))
        }
        return bool(addresses) and all(is_valid_public_ip(address) for address in addresses)
    except (OSError, ValueError):
        return False


class _SafeRedirectHandler(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        absolute_url = urljoin(req.full_url, newurl)
        if not _is_safe_source_url(absolute_url):
            raise urllib.error.URLError("unsafe redirect target")
        return super().redirect_request(req, fp, code, msg, headers, absolute_url)


def _safe_fetch(url: str, timeout: float = 6.0) -> str | None:
    """Safely fetch text from an online proxy list source with timeout."""
    if not _is_safe_source_url(url):
        logger.warning("CleanIPPool: blocked unsafe source URL host")
        return None
    try:
        req = urllib.request.Request(
            url,
            headers={
                "User-Agent": USER_AGENT,
                "Accept": "*/*",
                "Connection": "close",
            },
        )
        opener = urllib.request.build_opener(_SafeRedirectHandler())
        with opener.open(req, timeout=timeout) as resp:
            return resp.read().decode("utf-8", errors="ignore")
    except Exception as exc:
        logger.debug("Failed to fetch proxy source host %s: %s", urlparse(url).hostname or "unknown", exc)
        return None


def atomic_write(filepath: str, content: str) -> None:
    """Safely write file atomically via temp file to avoid partial reads."""
    os.makedirs(os.path.dirname(filepath), exist_ok=True)
    tmp_file = f"{filepath}.tmp.{os.getpid()}"
    try:
        with open(tmp_file, "w", encoding="utf-8") as f:
            f.write(content)
        os.chmod(tmp_file, 0o600)
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
    """Sources 10 & 11: Specialized GitHub proxy collections.

    Only the proxifly country-scoped file is IR-filtered at the source. The
    other mirrors are GLOBAL lists — their entries must NOT inherit Iranian
    metadata; the egress verification stage decides real country later.
    """
    ir_scoped = "https://raw.githubusercontent.com/proxifly/free-proxy-list/main/proxies/countries/IR/data.txt"
    global_mirrors = [
        "https://raw.githubusercontent.com/Zloi-user/hideip.me/main/http.txt",
        "https://raw.githubusercontent.com/Zloi-user/hideip.me/main/socks5.txt",
        "https://raw.githubusercontent.com/roosterkid/openproxylist/main/HTTPS_RAW.txt",
    ]
    results = []
    for url, declared_country in [(ir_scoped, "IR"), *[(u, "") for u in global_mirrors]]:
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
                            # "" = unknown; never fabricate "Iran" for a global list.
                            "city": "Iran" if declared_country == "IR" else None,
                            "country": declared_country,
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


def _dedupe_candidates(items: list[dict[str, Any]]) -> dict[str, CleanIPRecord]:
    """Normalize + dedupe raw harvester output.

    Identity is ``(protocol, ip, port)`` — the same ip:port offering both HTTP
    and SOCKS5 are TWO independent candidates (previously they collided on
    ``ip:port`` and whichever source answered first silently won). Country is
    only kept when a source explicitly declares it; there is NO "IR" default.
    """
    candidates_map: dict[str, CleanIPRecord] = {}
    try:
        from app.automation.proxy_rotator import ProxyRotator
    except Exception as exc:
        logger.debug(f"SSRF checks unavailable due to import failure: {exc}")
        return {}
    for p in items:
        ip = str(p.get("ip", "") or "").strip()
        port = p.get("port", 0)
        proto = str(p.get("protocol", "http") or "http").lower().strip()
        if proto not in CleanIPRecord.VALID_PROTOCOLS:
            continue
        proxy_url = f"{proto}://{ip}:{port}"

        # Strict SSRF and public IP checks
        if not ProxyRotator._is_safe_proxy_url(proxy_url):
            continue
        if not is_valid_public_ip(ip):
            continue
        if not is_valid_port(port):
            continue

        key = f"{proto}://{ip}:{port}"
        if key not in candidates_map:
            candidates_map[key] = CleanIPRecord(
                url=proxy_url,
                protocol=proto,
                ip=ip,
                port=int(port),
                country=str(p.get("country") or "").strip(),
                city=p.get("city"),
                isp=p.get("isp") or "Unknown ISP",
                source=p.get("source", "aggregator"),
            )
    return candidates_map


def aggregate_all_candidates() -> list[CleanIPRecord]:
    """
    Run all harvesters in parallel, enforce SSRF security checks,
    deduplicate, and return candidate CleanIPRecords.
    """
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

    raw_items: list[dict[str, Any]] = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=len(harvesters)) as executor:
        futures = {executor.submit(fn): name for name, fn in harvesters}
        for fut in concurrent.futures.as_completed(futures):
            try:
                raw_items.extend(fut.result())
            except Exception as exc:
                logger.debug(f"Harvester error: {futures[fut]}: {exc}")

    return list(_dedupe_candidates(raw_items).values())


# ==============================================================================
# Screening & Verification Engine
# ==============================================================================


def _probe_via_curl_cffi(candidate: CleanIPRecord, target_url: str, timeout: float) -> tuple[int, float, str]:
    """Probe through ``candidate`` with the production chrome120 TLS fingerprint.

    Returns ``(status_code, elapsed_ms, body_snippet)``. Raises on
    transport-level failure (dead proxy, reset, timeout) — which is itself a
    verdict distinct from "target rejected this IP".
    """
    from curl_cffi import requests as cc_requests  # type: ignore[import-not-found]

    session = cc_requests.Session(
        impersonate="chrome120",
        proxies={"http": candidate.url, "https": candidate.url},
        timeout=max(1.0, timeout),
        # Matches worker_proxy.check_proxy_health: free proxies sometimes
        # MITM TLS; only tunnel + WAF acceptance are under test here.
        verify=False,
    )
    try:
        session.headers.update(PROBE_HEADERS)
        start_time = time.perf_counter()
        response = session.get(target_url)
        elapsed_ms = (time.perf_counter() - start_time) * 1000
        snippet = ""
        try:
            snippet = (response.text or "")[:400].lower()
        except Exception:
            snippet = ""
        return response.status_code, elapsed_ms, snippet
    finally:
        try:
            session.close()
        except Exception:
            logger.debug("CleanIPPool: curl_cffi probe session close failed", exc_info=True)


# WAF/bot-challenge markers seen on 200 pages that are NOT the real UTCMS site
# (JS challenges, interstitials, block pages). A 200 alone proves nothing.
WAF_CHALLENGE_MARKERS = (
    "just a moment",
    "cf-browser-verification",
    "cf_chl",
    "checking your browser",
    "access denied",
    "denied access",
    "captcha",
    "bot detection",
    "are you a robot",
    "attention required",
    "request unsuccessful",  # Cloudflare-style 200-body block
)

# Statuses meaning THE TARGET refused this client/IP: proxy tunnel is fine.
TARGET_REJECTION_STATUSES = {403, 429}


def classify_probe_response(status_code: int | None, body_snippet: str) -> str:
    """Classify one probe round into independent verdicts.

    Returns one of:
      - "healthy":         real target page, accepted status, no challenge markers
      - "waf_challenge":   HTTP 2xx/3xx but body is a WAF/challenge/block page
      - "target_rejected": transport OK but target answered 403/429 → THIS IP is
                           not acceptable to UTCMS even though the proxy is alive
      - "unacceptable":    any other HTTP status
    Transport-level exceptions never reach here (they mean "dead").
    """
    body = (body_snippet or "").lower()
    if status_code in TARGET_REJECTION_STATUSES:
        return "target_rejected"
    if status_code in (200, 301, 302):
        if any(marker in body for marker in WAF_CHALLENGE_MARKERS):
            return "waf_challenge"
        return "healthy"
    return "unacceptable"


def probe_single_proxy(
    candidate: CleanIPRecord,
    target_url: str = UTCMS_TARGET_URL,
    timeout: float = DEFAULT_TIMEOUT_SECONDS,
) -> CleanIPRecord | None:
    """
    Test HTTPS CONNECT handshake against the target URL using the SAME Chrome
    fingerprint as production traffic. Returns the updated CleanIPRecord if
    verified healthy, or None.

    Verdicts are independent — "proxy dead" (transport), "UTCMS rejected this
    IP" (403/429) and "WAF challenge page" (2xx block body) get different
    penalties; a target-rejected IP must never enter the pool as "working".

    Falls back to a plain urllib opener only when curl_cffi is unavailable;
    that legacy path handles http(s) candidates only (urllib has no native
    SOCKS support) and is NOT fingerprint-representative.
    """
    if _CURL_CFFI_IMPORT_ERROR is None:
        # curl_cffi speaks http/https/socks4/socks5 natively via libcurl.
        try:
            status_code, elapsed_ms, snippet = _probe_via_curl_cffi(candidate, target_url, timeout)
            verdict = classify_probe_response(status_code, snippet)
            if verdict == "healthy":
                candidate.tags = [t for t in candidate.tags if t != "utcms_rejected"]
                return _mark_probe_healthy(candidate, elapsed_ms)
            penalty = 50.0 if verdict in ("target_rejected", "waf_challenge") else 25.0
            _mark_probe_failed(candidate, f"{verdict} status={status_code}", penalty=penalty)
            if verdict in ("target_rejected", "waf_challenge"):
                tag = "utcms_rejected" if verdict == "target_rejected" else "waf_challenge"
                if tag not in candidate.tags:
                    candidate.tags.append(tag)
            return None
        except Exception as exc:
            return _mark_probe_failed(candidate, str(exc))

    if candidate.protocol not in ("http", "https"):
        logger.debug(f"Proxy probe skipped (no SOCKS-capable client): {candidate.safe_url}")
        return None

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
            verdict = classify_probe_response(resp.status, "")
            if verdict == "healthy":
                return _mark_probe_healthy(candidate, elapsed_ms)
            penalty = 50.0 if verdict == "target_rejected" else 25.0
            return _mark_probe_failed(candidate, f"{verdict} status={resp.status}", penalty=penalty)
    except Exception as exc:
        return _mark_probe_failed(candidate, str(exc))


def _mark_probe_healthy(candidate: CleanIPRecord, elapsed_ms: float) -> CleanIPRecord:
    candidate.latency_ms = round(elapsed_ms, 1)
    candidate.last_checked = time.time()
    candidate.fail_count = 0
    candidate.blocked_until = 0.0
    # Score calculation (faster latency = higher score)
    score = 100.0 - min(80.0, candidate.latency_ms / 100.0)
    candidate.score = round(max(20.0, score), 1)
    return candidate


def _mark_probe_failed(candidate: CleanIPRecord, reason: str, penalty: float = 25.0) -> None:
    candidate.fail_count += 1
    candidate.score = max(0.0, candidate.score - penalty)
    candidate.last_checked = time.time()
    logger.debug(f"Proxy probe failed for {candidate.safe_url}: {reason}")
    return None


def _verify_egress_country(candidate: CleanIPRecord, timeout: float = 8.0) -> str | None:
    """Measure the REAL egress IP country by querying a GeoIP endpoint THROUGH
    the proxy. A candidate advertising 1.2.3.4 may exit from somewhere else
    entirely (transparent chains, CDNs); source metadata is not evidence.

    Returns the observed ISO country code ("" if endpoint answered without one)
    or None when the check itself could not run.
    """
    if _CURL_CFFI_IMPORT_ERROR is not None:
        return None
    try:
        from curl_cffi import requests as cc_requests  # type: ignore[import-not-found]

        session = cc_requests.Session(
            impersonate="chrome120",
            proxies={"http": candidate.url, "https": candidate.url},
            timeout=max(1.0, timeout),
            verify=False,
        )
        try:
            session.headers.update({"User-Agent": USER_AGENT, "Accept": "application/json"})
            response = session.get("http://ip-api.com/json/?fields=countryCode,status")
            data = response.json()
            if isinstance(data, dict):
                return str(data.get("countryCode") or "").upper()
        finally:
            try:
                session.close()
            except Exception:
                logger.debug("CleanIPPool: egress verify session close failed", exc_info=True)
    except Exception as exc:
        logger.debug(f"CleanIPPool: egress verification failed for {candidate.safe_url}: {exc}")
    return None


def run_screening_cycle(
    timeout: float = DEFAULT_TIMEOUT_SECONDS,
    max_workers: int = MAX_PROBE_WORKERS,
    max_pool_size: int = 50,
    max_candidates: int = 1000,
) -> list[CleanIPRecord]:
    """
    Perform a complete aggregation → probe → egress-verify → rank cycle.

    Pipeline per candidate:
      syntax/SSRF validation → Chrome-fingerprint UTCMS probe (dead vs
      target-rejected vs WAF-challenge vs healthy) → observed-egress GeoIP
      verification (declared IR is NOT trusted; measured IR is) → ranked pool.

    Updates runtime files and returns sorted verified proxies.
    """
    start_time = time.time()
    candidates = aggregate_all_candidates()[: max(1, min(max_candidates, 5000))]
    ir_declared = sum(1 for c in candidates if c.country == "IR")
    logger.info(
        f"CleanIPPool: harvested {len(candidates)} unique proxy candidates "
        f"({ir_declared} declared IR by their sources)."
    )

    verified: list[CleanIPRecord] = []
    probe_timeout = max(1.0, min(timeout, 30.0))

    def _egress_check(rec: CleanIPRecord) -> CleanIPRecord:
        observed = _verify_egress_country(rec, timeout=max(4.0, probe_timeout))
        if observed is None:
            # Check unavailable: keep record but mark it unverified so callers
            # can distinguish measured truth from source claims.
            rec.egress_verified = False
            rec.observed_country = None
            rec.tags.append("geo_unverified")
            return rec
        rec.observed_country = observed or None
        rec.egress_verified = bool(observed)
        if observed == "IR":
            return rec
        # Measured non-Iranian egress: hard fail for this pool's purpose.
        rec.score = max(0.0, rec.score - 60.0)
        if "non_iranian_egress" not in rec.tags:
            rec.tags.append("non_iranian_egress")
        return rec

    with concurrent.futures.ThreadPoolExecutor(max_workers=max(1, min(max_workers, 64))) as executor:
        futures = {executor.submit(probe_single_proxy, c, UTCMS_TARGET_URL, probe_timeout): c for c in candidates}
        for fut in concurrent.futures.as_completed(futures):
            try:
                res = fut.result()
                if res and res.is_usable:
                    verified.append(res)
            except Exception:
                pass

        # Sort fastest first, then measure the real egress of only the head of
        # the list (bounded cost): declared-IR records must OBSERVE as IR;
        # global-mirror records must observe as IR too, else they are demoted.
        verified.sort(key=lambda x: x.latency_ms)
        shortlist = verified[: max_pool_size * 3]
        if shortlist:
            geo_futures = {executor.submit(_egress_check, r): r for r in shortlist}
            checked: list[CleanIPRecord] = []
            for fut in concurrent.futures.as_completed(geo_futures):
                try:
                    checked.append(fut.result())
                except Exception:
                    pass
            verified = [r for r in checked if r.is_usable and "non_iranian_egress" not in r.tags]
            verified.sort(key=lambda x: (not x.egress_verified, x.latency_ms))

    verified = verified[: max(1, max_pool_size)]

    duration = round(time.time() - start_time, 2)
    ir_measured = sum(1 for r in verified if r.observed_country == "IR")
    logger.info(
        f"CleanIPPool: verified {len(verified)} working proxies in {duration}s "
        f"({ir_measured} with measured Iranian egress)."
    )

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
        self._refresh_lock = threading.Lock()
        # Round-robin cursors: selection must ROTATE across the whole pool.
        # Always returning the lowest-latency record concentrates every worker's
        # traffic on one IP — the pattern real mobile users never produce and
        # WAFs punish regardless of how "clean" the address is.
        self._rr_async: int = 0
        self._rr_sync: int = 0
        # Background refresh kick state for the sync path (see get_clean_ip_sync)
        self._bg_refresh_thread: threading.Thread | None = None
        self._bg_refresh_last_kick: float = 0.0
        self._initialized = True

    async def get_all_clean_ips(self) -> list[CleanIPRecord]:
        """Fetch all verified active proxies from Redis or local fallback."""
        now = time.time()
        if self._local_cache and (now - self._local_cache_time) < self._cache_ttl_seconds:
            return list(self._local_cache)

        try:
            r = await redis_manager.get()
            if r is not None:
                raw_data = await r.get(self.REDIS_KEY_POOL)
                if raw_data:
                    items = json.loads(raw_data)
                    records = [rec for rec in (CleanIPRecord.from_dict(item) for item in items) if rec is not None]
                    self._local_cache = records
                    self._local_cache_time = now
                    return records
        except Exception as exc:
            logger.debug(f"Redis get clean IP pool failed: {exc}")

        # Fallback to local runtime file if Redis is unavailable or empty
        if os.path.exists(FILE_WORKING_JSON):
            try:
                with open(FILE_WORKING_JSON, encoding="utf-8") as f:
                    items = json.load(f)
                    records = [rec for rec in (CleanIPRecord.from_dict(item) for item in items) if rec is not None]
                    self._local_cache = records
                    self._local_cache_time = now
                    return records
            except Exception as exc:
                logger.debug(f"File fallback read failed: {exc}")

        return []

    def clear_local_cache(self) -> None:
        """Clear in-memory cache of clean proxies and reset rotation state."""
        self._local_cache = []
        self._local_cache_time = 0.0
        self._rr_async = 0
        self._rr_sync = 0

    async def get_clean_ip(self) -> str | None:
        """
        Return a usable clean proxy URL, ROTATING across the whole pool.

        Real users arrive from thousands of different (mobile) IPs; funneling
        every job through the single lowest-latency proxy guarantees WAF and
        rate-limit attention for that one address no matter how clean the pool
        is. Round-robin distributes load over ALL verified records; blocked or
        dead entries are skipped.
        """
        ips = [record for record in await self.get_all_clean_ips() if record.is_usable]
        if not ips:
            return None

        start = self._rr_async % len(ips)
        self._rr_async = (self._rr_async + 1) % len(ips)
        ordered = ips[start:] + ips[:start]

        # Check Redis blocked status while walking the rotated order
        try:
            r = await redis_manager.get()
            for record in ordered:
                if not record.is_usable:
                    continue
                if r is not None:
                    url_hash = hashlib.sha256(record.url.encode()).hexdigest()[:16]
                    if await r.exists(f"{self.REDIS_BLOCKED_PREFIX}{url_hash}"):
                        continue
                return record.url
        except Exception as exc:
            logger.debug(f"Clean IP selection error: {exc}")
            if ordered:
                return ordered[0].url

        return None

    def get_clean_record_sync(self) -> CleanIPRecord | None:
        """Synchronous round-robin selection returning the FULL record so
        callers (e.g. ProxyRotator) can use measured metadata — never assume
        country="IR" from a bare URL."""
        url = self.get_clean_ip_sync()
        if url is None:
            return None
        for p in self._local_cache:
            if p.url == url:
                return p
        return CleanIPRecord(url=url)

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

    def _pool_is_stale(self) -> bool:
        """True when the persisted pool is older than the configured max age."""
        max_age = getattr(utcms_config, "CLEAN_IP_POOL_MAX_AGE_SECONDS", 1800)
        try:
            if os.path.exists(FILE_WORKING_JSON):
                return (time.time() - os.path.getmtime(FILE_WORKING_JSON)) > max_age
        except OSError:
            pass
        return True

    def _kick_background_refresh(self) -> None:
        """Best-effort non-blocking refresh trigger for SYNC callers.

        The sync path (Celery worker hot loop) historically only consumed
        cache/file state and NEVER triggered screening, so a dead best_iran_proxy.txt
        could be served forever. Beat's barpro.clean_ip.probe remains the primary
        refresher; this is the safety net when it has not run in time.
        """
        now = time.time()
        if now - self._bg_refresh_last_kick < 300:  # at most one kick per 5 min
            return
        if self._bg_refresh_thread is not None and self._bg_refresh_thread.is_alive():
            return

        def _run() -> None:
            try:
                asyncio.run(clean_ip_pool.refresh_pool(force=False))
            except Exception as exc:
                logger.debug(f"CleanIPPool: background refresh failed: {exc}")

        self._bg_refresh_last_kick = now
        self._bg_refresh_thread = threading.Thread(target=_run, name="clean-ip-pool-refresh", daemon=True)
        self._bg_refresh_thread.start()
        logger.info("CleanIPPool: pool stale — background screening kicked from sync path.")

    def get_clean_ip_sync(self) -> str | None:
        """Synchronous round-robin selection over the usable pool.

        Precedence: validated in-memory cache → best-file → full working list.
        Redis blocked entries are skipped; when the persisted pool is older
        than CLEAN_IP_POOL_MAX_AGE_SECONDS a background screening cycle is
        kicked (non-blocking) so the sync path can never serve the same dead
        file forever.
        """
        candidates: list[str] = []
        if self._local_cache:
            candidates = [p.url for p in self._local_cache if p.is_usable]

        if not candidates and os.path.exists(FILE_BEST_TXT):
            try:
                with open(FILE_BEST_TXT, encoding="utf-8") as f:
                    content = f.read().strip()
                    if content:
                        candidates = [content]
            except OSError as exc:
                logger.debug(f"Could not read {FILE_BEST_TXT}: {exc}")

        if not candidates and os.path.exists(FILE_WORKING_TXT):
            try:
                with open(FILE_WORKING_TXT, encoding="utf-8") as f:
                    candidates = [line.strip() for line in f if line.strip()]
            except OSError as exc:
                logger.debug(f"Could not read {FILE_WORKING_TXT}: {exc}")

        if not candidates:
            if self._pool_is_stale():
                self._kick_background_refresh()
            return None

        n = len(candidates)
        start = self._rr_sync % n
        self._rr_sync = (self._rr_sync + 1) % n
        for i in range(n):
            url = candidates[(start + i) % n]
            if not self._is_blocked_sync(url):
                return url

        # Everything we know about is currently blocked — refresh instead of
        # silently re-serving a blocked address on the next call.
        if self._pool_is_stale():
            self._kick_background_refresh()
        return None

    async def mark_blocked(self, proxy_url: str, duration_seconds: int = 1800) -> None:
        """
        Mark a specific third-party clean proxy as blocked in Redis without
        affecting the worker's own IP or circuit breaker.
        """
        if not proxy_url:
            return
        logger.warning(
            "CleanIPPool: marking proxy %s as blocked for %ss",
            CleanIPRecord(url=proxy_url).safe_url,
            duration_seconds,
        )
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

        # Invalidate the per-worker proxy cache IMMEDIATELY. Without this, the
        # 60s worker-side cache keeps serving the just-blocked address and the
        # worker keeps failing against a WAF-blocked IP it already knows about.
        try:
            from app.automation.worker_proxy import invalidate_worker_proxy_cache

            invalidate_worker_proxy_cache()
        except Exception as exc:
            logger.debug(f"Worker proxy cache invalidation failed: {exc}")

    async def refresh_pool(self, force: bool = False) -> list[CleanIPRecord]:
        """
        Execute a full screening cycle under distributed Redis lock
        and update Redis cache.
        """
        if not self._refresh_lock.acquire(blocking=False):
            logger.info("CleanIPPool: refresh already in progress in this process.")
            return [record for record in await self.get_all_clean_ips() if record.is_usable]

        r = None
        lock_token = uuid.uuid4().hex
        owns_redis_lock = False
        try:
            try:
                r = await redis_manager.get()
            except Exception as exc:
                logger.warning("CleanIPPool: Redis unavailable for refresh lock: %s", exc)

            if r is not None:
                lock_ttl = max(60, utcms_config.CLEAN_IP_REFRESH_LOCK_TTL_SECONDS)
                lock_acquired = await r.set(self.REDIS_LOCK_REFRESH, lock_token, ex=lock_ttl, nx=True)
                if not lock_acquired:
                    logger.info("CleanIPPool: Refresh already in progress by another worker.")
                    return [record for record in await self.get_all_clean_ips() if record.is_usable]
                owns_redis_lock = True

            if force:
                logger.info("CleanIPPool: forced refresh requested; concurrency lock remains enforced.")

            # Run screening in background thread pool to avoid blocking async loop
            loop = asyncio.get_running_loop()
            verified = await loop.run_in_executor(
                None,
                run_screening_cycle,
                getattr(utcms_config, "IRAN_PROXY_TIMEOUT_SECONDS", DEFAULT_TIMEOUT_SECONDS),
                getattr(utcms_config, "CLEAN_IP_MAX_PROBE_WORKERS", MAX_PROBE_WORKERS),
                getattr(utcms_config, "CLEAN_IP_MAX_POOL", 50),
                getattr(utcms_config, "CLEAN_IP_MAX_CANDIDATES", 1000),
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
            return [record for record in await self.get_all_clean_ips() if record.is_usable]
        finally:
            try:
                if r is not None and owns_redis_lock:
                    await r.eval(
                        "if redis.call('get', KEYS[1]) == ARGV[1] then "
                        "return redis.call('del', KEYS[1]) else return 0 end",
                        1,
                        self.REDIS_LOCK_REFRESH,
                        lock_token,
                    )
            except Exception:
                pass
            self._refresh_lock.release()


# Global singleton instance
clean_ip_pool = CleanIPPoolManager()


def get_clean_ip_pool() -> CleanIPPoolManager:
    """Return singleton CleanIPPoolManager."""
    return clean_ip_pool


async def get_best_clean_iran_proxy() -> str | None:
    """Convenience async accessor for the fastest active clean Iranian proxy."""
    return await clean_ip_pool.get_clean_ip()

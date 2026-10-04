#!/usr/bin/env python3
"""
BarPro - Domestic Network & Proxy Testing Suite (For when VPN is OFF)
====================================================================
Tests direct UTCMS portal connectivity and audits the Clean IP Pool
from an Iranian IP environment (domestic routing / National Information Network).

READ-ONLY with respect to pool state by default: findings go to a sidecar
report (runtime/proxies/vpn_off_audit_report.json). Pass --write-pool only if
you deliberately want this run's probe-only (NOT egress-verified) results to
replace the live pool files.

Usage:
  .venv/bin/python scripts/test_when_vpn_off.py
  .venv/bin/python scripts/test_when_vpn_off.py --candidates 50 --timeout 4.0
  .venv/bin/python scripts/test_when_vpn_off.py --skip-proxy-scan  # only test direct portal access
  .venv/bin/python scripts/test_when_vpn_off.py --write-pool       # DESTRUCTIVE: overwrite pool files
"""

import argparse
import concurrent.futures
import json
import os
import socket
import sys
import time
import urllib.request
from typing import Any

# Ensure project root is in sys.path
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from app.automation import clean_ip_pool as cip  # noqa: E402

# Colors for terminal output
GREEN = "\033[92m"
YELLOW = "\033[93m"
RED = "\033[91m"
CYAN = "\033[96m"
BOLD = "\033[1m"
RESET = "\033[0m"


def print_banner():
    print(f"\n{BOLD}{CYAN}========================================================================{RESET}")
    print(f"{BOLD}{CYAN}       🇮🇷  BarPro - Domestic Network & Proxy Audit (VPN OFF Mode)       {RESET}")
    print(f"{BOLD}{CYAN}========================================================================{RESET}\n")


def detect_public_ip() -> dict[str, Any]:
    """Detect current public egress IP and geographic country."""
    endpoints = [
        ("ipwho.is", "https://ipwho.is/"),
        ("country.is", "https://api.country.is/"),
        ("ip-api.com", "http://ip-api.com/json/"),
    ]
    for name, url in endpoints:
        try:
            req = urllib.request.Request(
                url,
                headers={"User-Agent": "BarPro-VpnTest/1.0", "Accept": "application/json"},
            )
            with urllib.request.urlopen(req, timeout=4.0) as resp:
                data = json.loads(resp.read().decode("utf-8", errors="ignore"))
                ip = data.get("ip") or data.get("query")
                country = data.get("country_code") or data.get("country")
                isp = data.get("isp") or (data.get("connection") or {}).get("isp") or data.get("org") or "Unknown ISP"
                city = data.get("city") or "Unknown City"
                if ip and country:
                    return {
                        "ip": ip,
                        "country": str(country).upper().strip(),
                        "isp": isp,
                        "city": city,
                        "source": name,
                    }
        except Exception:
            continue
    return {"ip": "Unknown", "country": "UNKNOWN", "isp": "Unknown", "city": "Unknown", "source": "None"}


def test_direct_utcms_access() -> dict[str, Any]:
    """Test direct connection to barname.utcms.ir with chrome120 fingerprint."""
    host = "barname.utcms.ir"
    target_url = cip.LOGIN_PROBE_URL

    # Step A: DNS Resolution Check
    dns_ip = None
    dns_err = None
    try:
        dns_ip = socket.gethostbyname(host)
    except Exception as exc:
        dns_err = str(exc)

    if not dns_ip:
        return {
            "success": False,
            "stage": "DNS_RESOLUTION",
            "error": f"Could not resolve {host}: {dns_err}",
            "dns_ip": None,
            "status_code": None,
            "latency_ms": None,
        }

    # Step B: HTTPS Handshake & Login Page Check
    try:
        from curl_cffi import requests as cc_requests

        t0 = time.perf_counter()
        session = cc_requests.Session(
            impersonate="chrome120",
            timeout=8.0,
            verify=True,
        )
        session.headers.update(cip.PROBE_HEADERS)
        try:
            resp = session.get(target_url)
            elapsed_ms = (time.perf_counter() - t0) * 1000
            status = resp.status_code
            text = resp.text or ""
            verdict = cip.classify_probe_response(status, text)
            return {
                "success": verdict == "healthy",
                "stage": "HTTPS_GET",
                "dns_ip": dns_ip,
                "status_code": status,
                "latency_ms": elapsed_ms,
                "verdict": verdict,
                "title": "ورود به سامانه" if "ورود" in text else "Unknown",
                "error": None if verdict == "healthy" else f"Verdict: {verdict}",
            }
        finally:
            session.close()
    except Exception as exc:
        return {
            "success": False,
            "stage": "HTTPS_CONNECT",
            "dns_ip": dns_ip,
            "status_code": None,
            "latency_ms": None,
            "error": str(exc),
        }


def _probe_with_reason(
    candidate: cip.CleanIPRecord,
    timeout: float,
) -> tuple[cip.CleanIPRecord, str, cip.CleanIPRecord | None]:
    """Probe one candidate and report WHY it failed.

    ``probe_single_proxy`` swallows every transport exception and returns None,
    so wrapping it in try/except produced buckets that could never fire: every
    candidate landed in SUCCESS or REJECTED, and an operator running this tool
    to tell "DNS/TLS interception" apart from "UTCMS rejected the IP" always saw
    zeros for exactly the failure modes the tool exists to diagnose. We therefore
    call the lower-level transport directly and classify its real exception.
    """
    if cip._CURL_CFFI_IMPORT_ERROR is not None:
        return (candidate, "OTHER", None)

    last_exc: Exception | None = None
    for attempt in range(1, cip.PROBE_TRANSPORT_ATTEMPTS + 1):
        try:
            status_code, elapsed_ms, snippet = cip._probe_via_curl_cffi(candidate, cip.LOGIN_PROBE_URL, timeout)
        except Exception as exc:  # transport-level: dead proxy, reset, timeout, TLS
            last_exc = exc
            continue

        verdict = cip.classify_probe_response(status_code, snippet)
        if verdict == "healthy":
            return (candidate, "SUCCESS", cip._mark_probe_healthy(candidate, elapsed_ms))
        if verdict == "target_unavailable" and attempt < cip.PROBE_TRANSPORT_ATTEMPTS:
            continue
        return (candidate, "REJECTED", None)

    msg = str(last_exc or "").lower()
    if "timed out" in msg or "timeout" in msg:
        return (candidate, "TIMEOUT", None)
    if "certificate" in msg or "ssl" in msg:
        return (candidate, "SSL_ERROR", None)
    if "connect" in msg or "refused" in msg or "reset" in msg or "proxy" in msg:
        return (candidate, "CONN_ERROR", None)
    return (candidate, "OTHER", None)


def _write_sidecar_report(verified: list[cip.CleanIPRecord], stats: dict[str, int]) -> str:
    """Write findings to a clearly-named diagnostic file, NEVER the runtime pool."""
    report_path = os.path.join(cip.PROXIES_RUNTIME_DIR, "vpn_off_audit_report.json")
    payload = {
        "generated_at_epoch": time.time(),
        "tool": "scripts/test_when_vpn_off.py",
        "note": (
            "DIAGNOSTIC OUTPUT ONLY. These records were certified by the login probe but "
            "NOT egress-verified, so they do not satisfy is_operational_iranian_egress and "
            "must not be loaded as pool state. Run with --write-pool to overwrite the live pool."
        ),
        "stats": stats,
        "verified": [p.to_dict() for p in verified],
    }
    os.makedirs(cip.PROXIES_RUNTIME_DIR, exist_ok=True)
    cip.atomic_write(report_path, json.dumps(payload, indent=2, ensure_ascii=False) + "\n")
    return report_path


def run_domestic_proxy_audit(
    max_candidates: int = 50,
    timeout: float = 4.0,
    concurrency: int = 25,
    write_pool: bool = False,
) -> list[cip.CleanIPRecord]:
    """Harvest candidates and test them using domestic routing."""
    print(f"{BOLD}[3/4] Harvesting candidates across all sources...{RESET}")
    candidates = cip.aggregate_all_candidates(force_refresh_all=False)
    print(f"      Gathered {BOLD}{len(candidates)}{RESET} deduplicated candidate proxies.")

    # Sort & prioritize Iranian candidates
    def _rank(c: cip.CleanIPRecord) -> tuple[int, float]:
        is_ir = (c.country == "IR") or (bool(c.city and "iran" in c.city.lower()))
        is_file_source = c.source in ("file_source", "custom_url")
        is_ir_source = c.source in (
            "freeproxy_world",
            "geonode",
            "spys",
            "proxyscrape_v4",
            "proxyscrape_v2",
            "vakhov",
            "monosans",
        )
        if is_file_source:
            tier = 0
        elif is_ir and is_ir_source:
            tier = 1
        elif is_ir:
            tier = 2
        else:
            tier = 3
        return (tier, -c.score)

    candidates.sort(key=_rank)
    selected = candidates[: max(1, min(max_candidates, len(candidates)))]
    ir_count = sum(1 for c in selected if c.country == "IR" or (c.city and "iran" in c.city.lower()))

    print(f"      Selected top {BOLD}{len(selected)}{RESET} candidates for screening ({ir_count} marked IR).")
    print(f"\n{BOLD}[4/4] Probing proxies against UTCMS login page...{RESET}")
    print(f"      Concurrency: {concurrency} threads | Timeout: {timeout}s | Impersonate: chrome120\n")

    verified: list[cip.CleanIPRecord] = []
    stats = {"SUCCESS": 0, "TIMEOUT": 0, "CONN_ERROR": 0, "SSL_ERROR": 0, "REJECTED": 0, "OTHER": 0}

    t0 = time.time()
    with concurrent.futures.ThreadPoolExecutor(max_workers=concurrency) as executor:
        futures = {executor.submit(_probe_with_reason, c, timeout): c for c in selected}
        for _idx, fut in enumerate(concurrent.futures.as_completed(futures), 1):
            c, status, res = fut.result()
            stats[status] = stats.get(status, 0) + 1
            if status == "SUCCESS" and res:
                verified.append(res)
                print(
                    f"  {GREEN}✓ [PASS]{RESET} {c.url:<28} | {res.latency_ms:>6.1f}ms | {c.isp or 'Iran ISP'} ({c.city})"
                )

    elapsed = time.time() - t0
    print(f"\n{BOLD}Audit completed in {elapsed:.1f}s:{RESET}")
    print(f"  {GREEN}● Working / Accepted: {len(verified)}{RESET}")
    print(f"  {RED}● Timed out:          {stats.get('TIMEOUT', 0)}{RESET}")
    print(f"  {RED}● Connection error:   {stats.get('CONN_ERROR', 0)}{RESET}")
    print(f"  {RED}● SSL / MITM blocked: {stats.get('SSL_ERROR', 0)}{RESET}")
    print(f"  {RED}● Other / Rejected:   {stats.get('REJECTED', 0) + stats.get('OTHER', 0)}{RESET}")

    if verified:
        verified.sort(key=lambda x: x.latency_ms)

    # The live runtime pool is NEVER touched by default.
    #
    # These records come from probe_single_proxy only, so egress_verified=False
    # and observed_country=None — every one of them FAILS
    # is_operational_iranian_egress. Writing them over FILE_BEST_TXT /
    # FILE_WORKING_TXT / FILE_WORKING_JSON on a worker host destroyed the real
    # verified proxies, supplied zero usable replacements, AND disabled the
    # self-healing: refreshing the file mtime makes _pool_is_stale() return
    # False, so _kick_background_refresh() is never called for
    # CLEAN_IP_POOL_MAX_AGE_SECONDS. atomic_write also chmods 0o600, so a root
    # run leaves files the uid-10001 container cannot read.
    if not write_pool:
        report_path = _write_sidecar_report(verified, stats)
        print(f"\n{CYAN}Diagnostic report written (runtime pool untouched):{RESET}")
        print(f"  - {report_path}")
        print(f"{CYAN}Pass --write-pool to overwrite the live pool files instead.{RESET}")
        return verified

    if verified:
        os.makedirs(cip.PROXIES_RUNTIME_DIR, exist_ok=True)
        cip.atomic_write(cip.FILE_BEST_TXT, f"{verified[0].url}\n")
        cip.atomic_write(cip.FILE_WORKING_TXT, "\n".join(p.url for p in verified) + "\n")
        cip.atomic_write(
            cip.FILE_WORKING_JSON,
            json.dumps([p.to_dict() for p in verified], indent=2, ensure_ascii=False) + "\n",
        )
        print(f"\n{YELLOW}--write-pool: overwrote runtime pool with {len(verified)} probe-only records.{RESET}")
        print(f"{YELLOW}These are NOT egress-verified; run a real screening cycle before relying on them.{RESET}")
        print(f"  - {cip.FILE_WORKING_TXT}")
        print(f"  - {cip.FILE_BEST_TXT}")
    else:
        print(f"\n{YELLOW}--write-pool requested but nothing passed; runtime pool left untouched.{RESET}")

    return verified


def main():
    parser = argparse.ArgumentParser(description="BarPro Domestic Network & Proxy Testing Tool (VPN OFF Mode)")
    parser.add_argument(
        "--candidates",
        type=int,
        default=50,
        help="Number of proxy candidates to screen (default: 50)",
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=4.0,
        help="Max HTTPS handshake timeout in seconds (default: 4.0)",
    )
    parser.add_argument(
        "--workers",
        type=int,
        default=25,
        help="Number of concurrent probe threads (default: 25)",
    )
    parser.add_argument(
        "--skip-proxy-scan",
        action="store_true",
        help="Only check direct UTCMS portal connectivity without scanning proxies",
    )
    parser.add_argument(
        "--write-pool",
        action="store_true",
        help=(
            "DESTRUCTIVE: overwrite the live runtime pool files with this run's probe-only "
            "results. Off by default — these records are NOT egress-verified and will fail "
            "is_operational_iranian_egress. Without this flag a sidecar report is written instead."
        ),
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Continue even if non-Iranian IP (VPN) is detected without prompting",
    )

    args = parser.parse_args()
    print_banner()

    # Step 1: Detect Egress IP and VPN Status
    print(f"{BOLD}[1/4] Checking Network & VPN Status...{RESET}")
    net = detect_public_ip()
    ip = net["ip"]
    country = net["country"]
    isp = net["isp"]
    city = net["city"]

    print(f"      Detected Public IP: {BOLD}{ip}{RESET}")
    print(f"      Detected Country:   {BOLD}{country}{RESET}")
    print(f"      ISP / Provider:     {BOLD}{isp}{RESET} ({city})")

    is_iranian = country == "IR"
    if not is_iranian:
        print(f"\n{YELLOW}{BOLD}⚠️  هشدار: آی‌پی فعلی شما مربوط به کشور ایران نیست ({country}).{RESET}")
        print(f"{YELLOW}به نظر می‌رسد فیلترشکن (VPN) شما هنوز روشن است!{RESET}")
        print(
            f"{YELLOW}برای تست در شبکه ملی و اینترنت داخلی، لطفاً فیلترشکن را خاموش کرده و مجدداً اسکریپت را اجرا کنید.{RESET}"
        )
        if not args.force:
            # A non-interactive run (cron, CI, `< /dev/null`) has no stdin to
            # answer with: treat that as an implicit refusal instead of raising
            # EOFError out of input() with a traceback.
            if not sys.stdin.isatty():
                print(f"\n{RED}تست متوقف شد (ورودی تعاملی موجود نیست). برای ادامه از --force استفاده کنید.{RESET}\n")
                sys.exit(0)
            try:
                answer = input("\nآیا می‌خواهید با همین آی‌پی ادامه دهید؟ [y/N]: ").strip().lower()
                if answer not in ("y", "yes"):
                    print(f"\n{RED}تست متوقف شد. پس از خاموش کردن VPN دوباره امتحان کنید.{RESET}\n")
                    sys.exit(0)
            except (KeyboardInterrupt, EOFError):
                print("\n")
                sys.exit(0)
    else:
        print(f"      {GREEN}✓ VPN خاموش است! اتصال مستقیم از شبکه ایران تایید شد.{RESET}")

    # Step 2: Direct UTCMS Connectivity Test
    print(f"\n{BOLD}[2/4] Testing Direct Access to UTCMS (barname.utcms.ir)...{RESET}")
    direct = test_direct_utcms_access()
    if direct["success"]:
        print(f"      {GREEN}✓ اتصال مستقیم به سامانه بارنامه برقرار است!{RESET}")
        print(f"      DNS Resolved IP: {direct['dns_ip']}")
        print(f"      HTTP Status:     {GREEN}{direct['status_code']} OK{RESET}")
        print(f"      Latency:         {BOLD}{direct['latency_ms']:.1f} ms{RESET}")
    else:
        print(f"      {RED}✗ خطا در اتصال مستقیم به سامانه بارنامه:{RESET}")
        print(f"      مرحله خطا:       {direct['stage']}")
        print(f"      پیام خطا:        {direct['error']}")
        if not is_iranian:
            print(
                f"      {YELLOW}دلیل احتمالی: به دلیل روشن بودن VPN، سرورهای DNS خارجی قادر به ترجمه barname.utcms.ir نیستند.{RESET}"
            )

    # Step 3: Run proxy screening if requested
    if args.skip_proxy_scan:
        print(f"\n{CYAN}غربالگری پروکسی‌ها رد شد (--skip-proxy-scan). تست پایان یافت.{RESET}\n")
        return

    verified = run_domestic_proxy_audit(
        max_candidates=args.candidates,
        timeout=args.timeout,
        concurrency=args.workers,
        write_pool=args.write_pool,
    )

    print(f"\n{BOLD}{CYAN}========================================================================{RESET}")
    if verified:
        print(f"{GREEN}{BOLD}🎉 نتیجه: تعداد {len(verified)} پروکسی فعال و سالم در شبکه داخلی شناسایی شد!{RESET}")
        print(f"بهترین پروکسی: {verified[0].url} (تاخیر: {verified[0].latency_ms:.1f}ms)")
    else:
        print(f"{YELLOW}{BOLD}نتیجه: هیچ پروکسی عمومی رایگانی نتوانست هندشیک لاگین را با موفقیت پاس کند.{RESET}")
        print("توضیح: این امر نشان‌دهنده نیاز قطعی سیستم به سرورهای اختصاصی Model B است.")
    print(f"{BOLD}{CYAN}========================================================================{RESET}\n")


if __name__ == "__main__":
    main()

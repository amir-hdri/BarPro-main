"""Measure UTCMS login latency using the curl_cffi HTTP-only path.

This script is a diagnostic tool. It bypasses Playwright entirely and
goes straight to ``UtcmsHttpLogin.authenticate()`` to answer one
question: *with the current worker IP and the bundled local CNN/CRNN
captcha solver, can we log in over HTTPS in under N seconds?*

Usage (from a worker container, where curl_cffi is installed):

    python -m scripts.measure_curl_cffi_login                # single attempt
    python -m scripts.measure_curl_cffi_login --attempts 5   # repeated
    python -m scripts.measure_curl_cffi_login --impersonate chrome120
    python -m scripts.measure_curl_cffi_login --no-proxy     # direct (no Squid)
    python -m scripts.measure_curl_cffi_login --user 1234567890 --pw secret

Environment variables (alternative to CLI flags):
    UTCMS_USERNAME, UTCMS_PASSWORD  — credentials
    LOGIN_URL                        — override login URL
    RPA_PROXIES / WORKER_N_PROXY     — proxy URL
    CAPTCHA_PROVIDER                 — cnn / pytorch_fuel / auto / off

The script writes a JSON report to logs/curl_cffi_login_<ts>.json.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app.automation.utcms_http_login import HttpLoginResult, UtcmsHttpLogin  # noqa: E402
from app.core.config import utcms_config  # noqa: E402


def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="Diagnostic: UTCMS login via curl_cffi (bypass WAF TLS fingerprint)."
    )
    p.add_argument("--user", default=os.getenv("UTCMS_USERNAME", utcms_config.UTCMS_USERNAME))
    p.add_argument("--pw", default=os.getenv("UTCMS_PASSWORD", utcms_config.UTCMS_PASSWORD))
    p.add_argument("--login-url", default=os.getenv("LOGIN_URL", utcms_config.LOGIN_URL))
    p.add_argument("--proxy", default=os.getenv("MEASURE_PROXY", ""))
    p.add_argument(
        "--impersonate",
        default=os.getenv("MEASURE_IMPERSONATE", UtcmsHttpLogin.DEFAULT_IMPERSONATE),
        help="curl_cffi impersonate profile (chrome120, chrome119, edge99, ...).",
    )
    p.add_argument("--attempts", type=int, default=int(os.getenv("MEASURE_ATTEMPTS", "1")))
    p.add_argument(
        "--no-proxy",
        action="store_true",
        help="Force direct connection (no proxy), regardless of RPA_PROXIES.",
    )
    p.add_argument(
        "--timeout",
        type=float,
        default=float(os.getenv("MEASURE_TIMEOUT", "30")),
        help="Per-request timeout in seconds.",
    )
    return p.parse_args()


async def _run(args: argparse.Namespace) -> dict:
    if not args.user or not args.pw:
        print("ERROR: --user and --pw (or UTCMS_USERNAME / UTCMS_PASSWORD) are required.")
        sys.exit(2)

    proxy_url = None
    if not args.no_proxy:
        if args.proxy:
            proxy_url = args.proxy
        else:
            try:
                from app.automation.worker_proxy import get_worker_proxy_url

                proxy_url = get_worker_proxy_url()
            except Exception as exc:
                print(f"WARNING: could not read worker proxy: {exc}")

    print("=" * 80)
    print("🔬 Measure UTCMS login (curl_cffi)")
    print("=" * 80)
    print(f"  login_url    : {args.login_url}")
    print(f"  proxy        : {proxy_url or '(direct)'}")
    print(f"  impersonate  : {args.impersonate}")
    print(f"  timeout      : {args.timeout}s")
    print(f"  attempts     : {args.attempts}")
    print(f"  user (masked): {args.user[:3]}***{args.user[-3:] if len(args.user) > 6 else '***'}")
    print()

    attempts: list[dict] = []
    overall_start = time.monotonic()
    for i in range(1, args.attempts + 1):
        print(f"--- attempt {i}/{args.attempts} ---")
        login = UtcmsHttpLogin(
            login_url=args.login_url,
            proxy_url=proxy_url,
            impersonate=args.impersonate,
            timeout=args.timeout,
        )
        start = time.monotonic()
        result: HttpLoginResult = await login.authenticate(args.user, args.pw)
        elapsed = time.monotonic() - start
        attempt = {
            "index": i,
            "elapsed_seconds": round(elapsed, 3),
            "success": result.success,
            "status_code": result.status_code,
            "final_url": result.final_url,
            "error": result.error,
            "cookies": [c.get("name") for c in result.cookies],
            "cookie_count": len(result.cookies),
        }
        attempts.append(attempt)
        tag = "✅" if result.success else "❌"
        print(
            f"  {tag} {elapsed:6.2f}s  status={result.status_code}  "
            f"url={result.final_url}  cookies={attempt['cookies']}"
        )
        if not result.success:
            print(f"     error: {result.error}")
        if i < args.attempts:
            await asyncio.sleep(1.0)
    total_elapsed = time.monotonic() - overall_start

    success_count = sum(1 for a in attempts if a["success"])
    summary = {
        "login_url": args.login_url,
        "proxy": proxy_url,
        "impersonate": args.impersonate,
        "timeout": args.timeout,
        "attempts": args.attempts,
        "success_count": success_count,
        "success_rate": round(success_count / max(1, args.attempts), 3),
        "total_elapsed_seconds": round(total_elapsed, 3),
        "avg_elapsed_seconds": round(
            sum(a["elapsed_seconds"] for a in attempts) / max(1, len(attempts)), 3
        ),
        "results": attempts,
    }
    print()
    print("=" * 80)
    print("📊 Summary")
    print("=" * 80)
    print(f"  success rate : {summary['success_rate'] * 100:.0f}%  ({success_count}/{args.attempts})")
    print(f"  total time   : {summary['total_elapsed_seconds']:.2f}s")
    print(f"  avg/attempt  : {summary['avg_elapsed_seconds']:.2f}s")

    log_dir = ROOT / "logs"
    log_dir.mkdir(exist_ok=True)
    log_path = log_dir / f"curl_cffi_login_{time.strftime('%Y%m%d_%H%M%S')}.json"
    log_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2))
    print(f"  report       : {log_path}")
    return summary


def main() -> int:
    args = _parse_args()
    try:
        asyncio.run(_run(args))
    except KeyboardInterrupt:
        print("\ninterrupted")
        return 130
    return 0


if __name__ == "__main__":
    sys.exit(main())

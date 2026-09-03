#!/usr/bin/env python3
"""
BarPro Clean Iranian Proxy Fleet Refresh & Benchmarking Tool
============================================================
Fetches candidate proxies from 11+ online sources, validates connectivity
and TLS handshake against https://utcms.ir, and updates the shared pool.

Usage:
  python3 scripts/refresh_iran_proxies.py --once
  python3 scripts/refresh_iran_proxies.py --interval 3 --timeout 7.5
"""

import argparse
import os
import sys
import time

# Ensure project root is in sys.path
BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

from app.automation.clean_ip_pool import run_screening_cycle, clean_ip_pool, FILE_BEST_TXT, FILE_WORKING_TXT, FILE_WORKING_JSON


def main():
    parser = argparse.ArgumentParser(
        description="BarPro Clean Iranian Proxy Pool Refresh & Benchmarking Tool"
    )
    parser.add_argument(
        "--once",
        action="store_true",
        help="Run a single screening and benchmark cycle, then exit",
    )
    parser.add_argument(
        "--interval",
        type=int,
        default=3,
        help="Refresh interval in minutes for continuous background mode (default: 3)",
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=7.5,
        help="Maximum HTTPS connect timeout per proxy in seconds (default: 7.5)",
    )
    parser.add_argument(
        "--max-pool",
        type=int,
        default=50,
        help="Maximum number of verified proxies to retain in the pool (default: 50)",
    )

    args = parser.parse_args()

    print("=" * 80)
    print("🚀 BarPro - Clean Iranian Proxy Pool Benchmarking Engine")
    print(f"Target: https://utcms.ir | Timeout: {args.timeout}s | Max Pool: {args.max_pool}")
    print("=" * 80)

    if args.once or args.interval <= 0:
        verified = run_screening_cycle(timeout=args.timeout, max_pool_size=args.max_pool)
        print("\n" + "=" * 80)
        print(f"📊 Summary: {len(verified)} verified healthy Iranian proxies found.")
        if verified:
            print(f"🏆 Best Egress Proxy: {verified[0].url} (Latency: {verified[0].latency_ms} ms, ISP: {verified[0].isp})")
            print("\nTop 5 Verified Proxies:")
            for idx, p in enumerate(verified[:5], 1):
                print(f"  {idx}. {p.url:<28} | {p.latency_ms:>6.1f} ms | {p.isp} ({p.city})")
            print(f"\nFiles updated:\n - {FILE_BEST_TXT}\n - {FILE_WORKING_TXT}\n - {FILE_WORKING_JSON}")
        print("=" * 80)
    else:
        print(f"Continuous monitoring started (refreshing every {args.interval} minutes)...")
        while True:
            try:
                verified = run_screening_cycle(timeout=args.timeout, max_pool_size=args.max_pool)
                print(f"[{time.strftime('%H:%M:%S')}] Verified {len(verified)} proxies. Best: {verified[0].url if verified else 'None'}")
                print(f"Waiting {args.interval} minutes for next cycle...")
                time.sleep(args.interval * 60)
            except KeyboardInterrupt:
                print("\nStopped.")
                break


if __name__ == "__main__":
    main()

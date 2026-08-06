"""Fetch first active driver UTCMS creds from DB and run the curl_cffi measure.

Designed to run inside the worker container:
    python scripts/measure_curl_cffi_with_db_creds.py [--attempts N]

It reads the driver's UTCMS username + decrypted password from the database,
then runs ``UtcmsHttpLogin.authenticate()`` against the real login URL and
prints a human-readable result.
"""

from __future__ import annotations

import argparse
import asyncio
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from sqlmodel import select  # noqa: E402

from app.automation.utcms_http_login import UtcmsHttpLogin  # noqa: E402
from app.automation.worker_proxy import get_worker_proxy_url  # noqa: E402
from app.core.config import utcms_config  # noqa: E402
from app.models_multitenant import Driver  # noqa: E402


async def _fetch_driver_creds_async() -> tuple[str, str]:
    from app.core.database import async_session_factory
    from app.auth_multitenant import decrypt_driver_password

    async with async_session_factory() as s:
        rs = (await s.exec(select(Driver))).all()
        for d in rs:
            if d.status != "active" or not d.utcms_username or not d.utcms_password_encrypted:
                continue
            try:
                pw = decrypt_driver_password(d.utcms_password_encrypted)
            except Exception as exc:
                print(f"  [warn] decrypt failed for {d.utcms_username}: {exc}")
                continue
            return d.utcms_username, pw
    raise SystemExit("No active driver with decrypted UTCMS creds found in DB.")


async def main() -> int:
    p = argparse.ArgumentParser(description="Measure curl_cffi UTCMS login with DB creds.")
    p.add_argument("--attempts", type=int, default=1)
    p.add_argument("--proxy", default=None, help='override proxy; use "" for direct')
    args = p.parse_args()

    user, pw = await _fetch_driver_creds_async()
    print(f"Credential loaded: user={user[:4]}***  pw_len={len(pw)}")

    proxy = args.proxy if args.proxy is not None else (get_worker_proxy_url() or "")
    print(f"Proxy: {proxy or '(direct)'}")

    result = None
    login = UtcmsHttpLogin(proxy_url=proxy)
    started = time.monotonic()
    try:
        result = await login.authenticate(user, pw)
    except Exception as exc:
        print(f"  ❌ authenticate() raised: {exc}")
        return 1
    elapsed = time.monotonic() - started

    tag = "✅ SUCCESS" if result.success else "❌ FAILED"
    print(f"  {tag}  elapsed={elapsed:.2f}s  status={result.status_code}  url={result.final_url}")
    print(f"  error : {result.error}")
    print(f"  cookies:{[c.get('name') for c in result.cookies]}")
    print(f"  cookie_count: {len(result.cookies)}")
    return 0 if result.success else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
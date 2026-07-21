#!/usr/bin/env python3
"""
Re-encrypt all driver passwords from an old DRIVER_ENCRYPTION_KEY to the current one.

Usage:
    docker exec barpro-backend python /app/scripts/reencrypt_drivers.py --old-key "OLD_KEY_HERE"

Or with env variable:
    docker exec -e OLD_DRIVER_KEY="OLD_KEY_HERE" barpro-backend python /app/scripts/reencrypt_drivers.py

This script MUST be run whenever the DRIVER_ENCRYPTION_KEY is changed.
It safely re-encrypts all passwords without ever logging the plaintext values.
"""

import argparse
import asyncio
import logging
import os
import sys

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)


def _build_fernet(raw_key: str):
    from base64 import urlsafe_b64decode, urlsafe_b64encode

    from cryptography.fernet import Fernet
    from cryptography.hazmat.primitives import hashes
    from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC

    key_bytes = raw_key.encode("utf-8")
    try:
        decoded = urlsafe_b64decode(key_bytes)
        if len(decoded) == 32:
            return Fernet(raw_key)
    except Exception:
        pass
    kdf = PBKDF2HMAC(
        algorithm=hashes.SHA256(),
        length=32,
        salt=b"barpro-fernet-kdf",
        iterations=600_000,
    )
    derived = urlsafe_b64encode(kdf.derive(key_bytes))
    return Fernet(derived.decode())


async def reencrypt_all(old_key: str) -> None:
    from cryptography.fernet import InvalidToken
    from sqlalchemy import text

    from app.core.database import async_engine
    from app.core.config import utcms_config

    old_fernet = _build_fernet(old_key)
    new_fernet = _build_fernet(utcms_config.DRIVER_ENCRYPTION_KEY)

    if old_key.strip() == utcms_config.DRIVER_ENCRYPTION_KEY.strip():
        logger.warning("Old key and new key are the same — nothing to do.")
        return

    async with async_engine.begin() as conn:
        rows = await conn.execute(text("SELECT id, utcms_username, utcms_password_encrypted FROM drivers"))
        drivers = rows.fetchall()

    success = 0
    failed = []

    async with async_engine.begin() as conn:
        for driver in drivers:
            driver_id, username, enc = driver
            try:
                plaintext = old_fernet.decrypt(enc.encode()).decode()
                new_enc = new_fernet.encrypt(plaintext.encode()).decode()
                await conn.execute(
                    text("UPDATE drivers SET utcms_password_encrypted = :enc WHERE id = :id"),
                    {"enc": new_enc, "id": driver_id},
                )
                success += 1
                logger.info("✅  Driver %d (%s) re-encrypted.", driver_id, username)
            except InvalidToken:
                failed.append((driver_id, username))
                logger.error(
                    "❌  Driver %d (%s) — cannot decrypt with old key (already on new key or different key).",
                    driver_id,
                    username,
                )

    logger.info("Done. Success: %d / %d", success, len(drivers))
    if failed:
        logger.warning(
            "Failed drivers (re-save their password via UI): %s",
            ", ".join(f"{uid}({uname})" for uid, uname in failed),
        )


def main():
    parser = argparse.ArgumentParser(description="Re-encrypt driver passwords after key rotation.")
    parser.add_argument("--old-key", default=os.environ.get("OLD_DRIVER_KEY", ""), help="Old DRIVER_ENCRYPTION_KEY")
    args = parser.parse_args()

    old_key = args.old_key.strip()
    if not old_key:
        logger.error("Provide the old key via --old-key or OLD_DRIVER_KEY env variable.")
        sys.exit(1)

    asyncio.run(reencrypt_all(old_key))


if __name__ == "__main__":
    main()

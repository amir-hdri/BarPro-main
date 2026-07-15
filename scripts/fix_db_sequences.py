#!/usr/bin/env python3
"""
Fix database sequences to prevent PK collision errors.

Run after any manual SQL inserts or data migration:
    docker exec barpro-backend python /app/scripts/fix_db_sequences.py
"""
import asyncio
import logging
from sqlalchemy import text

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

SEQUENCE_TABLES = [
    ("clients", "clients_id_seq"),
    ("drivers", "drivers_id_seq"),
    ("driver_plates", "driver_plates_id_seq"),
    ("waybill_jobs", "waybill_jobs_id_seq"),
    ("fuel_inquiries", "fuel_inquiries_id_seq"),
    ("waybill_attempts", "waybill_attempts_id_seq"),
]


async def fix_sequences():
    from app.core.database import async_engine

    async with async_engine.begin() as conn:
        for table, seq in SEQUENCE_TABLES:
            try:
                result = await conn.execute(
                    text(f"SELECT setval('{seq}', COALESCE((SELECT MAX(id) FROM {table}), 0) + 1, false)")
                )
                val = result.scalar()
                logger.info("✅ %s → next id = %d", table, val)
            except Exception as e:
                logger.warning("⚠️  Skipped %s: %s", table, e)

    logger.info("All sequences fixed.")


if __name__ == "__main__":
    asyncio.run(fix_sequences())

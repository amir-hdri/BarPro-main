#!/usr/bin/env python3
"""Check migration status."""

import os

import psycopg2


def check_status():
    """Check migration version and indexes."""
    conn = psycopg2.connect(
        host=os.getenv("POSTGRES_HOST", "127.0.0.1"),
        port=int(os.getenv("POSTGRES_PORT", 5432)),
        database=os.getenv("POSTGRES_DB", "utcms_rpa"),
        user=os.getenv("POSTGRES_USER", "postgres"),
        password=os.getenv("POSTGRES_PASSWORD", "postgres"),
    )

    try:
        cursor = conn.cursor()

        # Check version
        cursor.execute("SELECT version_num FROM alembic_version")
        version = cursor.fetchone()[0]
        print(f"📌 Current migration version: {version}")

        # Check indexes
        cursor.execute(
            """
            SELECT indexname
            FROM pg_indexes
            WHERE schemaname = 'public'
            AND indexname LIKE 'idx_%'
            ORDER BY indexname
        """
        )

        indexes = cursor.fetchall()
        print(f"\n📊 Performance indexes ({len(indexes)}):")
        for idx in indexes:
            print(f"  ✓ {idx[0]}")

    finally:
        conn.close()


if __name__ == "__main__":
    check_status()

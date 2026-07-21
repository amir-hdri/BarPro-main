#!/usr/bin/env python3
"""بررسی ساختار جدول drivers."""

import os

import psycopg2


def check_schema():
    conn = psycopg2.connect(
        host=os.getenv("POSTGRES_HOST", "127.0.0.1"),
        port=int(os.getenv("POSTGRES_PORT", 5432)),
        database=os.getenv("POSTGRES_DB", "utcms_rpa"),
        user=os.getenv("POSTGRES_USER", "postgres"),
        password=os.getenv("POSTGRES_PASSWORD", "postgres"),
    )

    cursor = conn.cursor()

    print("=" * 80)
    print("📋 ساختار جدول drivers")
    print("=" * 80)

    cursor.execute(
        """
        SELECT column_name, data_type, is_nullable, column_default
        FROM information_schema.columns
        WHERE table_name = 'drivers'
        ORDER BY ordinal_position
    """
    )

    columns = cursor.fetchall()
    print(f"\nتعداد ستون‌ها: {len(columns)}\n")

    for col_name, data_type, nullable, default in columns:
        null_str = "NULL" if nullable == "YES" else "NOT NULL"
        default_str = f" DEFAULT {default}" if default else ""
        print(f"  ✓ {col_name:30s} {data_type:20s} {null_str:10s}{default_str}")

    print("\n" + "=" * 80)
    print("📋 نمونه داده از drivers")
    print("=" * 80)

    cursor.execute("SELECT * FROM drivers LIMIT 2")
    rows = cursor.fetchall()
    col_names = [desc[0] for desc in cursor.description]

    for row in rows:
        print("\n🚗 Driver:")
        for col, val in zip(col_names, row, strict=False):
            print(f"  {col:30s}: {val}")

    conn.close()


if __name__ == "__main__":
    check_schema()

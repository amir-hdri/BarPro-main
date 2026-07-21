#!/usr/bin/env python3
"""بررسی کامل وضعیت پایگاه داده."""

import os
import sys

import psycopg2


def check_database():
    """بررسی جامع پایگاه داده."""
    try:
        conn = psycopg2.connect(
            host=os.getenv("POSTGRES_HOST", "127.0.0.1"),
            port=int(os.getenv("POSTGRES_PORT", 5432)),
            database=os.getenv("POSTGRES_DB", "utcms_rpa"),
            user=os.getenv("POSTGRES_USER", "postgres"),
            password=os.getenv("POSTGRES_PASSWORD", "postgres"),
        )

        cursor = conn.cursor()

        print("=" * 80)
        print("📊 بررسی کامل پایگاه داده")
        print("=" * 80)

        # 1. بررسی نسخه migration
        print("\n1️⃣ نسخه Migration:")
        cursor.execute("SELECT version_num FROM alembic_version")
        version = cursor.fetchone()
        if version:
            print(f"   ✅ نسخه فعلی: {version[0]}")
        else:
            print("   ❌ جدول alembic_version خالی است!")

        # 2. لیست جداول
        print("\n2️⃣ جداول موجود:")
        cursor.execute(
            """
            SELECT table_name,
                   pg_size_pretty(pg_total_relation_size(quote_ident(table_name)::regclass)) as size
            FROM information_schema.tables
            WHERE table_schema = 'public'
            ORDER BY table_name
        """
        )
        tables = cursor.fetchall()
        print(f"   تعداد کل: {len(tables)} جدول")
        for table, size in tables:
            cursor.execute(f"SELECT COUNT(*) FROM {table}")
            count = cursor.fetchone()[0]
            print(f"   ✓ {table:30s} - {count:6d} ردیف - {size}")

        # 3. بررسی indexes
        print("\n3️⃣ Indexes عملکردی:")
        cursor.execute(
            """
            SELECT indexname, tablename
            FROM pg_indexes
            WHERE schemaname = 'public'
            AND indexname LIKE 'idx_%'
            ORDER BY tablename, indexname
        """
        )
        indexes = cursor.fetchall()
        if indexes:
            print(f"   تعداد: {len(indexes)} index")
            current_table = None
            for idx_name, table_name in indexes:
                if table_name != current_table:
                    print(f"\n   📋 {table_name}:")
                    current_table = table_name
                print(f"      ✓ {idx_name}")
        else:
            print("   ⚠️  هیچ index عملکردی وجود ندارد!")

        # 4. بررسی constraints
        print("\n4️⃣ Constraints:")
        cursor.execute(
            """
            SELECT conname, contype, conrelid::regclass
            FROM pg_constraint
            WHERE connamespace = 'public'::regnamespace
            ORDER BY conrelid::regclass::text, contype
        """
        )
        constraints = cursor.fetchall()
        print(f"   تعداد: {len(constraints)} constraint")

        # 5. بررسی foreign keys
        print("\n5️⃣ Foreign Keys:")
        cursor.execute(
            """
            SELECT
                tc.table_name,
                kcu.column_name,
                ccu.table_name AS foreign_table_name,
                ccu.column_name AS foreign_column_name
            FROM information_schema.table_constraints AS tc
            JOIN information_schema.key_column_usage AS kcu
              ON tc.constraint_name = kcu.constraint_name
              AND tc.table_schema = kcu.table_schema
            JOIN information_schema.constraint_column_usage AS ccu
              ON ccu.constraint_name = tc.constraint_name
              AND ccu.table_schema = tc.table_schema
            WHERE tc.constraint_type = 'FOREIGN KEY'
            AND tc.table_schema = 'public'
            ORDER BY tc.table_name
        """
        )
        fks = cursor.fetchall()
        if fks:
            print(f"   تعداد: {len(fks)} foreign key")
            for table, col, ref_table, ref_col in fks:
                print(f"   ✓ {table}.{col} → {ref_table}.{ref_col}")
        else:
            print("   ℹ️  هیچ foreign key تعریف نشده")

        # 6. بررسی داده‌های مهم
        print("\n6️⃣ داده‌های موجود:")

        # Clients
        cursor.execute("SELECT COUNT(*) FROM clients")
        clients_count = cursor.fetchone()[0]
        print(f"   👥 Clients: {clients_count}")
        if clients_count > 0:
            cursor.execute("SELECT id, name FROM clients LIMIT 3")
            for cid, name in cursor.fetchall():
                print(f"      - {name} (ID: {cid})")

        # Drivers
        cursor.execute("SELECT COUNT(*) FROM drivers")
        drivers_count = cursor.fetchone()[0]
        print(f"   🚗 Drivers: {drivers_count}")
        if drivers_count > 0:
            cursor.execute("SELECT id, username, state FROM drivers LIMIT 3")
            for _did, username, state in cursor.fetchall():
                print(f"      - {username} ({state})")

        # Waybill Jobs
        cursor.execute("SELECT COUNT(*) FROM waybill_jobs")
        jobs_count = cursor.fetchone()[0]
        print(f"   📦 Waybill Jobs: {jobs_count}")
        if jobs_count > 0:
            cursor.execute(
                """
                SELECT status, COUNT(*)
                FROM waybill_jobs
                GROUP BY status
            """
            )
            for status, count in cursor.fetchall():
                print(f"      - {status}: {count}")

        # Waybill Tasks
        cursor.execute("SELECT COUNT(*) FROM waybilltask")
        tasks_count = cursor.fetchone()[0]
        print(f"   📋 Waybill Tasks: {tasks_count}")
        if tasks_count > 0:
            cursor.execute(
                """
                SELECT status, COUNT(*)
                FROM waybilltask
                GROUP BY status
            """
            )
            for status, count in cursor.fetchall():
                print(f"      - {status}: {count}")

        # 7. بررسی مشکلات احتمالی
        print("\n7️⃣ بررسی مشکلات:")
        issues = []

        # آیا migration کامل شده؟
        if version and version[0] != "006_add_performance_indexes":
            issues.append(f"⚠️  Migration ناقص است (فعلی: {version[0]}, مورد انتظار: 006_add_performance_indexes)")

        # آیا indexes ساخته شده؟
        if len(indexes) == 0:
            issues.append("⚠️  هیچ index عملکردی وجود ندارد - migration 006 اجرا نشده")

        # آیا داده اولیه وجود دارد؟
        if clients_count == 0:
            issues.append("⚠️  هیچ client تعریف نشده - نیاز به seed data")

        if drivers_count == 0:
            issues.append("⚠️  هیچ driver تعریف نشده - نیاز به seed data")

        if issues:
            for issue in issues:
                print(f"   {issue}")
        else:
            print("   ✅ مشکل خاصی یافت نشد!")

        print("\n" + "=" * 80)
        print("✅ بررسی کامل شد")
        print("=" * 80)

        conn.close()
        return len(issues) == 0

    except psycopg2.OperationalError as e:
        print("\n❌ خطا در اتصال به پایگاه داده:")
        print(f"   {e}")
        print("\n💡 راه‌حل:")
        print("   1. مطمئن شوید PostgreSQL در حال اجرا است:")
        print("      docker ps | grep postgres")
        print("   2. بررسی کنید پورت 5432 در دسترس است:")
        print("      lsof -i :5432")
        return False
    except Exception as e:
        print(f"\n❌ خطای غیرمنتظره: {e}")
        import traceback

        traceback.print_exc()
        return False


if __name__ == "__main__":
    success = check_database()
    sys.exit(0 if success else 1)

"""Database analysis and optimization script.

Analyzes database performance and suggests optimizations:
- Missing indexes
- Slow queries
- Table statistics
- Connection pool settings
"""
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from sqlalchemy import text

from app.core.database import engine


async def is_postgres(conn):
    try:
        res = await conn.execute(text("SELECT version();"))
        version = res.scalar()
        return 'PostgreSQL' in version
    except Exception:
        return False



async def analyze_indexes():
    """Analyze index usage and suggest improvements."""
    print("\n=== Index Analysis ===")

    async with engine.begin() as conn:
        # Check for missing indexes on foreign keys
        result = await conn.execute(text("""
            SELECT
                tablename,
                indexname,
                indexdef
            FROM pg_indexes
            WHERE schemaname = 'public'
            ORDER BY tablename, indexname;
        """))

        indexes = result.fetchall()
        print(f"\nTotal indexes: {len(indexes)}")

        for idx in indexes:
            print(f"  {idx[0]}.{idx[1]}")


async def analyze_table_stats():
    """Analyze table statistics."""
    print("\n=== Table Statistics ===")

    async with engine.begin() as conn:
        result = await conn.execute(text("""
            SELECT
                schemaname,
                tablename,
                pg_size_pretty(pg_total_relation_size(schemaname||'.'||tablename)) AS size,
                n_live_tup as row_count,
                n_dead_tup as dead_rows,
                last_vacuum,
                last_autovacuum
            FROM pg_stat_user_tables
            ORDER BY pg_total_relation_size(schemaname||'.'||tablename) DESC;
        """))

        tables = result.fetchall()
        print(f"\n{'Table':<30} {'Size':<15} {'Rows':<12} {'Dead Rows':<12}")
        print("-" * 70)

        for table in tables:
            print(f"{table[1]:<30} {table[2]:<15} {table[3]:<12} {table[4]:<12}")


async def analyze_slow_queries():
    """Analyze slow query patterns."""
    print("\n=== Query Performance ===")

    async with engine.begin() as conn:
        # Check if pg_stat_statements is available
        result = await conn.execute(text("""
            SELECT EXISTS (
                SELECT 1 FROM pg_extension WHERE extname = 'pg_stat_statements'
            );
        """))

        has_pg_stat = result.scalar()

        if not has_pg_stat:
            print("pg_stat_statements extension not available")
            print("Enable with: CREATE EXTENSION pg_stat_statements;")
            return

        result = await conn.execute(text("""
            SELECT
                substring(query, 1, 100) as query_snippet,
                calls,
                mean_exec_time,
                total_exec_time
            FROM pg_stat_statements
            WHERE query NOT LIKE '%pg_stat_statements%'
            ORDER BY mean_exec_time DESC
            LIMIT 10;
        """))

        queries = result.fetchall()
        print(f"\n{'Query':<50} {'Calls':<10} {'Avg Time (ms)':<15}")
        print("-" * 80)

        for query in queries:
            print(f"{query[0]:<50} {query[1]:<10} {query[2]:<15.2f}")


async def suggest_optimizations():
    """Suggest database optimizations."""
    print("\n=== Optimization Suggestions ===")

    suggestions = []

    async with engine.begin() as conn:
        # Check for tables without primary keys
        result = await conn.execute(text("""
            SELECT tablename
            FROM pg_tables
            WHERE schemaname = 'public'
            AND tablename NOT IN (
                SELECT tablename
                FROM pg_indexes
                WHERE indexdef LIKE '%PRIMARY KEY%'
            );
        """))

        tables_without_pk = result.fetchall()
        if tables_without_pk:
            suggestions.append(
                f"Tables without primary key: {', '.join(t[0] for t in tables_without_pk)}"
            )

        # Check for high dead tuple ratio
        result = await conn.execute(text("""
            SELECT
                tablename,
                n_dead_tup,
                n_live_tup,
                ROUND(n_dead_tup * 100.0 / NULLIF(n_live_tup, 0), 2) as dead_ratio
            FROM pg_stat_user_tables
            WHERE n_live_tup > 0
            AND n_dead_tup * 100.0 / n_live_tup > 10
            ORDER BY dead_ratio DESC;
        """))

        bloated_tables = result.fetchall()
        if bloated_tables:
            suggestions.append(
                f"Tables needing VACUUM: {', '.join(t[0] for t in bloated_tables)}"
            )

    if suggestions:
        for i, suggestion in enumerate(suggestions, 1):
            print(f"{i}. {suggestion}")
    else:
        print("No immediate optimizations needed.")


async def check_connection_pool():
    """Check connection pool configuration."""
    print("\n=== Connection Pool Settings ===")

    async with engine.begin() as conn:
        result = await conn.execute(text("""
            SELECT
                setting,
                unit,
                context
            FROM pg_settings
            WHERE name IN (
                'max_connections',
                'shared_buffers',
                'effective_cache_size',
                'work_mem',
                'maintenance_work_mem'
            );
        """))

        settings = result.fetchall()
        for setting in settings:
            print(f"  {setting[0]}: {setting[1]} {setting[2] or ''}")

    print(f"\nSQLAlchemy pool size: {engine.pool.size()}")
    print(f"SQLAlchemy pool timeout: {engine.pool.timeout()}")


async def main():
    """Run all database analyses."""
    print("=" * 80)
    print("Database Performance Analysis")
    print("=" * 80)

    try:
        async with engine.begin() as conn:
            if not await is_postgres(conn):
                print("This script is designed for PostgreSQL databases only. Current database is not PostgreSQL.")
                return
        await analyze_table_stats()
        await analyze_indexes()
        await analyze_slow_queries()
        await check_connection_pool()
        await suggest_optimizations()
    except Exception as e:
        print(f"\nError during analysis: {e}")
        import traceback
        traceback.print_exc()
    finally:
        await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())

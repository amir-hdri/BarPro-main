 #!/usr/bin/env python3

import asyncio
import logging
import sys
from pathlib import Path

 # Add project root to path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from alembic import command
from alembic.config import Config
from app.core.config import utcms_config

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


async def check_database_exists() -> bool:
     """Check if database has any tables."""
     engine = create_async_engine(utcms_config.DATABASE_URL, echo=False)
     try:
         async with engine.connect() as conn:
             if 'sqlite' in utcms_config.DATABASE_URL:
                 result = await conn.execute(text("SELECT COUNT(*) FROM sqlite_master WHERE type='table'"))
             else:
                 result = await conn.execute(text("SELECT COUNT(*) FROM information_schema.tables WHERE table_schema = 'public'"))
             count = result.scalar()
             return count > 0
     except Exception as e:
         logger.error(f"Failed to check database: {e}")
         return False
     finally:
         await engine.dispose()


async def check_alembic_version() -> str | None:
     """Get current alembic version."""
     engine = create_async_engine(utcms_config.DATABASE_URL, echo=False)
     try:
         async with engine.connect() as conn:
             result = await conn.execute(text(
                 "SELECT version_num FROM alembic_version LIMIT 1"
             ))
             row = result.fetchone()
             return row[0] if row else None
     except Exception:
         return None
     finally:
         await engine.dispose()


def run_migrations():
     """Run Alembic migrations."""
     project_root = Path(__file__).resolve().parent.parent
     alembic_ini_path = project_root / "alembic.ini"

     if not alembic_ini_path.exists():
         raise FileNotFoundError(f"alembic.ini not found at {alembic_ini_path}")

     alembic_cfg = Config(str(alembic_ini_path))
     alembic_cfg.set_main_option("sqlalchemy.url", utcms_config.DATABASE_URL)

     logger.info("Running migrations...")
     command.upgrade(alembic_cfg, "head")
     logger.info("✅ Migrations completed successfully")


async def main():
    """Main initialization logic."""
    logger.info("🔄 Starting database initialization...")
    logger.info(
        f"📋 Database URL: {utcms_config.DATABASE_URL.split('@')[1] if '@' in utcms_config.DATABASE_URL else 'local'}"
    )

    # Check if database exists
    has_tables = await check_database_exists()
    current_version = await check_alembic_version()

    if has_tables:
        logger.info(
            f"📊 Database exists with tables (current version: {current_version or 'unknown'})"
        )
    else:
        logger.info("📊 Database is empty - will create fresh schema")

    # Alembic's env.py uses asyncio.run(), so execute migrations in a worker
    # thread to avoid nesting an event loop inside this async entrypoint.
    try:
        await asyncio.to_thread(run_migrations)

        # Verify final state
        final_version = await check_alembic_version()
        logger.info(f"✅ Database initialized successfully (version: {final_version})")
        return 0

    except Exception as e:
        logger.error(f"❌ Database initialization failed: {e}")
        logger.error("💡 Try: scripts/reset_database.sh to reset and retry")
        return 1


if __name__ == "__main__":
     exit_code = asyncio.run(main())
     sys.exit(exit_code)

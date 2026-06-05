"""Database configuration and session management with Alembic migrations support."""

import logging
from pathlib import Path

from alembic.config import Config
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.orm import sessionmaker
from sqlmodel.ext.asyncio.session import AsyncSession

from app.core.config import utcms_config

logger = logging.getLogger(__name__)

# Database engine with optimized connection pooling
# Pool settings tuned for async workload with multiple workers
engine_kwargs = {
    "echo": False,
    "future": True,
}

# SQLite does not support standard pooling arguments like pool_size, max_overflow
if "sqlite" not in utcms_config.DATABASE_URL.lower():
    engine_kwargs.update({
        "pool_size": 20,  # Base pool size for concurrent connections
        "max_overflow": 10,  # Additional connections during peak load
        "pool_timeout": 30,  # Wait time before raising timeout error
        "pool_recycle": 3600,  # Recycle connections after 1 hour
        "pool_pre_ping": True,  # Verify connection health before use
    })

engine = create_async_engine(
    utcms_config.DATABASE_URL,
    **engine_kwargs
)
async_session_factory = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


def _get_alembic_config() -> Config:
    """Get Alembic configuration with current database URL."""
    project_root = Path(__file__).resolve().parent.parent.parent
    alembic_ini_path = project_root / "alembic.ini"

    if not alembic_ini_path.exists():
        raise FileNotFoundError(
            f"Alembic configuration not found at {alembic_ini_path}. "
            "Run 'alembic init alembic' to initialize migrations."
        )

    alembic_cfg = Config(str(alembic_ini_path))
    alembic_cfg.set_main_option("sqlalchemy.url", utcms_config.DATABASE_URL)
    return alembic_cfg


async def run_migrations() -> None:
    """Run pending Alembic migrations programmatically.
    
    CRITICAL: On PostgreSQL, we MUST NOT fallback to create_all() if migrations fail,
    because partial schema may already exist, causing duplicate constraint errors.
    """
    import os
    import sys

    if "pytest" in sys.modules or "PYTEST_CURRENT_TEST" in os.environ or os.getenv("ENVIRONMENT") == "test":
        logger.info("database_migrations_skipped", extra={"extra_fields": {"note": "Skipped programmatic migrations in test environment."}})
        return

    try:
        alembic_cfg = _get_alembic_config()
        
        # Run migrations in a separate thread to avoid event loop conflicts
        # since alembic env.py uses asyncio.run()
        from alembic import command
        import asyncio
        
        logger.info("Running pending database migrations programmatically...")
        await asyncio.to_thread(command.upgrade, alembic_cfg, "head")
        
        logger.info("database_migrations_applied", extra={"extra_fields": {"status": "success"}})
    except Exception as exc:
        logger.error(
            "database_migration_failed",
            extra={"extra_fields": {"error": str(exc)}},
        )
        # On PostgreSQL, create_all() fallback is dangerous because:
        # 1. Partial migrations may have already created some tables/constraints
        # 2. create_all() will try to recreate them, causing duplicate errors
        # 3. Multiple models may share constraint names (e.g., uq_waybill_task_task_id)
        #
        # Solution: Only use create_all() for SQLite (fresh DB), fail fast on PostgreSQL
        logger.error(
            "migration_failed_postgresql",
            extra={"extra_fields": {
                "error": str(exc),
                "solution": "Fix migrations manually: alembic downgrade base && alembic upgrade head"
            }},
        )
        raise RuntimeError(
            f"Database migration failed on PostgreSQL: {exc}\n"
            "Please fix migrations manually or reset database."
        ) from exc


async def init_db():
    """Initialize database with Alembic migrations, fallback to legacy creation."""
    await run_migrations()



async def get_session() -> AsyncSession:
    """Dependency for database session."""
    async with async_session_factory() as session:
        try:
            yield session
        finally:
            await session.close()

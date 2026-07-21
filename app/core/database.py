"""Database configuration and session management with Alembic migrations support."""

import asyncio
import logging
import os
import sys
from pathlib import Path

from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import AsyncAdaptedQueuePool
from sqlmodel.ext.asyncio.session import AsyncSession

from alembic.config import Config
from app.core.config import utcms_config

logger = logging.getLogger(__name__)

# Database engine with optimized connection pooling
# Pool settings tuned for async workload with multiple workers


engine_kwargs = {
    "echo": False,
    "future": True,
}

# If Celery worker is running, use AsyncAdaptedQueuePool with optimized pool settings
if "celery" in sys.modules or (len(sys.argv) > 0 and "celery" in sys.argv[0]):
    engine_kwargs["poolclass"] = AsyncAdaptedQueuePool
    engine_kwargs["pool_size"] = 2
    engine_kwargs["max_overflow"] = 2
    engine_kwargs["pool_recycle"] = 600
    engine_kwargs["pool_pre_ping"] = True
elif "sqlite" not in utcms_config.DATABASE_URL.lower():
    engine_kwargs.update(
        {
            "pool_size": 20,  # Base pool size for concurrent connections
            "max_overflow": 10,  # Additional connections during peak load
            "pool_timeout": 30,  # Wait time before raising timeout error
            "pool_recycle": 3600,  # Recycle connections after 1 hour
            "pool_pre_ping": True,  # Verify connection health before use
        }
    )

engine = create_async_engine(utcms_config.DATABASE_URL, **engine_kwargs)
async_session_factory = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


def _get_alembic_config() -> "Config":
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
    """Run pending Alembic migrations programmatically using a distributed lock.

    Uses Redis to ensure only ONE Celery worker runs migrations at startup,
    preventing deadlocks when multiple workers start simultaneously.
    On PostgreSQL, we MUST NOT fallback to create_all() if migrations fail.
    """
    if os.getenv("SKIP_MIGRATIONS") == "true":
        logger.info(
            "database_migrations_skipped_by_env",
            extra={"extra_fields": {"note": "SKIP_MIGRATIONS=true set, skipping migrations."}},
        )
        return

    if "pytest" in sys.modules or "PYTEST_CURRENT_TEST" in os.environ or os.getenv("ENVIRONMENT") == "test":
        logger.info(
            "database_migrations_skipped",
            extra={"extra_fields": {"note": "Skipped programmatic migrations in test environment."}},
        )
        return

    # Try to acquire a distributed lock via Redis (only one worker runs migrations)
    lock_acquired = False
    try:
        from app.core.redis import redis_manager

        if redis_manager is not None and redis_manager._redis is not None:
            lock_acquired = await redis_manager._redis.setnx("migration_lock", "1")
            if lock_acquired:
                await redis_manager._redis.expire("migration_lock", 300)  # 5 min TTL
                logger.info("migration_lock_acquired", extra={"extra_fields": {"note": "Running migrations..."}})
            else:
                logger.info(
                    "migration_lock_held_by_another_worker",
                    extra={"extra_fields": {"note": "Skipping migrations — another worker is handling them."}},
                )
                return
        else:
            logger.info(
                "migration_redis_unavailable_running_directly",
                extra={"extra_fields": {"note": "Redis not available, running migrations directly."}},
            )
    except Exception:
        logger.warning("migration_lock_check_failed_running_directly", exc_info=True)

    try:
        from alembic import command
        from alembic.config import Config

        alembic_ini_path = os.path.join(os.path.dirname(__file__), "..", "..", "alembic.ini")
        if not os.path.exists(alembic_ini_path):
            logger.warning("alembic_ini_not_found", extra={"extra_fields": {"path": alembic_ini_path}})
            return

        alembic_cfg = Config(str(alembic_ini_path))
        alembic_cfg.set_main_option("sqlalchemy.url", utcms_config.DATABASE_URL)

        def _run_upgrade(cfg: Config) -> None:
            command.upgrade(cfg, "head")

        await asyncio.to_thread(_run_upgrade, alembic_cfg)
        logger.info("database_migrations_applied", extra={"extra_fields": {"status": "success"}})
    except Exception as exc:
        logger.error("database_migration_failed", extra={"extra_fields": {"error": str(exc)}})
        logger.error(
            "migration_failed_postgresql",
            extra={
                "extra_fields": {
                    "error": str(exc),
                    "solution": "Fix migrations manually: alembic downgrade base && alembic upgrade head",
                }
            },
        )
        raise RuntimeError(
            f"Database migration failed on PostgreSQL: {exc}\n" "Please fix migrations manually or reset database."
        ) from exc
    finally:
        if lock_acquired:
            try:
                from app.core.redis import redis_manager

                if redis_manager is not None and redis_manager._redis is not None:
                    await redis_manager._redis.delete("migration_lock")
            except Exception:
                logger.warning("migration_lock_release_failed", exc_info=True)


async def init_db():
    """Initialize database with Alembic migrations, fallback to legacy creation."""
    await run_migrations()


async def get_session() -> AsyncSession:
    """Dependency for database session.

    Properly handles commit on success and rollback on failure.
    This prevents dirty sessions from leaking into subsequent requests.
    """
    async with async_session_factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()

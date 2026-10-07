"""Explicit CI services or a private local Redis; never use production defaults."""

import asyncio
import os
import shutil
import tempfile
import uuid
from collections.abc import AsyncIterator
from pathlib import Path

import pytest
from redis.asyncio import Redis
from redis.exceptions import ConnectionError as RedisConnectionError
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlmodel import SQLModel
from sqlmodel.ext.asyncio.session import AsyncSession

from app.automation import gps_shipping_manager as shipping


@pytest.fixture
async def redis_claim_store() -> AsyncIterator[tuple[Redis, str]]:
    """Use only unique test-owned keys, including on an explicitly supplied CI Redis."""
    url = os.getenv("BARPRO_TEST_REDIS_URL")
    process = None
    directory = None
    if url:
        connection = Redis.from_url(url, decode_responses=True, socket_connect_timeout=2, socket_timeout=2)
    else:
        binary = shutil.which("redis-server")
        if binary is None:
            if os.getenv("BARPRO_REQUIRE_REDIS_INTEGRATION") == "1":
                pytest.fail("Redis integration requires BARPRO_TEST_REDIS_URL or redis-server")
            pytest.skip("No explicit test Redis URL or local redis-server binary")
        # A short path also fits macOS's Unix socket pathname limit.
        directory = tempfile.TemporaryDirectory(prefix="barpro-redis-")
        socket_path = Path(directory.name) / "redis.sock"
        process = await asyncio.create_subprocess_exec(
            binary,
            "--port",
            "0",
            "--unixsocket",
            str(socket_path),
            "--unixsocketperm",
            "700",
            "--save",
            "",
            "--appendonly",
            "no",
            "--dir",
            directory.name,
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.PIPE,
        )
        connection = Redis(unix_socket_path=str(socket_path), decode_responses=True, socket_timeout=2)
    job_id = f"integration-{uuid.uuid4().hex}"
    keys = [
        template.format(job_id=job_id)
        for template in (shipping.COMPLETION_CLAIM_KEY, shipping.LEGACY_COMPLETION_CLAIM_KEY)
    ]
    ready = False
    try:
        async with asyncio.timeout(8):
            while True:
                try:
                    await connection.ping()
                    ready = True
                    break
                except RedisConnectionError:
                    if url or (process is not None and process.returncode is not None):
                        raise
                    await asyncio.sleep(0.05)
        assert int((await connection.info("server"))["redis_version"].split(".")[0]) >= 7
        yield connection, job_id
    finally:
        try:
            if ready:
                await connection.delete(*keys)
        finally:
            try:
                await connection.aclose()
            finally:
                try:
                    if process is not None:
                        if process.returncode is None:
                            process.terminate()
                        try:
                            await asyncio.wait_for(process.communicate(), timeout=5)
                        except TimeoutError:
                            process.kill()
                            await process.communicate()
                finally:
                    if directory is not None:
                        directory.cleanup()


@pytest.fixture
async def postgres_factory() -> AsyncIterator[async_sessionmaker[AsyncSession]]:
    """Create and remove only this test's isolated schema in an explicit test DB."""
    dsn = os.getenv("BARPRO_TEST_POSTGRES_DSN")
    if not dsn:
        if os.getenv("BARPRO_REQUIRE_PG_INTEGRATION") == "1":
            pytest.fail("PostgreSQL integration requires BARPRO_TEST_POSTGRES_DSN")
        pytest.skip("PostgreSQL unverified locally: set BARPRO_TEST_POSTGRES_DSN to an isolated PostgreSQL 16 test DB")
    if not dsn.startswith("postgresql+asyncpg://"):
        pytest.fail("BARPRO_TEST_POSTGRES_DSN must use postgresql+asyncpg")
    schema = f"barpro_test_{uuid.uuid4().hex}"
    admin_engine = create_async_engine(dsn, connect_args={"timeout": 5})
    engine = None
    created = False
    try:
        async with admin_engine.begin() as connection:
            version = int((await connection.exec_driver_sql("SHOW server_version_num")).scalar_one())
            assert version >= 160000, "Integration contract requires PostgreSQL 16 or newer"
            await connection.execute(text(f'CREATE SCHEMA "{schema}"'))
            created = True
        engine = create_async_engine(
            dsn,
            connect_args={"timeout": 5, "server_settings": {"search_path": schema, "timezone": "America/Los_Angeles"}},
        )
        async with engine.begin() as connection:
            await connection.run_sync(SQLModel.metadata.create_all)
        yield async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    finally:
        try:
            if engine is not None:
                await engine.dispose()
        finally:
            try:
                if created:
                    async with admin_engine.begin() as connection:
                        await connection.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))
            finally:
                await admin_engine.dispose()

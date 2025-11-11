"""Database connection pool management."""

import asyncpg
import structlog
from contextlib import asynccontextmanager
from typing import AsyncIterator

from authorization_api.config import settings

logger = structlog.get_logger()

# Global connection pool
_pool: asyncpg.Pool | None = None


async def create_pool() -> asyncpg.Pool:
    """Create and return a connection pool.

    Returns:
        asyncpg.Pool: Database connection pool
    """
    logger.info(
        "creating_database_pool",
        database_url=settings.database_url.split("@")[-1],  # Hide credentials
        min_size=settings.database_pool_min_size,
        max_size=settings.database_pool_max_size,
    )

    pool = await asyncpg.create_pool(
        dsn=settings.database_url,
        min_size=settings.database_pool_min_size,
        max_size=settings.database_pool_max_size,
        command_timeout=30.0,
        server_settings={
            "application_name": settings.service_name,
        },
    )

    if pool is None:
        raise RuntimeError("Failed to create database pool")

    logger.info("database_pool_created")
    return pool


async def get_pool() -> asyncpg.Pool:
    """Get the global connection pool.

    Returns:
        asyncpg.Pool: Database connection pool

    Raises:
        RuntimeError: If pool is not initialized
    """
    global _pool
    if _pool is None:
        _pool = await create_pool()
    return _pool


async def close_pool() -> None:
    """Close the global connection pool."""
    global _pool
    if _pool is not None:
        logger.info("closing_database_pool")
        await _pool.close()
        _pool = None
        logger.info("database_pool_closed")


@asynccontextmanager
async def get_connection() -> AsyncIterator[asyncpg.Connection]:
    """Get a database connection from the pool.

    Yields:
        asyncpg.Connection: Database connection

    Example:
        async with get_connection() as conn:
            result = await conn.fetchrow("SELECT 1")
    """
    pool = await get_pool()
    async with pool.acquire() as connection:
        yield connection


@asynccontextmanager
async def transaction() -> AsyncIterator[asyncpg.Connection]:
    """Get a database connection with an active transaction.

    Yields:
        asyncpg.Connection: Database connection with transaction

    Example:
        async with transaction() as conn:
            await conn.execute("INSERT INTO ...")
            await conn.execute("INSERT INTO ...")
            # Auto-commits on success, auto-rolls back on exception
    """
    async with get_connection() as conn:
        async with conn.transaction():
            yield conn

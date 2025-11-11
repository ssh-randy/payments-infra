"""FastAPI application entry point for Authorization API."""

import asyncio
from contextlib import asynccontextmanager
from typing import AsyncIterator

import structlog
from fastapi import FastAPI, Response
from fastapi.responses import JSONResponse

from authorization_api.config import settings
from authorization_api.infrastructure.database import close_pool, get_pool
from authorization_api.logging_config import configure_logging

# Configure logging at module level
configure_logging()

logger = structlog.get_logger()

# Background task for outbox processor
_outbox_processor_task: asyncio.Task | None = None


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Application lifespan manager.

    Handles startup and shutdown:
    - Initialize database pool
    - Start outbox processor
    - Clean up on shutdown
    """
    logger.info("starting_authorization_api", environment=settings.environment)

    # Initialize database pool
    try:
        pool = await get_pool()
        logger.info("database_pool_initialized")

        # Verify database connection
        async with pool.acquire() as conn:
            await conn.fetchval("SELECT 1")
        logger.info("database_connection_verified")

    except Exception as e:
        logger.error("failed_to_initialize_database", error=str(e))
        raise

    # Start outbox processor if enabled
    global _outbox_processor_task
    if settings.outbox_processor_enabled:
        from authorization_api.infrastructure.outbox_processor import run_outbox_processor

        _outbox_processor_task = asyncio.create_task(run_outbox_processor())
        logger.info("outbox_processor_started")

    logger.info("authorization_api_started")

    yield

    # Shutdown
    logger.info("shutting_down_authorization_api")

    # Stop outbox processor
    if _outbox_processor_task is not None:
        logger.info("stopping_outbox_processor")
        _outbox_processor_task.cancel()
        try:
            await _outbox_processor_task
        except asyncio.CancelledError:
            pass
        logger.info("outbox_processor_stopped")

    # Close database pool
    await close_pool()

    logger.info("authorization_api_shutdown_complete")


# Create FastAPI app
app = FastAPI(
    title="Authorization API",
    description="Payment authorization API with event sourcing",
    version="0.1.0",
    lifespan=lifespan,
)


@app.get("/health")
async def health_check() -> Response:
    """Health check endpoint.

    Returns:
        200 OK if service is healthy
        503 Service Unavailable if unhealthy
    """
    try:
        # Check database connectivity
        pool = await get_pool()
        async with pool.acquire() as conn:
            await conn.fetchval("SELECT 1")

        return JSONResponse(
            status_code=200,
            content={
                "status": "healthy",
                "service": settings.service_name,
                "environment": settings.environment,
            },
        )
    except Exception as e:
        logger.error("health_check_failed", error=str(e))
        return JSONResponse(
            status_code=503,
            content={
                "status": "unhealthy",
                "service": settings.service_name,
                "error": str(e),
            },
        )


@app.get("/")
async def root() -> dict[str, str]:
    """Root endpoint."""
    return {
        "service": "Authorization API",
        "version": "0.1.0",
        "status": "running",
    }

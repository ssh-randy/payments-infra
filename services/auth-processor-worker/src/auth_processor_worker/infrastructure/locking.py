"""Distributed locking mechanism using PostgreSQL.

This module provides distributed locking to ensure exactly-once processing
of authorization requests across multiple worker instances.
"""

import asyncio
import uuid
import structlog
from datetime import datetime, timedelta
from typing import Optional

from auth_processor_worker.infrastructure.database import get_connection

logger = structlog.get_logger()


async def acquire_lock(
    auth_request_id: uuid.UUID,
    worker_id: str,
    ttl_seconds: int = 30
) -> bool:
    """Acquire a distributed lock for an auth request.

    Uses PostgreSQL INSERT ... ON CONFLICT DO NOTHING to atomically
    acquire a lock. This ensures only one worker can process a given
    auth_request_id at a time.

    Args:
        auth_request_id: UUID of the authorization request
        worker_id: Identifier of the worker attempting to acquire the lock
        ttl_seconds: Time-to-live for the lock in seconds (default: 30)

    Returns:
        bool: True if lock was acquired, False if already held by another worker

    Example:
        >>> lock_acquired = await acquire_lock(
        ...     auth_request_id=uuid.UUID("..."),
        ...     worker_id="worker-123"
        ... )
        >>> if lock_acquired:
        ...     # Process the request
        ...     await release_lock(auth_request_id, worker_id)
    """
    async with get_connection() as conn:
        try:
            # Use INSERT ... ON CONFLICT DO NOTHING for atomic lock acquisition
            # RETURNING clause will return the row if inserted, or nothing if conflict
            result = await conn.fetchrow(
                """
                INSERT INTO auth_processing_locks (auth_request_id, worker_id, expires_at)
                VALUES ($1, $2, NOW() + $3 * INTERVAL '1 second')
                ON CONFLICT (auth_request_id) DO NOTHING
                RETURNING auth_request_id
                """,
                auth_request_id,
                worker_id,
                ttl_seconds,
            )

            if result is not None:
                logger.info(
                    "lock_acquired",
                    auth_request_id=str(auth_request_id),
                    worker_id=worker_id,
                    ttl_seconds=ttl_seconds,
                )
                return True
            else:
                # Lock already exists - check if it's expired
                existing_lock = await conn.fetchrow(
                    """
                    SELECT worker_id, expires_at
                    FROM auth_processing_locks
                    WHERE auth_request_id = $1
                    """,
                    auth_request_id,
                )

                if existing_lock:
                    logger.debug(
                        "lock_already_held",
                        auth_request_id=str(auth_request_id),
                        worker_id=worker_id,
                        held_by=existing_lock["worker_id"],
                        expires_at=existing_lock["expires_at"].isoformat(),
                    )

                return False

        except Exception as e:
            logger.error(
                "lock_acquisition_failed",
                auth_request_id=str(auth_request_id),
                worker_id=worker_id,
                error=str(e),
            )
            raise


async def release_lock(
    auth_request_id: uuid.UUID,
    worker_id: str,
) -> None:
    """Release a distributed lock for an auth request.

    Deletes the lock row matching both auth_request_id and worker_id.
    This ensures only the worker that acquired the lock can release it.

    Args:
        auth_request_id: UUID of the authorization request
        worker_id: Identifier of the worker releasing the lock

    Example:
        >>> await release_lock(
        ...     auth_request_id=uuid.UUID("..."),
        ...     worker_id="worker-123"
        ... )
    """
    async with get_connection() as conn:
        try:
            result = await conn.execute(
                """
                DELETE FROM auth_processing_locks
                WHERE auth_request_id = $1 AND worker_id = $2
                """,
                auth_request_id,
                worker_id,
            )

            # Extract number of rows deleted from result string "DELETE N"
            rows_deleted = int(result.split()[-1]) if result else 0

            if rows_deleted > 0:
                logger.info(
                    "lock_released",
                    auth_request_id=str(auth_request_id),
                    worker_id=worker_id,
                )
            else:
                logger.warning(
                    "lock_not_found_on_release",
                    auth_request_id=str(auth_request_id),
                    worker_id=worker_id,
                )

        except Exception as e:
            logger.error(
                "lock_release_failed",
                auth_request_id=str(auth_request_id),
                worker_id=worker_id,
                error=str(e),
            )
            raise


async def cleanup_expired_locks() -> int:
    """Clean up expired locks from the database.

    Deletes all locks where expires_at < NOW(). This should be called
    periodically (e.g., every 30 seconds) to prevent lock table bloat
    and handle cases where workers crash without releasing locks.

    Returns:
        int: Number of expired locks cleaned up

    Example:
        >>> cleaned = await cleanup_expired_locks()
        >>> print(f"Cleaned up {cleaned} expired locks")
    """
    async with get_connection() as conn:
        try:
            result = await conn.execute(
                """
                DELETE FROM auth_processing_locks
                WHERE expires_at < NOW()
                """
            )

            # Extract number of rows deleted from result string "DELETE N"
            rows_deleted = int(result.split()[-1]) if result else 0

            if rows_deleted > 0:
                logger.info(
                    "expired_locks_cleaned",
                    count=rows_deleted,
                )

            return rows_deleted

        except Exception as e:
            logger.error(
                "lock_cleanup_failed",
                error=str(e),
            )
            raise


async def start_lock_cleanup_task(
    interval_seconds: int = 30,
    stop_event: Optional[asyncio.Event] = None,
) -> None:
    """Background task that periodically cleans up expired locks.

    This task should be started when the worker service starts and
    runs continuously until the stop_event is set.

    Args:
        interval_seconds: How often to run cleanup (default: 30 seconds)
        stop_event: Optional event to signal task shutdown

    Example:
        >>> stop_event = asyncio.Event()
        >>> cleanup_task = asyncio.create_task(
        ...     start_lock_cleanup_task(stop_event=stop_event)
        ... )
        >>> # ... later when shutting down ...
        >>> stop_event.set()
        >>> await cleanup_task
    """
    if stop_event is None:
        stop_event = asyncio.Event()

    logger.info(
        "lock_cleanup_task_started",
        interval_seconds=interval_seconds,
    )

    try:
        while not stop_event.is_set():
            try:
                await cleanup_expired_locks()
            except Exception as e:
                logger.error(
                    "lock_cleanup_iteration_failed",
                    error=str(e),
                )

            # Wait for interval or until stop_event is set
            try:
                await asyncio.wait_for(
                    stop_event.wait(),
                    timeout=interval_seconds
                )
                break  # Stop event was set
            except asyncio.TimeoutError:
                continue  # Timeout reached, run cleanup again

    finally:
        logger.info("lock_cleanup_task_stopped")

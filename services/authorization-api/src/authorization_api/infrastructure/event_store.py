"""Event store implementation for writing and reading events."""

import uuid
from typing import Any

import asyncpg
import structlog

logger = structlog.get_logger()


async def write_event(
    conn: asyncpg.Connection,
    event_id: uuid.UUID,
    aggregate_id: uuid.UUID,
    aggregate_type: str,
    event_type: str,
    event_data: bytes,
    sequence_number: int,
    metadata: dict[str, Any] | None = None,
) -> None:
    """Write an event to the event store.

    Args:
        conn: Database connection (must be in transaction)
        event_id: Unique event ID
        aggregate_id: Aggregate ID (e.g., auth_request_id)
        aggregate_type: Type of aggregate (e.g., 'auth_request')
        event_type: Type of event (e.g., 'AuthRequestCreated')
        event_data: Serialized protobuf event data
        sequence_number: Sequence number for this aggregate
        metadata: Optional metadata (correlation_id, causation_id, etc.)
    """
    metadata_json = metadata or {}

    await conn.execute(
        """
        INSERT INTO payment_events (
            event_id,
            aggregate_id,
            aggregate_type,
            event_type,
            event_data,
            sequence_number,
            metadata
        )
        VALUES ($1, $2, $3, $4, $5, $6, $7)
        """,
        event_id,
        aggregate_id,
        aggregate_type,
        event_type,
        event_data,
        sequence_number,
        metadata_json,
    )

    logger.info(
        "event_written",
        event_id=str(event_id),
        aggregate_id=str(aggregate_id),
        event_type=event_type,
        sequence_number=sequence_number,
    )


async def get_next_sequence_number(
    conn: asyncpg.Connection,
    aggregate_id: uuid.UUID,
) -> int:
    """Get the next sequence number for an aggregate.

    Args:
        conn: Database connection
        aggregate_id: Aggregate ID

    Returns:
        Next sequence number (1 if no events exist)
    """
    result = await conn.fetchval(
        """
        SELECT COALESCE(MAX(sequence_number), 0) + 1
        FROM payment_events
        WHERE aggregate_id = $1
        """,
        aggregate_id,
    )

    return result or 1

"""Outbox pattern implementation for reliable queue delivery."""

import uuid

import asyncpg
import structlog

logger = structlog.get_logger()


async def write_outbox_message(
    conn: asyncpg.Connection,
    aggregate_id: uuid.UUID,
    message_type: str,
    payload: bytes,
) -> None:
    """Write a message to the outbox table.

    Args:
        conn: Database connection (must be in transaction)
        aggregate_id: Aggregate ID (e.g., auth_request_id)
        message_type: Type of message (e.g., 'auth_request_queued')
        payload: Serialized protobuf message
    """
    await conn.execute(
        """
        INSERT INTO outbox (aggregate_id, message_type, payload, created_at)
        VALUES ($1, $2, $3, NOW())
        """,
        aggregate_id,
        message_type,
        payload,
    )

    logger.info(
        "outbox_message_written",
        aggregate_id=str(aggregate_id),
        message_type=message_type,
    )

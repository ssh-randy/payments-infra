"""Outbox processor for reliable message delivery to SQS."""

import asyncio
import structlog

from payments.v1.events_pb2 import (
    AuthRequestQueuedMessage,
    VoidRequestQueuedMessage,
)

from authorization_api.config import settings
from authorization_api.infrastructure.database import get_pool
from authorization_api.infrastructure.sqs_client import (
    send_to_auth_requests_queue,
    send_to_void_requests_queue,
)

logger = structlog.get_logger()


async def fetch_unprocessed_messages(conn, limit: int) -> list[dict]:
    """Fetch unprocessed outbox messages.

    Uses FOR UPDATE SKIP LOCKED to prevent multiple processors from
    processing the same messages.

    Args:
        conn: Database connection
        limit: Maximum number of messages to fetch

    Returns:
        List of outbox message records
    """
    rows = await conn.fetch(
        """
        SELECT id, aggregate_id, message_type, payload
        FROM outbox
        WHERE processed_at IS NULL
        ORDER BY created_at
        LIMIT $1
        FOR UPDATE SKIP LOCKED
        """,
        limit,
    )

    return [dict(row) for row in rows]


async def send_message_to_sqs(message: dict) -> None:
    """Send a single outbox message to appropriate SQS queue.

    Args:
        message: Outbox message record with id, aggregate_id, message_type, payload

    Raises:
        Exception: If sending to SQS fails
    """
    message_type = message["message_type"]
    payload = message["payload"]
    aggregate_id = str(message["aggregate_id"])

    if message_type == "auth_request_queued":
        # Deserialize to get restaurant_id for message grouping
        queued_msg = AuthRequestQueuedMessage()
        queued_msg.ParseFromString(payload)

        await send_to_auth_requests_queue(
            message_body=payload,
            message_deduplication_id=aggregate_id,
            message_group_id=queued_msg.restaurant_id,
        )

    elif message_type == "void_request_queued":
        # Standard queue, no deduplication or grouping needed
        await send_to_void_requests_queue(message_body=payload)

    else:
        logger.warning(
            "unknown_message_type",
            message_type=message_type,
            message_id=message["id"],
        )
        raise ValueError(f"Unknown message type: {message_type}")


async def mark_message_as_processed(conn, message_id: int) -> None:
    """Mark an outbox message as processed.

    Args:
        conn: Database connection
        message_id: Outbox message ID
    """
    await conn.execute(
        """
        UPDATE outbox
        SET processed_at = NOW()
        WHERE id = $1
        """,
        message_id,
    )


async def process_outbox_batch() -> int:
    """Process a single batch of outbox messages.

    Returns:
        Number of messages processed
    """
    pool = await get_pool()

    # Use a transaction to fetch and mark messages
    async with pool.acquire() as conn:
        # Fetch unprocessed messages
        messages = await fetch_unprocessed_messages(
            conn, settings.outbox_processor_batch_size
        )

        if not messages:
            return 0

        logger.debug("processing_outbox_batch", count=len(messages))

        processed_count = 0

        for message in messages:
            try:
                # Send to SQS
                await send_message_to_sqs(message)

                # Mark as processed (in same connection to ensure consistency)
                await mark_message_as_processed(conn, message["id"])

                processed_count += 1

            except Exception as e:
                logger.error(
                    "failed_to_process_outbox_message",
                    message_id=message["id"],
                    message_type=message["message_type"],
                    aggregate_id=str(message["aggregate_id"]),
                    error=str(e),
                )
                # Continue processing other messages
                # This message will be retried on next poll

        if processed_count > 0:
            logger.info("outbox_batch_processed", processed=processed_count)

        return processed_count


async def run_outbox_processor() -> None:
    """Run the outbox processor in the background.

    This polls the outbox table and sends messages to SQS.
    Implements the Transactional Outbox Pattern for at-least-once delivery.
    """
    logger.info(
        "outbox_processor_starting",
        interval_ms=settings.outbox_processor_interval_ms,
        batch_size=settings.outbox_processor_batch_size,
    )

    try:
        while True:
            try:
                # Process a batch of messages
                await process_outbox_batch()

                # Sleep for configured interval
                await asyncio.sleep(settings.outbox_processor_interval_ms / 1000.0)

            except Exception as e:
                logger.error("outbox_processor_error", error=str(e))
                await asyncio.sleep(1.0)  # Back off on error

    except asyncio.CancelledError:
        logger.info("outbox_processor_cancelled")
        raise

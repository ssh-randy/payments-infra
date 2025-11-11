"""Outbox processor for reliable message delivery to SQS."""

import asyncio
import structlog

from authorization_api.config import settings

logger = structlog.get_logger()


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
                # TODO: Implement outbox processing logic
                # 1. SELECT unprocessed messages from outbox (FOR UPDATE SKIP LOCKED)
                # 2. Send each message to SQS
                # 3. UPDATE outbox SET processed_at = NOW()

                await asyncio.sleep(settings.outbox_processor_interval_ms / 1000.0)

            except Exception as e:
                logger.error("outbox_processor_error", error=str(e))
                await asyncio.sleep(1.0)  # Back off on error

    except asyncio.CancelledError:
        logger.info("outbox_processor_cancelled")
        raise

"""Read model update functions for auth_request_state table.

These functions handle atomic updates to the read model based on event types.
They must be called within a transaction context.
"""

import uuid
from datetime import datetime

import asyncpg
import structlog

logger = structlog.get_logger()


async def update_to_processing(
    conn: asyncpg.Connection,
    auth_request_id: uuid.UUID,
    sequence_number: int,
) -> None:
    """Update read model to PROCESSING status.

    Called when AuthAttemptStarted event is recorded.

    Args:
        conn: Database connection (must be in transaction)
        auth_request_id: Authorization request ID
        sequence_number: Event sequence number
    """
    await conn.execute(
        """
        UPDATE auth_request_state
        SET status = 'PROCESSING',
            updated_at = $2,
            last_event_sequence = $3
        WHERE auth_request_id = $1
        """,
        auth_request_id,
        datetime.utcnow(),
        sequence_number,
    )

    logger.info(
        "read_model_updated",
        auth_request_id=str(auth_request_id),
        status="PROCESSING",
        sequence=sequence_number,
    )


async def update_to_authorized(
    conn: asyncpg.Connection,
    auth_request_id: uuid.UUID,
    sequence_number: int,
    processor_auth_id: str,
    processor_name: str,
    authorized_amount_cents: int,
    authorization_code: str,
) -> None:
    """Update read model to AUTHORIZED status.

    Called when AuthResponseReceived event with AUTHORIZED status is recorded.

    Args:
        conn: Database connection (must be in transaction)
        auth_request_id: Authorization request ID
        sequence_number: Event sequence number
        processor_auth_id: Processor's authorization ID
        processor_name: Name of payment processor
        authorized_amount_cents: Authorized amount in cents
        authorization_code: Authorization code from processor
    """
    now = datetime.utcnow()

    await conn.execute(
        """
        UPDATE auth_request_state
        SET status = 'AUTHORIZED',
            processor_auth_id = $2,
            processor_name = $3,
            authorized_amount_cents = $4,
            authorization_code = $5,
            completed_at = $6,
            updated_at = $7,
            last_event_sequence = $8
        WHERE auth_request_id = $1
        """,
        auth_request_id,
        processor_auth_id,
        processor_name,
        authorized_amount_cents,
        authorization_code,
        now,
        now,
        sequence_number,
    )

    logger.info(
        "read_model_updated",
        auth_request_id=str(auth_request_id),
        status="AUTHORIZED",
        processor_name=processor_name,
        sequence=sequence_number,
    )


async def update_to_denied(
    conn: asyncpg.Connection,
    auth_request_id: uuid.UUID,
    sequence_number: int,
    processor_name: str,
    denial_code: str,
    denial_reason: str,
) -> None:
    """Update read model to DENIED status.

    Called when AuthResponseReceived event with DENIED status is recorded.

    Args:
        conn: Database connection (must be in transaction)
        auth_request_id: Authorization request ID
        sequence_number: Event sequence number
        processor_name: Name of payment processor
        denial_code: Denial code from processor
        denial_reason: Human-readable denial reason
    """
    now = datetime.utcnow()

    await conn.execute(
        """
        UPDATE auth_request_state
        SET status = 'DENIED',
            processor_name = $2,
            denial_code = $3,
            denial_reason = $4,
            completed_at = $5,
            updated_at = $6,
            last_event_sequence = $7
        WHERE auth_request_id = $1
        """,
        auth_request_id,
        processor_name,
        denial_code,
        denial_reason,
        now,
        now,
        sequence_number,
    )

    logger.info(
        "read_model_updated",
        auth_request_id=str(auth_request_id),
        status="DENIED",
        denial_code=denial_code,
        sequence=sequence_number,
    )


async def update_to_failed(
    conn: asyncpg.Connection,
    auth_request_id: uuid.UUID,
    sequence_number: int,
) -> None:
    """Update read model to FAILED status.

    Called when AuthAttemptFailed event with is_retryable=False is recorded.

    Args:
        conn: Database connection (must be in transaction)
        auth_request_id: Authorization request ID
        sequence_number: Event sequence number
    """
    now = datetime.utcnow()

    await conn.execute(
        """
        UPDATE auth_request_state
        SET status = 'FAILED',
            completed_at = $2,
            updated_at = $3,
            last_event_sequence = $4
        WHERE auth_request_id = $1
        """,
        auth_request_id,
        now,
        now,
        sequence_number,
    )

    logger.info(
        "read_model_updated",
        auth_request_id=str(auth_request_id),
        status="FAILED",
        sequence=sequence_number,
    )


async def update_retry_attempt(
    conn: asyncpg.Connection,
    auth_request_id: uuid.UUID,
    sequence_number: int,
) -> None:
    """Update read model after retryable failure.

    Status remains PROCESSING - just updates sequence number and timestamp.

    Called when AuthAttemptFailed event with is_retryable=True is recorded.

    Args:
        conn: Database connection (must be in transaction)
        auth_request_id: Authorization request ID
        sequence_number: Event sequence number
    """
    await conn.execute(
        """
        UPDATE auth_request_state
        SET updated_at = $2,
            last_event_sequence = $3
        WHERE auth_request_id = $1
        """,
        auth_request_id,
        datetime.utcnow(),
        sequence_number,
    )

    logger.info(
        "read_model_updated",
        auth_request_id=str(auth_request_id),
        status="PROCESSING",
        note="retry_attempt_recorded",
        sequence=sequence_number,
    )


async def update_to_expired(
    conn: asyncpg.Connection,
    auth_request_id: uuid.UUID,
    sequence_number: int,
) -> None:
    """Update read model to EXPIRED status.

    Called when AuthRequestExpired event is recorded (void detected before processing).

    Args:
        conn: Database connection (must be in transaction)
        auth_request_id: Authorization request ID
        sequence_number: Event sequence number
    """
    now = datetime.utcnow()

    await conn.execute(
        """
        UPDATE auth_request_state
        SET status = 'EXPIRED',
            completed_at = $2,
            updated_at = $3,
            last_event_sequence = $4
        WHERE auth_request_id = $1
        """,
        auth_request_id,
        now,
        now,
        sequence_number,
    )

    logger.info(
        "read_model_updated",
        auth_request_id=str(auth_request_id),
        status="EXPIRED",
        sequence=sequence_number,
    )


async def get_auth_request_details(
    conn: asyncpg.Connection,
    auth_request_id: uuid.UUID,
) -> asyncpg.Record | None:
    """Get auth request details from read model.

    Args:
        conn: Database connection
        auth_request_id: Authorization request ID

    Returns:
        Database record or None if not found
    """
    return await conn.fetchrow(
        """
        SELECT
            auth_request_id,
            restaurant_id,
            payment_token,
            status,
            amount_cents,
            currency,
            metadata,
            created_at,
            last_event_sequence
        FROM auth_request_state
        WHERE auth_request_id = $1
        """,
        auth_request_id,
    )


async def get_restaurant_config(
    conn: asyncpg.Connection,
    restaurant_id: uuid.UUID,
) -> asyncpg.Record | None:
    """Get restaurant payment processor configuration.

    Args:
        conn: Database connection
        restaurant_id: Restaurant ID

    Returns:
        Database record with processor_name and processor_config, or None if not found
    """
    return await conn.fetchrow(
        """
        SELECT
            restaurant_id,
            config_version,
            processor_name,
            processor_config,
            is_active
        FROM restaurant_payment_configs
        WHERE restaurant_id = $1 AND is_active = true
        """,
        restaurant_id,
    )

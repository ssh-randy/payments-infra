"""Transaction coordinator for atomic event + read model updates.

This module implements the critical requirement: Events and read model updates
MUST be in the same database transaction. If either fails, both rollback.
"""

import uuid
from typing import Any

import structlog

from auth_processor_worker.infrastructure import database, event_store, read_model

logger = structlog.get_logger()


class EventType:
    """Event type constants."""

    AUTH_ATTEMPT_STARTED = "AuthAttemptStarted"
    AUTH_RESPONSE_RECEIVED = "AuthResponseReceived"
    AUTH_ATTEMPT_FAILED = "AuthAttemptFailed"
    AUTH_REQUEST_EXPIRED = "AuthRequestExpired"


async def record_auth_attempt_started(
    auth_request_id: uuid.UUID,
    event_data: bytes,
    metadata: dict[str, Any] | None = None,
) -> int:
    """Record AuthAttemptStarted event and update status to PROCESSING.

    This is an atomic operation - both event and read model are written in
    the same transaction.

    Args:
        auth_request_id: Authorization request ID
        event_data: Serialized protobuf event data
        metadata: Optional metadata (worker_id, correlation_id, etc.)

    Returns:
        Sequence number of the recorded event

    Raises:
        Exception: If transaction fails, both event and read model rollback
    """
    async with database.transaction() as conn:
        # Get next sequence number within transaction
        sequence_number = await event_store.get_next_sequence_number(
            conn, auth_request_id
        )

        # Write event
        event_id = uuid.uuid4()
        await event_store.write_event(
            conn=conn,
            event_id=event_id,
            aggregate_id=auth_request_id,
            aggregate_type="auth_request",
            event_type=EventType.AUTH_ATTEMPT_STARTED,
            event_data=event_data,
            sequence_number=sequence_number,
            metadata=metadata,
        )

        # Update read model
        await read_model.update_to_processing(
            conn=conn,
            auth_request_id=auth_request_id,
            sequence_number=sequence_number,
        )

        # Transaction commits here (or rolls back on exception)

    logger.info(
        "auth_attempt_started_recorded",
        auth_request_id=str(auth_request_id),
        sequence=sequence_number,
    )

    return sequence_number


async def record_auth_response_authorized(
    auth_request_id: uuid.UUID,
    event_data: bytes,
    processor_auth_id: str,
    processor_name: str,
    authorized_amount_cents: int,
    authorization_code: str,
    metadata: dict[str, Any] | None = None,
) -> int:
    """Record AuthResponseReceived (AUTHORIZED) event and update status.

    This is an atomic operation - both event and read model are written in
    the same transaction.

    Args:
        auth_request_id: Authorization request ID
        event_data: Serialized protobuf event data
        processor_auth_id: Processor's authorization ID
        processor_name: Name of payment processor
        authorized_amount_cents: Authorized amount in cents
        authorization_code: Authorization code from processor
        metadata: Optional metadata

    Returns:
        Sequence number of the recorded event

    Raises:
        Exception: If transaction fails, both event and read model rollback
    """
    async with database.transaction() as conn:
        # Get next sequence number within transaction
        sequence_number = await event_store.get_next_sequence_number(
            conn, auth_request_id
        )

        # Write event
        event_id = uuid.uuid4()
        await event_store.write_event(
            conn=conn,
            event_id=event_id,
            aggregate_id=auth_request_id,
            aggregate_type="auth_request",
            event_type=EventType.AUTH_RESPONSE_RECEIVED,
            event_data=event_data,
            sequence_number=sequence_number,
            metadata=metadata,
        )

        # Update read model
        await read_model.update_to_authorized(
            conn=conn,
            auth_request_id=auth_request_id,
            sequence_number=sequence_number,
            processor_auth_id=processor_auth_id,
            processor_name=processor_name,
            authorized_amount_cents=authorized_amount_cents,
            authorization_code=authorization_code,
        )

        # Transaction commits here (or rolls back on exception)

    logger.info(
        "auth_response_authorized_recorded",
        auth_request_id=str(auth_request_id),
        processor_name=processor_name,
        sequence=sequence_number,
    )

    return sequence_number


async def record_auth_response_denied(
    auth_request_id: uuid.UUID,
    event_data: bytes,
    processor_name: str,
    denial_code: str,
    denial_reason: str,
    metadata: dict[str, Any] | None = None,
) -> int:
    """Record AuthResponseReceived (DENIED) event and update status.

    This is an atomic operation - both event and read model are written in
    the same transaction.

    Args:
        auth_request_id: Authorization request ID
        event_data: Serialized protobuf event data
        processor_name: Name of payment processor
        denial_code: Denial code from processor
        denial_reason: Human-readable denial reason
        metadata: Optional metadata

    Returns:
        Sequence number of the recorded event

    Raises:
        Exception: If transaction fails, both event and read model rollback
    """
    async with database.transaction() as conn:
        # Get next sequence number within transaction
        sequence_number = await event_store.get_next_sequence_number(
            conn, auth_request_id
        )

        # Write event
        event_id = uuid.uuid4()
        await event_store.write_event(
            conn=conn,
            event_id=event_id,
            aggregate_id=auth_request_id,
            aggregate_type="auth_request",
            event_type=EventType.AUTH_RESPONSE_RECEIVED,
            event_data=event_data,
            sequence_number=sequence_number,
            metadata=metadata,
        )

        # Update read model
        await read_model.update_to_denied(
            conn=conn,
            auth_request_id=auth_request_id,
            sequence_number=sequence_number,
            processor_name=processor_name,
            denial_code=denial_code,
            denial_reason=denial_reason,
        )

        # Transaction commits here (or rolls back on exception)

    logger.info(
        "auth_response_denied_recorded",
        auth_request_id=str(auth_request_id),
        denial_code=denial_code,
        sequence=sequence_number,
    )

    return sequence_number


async def record_auth_attempt_failed_terminal(
    auth_request_id: uuid.UUID,
    event_data: bytes,
    metadata: dict[str, Any] | None = None,
) -> int:
    """Record terminal AuthAttemptFailed event and update status to FAILED.

    This is an atomic operation - both event and read model are written in
    the same transaction.

    Args:
        auth_request_id: Authorization request ID
        event_data: Serialized protobuf event data (with is_retryable=False)
        metadata: Optional metadata

    Returns:
        Sequence number of the recorded event

    Raises:
        Exception: If transaction fails, both event and read model rollback
    """
    async with database.transaction() as conn:
        # Get next sequence number within transaction
        sequence_number = await event_store.get_next_sequence_number(
            conn, auth_request_id
        )

        # Write event
        event_id = uuid.uuid4()
        await event_store.write_event(
            conn=conn,
            event_id=event_id,
            aggregate_id=auth_request_id,
            aggregate_type="auth_request",
            event_type=EventType.AUTH_ATTEMPT_FAILED,
            event_data=event_data,
            sequence_number=sequence_number,
            metadata=metadata,
        )

        # Update read model to FAILED
        await read_model.update_to_failed(
            conn=conn,
            auth_request_id=auth_request_id,
            sequence_number=sequence_number,
        )

        # Transaction commits here (or rolls back on exception)

    logger.info(
        "auth_attempt_failed_terminal_recorded",
        auth_request_id=str(auth_request_id),
        sequence=sequence_number,
    )

    return sequence_number


async def record_auth_attempt_failed_retryable(
    auth_request_id: uuid.UUID,
    event_data: bytes,
    metadata: dict[str, Any] | None = None,
) -> int:
    """Record retryable AuthAttemptFailed event (status stays PROCESSING).

    This is an atomic operation - both event and read model are written in
    the same transaction.

    Args:
        auth_request_id: Authorization request ID
        event_data: Serialized protobuf event data (with is_retryable=True)
        metadata: Optional metadata

    Returns:
        Sequence number of the recorded event

    Raises:
        Exception: If transaction fails, both event and read model rollback
    """
    async with database.transaction() as conn:
        # Get next sequence number within transaction
        sequence_number = await event_store.get_next_sequence_number(
            conn, auth_request_id
        )

        # Write event
        event_id = uuid.uuid4()
        await event_store.write_event(
            conn=conn,
            event_id=event_id,
            aggregate_id=auth_request_id,
            aggregate_type="auth_request",
            event_type=EventType.AUTH_ATTEMPT_FAILED,
            event_data=event_data,
            sequence_number=sequence_number,
            metadata=metadata,
        )

        # Update retry attempt (status remains PROCESSING)
        await read_model.update_retry_attempt(
            conn=conn,
            auth_request_id=auth_request_id,
            sequence_number=sequence_number,
        )

        # Transaction commits here (or rolls back on exception)

    logger.info(
        "auth_attempt_failed_retryable_recorded",
        auth_request_id=str(auth_request_id),
        sequence=sequence_number,
    )

    return sequence_number


async def record_auth_request_expired(
    auth_request_id: uuid.UUID,
    event_data: bytes,
    metadata: dict[str, Any] | None = None,
) -> int:
    """Record AuthRequestExpired event and update status to EXPIRED.

    This is an atomic operation - both event and read model are written in
    the same transaction.

    Args:
        auth_request_id: Authorization request ID
        event_data: Serialized protobuf event data
        metadata: Optional metadata

    Returns:
        Sequence number of the recorded event

    Raises:
        Exception: If transaction fails, both event and read model rollback
    """
    async with database.transaction() as conn:
        # Get next sequence number within transaction
        sequence_number = await event_store.get_next_sequence_number(
            conn, auth_request_id
        )

        # Write event
        event_id = uuid.uuid4()
        await event_store.write_event(
            conn=conn,
            event_id=event_id,
            aggregate_id=auth_request_id,
            aggregate_type="auth_request",
            event_type=EventType.AUTH_REQUEST_EXPIRED,
            event_data=event_data,
            sequence_number=sequence_number,
            metadata=metadata,
        )

        # Update read model to EXPIRED
        await read_model.update_to_expired(
            conn=conn,
            auth_request_id=auth_request_id,
            sequence_number=sequence_number,
        )

        # Transaction commits here (or rolls back on exception)

    logger.info(
        "auth_request_expired_recorded",
        auth_request_id=str(auth_request_id),
        sequence=sequence_number,
    )

    return sequence_number

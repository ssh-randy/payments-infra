"""
Core auth request processing orchestration.

This module implements the main workflow that ties together all components:
- Distributed locking
- Void detection
- Token decryption
- Payment processor calls
- Atomic event/read model updates
- Error handling and retries
"""

import sys
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any

import structlog

# Add shared proto directory to Python path
_shared_proto_path = Path(__file__).parent.parent.parent.parent.parent.parent / "shared" / "python"
if str(_shared_proto_path) not in sys.path:
    sys.path.insert(0, str(_shared_proto_path))

from payments_proto.payments.v1 import authorization_pb2, events_pb2

from auth_processor_worker.clients.payment_token_client import PaymentTokenServiceClient
from auth_processor_worker.config import settings
from auth_processor_worker.infrastructure import database, event_store, locking, read_model, transaction
from auth_processor_worker.models.authorization import AuthStatus, PaymentData
from auth_processor_worker.models.exceptions import (
    Forbidden,
    ProcessorTimeout,
    TokenExpired,
    TokenNotFound,
)
from auth_processor_worker.processors.factory import get_processor

logger = structlog.get_logger(__name__)


class ProcessingResult:
    """Result of processing an auth request."""

    SUCCESS = "success"
    SKIPPED_LOCK_NOT_ACQUIRED = "skipped_lock_not_acquired"
    SKIPPED_VOID_DETECTED = "skipped_void_detected"
    TERMINAL_FAILURE = "terminal_failure"
    RETRYABLE_FAILURE = "retryable_failure"


async def process_auth_request(
    auth_request_id: uuid.UUID,
    worker_id: str,
    receive_count: int,
) -> str:
    """
    Process an authorization request - main orchestration function.

    This function implements the complete processing workflow:
    1. Acquire distributed lock
    2. Check for void event (race condition)
    3. Emit AuthAttemptStarted event + update read model
    4. Fetch auth request details and restaurant config
    5. Call Payment Token Service to decrypt token
    6. Call payment processor (Stripe)
    7. Atomically record result event + update read model
    8. Release lock

    Args:
        auth_request_id: Authorization request ID
        worker_id: Unique worker identifier
        receive_count: Number of times this message has been received (for retry logic)

    Returns:
        Processing result status (SUCCESS, SKIPPED_*, TERMINAL_FAILURE, RETRYABLE_FAILURE)

    Error Handling:
        - Lock not acquired → skip (another worker processing)
        - Void detected → write AuthRequestExpired + update to EXPIRED
        - Token errors (404, 410, 403) → terminal failure
        - Processor timeout → retryable failure (up to MAX_RETRIES)
        - Processor decline → write DENIED status (not a failure)
    """
    lock_acquired = False
    max_retries = settings.worker.max_retries

    try:
        # Step 1: Acquire distributed lock
        lock_acquired = await locking.acquire_lock(
            auth_request_id=auth_request_id,
            worker_id=worker_id,
            ttl_seconds=settings.worker.lock_ttl_seconds,
        )

        if not lock_acquired:
            logger.info(
                "processing_skipped_lock_not_acquired",
                auth_request_id=str(auth_request_id),
                worker_id=worker_id,
            )
            return ProcessingResult.SKIPPED_LOCK_NOT_ACQUIRED

        logger.info(
            "processing_started",
            auth_request_id=str(auth_request_id),
            worker_id=worker_id,
            receive_count=receive_count,
        )

        # Step 2: Check for void event (race condition)
        async with database.get_connection() as conn:
            void_detected = await event_store.check_for_void_event(
                conn=conn,
                aggregate_id=auth_request_id,
            )

        if void_detected:
            logger.info(
                "void_detected_before_processing",
                auth_request_id=str(auth_request_id),
                worker_id=worker_id,
            )

            # Record AuthRequestExpired event
            event_data = _create_expired_event(auth_request_id, worker_id)
            await transaction.record_auth_request_expired(
                auth_request_id=auth_request_id,
                event_data=event_data.SerializeToString(),
                metadata=_create_metadata(worker_id),
            )

            return ProcessingResult.SKIPPED_VOID_DETECTED

        # Step 3: Emit AuthAttemptStarted event + update read model
        event_data = _create_attempt_started_event(auth_request_id, worker_id)
        await transaction.record_auth_attempt_started(
            auth_request_id=auth_request_id,
            event_data=event_data.SerializeToString(),
            metadata=_create_metadata(worker_id),
        )

        # Step 4: Fetch auth request details and restaurant config
        async with database.get_connection() as conn:
            auth_details = await read_model.get_auth_request_details(
                conn=conn,
                auth_request_id=auth_request_id,
            )

            if not auth_details:
                logger.error(
                    "auth_request_not_found",
                    auth_request_id=str(auth_request_id),
                )
                # Record terminal failure
                await _record_terminal_failure(
                    auth_request_id=auth_request_id,
                    worker_id=worker_id,
                    error_message="Auth request not found in database",
                    error_code="NOT_FOUND",
                )
                return ProcessingResult.TERMINAL_FAILURE

            restaurant_config = await read_model.get_restaurant_config(
                conn=conn,
                restaurant_id=auth_details["restaurant_id"],
            )

            if not restaurant_config:
                logger.error(
                    "restaurant_config_not_found",
                    auth_request_id=str(auth_request_id),
                    restaurant_id=str(auth_details["restaurant_id"]),
                )
                # Record terminal failure
                await _record_terminal_failure(
                    auth_request_id=auth_request_id,
                    worker_id=worker_id,
                    error_message="Restaurant configuration not found",
                    error_code="CONFIG_NOT_FOUND",
                )
                return ProcessingResult.TERMINAL_FAILURE

        # Step 5: Call Payment Token Service to decrypt token
        try:
            payment_data = await _decrypt_payment_token(
                payment_token=auth_details["payment_token"],
                restaurant_id=str(auth_details["restaurant_id"]),
            )
        except (TokenNotFound, TokenExpired, Forbidden) as e:
            # Terminal errors - cannot recover
            logger.error(
                "token_service_terminal_error",
                auth_request_id=str(auth_request_id),
                error_type=type(e).__name__,
                error=str(e),
            )
            await _record_terminal_failure(
                auth_request_id=auth_request_id,
                worker_id=worker_id,
                error_message=str(e),
                error_code=type(e).__name__,
            )
            return ProcessingResult.TERMINAL_FAILURE

        except ProcessorTimeout as e:
            # Retryable error - Payment Token Service unavailable
            logger.warning(
                "token_service_timeout",
                auth_request_id=str(auth_request_id),
                receive_count=receive_count,
                max_retries=max_retries,
                error=str(e),
            )

            if receive_count >= max_retries:
                # Max retries exceeded - record terminal failure
                await _record_terminal_failure(
                    auth_request_id=auth_request_id,
                    worker_id=worker_id,
                    error_message=f"Max retries ({max_retries}) exceeded: {str(e)}",
                    error_code="MAX_RETRIES_EXCEEDED",
                )
                return ProcessingResult.TERMINAL_FAILURE
            else:
                # Record retryable failure - message will be retried
                await _record_retryable_failure(
                    auth_request_id=auth_request_id,
                    worker_id=worker_id,
                    error_message=str(e),
                    error_code="TOKEN_SERVICE_TIMEOUT",
                    retry_count=receive_count,
                )
                return ProcessingResult.RETRYABLE_FAILURE

        # Step 6: Call payment processor
        processor_name = restaurant_config["processor_name"]
        processor_config = restaurant_config["processor_config"]

        try:
            processor = get_processor(
                processor_name=processor_name,
                processor_config=processor_config,
            )

            result = await processor.authorize(
                payment_data=payment_data,
                amount_cents=auth_details["amount_cents"],
                currency=auth_details["currency"],
                config=processor_config,
            )

            # Step 7: Atomically record result event + update read model
            if result.status == AuthStatus.AUTHORIZED:
                # Success - record AUTHORIZED response
                event_data = _create_authorized_event(
                    auth_request_id=auth_request_id,
                    worker_id=worker_id,
                    result=result,
                )
                await transaction.record_auth_response_authorized(
                    auth_request_id=auth_request_id,
                    event_data=event_data.SerializeToString(),
                    processor_auth_id=result.processor_auth_id,
                    processor_name=result.processor_name,
                    authorized_amount_cents=result.authorized_amount_cents,
                    authorization_code=result.authorization_code or "",
                    metadata=_create_metadata(worker_id),
                )

                logger.info(
                    "processing_completed_authorized",
                    auth_request_id=str(auth_request_id),
                    processor_name=processor_name,
                    processor_auth_id=result.processor_auth_id,
                )

            else:  # AuthStatus.DENIED
                # Decline - record DENIED response (not a failure)
                event_data = _create_denied_event(
                    auth_request_id=auth_request_id,
                    worker_id=worker_id,
                    result=result,
                )
                await transaction.record_auth_response_denied(
                    auth_request_id=auth_request_id,
                    event_data=event_data.SerializeToString(),
                    processor_name=result.processor_name,
                    denial_code=result.denial_code or "",
                    denial_reason=result.denial_reason or "",
                    metadata=_create_metadata(worker_id),
                )

                logger.info(
                    "processing_completed_denied",
                    auth_request_id=str(auth_request_id),
                    processor_name=processor_name,
                    denial_code=result.denial_code,
                )

            return ProcessingResult.SUCCESS

        except ProcessorTimeout as e:
            # Retryable error - Processor unavailable
            logger.warning(
                "processor_timeout",
                auth_request_id=str(auth_request_id),
                processor_name=processor_name,
                receive_count=receive_count,
                max_retries=max_retries,
                error=str(e),
            )

            if receive_count >= max_retries:
                # Max retries exceeded - record terminal failure
                await _record_terminal_failure(
                    auth_request_id=auth_request_id,
                    worker_id=worker_id,
                    error_message=f"Max retries ({max_retries}) exceeded: {str(e)}",
                    error_code="MAX_RETRIES_EXCEEDED",
                )
                return ProcessingResult.TERMINAL_FAILURE
            else:
                # Record retryable failure - message will be retried
                await _record_retryable_failure(
                    auth_request_id=auth_request_id,
                    worker_id=worker_id,
                    error_message=str(e),
                    error_code="PROCESSOR_TIMEOUT",
                    retry_count=receive_count,
                )
                return ProcessingResult.RETRYABLE_FAILURE

    except Exception as e:
        # Unexpected error - log and record terminal failure
        logger.error(
            "processing_unexpected_error",
            auth_request_id=str(auth_request_id),
            worker_id=worker_id,
            error=str(e),
            exc_info=True,
        )

        try:
            await _record_terminal_failure(
                auth_request_id=auth_request_id,
                worker_id=worker_id,
                error_message=f"Unexpected error: {str(e)}",
                error_code="UNEXPECTED_ERROR",
            )
        except Exception as record_error:
            logger.error(
                "failed_to_record_terminal_failure",
                auth_request_id=str(auth_request_id),
                error=str(record_error),
                exc_info=True,
            )

        return ProcessingResult.TERMINAL_FAILURE

    finally:
        # Step 8: Always release lock (even on errors)
        if lock_acquired:
            try:
                await locking.release_lock(
                    auth_request_id=auth_request_id,
                    worker_id=worker_id,
                )
                logger.info(
                    "lock_released",
                    auth_request_id=str(auth_request_id),
                    worker_id=worker_id,
                )
            except Exception as e:
                logger.error(
                    "lock_release_failed",
                    auth_request_id=str(auth_request_id),
                    worker_id=worker_id,
                    error=str(e),
                    exc_info=True,
                )


# Helper functions for creating events

def _create_metadata(worker_id: str) -> dict[str, Any]:
    """Create metadata dictionary for events."""
    return {
        "worker_id": worker_id,
        "timestamp": datetime.utcnow().isoformat(),
    }


def _create_attempt_started_event(
    auth_request_id: uuid.UUID,
    worker_id: str,
) -> events_pb2.AuthAttemptStarted:
    """Create AuthAttemptStarted event."""
    return events_pb2.AuthAttemptStarted(
        auth_request_id=str(auth_request_id),
        worker_id=worker_id,
        restaurant_payment_config_version="",  # Optional field
        started_at=int(datetime.utcnow().timestamp()),
    )


def _create_expired_event(
    auth_request_id: uuid.UUID,
    worker_id: str,
) -> events_pb2.AuthRequestExpired:
    """Create AuthRequestExpired event."""
    return events_pb2.AuthRequestExpired(
        auth_request_id=str(auth_request_id),
        reason="Void detected before processing could begin",
        expired_at=int(datetime.utcnow().timestamp()),
    )


def _create_authorized_event(
    auth_request_id: uuid.UUID,
    worker_id: str,
    result: Any,  # AuthorizationResult
) -> events_pb2.AuthResponseReceived:
    """Create AuthResponseReceived event for AUTHORIZED status."""
    # Create the nested AuthorizationResult protobuf
    auth_result_proto = authorization_pb2.AuthorizationResult(
        processor_auth_id=result.processor_auth_id or "",
        processor_name=result.processor_name,
        authorized_amount_cents=result.authorized_amount_cents or 0,
        currency=result.currency or "",
        authorization_code=result.authorization_code or "",
        authorized_at=int(result.authorized_at.timestamp()) if result.authorized_at else int(datetime.utcnow().timestamp()),
    )

    return events_pb2.AuthResponseReceived(
        auth_request_id=str(auth_request_id),
        status=authorization_pb2.AUTH_STATUS_AUTHORIZED,
        result=auth_result_proto,
        received_at=int(datetime.utcnow().timestamp()),
    )


def _create_denied_event(
    auth_request_id: uuid.UUID,
    worker_id: str,
    result: Any,  # AuthorizationResult
) -> events_pb2.AuthResponseReceived:
    """Create AuthResponseReceived event for DENIED status."""
    # Create the nested AuthorizationResult protobuf
    auth_result_proto = authorization_pb2.AuthorizationResult(
        processor_name=result.processor_name,
        denial_code=result.denial_code or "",
        denial_reason=result.denial_reason or "",
    )

    return events_pb2.AuthResponseReceived(
        auth_request_id=str(auth_request_id),
        status=authorization_pb2.AUTH_STATUS_DENIED,
        result=auth_result_proto,
        received_at=int(datetime.utcnow().timestamp()),
    )


async def _decrypt_payment_token(
    payment_token: str,
    restaurant_id: str,
) -> PaymentData:
    """
    Decrypt payment token using Payment Token Service.

    Returns:
        PaymentData with decrypted card information

    Raises:
        TokenNotFound: Token doesn't exist (terminal error)
        TokenExpired: Token expired (terminal error)
        Forbidden: Unauthorized access (terminal error)
        ProcessorTimeout: Service unavailable (retryable error)
    """
    client = PaymentTokenServiceClient(
        base_url=settings.payment_token_service.base_url,
        service_auth_token=settings.payment_token_service.service_auth_token,
        timeout_seconds=settings.payment_token_service.timeout_seconds,
    )

    try:
        payment_data_proto = await client.decrypt(
            payment_token=payment_token,
            restaurant_id=restaurant_id,
            requesting_service="auth-processor-worker",
        )

        # Convert protobuf to domain model
        # Note: billing_zip field exists in domain model but not in protobuf, defaults to None
        return PaymentData(
            card_number=payment_data_proto.card_number,
            exp_month=payment_data_proto.exp_month,
            exp_year=payment_data_proto.exp_year,
            cvv=payment_data_proto.cvv,
            cardholder_name=payment_data_proto.cardholder_name,
        )
    finally:
        await client.close()


async def _record_terminal_failure(
    auth_request_id: uuid.UUID,
    worker_id: str,
    error_message: str,
    error_code: str,
) -> None:
    """Record a terminal failure event (not retryable)."""
    event_data = events_pb2.AuthAttemptFailed(
        auth_request_id=str(auth_request_id),
        error_message=error_message,
        error_code=error_code,
        is_retryable=False,
        failed_at=int(datetime.utcnow().timestamp()),
    )

    await transaction.record_auth_attempt_failed_terminal(
        auth_request_id=auth_request_id,
        event_data=event_data.SerializeToString(),
        metadata=_create_metadata(worker_id),
    )


async def _record_retryable_failure(
    auth_request_id: uuid.UUID,
    worker_id: str,
    error_message: str,
    error_code: str,
    retry_count: int,
) -> None:
    """Record a retryable failure event (status stays PROCESSING)."""
    event_data = events_pb2.AuthAttemptFailed(
        auth_request_id=str(auth_request_id),
        error_message=error_message,
        error_code=error_code,
        is_retryable=True,
        retry_count=retry_count,
        failed_at=int(datetime.utcnow().timestamp()),
    )

    await transaction.record_auth_attempt_failed_retryable(
        auth_request_id=auth_request_id,
        event_data=event_data.SerializeToString(),
        metadata=_create_metadata(worker_id),
    )

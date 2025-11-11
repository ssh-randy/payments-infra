"""POST /authorize endpoint implementation."""

import asyncio
import uuid

import structlog
from fastapi import APIRouter, HTTPException, Request, Response
from fastapi.responses import Response as FastAPIResponse

from payments.v1.authorization_pb2 import (
    AuthorizeRequest,
    AuthorizeResponse,
    AuthStatus,
)

from authorization_api.config import settings
from authorization_api.domain.events import (
    create_auth_request_created_event,
    create_auth_request_queued_message,
)
from authorization_api.domain.read_models import (
    create_auth_request_state,
    get_auth_request_state,
    build_authorization_result,
    map_status_to_proto,
)
from authorization_api.infrastructure.database import transaction
from authorization_api.infrastructure.event_store import write_event
from authorization_api.infrastructure.outbox import write_outbox_message

logger = structlog.get_logger()

router = APIRouter()


async def check_idempotency(
    conn, idempotency_key: str, restaurant_id: uuid.UUID
) -> uuid.UUID | None:
    """Check if idempotency key already exists.

    Args:
        conn: Database connection
        idempotency_key: Client-provided idempotency key
        restaurant_id: Restaurant UUID

    Returns:
        Existing auth_request_id if found, None otherwise
    """
    result = await conn.fetchrow(
        """
        SELECT auth_request_id
        FROM auth_idempotency_keys
        WHERE idempotency_key = $1 AND restaurant_id = $2
        """,
        idempotency_key,
        restaurant_id,
    )

    if result:
        logger.info(
            "idempotency_key_found",
            idempotency_key=idempotency_key,
            auth_request_id=str(result["auth_request_id"]),
        )
        return result["auth_request_id"]

    return None


async def write_idempotency_key(
    conn, idempotency_key: str, auth_request_id: uuid.UUID, restaurant_id: uuid.UUID
) -> None:
    """Write idempotency key to database.

    Args:
        conn: Database connection (must be in transaction)
        idempotency_key: Client-provided idempotency key
        auth_request_id: Authorization request ID
        restaurant_id: Restaurant UUID
    """
    await conn.execute(
        """
        INSERT INTO auth_idempotency_keys (
            idempotency_key,
            auth_request_id,
            restaurant_id,
            created_at,
            expires_at
        )
        VALUES ($1, $2, $3, NOW(), NOW() + INTERVAL '24 hours')
        """,
        idempotency_key,
        auth_request_id,
        restaurant_id,
    )

    logger.info(
        "idempotency_key_created",
        idempotency_key=idempotency_key,
        auth_request_id=str(auth_request_id),
    )


async def poll_for_completion(
    auth_request_id: uuid.UUID,
    max_duration_seconds: int,
    poll_interval_ms: int,
) -> tuple[str, dict | None]:
    """Poll read model for authorization completion.

    Args:
        auth_request_id: Authorization request ID
        max_duration_seconds: Maximum time to poll (default 5s)
        poll_interval_ms: Poll interval in milliseconds (default 100ms)

    Returns:
        Tuple of (status, result_dict)
    """
    from authorization_api.infrastructure.database import get_connection

    poll_interval_seconds = poll_interval_ms / 1000.0
    iterations = int(max_duration_seconds / poll_interval_seconds)

    for _ in range(iterations):
        await asyncio.sleep(poll_interval_seconds)

        async with get_connection() as conn:
            record = await get_auth_request_state(conn, auth_request_id)

            if not record:
                logger.error(
                    "auth_request_disappeared",
                    auth_request_id=str(auth_request_id),
                )
                break

            status = record["status"]

            # Check if completed
            if status in ("AUTHORIZED", "DENIED", "FAILED"):
                logger.info(
                    "auth_request_completed_during_poll",
                    auth_request_id=str(auth_request_id),
                    status=status,
                )
                return status, dict(record)

    # Timeout - still processing
    logger.info(
        "auth_request_poll_timeout",
        auth_request_id=str(auth_request_id),
        max_duration_seconds=max_duration_seconds,
    )
    return "PROCESSING", None


@router.post("/v1/authorize")
async def post_authorize(request: Request) -> Response:
    """Create an authorization request.

    Implements the transactional outbox pattern:
    1. Check idempotency
    2. Atomic transaction:
       - Write event to payment_events
       - Write read model to auth_request_state
       - Write to outbox table
       - Write idempotency key
    3. Poll for up to 5 seconds
    4. Return result or 202 Accepted

    Args:
        request: FastAPI request object

    Returns:
        Protobuf response (200 or 202)
    """
    # Parse protobuf request
    body = await request.body()
    auth_request = AuthorizeRequest()
    auth_request.ParseFromString(body)

    # Validate required fields
    if not auth_request.payment_token:
        raise HTTPException(status_code=400, detail="payment_token is required")
    if not auth_request.restaurant_id:
        raise HTTPException(status_code=400, detail="restaurant_id is required")
    if not auth_request.idempotency_key:
        raise HTTPException(status_code=400, detail="idempotency_key is required")
    if auth_request.amount_cents <= 0:
        raise HTTPException(status_code=400, detail="amount_cents must be positive")
    if not auth_request.currency:
        raise HTTPException(status_code=400, detail="currency is required")

    # Parse restaurant_id as UUID
    try:
        restaurant_id = uuid.UUID(auth_request.restaurant_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid restaurant_id format")

    logger.info(
        "authorize_request_received",
        payment_token=auth_request.payment_token,
        restaurant_id=str(restaurant_id),
        amount_cents=auth_request.amount_cents,
        currency=auth_request.currency,
        idempotency_key=auth_request.idempotency_key,
    )

    # Check idempotency (outside transaction for efficiency)
    async with transaction() as conn:
        existing_auth_request_id = await check_idempotency(
            conn, auth_request.idempotency_key, restaurant_id
        )

        if existing_auth_request_id:
            # Return existing request status
            logger.info(
                "idempotent_request_returning_existing",
                auth_request_id=str(existing_auth_request_id),
            )

            # Get current state
            record = await get_auth_request_state(conn, existing_auth_request_id)

            if not record:
                raise HTTPException(
                    status_code=500, detail="Idempotency key exists but request not found"
                )

            status = map_status_to_proto(record["status"])
            response = AuthorizeResponse(
                auth_request_id=str(existing_auth_request_id),
                status=status,
            )

            # Add result if completed
            if record["status"] in ("AUTHORIZED", "DENIED"):
                result = build_authorization_result(record)
                if result:
                    response.result.CopyFrom(result)

            # Add status URL if still processing
            if record["status"] in ("PENDING", "PROCESSING"):
                response.status_url = (
                    f"/v1/authorize/{existing_auth_request_id}/status"
                )

            return FastAPIResponse(
                content=response.SerializeToString(),
                media_type="application/x-protobuf",
                status_code=200 if status in (AuthStatus.AUTH_STATUS_AUTHORIZED, AuthStatus.AUTH_STATUS_DENIED, AuthStatus.AUTH_STATUS_FAILED) else 202,
            )

    # Generate new auth_request_id
    auth_request_id = uuid.uuid4()
    event_id = uuid.uuid4()

    # Convert metadata to dict
    metadata_dict = dict(auth_request.metadata) if auth_request.metadata else None

    # ATOMIC TRANSACTION: Write event + read model + outbox + idempotency
    async with transaction() as conn:
        logger.info(
            "starting_atomic_transaction",
            auth_request_id=str(auth_request_id),
        )

        # 1. Write event to event store
        event_data = create_auth_request_created_event(
            auth_request_id=auth_request_id,
            payment_token=auth_request.payment_token,
            restaurant_id=restaurant_id,
            amount_cents=auth_request.amount_cents,
            currency=auth_request.currency,
            metadata=metadata_dict,
        )

        await write_event(
            conn=conn,
            event_id=event_id,
            aggregate_id=auth_request_id,
            aggregate_type="auth_request",
            event_type="AuthRequestCreated",
            event_data=event_data,
            sequence_number=1,  # First event
            metadata={"idempotency_key": auth_request.idempotency_key},
        )

        # 2. Write read model
        await create_auth_request_state(
            conn=conn,
            auth_request_id=auth_request_id,
            restaurant_id=restaurant_id,
            payment_token=auth_request.payment_token,
            amount_cents=auth_request.amount_cents,
            currency=auth_request.currency,
            metadata=metadata_dict,
        )

        # 3. Write to outbox (for reliable SQS delivery)
        queue_message = create_auth_request_queued_message(
            auth_request_id=auth_request_id,
            restaurant_id=restaurant_id,
        )

        await write_outbox_message(
            conn=conn,
            aggregate_id=auth_request_id,
            message_type="auth_request_queued",
            payload=queue_message,
        )

        # 4. Write idempotency key
        await write_idempotency_key(
            conn=conn,
            idempotency_key=auth_request.idempotency_key,
            auth_request_id=auth_request_id,
            restaurant_id=restaurant_id,
        )

        logger.info(
            "atomic_transaction_committed",
            auth_request_id=str(auth_request_id),
        )

    # 5. Poll for completion (5-second fast path)
    final_status, result_record = await poll_for_completion(
        auth_request_id=auth_request_id,
        max_duration_seconds=settings.max_poll_duration_seconds,
        poll_interval_ms=settings.poll_interval_ms,
    )

    # Build response
    response = AuthorizeResponse(
        auth_request_id=str(auth_request_id),
        status=map_status_to_proto(final_status),
    )

    # Fast path: completed within 5 seconds
    if final_status in ("AUTHORIZED", "DENIED", "FAILED") and result_record:
        logger.info(
            "authorize_fast_path_completed",
            auth_request_id=str(auth_request_id),
            status=final_status,
        )

        if final_status in ("AUTHORIZED", "DENIED"):
            # result_record is a dict, create a Record-like object
            class DictRecord(dict):
                def __getitem__(self, key):
                    return super().get(key)

            record_obj = DictRecord(result_record)
            result = build_authorization_result(record_obj)
            if result:
                response.result.CopyFrom(result)

        return FastAPIResponse(
            content=response.SerializeToString(),
            media_type="application/x-protobuf",
            status_code=200,
        )

    # Slow path: still processing after 5 seconds
    logger.info(
        "authorize_slow_path_timeout",
        auth_request_id=str(auth_request_id),
    )

    response.status_url = f"/v1/authorize/{auth_request_id}/status"

    return FastAPIResponse(
        content=response.SerializeToString(),
        media_type="application/x-protobuf",
        status_code=202,
    )

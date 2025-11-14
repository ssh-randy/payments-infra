"""POST /authorize endpoint implementation."""

import asyncio
import json
import uuid

import structlog
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse

from authorization_api.api.models import (
    AuthorizeRequestJSON,
    AuthorizeResponseJSON,
    AuthorizationResultJSON,
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


def _build_result_dict(record) -> dict:
    """Build authorization result dictionary from database record.

    Args:
        record: Database record with authorization result fields

    Returns:
        Dictionary with authorization result data
    """
    result = {}

    # Add fields if present
    if record.get("processor_name"):
        result["processor_name"] = record["processor_name"]
    if record.get("processor_auth_id"):
        result["processor_auth_id"] = record["processor_auth_id"]
    if record.get("processor_auth_code"):
        result["processor_auth_code"] = record["processor_auth_code"]
    if record.get("processor_decline_code"):
        result["processor_decline_code"] = record["processor_decline_code"]
    if record.get("decline_reason"):
        result["decline_reason"] = record["decline_reason"]
    if record.get("network_status"):
        result["network_status"] = record["network_status"]
    if record.get("risk_score") is not None:
        result["risk_score"] = record["risk_score"]
    if record.get("error_message"):
        result["error_message"] = record["error_message"]

    return result if result else None


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
async def post_authorize(request: Request) -> JSONResponse:
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
        JSON response (200 or 202)
    """
    # Parse JSON request
    body = await request.body()
    try:
        json_data = json.loads(body)
        auth_request = AuthorizeRequestJSON(**json_data)
    except Exception as e:
        logger.error(f"Failed to parse JSON request: {str(e)}")
        raise HTTPException(
            status_code=400,
            detail=f"Invalid JSON request: {str(e)}",
        )

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

            status = record["status"]
            response_data = {
                "auth_request_id": str(existing_auth_request_id),
                "status": status,
            }

            # Add result if completed
            if status in ("AUTHORIZED", "DENIED"):
                result_data = _build_result_dict(record)
                if result_data:
                    response_data["result"] = result_data

            # Add status URL if still processing
            if status in ("PENDING", "PROCESSING"):
                response_data["status_url"] = f"/v1/authorize/{existing_auth_request_id}/status"

            http_status = 200 if status in ("AUTHORIZED", "DENIED", "FAILED") else 202
            return JSONResponse(
                content=response_data,
                status_code=http_status,
            )

    # Generate new auth_request_id
    auth_request_id = uuid.uuid4()
    event_id = uuid.uuid4()

    # Convert metadata to dict
    metadata_dict = auth_request.metadata if auth_request.metadata else None

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
    response_data = {
        "auth_request_id": str(auth_request_id),
        "status": final_status,
    }

    # Fast path: completed within 5 seconds
    if final_status in ("AUTHORIZED", "DENIED", "FAILED") and result_record:
        logger.info(
            "authorize_fast_path_completed",
            auth_request_id=str(auth_request_id),
            status=final_status,
        )

        if final_status in ("AUTHORIZED", "DENIED"):
            result_data = _build_result_dict(result_record)
            if result_data:
                response_data["result"] = result_data

        return JSONResponse(
            content=response_data,
            status_code=200,
        )

    # Slow path: still processing after 5 seconds
    logger.info(
        "authorize_slow_path_timeout",
        auth_request_id=str(auth_request_id),
    )

    response_data["status_url"] = f"/v1/authorize/{auth_request_id}/status"

    return JSONResponse(
        content=response_data,
        status_code=202,
    )

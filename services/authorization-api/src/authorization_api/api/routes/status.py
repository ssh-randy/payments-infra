"""GET /authorize/{id}/status endpoint implementation."""

import uuid

import asyncpg
import structlog
from fastapi import APIRouter, HTTPException, Response
from fastapi.responses import Response as FastAPIResponse

from payments.v1.authorization_pb2 import GetAuthStatusResponse

from authorization_api.domain.read_models import (
    get_auth_request_state,
    build_authorization_result,
    map_status_to_proto,
)
from authorization_api.infrastructure.database import get_connection

logger = structlog.get_logger()

router = APIRouter()


async def build_status_response(
    conn: asyncpg.Connection,
    auth_request_id: uuid.UUID,
    restaurant_id: uuid.UUID,
) -> GetAuthStatusResponse:
    """Build status response from database record.

    Args:
        conn: Database connection
        auth_request_id: Authorization request UUID
        restaurant_id: Restaurant UUID

    Returns:
        GetAuthStatusResponse protobuf

    Raises:
        HTTPException: 404 if not found or restaurant mismatch
    """
    record = await get_auth_request_state(conn, auth_request_id)

    # Check if auth request exists
    if not record:
        logger.warning(
            "auth_request_not_found",
            auth_request_id=str(auth_request_id),
        )
        raise HTTPException(status_code=404, detail="Auth request not found")

    # Verify restaurant_id matches (security check)
    if record["restaurant_id"] != restaurant_id:
        logger.warning(
            "restaurant_id_mismatch",
            auth_request_id=str(auth_request_id),
            requested_restaurant_id=str(restaurant_id),
            actual_restaurant_id=str(record["restaurant_id"]),
        )
        raise HTTPException(status_code=404, detail="Auth request not found")

    # Build protobuf response
    response = GetAuthStatusResponse(
        auth_request_id=str(auth_request_id),
        status=map_status_to_proto(record["status"]),
        created_at=int(record["created_at"].timestamp()),
        updated_at=int(record["updated_at"].timestamp()),
    )

    # Add authorization result if completed (AUTHORIZED or DENIED)
    if record["status"] in ("AUTHORIZED", "DENIED"):
        result = build_authorization_result(record)
        if result:
            response.result.CopyFrom(result)

    logger.info(
        "get_status_success",
        auth_request_id=str(auth_request_id),
        status=record["status"],
    )

    return response


@router.get("/v1/authorize/{auth_request_id}/status")
async def get_status(auth_request_id: str, restaurant_id: str) -> Response:
    """Get authorization request status.

    Reads from the auth_request_state read model to return current status.
    This is a read-only operation - no transaction needed.

    Args:
        auth_request_id: Authorization request UUID (path parameter)
        restaurant_id: Restaurant UUID (query parameter)

    Returns:
        GetAuthStatusResponse protobuf with current status

    Raises:
        HTTPException: 400 if invalid UUIDs, 404 if not found or restaurant mismatch
    """
    # Parse and validate UUIDs
    try:
        auth_request_uuid = uuid.UUID(auth_request_id)
    except ValueError:
        raise HTTPException(
            status_code=400, detail="Invalid auth_request_id format"
        )

    try:
        restaurant_uuid = uuid.UUID(restaurant_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid restaurant_id format")

    logger.info(
        "get_status_request",
        auth_request_id=auth_request_id,
        restaurant_id=restaurant_id,
    )

    # Query read model (simple SELECT - no transaction needed)
    async with get_connection() as conn:
        response = await build_status_response(
            conn, auth_request_uuid, restaurant_uuid
        )

        return FastAPIResponse(
            content=response.SerializeToString(),
            media_type="application/x-protobuf",
            status_code=200,
        )

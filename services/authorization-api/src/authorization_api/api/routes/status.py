"""GET /authorize/{id}/status endpoint implementation."""

import uuid

import asyncpg
import structlog
from fastapi import APIRouter, HTTPException
from fastapi.responses import JSONResponse

from authorization_api.domain.read_models import get_auth_request_state
from authorization_api.infrastructure.database import get_connection

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


async def build_status_response(
    conn: asyncpg.Connection,
    auth_request_id: uuid.UUID,
    restaurant_id: uuid.UUID,
) -> dict:
    """Build status response from database record.

    Args:
        conn: Database connection
        auth_request_id: Authorization request UUID
        restaurant_id: Restaurant UUID

    Returns:
        Dictionary with status response data

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

    # Build JSON response
    response = {
        "auth_request_id": str(auth_request_id),
        "status": record["status"],
        "created_at": int(record["created_at"].timestamp()),
        "updated_at": int(record["updated_at"].timestamp()),
    }

    # Add authorization result if completed (AUTHORIZED or DENIED)
    if record["status"] in ("AUTHORIZED", "DENIED"):
        result = _build_result_dict(record)
        if result:
            response["result"] = result

    logger.info(
        "get_status_success",
        auth_request_id=str(auth_request_id),
        status=record["status"],
    )

    return response


@router.get("/v1/authorize/{auth_request_id}/status")
async def get_status(auth_request_id: str, restaurant_id: str) -> JSONResponse:
    """Get authorization request status.

    Reads from the auth_request_state read model to return current status.
    This is a read-only operation - no transaction needed.

    Args:
        auth_request_id: Authorization request UUID (path parameter)
        restaurant_id: Restaurant UUID (query parameter)

    Returns:
        JSON response with current status

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

        return JSONResponse(
            content=response,
            status_code=200,
        )

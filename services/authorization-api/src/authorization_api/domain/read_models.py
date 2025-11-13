"""Read model helpers for auth_request_state table."""

import json
import uuid
from datetime import datetime
from typing import Any

import asyncpg
import structlog

from payments.v1.authorization_pb2 import (
    AuthStatus,
    AuthorizationResult,
    GetAuthStatusResponse,
)

logger = structlog.get_logger()


async def create_auth_request_state(
    conn: asyncpg.Connection,
    auth_request_id: uuid.UUID,
    restaurant_id: uuid.UUID,
    payment_token: str,
    amount_cents: int,
    currency: str,
    metadata: dict[str, str] | None = None,
) -> None:
    """Create initial auth request state in read model.

    Args:
        conn: Database connection (must be in transaction)
        auth_request_id: Authorization request ID
        restaurant_id: Restaurant UUID
        payment_token: Payment token
        amount_cents: Amount in cents
        currency: ISO currency code
        metadata: Optional metadata
    """
    metadata_json = json.dumps(metadata or {})
    now = datetime.utcnow()

    await conn.execute(
        """
        INSERT INTO auth_request_state (
            auth_request_id,
            restaurant_id,
            payment_token,
            status,
            amount_cents,
            currency,
            created_at,
            updated_at,
            metadata,
            last_event_sequence
        )
        VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10)
        """,
        auth_request_id,
        restaurant_id,
        payment_token,
        "PENDING",
        amount_cents,
        currency,
        now,
        now,
        metadata_json,
        1,  # First event sequence
    )

    logger.info(
        "auth_request_state_created",
        auth_request_id=str(auth_request_id),
        restaurant_id=str(restaurant_id),
        status="PENDING",
    )


async def get_auth_request_state(
    conn: asyncpg.Connection,
    auth_request_id: uuid.UUID,
) -> asyncpg.Record | None:
    """Get auth request state from read model.

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
            processor_auth_id,
            processor_name,
            authorized_amount_cents,
            authorization_code,
            denial_code,
            denial_reason,
            created_at,
            updated_at,
            completed_at,
            metadata,
            last_event_sequence
        FROM auth_request_state
        WHERE auth_request_id = $1
        """,
        auth_request_id,
    )


def build_authorization_result(record: asyncpg.Record) -> AuthorizationResult | None:
    """Build AuthorizationResult protobuf from database record.

    Args:
        record: Database record from auth_request_state

    Returns:
        AuthorizationResult protobuf or None if not completed
    """
    if record["status"] not in ("AUTHORIZED", "DENIED"):
        return None

    result = AuthorizationResult()

    if record["processor_auth_id"]:
        result.processor_auth_id = record["processor_auth_id"]
    if record["processor_name"]:
        result.processor_name = record["processor_name"]
    if record["authorized_amount_cents"]:
        result.authorized_amount_cents = record["authorized_amount_cents"]
    if record["currency"]:
        result.currency = record["currency"]
    if record["authorization_code"]:
        result.authorization_code = record["authorization_code"]
    if record["completed_at"]:
        result.authorized_at = int(record["completed_at"].timestamp())

    # Denial information
    if record["denial_code"]:
        result.denial_code = record["denial_code"]
    if record["denial_reason"]:
        result.denial_reason = record["denial_reason"]

    return result


def map_status_to_proto(status_str: str) -> AuthStatus:
    """Map database status string to protobuf enum.

    Args:
        status_str: Status from database

    Returns:
        AuthStatus enum value
    """
    status_map = {
        "PENDING": AuthStatus.AUTH_STATUS_PENDING,
        "PROCESSING": AuthStatus.AUTH_STATUS_PROCESSING,
        "AUTHORIZED": AuthStatus.AUTH_STATUS_AUTHORIZED,
        "DENIED": AuthStatus.AUTH_STATUS_DENIED,
        "FAILED": AuthStatus.AUTH_STATUS_FAILED,
        "VOIDED": AuthStatus.AUTH_STATUS_VOIDED,
        "EXPIRED": AuthStatus.AUTH_STATUS_EXPIRED,
    }
    return status_map.get(status_str, AuthStatus.AUTH_STATUS_UNSPECIFIED)

"""Integration tests for GET /authorize/{id}/status endpoint with real database.

These tests verify:
- Reading from auth_request_state table
- Restaurant ID validation
- Authorization result building for completed requests
- 404 handling for not found and mismatched restaurant IDs
"""

import uuid
from datetime import datetime

import pytest
from payments_proto.payments.v1.authorization_pb2 import AuthStatus, GetAuthStatusResponse

from authorization_api.api.routes.status import build_status_response
from authorization_api.domain.read_models import create_auth_request_state
from fastapi import HTTPException


@pytest.mark.asyncio
async def test_get_status_pending_request(
    db_conn, test_restaurant_id, test_payment_token
):
    """Test GET /status returns PENDING status from database."""
    auth_request_id = uuid.uuid4()

    # Create auth request state in database (PENDING status)
    await create_auth_request_state(
        conn=db_conn,
        auth_request_id=auth_request_id,
        restaurant_id=test_restaurant_id,
        payment_token=test_payment_token,
        amount_cents=1050,
        currency="USD",
        metadata={"order_id": "order-123"},
    )

    # Get status
    status_response = await build_status_response(
        conn=db_conn,
        auth_request_id=auth_request_id,
        restaurant_id=test_restaurant_id,
    )

    # Verify response
    assert status_response.auth_request_id == str(auth_request_id)
    assert status_response.status == AuthStatus.AUTH_STATUS_PENDING
    assert status_response.created_at > 0
    assert status_response.updated_at > 0
    # No result for PENDING status
    assert not status_response.HasField("result")


@pytest.mark.asyncio
async def test_get_status_authorized_with_result(
    db_conn, test_restaurant_id, test_payment_token
):
    """Test GET /status returns AUTHORIZED with complete authorization result."""
    auth_request_id = uuid.uuid4()

    # Create auth request state
    await create_auth_request_state(
        conn=db_conn,
        auth_request_id=auth_request_id,
        restaurant_id=test_restaurant_id,
        payment_token=test_payment_token,
        amount_cents=1050,
        currency="USD",
    )

    # Simulate authorization completion (update status to AUTHORIZED)
    await db_conn.execute(
        """
        UPDATE auth_request_state
        SET status = $1,
            processor_auth_id = $2,
            processor_name = $3,
            authorized_amount_cents = $4,
            authorization_code = $5,
            completed_at = $6,
            updated_at = $7,
            last_event_sequence = 2
        WHERE auth_request_id = $8
        """,
        "AUTHORIZED",
        "ch_stripe_123",
        "stripe",
        1050,
        "AUTH-12345",
        datetime.utcnow(),
        datetime.utcnow(),
        auth_request_id,
    )

    # Get status
    status_response = await build_status_response(
        conn=db_conn,
        auth_request_id=auth_request_id,
        restaurant_id=test_restaurant_id,
    )

    # Verify response
    assert status_response.status == AuthStatus.AUTH_STATUS_AUTHORIZED
    assert status_response.HasField("result")
    assert status_response.result.processor_auth_id == "ch_stripe_123"
    assert status_response.result.processor_name == "stripe"
    assert status_response.result.authorized_amount_cents == 1050
    assert status_response.result.currency == "USD"
    assert status_response.result.authorization_code == "AUTH-12345"
    assert status_response.result.authorized_at > 0


@pytest.mark.asyncio
async def test_get_status_denied_with_result(
    db_conn, test_restaurant_id, test_payment_token
):
    """Test GET /status returns DENIED with denial information."""
    auth_request_id = uuid.uuid4()

    # Create auth request state
    await create_auth_request_state(
        conn=db_conn,
        auth_request_id=auth_request_id,
        restaurant_id=test_restaurant_id,
        payment_token=test_payment_token,
        amount_cents=1050,
        currency="USD",
    )

    # Simulate denial (update status to DENIED)
    await db_conn.execute(
        """
        UPDATE auth_request_state
        SET status = $1,
            processor_auth_id = $2,
            processor_name = $3,
            denial_code = $4,
            denial_reason = $5,
            completed_at = $6,
            updated_at = $7,
            last_event_sequence = 2
        WHERE auth_request_id = $8
        """,
        "DENIED",
        "ch_stripe_123",
        "stripe",
        "insufficient_funds",
        "Card declined: insufficient funds",
        datetime.utcnow(),
        datetime.utcnow(),
        auth_request_id,
    )

    # Get status
    status_response = await build_status_response(
        conn=db_conn,
        auth_request_id=auth_request_id,
        restaurant_id=test_restaurant_id,
    )

    # Verify response
    assert status_response.status == AuthStatus.AUTH_STATUS_DENIED
    assert status_response.HasField("result")
    assert status_response.result.processor_auth_id == "ch_stripe_123"
    assert status_response.result.processor_name == "stripe"
    assert status_response.result.denial_code == "insufficient_funds"
    assert status_response.result.denial_reason == "Card declined: insufficient funds"


@pytest.mark.asyncio
async def test_get_status_processing(db_conn, test_restaurant_id, test_payment_token):
    """Test GET /status returns PROCESSING status."""
    auth_request_id = uuid.uuid4()

    # Create auth request state
    await create_auth_request_state(
        conn=db_conn,
        auth_request_id=auth_request_id,
        restaurant_id=test_restaurant_id,
        payment_token=test_payment_token,
        amount_cents=1050,
        currency="USD",
    )

    # Update to PROCESSING status
    await db_conn.execute(
        """
        UPDATE auth_request_state
        SET status = $1, updated_at = $2, last_event_sequence = 2
        WHERE auth_request_id = $3
        """,
        "PROCESSING",
        datetime.utcnow(),
        auth_request_id,
    )

    # Get status
    status_response = await build_status_response(
        conn=db_conn,
        auth_request_id=auth_request_id,
        restaurant_id=test_restaurant_id,
    )

    # Verify response
    assert status_response.status == AuthStatus.AUTH_STATUS_PROCESSING
    # No result for PROCESSING status
    assert not status_response.HasField("result")


@pytest.mark.asyncio
async def test_get_status_404_not_found(db_conn, test_restaurant_id):
    """Test GET /status returns 404 when auth request doesn't exist."""
    non_existent_id = uuid.uuid4()

    # Try to get status for non-existent auth request
    with pytest.raises(HTTPException) as exc_info:
        await build_status_response(
            conn=db_conn,
            auth_request_id=non_existent_id,
            restaurant_id=test_restaurant_id,
        )

    assert exc_info.value.status_code == 404
    assert "not found" in str(exc_info.value.detail).lower()


@pytest.mark.asyncio
async def test_get_status_404_restaurant_mismatch(
    db_conn, test_restaurant_id, test_payment_token
):
    """Test GET /status returns 404 when restaurant_id doesn't match."""
    auth_request_id = uuid.uuid4()
    wrong_restaurant_id = uuid.uuid4()

    # Create auth request for one restaurant
    await create_auth_request_state(
        conn=db_conn,
        auth_request_id=auth_request_id,
        restaurant_id=test_restaurant_id,
        payment_token=test_payment_token,
        amount_cents=1050,
        currency="USD",
    )

    # Try to get status with different restaurant_id
    with pytest.raises(HTTPException) as exc_info:
        await build_status_response(
            conn=db_conn,
            auth_request_id=auth_request_id,
            restaurant_id=wrong_restaurant_id,
        )

    assert exc_info.value.status_code == 404
    assert "not found" in str(exc_info.value.detail).lower()


@pytest.mark.asyncio
async def test_get_status_multiple_restaurants(
    db_conn, test_payment_token
):
    """Test that each restaurant can only see their own auth requests."""
    restaurant_id_1 = uuid.uuid4()
    restaurant_id_2 = uuid.uuid4()
    auth_request_id_1 = uuid.uuid4()
    auth_request_id_2 = uuid.uuid4()

    # Create auth request for restaurant 1
    await create_auth_request_state(
        conn=db_conn,
        auth_request_id=auth_request_id_1,
        restaurant_id=restaurant_id_1,
        payment_token=test_payment_token,
        amount_cents=1050,
        currency="USD",
    )

    # Create auth request for restaurant 2
    await create_auth_request_state(
        conn=db_conn,
        auth_request_id=auth_request_id_2,
        restaurant_id=restaurant_id_2,
        payment_token=test_payment_token,
        amount_cents=2000,
        currency="USD",
    )

    # Restaurant 1 can see their own request
    response_1 = await build_status_response(
        conn=db_conn,
        auth_request_id=auth_request_id_1,
        restaurant_id=restaurant_id_1,
    )
    assert response_1.auth_request_id == str(auth_request_id_1)

    # Restaurant 2 can see their own request
    response_2 = await build_status_response(
        conn=db_conn,
        auth_request_id=auth_request_id_2,
        restaurant_id=restaurant_id_2,
    )
    assert response_2.auth_request_id == str(auth_request_id_2)

    # Restaurant 1 CANNOT see restaurant 2's request
    with pytest.raises(HTTPException) as exc_info:
        await build_status_response(
            conn=db_conn,
            auth_request_id=auth_request_id_2,
            restaurant_id=restaurant_id_1,
        )
    assert exc_info.value.status_code == 404

    # Restaurant 2 CANNOT see restaurant 1's request
    with pytest.raises(HTTPException) as exc_info:
        await build_status_response(
            conn=db_conn,
            auth_request_id=auth_request_id_1,
            restaurant_id=restaurant_id_2,
        )
    assert exc_info.value.status_code == 404


@pytest.mark.asyncio
async def test_get_status_voided(db_conn, test_restaurant_id, test_payment_token):
    """Test GET /status returns VOIDED status."""
    auth_request_id = uuid.uuid4()

    # Create auth request
    await create_auth_request_state(
        conn=db_conn,
        auth_request_id=auth_request_id,
        restaurant_id=test_restaurant_id,
        payment_token=test_payment_token,
        amount_cents=1050,
        currency="USD",
    )

    # Update to VOIDED status
    await db_conn.execute(
        """
        UPDATE auth_request_state
        SET status = $1, updated_at = $2, last_event_sequence = 2
        WHERE auth_request_id = $3
        """,
        "VOIDED",
        datetime.utcnow(),
        auth_request_id,
    )

    # Get status
    status_response = await build_status_response(
        conn=db_conn,
        auth_request_id=auth_request_id,
        restaurant_id=test_restaurant_id,
    )

    # Verify response
    assert status_response.status == AuthStatus.AUTH_STATUS_VOIDED
    # No result for VOIDED status
    assert not status_response.HasField("result")


@pytest.mark.asyncio
async def test_get_status_failed(db_conn, test_restaurant_id, test_payment_token):
    """Test GET /status returns FAILED status."""
    auth_request_id = uuid.uuid4()

    # Create auth request
    await create_auth_request_state(
        conn=db_conn,
        auth_request_id=auth_request_id,
        restaurant_id=test_restaurant_id,
        payment_token=test_payment_token,
        amount_cents=1050,
        currency="USD",
    )

    # Update to FAILED status
    await db_conn.execute(
        """
        UPDATE auth_request_state
        SET status = $1, updated_at = $2, last_event_sequence = 2
        WHERE auth_request_id = $3
        """,
        "FAILED",
        datetime.utcnow(),
        auth_request_id,
    )

    # Get status
    status_response = await build_status_response(
        conn=db_conn,
        auth_request_id=auth_request_id,
        restaurant_id=test_restaurant_id,
    )

    # Verify response
    assert status_response.status == AuthStatus.AUTH_STATUS_FAILED
    # No result for FAILED status
    assert not status_response.HasField("result")

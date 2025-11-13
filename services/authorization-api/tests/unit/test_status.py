"""Unit tests for GET /authorize/{id}/status endpoint."""

import uuid
from datetime import datetime
from unittest.mock import AsyncMock, patch

import pytest
from payments.v1.authorization_pb2 import AuthStatus, GetAuthStatusResponse


@pytest.mark.asyncio
async def test_get_status_returns_pending():
    """Test that GET /status returns PENDING status correctly."""
    from authorization_api.api.routes.status import get_status

    auth_request_id = uuid.uuid4()
    restaurant_id = uuid.uuid4()

    # Mock database record (PENDING status)
    mock_record = {
        "auth_request_id": auth_request_id,
        "restaurant_id": restaurant_id,
        "status": "PENDING",
        "payment_token": "pt_test_12345",
        "amount_cents": 1050,
        "currency": "USD",
        "processor_auth_id": None,
        "processor_name": None,
        "authorized_amount_cents": None,
        "authorization_code": None,
        "denial_code": None,
        "denial_reason": None,
        "created_at": datetime(2024, 1, 1, 12, 0, 0),
        "updated_at": datetime(2024, 1, 1, 12, 0, 0),
        "completed_at": None,
        "metadata": {},
        "last_event_sequence": 1,
    }

    # Mock database connection
    mock_conn = AsyncMock()
    mock_conn.fetchrow.return_value = mock_record

    with patch(
        "authorization_api.api.routes.status.get_connection"
    ) as mock_get_conn, patch(
        "authorization_api.api.routes.status.get_auth_request_state"
    ) as mock_get_state:

        mock_get_conn.return_value.__aenter__.return_value = mock_conn
        mock_get_conn.return_value.__aexit__.return_value = None
        mock_get_state.return_value = mock_record

        # Call endpoint
        response = await get_status(
            auth_request_id=str(auth_request_id), restaurant_id=str(restaurant_id)
        )

        # Verify response
        assert response.status_code == 200
        assert response.media_type == "application/x-protobuf"

        # Parse protobuf response
        status_response = GetAuthStatusResponse()
        status_response.ParseFromString(response.body)

        assert status_response.auth_request_id == str(auth_request_id)
        assert status_response.status == AuthStatus.AUTH_STATUS_PENDING
        assert status_response.created_at > 0
        assert status_response.updated_at > 0
        # No result for PENDING status
        assert not status_response.HasField("result")


@pytest.mark.asyncio
async def test_get_status_returns_authorized_with_result():
    """Test that GET /status returns AUTHORIZED with full result."""
    from authorization_api.api.routes.status import get_status

    auth_request_id = uuid.uuid4()
    restaurant_id = uuid.uuid4()

    # Mock database record (AUTHORIZED status)
    mock_record = {
        "auth_request_id": auth_request_id,
        "restaurant_id": restaurant_id,
        "status": "AUTHORIZED",
        "payment_token": "pt_test_12345",
        "amount_cents": 1050,
        "currency": "USD",
        "processor_auth_id": "ch_stripe_123",
        "processor_name": "stripe",
        "authorized_amount_cents": 1050,
        "authorization_code": "AUTH-12345",
        "denial_code": None,
        "denial_reason": None,
        "created_at": datetime(2024, 1, 1, 12, 0, 0),
        "updated_at": datetime(2024, 1, 1, 12, 1, 0),
        "completed_at": datetime(2024, 1, 1, 12, 1, 0),
        "metadata": {},
        "last_event_sequence": 2,
    }

    mock_conn = AsyncMock()
    mock_conn.fetchrow.return_value = mock_record

    with patch(
        "authorization_api.api.routes.status.get_connection"
    ) as mock_get_conn, patch(
        "authorization_api.api.routes.status.get_auth_request_state"
    ) as mock_get_state:

        mock_get_conn.return_value.__aenter__.return_value = mock_conn
        mock_get_conn.return_value.__aexit__.return_value = None
        mock_get_state.return_value = mock_record

        # Call endpoint
        response = await get_status(
            auth_request_id=str(auth_request_id), restaurant_id=str(restaurant_id)
        )

        # Verify response
        assert response.status_code == 200

        # Parse protobuf response
        status_response = GetAuthStatusResponse()
        status_response.ParseFromString(response.body)

        assert status_response.status == AuthStatus.AUTH_STATUS_AUTHORIZED
        assert status_response.HasField("result")
        assert status_response.result.processor_auth_id == "ch_stripe_123"
        assert status_response.result.processor_name == "stripe"
        assert status_response.result.authorization_code == "AUTH-12345"
        assert status_response.result.authorized_amount_cents == 1050
        assert status_response.result.currency == "USD"


@pytest.mark.asyncio
async def test_get_status_returns_denied_with_result():
    """Test that GET /status returns DENIED with denial information."""
    from authorization_api.api.routes.status import get_status

    auth_request_id = uuid.uuid4()
    restaurant_id = uuid.uuid4()

    # Mock database record (DENIED status)
    mock_record = {
        "auth_request_id": auth_request_id,
        "restaurant_id": restaurant_id,
        "status": "DENIED",
        "payment_token": "pt_test_12345",
        "amount_cents": 1050,
        "currency": "USD",
        "processor_auth_id": "ch_stripe_123",
        "processor_name": "stripe",
        "authorized_amount_cents": None,
        "authorization_code": None,
        "denial_code": "insufficient_funds",
        "denial_reason": "Card declined: insufficient funds",
        "created_at": datetime(2024, 1, 1, 12, 0, 0),
        "updated_at": datetime(2024, 1, 1, 12, 1, 0),
        "completed_at": datetime(2024, 1, 1, 12, 1, 0),
        "metadata": {},
        "last_event_sequence": 2,
    }

    mock_conn = AsyncMock()

    with patch(
        "authorization_api.api.routes.status.get_connection"
    ) as mock_get_conn, patch(
        "authorization_api.api.routes.status.get_auth_request_state"
    ) as mock_get_state:

        mock_get_conn.return_value.__aenter__.return_value = mock_conn
        mock_get_conn.return_value.__aexit__.return_value = None
        mock_get_state.return_value = mock_record

        # Call endpoint
        response = await get_status(
            auth_request_id=str(auth_request_id), restaurant_id=str(restaurant_id)
        )

        # Parse protobuf response
        status_response = GetAuthStatusResponse()
        status_response.ParseFromString(response.body)

        assert status_response.status == AuthStatus.AUTH_STATUS_DENIED
        assert status_response.HasField("result")
        assert status_response.result.denial_code == "insufficient_funds"
        assert status_response.result.denial_reason == "Card declined: insufficient funds"


@pytest.mark.asyncio
async def test_get_status_404_when_not_found():
    """Test that GET /status returns 404 when auth request not found."""
    from authorization_api.api.routes.status import get_status
    from fastapi import HTTPException

    auth_request_id = uuid.uuid4()
    restaurant_id = uuid.uuid4()

    mock_conn = AsyncMock()

    with patch(
        "authorization_api.api.routes.status.get_connection"
    ) as mock_get_conn, patch(
        "authorization_api.api.routes.status.get_auth_request_state"
    ) as mock_get_state:

        mock_get_conn.return_value.__aenter__.return_value = mock_conn
        mock_get_conn.return_value.__aexit__.return_value = None
        # Return None to simulate not found
        mock_get_state.return_value = None

        # Call endpoint - should raise 404
        with pytest.raises(HTTPException) as exc_info:
            await get_status(
                auth_request_id=str(auth_request_id), restaurant_id=str(restaurant_id)
            )

        assert exc_info.value.status_code == 404
        assert "not found" in str(exc_info.value.detail).lower()


@pytest.mark.asyncio
async def test_get_status_404_when_restaurant_mismatch():
    """Test that GET /status returns 404 when restaurant_id doesn't match."""
    from authorization_api.api.routes.status import get_status
    from fastapi import HTTPException

    auth_request_id = uuid.uuid4()
    actual_restaurant_id = uuid.uuid4()
    wrong_restaurant_id = uuid.uuid4()

    # Mock record with different restaurant_id
    mock_record = {
        "auth_request_id": auth_request_id,
        "restaurant_id": actual_restaurant_id,
        "status": "PENDING",
        "created_at": datetime(2024, 1, 1, 12, 0, 0),
        "updated_at": datetime(2024, 1, 1, 12, 0, 0),
    }

    mock_conn = AsyncMock()

    with patch(
        "authorization_api.api.routes.status.get_connection"
    ) as mock_get_conn, patch(
        "authorization_api.api.routes.status.get_auth_request_state"
    ) as mock_get_state:

        mock_get_conn.return_value.__aenter__.return_value = mock_conn
        mock_get_conn.return_value.__aexit__.return_value = None
        mock_get_state.return_value = mock_record

        # Call endpoint with wrong restaurant_id
        with pytest.raises(HTTPException) as exc_info:
            await get_status(
                auth_request_id=str(auth_request_id),
                restaurant_id=str(wrong_restaurant_id),
            )

        assert exc_info.value.status_code == 404
        assert "not found" in str(exc_info.value.detail).lower()


@pytest.mark.asyncio
async def test_get_status_400_invalid_auth_request_id():
    """Test that GET /status returns 400 for invalid auth_request_id format."""
    from authorization_api.api.routes.status import get_status
    from fastapi import HTTPException

    restaurant_id = uuid.uuid4()

    with pytest.raises(HTTPException) as exc_info:
        await get_status(
            auth_request_id="invalid-uuid", restaurant_id=str(restaurant_id)
        )

    assert exc_info.value.status_code == 400
    assert "auth_request_id" in str(exc_info.value.detail).lower()


@pytest.mark.asyncio
async def test_get_status_400_invalid_restaurant_id():
    """Test that GET /status returns 400 for invalid restaurant_id format."""
    from authorization_api.api.routes.status import get_status
    from fastapi import HTTPException

    auth_request_id = uuid.uuid4()

    with pytest.raises(HTTPException) as exc_info:
        await get_status(auth_request_id=str(auth_request_id), restaurant_id="invalid-uuid")

    assert exc_info.value.status_code == 400
    assert "restaurant_id" in str(exc_info.value.detail).lower()

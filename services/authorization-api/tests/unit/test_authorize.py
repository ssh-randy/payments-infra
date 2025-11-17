"""Unit tests for POST /authorize endpoint."""

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from payments_proto.payments.v1.authorization_pb2 import AuthorizeRequest, AuthorizeResponse, AuthStatus


@pytest.fixture
def auth_request_proto():
    """Create a sample AuthorizeRequest protobuf."""
    return AuthorizeRequest(
        payment_token="pt_test_12345",
        restaurant_id=str(uuid.uuid4()),
        amount_cents=1050,
        currency="USD",
        idempotency_key=str(uuid.uuid4()),
        metadata={"order_id": "order-123", "table_number": "5"},
    )


@pytest.mark.asyncio
async def test_authorize_creates_new_request(auth_request_proto):
    """Test that POST /authorize creates a new auth request with atomic writes."""
    from authorization_api.api.routes.authorize import post_authorize
    from fastapi import Request

    # Mock request
    request = MagicMock(spec=Request)
    request.body = AsyncMock(return_value=auth_request_proto.SerializeToString())

    # Mock database transaction and operations
    mock_conn = AsyncMock()
    mock_conn.fetchrow.return_value = None  # No existing idempotency key
    mock_conn.execute = AsyncMock()

    # Mock transaction context manager
    @pytest.fixture
    async def mock_transaction():
        yield mock_conn

    with patch(
        "authorization_api.api.routes.authorize.transaction"
    ) as mock_txn, patch(
        "authorization_api.api.routes.authorize.poll_for_completion"
    ) as mock_poll:

        # Setup mocks
        mock_txn.return_value.__aenter__.return_value = mock_conn
        mock_txn.return_value.__aexit__.return_value = None

        # Mock poll returning timeout (slow path)
        mock_poll.return_value = ("PROCESSING", None)

        # Call endpoint
        response = await post_authorize(request)

        # Verify response
        assert response.status_code == 202
        assert response.media_type == "application/x-protobuf"

        # Parse response
        auth_response = AuthorizeResponse()
        auth_response.ParseFromString(response.body)

        assert auth_response.status == AuthStatus.AUTH_STATUS_PROCESSING
        assert auth_response.auth_request_id
        assert "/status" in auth_response.status_url

        # Verify database operations were called
        # 1. Check idempotency
        # 2. Write event
        # 3. Write read model
        # 4. Write outbox
        # 5. Write idempotency key
        # Total: At least 4 execute calls + 1 fetchrow
        assert mock_conn.execute.call_count >= 4


@pytest.mark.asyncio
async def test_authorize_idempotency_returns_existing(auth_request_proto):
    """Test that duplicate idempotency key returns existing request."""
    from authorization_api.api.routes.authorize import post_authorize
    from fastapi import Request

    existing_auth_request_id = uuid.uuid4()

    # Mock request
    request = MagicMock(spec=Request)
    request.body = AsyncMock(return_value=auth_request_proto.SerializeToString())

    # Mock database
    mock_conn = AsyncMock()

    # First fetchrow: idempotency key exists
    # Second fetchrow: get auth request state
    mock_conn.fetchrow.side_effect = [
        {"auth_request_id": existing_auth_request_id},  # Idempotency check
        {  # Get state
            "auth_request_id": existing_auth_request_id,
            "restaurant_id": uuid.UUID(auth_request_proto.restaurant_id),
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
            "created_at": None,
            "updated_at": None,
            "completed_at": None,
            "metadata": {},
            "last_event_sequence": 1,
        },
    ]

    with patch("authorization_api.api.routes.authorize.transaction") as mock_txn:
        mock_txn.return_value.__aenter__.return_value = mock_conn
        mock_txn.return_value.__aexit__.return_value = None

        # Call endpoint
        response = await post_authorize(request)

        # Verify response
        assert response.status_code == 202  # Still processing
        assert response.media_type == "application/x-protobuf"

        # Parse response
        auth_response = AuthorizeResponse()
        auth_response.ParseFromString(response.body)

        assert auth_response.status == AuthStatus.AUTH_STATUS_PENDING
        assert str(existing_auth_request_id) == auth_response.auth_request_id

        # Verify no new write operations (only reads)
        mock_conn.execute.assert_not_called()


@pytest.mark.asyncio
async def test_authorize_fast_path_completed():
    """Test that authorization completing within 5 seconds returns 200."""
    from authorization_api.api.routes.authorize import post_authorize
    from fastapi import Request

    auth_request_proto = AuthorizeRequest(
        payment_token="pt_test_12345",
        restaurant_id=str(uuid.uuid4()),
        amount_cents=1050,
        currency="USD",
        idempotency_key=str(uuid.uuid4()),
    )

    request = MagicMock(spec=Request)
    request.body = AsyncMock(return_value=auth_request_proto.SerializeToString())

    mock_conn = AsyncMock()
    mock_conn.fetchrow.return_value = None  # No existing idempotency key
    mock_conn.execute = AsyncMock()

    # Mock completed state
    completed_state = {
        "auth_request_id": uuid.uuid4(),
        "restaurant_id": uuid.UUID(auth_request_proto.restaurant_id),
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
        "created_at": None,
        "updated_at": None,
        "completed_at": None,
        "metadata": {},
        "last_event_sequence": 2,
    }

    with patch(
        "authorization_api.api.routes.authorize.transaction"
    ) as mock_txn, patch(
        "authorization_api.api.routes.authorize.poll_for_completion"
    ) as mock_poll:

        mock_txn.return_value.__aenter__.return_value = mock_conn
        mock_txn.return_value.__aexit__.return_value = None

        # Mock poll returning AUTHORIZED
        mock_poll.return_value = ("AUTHORIZED", completed_state)

        # Call endpoint
        response = await post_authorize(request)

        # Verify fast path response (200)
        assert response.status_code == 200
        assert response.media_type == "application/x-protobuf"

        # Parse response
        auth_response = AuthorizeResponse()
        auth_response.ParseFromString(response.body)

        assert auth_response.status == AuthStatus.AUTH_STATUS_AUTHORIZED
        assert auth_response.result.processor_auth_id == "ch_stripe_123"
        assert auth_response.result.authorization_code == "AUTH-12345"


@pytest.mark.asyncio
async def test_authorize_validation_errors():
    """Test that missing required fields return 400 errors."""
    from authorization_api.api.routes.authorize import post_authorize
    from fastapi import Request, HTTPException

    # Missing payment_token
    invalid_request = AuthorizeRequest(
        restaurant_id=str(uuid.uuid4()),
        amount_cents=1050,
        currency="USD",
        idempotency_key=str(uuid.uuid4()),
    )

    request = MagicMock(spec=Request)
    request.body = AsyncMock(return_value=invalid_request.SerializeToString())

    with pytest.raises(HTTPException) as exc_info:
        await post_authorize(request)

    assert exc_info.value.status_code == 400
    assert "payment_token" in str(exc_info.value.detail)


@pytest.mark.asyncio
async def test_authorize_atomic_transaction_rollback():
    """Test that transaction rollback prevents partial writes."""
    from authorization_api.api.routes.authorize import post_authorize
    from fastapi import Request

    auth_request_proto = AuthorizeRequest(
        payment_token="pt_test_12345",
        restaurant_id=str(uuid.uuid4()),
        amount_cents=1050,
        currency="USD",
        idempotency_key=str(uuid.uuid4()),
    )

    request = MagicMock(spec=Request)
    request.body = AsyncMock(return_value=auth_request_proto.SerializeToString())

    mock_conn = AsyncMock()
    mock_conn.fetchrow.return_value = None

    # Simulate failure on 3rd execute (outbox write)
    mock_conn.execute.side_effect = [
        None,  # Event write
        None,  # Read model write
        Exception("Database error"),  # Outbox write fails
    ]

    with patch("authorization_api.api.routes.authorize.transaction") as mock_txn:
        mock_txn.return_value.__aenter__.return_value = mock_conn
        mock_txn.return_value.__aexit__.side_effect = Exception("Transaction rolled back")

        # Call should raise exception
        with pytest.raises(Exception):
            await post_authorize(request)

        # Verify rollback occurred (transaction __aexit__ was called)
        assert mock_txn.return_value.__aexit__.called

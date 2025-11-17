"""Unit tests for outbox processor."""

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from payments_proto.payments.v1.events_pb2 import AuthRequestQueuedMessage, VoidRequestQueuedMessage

from authorization_api.infrastructure.outbox_processor import (
    fetch_unprocessed_messages,
    send_message_to_sqs,
    mark_message_as_processed,
    process_outbox_batch,
)


@pytest.mark.asyncio
async def test_fetch_unprocessed_messages():
    """Test fetching unprocessed messages from outbox."""
    # Create mock connection
    mock_conn = AsyncMock()

    # Mock database response
    mock_row = {
        "id": 1,
        "aggregate_id": uuid.uuid4(),
        "message_type": "auth_request_queued",
        "payload": b"test_payload",
    }
    mock_conn.fetch.return_value = [mock_row]

    # Call function
    messages = await fetch_unprocessed_messages(mock_conn, limit=100)

    # Verify
    assert len(messages) == 1
    assert messages[0]["id"] == 1
    assert messages[0]["message_type"] == "auth_request_queued"

    # Verify SQL query
    mock_conn.fetch.assert_called_once()
    call_args = mock_conn.fetch.call_args
    assert "WHERE processed_at IS NULL" in call_args[0][0]
    assert "FOR UPDATE SKIP LOCKED" in call_args[0][0]
    assert call_args[0][1] == 100


@pytest.mark.asyncio
async def test_send_message_to_sqs_auth_request():
    """Test sending auth request message to SQS."""
    # Create test message
    auth_request_id = uuid.uuid4()
    restaurant_id = uuid.uuid4()

    queued_msg = AuthRequestQueuedMessage(
        auth_request_id=str(auth_request_id),
        restaurant_id=str(restaurant_id),
        created_at=1234567890,
    )

    message = {
        "id": 1,
        "aggregate_id": auth_request_id,
        "message_type": "auth_request_queued",
        "payload": queued_msg.SerializeToString(),
    }

    # Mock SQS send functions
    with patch(
        "authorization_api.infrastructure.outbox_processor.send_to_auth_requests_queue"
    ) as mock_send:
        mock_send.return_value = None

        # Call function
        await send_message_to_sqs(message)

        # Verify
        mock_send.assert_called_once()
        call_kwargs = mock_send.call_args[1]
        assert call_kwargs["message_deduplication_id"] == str(auth_request_id)
        assert call_kwargs["message_group_id"] == str(restaurant_id)


@pytest.mark.asyncio
async def test_send_message_to_sqs_void_request():
    """Test sending void request message to SQS."""
    # Create test message
    auth_request_id = uuid.uuid4()
    restaurant_id = uuid.uuid4()

    void_msg = VoidRequestQueuedMessage(
        auth_request_id=str(auth_request_id),
        restaurant_id=str(restaurant_id),
        reason="customer_cancelled",
        created_at=1234567890,
    )

    message = {
        "id": 2,
        "aggregate_id": auth_request_id,
        "message_type": "void_request_queued",
        "payload": void_msg.SerializeToString(),
    }

    # Mock SQS send functions
    with patch(
        "authorization_api.infrastructure.outbox_processor.send_to_void_requests_queue"
    ) as mock_send:
        mock_send.return_value = None

        # Call function
        await send_message_to_sqs(message)

        # Verify
        mock_send.assert_called_once()
        call_kwargs = mock_send.call_args[1]
        assert call_kwargs["message_body"] == void_msg.SerializeToString()


@pytest.mark.asyncio
async def test_send_message_to_sqs_unknown_type():
    """Test sending message with unknown type raises error."""
    message = {
        "id": 3,
        "aggregate_id": uuid.uuid4(),
        "message_type": "unknown_type",
        "payload": b"test",
    }

    # Should raise ValueError
    with pytest.raises(ValueError, match="Unknown message type"):
        await send_message_to_sqs(message)


@pytest.mark.asyncio
async def test_mark_message_as_processed():
    """Test marking message as processed."""
    mock_conn = AsyncMock()

    await mark_message_as_processed(mock_conn, message_id=123)

    # Verify SQL executed
    mock_conn.execute.assert_called_once()
    call_args = mock_conn.execute.call_args
    assert "UPDATE outbox" in call_args[0][0]
    assert "SET processed_at = NOW()" in call_args[0][0]
    assert call_args[0][1] == 123


@pytest.mark.asyncio
async def test_process_outbox_batch_no_messages():
    """Test processing when no messages are available."""
    # Mock database pool
    mock_conn = AsyncMock()
    mock_conn.fetch.return_value = []

    mock_acquire = MagicMock()
    mock_acquire.__aenter__ = AsyncMock(return_value=mock_conn)
    mock_acquire.__aexit__ = AsyncMock(return_value=None)

    mock_pool = MagicMock()
    mock_pool.acquire.return_value = mock_acquire

    # Mock get_pool to return the pool (not a coroutine)
    async def mock_get_pool():
        return mock_pool

    with patch(
        "authorization_api.infrastructure.outbox_processor.get_pool",
        side_effect=mock_get_pool,
    ):
        # Call function
        processed_count = await process_outbox_batch()

        # Verify
        assert processed_count == 0


@pytest.mark.asyncio
async def test_process_outbox_batch_success():
    """Test processing a batch of messages successfully."""
    # Create test data
    auth_request_id = uuid.uuid4()
    restaurant_id = uuid.uuid4()

    queued_msg = AuthRequestQueuedMessage(
        auth_request_id=str(auth_request_id),
        restaurant_id=str(restaurant_id),
        created_at=1234567890,
    )

    message = {
        "id": 1,
        "aggregate_id": auth_request_id,
        "message_type": "auth_request_queued",
        "payload": queued_msg.SerializeToString(),
    }

    # Mock database
    mock_conn = AsyncMock()
    mock_conn.fetch.return_value = [message]
    mock_conn.execute.return_value = None

    mock_acquire = MagicMock()
    mock_acquire.__aenter__ = AsyncMock(return_value=mock_conn)
    mock_acquire.__aexit__ = AsyncMock(return_value=None)

    mock_pool = MagicMock()
    mock_pool.acquire.return_value = mock_acquire

    # Mock get_pool to return the pool (not a coroutine)
    async def mock_get_pool():
        return mock_pool

    with patch(
        "authorization_api.infrastructure.outbox_processor.get_pool",
        side_effect=mock_get_pool,
    ):
        with patch(
            "authorization_api.infrastructure.outbox_processor.send_to_auth_requests_queue"
        ) as mock_send:
            mock_send.return_value = None

            # Call function
            processed_count = await process_outbox_batch()

            # Verify
            assert processed_count == 1
            mock_send.assert_called_once()
            mock_conn.execute.assert_called_once()


@pytest.mark.asyncio
async def test_process_outbox_batch_partial_failure():
    """Test that processing continues even if one message fails."""
    # Create two test messages
    auth_request_id_1 = uuid.uuid4()
    auth_request_id_2 = uuid.uuid4()
    restaurant_id = uuid.uuid4()

    queued_msg_1 = AuthRequestQueuedMessage(
        auth_request_id=str(auth_request_id_1),
        restaurant_id=str(restaurant_id),
        created_at=1234567890,
    )

    queued_msg_2 = AuthRequestQueuedMessage(
        auth_request_id=str(auth_request_id_2),
        restaurant_id=str(restaurant_id),
        created_at=1234567891,
    )

    messages = [
        {
            "id": 1,
            "aggregate_id": auth_request_id_1,
            "message_type": "auth_request_queued",
            "payload": queued_msg_1.SerializeToString(),
        },
        {
            "id": 2,
            "aggregate_id": auth_request_id_2,
            "message_type": "auth_request_queued",
            "payload": queued_msg_2.SerializeToString(),
        },
    ]

    # Mock database
    mock_conn = AsyncMock()
    mock_conn.fetch.return_value = messages
    mock_conn.execute.return_value = None

    mock_acquire = MagicMock()
    mock_acquire.__aenter__ = AsyncMock(return_value=mock_conn)
    mock_acquire.__aexit__ = AsyncMock(return_value=None)

    mock_pool = MagicMock()
    mock_pool.acquire.return_value = mock_acquire

    # Mock get_pool to return the pool (not a coroutine)
    async def mock_get_pool():
        return mock_pool

    with patch(
        "authorization_api.infrastructure.outbox_processor.get_pool",
        side_effect=mock_get_pool,
    ):
        with patch(
            "authorization_api.infrastructure.outbox_processor.send_to_auth_requests_queue"
        ) as mock_send:
            # First call fails, second succeeds
            mock_send.side_effect = [Exception("SQS error"), None]

            # Call function
            processed_count = await process_outbox_batch()

            # Verify: only second message was processed
            assert processed_count == 1
            assert mock_send.call_count == 2
            # Only one execute (for second message)
            assert mock_conn.execute.call_count == 1

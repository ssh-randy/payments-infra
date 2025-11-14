"""Unit tests for SQS consumer."""

import asyncio
import base64
import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from payments_proto.payments.v1 import events_pb2

from auth_processor_worker.infrastructure.sqs_consumer import SQSConsumer


def create_protobuf_message(auth_request_id: str, restaurant_id: str = "rest-123", created_at: int = 1234567890) -> str:
    """Create a base64-encoded protobuf message for testing."""
    msg = events_pb2.AuthRequestQueuedMessage(
        auth_request_id=auth_request_id,
        restaurant_id=restaurant_id,
        created_at=created_at,
    )
    return base64.b64encode(msg.SerializeToString()).decode('utf-8')


@pytest.fixture
def mock_sqs_client():
    """Mock SQS client for testing."""
    client = AsyncMock()
    client.receive_message = AsyncMock()
    client.delete_message = AsyncMock()
    return client


@pytest.fixture
def sqs_consumer():
    """Create an SQSConsumer instance for testing."""
    return SQSConsumer(
        queue_url="https://sqs.us-east-1.amazonaws.com/123456789012/test-queue.fifo",
        batch_size=1,
        wait_time_seconds=20,
        visibility_timeout=30,
        aws_region="us-east-1",
        aws_endpoint_url="http://localhost:4566",
    )


@pytest.mark.asyncio
async def test_consumer_initialization():
    """Test SQSConsumer initialization."""
    consumer = SQSConsumer(
        queue_url="https://test-queue-url",
        batch_size=5,
        wait_time_seconds=10,
        visibility_timeout=60,
    )

    assert consumer.queue_url == "https://test-queue-url"
    assert consumer.batch_size == 5
    assert consumer.wait_time_seconds == 10
    assert consumer.visibility_timeout == 60
    assert consumer.running is False
    assert consumer.message_handler is None


@pytest.mark.asyncio
async def test_process_messages_with_valid_message(mock_sqs_client):
    """Test processing a valid SQS message."""
    # Create consumer with a message handler
    handler_called = False
    received_data = None

    async def test_handler(data):
        nonlocal handler_called, received_data
        handler_called = True
        received_data = data

    consumer = SQSConsumer(
        queue_url="https://test-queue",
        message_handler=test_handler,
    )

    # Mock SQS response with a valid message (base64-encoded protobuf)
    mock_sqs_client.receive_message.return_value = {
        "Messages": [
            {
                "MessageId": "msg-123",
                "ReceiptHandle": "receipt-handle-123",
                "Body": create_protobuf_message("auth-req-456", "rest-123"),
                "Attributes": {
                    "ApproximateReceiveCount": "1",
                    "MessageGroupId": "group-1",
                },
            }
        ]
    }

    # Set the mock client
    consumer._sqs_client = mock_sqs_client

    # Process messages
    await consumer.process_messages()

    # Verify handler was called
    assert handler_called is True
    assert received_data is not None
    assert received_data["auth_request_id"] == "auth-req-456"
    assert received_data["message_id"] == "msg-123"
    assert received_data["receive_count"] == 1

    # Verify message was deleted
    mock_sqs_client.delete_message.assert_called_once_with(
        QueueUrl="https://test-queue",
        ReceiptHandle="receipt-handle-123",
    )


@pytest.mark.asyncio
async def test_process_messages_with_no_messages(mock_sqs_client):
    """Test processing when no messages are available."""
    consumer = SQSConsumer(queue_url="https://test-queue")

    # Mock SQS response with no messages
    mock_sqs_client.receive_message.return_value = {}

    consumer._sqs_client = mock_sqs_client

    # Process messages (should not raise)
    await consumer.process_messages()

    # Verify delete was not called
    mock_sqs_client.delete_message.assert_not_called()


@pytest.mark.asyncio
async def test_process_messages_with_missing_auth_request_id(mock_sqs_client):
    """Test processing a message without auth_request_id."""
    consumer = SQSConsumer(queue_url="https://test-queue")

    # Mock SQS response with invalid message (missing auth_request_id)
    mock_sqs_client.receive_message.return_value = {
        "Messages": [
            {
                "MessageId": "msg-123",
                "ReceiptHandle": "receipt-handle-123",
                "Body": json.dumps({"some_field": "value"}),  # Missing auth_request_id
                "Attributes": {"ApproximateReceiveCount": "1"},
            }
        ]
    }

    consumer._sqs_client = mock_sqs_client

    # Process messages
    await consumer.process_messages()

    # Message should still be deleted (malformed message)
    mock_sqs_client.delete_message.assert_called_once()


@pytest.mark.asyncio
async def test_process_messages_with_json_decode_error(mock_sqs_client):
    """Test processing a message with invalid JSON."""
    consumer = SQSConsumer(queue_url="https://test-queue")

    # Mock SQS response with invalid JSON
    mock_sqs_client.receive_message.return_value = {
        "Messages": [
            {
                "MessageId": "msg-123",
                "ReceiptHandle": "receipt-handle-123",
                "Body": "invalid-json{{{",
                "Attributes": {"ApproximateReceiveCount": "1"},
            }
        ]
    }

    consumer._sqs_client = mock_sqs_client

    # Process messages (should not raise)
    await consumer.process_messages()

    # Malformed message should be deleted
    mock_sqs_client.delete_message.assert_called_once()


@pytest.mark.asyncio
async def test_process_messages_with_handler_exception(mock_sqs_client):
    """Test processing when message handler raises an exception."""

    async def failing_handler(data):
        raise ValueError("Handler error")

    consumer = SQSConsumer(
        queue_url="https://test-queue",
        message_handler=failing_handler,
    )

    # Mock SQS response with valid message (base64-encoded protobuf)
    mock_sqs_client.receive_message.return_value = {
        "Messages": [
            {
                "MessageId": "msg-123",
                "ReceiptHandle": "receipt-handle-123",
                "Body": create_protobuf_message("auth-req-456", "rest-123"),
                "Attributes": {"ApproximateReceiveCount": "2"},
            }
        ]
    }

    consumer._sqs_client = mock_sqs_client

    # Process messages (should not raise)
    await consumer.process_messages()

    # Message should NOT be deleted on handler error
    mock_sqs_client.delete_message.assert_not_called()


@pytest.mark.asyncio
async def test_stop_consumer():
    """Test stopping the consumer."""
    consumer = SQSConsumer(queue_url="https://test-queue")
    consumer.running = True

    await consumer.stop()

    assert consumer.running is False


@pytest.mark.asyncio
async def test_delete_message_success(mock_sqs_client):
    """Test successful message deletion."""
    consumer = SQSConsumer(queue_url="https://test-queue")
    consumer._sqs_client = mock_sqs_client

    await consumer._delete_message("receipt-handle-123", "msg-123")

    mock_sqs_client.delete_message.assert_called_once_with(
        QueueUrl="https://test-queue",
        ReceiptHandle="receipt-handle-123",
    )


@pytest.mark.asyncio
async def test_delete_message_with_missing_receipt_handle(mock_sqs_client):
    """Test deletion when receipt handle is missing."""
    consumer = SQSConsumer(queue_url="https://test-queue")
    consumer._sqs_client = mock_sqs_client

    # Should not raise, but should log error
    await consumer._delete_message(None, "msg-123")

    # Delete should not be called
    mock_sqs_client.delete_message.assert_not_called()


@pytest.mark.asyncio
async def test_process_messages_without_initialized_client():
    """Test processing messages before client is initialized."""
    consumer = SQSConsumer(queue_url="https://test-queue")

    with pytest.raises(RuntimeError, match="SQS client not initialized"):
        await consumer.process_messages()


@pytest.mark.asyncio
async def test_process_messages_with_multiple_messages(mock_sqs_client):
    """Test processing multiple messages in a batch."""
    handler_calls = []

    async def test_handler(data):
        handler_calls.append(data["auth_request_id"])

    consumer = SQSConsumer(
        queue_url="https://test-queue",
        batch_size=3,
        message_handler=test_handler,
    )

    # Mock SQS response with multiple messages (base64-encoded protobuf)
    mock_sqs_client.receive_message.return_value = {
        "Messages": [
            {
                "MessageId": "msg-1",
                "ReceiptHandle": "receipt-1",
                "Body": create_protobuf_message("auth-1", "rest-1"),
                "Attributes": {"ApproximateReceiveCount": "1"},
            },
            {
                "MessageId": "msg-2",
                "ReceiptHandle": "receipt-2",
                "Body": create_protobuf_message("auth-2", "rest-2"),
                "Attributes": {"ApproximateReceiveCount": "1"},
            },
            {
                "MessageId": "msg-3",
                "ReceiptHandle": "receipt-3",
                "Body": create_protobuf_message("auth-3", "rest-3"),
                "Attributes": {"ApproximateReceiveCount": "1"},
            },
        ]
    }

    consumer._sqs_client = mock_sqs_client

    await consumer.process_messages()

    # All handlers should be called
    assert len(handler_calls) == 3
    assert "auth-1" in handler_calls
    assert "auth-2" in handler_calls
    assert "auth-3" in handler_calls

    # All messages should be deleted
    assert mock_sqs_client.delete_message.call_count == 3


@pytest.mark.asyncio
async def test_start_and_stop_gracefully():
    """Test that stop() sets the running flag to False."""
    consumer = SQSConsumer(
        queue_url="https://test-queue",
        aws_endpoint_url="http://localhost:4566",
    )

    # Initially not running
    assert consumer.running is False

    # Simulate starting
    consumer.running = True
    assert consumer.running is True

    # Stop the consumer
    await consumer.stop()

    # Should no longer be running
    assert consumer.running is False

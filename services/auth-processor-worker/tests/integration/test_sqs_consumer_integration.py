"""Integration tests for SQS consumer with LocalStack."""

import asyncio
import base64
import json
import os
import sys
import uuid
from pathlib import Path

import aioboto3
import pytest
import pytest_asyncio

# Add shared proto directory to Python path
_shared_proto_path = Path(__file__).parent.parent.parent.parent.parent.parent / "shared" / "python"
if str(_shared_proto_path) not in sys.path:
    sys.path.insert(0, str(_shared_proto_path))

from payments_proto.payments.v1 import events_pb2

from auth_processor_worker.infrastructure.sqs_consumer import SQSConsumer

# LocalStack configuration
LOCALSTACK_ENDPOINT = os.getenv("AWS_ENDPOINT_URL", "http://localhost:4566")
AWS_REGION = os.getenv("AWS_REGION", "us-east-1")

# Mark all tests in this module as integration tests
pytestmark = pytest.mark.integration


@pytest_asyncio.fixture
async def sqs_client():
    """Create an SQS client connected to LocalStack."""
    session = aioboto3.Session()
    async with session.client(
        "sqs",
        region_name=AWS_REGION,
        endpoint_url=LOCALSTACK_ENDPOINT,
        aws_access_key_id="test",
        aws_secret_access_key="test",
    ) as client:
        yield client


@pytest_asyncio.fixture
async def test_queue(sqs_client):
    """Create a test FIFO queue in LocalStack."""
    # Generate unique queue name
    queue_name = f"test-auth-requests-{uuid.uuid4().hex[:8]}.fifo"

    # Create queue
    response = await sqs_client.create_queue(
        QueueName=queue_name,
        Attributes={
            "FifoQueue": "true",
            "ContentBasedDeduplication": "false",
            "VisibilityTimeout": "30",
            "MessageRetentionPeriod": "300",  # 5 minutes for testing
        },
    )

    queue_url = response["QueueUrl"]

    yield queue_url

    # Cleanup: Delete queue after test
    try:
        await sqs_client.delete_queue(QueueUrl=queue_url)
    except Exception:
        pass  # Ignore cleanup errors


@pytest.mark.asyncio
async def test_sqs_consumer_receives_and_processes_message(sqs_client, test_queue):
    """Test that SQS consumer can receive and process messages from LocalStack."""
    # Track processed messages
    processed_messages = []

    async def message_handler(message_data):
        """Handler that records processed messages."""
        processed_messages.append(message_data)

    # Create consumer
    consumer = SQSConsumer(
        queue_url=test_queue,
        batch_size=1,
        wait_time_seconds=5,  # Shorter wait for testing
        visibility_timeout=30,
        aws_region=AWS_REGION,
        aws_endpoint_url=LOCALSTACK_ENDPOINT,
        message_handler=message_handler,
    )

    # Send a test message to the queue
    auth_request_id = f"auth-req-{uuid.uuid4().hex}"

    # Create protobuf message
    import time
    queued_msg = events_pb2.AuthRequestQueuedMessage(
        auth_request_id=auth_request_id,
        restaurant_id="rest-123",
        created_at=int(time.time()),
    )

    # Serialize and base64 encode
    message_bytes = queued_msg.SerializeToString()
    message_body = base64.b64encode(message_bytes).decode('utf-8')

    await sqs_client.send_message(
        QueueUrl=test_queue,
        MessageBody=message_body,
        MessageGroupId="test-group",
        MessageDeduplicationId=auth_request_id,
    )

    # Use the sqs_client fixture instead of creating a new session
    consumer._sqs_client = sqs_client

    # Process messages (should receive and process the message)
    await consumer.process_messages()

    # Verify message was processed
    assert len(processed_messages) == 1
    assert processed_messages[0]["auth_request_id"] == auth_request_id
    assert processed_messages[0]["receive_count"] == 1

    # Verify message was deleted from queue
    response = await sqs_client.receive_message(
        QueueUrl=test_queue,
        MaxNumberOfMessages=10,
        WaitTimeSeconds=1,
    )
    messages = response.get("Messages", [])
    assert len(messages) == 0  # Queue should be empty


@pytest.mark.asyncio
async def test_sqs_consumer_handles_multiple_messages(sqs_client, test_queue):
    """Test processing multiple messages in sequence."""
    processed_messages = []

    async def message_handler(message_data):
        processed_messages.append(message_data["auth_request_id"])

    consumer = SQSConsumer(
        queue_url=test_queue,
        batch_size=5,  # Can receive up to 5 messages
        wait_time_seconds=5,
        visibility_timeout=30,
        aws_region=AWS_REGION,
        aws_endpoint_url=LOCALSTACK_ENDPOINT,
        message_handler=message_handler,
    )

    # Send multiple messages
    import time
    message_ids = []
    for i in range(3):
        auth_request_id = f"auth-req-{uuid.uuid4().hex}"
        message_ids.append(auth_request_id)

        # Create protobuf message
        queued_msg = events_pb2.AuthRequestQueuedMessage(
            auth_request_id=auth_request_id,
            restaurant_id="rest-123",
            created_at=int(time.time()),
        )

        # Serialize and base64 encode
        message_bytes = queued_msg.SerializeToString()
        message_body = base64.b64encode(message_bytes).decode('utf-8')

        await sqs_client.send_message(
            QueueUrl=test_queue,
            MessageBody=message_body,
            MessageGroupId="test-group",
            MessageDeduplicationId=auth_request_id,
        )

    # Use the sqs_client fixture instead of creating a new session
    consumer._sqs_client = sqs_client

    # Process messages (FIFO queue processes one at a time per group)
    # We need to call process_messages multiple times
    for _ in range(3):
        await consumer.process_messages()

    # Verify all messages were processed
    assert len(processed_messages) == 3
    for msg_id in message_ids:
        assert msg_id in processed_messages


@pytest.mark.asyncio
async def test_sqs_consumer_retry_on_handler_failure(sqs_client, test_queue):
    """Test that failed messages remain in queue for retry."""
    attempt_count = 0

    async def failing_handler(message_data):
        nonlocal attempt_count
        attempt_count += 1
        raise ValueError("Simulated processing error")

    consumer = SQSConsumer(
        queue_url=test_queue,
        batch_size=1,
        wait_time_seconds=1,
        visibility_timeout=2,  # Short timeout for faster retry
        aws_region=AWS_REGION,
        aws_endpoint_url=LOCALSTACK_ENDPOINT,
        message_handler=failing_handler,
    )

    # Send a test message
    import time
    auth_request_id = f"auth-req-{uuid.uuid4().hex}"

    # Create protobuf message
    queued_msg = events_pb2.AuthRequestQueuedMessage(
        auth_request_id=auth_request_id,
        restaurant_id="rest-123",
        created_at=int(time.time()),
    )

    # Serialize and base64 encode
    message_bytes = queued_msg.SerializeToString()
    message_body = base64.b64encode(message_bytes).decode('utf-8')

    await sqs_client.send_message(
        QueueUrl=test_queue,
        MessageBody=message_body,
        MessageGroupId="test-group",
        MessageDeduplicationId=auth_request_id,
    )

    # Use the sqs_client fixture instead of creating a new session
    consumer._sqs_client = sqs_client

    # First attempt - should fail
    await consumer.process_messages()
    assert attempt_count == 1

    # Wait for visibility timeout to expire
    await asyncio.sleep(3)

    # Second attempt - should receive same message again
    await consumer.process_messages()
    assert attempt_count == 2


@pytest.mark.asyncio
async def test_sqs_consumer_handles_malformed_messages(sqs_client, test_queue):
    """Test that malformed messages are deleted (not retried)."""
    processed_messages = []

    async def message_handler(message_data):
        processed_messages.append(message_data)

    consumer = SQSConsumer(
        queue_url=test_queue,
        batch_size=1,
        wait_time_seconds=1,
        visibility_timeout=30,
        aws_region=AWS_REGION,
        aws_endpoint_url=LOCALSTACK_ENDPOINT,
        message_handler=message_handler,
    )

    # Send malformed message (invalid JSON)
    await sqs_client.send_message(
        QueueUrl=test_queue,
        MessageBody="invalid-json{{{",
        MessageGroupId="test-group",
        MessageDeduplicationId=f"msg-{uuid.uuid4().hex}",
    )

    # Use the sqs_client fixture instead of creating a new session
    consumer._sqs_client = sqs_client

    # Process messages
    await consumer.process_messages()

    # Handler should not have been called
    assert len(processed_messages) == 0

    # Malformed message should be deleted
    response = await sqs_client.receive_message(
        QueueUrl=test_queue,
        MaxNumberOfMessages=10,
        WaitTimeSeconds=1,
    )
    messages = response.get("Messages", [])
    assert len(messages) == 0


@pytest.mark.asyncio
async def test_sqs_consumer_no_messages_available(sqs_client, test_queue):
    """Test consumer behavior when no messages are available."""
    processed_messages = []

    async def message_handler(message_data):
        processed_messages.append(message_data)

    consumer = SQSConsumer(
        queue_url=test_queue,
        batch_size=1,
        wait_time_seconds=1,  # Short wait for testing
        visibility_timeout=30,
        aws_region=AWS_REGION,
        aws_endpoint_url=LOCALSTACK_ENDPOINT,
        message_handler=message_handler,
    )

    # Use the sqs_client fixture instead of creating a new session
    consumer._sqs_client = sqs_client

    # Process messages (queue is empty)
    await consumer.process_messages()

    # No messages should be processed
    assert len(processed_messages) == 0

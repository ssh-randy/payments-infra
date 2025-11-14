"""SQS fixtures for integration testing with LocalStack.

These fixtures provide:
- SQS client connected to LocalStack
- Test queue management (create, purge, cleanup)
- Message publishing helpers
"""

import asyncio
import base64
import json
import os
import sys
import uuid
from pathlib import Path
from typing import Any

import aioboto3
import pytest
import pytest_asyncio
from botocore.exceptions import ClientError

# Add shared proto directory to Python path
_shared_proto_path = Path(__file__).parent.parent.parent.parent.parent.parent / "shared" / "python"
if str(_shared_proto_path) not in sys.path:
    sys.path.insert(0, str(_shared_proto_path))

from payments_proto.payments.v1 import events_pb2

# Test queue configuration
TEST_QUEUE_NAME = "auth-requests-test.fifo"
TEST_DLQ_NAME = "auth-requests-test-dlq.fifo"

# LocalStack configuration
AWS_ENDPOINT_URL = os.getenv("AWS_ENDPOINT_URL", "http://localhost:4566")
AWS_REGION = os.getenv("AWS_REGION", "us-east-1")


@pytest_asyncio.fixture(scope="function")
async def sqs_client():
    """
    Create an SQS client connected to LocalStack.

    Scope: function - creates a fresh client for each test to avoid event loop conflicts.
    """
    session = aioboto3.Session()
    async with session.client(
        "sqs",
        region_name=AWS_REGION,
        endpoint_url=AWS_ENDPOINT_URL,
    ) as client:
        yield client


@pytest_asyncio.fixture(scope="function")
async def test_sqs_queue(sqs_client):
    """
    Create and manage a shared test SQS FIFO queue.

    This fixture:
    1. Creates the test queue if it doesn't exist
    2. Purges any existing messages before the test
    3. Yields the queue URL
    4. Purges messages after the test (cleanup)

    Scope: function - runs before/after each test to ensure clean state.

    Returns:
        str: Queue URL for the test queue
    """
    queue_url = None

    try:
        # Create the test queue (idempotent - returns existing if already created)
        response = await sqs_client.create_queue(
            QueueName=TEST_QUEUE_NAME,
            Attributes={
                "FifoQueue": "true",
                "ContentBasedDeduplication": "false",
                "MessageRetentionPeriod": "300",  # 5 minutes for tests
                "VisibilityTimeout": "30",
                "ReceiveMessageWaitTimeSeconds": "5",  # Shorter for tests
            },
        )
        queue_url = response["QueueUrl"]

        # Purge queue before test to ensure clean state
        try:
            await sqs_client.purge_queue(QueueUrl=queue_url)
            # Wait a moment for purge to complete
            await asyncio.sleep(1)
        except ClientError as e:
            # Purge can fail if queue was recently purged (60 second cooldown)
            # This is fine - queue is likely already empty
            if e.response["Error"]["Code"] != "PurgeQueueInProgress":
                raise

        yield queue_url

    finally:
        # Cleanup: Purge messages after test
        if queue_url:
            try:
                await sqs_client.purge_queue(QueueUrl=queue_url)
            except ClientError:
                # Ignore cleanup errors
                pass


@pytest_asyncio.fixture
async def publish_auth_request(sqs_client, test_sqs_queue):
    """
    Factory fixture that returns a function to publish auth request messages.

    Usage:
        await publish_auth_request(
            auth_request_id=uuid.uuid4(),
            message_group_id="test-group",
        )

    Returns:
        Callable: Async function to publish messages
    """
    async def _publish(
        auth_request_id: uuid.UUID,
        message_group_id: str = "test-group",
        message_deduplication_id: str | None = None,
        restaurant_id: str | None = None,
    ) -> dict[str, str]:
        """
        Publish an auth request message to the test queue.

        Args:
            auth_request_id: Authorization request ID
            message_group_id: FIFO message group ID (default: "test-group")
            message_deduplication_id: Optional deduplication ID (auto-generated if None)
            restaurant_id: Optional restaurant ID (defaults to test restaurant)

        Returns:
            dict: SQS response with MessageId
        """
        # Create protobuf message
        import time
        queued_msg = events_pb2.AuthRequestQueuedMessage(
            auth_request_id=str(auth_request_id),
            restaurant_id=restaurant_id or "rest_test_12345",
            created_at=int(time.time()),
        )

        # Serialize to bytes
        message_bytes = queued_msg.SerializeToString()

        # Base64 encode
        message_body = base64.b64encode(message_bytes).decode('utf-8')

        # Auto-generate deduplication ID if not provided
        if message_deduplication_id is None:
            message_deduplication_id = str(uuid.uuid4())

        response = await sqs_client.send_message(
            QueueUrl=test_sqs_queue,
            MessageBody=message_body,
            MessageGroupId=message_group_id,
            MessageDeduplicationId=message_deduplication_id,
        )

        return response

    return _publish


@pytest_asyncio.fixture
async def receive_messages(sqs_client, test_sqs_queue):
    """
    Factory fixture that returns a function to receive messages from the queue.

    Useful for verifying message visibility and testing retry scenarios.

    Returns:
        Callable: Async function to receive messages
    """
    async def _receive(
        max_messages: int = 1,
        wait_time_seconds: int = 2,
        visibility_timeout: int = 30,
    ) -> list[dict[str, Any]]:
        """
        Receive messages from the test queue.

        Args:
            max_messages: Maximum number of messages to receive (1-10)
            wait_time_seconds: Long polling wait time
            visibility_timeout: Message visibility timeout

        Returns:
            list: List of message dictionaries
        """
        response = await sqs_client.receive_message(
            QueueUrl=test_sqs_queue,
            MaxNumberOfMessages=max_messages,
            WaitTimeSeconds=wait_time_seconds,
            VisibilityTimeout=visibility_timeout,
            AttributeNames=["ApproximateReceiveCount", "MessageGroupId"],
            MessageAttributeNames=["All"],
        )

        return response.get("Messages", [])

    return _receive


@pytest_asyncio.fixture
async def delete_message(sqs_client, test_sqs_queue):
    """
    Factory fixture that returns a function to delete messages from the queue.

    Useful for cleanup in tests.

    Returns:
        Callable: Async function to delete a message
    """
    async def _delete(receipt_handle: str) -> None:
        """
        Delete a message from the queue.

        Args:
            receipt_handle: SQS receipt handle from received message
        """
        await sqs_client.delete_message(
            QueueUrl=test_sqs_queue,
            ReceiptHandle=receipt_handle,
        )

    return _delete


@pytest_asyncio.fixture
async def get_queue_attributes(sqs_client, test_sqs_queue):
    """
    Factory fixture that returns a function to get queue attributes.

    Useful for verifying message counts, DLQ stats, etc.

    Returns:
        Callable: Async function to get queue attributes
    """
    async def _get_attributes() -> dict[str, str]:
        """
        Get all queue attributes.

        Returns:
            dict: Queue attributes including message counts
        """
        response = await sqs_client.get_queue_attributes(
            QueueUrl=test_sqs_queue,
            AttributeNames=["All"],
        )

        return response.get("Attributes", {})

    return _get_attributes

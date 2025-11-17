"""Integration tests for outbox processor with real database and LocalStack SQS."""

import asyncio
import base64
import os
import uuid

import boto3
import pytest
import pytest_asyncio

from payments_proto.payments.v1.events_pb2 import AuthRequestQueuedMessage, VoidRequestQueuedMessage

from authorization_api.infrastructure.outbox import write_outbox_message
from authorization_api.infrastructure.outbox_processor import process_outbox_batch
from authorization_api.domain.events import (
    create_auth_request_queued_message,
    create_void_request_queued_message,
)


# LocalStack configuration
LOCALSTACK_ENDPOINT = os.getenv("AWS_ENDPOINT_URL", "http://localhost:4566")
AUTH_REQUESTS_QUEUE_URL = "http://localhost:4566/000000000000/auth-requests.fifo"
VOID_REQUESTS_QUEUE_URL = "http://localhost:4566/000000000000/void-requests"


@pytest_asyncio.fixture(autouse=True)
async def cleanup_integration_test(db_pool, sqs_client):
    """Clean up after each integration test."""
    yield

    # Clean up database
    async with db_pool.acquire() as conn:
        await conn.execute("TRUNCATE auth_idempotency_keys CASCADE")
        await conn.execute("TRUNCATE outbox CASCADE")
        await conn.execute("TRUNCATE auth_request_state CASCADE")
        await conn.execute("TRUNCATE payment_events CASCADE")

    # Clean up SQS queues
    try:
        sqs_client.purge_queue(QueueUrl=AUTH_REQUESTS_QUEUE_URL)
    except Exception:
        pass

    try:
        sqs_client.purge_queue(QueueUrl=VOID_REQUESTS_QUEUE_URL)
    except Exception:
        pass


@pytest_asyncio.fixture(scope="module")
def sqs_client():
    """Create SQS client for LocalStack."""
    client = boto3.client(
        "sqs",
        endpoint_url=LOCALSTACK_ENDPOINT,
        region_name="us-east-1",
        aws_access_key_id="test",
        aws_secret_access_key="test",
    )

    # Ensure queues exist
    try:
        # Check if queues exist, create if not
        queues = client.list_queues()
        existing_queue_urls = queues.get("QueueUrls", [])

        if AUTH_REQUESTS_QUEUE_URL not in existing_queue_urls:
            client.create_queue(
                QueueName="auth-requests.fifo",
                Attributes={
                    "FifoQueue": "true",
                    "ContentBasedDeduplication": "false",
                },
            )

        if VOID_REQUESTS_QUEUE_URL not in existing_queue_urls:
            client.create_queue(QueueName="void-requests")

    except Exception as e:
        print(f"Warning: Could not verify SQS queues: {e}")

    yield client

    # Cleanup: purge queues after tests
    try:
        client.purge_queue(QueueUrl=AUTH_REQUESTS_QUEUE_URL)
        client.purge_queue(QueueUrl=VOID_REQUESTS_QUEUE_URL)
    except Exception as e:
        print(f"Warning: Could not purge queues: {e}")


@pytest.mark.asyncio
@pytest.mark.integration
async def test_outbox_processor_sends_auth_request_to_sqs(
    db_pool, sqs_client, test_restaurant_id
):
    """Test that outbox processor sends auth request messages to SQS."""
    # Create test data
    auth_request_id = uuid.uuid4()

    # Write message to outbox using the pool
    async with db_pool.acquire() as conn:
        payload = create_auth_request_queued_message(auth_request_id, test_restaurant_id)
        await write_outbox_message(
            conn,
            aggregate_id=auth_request_id,
            message_type="auth_request_queued",
            payload=payload,
        )

    # Set environment variables for processor
    os.environ["AUTH_REQUESTS_QUEUE_URL"] = AUTH_REQUESTS_QUEUE_URL
    os.environ["VOID_REQUESTS_QUEUE_URL"] = VOID_REQUESTS_QUEUE_URL
    os.environ["AWS_ENDPOINT_URL"] = LOCALSTACK_ENDPOINT
    os.environ["AWS_ACCESS_KEY_ID"] = "test"
    os.environ["AWS_SECRET_ACCESS_KEY"] = "test"
    os.environ["DATABASE_URL"] = os.getenv("TEST_DATABASE_URL", "postgresql://postgres:password@localhost:5432/payment_events_test")

    # Reset SQS client cache
    from authorization_api.infrastructure import sqs_client as sqs_module
    sqs_module._sqs_client = None

    # Reset database pool cache to use test database
    from authorization_api.infrastructure import database
    database._pool = db_pool

    # Process outbox batch
    from authorization_api.infrastructure.outbox_processor import (
        process_outbox_batch as process_batch,
    )

    processed_count = await process_batch()

    # Verify message was processed
    assert processed_count == 1

    # Verify message was marked as processed in database
    async with db_pool.acquire() as conn:
        result = await conn.fetchrow(
            "SELECT processed_at FROM outbox WHERE aggregate_id = $1", auth_request_id
        )
        assert result["processed_at"] is not None

    # Verify message was sent to SQS
    # Wait a bit for message to appear
    await asyncio.sleep(0.5)

    response = sqs_client.receive_message(
        QueueUrl=AUTH_REQUESTS_QUEUE_URL,
        MaxNumberOfMessages=1,
        WaitTimeSeconds=1,
    )

    assert "Messages" in response
    assert len(response["Messages"]) == 1

    # Verify message content (decode base64)
    message_body_str = response["Messages"][0]["Body"]
    message_body = base64.b64decode(message_body_str)
    queued_msg = AuthRequestQueuedMessage()
    queued_msg.ParseFromString(message_body)

    assert queued_msg.auth_request_id == str(auth_request_id)
    assert queued_msg.restaurant_id == str(test_restaurant_id)

    # Cleanup: delete message from queue
    sqs_client.delete_message(
        QueueUrl=AUTH_REQUESTS_QUEUE_URL,
        ReceiptHandle=response["Messages"][0]["ReceiptHandle"],
    )


@pytest.mark.asyncio
@pytest.mark.integration
async def test_outbox_processor_sends_void_request_to_sqs(db_pool, sqs_client):
    """Test that outbox processor sends void request messages to SQS."""
    # Create test data
    auth_request_id = uuid.uuid4()
    restaurant_id = uuid.uuid4()
    reason = "customer_cancelled"

    # Write message to outbox
    async with db_pool.acquire() as conn:
        payload = create_void_request_queued_message(
            auth_request_id, restaurant_id, reason
        )
        await write_outbox_message(
            conn,
            aggregate_id=auth_request_id,
            message_type="void_request_queued",
            payload=payload,
        )

    # Set environment variables
    os.environ["AUTH_REQUESTS_QUEUE_URL"] = AUTH_REQUESTS_QUEUE_URL
    os.environ["VOID_REQUESTS_QUEUE_URL"] = VOID_REQUESTS_QUEUE_URL
    os.environ["AWS_ENDPOINT_URL"] = LOCALSTACK_ENDPOINT
    os.environ["AWS_ACCESS_KEY_ID"] = "test"
    os.environ["AWS_SECRET_ACCESS_KEY"] = "test"

    # Reset caches
    from authorization_api.infrastructure import sqs_client as sqs_module
    from authorization_api.infrastructure import database
    sqs_module._sqs_client = None
    database._pool = db_pool

    # Process outbox batch
    from authorization_api.infrastructure.outbox_processor import (
        process_outbox_batch as process_batch,
    )

    processed_count = await process_batch()

    # Verify message was processed
    assert processed_count == 1

    # Verify message was sent to SQS
    await asyncio.sleep(0.5)

    response = sqs_client.receive_message(
        QueueUrl=VOID_REQUESTS_QUEUE_URL,
        MaxNumberOfMessages=1,
        WaitTimeSeconds=1,
    )

    assert "Messages" in response
    assert len(response["Messages"]) == 1

    # Verify message content (decode base64)
    message_body_str = response["Messages"][0]["Body"]
    message_body = base64.b64decode(message_body_str)
    void_msg = VoidRequestQueuedMessage()
    void_msg.ParseFromString(message_body)

    assert void_msg.auth_request_id == str(auth_request_id)
    assert void_msg.restaurant_id == str(restaurant_id)
    assert void_msg.reason == reason

    # Cleanup
    sqs_client.delete_message(
        QueueUrl=VOID_REQUESTS_QUEUE_URL,
        ReceiptHandle=response["Messages"][0]["ReceiptHandle"],
    )


@pytest.mark.asyncio
@pytest.mark.integration
async def test_outbox_processor_handles_multiple_messages(
    db_pool, sqs_client, test_restaurant_id
):
    """Test that outbox processor handles multiple messages in a batch."""
    # Create multiple test messages
    auth_request_ids = [uuid.uuid4() for _ in range(5)]

    async with db_pool.acquire() as conn:
        for auth_request_id in auth_request_ids:
            payload = create_auth_request_queued_message(
                auth_request_id, test_restaurant_id
            )
            await write_outbox_message(
                conn,
                aggregate_id=auth_request_id,
                message_type="auth_request_queued",
                payload=payload,
            )

    # Set environment variables
    os.environ["AUTH_REQUESTS_QUEUE_URL"] = AUTH_REQUESTS_QUEUE_URL
    os.environ["VOID_REQUESTS_QUEUE_URL"] = VOID_REQUESTS_QUEUE_URL
    os.environ["AWS_ENDPOINT_URL"] = LOCALSTACK_ENDPOINT
    os.environ["AWS_ACCESS_KEY_ID"] = "test"
    os.environ["AWS_SECRET_ACCESS_KEY"] = "test"

    # Reset caches
    from authorization_api.infrastructure import sqs_client as sqs_module
    from authorization_api.infrastructure import database
    sqs_module._sqs_client = None
    database._pool = db_pool

    # Process outbox batch
    from authorization_api.infrastructure.outbox_processor import (
        process_outbox_batch as process_batch,
    )

    processed_count = await process_batch()

    # Verify all messages were processed
    assert processed_count == 5

    # Verify all messages are marked as processed
    async with db_pool.acquire() as conn:
        result = await conn.fetch(
            "SELECT COUNT(*) as count FROM outbox WHERE processed_at IS NOT NULL"
        )
        assert result[0]["count"] == 5

    # Verify messages were sent to SQS
    await asyncio.sleep(0.5)

    received_messages = []
    for _ in range(5):
        response = sqs_client.receive_message(
            QueueUrl=AUTH_REQUESTS_QUEUE_URL,
            MaxNumberOfMessages=1,
            WaitTimeSeconds=1,
        )
        if "Messages" in response:
            received_messages.extend(response["Messages"])
            # Delete message
            for msg in response["Messages"]:
                sqs_client.delete_message(
                    QueueUrl=AUTH_REQUESTS_QUEUE_URL,
                    ReceiptHandle=msg["ReceiptHandle"],
                )

    assert len(received_messages) == 5


@pytest.mark.asyncio
@pytest.mark.integration
async def test_outbox_processor_skips_processed_messages(
    db_pool, sqs_client, test_restaurant_id
):
    """Test that outbox processor skips already processed messages."""
    # Create test message
    auth_request_id = uuid.uuid4()
    payload = create_auth_request_queued_message(auth_request_id, test_restaurant_id)

    # Write message and mark as processed
    async with db_pool.acquire() as conn:
        await write_outbox_message(
            conn,
            aggregate_id=auth_request_id,
            message_type="auth_request_queued",
            payload=payload,
        )

        await conn.execute(
            "UPDATE outbox SET processed_at = NOW() WHERE aggregate_id = $1",
            auth_request_id,
        )

    # Set environment variables
    os.environ["AUTH_REQUESTS_QUEUE_URL"] = AUTH_REQUESTS_QUEUE_URL
    os.environ["VOID_REQUESTS_QUEUE_URL"] = VOID_REQUESTS_QUEUE_URL
    os.environ["AWS_ENDPOINT_URL"] = LOCALSTACK_ENDPOINT
    os.environ["AWS_ACCESS_KEY_ID"] = "test"
    os.environ["AWS_SECRET_ACCESS_KEY"] = "test"

    # Reset caches
    from authorization_api.infrastructure import sqs_client as sqs_module
    from authorization_api.infrastructure import database
    sqs_module._sqs_client = None
    database._pool = db_pool

    # Process outbox batch
    from authorization_api.infrastructure.outbox_processor import (
        process_outbox_batch as process_batch,
    )

    processed_count = await process_batch()

    # Verify no messages were processed
    assert processed_count == 0

    # Verify no messages in SQS
    await asyncio.sleep(0.5)

    response = sqs_client.receive_message(
        QueueUrl=AUTH_REQUESTS_QUEUE_URL,
        MaxNumberOfMessages=1,
        WaitTimeSeconds=1,
    )

    assert "Messages" not in response or len(response.get("Messages", [])) == 0

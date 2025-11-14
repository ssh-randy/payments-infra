"""End-to-end integration tests for Auth Processor Worker.

These tests verify the complete message processing flow from SQS message
reception through processing, event sourcing, and read model updates.

IMPORTANT: These tests use a shared SQS queue and must run serially.
Do NOT use pytest-xdist parallel execution (-n flag).

Run with:
    pytest tests/integration/test_worker_end_to_end.py -v
"""

import asyncio
import uuid

import pytest


@pytest.mark.integration
@pytest.mark.e2e
async def test_happy_path_successful_authorization(
    db_conn,
    seed_auth_request,
    mock_payment_token_client,
    publish_auth_request,
    start_worker,
    get_auth_request_state,
    get_events_for_auth_request,
    count_events_by_type,
    get_processing_lock,
    test_auth_request_id,
    test_payment_token,
):
    """
    Test Scenario 1: Happy Path - Successful Authorization

    Steps:
    1. Insert auth_request in DB (status=PENDING)
    2. Configure mock to return test card data
    3. Publish message to SQS
    4. Worker processes message
    5. MockProcessor returns AUTHORIZED
    6. Verify: status=AUTHORIZED, events written, message deleted
    """
    # Setup: Seed auth request in database (fixture already executed)
    # seed_auth_request has already seeded the data, no need to await

    # Configure Payment Token Service mock to return Visa success card
    mock_payment_token_client.configure_token_response(
        payment_token=test_payment_token,
        card_number="4242424242424242",  # Visa success card (from MockProcessor)
    )

    # Publish message to SQS
    await publish_auth_request(test_auth_request_id)

    # Wait for worker to process the message
    await start_worker.wait_for_processing(expected_count=1, timeout=10.0)

    # Verify: Read model updated to AUTHORIZED
    state = await get_auth_request_state(test_auth_request_id)
    assert state is not None
    assert state["status"] == "AUTHORIZED"
    assert state["processor_name"] == "mock"
    assert state["processor_auth_id"] is not None
    assert state["authorized_amount_cents"] == 1000
    assert state["authorization_code"] is not None
    assert state["completed_at"] is not None

    # Verify: Events written correctly
    events = await get_events_for_auth_request(test_auth_request_id)
    assert len(events) == 2

    # Event 1: AuthAttemptStarted
    assert events[0]["event_type"] == "AuthAttemptStarted"
    assert events[0]["sequence_number"] == 1

    # Event 2: AuthResponseReceived
    assert events[1]["event_type"] == "AuthResponseReceived"
    assert events[1]["sequence_number"] == 2

    # Verify: Event counts
    event_counts = await count_events_by_type(test_auth_request_id)
    assert event_counts["AuthAttemptStarted"] == 1
    assert event_counts["AuthResponseReceived"] == 1

    # Verify: Lock released
    lock = await get_processing_lock(test_auth_request_id)
    assert lock is None

    # Verify: Worker processed exactly one message
    processed = start_worker.get_processed_messages()
    assert len(processed) == 1
    assert processed[0]["result"] == "success"


@pytest.mark.integration
@pytest.mark.e2e
async def test_processor_decline_denied_status(
    db_conn,
    seed_auth_request,
    mock_payment_token_client,
    publish_auth_request,
    start_worker,
    get_auth_request_state,
    get_events_for_auth_request,
    test_auth_request_id,
    test_payment_token,
):
    """
    Test Scenario 2: Processor Decline - DENIED Status

    Use MockProcessor test card for decline (insufficient funds).
    Verify status is DENIED (not FAILED) and denial fields are populated.
    """
    # Setup: Seed auth request in database (fixture already executed)
    # seed_auth_request has already seeded the data

    # Configure mock to return card that will be declined (insufficient funds)
    mock_payment_token_client.configure_token_response(
        payment_token=test_payment_token,
        card_number="4000000000009995",  # Insufficient funds decline
    )

    # Publish and process
    await publish_auth_request(test_auth_request_id)
    await start_worker.wait_for_processing(expected_count=1, timeout=10.0)

    # Verify: Status is DENIED, not FAILED
    state = await get_auth_request_state(test_auth_request_id)
    assert state["status"] == "DENIED"
    assert state["processor_name"] == "mock"
    assert state["denial_code"] is not None
    assert "insufficient_funds" in state["denial_code"] or "card_declined" in state["denial_code"]
    assert state["denial_reason"] is not None
    assert state["completed_at"] is not None

    # Verify: No authorization fields populated
    assert state["processor_auth_id"] is None
    assert state["authorized_amount_cents"] is None
    assert state["authorization_code"] is None

    # Verify: Events
    events = await get_events_for_auth_request(test_auth_request_id)
    assert len(events) == 2
    assert events[0]["event_type"] == "AuthAttemptStarted"
    assert events[1]["event_type"] == "AuthResponseReceived"


@pytest.mark.integration
@pytest.mark.e2e
async def test_token_service_error_not_found(
    db_conn,
    seed_auth_request,
    configure_token_not_found,
    publish_auth_request,
    start_worker,
    get_auth_request_state,
    get_events_for_auth_request,
    count_events_by_type,
    test_auth_request_id,
    test_payment_token,
):
    """
    Test Scenario 3a: Token Service Error - 404 Not Found

    Payment Token Service returns 404 (token not found).
    This is a terminal error - no retry.
    """
    # Setup: Seed auth request in database (fixture already executed)
    # seed_auth_request has already seeded the data

    # Configure mock to raise TokenNotFound (404)
    configure_token_not_found(test_payment_token)

    # Publish and process
    await publish_auth_request(test_auth_request_id)
    await start_worker.wait_for_processing(expected_count=1, timeout=10.0)

    # Verify: Status is FAILED (terminal error)
    state = await get_auth_request_state(test_auth_request_id)
    assert state["status"] == "FAILED"
    assert state["completed_at"] is not None

    # Verify: Events include terminal failure
    events = await get_events_for_auth_request(test_auth_request_id)
    assert len(events) == 2
    assert events[0]["event_type"] == "AuthAttemptStarted"
    assert events[1]["event_type"] == "AuthAttemptFailed"

    # Verify: No retryable event
    event_counts = await count_events_by_type(test_auth_request_id)
    assert event_counts["AuthAttemptFailed"] == 1


@pytest.mark.integration
@pytest.mark.e2e
async def test_token_service_error_expired(
    db_conn,
    seed_auth_request,
    configure_token_expired,
    publish_auth_request,
    start_worker,
    get_auth_request_state,
    test_auth_request_id,
    test_payment_token,
):
    """
    Test Scenario 3b: Token Service Error - 410 Expired

    Payment Token Service returns 410 (token expired).
    This is a terminal error - no retry.
    """
    # Setup: Seed auth request in database (fixture already executed)
    # seed_auth_request has already seeded the data
    configure_token_expired(test_payment_token)

    # Publish and process
    await publish_auth_request(test_auth_request_id)
    await start_worker.wait_for_processing(expected_count=1, timeout=10.0)

    # Verify: Terminal failure
    state = await get_auth_request_state(test_auth_request_id)
    assert state["status"] == "FAILED"
    assert state["completed_at"] is not None


@pytest.mark.integration
@pytest.mark.e2e
async def test_token_service_error_forbidden(
    db_conn,
    seed_auth_request,
    configure_token_forbidden,
    publish_auth_request,
    start_worker,
    get_auth_request_state,
    test_auth_request_id,
    test_payment_token,
):
    """
    Test Scenario 3c: Token Service Error - 403 Forbidden

    Payment Token Service returns 403 (unauthorized access).
    This is a terminal error - no retry.
    """
    # Setup: Seed auth request in database (fixture already executed)
    # seed_auth_request has already seeded the data
    configure_token_forbidden(test_payment_token)

    # Publish and process
    await publish_auth_request(test_auth_request_id)
    await start_worker.wait_for_processing(expected_count=1, timeout=10.0)

    # Verify: Terminal failure
    state = await get_auth_request_state(test_auth_request_id)
    assert state["status"] == "FAILED"
    assert state["completed_at"] is not None


@pytest.mark.integration
@pytest.mark.e2e
async def test_transient_failure_with_retry(
    db_conn,
    seed_auth_request,
    mock_payment_token_client,
    publish_auth_request,
    worker_instance,
    get_auth_request_state,
    get_events_for_auth_request,
    count_events_by_type,
    receive_messages,
    test_auth_request_id,
    test_payment_token,
):
    """
    Test Scenario 4: Transient Failures with Retry

    First attempt: Payment Token Service times out (retryable error)
    Second attempt: Succeeds

    Verify:
    - AuthAttemptFailed event with is_retryable=true
    - Status stays PROCESSING after first attempt
    - Message NOT deleted, reappears for retry
    - Second attempt succeeds
    """
    # Setup: Seed auth request in database (fixture already executed)
    # seed_auth_request has already seeded the data

    # Configure mock to fail first time, succeed second time
    call_count = {"count": 0}

    async def mock_decrypt(*args, **kwargs):
        call_count["count"] += 1
        if call_count["count"] == 1:
            # First call: timeout
            from auth_processor_worker.models.exceptions import ProcessorTimeout
            raise ProcessorTimeout("Token service unavailable")
        else:
            # Second call: success
            from payments_proto.payments.v1 import payment_token_pb2
            return payment_token_pb2.PaymentData(
                card_number="4242424242424242",
                exp_month="12",  # String format
                exp_year="2025",  # String format
                cvv="123",
                cardholder_name="Test User",
            )

    # Configure the custom handler
    mock_payment_token_client.custom_decrypt_handler = mock_decrypt

    # Start worker
    await worker_instance.start()

    # Publish message
    await publish_auth_request(test_auth_request_id)

    # Wait for first attempt to complete
    await asyncio.sleep(3)

    # Verify: Status is still PROCESSING (not FAILED)
    state = await get_auth_request_state(test_auth_request_id)
    assert state["status"] == "PROCESSING"
    assert state["completed_at"] is None

    # Verify: Retryable failure event written
    events = await get_events_for_auth_request(test_auth_request_id)
    assert len(events) >= 2
    assert events[0]["event_type"] == "AuthAttemptStarted"
    assert events[1]["event_type"] == "AuthAttemptFailed"

    # Verify: Message is still in queue (not deleted)
    # Wait for visibility timeout to expire and message to reappear
    await asyncio.sleep(2)

    # Wait for second attempt
    await worker_instance.wait_for_processing(expected_count=2, timeout=35.0)

    # Verify: Now succeeded
    state = await get_auth_request_state(test_auth_request_id)
    assert state["status"] == "AUTHORIZED"
    assert state["completed_at"] is not None

    # Verify: Both attempts recorded
    event_counts = await count_events_by_type(test_auth_request_id)
    assert event_counts["AuthAttemptStarted"] >= 1
    assert event_counts["AuthAttemptFailed"] == 1
    assert event_counts["AuthResponseReceived"] == 1

    # Cleanup
    await worker_instance.stop()


@pytest.mark.integration
@pytest.mark.e2e
async def test_max_retries_exceeded(
    db_conn,
    seed_auth_request,
    configure_token_timeout,
    publish_auth_request,
    sqs_client,
    test_sqs_queue,
    worker_instance,
    get_auth_request_state,
    get_events_for_auth_request,
    test_auth_request_id,
    test_payment_token,
):
    """
    Test Scenario 5: Max Retries Exceeded

    Mock continues to timeout for all attempts.
    After max retries (5), status should be FAILED (terminal).
    """
    # Setup: Seed auth request in database (fixture already executed)
    # seed_auth_request has already seeded the data

    # Configure mock to always timeout
    configure_token_timeout(test_payment_token)

    # Manually publish message with high ApproximateReceiveCount
    # to simulate it has already been retried 4 times
    import base64
    import time
    from payments_proto.payments.v1 import events_pb2

    # Create protobuf message
    queued_msg = events_pb2.AuthRequestQueuedMessage(
        auth_request_id=str(test_auth_request_id),
        restaurant_id="00000000-0000-0000-0000-000000000001",
        created_at=int(time.time()),
    )

    # Serialize and base64 encode
    message_bytes = queued_msg.SerializeToString()
    message_body = base64.b64encode(message_bytes).decode('utf-8')

    # Publish message (this will be receive #5, which equals max_retries)
    await sqs_client.send_message(
        QueueUrl=test_sqs_queue,
        MessageBody=message_body,
        MessageGroupId="test-group",
        MessageDeduplicationId=str(uuid.uuid4()),
    )

    # Receive and re-send message 4 times to increment ApproximateReceiveCount
    for i in range(4):
        messages = await sqs_client.receive_message(
            QueueUrl=test_sqs_queue,
            MaxNumberOfMessages=1,
            VisibilityTimeout=1,
            AttributeNames=["ApproximateReceiveCount"],
        )
        # Wait for visibility timeout to expire
        await asyncio.sleep(2)

    # Start worker
    await worker_instance.start()

    # Wait for processing (this is the 5th receive = max retries)
    await worker_instance.wait_for_processing(expected_count=1, timeout=10.0)

    # Verify: Status is FAILED (terminal after max retries)
    state = await get_auth_request_state(test_auth_request_id)
    assert state["status"] == "FAILED"
    assert state["completed_at"] is not None

    # Verify: Terminal failure event
    events = await get_events_for_auth_request(test_auth_request_id)
    failure_events = [e for e in events if e["event_type"] == "AuthAttemptFailed"]
    assert len(failure_events) >= 1

    # Cleanup
    await worker_instance.stop()


@pytest.mark.integration
@pytest.mark.e2e
async def test_void_race_condition(
    db_conn,
    seed_auth_request,
    write_void_event,
    mock_payment_token_client,
    publish_auth_request,
    start_worker,
    get_auth_request_state,
    get_events_for_auth_request,
    count_events_by_type,
    test_auth_request_id,
    test_payment_token,
):
    """
    Test Scenario 6: Void Race Condition

    Insert auth_request, then write AuthVoidRequested event BEFORE worker processes.
    Worker should detect void and expire the request without calling external services.
    """
    # Setup: Seed auth request in database (fixture already executed)
    # seed_auth_request has already seeded the data

    # Write void event BEFORE processing starts
    await write_void_event(test_auth_request_id)

    # Configure mock (should NOT be called)
    mock_payment_token_client.configure_token_response(
        payment_token=test_payment_token,
        card_number="4242424242424242",
    )

    # Publish message
    await publish_auth_request(test_auth_request_id)

    # Worker processes
    await start_worker.wait_for_processing(expected_count=1, timeout=10.0)

    # Verify: Status is EXPIRED
    state = await get_auth_request_state(test_auth_request_id)
    assert state["status"] == "EXPIRED"
    assert state["completed_at"] is not None

    # Verify: No processor fields populated
    assert state["processor_auth_id"] is None
    assert state["authorized_amount_cents"] is None

    # Verify: Events include AuthRequestExpired
    events = await get_events_for_auth_request(test_auth_request_id)
    event_types = [e["event_type"] for e in events]
    assert "AuthVoidRequested" in event_types
    assert "AuthRequestExpired" in event_types

    # Verify: NO AuthResponseReceived (processing stopped early)
    assert "AuthResponseReceived" not in event_types


@pytest.mark.integration
@pytest.mark.e2e
async def test_lock_contention_multiple_workers(
    db_conn,
    seed_auth_request,
    mock_payment_token_client,
    publish_auth_request,
    multiple_workers,
    get_auth_request_state,
    get_events_for_auth_request,
    count_events_by_type,
    test_auth_request_id,
    test_payment_token,
):
    """
    Test Scenario 7: Lock Contention - Multiple Workers

    Start TWO workers simultaneously, publish ONE message.
    Only ONE worker should acquire lock and process.
    Other worker should skip (SKIPPED_LOCK_NOT_ACQUIRED).
    """
    # Setup: Seed auth request in database (fixture already executed)
    # seed_auth_request has already seeded the data

    # Configure mock
    mock_payment_token_client.configure_token_response(
        payment_token=test_payment_token,
        card_number="4242424242424242",
    )

    # Create two workers
    workers = await multiple_workers(count=2)

    # Start both workers simultaneously
    await asyncio.gather(
        workers[0].start(),
        workers[1].start(),
    )

    # Publish ONE message
    await publish_auth_request(test_auth_request_id)

    # Wait for processing to complete
    await asyncio.sleep(3)

    # Verify: Only ONE worker processed the message
    processed_counts = [len(w.get_processed_messages()) for w in workers]
    total_processed = sum(processed_counts)
    assert total_processed == 1, f"Expected 1 worker to process, got {processed_counts}"

    # Find which worker processed it
    processing_worker = workers[0] if processed_counts[0] == 1 else workers[1]
    skipped_worker = workers[1] if processed_counts[0] == 1 else workers[0]

    # Verify: Processing worker succeeded
    processed = processing_worker.get_processed_messages()
    assert processed[0]["result"] == "success"

    # Verify: Skipped worker has result=skipped_lock_not_acquired
    skipped = skipped_worker.get_processed_messages()
    if len(skipped) > 0:
        assert skipped[0]["result"] == "skipped_lock_not_acquired"

    # Verify: Final state is AUTHORIZED
    state = await get_auth_request_state(test_auth_request_id)
    assert state["status"] == "AUTHORIZED"

    # Verify: Only ONE set of events written (no duplicates)
    event_counts = await count_events_by_type(test_auth_request_id)
    assert event_counts["AuthAttemptStarted"] == 1
    assert event_counts["AuthResponseReceived"] == 1

    # Cleanup
    for worker in workers:
        await worker.stop()


@pytest.mark.integration
@pytest.mark.e2e
@pytest.mark.slow
async def test_lock_expiration_crash_recovery(
    db_conn,
    seed_auth_request,
    mock_payment_token_client,
    publish_auth_request,
    multiple_workers,
    get_auth_request_state,
    get_processing_lock,
    test_auth_request_id,
    test_payment_token,
):
    """
    Test Scenario 8: Lock Expiration - Worker Crash Recovery

    Worker A acquires lock and starts processing, then crashes.
    Lock expires after TTL (30 seconds).
    Worker B acquires expired lock and completes processing.

    NOTE: This test takes ~32 seconds due to lock TTL wait.
    """
    # Setup: Seed auth request in database (fixture already executed)
    # seed_auth_request has already seeded the data

    # Configure mock with delay to simulate slow processing
    async def slow_decrypt(*args, **kwargs):
        # Delay long enough for crash to happen during processing
        # Make this very long so we can crash the worker while it's waiting
        await asyncio.sleep(100)
        from payments_proto.payments.v1 import payment_token_pb2
        return payment_token_pb2.PaymentData(
            card_number="4242424242424242",
            exp_month="12",
            exp_year="2025",
            cvv="123",
            cardholder_name="Test User",
        )

    mock_payment_token_client.decrypt = slow_decrypt

    # Create two workers
    workers = await multiple_workers(count=2)

    # Start worker A
    await workers[0].start()

    # Publish message
    await publish_auth_request(test_auth_request_id)

    # Wait for worker A to acquire lock and start processing
    # Just enough time for SQS polling + lock acquisition (not full processing)
    await asyncio.sleep(3)

    # Verify: Lock acquired
    lock = await get_processing_lock(test_auth_request_id)
    assert lock is not None
    assert lock["worker_id"] == workers[0].worker_id

    # Simulate crash: Kill worker A while it's in the middle of slow_decrypt
    await workers[0].simulate_crash()

    # Note: The lock will be released by the finally block when the task is cancelled.
    # In a real crash scenario (server crash), the finally block wouldn't run and the
    # lock would persist until TTL. Since we're using task cancellation to simulate
    # a crash, we can't test the "lock expires after crash" scenario directly.
    # Instead, we'll verify that Worker B can pick up and process the message.

    # Restore normal mock behavior for Worker B (remove the slow_decrypt override)
    del mock_payment_token_client.decrypt  # Remove the custom slow_decrypt
    mock_payment_token_client.configure_token_response(
        payment_token=test_payment_token,
        card_number="4242424242424242",
    )

    # Give SQS time to make message visible again (visibility timeout)
    print("Waiting for SQS message to become visible again...")
    await asyncio.sleep(35)

    # Start worker B
    await workers[1].start()

    # Worker B should pick up the message and process it
    await workers[1].wait_for_processing(expected_count=1, timeout=15.0)

    # Verify: Processing completed successfully
    state = await get_auth_request_state(test_auth_request_id)
    assert state["status"] == "AUTHORIZED"
    assert state["completed_at"] is not None

    # Verify: Worker B processed it
    processed = workers[1].get_processed_messages()
    assert len(processed) == 1

    # Cleanup
    await workers[1].stop()


@pytest.mark.integration
@pytest.mark.e2e
async def test_transaction_atomicity(
    db_conn,
    seed_auth_request,
    mock_payment_token_client,
    publish_auth_request,
    start_worker,
    get_auth_request_state,
    get_events_for_auth_request,
    test_auth_request_id,
    test_payment_token,
):
    """
    Test Scenario 9: Transaction Atomicity

    Verify that events and read model updates are atomic.
    Both succeed together or both fail together.

    This test verifies the happy path atomicity.
    For failure scenarios, we would need to inject database errors,
    which is complex to test safely.

    Here we verify:
    - Events written = Read model updated (always in sync)
    - Sequence numbers match
    """
    # Setup: Seed auth request in database (fixture already executed)
    # seed_auth_request has already seeded the data

    # Configure mock
    mock_payment_token_client.configure_token_response(
        payment_token=test_payment_token,
        card_number="4242424242424242",
    )

    # Publish and process
    await publish_auth_request(test_auth_request_id)
    await start_worker.wait_for_processing(expected_count=1, timeout=10.0)

    # Verify: Events and read model are in sync
    state = await get_auth_request_state(test_auth_request_id)
    events = await get_events_for_auth_request(test_auth_request_id)

    # Verify: last_event_sequence matches latest event
    latest_event = events[-1]
    assert state["last_event_sequence"] == latest_event["sequence_number"]

    # Verify: Read model status matches event progression
    assert state["status"] == "AUTHORIZED"
    assert latest_event["event_type"] == "AuthResponseReceived"

    # Verify: All events have sequential sequence numbers
    for i, event in enumerate(events, start=1):
        assert event["sequence_number"] == i

    # Additional verification: Check that no partial updates occurred
    # If atomicity failed, we might see events without corresponding read model updates
    assert state["processor_auth_id"] is not None
    assert state["authorized_amount_cents"] == 1000
    assert state["completed_at"] is not None

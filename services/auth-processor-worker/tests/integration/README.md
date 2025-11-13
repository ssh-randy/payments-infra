# Integration Tests - Auth Processor Worker

This directory contains end-to-end integration tests for the Auth Processor Worker that verify the complete message processing flow.

## Test Infrastructure

### Real Components
- **PostgreSQL**: Real database with Alembic migrations
- **LocalStack SQS**: Real SQS FIFO queues for message processing
- **MockProcessor**: Deterministic payment processor with test card behaviors
- **Worker**: Real worker instance with full orchestration logic

### Mocked Components
- **Payment Token Service**: Mocked via `mock_payment_token_client` fixture to return configurable card data

## Test Fixtures

All fixtures are located in `tests/integration/fixtures/`:

### SQS Fixtures (`sqs_fixtures.py`)
- `sqs_client`: AWS SQS client connected to LocalStack
- `test_sqs_queue`: Shared FIFO test queue with automatic cleanup
- `publish_auth_request`: Factory to publish auth request messages
- `receive_messages`: Helper to receive messages from queue
- `get_queue_attributes`: Helper to inspect queue state

### Payment Token Fixtures (`token_fixtures.py`)
- `mock_payment_token_client`: Main mock that patches PaymentTokenServiceClient
- `configure_token_success`: Quick helper for successful token responses
- `configure_token_not_found`: Helper for 404 responses
- `configure_token_expired`: Helper for 410 responses
- `configure_token_forbidden`: Helper for 403 responses
- `configure_token_timeout`: Helper for 5xx/timeout responses

### Worker Fixtures (`worker_fixtures.py`)
- `worker_instance`: Single worker instance with lifecycle control
- `multiple_workers`: Factory for creating multiple concurrent workers
- `start_worker`: Auto-started worker with cleanup

### Helper Fixtures (in `tests/conftest.py`)
- `write_void_event`: Write void events to test race conditions
- `get_events_for_auth_request`: Retrieve all events for verification
- `get_auth_request_state`: Get read model state
- `seed_restaurant_config`: Seed custom restaurant configs
- `get_processing_lock`: Check lock state
- `count_events_by_type`: Count events by type

## Running Tests

### Prerequisites

1. Start required services:
```bash
cd ../../infrastructure/docker
docker-compose up -d postgres localstack
```

2. Initialize LocalStack:
```bash
cd ../../../scripts
./init_localstack_test.sh
```

### Running All Integration Tests

```bash
cd services/auth-processor-worker
poetry run pytest tests/integration -v
```

### Running Specific Tests

```bash
# Run a specific test file
poetry run pytest tests/integration/test_worker_end_to_end.py -v

# Run a specific test
poetry run pytest tests/integration/test_worker_end_to_end.py::test_happy_path_successful_authorization -v

# Run with more verbose output
poetry run pytest tests/integration -vv -s
```

### Important Notes

- ⚠️ **Run Serially**: Integration tests MUST run serially (not in parallel) because they share a test SQS queue
- ⚠️ **Do NOT use `-n` flag** (pytest-xdist parallel execution) for integration tests
- Tests are automatically marked with `@pytest.mark.integration` and `@pytest.mark.serial`

## Writing New Tests

### Basic Test Structure

```python
import pytest

@pytest.mark.integration
async def test_my_scenario(
    db_conn,
    seed_auth_request,
    mock_payment_token_client,
    publish_auth_request,
    start_worker,
    get_auth_request_state,
    test_auth_request_id,
):
    # 1. Setup: Seed data and configure mocks
    await seed_auth_request
    mock_payment_token_client.configure_token_response(
        payment_token="pt_test_12345678",
        card_number="4242424242424242",  # Visa success card
    )

    # 2. Act: Publish message and wait for processing
    await publish_auth_request(test_auth_request_id)
    await start_worker.wait_for_processing(expected_count=1, timeout=10.0)

    # 3. Assert: Verify final state
    state = await get_auth_request_state(test_auth_request_id)
    assert state["status"] == "AUTHORIZED"
    assert state["processor_name"] == "mock"
```

### Testing Error Scenarios

```python
@pytest.mark.integration
async def test_token_not_found(
    db_conn,
    seed_auth_request,
    configure_token_not_found,  # Helper fixture
    publish_auth_request,
    start_worker,
    get_auth_request_state,
    test_auth_request_id,
):
    await seed_auth_request
    configure_token_not_found("pt_test_12345678")

    await publish_auth_request(test_auth_request_id)
    await start_worker.wait_for_processing(expected_count=1)

    state = await get_auth_request_state(test_auth_request_id)
    assert state["status"] == "FAILED"
```

### Testing Concurrency

```python
@pytest.mark.integration
async def test_lock_contention(
    db_conn,
    seed_auth_request,
    mock_payment_token_client,
    publish_auth_request,
    multiple_workers,
    test_auth_request_id,
):
    await seed_auth_request
    mock_payment_token_client.configure_default_response()

    # Create 3 workers
    workers = await multiple_workers(count=3)

    # Start all workers simultaneously
    for worker in workers:
        await worker.start()

    # Publish ONE message
    await publish_auth_request(test_auth_request_id)

    # Wait for processing
    await asyncio.sleep(2)

    # Only ONE worker should have processed it
    processed_counts = [len(w.get_processed_messages()) for w in workers]
    assert sum(processed_counts) == 1
```

## Test Scenarios to Implement

See issue **i-30mi** for the complete list of 9 test scenarios:

1. ✅ Happy Path - Successful Authorization
2. ✅ Processor Decline - DENIED Status
3. ✅ Token Service Errors (404, 410, 403)
4. ✅ Transient Failures with Retry
5. ✅ Max Retries Exceeded
6. ✅ Void Race Condition
7. ✅ Lock Contention - Multiple Workers
8. ✅ Lock Expiration - Worker Crash Recovery
9. ✅ Transaction Atomicity

## Debugging Tests

### View Worker Logs

Workers use structlog for logging. To see logs during tests:

```bash
pytest tests/integration -v -s --log-cli-level=DEBUG
```

### Inspect Database State

```python
async def test_debug_example(db_conn, test_auth_request_id):
    # Check auth request state
    state = await db_conn.fetchrow(
        "SELECT * FROM auth_request_state WHERE auth_request_id = $1",
        test_auth_request_id
    )
    print(f"State: {dict(state)}")

    # Check events
    events = await db_conn.fetch(
        "SELECT event_type, sequence_number FROM payment_events WHERE aggregate_id = $1 ORDER BY sequence_number",
        test_auth_request_id
    )
    print(f"Events: {[dict(e) for e in events]}")
```

### Check SQS Queue

```python
async def test_debug_queue(get_queue_attributes):
    attrs = await get_queue_attributes()
    print(f"Messages in queue: {attrs.get('ApproximateNumberOfMessages')}")
    print(f"Messages in flight: {attrs.get('ApproximateNumberOfMessagesNotVisible')}")
```

## Cleanup

Tests automatically clean up:
- Database records (via `db_conn` fixture)
- SQS messages (via `test_sqs_queue` fixture)
- Worker instances (via `worker_instance` fixture)

If tests fail and leave state behind, you can manually clean up:

```bash
# Reset PostgreSQL test database
cd infrastructure/docker
docker-compose exec postgres psql -U postgres -d payment_events_test -c "TRUNCATE auth_request_state, payment_events, auth_processing_locks CASCADE;"

# Purge SQS test queue
aws --endpoint-url=http://localhost:4566 sqs purge-queue --queue-url https://sqs.us-east-1.amazonaws.com/000000000000/auth-requests-test.fifo
```

# Authorization API Tests

This directory contains unit and integration tests for the Authorization API service.

## Test Organization

```
tests/
├── unit/                    # Unit tests (fast, no external dependencies)
│   ├── test_authorize.py
│   ├── test_config.py
│   ├── test_health.py
│   ├── test_outbox_processor.py
│   └── test_status.py
├── integration/             # Integration tests (require database + LocalStack)
│   ├── test_authorize_integration.py
│   ├── test_outbox_processor_integration.py
│   └── test_status_integration.py
├── e2e/                     # End-to-end tests (full system integration)
│   └── test_authorization_e2e.py
└── conftest.py             # Shared fixtures and test configuration
```

## Running Tests

### Prerequisites

Install dependencies:
```bash
poetry install
```

### Unit Tests

Unit tests are fast and don't require external services. They use mocks for database and external dependencies.

**Run all unit tests:**
```bash
poetry run pytest tests/unit/ -v
```

**Run specific unit test file:**
```bash
poetry run pytest tests/unit/test_outbox_processor.py -v
```

**Run specific test:**
```bash
poetry run pytest tests/unit/test_outbox_processor.py::test_fetch_unprocessed_messages -v
```

**Run with coverage:**
```bash
poetry run pytest tests/unit/ --cov=authorization_api --cov-report=html
```

### Integration Tests

Integration tests require PostgreSQL and LocalStack (for SQS). They test the full stack with real database and SQS interactions.

**Note:** The test suite automatically checks if required services are running before executing integration tests. If services are not available, you'll get a clear error message with instructions on how to start them.

#### Prerequisites for Integration Tests

1. **Start PostgreSQL and LocalStack:**

   From the infrastructure directory:
   ```bash
   cd ../../infrastructure/docker
   docker-compose up -d postgres localstack
   ```

   Or start them separately:
   ```bash
   # Start PostgreSQL
   docker run -d --name payments-postgres \
     -e POSTGRES_USER=postgres \
     -e POSTGRES_PASSWORD=password \
     -e POSTGRES_DB=payment_events_db \
     -p 5432:5432 \
     postgres:15-alpine

   # Start LocalStack
   docker run -d --name payments-localstack \
     -p 4566:4566 \
     -e SERVICES=sqs,kms,secretsmanager \
     -e DEBUG=1 \
     localstack/localstack:latest
   ```

2. **Verify services are running:**
   ```bash
   # Check PostgreSQL
   docker ps | grep postgres

   # Check LocalStack
   curl http://localhost:4566/_localstack/health
   ```

#### Running Integration Tests

**Run all integration tests:**
```bash
AWS_ENDPOINT_URL=http://localhost:4566 \
AWS_ACCESS_KEY_ID=test \
AWS_SECRET_ACCESS_KEY=test \
poetry run pytest tests/integration/ -v -m integration
```

**Run specific integration test:**
```bash
AWS_ENDPOINT_URL=http://localhost:4566 \
AWS_ACCESS_KEY_ID=test \
AWS_SECRET_ACCESS_KEY=test \
poetry run pytest tests/integration/test_outbox_processor_integration.py -v -m integration
```

**Run single test:**
```bash
AWS_ENDPOINT_URL=http://localhost:4566 \
AWS_ACCESS_KEY_ID=test \
AWS_SECRET_ACCESS_KEY=test \
poetry run pytest tests/integration/test_outbox_processor_integration.py::test_outbox_processor_sends_auth_request_to_sqs -v -m integration
```

### End-to-End Tests

End-to-end (E2E) tests verify the complete Authorization API flow from HTTP request through database, outbox processor, to SQS delivery. They test the full system integration including:

- HTTP API endpoints (POST /authorize, GET /status)
- Database transaction atomicity
- Event sourcing and read models
- Outbox pattern reliability
- SQS message delivery
- 5-second polling behavior (fast path vs timeout)
- Idempotency guarantees
- Concurrent request handling

**E2E tests require the same prerequisites as integration tests** (PostgreSQL + LocalStack).

#### Running E2E Tests

**Run all e2e tests:**
```bash
AWS_ENDPOINT_URL=http://localhost:4566 \
AWS_ACCESS_KEY_ID=test \
AWS_SECRET_ACCESS_KEY=test \
poetry run pytest tests/e2e/ -v -m e2e
```

**Run specific e2e test:**
```bash
AWS_ENDPOINT_URL=http://localhost:4566 \
AWS_ACCESS_KEY_ID=test \
AWS_SECRET_ACCESS_KEY=test \
poetry run pytest tests/e2e/test_authorization_e2e.py::test_e2e_happy_path_authorize_to_sqs -v -m e2e
```

#### E2E Test Scenarios

The e2e test suite includes 8 comprehensive scenarios:

1. **Happy path**: POST /authorize → event/read model/outbox → SQS message delivery
2. **Idempotency**: Same idempotency key returns same auth_request_id
3. **Fast path (5-second polling)**: Mock worker completes within 5 seconds → 200 response with result
4. **Timeout path**: No worker response → 202 response with status_url
5. **GET /status**: Query status for PENDING, AUTHORIZED, DENIED requests
6. **SQS message format**: Validate base64-encoded protobuf format
7. **Outbox reliability**: Processor retries on failure, at-least-once delivery
8. **Concurrent requests**: Multiple restaurants making concurrent requests

**Note:** E2E tests take longer to run (30-40 seconds) because they test the full system including the 5-second polling behavior.

## Test Database

Integration tests use a separate test database (`payment_events_test`) that is created and migrated automatically by the test fixtures.

The test database is:
- Created before test session starts
- Migrated using Alembic
- Truncated between individual tests
- Dropped after test session completes

## Environment Variables

Integration tests use these environment variables:

| Variable | Default | Description |
|----------|---------|-------------|
| `TEST_DATABASE_URL` | `postgresql://postgres:password@localhost:5432/payment_events_test` | Test database connection string |
| `AWS_ENDPOINT_URL` | `http://localhost:4566` | LocalStack endpoint for SQS |
| `AWS_ACCESS_KEY_ID` | `test` | AWS credentials for LocalStack |
| `AWS_SECRET_ACCESS_KEY` | `test` | AWS credentials for LocalStack |
| `AWS_REGION` | `us-east-1` | AWS region |

## Test Markers

Tests use pytest markers for categorization:

- `@pytest.mark.integration` - Integration tests requiring database/LocalStack
- `@pytest.mark.e2e` - End-to-end tests requiring full system integration
- No marker - Unit tests (fast, isolated)

**Run only unit tests:**
```bash
poetry run pytest tests/unit/ -v
```

**Run only integration tests:**
```bash
AWS_ENDPOINT_URL=http://localhost:4566 \
AWS_ACCESS_KEY_ID=test \
AWS_SECRET_ACCESS_KEY=test \
poetry run pytest -m integration -v
```

**Run only e2e tests:**
```bash
AWS_ENDPOINT_URL=http://localhost:4566 \
AWS_ACCESS_KEY_ID=test \
AWS_SECRET_ACCESS_KEY=test \
poetry run pytest -m e2e -v
```

## Common Test Commands

### Run all tests
```bash
# Unit tests only (fast)
poetry run pytest tests/unit/ -v

# All tests including integration and e2e (requires services)
AWS_ENDPOINT_URL=http://localhost:4566 \
AWS_ACCESS_KEY_ID=test \
AWS_SECRET_ACCESS_KEY=test \
poetry run pytest tests/ -v

# Only integration + e2e tests (skip unit tests)
AWS_ENDPOINT_URL=http://localhost:4566 \
AWS_ACCESS_KEY_ID=test \
AWS_SECRET_ACCESS_KEY=test \
poetry run pytest -m "integration or e2e" -v
```

### Run tests with output
```bash
# Show print statements
poetry run pytest tests/unit/ -v -s

# Show detailed output
poetry run pytest tests/unit/ -vv
```

### Run tests in parallel
```bash
# Install pytest-xdist first
poetry add --group dev pytest-xdist

# Run tests in parallel (unit tests only)
poetry run pytest tests/unit/ -n auto
```

### Stop on first failure
```bash
poetry run pytest tests/unit/ -v -x
```

### Run tests matching pattern
```bash
# Run all tests with "outbox" in the name
poetry run pytest tests/ -v -k "outbox"

# Run all tests with "auth" in the name
poetry run pytest tests/ -v -k "auth"
```

## Service Availability Checks

The test suite automatically checks if required services are available before running integration tests:

- **PostgreSQL** (localhost:5432) - Required for all integration tests
- **LocalStack** (localhost:4566) - Required for SQS integration tests

If services are not running, you'll see a helpful error message like:

```
================================================================================
ERROR: Required services are not available for integration tests
================================================================================

PostgreSQL is not running on localhost:5432
  Start services with:
    cd ../../infrastructure/docker
    docker-compose up -d postgres localstack

LocalStack is not running on localhost:4566
  This is required for integration tests that use SQS.
  Start services with:
    cd ../../infrastructure/docker
    docker-compose up -d postgres localstack

================================================================================
See tests/README.md for more details on running integration tests.
================================================================================
```

**This check only runs when executing integration tests** - unit tests can run without any services.

## Troubleshooting

### LocalStack issues

If LocalStack fails to start:
```bash
# Stop and remove container
docker stop payments-localstack
docker rm payments-localstack

# Remove volume
docker volume rm docker_localstack_data

# Start fresh
docker run -d --name payments-localstack \
  -p 4566:4566 \
  -e SERVICES=sqs,kms,secretsmanager \
  -e DEBUG=1 \
  localstack/localstack:latest
```

### Database connection issues

If database tests fail:
```bash
# Check if PostgreSQL is running
docker ps | grep postgres

# Check database exists
docker exec payments-postgres psql -U postgres -l

# Reset test database
docker exec payments-postgres psql -U postgres -c "DROP DATABASE IF EXISTS payment_events_test"
docker exec payments-postgres psql -U postgres -c "CREATE DATABASE payment_events_test"
```

### Test isolation issues

If tests are interfering with each other:
```bash
# Run tests sequentially (not in parallel)
poetry run pytest tests/integration/ -v --tb=short

# Check for leftover data
docker exec payments-postgres psql -U postgres payment_events_test -c "SELECT COUNT(*) FROM outbox"
```

## Test Coverage

Generate coverage report:
```bash
# Run with coverage
poetry run pytest tests/ --cov=authorization_api --cov-report=html --cov-report=term

# Open HTML report
open htmlcov/index.html
```

## CI/CD

For CI/CD pipelines, use this command:
```bash
# Start services in CI
docker-compose -f infrastructure/docker/docker-compose.yml up -d postgres localstack

# Wait for services
sleep 10

# Run all tests
AWS_ENDPOINT_URL=http://localhost:4566 \
AWS_ACCESS_KEY_ID=test \
AWS_SECRET_ACCESS_KEY=test \
poetry run pytest tests/ -v --cov=authorization_api --cov-report=xml

# Cleanup
docker-compose -f infrastructure/docker/docker-compose.yml down
```

## Writing New Tests

### Unit Test Example

```python
from unittest.mock import AsyncMock, patch
import pytest

@pytest.mark.asyncio
async def test_my_feature():
    """Test description."""
    # Arrange
    mock_conn = AsyncMock()
    mock_conn.fetch.return_value = [{"id": 1}]

    # Act
    result = await my_function(mock_conn)

    # Assert
    assert result == expected_value
    mock_conn.fetch.assert_called_once()
```

### Integration Test Example

```python
import pytest

@pytest.mark.asyncio
@pytest.mark.integration
async def test_my_feature_integration(db_pool):
    """Test description with real database."""
    async with db_pool.acquire() as conn:
        # Arrange
        await conn.execute("INSERT INTO ...")

        # Act
        result = await my_function()

        # Assert
        row = await conn.fetchrow("SELECT * FROM ...")
        assert row["field"] == expected_value
```

### End-to-End Test Example

```python
import pytest
from payments.v1.authorization_pb2 import AuthorizeRequest, AuthorizeResponse

@pytest.mark.asyncio
@pytest.mark.e2e
async def test_my_feature_e2e(http_client, db_pool, sqs_client):
    """Test complete flow from HTTP request to SQS delivery."""
    # Arrange - Create protobuf request
    request_proto = AuthorizeRequest(
        payment_token="pt_test_123",
        restaurant_id="00000000-0000-0000-0000-000000000001",
        amount_cents=1000,
        currency="USD",
        idempotency_key="test-key-123",
    )

    # Act - Make HTTP request
    response = await http_client.post(
        "/v1/authorize",
        content=request_proto.SerializeToString(),
        headers={"Content-Type": "application/x-protobuf"},
    )

    # Assert - Verify HTTP response
    assert response.status_code == 202
    response_proto = AuthorizeResponse()
    response_proto.ParseFromString(response.content)

    # Verify database writes
    async with db_pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT * FROM auth_request_state WHERE auth_request_id = $1",
            uuid.UUID(response_proto.auth_request_id)
        )
        assert row["status"] == "PENDING"

    # Trigger outbox processor and verify SQS delivery
    from authorization_api.infrastructure.outbox_processor import process_outbox_batch
    await process_outbox_batch()

    # Verify message in SQS
    sqs_message = sqs_client.receive_message(
        QueueUrl="http://localhost:4566/000000000000/auth-requests.fifo",
        MaxNumberOfMessages=1,
    )
    assert "Messages" in sqs_message
```

## Additional Resources

- [pytest documentation](https://docs.pytest.org/)
- [pytest-asyncio documentation](https://pytest-asyncio.readthedocs.io/)
- [LocalStack documentation](https://docs.localstack.cloud/)
- [asyncpg documentation](https://magicstack.github.io/asyncpg/)

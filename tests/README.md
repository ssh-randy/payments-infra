# Payment Infrastructure Tests

This directory contains comprehensive tests for the payment authorization system at different levels of integration.

## Test Types

### Integration Tests (This README)
In-process testing with mocked external services:
- All components run in-process (FastAPI via ASGI, Worker via asyncio)
- Payment Token Service is mocked
- Fast execution (~5-15s per test)
- Ideal for development and rapid feedback
- **Location:** `tests/integration/`

### End-to-End Tests ([See e2e/README.md](e2e/README.md))
True production-like testing with Docker containers:
- Each service in separate Docker container
- Real HTTP requests over network
- Real Payment Token Service with encryption
- Slower execution (~20-60s per test)
- Validates complete system deployment
- **Location:** `tests/e2e/`

---

# Integration Tests

These integration tests run all components in-process for fast feedback during development.

## Overview

These tests validate the entire system integration from client request through worker processing to final status check:

```
Client → POST /authorize → DB + Outbox → SQS → Worker → Processes → Updates DB → GET /status → Returns result
```

## Test Infrastructure

### Real Components
- **Authorization API**: FastAPI service running in-process
- **Auth Processor Worker**: SQS consumer processing messages
- **PostgreSQL**: Shared database for both services
- **LocalStack SQS**: FIFO queues for message delivery
- **Outbox Processor**: Ensures at-least-once delivery to SQS

### Mocked Components
- **Payment Token Service**: Mocked decrypt endpoint
- **Payment Processors**: Uses MockProcessor for deterministic testing

## Test Scenarios

The test suite includes 10 comprehensive scenarios:

1. **Happy Path** - Full authorization flow from API to worker to status check
2. **Fast Path** - Worker completes within 5 seconds, returns synchronous response
3. **Card Decline** - Full flow with denied card
4. **Idempotency** - Same idempotency key returns same auth_request_id across full flow
5. **Token Service Error** - Invalid payment token results in FAILED status
6. **Transient Error with Retry** - Worker retries on temporary failures
7. **Max Retries Exceeded** - Worker exhausts retries and marks as FAILED
8. **Concurrent Requests** - Multiple restaurants making simultaneous requests
9. **Status Polling** - Client polls status during processing

## Prerequisites

### 1. Start Required Services

```bash
# From repository root
cd infrastructure/docker
docker-compose up -d postgres localstack
```

### 2. Run Database Migrations (Automatic)

The test suite automatically runs Alembic migrations to set up the test database schema. However, you can manually run migrations if needed:

```bash
cd infrastructure/migrations
alembic upgrade head
```

### 3. Install Test Dependencies

Install the test dependencies using pip or tox:

```bash
# Option 1: Using tox (recommended - creates isolated test environment)
cd tests
pip install tox
tox -e e2e --notest  # Create environment without running tests

# Option 2: Using pip directly
cd tests
pip install -r requirements.txt
```

**Note:** The Authorization API and Auth Processor Worker dependencies must also be installed:

```bash
# Authorization API
cd services/authorization-api
poetry install

# Auth Processor Worker
cd services/auth-processor-worker
poetry install
```

## Running the Tests

**Quick Start:** If postgres and localstack are already running, you can run tests immediately. The tests automatically:
- Create SQS queues if they don't exist
- Run database migrations
- Clean up after each test

### Run All Full System Tests

```bash
# From repository root
cd tests

# Option 1: Using tox (recommended - handles environment setup)
tox -e integration

# Option 2: Using pytest directly
AWS_ENDPOINT_URL=http://localhost:4566 \
AWS_ACCESS_KEY_ID=test \
AWS_SECRET_ACCESS_KEY=test \
pytest integration/e2e/test_full_system.py -v -m full_system
```

### Run Specific Test

```bash
cd tests

# Option 1: Using tox
tox -e integration -- integration/e2e/test_full_system.py::test_full_authorization_flow -v

# Option 2: Using pytest directly
AWS_ENDPOINT_URL=http://localhost:4566 \
AWS_ACCESS_KEY_ID=test \
AWS_SECRET_ACCESS_KEY=test \
pytest integration/e2e/test_full_system.py::test_full_authorization_flow -v
```

### Run with Detailed Logging

```bash
cd tests

# Option 1: Using tox
tox -e integration -- -v -s --log-cli-level=DEBUG

# Option 2: Using pytest directly
AWS_ENDPOINT_URL=http://localhost:4566 \
AWS_ACCESS_KEY_ID=test \
AWS_SECRET_ACCESS_KEY=test \
pytest integration/e2e/test_full_system.py -v -s --log-cli-level=DEBUG
```

## Test Duration

- **Individual tests**: 5-15 seconds each
- **Full suite**: ~2-3 minutes total
- **Tests with retries**: Up to 30 seconds (test_max_retries_exceeded)

## Test Architecture

### Directory Structure

```
tests/
├── conftest.py                      # Root-level fixtures (database, common fixtures)
├── pytest.ini                       # Pytest configuration
├── README.md                        # This file (integration tests)
├── integration/                     # In-process integration tests
│   ├── __init__.py
│   ├── conftest.py                  # Integration-specific fixture imports
│   ├── test_full_system.py          # Main test scenarios (in-process)
│   ├── fixtures/
│   │   ├── __init__.py
│   │   └── system_fixtures.py       # Worker, SQS, mock fixtures
│   └── helpers/
│       ├── __init__.py
│       └── api_client.py            # API client helper (ASGI)
└── e2e/                             # Docker-based E2E tests
    ├── README.md                    # E2E test documentation
    ├── conftest.py                  # E2E fixtures
    ├── test_full_e2e.py             # Complete flow tests (6 scenarios)
    ├── fixtures/
    │   └── docker_fixtures.py       # Docker Compose management
    └── helpers/
        ├── http_client.py           # Real HTTP clients (async)
        └── wait_for_services.py     # Health check helpers
```

### Key Fixtures

#### `db_pool` (from tests/conftest.py)
- Creates a connection pool to the test database
- Automatically runs Alembic migrations
- Cleans up after each test

#### `api_client` (from helpers/api_client.py)
- Wrapper around httpx.AsyncClient for the Authorization API
- Provides helpers for POST /authorize and GET /status
- Includes `poll_until_complete()` for waiting on async processing

#### `worker_instance` (from fixtures/system_fixtures.py)
- Creates and manages a worker instance
- Provides `start()`, `stop()`, and `wait_for_processing()` methods
- Tracks processed messages and errors

#### `mock_payment_token_client` (from fixtures/system_fixtures.py)
- Mocks the Payment Token Service
- Configure responses with `configure_token_response()`
- Configure errors with `configure_token_error()`

#### `sqs_client` (from fixtures/system_fixtures.py)
- Boto3 SQS client for LocalStack
- Used to verify message delivery
- Automatically purges queue after tests

## Troubleshooting

### Services Not Running

If you see errors about PostgreSQL or LocalStack not being available:

```bash
cd infrastructure/docker
docker-compose up -d postgres localstack

# Verify services are running
docker-compose ps
```

### Queue Not Found

If you see SQS queue errors:

```bash
cd scripts
./init_localstack_test.sh
```

### Database Migration Issues

If you see database schema errors:

```bash
cd infrastructure/migrations
alembic upgrade head
```

### Worker Not Processing Messages

Check that:
1. LocalStack is running on port 4566
2. Queue exists and is accessible
3. Worker logs show no errors (run with `-s --log-cli-level=DEBUG`)

### Tests Hanging

If tests hang during polling:
1. Check outbox processor is running (called in tests)
2. Verify SQS messages are being delivered
3. Check worker is started before outbox processing
4. Increase timeout values if needed

## Environment Variables

These environment variables are automatically set by fixtures but can be overridden:

- `AWS_ENDPOINT_URL`: LocalStack endpoint (default: http://localhost:4566)
- `AWS_ACCESS_KEY_ID`: AWS access key (default: test)
- `AWS_SECRET_ACCESS_KEY`: AWS secret key (default: test)
- `TEST_DATABASE_URL`: Test database URL (default: postgresql://postgres:password@localhost:5432/payment_events_test)
- `AUTH_REQUESTS_QUEUE_URL`: SQS queue URL (default: http://localhost:4566/000000000000/auth-requests.fifo)

## CI/CD Integration

These tests are designed to run in CI/CD pipelines. Ensure:

1. PostgreSQL service is available
2. LocalStack container is running
3. Queues are initialized before running tests
4. Database migrations run before tests
5. Tests run serially (not in parallel) to avoid queue conflicts

Example GitHub Actions:

```yaml
- name: Start Services
  run: |
    cd infrastructure/docker
    docker-compose up -d postgres localstack

- name: Initialize LocalStack
  run: |
    cd scripts
    ./init_localstack_test.sh

- name: Install Tox
  run: pip install tox

- name: Run Full System Tests
  run: |
    cd tests
    tox -e integration
```

## Related Tests

- **E2E Tests**: `tests/e2e/` - Docker-based end-to-end tests ([README](e2e/README.md))
- **Authorization API Tests**: `services/authorization-api/tests/e2e/` - Tests API in isolation
- **Worker Tests**: `services/auth-processor-worker/tests/integration/` - Tests worker in isolation
- **Integration Tests**: This directory - In-process integration tests

## Coverage

These integration tests provide comprehensive coverage of:
- ✅ Complete API → Worker → Status flow (in-process)
- ✅ Fast path (5-second polling) behavior
- ✅ Outbox processor reliability
- ✅ SQS message delivery
- ✅ Worker message consumption and processing
- ✅ All error scenarios (declines, failures, retries)
- ✅ Idempotency across services
- ✅ Concurrent request handling
- ✅ Status polling during processing

**For production-like testing with real HTTP and Docker containers, see [E2E Tests](e2e/README.md).**

## References

- **Issue**: i-8gcz - Write full system end-to-end tests
- **Specs**: s-9jeq (Authorization API), s-w5sf (Auth Processor Worker)
- **Dependencies**: i-19p2 (API e2e tests), i-30mi (Worker integration tests)

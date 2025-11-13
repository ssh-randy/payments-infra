# Payment Token Service Tests

This directory contains unit, integration, and end-to-end tests for the Payment Token Service.

## Test Organization

```
tests/
├── unit/                    # Unit tests (fast, no external dependencies)
│   ├── test_encryption.py
│   ├── test_kms.py
│   └── test_token_domain.py
├── integration/             # Integration tests (require database + LocalStack)
│   ├── test_create_token.py
│   └── test_decrypt_internal.py
├── e2e/                     # End-to-end tests (full system integration)
│   ├── test_api_contracts.py
│   ├── test_decrypt_behaviors.py
│   ├── test_token_creation_behaviors.py
│   └── test_token_retrieval_behaviors.py
└── conftest.py             # Shared fixtures and test configuration
```

## Running Tests

### Prerequisites

Install dependencies:
```bash
poetry install
```

### Unit Tests

Unit tests are fast and don't require external services. They use mocks for database, KMS, and external dependencies.

**Run all unit tests:**
```bash
poetry run pytest tests/unit/ -v
```

**Run specific unit test file:**
```bash
poetry run pytest tests/unit/test_encryption.py -v
```

**Run specific test:**
```bash
poetry run pytest tests/unit/test_encryption.py::TestEncryptDecrypt::test_encrypt_decrypt_roundtrip -v
```

**Run with coverage:**
```bash
poetry run pytest tests/unit/ --cov=payment_token --cov-report=html
```

### Integration Tests

Integration tests require PostgreSQL and LocalStack (for KMS). They test the full stack with real database and KMS interactions.

**Note:** The test suite automatically checks if required services are running before executing integration tests. If services are not available, you'll get a clear error message with instructions on how to start them.

#### Prerequisites for Integration Tests

1. **Start PostgreSQL and LocalStack:**

   From the infrastructure directory:
   ```bash
   cd ../../infrastructure/docker
   docker-compose up -d postgres-tokens localstack
   ```

   Or start them separately:
   ```bash
   # Start PostgreSQL (tokens database on port 5433)
   docker run -d --name payments-postgres-tokens \
     -e POSTGRES_USER=postgres \
     -e POSTGRES_PASSWORD=password \
     -e POSTGRES_DB=payment_tokens_db \
     -p 5433:5432 \
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
   docker ps | grep postgres-tokens

   # Check LocalStack
   curl http://localhost:4566/_localstack/health
   ```

3. **Create test database:**
   ```bash
   # Create the test database (if not auto-created)
   PGPASSWORD=password psql -h localhost -p 5433 -U postgres -d payment_tokens_db -c "CREATE DATABASE payment_tokens_test;"
   ```

#### Running Integration Tests

**Run all integration tests:**
```bash
TEST_DATABASE_URL="postgresql://postgres:password@localhost:5433/payment_tokens_test" \
AWS_ENDPOINT_URL=http://localhost:4566 \
AWS_ACCESS_KEY_ID=test \
AWS_SECRET_ACCESS_KEY=test \
poetry run pytest tests/integration/ -v
```

**Run specific integration test:**
```bash
TEST_DATABASE_URL="postgresql://postgres:password@localhost:5433/payment_tokens_test" \
AWS_ENDPOINT_URL=http://localhost:4566 \
AWS_ACCESS_KEY_ID=test \
AWS_SECRET_ACCESS_KEY=test \
poetry run pytest tests/integration/test_create_token.py -v
```

**Run single test:**
```bash
TEST_DATABASE_URL="postgresql://postgres:password@localhost:5433/payment_tokens_test" \
AWS_ENDPOINT_URL=http://localhost:4566 \
AWS_ACCESS_KEY_ID=test \
AWS_SECRET_ACCESS_KEY=test \
poetry run pytest tests/integration/test_create_token.py::test_create_token_success -v
```

### End-to-End Tests

End-to-end (E2E) tests verify the complete Payment Token Service flow including:

- Token creation from device-encrypted payment data
- Token retrieval and validation
- Internal decrypt API for authorized services
- Token expiration and ownership validation
- Idempotency guarantees
- API contract conformance

**E2E tests require the same prerequisites as integration tests** (PostgreSQL + LocalStack).

#### Running E2E Tests

**Run all e2e tests:**
```bash
TEST_DATABASE_URL="postgresql://postgres:password@localhost:5433/payment_tokens_test" \
AWS_ENDPOINT_URL=http://localhost:4566 \
AWS_ACCESS_KEY_ID=test \
AWS_SECRET_ACCESS_KEY=test \
poetry run pytest tests/e2e/ -v
```

**Run specific e2e test:**
```bash
TEST_DATABASE_URL="postgresql://postgres:password@localhost:5433/payment_tokens_test" \
AWS_ENDPOINT_URL=http://localhost:4566 \
AWS_ACCESS_KEY_ID=test \
AWS_SECRET_ACCESS_KEY=test \
poetry run pytest tests/e2e/test_token_creation_behaviors.py -v
```

## Test Database

Integration tests use a separate test database (`payment_tokens_test`) that is created and migrated automatically by the test fixtures.

The test database is:
- Created automatically if it doesn't exist (when using enhanced conftest)
- Migrated using Alembic before tests run
- Cleaned between test sessions via Alembic downgrade/upgrade
- Tables are isolated per test via transaction rollback

## Environment Variables

Integration and E2E tests use these environment variables:

| Variable | Default | Description |
|----------|---------|-------------|
| `TEST_DATABASE_URL` | `postgresql://postgres:password@localhost:5433/payment_tokens_test` | Test database connection string |
| `AWS_ENDPOINT_URL` | `http://localhost:4566` | LocalStack endpoint for KMS |
| `AWS_ACCESS_KEY_ID` | `test` | AWS credentials for LocalStack |
| `AWS_SECRET_ACCESS_KEY` | `test` | AWS credentials for LocalStack |
| `AWS_REGION` | `us-east-1` | AWS region |

**Note:** The payment-token service uses port **5433** (mapped to postgres-tokens container) not 5432.

## Common Test Commands

### Run all tests
```bash
# Unit tests only (fast, no services required)
poetry run pytest tests/unit/ -v

# All tests including integration and e2e (requires services)
TEST_DATABASE_URL="postgresql://postgres:password@localhost:5433/payment_tokens_test" \
AWS_ENDPOINT_URL=http://localhost:4566 \
AWS_ACCESS_KEY_ID=test \
AWS_SECRET_ACCESS_KEY=test \
poetry run pytest tests/ -v

# Only integration + e2e tests (skip unit tests)
TEST_DATABASE_URL="postgresql://postgres:password@localhost:5433/payment_tokens_test" \
AWS_ENDPOINT_URL=http://localhost:4566 \
AWS_ACCESS_KEY_ID=test \
AWS_SECRET_ACCESS_KEY=test \
poetry run pytest tests/integration tests/e2e -v
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

# Run unit tests in parallel (safe for unit tests)
poetry run pytest tests/unit/ -n auto

# Do NOT run integration tests in parallel (database conflicts)
```

### Stop on first failure
```bash
poetry run pytest tests/unit/ -v -x
```

### Run tests matching pattern
```bash
# Run all tests with "encrypt" in the name
poetry run pytest tests/ -v -k "encrypt"

# Run all tests with "token" in the name
poetry run pytest tests/ -v -k "token"
```

## Service Availability Checks

The test suite automatically checks if required services are available before running integration tests:

- **PostgreSQL** (localhost:5433) - Required for all integration tests
- **LocalStack** (localhost:4566) - Required for KMS integration tests

If services are not running, you'll see a helpful error message like:

```
================================================================================
ERROR: Required services are not available for integration tests
================================================================================

PostgreSQL is not running on localhost:5433
  Start services with:
    cd ../../infrastructure/docker
    docker-compose up -d postgres-tokens localstack

LocalStack is not running on localhost:4566
  This is required for integration tests that use KMS.
  Start services with:
    cd ../../infrastructure/docker
    docker-compose up -d postgres-tokens localstack

================================================================================
See tests/README.md for more details on running integration tests.
================================================================================
```

**This check only runs when executing integration/e2e tests** - unit tests can run without any services.

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

# Initialize KMS
cd ../../scripts
./init_localstack_test.sh
```

### Database connection issues

If database tests fail:
```bash
# Check if PostgreSQL is running
docker ps | grep postgres-tokens

# Check database exists
PGPASSWORD=password psql -h localhost -p 5433 -U postgres -l

# Create test database manually
PGPASSWORD=password psql -h localhost -p 5433 -U postgres -d payment_tokens_db -c "DROP DATABASE IF EXISTS payment_tokens_test"
PGPASSWORD=password psql -h localhost -p 5433 -U postgres -d payment_tokens_db -c "CREATE DATABASE payment_tokens_test"
```

### Migration issues

If Alembic migrations fail:
```bash
# Reset test database
TEST_DATABASE_URL="postgresql://postgres:password@localhost:5433/payment_tokens_test" \
poetry run alembic downgrade base

TEST_DATABASE_URL="postgresql://postgres:password@localhost:5433/payment_tokens_test" \
poetry run alembic upgrade head
```

### Port conflicts

If you see "port already in use" errors:

```bash
# Check what's using port 5433 (PostgreSQL tokens)
lsof -i :5433

# Check what's using port 4566 (LocalStack)
lsof -i :4566

# Stop docker-compose services
cd ../../infrastructure/docker
docker-compose down
```

## Test Coverage

Generate coverage report:
```bash
# Run with coverage
poetry run pytest tests/ --cov=payment_token --cov-report=html --cov-report=term

# Open HTML report
open htmlcov/index.html
```

## CI/CD

For CI/CD pipelines, use this command:
```bash
# Start services in CI
docker-compose -f infrastructure/docker/docker-compose.yml up -d postgres-tokens localstack

# Wait for services to be healthy
sleep 10

# Create test database
PGPASSWORD=password psql -h localhost -p 5433 -U postgres -d payment_tokens_db -c "CREATE DATABASE payment_tokens_test;"

# Run all tests
TEST_DATABASE_URL="postgresql://postgres:password@localhost:5433/payment_tokens_test" \
AWS_ENDPOINT_URL=http://localhost:4566 \
AWS_ACCESS_KEY_ID=test \
AWS_SECRET_ACCESS_KEY=test \
poetry run pytest tests/ -v --cov=payment_token --cov-report=xml

# Cleanup
docker-compose -f infrastructure/docker/docker-compose.yml down
```

## Writing New Tests

### Unit Test Example

```python
from unittest.mock import Mock, patch
import pytest

def test_my_feature():
    """Test description."""
    # Arrange
    mock_kms = Mock()
    mock_kms.get_bdk.return_value = b"0" * 32

    # Act
    result = my_function(mock_kms)

    # Assert
    assert result == expected_value
    mock_kms.get_bdk.assert_called_once()
```

### Integration Test Example

```python
import pytest

@pytest.mark.asyncio
async def test_my_feature_integration(db_session, service_key):
    """Test description with real database."""
    # Arrange
    from payment_token.domain.token_service import TokenService
    token_service = TokenService(db_session, service_key)

    # Act
    token = await token_service.create_token(...)

    # Assert
    assert token.token_id.startswith("pt_")
    stored = db_session.query(PaymentToken).filter_by(token_id=token.token_id).first()
    assert stored is not None
```

### E2E Test Example

```python
import pytest
from httpx import AsyncClient

@pytest.mark.asyncio
async def test_create_token_e2e(db_session, test_client):
    """Test complete token creation flow via HTTP API."""
    async with AsyncClient(app=app, base_url="http://test") as client:
        response = await client.post(
            "/v1/tokens",
            json={
                "restaurant_id": "12345678-1234-1234-1234-123456789abc",
                "device_token": "device_test_123",
                "encrypted_data": "base64_encoded_data",
            },
            headers={"X-API-Key": "test-api-key"},
        )

        assert response.status_code == 201
        data = response.json()
        assert "token_id" in data
        assert data["token_id"].startswith("pt_")
```

## Additional Resources

- [pytest documentation](https://docs.pytest.org/)
- [pytest-asyncio documentation](https://pytest-asyncio.readthedocs.io/)
- [LocalStack documentation](https://docs.localstack.cloud/)
- [Alembic documentation](https://alembic.sqlalchemy.org/)

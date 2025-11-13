# End-to-End Tests with Docker Containers

The `e2e/` directory contains **true end-to-end tests** that validate the complete payment authorization flow across all services running in separate Docker containers with real HTTP requests and network communication.

## Overview

These E2E tests run each service in its own Docker container:

```
┌─────────────────────────────────────────────────────────────────┐
│                         E2E Test Suite                          │
│                     (Real HTTP Requests)                        │
└─────────────────────────────────────────────────────────────────┘
                                 │
                 ┌───────────────┼───────────────┐
                 │               │               │
                 ▼               ▼               ▼
        ┌──────────────┐  ┌──────────────┐  ┌──────────────┐
        │Authorization │  │  Payment     │  │Auth Processor│
        │     API      │  │Token Service │  │    Worker    │
        │  (Container) │  │  (Container) │  │  (Container) │
        └──────────────┘  └──────────────┘  └──────────────┘
                 │               │               │
                 └───────────────┼───────────────┘
                                 ▼
                    ┌────────────────────────────┐
                    │ PostgreSQL + LocalStack    │
                    │      (Containers)          │
                    └────────────────────────────┘
```

## Test Flow

Each E2E test validates the complete flow:

```
1. Client encrypts card data
   ↓ POST /v1/payment-tokens (HTTP → Payment Token Service)
2. Get payment token
   ↓ POST /v1/authorize (HTTP → Authorization API)
3. Authorization API writes to DB + Outbox
   ↓ Outbox Processor → SQS
4. Worker picks up message
   ↓ Worker → Payment Token Service (HTTP)
5. Worker decrypts payment token
   ↓ Worker → Payment Processor (Mock/Stripe)
6. Worker processes authorization
   ↓ Worker writes events + updates read model
7. Client checks status
   ↓ GET /v1/authorize/{id}/status (HTTP → Authorization API)
8. Verify final status
```

## Prerequisites

### System Requirements

- Docker and Docker Compose installed
- At least 4GB free RAM
- Ports available: 8000, 8001, 4567, 5434, 5435
- Bash shell (for helper scripts)
- Python 3.11+

### Dependencies

Python test dependencies are managed via Tox or pip:

```bash
cd tests
deactivate # OPTIONAL, exit any poetry environments/venvs that may be activated

# Option 1: Using tox (recommended - creates isolated test environment)
pip install tox
tox -e e2e --notest  # Create environment without running tests

# Option 2: Using pip directly
pip install -r requirements.txt
```

Key dependencies:
- `httpx` - Async HTTP client
- `pytest` - Test framework
- `pytest-asyncio` - Async test support
- Protobuf-generated Python files

## Running E2E Tests

### Quick Start

**The tests automatically manage Docker containers for you!** Just run:

```bash
# From repository root
cd tests

# Option 1: Using tox (recommended)
tox -e e2e

# Option 2: Using pytest directly
pytest e2e/test_full_e2e.py -v -m e2e
```

**That's it!** The `docker_services` pytest fixture (session-scoped) automatically:
- Starts all containers in the correct order via docker-compose
- Waits for health checks
- Runs database migrations
- Initializes LocalStack (creates SQS queues and KMS keys)
- Runs all tests
- **Cleans up containers automatically** when tests complete

**No manual docker-compose commands needed!**

### How It Works

When you run the E2E tests, the `docker_services` fixture automatically:

1. **Starts services** via docker-compose:
   - PostgreSQL (main database) on port 5434
   - PostgreSQL (tokens database) on port 5435
   - LocalStack (SQS, KMS) on port 4567
   - Payment Token Service on port 8001
   - Authorization API on port 8000
   - Auth Processor Worker (no exposed port)

2. **Waits for health checks** (~60-90 seconds for all services)

3. **Runs your tests**

4. **Cleans up automatically** (equivalent to `docker-compose down -v`)

### Running Specific Tests

```bash
cd tests

# Run all E2E tests
tox -e e2e

# Run specific test
tox -e e2e -- e2e/test_full_e2e.py::test_full_e2e_happy_path

# Run with detailed logging
tox -e e2e -- -v -s --log-cli-level=INFO
```

### Manual Docker Control (Optional)

If you want to keep containers running between test runs (faster iteration):

```bash
# Start services manually (tests will skip startup if already running)
cd infrastructure/docker
docker-compose -f docker-compose.e2e.yml up -d --build

# Run tests (won't cleanup)
cd ../../tests
pytest e2e/test_full_e2e.py -v

# Manual cleanup when done
cd ../infrastructure/docker
docker-compose -f docker-compose.e2e.yml down -v
```

## Test Scenarios

### Test 1: Full Happy Path

**File:** `test_full_e2e_happy_path`

Validates the complete successful flow:
1. Creates payment token with valid card
2. Submits authorization request
3. Worker processes authorization
4. Status returns AUTHORIZED with correct amount

**Expected:** Status = AUTHORIZED, amount = $50.00, processor = mock

### Test 2: Card Decline

**File:** `test_full_e2e_card_decline`

Tests handling of declined cards:
1. Creates payment token with card `4000000000009995` (insufficient funds)
2. Submits authorization request
3. Worker processes and gets decline from processor
4. Status returns DENIED with decline code

**Expected:** Status = DENIED, denial_code and denial_reason present

### Test 3: Invalid Token

**File:** `test_full_e2e_invalid_token`

Tests error handling for invalid payment tokens:
1. Submits authorization with non-existent token
2. Worker fails to decrypt token
3. Status returns FAILED

**Expected:** Status = FAILED

### Test 4: Payment Token Service Down

**File:** `test_full_e2e_payment_token_service_down`

Tests resilience when Payment Token Service is unavailable:
1. Creates token while service is up
2. Stops Payment Token Service container
3. Submits authorization request
4. Worker retries and eventually fails
5. Restarts Payment Token Service

**Expected:** Status = FAILED (graceful degradation)

### Test 5: Concurrent Requests

**File:** `test_full_e2e_concurrent_requests`

Tests system under concurrent load:
1. Creates 10 payment tokens concurrently
2. Submits 10 authorization requests concurrently
3. All requests process successfully
4. Verifies no race conditions or errors

**Expected:** All 10 requests succeed with correct amounts

### Test 6: Fast Path

**File:** `test_full_e2e_fast_path`

Tests the 5-second fast path optimization:
1. Submits authorization request
2. Worker completes within 5 seconds
3. Initial response returns 200 (not 202) with result

**Expected:** Immediate result in POST response (no polling needed)

### Test 7: Idempotency

**File:** `test_full_e2e_idempotency`

Tests idempotency guarantees:
1. Submits authorization request with idempotency key
2. Submits same request again with same key
3. Verifies both requests return same auth_request_id
4. Verifies only one authorization is created and processed

**Expected:** Same auth_request_id returned, single authorization processed

## Test Infrastructure

### Docker Compose Configuration

**File:** `infrastructure/docker/docker-compose.e2e.yml`

Key features:
- **Automatic initialization:** LocalStack resources created automatically
- **Health checks:** All services have health checks
- **Smart dependencies:** Services start only when dependencies are healthy
- **Database migrations:** Run automatically on container startup
- **Network isolation:** All services on `payments-e2e-network`
- **Port mapping:** Different from dev to avoid conflicts

**Startup order:**
1. PostgreSQL databases (health checked)
2. LocalStack (health checked)
3. LocalStack init container (creates queues, exits)
4. Payment Token Service (depends on postgres-tokens + localstack-init)
5. Authorization API (depends on postgres + localstack-init + payment-token)
6. Worker (depends on all above)

### HTTP Client Helpers

**File:** `e2e/helpers/http_client.py`

Provides async HTTP clients:

```python
# Authorization API client
async with AuthorizationAPIClient() as client:
    response = await client.authorize(...)
    status = await client.get_status(...)
    final = await client.poll_until_complete(...)

# Payment Token Service client
async with PaymentTokenServiceClient() as client:
    token = await client.create_token(...)
```

### Fixtures

**File:** `e2e/fixtures/docker_fixtures.py`

Key fixtures:
- `docker_services` - Starts/stops all containers (session scope)
- `authorization_api_url` - Returns http://localhost:8000
- `payment_token_service_url` - Returns http://localhost:8001
- `auth_client` - Pre-configured Authorization API client
- `token_client` - Pre-configured Payment Token Service client

## Environment Variables

The E2E environment uses different ports and database names to avoid conflicts:

| Service | Variable | E2E Value | Dev Value |
|---------|----------|-----------|-----------|
| Authorization API | PORT | 8000 | 8000 |
| Payment Token Service | PORT | 8000 (container) | 8001 |
| PostgreSQL (main) | PORT | 5434 | 5432 |
| PostgreSQL (tokens) | PORT | 5435 | 5433 |
| LocalStack | PORT | 4567 | 4566 |
| PostgreSQL (main) | DATABASE | payment_events_e2e | payment_events |
| PostgreSQL (tokens) | DATABASE | payment_tokens_e2e | payment_tokens |
| SQS Queue | NAME | auth-requests-e2e.fifo | auth-requests.fifo |

## Troubleshooting

### Services Not Starting

**Problem:** `docker-compose up` fails or containers exit

**Solution:**
```bash
# Check logs
docker-compose -f docker-compose.e2e.yml logs

# Rebuild images
docker-compose -f docker-compose.e2e.yml up -d --build --force-recreate

# Check for port conflicts
lsof -i :8000 -i :8001 -i :4567 -i :5434 -i :5435
```

### Health Checks Failing

**Problem:** `wait_for_e2e_services.sh` times out

**Solution:**
```bash
# Check service logs
docker logs authorization-api-service
docker logs payment-token-service

# Check database connectivity
PGPASSWORD=password psql -h localhost -p 5434 -U postgres -d payment_events_e2e

# Check LocalStack
curl http://localhost:4567/_localstack/health
```

### Tests Timeout

**Problem:** Tests hang waiting for authorization completion

**Possible causes:**
1. Worker not running: `docker logs auth-processor-worker`
2. SQS queue not created: Run `./scripts/init_localstack_e2e.sh`
3. Outbox processor not running: Check Authorization API logs
4. Database connection issues: Check PostgreSQL logs

**Solution:**
```bash
# Check worker logs
docker logs auth-processor-worker --tail=50 -f

# Check SQS messages
aws --endpoint-url=http://localhost:4567 sqs receive-message \
    --queue-url https://sqs.us-east-1.amazonaws.com/000000000000/auth-requests-e2e.fifo

# Check database state
PGPASSWORD=password psql -h localhost -p 5434 -U postgres -d payment_events_e2e \
    -c "SELECT * FROM auth_request_state ORDER BY created_at DESC LIMIT 5;"
```

### Import Errors

**Problem:** `ModuleNotFoundError: No module named 'payments'`

**Solution:**
```bash
# Ensure protobuf files are generated
cd services/authorization-api
poetry run python -m grpc_tools.protoc --python_out=. --proto_path=../../shared/protos ../../shared/protos/payments/v1/*.proto

# Install test dependencies
cd ../../tests
pip install -r requirements.txt
# or
tox -e e2e --notest
```

### Worker Not Processing Messages

**Problem:** Authorization stuck in PENDING/PROCESSING

**Checklist:**
1. Worker container is running: `docker ps | grep worker`
2. Queue exists: `aws --endpoint-url=http://localhost:4567 sqs list-queues`
3. Messages in queue: Check SQS via AWS CLI
4. Worker can reach Payment Token Service: Check network connectivity
5. Database migrations applied: Check alembic version

**Check worker logs:**
```bash
docker logs auth-processor-worker --tail=50 -f
```

### Tests Return AUTH_STATUS_FAILED

**Problem:** E2E tests complete but authorizations fail instead of succeeding

**Common causes and solutions:**

#### 1. Token Ownership Mismatch (403 Forbidden)
**Symptom:** Worker logs show `HTTP/1.1 403 Forbidden` when calling Payment Token Service
**Root cause:** Payment token created for different restaurant_id than used in authorization
**Solution:** Ensure all `create_token()` calls pass the same `restaurant_id` parameter:
```python
token_response = await token_client.create_token(
    card_number="4242424242424242",
    restaurant_id=str(test_restaurant_id),  # ← Must match authorization request
    ...
)
```

#### 2. Protobuf Field Mismatch
**Symptom:** Worker logs show `Protocol message PaymentData has no 'billing_zip' field`
**Root cause:** Code tries to access protobuf field that doesn't exist in .proto definition
**Solution:** Ensure domain models and protobuf definitions are in sync. Don't access fields that don't exist in the protobuf.

#### 3. JSONB Type Codec Issues
**Symptom:** Worker logs show `'str' object has no attribute 'get'`
**Root cause:** asyncpg returns JSONB columns as strings instead of parsed dicts
**Solution:** Configure asyncpg connection pool with JSONB codec:
```python
async def _init_connection(conn: asyncpg.Connection) -> None:
    await conn.set_type_codec(
        "jsonb",
        encoder=json.dumps,
        decoder=json.loads,
        schema="pg_catalog",
    )

pool = await asyncpg.create_pool(..., init=_init_connection)
```

#### 4. Missing Restaurant Configuration
**Symptom:** Worker logs show `restaurant_config_not_found`
**Root cause:** Test restaurant ID not configured in database
**Solution:** The `docker_services` fixture automatically sets up test restaurant config. If using custom restaurant IDs, ensure they're configured in the test database.

## Performance

### Expected Test Duration

| Test | Duration | Notes |
|------|----------|-------|
| Happy Path | 10-20s | Depends on worker processing speed |
| Card Decline | 10-20s | Similar to happy path |
| Invalid Token | 10-20s | Worker must attempt and fail |
| Service Down | 30-40s | Includes container stop/start |
| Concurrent | 15-25s | Parallel processing helps |
| Fast Path | 5-15s | May complete in single request |
| Idempotency | 10-20s | Similar to happy path |

**Full Suite:** ~2-4 minutes

### Optimization Tips

1. **Use shared docker_services fixture** - Reuse containers across tests
2. **Run tests serially** - Avoid database conflicts
3. **Keep containers running** - Between test runs during development
4. **Pre-build images** - Use `--build` only when code changes

## CI/CD Integration

### GitHub Actions Example

```yaml
name: E2E Tests

on: [push, pull_request]

jobs:
  e2e:
    runs-on: ubuntu-latest

    steps:
      - uses: actions/checkout@v3

      - name: Start E2E Services
        run: |
          cd infrastructure/docker
          docker-compose -f docker-compose.e2e.yml up -d --build

      - name: Wait for Services to be Ready
        run: |
          # Wait for health checks (docker-compose handles dependencies)
          timeout 180 bash -c 'until docker ps | grep -q "healthy.*authorization-api"; do sleep 5; done'

      - name: Install Tox
        run: pip install tox

      - name: Run E2E Tests
        run: |
          cd tests
          tox -e e2e

      - name: Show Logs on Failure
        if: failure()
        run: |
          cd infrastructure/docker
          docker-compose -f docker-compose.e2e.yml logs

      - name: Cleanup
        if: always()
        run: |
          cd infrastructure/docker
          docker-compose -f docker-compose.e2e.yml down -v
```

**Note:** No manual initialization scripts needed! Docker Compose handles everything.

## Coverage

These E2E tests provide comprehensive validation of:

- ✅ Real HTTP requests over network
- ✅ Complete service-to-service communication
- ✅ Payment token encryption/decryption
- ✅ SQS message delivery and consumption
- ✅ Outbox processor reliability
- ✅ Worker processing logic
- ✅ Database transactions and read models
- ✅ Error handling and retries
- ✅ Concurrent request handling
- ✅ Fast path optimization
- ✅ Idempotency guarantees
- ✅ Service resilience and degradation

## Related Documentation

- **Authorization API:** `services/authorization-api/README.md`
- **Auth Processor Worker:** `services/auth-processor-worker/README.md`
- **Payment Token Service:** `services/payment-token/README.md`
- **Docker Setup:** `infrastructure/docker/README.md`

## References

- **Issue:** i-qu3q - Write full dockerized end-to-end tests
- **Dependency:** i-3zhb - Docker infrastructure setup

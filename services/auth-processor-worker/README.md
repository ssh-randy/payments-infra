# Auth Processor Worker Service

Background worker service that processes payment authorization requests by dequeuing from SQS, calling payment processors, and recording results atomically.

## Overview

The Auth Processor Worker implements exactly-once processing with distributed locking and atomic event + read model updates. It:

- Consumes authorization requests from an SQS FIFO queue
- Acquires distributed locks to prevent duplicate processing
- Decrypts payment tokens via the Payment Token Service
- Calls payment processors (Stripe, Chase, etc.)
- Records results atomically (event + read model in same transaction)
- Handles retries with exponential backoff
- Manages terminal failures via dead letter queue

## Architecture

```
SQS Queue → Lock Acquisition → Token Decryption → Processor Call → Atomic Write → Delete Message
```

## Project Structure

```
src/auth_processor_worker/
├── __init__.py
├── main.py                    # Entry point and worker orchestration
├── config.py                  # Configuration management
├── logging_config.py          # Structured logging setup
├── models/                    # Domain models and events
├── infrastructure/            # Database, SQS, external clients
├── processors/                # Payment processor integrations
└── handlers/                  # Business logic handlers
```

## Setup

### Prerequisites

- Python 3.11+
- Poetry
- PostgreSQL (payment events database)
- LocalStack (for local development)

### Installation

```bash
cd services/auth-processor-worker
poetry install
```

### Configuration

Copy the environment template and configure:

```bash
cp .env.template .env
# Edit .env with your configuration
```

Key configuration:

- `DATABASE_URL`: PostgreSQL connection for events and read models
- `WORKER__SQS_QUEUE_URL`: SQS FIFO queue URL
- `PAYMENT_TOKEN_SERVICE__BASE_URL`: Payment Token Service endpoint
- `STRIPE__API_KEY`: Stripe API key

## Running Locally

### With Docker Compose

```bash
cd infrastructure/docker
docker-compose up auth-processor-worker
```

### Standalone

```bash
cd services/auth-processor-worker
poetry run python -m auth_processor_worker.main
```

## Testing

```bash
# Run all tests
poetry run pytest

# Run with coverage
poetry run pytest --cov=auth_processor_worker --cov-report=term-missing

# Run specific test types
poetry run pytest tests/unit/
poetry run pytest tests/integration/
```

## Development

### Code Quality

```bash
# Format code
poetry run black src/ tests/

# Lint
poetry run ruff check src/ tests/

# Type check
poetry run mypy src/
```

## Key Features

### Exactly-Once Processing

Distributed locks ensure only one worker processes each auth request, preventing duplicate processor calls.

### Atomic Transactions

Events and read model updates are written in the same transaction, eliminating eventual consistency delays.

### Retry Logic

Transient failures (timeouts, 500 errors) are retried with exponential backoff up to MAX_RETRIES.

### Terminal Failures

Non-retryable errors (invalid token, expired token, max retries) are sent to dead letter queue.

### Graceful Shutdown

Signal handlers (SIGTERM, SIGINT) ensure clean shutdown with proper lock release.

## Dependencies

- **Payment Token Service**: Decrypts payment tokens
- **Payment Processors**: Stripe, Chase, Worldpay APIs
- **PostgreSQL**: Shared event store and read models
- **SQS**: Authorization request queue

## Monitoring

The service emits structured JSON logs with:

- Correlation IDs for request tracing
- Processing metrics (latency, success/failure rates)
- Retry counts and error details
- Lock acquisition/release events

## Related Services

- **Authorization API**: Enqueues auth requests
- **Payment Token Service**: Provides token decryption
- **Processor integrations**: Stripe, Chase, etc.

## License

Proprietary

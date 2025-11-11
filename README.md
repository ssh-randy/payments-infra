# Payments Infrastructure

Microservices monorepo for payment processing infrastructure with event sourcing, built in Python.

## Architecture Overview

This monorepo contains three core microservices that work together to process payment authorizations:

### Services

1. **Payment Token Service** (`services/payment-token/`)
   - PCI-compliant tokenization service
   - Encrypts and stores sensitive payment card data
   - Issues secure tokens for use by other services
   - Isolated database for PCI compliance

2. **Authorization API** (`services/authorization-api/`)
   - Main API entry point for payment authorization requests
   - Event sourcing with read models
   - Transactional outbox pattern for reliable queue delivery
   - Handles status queries and void operations

3. **Auth Processor Worker** (`services/auth-processor-worker/`)
   - Background worker that processes authorization requests from SQS
   - Integrates with payment processors (Stripe, Chase, etc.)
   - Updates event store and read models on completion

### Shared Components

- **`shared/protos/`**: Protobuf definitions for consistent data models
- **`shared/python/payments_common/`**: Shared utilities (database, logging, auth)
- **`shared/python/payments_proto/`**: Generated protobuf Python code

## Technology Stack

- **Language**: Python 3.11+
- **Package Manager**: Poetry
- **API Framework**: FastAPI
- **Database**: PostgreSQL (Aurora recommended for production)
- **Queue**: AWS SQS (FIFO for auth requests)
- **Event Store**: PostgreSQL with append-only event log
- **Protobuf**: Protocol Buffers for serialization
- **Container**: Docker + ECS (AWS)
- **IaC**: Terraform

## Quick Start

### Prerequisites

- Python 3.11+
- Poetry
- Docker and Docker Compose
- Protocol Buffers compiler (`protoc`)

### Setup

1. Clone the repository
2. Install dependencies and generate protobuf code:

```bash
make setup
```

3. Start local development environment:

```bash
make docker-up
```

This will start:
- PostgreSQL (main database on port 5432)
- PostgreSQL (tokens database on port 5433)
- LocalStack (AWS services emulation)
- All three microservices

4. Seed test data:

```bash
make seed-data
```

### Available Make Commands

```bash
make help          # Show all available commands
make setup         # Initial setup (install + generate protos)
make proto         # Generate protobuf code
make install       # Install all dependencies
make test          # Run all tests
make test-unit     # Run unit tests only
make test-integration  # Run integration tests
make test-e2e      # Run end-to-end tests
make lint          # Run linters (ruff)
make format        # Format code (black + ruff)
make typecheck     # Run type checking (mypy)
make docker-up     # Start local environment
make docker-down   # Stop local environment
make docker-logs   # View docker-compose logs
make seed-data     # Seed test data
make clean         # Clean generated files and caches
make ci            # Run all CI checks
```

## Project Structure

```
payments-infra/
├── services/               # Microservices
│   ├── payment-token/     # PCI tokenization service
│   ├── authorization-api/ # Main API + outbox processor
│   └── auth-processor-worker/  # Background worker
│
├── shared/                # Shared code
│   ├── protos/           # Protobuf definitions
│   └── python/
│       ├── payments_common/   # Shared utilities
│       └── payments_proto/    # Generated proto code
│
├── infrastructure/        # Infrastructure as code
│   ├── terraform/        # Terraform modules
│   └── docker/           # Docker configs
│
├── tests/                # Cross-service tests
│   ├── integration/
│   └── e2e/
│
├── scripts/              # Utility scripts
│   ├── generate_protos.sh
│   ├── setup_local_db.sh
│   └── seed_test_data.py
│
├── docs/                 # Documentation
├── Makefile             # Common tasks
└── docker-compose.yml   # Local development
```

## Development Workflow

### Adding a New Service

1. Create service directory under `services/`
2. Set up Python package structure with Poetry
3. Add Dockerfile
4. Update `docker-compose.yml`
5. Update Makefile commands

### Working with Protobufs

1. Edit `.proto` files in `shared/protos/payments/v1/`
2. Regenerate Python code: `make proto`
3. Generated code will be in `shared/python/payments_proto/`

### Running Tests

```bash
# All tests
make test

# Specific service
cd services/payment-token && poetry run pytest

# With coverage
cd services/payment-token && poetry run pytest --cov
```

### Code Quality

```bash
# Format code
make format

# Run linters
make lint

# Type check
make typecheck

# All CI checks
make ci
```

## Architecture Patterns

### Event Sourcing
- All state changes recorded as immutable events in `payment_events` table
- Events use protobuf serialization for schema evolution
- Read models materialized from events for fast queries

### Transactional Outbox
- Events + outbox entries written in single transaction
- Background processor sends to SQS reliably
- At-least-once delivery guarantee

### CQRS
- Write model: Event store (append-only)
- Read model: `auth_request_state` table (optimized for queries)
- Synchronous projection updates

## Service Communication

- **External**: REST API with JSON (Authorization API)
- **Internal**: REST with protobuf serialization
- **Async**: SQS FIFO queues for background processing

## Database Schema

### Main Database (`payment_events_db`)
- `payment_events`: Event store (append-only)
- `outbox`: Transactional outbox for queue delivery
- `auth_request_state`: Read model for auth status
- `restaurant_payment_configs`: Payment processor configurations
- `auth_idempotency_keys`: Idempotency tracking
- `auth_processing_locks`: Distributed locking

### Tokens Database (`payment_tokens_db`)
- Isolated database for PCI compliance
- Only accessible by Payment Token Service
- Encrypted at rest with AWS KMS

### Database Migrations

Database schemas are managed with Alembic migrations:

```bash
# Run migrations for payment_events_db
./scripts/migrate_payment_events_db.sh

# Run migrations for payment_tokens_db (token service)
./scripts/migrate_payment_token_db.sh

# Reset payment_events_db (local dev only - destructive!)
./scripts/reset_payment_events_db.sh
```

See `infrastructure/migrations/README.md` for detailed migration documentation.

## Deployment

### Local Development
```bash
make docker-up
```

### Production (AWS ECS)
Infrastructure managed with Terraform. See `infrastructure/terraform/` for details.

Key components:
- ECS Fargate for container orchestration
- Aurora PostgreSQL for databases
- SQS FIFO queues for async processing
- Application Load Balancer for API Gateway
- CloudWatch for logging and monitoring

## Monitoring

Key metrics to monitor:
- Auth request latency (p50, p95, p99)
- SQS queue depth
- Outbox processing lag
- Worker processing rate
- Error rates and DLQ depth
- Database connection pool usage

## Security

- PCI DSS compliance for tokenization service
- All payment data encrypted at rest (AWS KMS)
- TLS 1.3 for all connections
- No PII in application logs
- JWT-based API authentication
- Isolated network zones for PCI data

## Contributing

1. Create a feature branch
2. Make changes and add tests
3. Run `make ci` to ensure all checks pass
4. Submit a pull request

## Documentation

- [Architecture Deep Dive](docs/specs/)
- [API Documentation](services/authorization-api/README.md)
- [Event Catalog](docs/events.md)
- [Runbooks](docs/runbooks/)

## Troubleshooting

### Docker Issues
```bash
# Clean restart
make docker-down
docker system prune -f
make docker-up
```

### Database Issues
```bash
# Recreate databases
make docker-down
docker volume rm payments-postgres_data payments-postgres-tokens_data
make docker-up
```

### Protobuf Issues
```bash
# Regenerate proto code
make clean
make proto
```

## License

[Your License Here]

## Support

For questions or issues, please contact [your team contact info] or open an issue in this repository.

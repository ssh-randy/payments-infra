# Payment Token Service

PCI-compliant microservice for tokenizing payment data from POS hardware.

## Overview

This service handles:
- Device-based decryption of payment data
- Re-encryption with rotating keys
- Token storage and retrieval
- Secure internal decryption API for authorized workers

## Database Setup

### Prerequisites

- PostgreSQL 14+
- Python 3.11+
- Poetry

### Running Migrations

**Initial Setup:**
```bash
# From project root
./scripts/migrate_payment_token_db.sh
```

**Or manually from the service directory:**
```bash
cd services/payment-token
poetry install
poetry run alembic upgrade head
```

### Resetting Database (Local Testing)

**WARNING: This will delete all data!**

```bash
# From project root
./scripts/reset_payment_token_db.sh
```

This script will:
1. Downgrade all migrations (drop tables)
2. Upgrade to latest (recreate tables)

### Creating New Migrations

```bash
cd services/payment-token
poetry run alembic revision -m "Description of changes"
# Edit the generated migration file in alembic/versions/
poetry run alembic upgrade head
```

### Viewing Migration History

```bash
cd services/payment-token
poetry run alembic history
poetry run alembic current
```

## Database Schema

The service uses 4 main tables:

1. **payment_tokens** - Encrypted payment tokens
2. **token_idempotency_keys** - Idempotency tracking (24hr window)
3. **encryption_keys** - Key version metadata for rotation
4. **decrypt_audit_log** - PCI compliance audit trail (7 year retention)

## Configuration

Environment variables (can be set in `.env`):

```bash
DATABASE_URL=postgresql://postgres:postgres@localhost:5432/payment_tokens
DEBUG=false
ENVIRONMENT=development
DEFAULT_TOKEN_TTL_HOURS=24
BDK_KMS_KEY_ID=arn:aws:kms:us-east-1:...
CURRENT_KEY_VERSION=v1
```

## Development

### Install Dependencies

```bash
poetry install
```

### Run Tests

```bash
poetry run pytest
```

### Type Checking

```bash
poetry run mypy src
```

### Code Formatting

```bash
poetry run black src tests
poetry run ruff check src tests
```

## Integration Testing

For integration tests that require a clean database:

```python
from payment_token.infrastructure.database import reset_db, get_db_session

# In test setup
reset_db()

# Or use the session context manager
with get_db_session() as session:
    # Your test code here
    pass
```

## Architecture

- **Domain Layer**: `src/payment_token/domain/` - Business logic
- **Infrastructure Layer**: `src/payment_token/infrastructure/` - Database, KMS
- **API Layer**: `src/payment_token/api/` - FastAPI/gRPC endpoints

## Security

- Separate VPC and database instance (PCI compliance)
- BDK never leaves AWS KMS
- Derived keys exist only in memory
- All decrypt operations are audit logged
- Mutual TLS for internal endpoints

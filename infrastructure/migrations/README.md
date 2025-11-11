# Payment Events Database Migrations

This directory contains Alembic migrations for the `payment_events_db` database, which is shared by the Authorization API and Auth Processor Worker services.

## Database Schema

The `payment_events_db` contains the following tables:

1. **payment_events** - Event store (append-only) for all payment events
2. **auth_request_state** - Read model for fast queries on authorization request status
3. **outbox** - Transactional outbox for reliable queue delivery
4. **auth_idempotency_keys** - Request idempotency tracking
5. **restaurant_payment_configs** - Payment processor configurations per restaurant
6. **auth_processing_locks** - Distributed locking for workers

See `specs/shared_infrastructure_components.md` for detailed schema documentation.

## Running Migrations

### Using the Helper Script (Recommended)

```bash
# From project root
./scripts/migrate_payment_events_db.sh
```

This script will:
- Use the default connection: `postgresql://postgres:password@localhost:5432/payment_events_db`
- Or use the `DATABASE_URL` environment variable if set
- Run all pending migrations

### Manual Migration

```bash
cd infrastructure/migrations

# Run all pending migrations
poetry run alembic upgrade head

# Rollback one migration
poetry run alembic downgrade -1

# View migration history
poetry run alembic history

# View current version
poetry run alembic current
```

### Environment Variables

- `DATABASE_URL` - Override the default database connection string
  - Default: `postgresql://postgres:password@localhost:5432/payment_events_db`
  - Example: `DATABASE_URL=postgresql://user:pass@host:port/dbname poetry run alembic upgrade head`

## Resetting the Database (Local Development Only)

To completely reset the `payment_events_db` database:

```bash
# From project root
./scripts/reset_payment_events_db.sh
```

⚠️ **WARNING**: This will delete all data! Only use for local development.

## Creating New Migrations

```bash
cd infrastructure/migrations

# Create a new migration
poetry run alembic revision -m "description_of_changes"

# Edit the generated file in alembic/versions/
# Implement upgrade() and downgrade() functions

# Test the migration
poetry run alembic upgrade head
poetry run alembic downgrade -1
poetry run alembic upgrade head
```

## Seed Data

The initial migration includes seed data for local development:

- **Test Restaurant**: `00000000-0000-0000-0000-000000000001`
  - Processor: Stripe
  - Config: Test API key and statement descriptor

## Docker Integration

When using Docker Compose, migrations are NOT run automatically. You must run them manually:

```bash
# Start the database
docker-compose -f infrastructure/docker/docker-compose.yml up -d postgres

# Run migrations
./scripts/migrate_payment_events_db.sh
```

## Troubleshooting

### "relation already exists"
The migration has already been run. Check current version with `alembic current`.

### "can't connect to database"
Ensure the PostgreSQL container is running: `docker ps | grep payments-postgres`

### "No such file or directory: alembic.ini"
Run commands from `infrastructure/migrations/` directory or use the helper scripts.

## Migration Best Practices

1. **Never modify existing migrations** - Create new migrations for schema changes
2. **Always implement downgrade()** - Ensure migrations can be rolled back
3. **Test migrations** - Always test upgrade and downgrade before committing
4. **Use transactions** - Alembic uses transactions by default, keep it that way
5. **Document complex changes** - Add comments for non-obvious migration logic

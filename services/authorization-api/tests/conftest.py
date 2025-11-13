"""Pytest configuration and shared fixtures for all tests.

This module provides shared test fixtures including:
- Test database setup with Alembic migrations
- Async database connection management
- Sample test data
- Service availability checks for integration tests
"""

import asyncio
import os
import sys
import uuid
from pathlib import Path
from subprocess import run

import asyncpg
import pytest
import pytest_asyncio
from alembic import command
from alembic.config import Config

# Add src and shared to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))
sys.path.insert(
    0, "/Users/randy/sudocodeai/demos/payments-infra/shared/python"
)
sys.path.insert(
    0, "/Users/randy/sudocodeai/demos/payments-infra/shared/python/payments_proto"
)


# Test database URL - use a separate test database
TEST_DATABASE_URL = os.getenv(
    "TEST_DATABASE_URL",
    "postgresql://postgres:password@localhost:5432/payment_events_test",
)


def check_service_availability():
    """Check if required services for integration tests are available.

    This function checks:
    - PostgreSQL is running and accessible
    - LocalStack is running (for integration tests)

    If services are not available, it provides helpful error messages.
    """
    import socket

    errors = []

    # Check PostgreSQL
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(1)
        result = sock.connect_ex(('localhost', 5432))
        sock.close()

        if result != 0:
            errors.append(
                "PostgreSQL is not running on localhost:5432\n"
                "  Start services with:\n"
                "    cd ../../infrastructure/docker\n"
                "    docker-compose up -d postgres localstack"
            )
    except Exception as e:
        errors.append(f"Failed to check PostgreSQL: {e}")

    # Check LocalStack (only for integration tests marked with @pytest.mark.integration)
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(1)
        result = sock.connect_ex(('localhost', 4566))
        sock.close()

        if result != 0:
            errors.append(
                "LocalStack is not running on localhost:4566\n"
                "  This is required for integration tests that use SQS.\n"
                "  Start services with:\n"
                "    cd ../../infrastructure/docker\n"
                "    docker-compose up -d postgres localstack"
            )
    except Exception as e:
        errors.append(f"Failed to check LocalStack: {e}")

    if errors:
        error_message = "\n\n" + "="*80 + "\n"
        error_message += "ERROR: Required services are not available for integration tests\n"
        error_message += "="*80 + "\n\n"
        error_message += "\n\n".join(errors)
        error_message += "\n\n" + "="*80 + "\n"
        error_message += "See tests/README.md for more details on running integration tests.\n"
        error_message += "="*80 + "\n"
        pytest.exit(error_message, returncode=1)


@pytest.fixture(scope="session", autouse=True)
def check_services_for_integration_tests(request):
    """Check service availability before running integration tests.

    This fixture runs automatically for all test sessions.
    It only checks services if integration tests are being run.
    """
    # Check if we're running integration tests
    integration_tests = False
    for item in request.session.items:
        if item.get_closest_marker("integration"):
            integration_tests = True
            break

    # Only check services if running integration tests
    if integration_tests:
        check_service_availability()


@pytest_asyncio.fixture(scope="session")
async def setup_test_database():
    """Set up test database with Alembic migrations.

    This fixture:
    1. Creates test database if it doesn't exist
    2. Runs Alembic migrations to set up schema
    3. Yields for tests
    4. Cleans up after all tests complete
    """
    # Parse database URL to get connection details
    # postgresql://user:password@host:port/dbname
    parts = TEST_DATABASE_URL.replace("postgresql://", "").split("@")
    user_pass = parts[0].split(":")
    host_port_db = parts[1].split("/")
    host_port = host_port_db[0].split(":")

    user = user_pass[0]
    password = user_pass[1]
    host = host_port[0]
    port = host_port[1] if len(host_port) > 1 else "5432"
    dbname = host_port_db[1]

    # Connect to postgres database to create test database
    postgres_url = f"postgresql://{user}:{password}@{host}:{port}/postgres"

    try:
        conn = await asyncpg.connect(postgres_url)

        # Drop and recreate test database
        await conn.execute(f'DROP DATABASE IF EXISTS "{dbname}"')
        await conn.execute(f'CREATE DATABASE "{dbname}"')

        await conn.close()
    except Exception as e:
        print(f"Warning: Could not recreate database: {e}")

    # Run Alembic migrations
    migrations_dir = Path(__file__).parent.parent.parent.parent / "infrastructure" / "migrations"
    alembic_cfg = Config(str(migrations_dir / "alembic.ini"))
    alembic_cfg.set_main_option("script_location", str(migrations_dir / "alembic"))
    alembic_cfg.set_main_option("sqlalchemy.url", TEST_DATABASE_URL)

    # Upgrade to head (create all tables)
    command.upgrade(alembic_cfg, "head")

    yield

    # Cleanup: drop database
    try:
        conn = await asyncpg.connect(postgres_url)
        await conn.execute(f'DROP DATABASE IF EXISTS "{dbname}"')
        await conn.close()
    except Exception as e:
        print(f"Warning: Could not drop database: {e}")


@pytest_asyncio.fixture(scope="function")
async def db_pool(setup_test_database):
    """Create a database connection pool for each test.

    This fixture:
    1. Creates a connection pool
    2. Yields the pool for the test
    3. Closes the pool after the test
    """
    pool = await asyncpg.create_pool(
        dsn=TEST_DATABASE_URL,
        min_size=1,
        max_size=5,
        command_timeout=30.0,
    )

    yield pool

    await pool.close()


@pytest_asyncio.fixture
async def db_conn(db_pool):
    """Get a database connection for each test.

    This fixture:
    1. Acquires a connection from the pool
    2. Yields the connection for the test
    3. Cleans up all test data after the test
    """
    conn = await db_pool.acquire()

    yield conn

    # Cleanup: delete all test data (but keep schema)
    await conn.execute("TRUNCATE auth_idempotency_keys CASCADE")
    await conn.execute("TRUNCATE outbox CASCADE")
    await conn.execute("TRUNCATE auth_request_state CASCADE")
    await conn.execute("TRUNCATE payment_events CASCADE")

    await db_pool.release(conn)


@pytest.fixture
def test_restaurant_id():
    """Standard test restaurant ID (valid UUID format)."""
    return uuid.UUID("00000000-0000-0000-0000-000000000001")


@pytest.fixture
def test_payment_token():
    """Standard test payment token."""
    return "pt_test_12345678"


@pytest.fixture
def test_idempotency_key():
    """Generate a unique idempotency key for each test."""
    return str(uuid.uuid4())
